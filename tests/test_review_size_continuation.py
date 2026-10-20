"""Review-only continuation cannot repeat completed work or weaken native admission."""

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from functools import wraps
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_codex_runtime
from test_assembled_budget_runtime import authorized
from test_assembled_size_recovery import review_job

from humanvoice import automatic_reproduction
from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.model import ModelAdapter
from tools import assembled_size_recovery as recovery
from tools import reproduction_review_size_recovery as continuation
from tools.inventory_transport_continuation import canonical_request

codex = test_codex_runtime.codex
pytest_plugins = ("test_semantic_repair_protocol",)


@pytest.fixture
def guarded(tmp_path, monkeypatch):
    parent = review_job()
    child = recovery.partition(parent, digest(parent["prompt"]), 0)[0]
    request = canonical_request(None, (), {"prompt": child["prompt"],
        "purpose": "assembled_candidate_verification", "response_schema": "critic-response"})
    proof = {"completed": [], "failed_job": parent, "first_request_hash": digest(request)}
    calls = []
    original = ModelAdapter.invoke

    @wraps(original)
    def invoke(model, *arguments, **keywords):
        calls.append(canonical_request(model, arguments, keywords))
        return "synthetic response"

    monkeypatch.setattr(ModelAdapter, "invoke", invoke)
    monkeypatch.setattr(continuation, "verify_retained", lambda *args: None)
    monkeypatch.setattr(continuation.semantic, "assembled_requests", lambda snapshot: [request])
    return SimpleNamespace(snapshot=tmp_path, proof=proof, request=request, calls=calls,
                           model=SimpleNamespace(snapshot_dir=tmp_path))


@pytest.mark.parametrize("defect", ["completed", "snapshot", "prompt", "writer", "parent", "duplicate"])
def test_review_guard_rejects_completed_or_changed_work(guarded, defect):
    fixture = guarded
    request = dict(fixture.request)
    if defect == "completed":
        fixture.proof["completed"] = [{"request_hash": digest(request)}]
    elif defect == "snapshot":
        fixture.model.snapshot_dir = fixture.snapshot / "other"
    elif defect == "prompt":
        request["prompt"] += " "
    elif defect == "writer":
        request["purpose"] = "source_grounded_rewrite"
    elif defect == "parent":
        request["prompt"] = fixture.proof["failed_job"]["prompt"]
    with continuation.guarded_reviews(fixture.snapshot, fixture.proof):
        if defect == "duplicate":
            ModelAdapter.invoke(fixture.model, **request)
        with pytest.raises(ValueError, match="exact remaining"):
            ModelAdapter.invoke(fixture.model, **request)
    assert len(fixture.calls) == (1 if defect == "duplicate" else 0)


def test_review_probe_reaches_exact_child_without_provider(guarded):
    fixture = guarded
    with continuation.guarded_reviews(fixture.snapshot, fixture.proof, probe=True) as (activity, boundary):
        with pytest.raises(boundary):
            ModelAdapter.invoke(fixture.model, **fixture.request)
    assert activity == [fixture.proof["first_request_hash"]] and not fixture.calls


def test_review_guard_stops_after_non_size_error(guarded, monkeypatch):
    fixture = guarded
    original = ModelAdapter.invoke

    @wraps(original)
    def invoke(*arguments, **keywords):
        raise RuntimeError("synthetic unknown failure")

    monkeypatch.setattr(ModelAdapter, "invoke", invoke)
    stop = continuation.previous.previous.critic.CriticTransportStop
    with continuation.guarded_reviews(fixture.snapshot, fixture.proof):
        with pytest.raises(stop, match="synthetic unknown"):
            ModelAdapter.invoke(fixture.model, **fixture.request)
        with pytest.raises(stop, match="already stopped"):
            ModelAdapter.invoke(fixture.model, **fixture.request)


def test_review_size_pipeline_restores_functions(monkeypatch):
    from tools import automatic_reproduction_worker, parallel_verification_replay

    @contextmanager
    def prior(**keywords):
        yield

    monkeypatch.setattr(continuation.previous, "pipeline", prior)
    before = (continuation.MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for,
              automatic_reproduction._command, ModelAdapter.invoke,
              automatic_reproduction.validate_accounted_calls, parallel_verification_replay.verify_settlement)
    with pytest.raises(RuntimeError, match="synthetic stop"):
        with continuation.pipeline():
            assert automatic_reproduction._command is not before[2]
            raise RuntimeError("synthetic stop")
    assert before == (continuation.MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for,
              automatic_reproduction._command, ModelAdapter.invoke,
              automatic_reproduction.validate_accounted_calls, parallel_verification_replay.verify_settlement)


@pytest.mark.parametrize("interrupted", [False, True])
def test_review_size_controller_routes_and_restores(monkeypatch, interrupted):
    from tools import run_review_size_20261020 as controller

    identifier, sized = controller.previous.previous.previous, controller.previous.previous.previous.previous
    monkeypatch.setattr(controller, "refresh", lambda *args: None)
    before = (controller.scope.RUNNER, identifier.continuation, sized.continuation, sized.benchmark_chain, sized.split_bound)

    def sequence():
        assert controller.ACTIVE
        assert controller.scope.RUNNER.name == "reproduction_review_size_runner.py"
        assert identifier.continuation is sized.continuation is continuation
        assert sized.benchmark_chain is controller.benchmark_chain
        assert sized.split_bound is controller.split_bound
        if interrupted:
            raise RuntimeError("synthetic stop")

    monkeypatch.setattr(sized, "run", sequence)
    if interrupted:
        with pytest.raises(RuntimeError, match="synthetic stop"):
            controller.run()
    else:
        controller.run()
    assert before == (controller.scope.RUNNER, identifier.continuation, sized.continuation, sized.benchmark_chain, sized.split_bound)
    assert not controller.ACTIVE


def test_activation_waits_for_in_progress_validation(tmp_path, monkeypatch):
    import sys
    from tools import run_review_size_20261020 as controller

    checkpoint = tmp_path / "validated.json"
    write_json(checkpoint, {})
    monkeypatch.setattr(sys, "argv", ["review-size-controller", "activate", "--live"])
    monkeypatch.setattr(controller, "BASE", tmp_path)
    monkeypatch.setattr(controller, "EVIDENCE", tmp_path)
    monkeypatch.setattr(controller, "PROBE", checkpoint)
    monkeypatch.setattr(controller, "PROOF", checkpoint)
    monkeypatch.setattr(controller.continuation, "DIAGNOSTIC", checkpoint)
    monkeypatch.setattr(controller.scope, "accounting_scope", nullcontext)
    monkeypatch.setattr(controller.continuation, "pipeline", nullcontext)
    monkeypatch.setattr(controller, "cached_parallel_verification", lambda **keywords: nullcontext())
    activity = []

    def verify(**keywords):
        activity.append("verified")
        return {"status": "pass", "regression_tests": 1}

    monkeypatch.setattr(controller, "verify", verify)
    monkeypatch.setattr(controller, "run", lambda: activity.append("activated"))
    monkeypatch.setattr(controller, "refresh", lambda *arguments: None)
    with (tmp_path / "inventory-prefix-controller.lock").open("a") as lock:
        controller.fcntl.flock(lock, controller.fcntl.LOCK_EX | controller.fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(controller.main)
            try:
                with pytest.raises(TimeoutError):
                    pending.result(timeout=0.2)
                assert not activity
            finally:
                controller.fcntl.flock(lock, controller.fcntl.LOCK_UN)
            assert pending.result(timeout=5) == 0
    assert activity == ["verified", "activated"]


@pytest.mark.parametrize("defect", [None, "phantom", "duplicate", "completed", "writer"])
def test_review_size_accounting_requires_exact_guarded_activity(tmp_path, monkeypatch, defect):
    proof = {"all_fresh_runtime_ids": ["inherited"], "completed": [{"request_hash": "old"}]}
    activity = {"status": "pass", "probe": False, "requests": ["new"]}
    evidence = {"calls": [{"journal": {"request_hash": "new",
        "request": {"purpose": "assembled_candidate_verification"}}}]}
    if defect == "phantom":
        activity["requests"].append("unallocated")
    elif defect == "duplicate":
        activity["requests"].append("new")
    elif defect == "completed":
        proof["completed"].append({"request_hash": "new"})
    elif defect == "writer":
        evidence["calls"][0]["journal"]["request"]["purpose"] = "source_grounded_rewrite"
    write_json(tmp_path / "review-size-execution.json", activity)
    monkeypatch.setattr(continuation, "validate_extension", lambda plan: plan)
    monkeypatch.setattr(continuation, "predecessor_evidence", lambda output: proof)
    monkeypatch.setattr(continuation, "verify_retained", lambda *args: None)
    monkeypatch.setattr(continuation.writer_repair, "NATIVES", (lambda *args: evidence,))
    plan = {"technical_restart": {"predecessor": "frozen"}}
    if defect:
        with pytest.raises(ValueError, match="review-only activity"):
            continuation.validate_accounted_calls(tmp_path, plan, {"inherited", "new"})
    else:
        assert continuation.validate_accounted_calls(tmp_path, plan, {"inherited", "new"}) == evidence


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_size_accounting_preserves_failed_charge(rejected, authorized, monkeypatch):
    import shutil
    from humanvoice import codex_runtime
    from humanvoice.runtime_admission import audit_activity
    from tools import assembled_budget_runtime as budget
    from tools import semantic_repair_protocol as protocol
    from tools import automatic_manuscript_stage as manuscript
    from tools.ensemble_closure_contract import AllocationLedger

    fixture = rejected
    shutil.copytree(fixture.snapshot, fixture.successor)
    snapshot = fixture.successor
    recovery.install(snapshot)
    budget.install(snapshot, authorized[0])
    original_launch, requests = codex_runtime.launch, []

    def launch(arguments, prompt, directory, timeout):
        request = read_json(directory / "inputs/api-request.json")
        purpose = request["purpose"]
        requests.append((purpose, digest(prompt)))
        settings = read_json(fixture.codex.settings)
        oversized = purpose == "assembled_candidate_verification" and "size partition" not in prompt
        write_json(fixture.codex.settings, settings | {"output_tokens": 40963 if oversized else 100})
        return original_launch(arguments, prompt, directory, timeout)

    monkeypatch.setattr(codex_runtime, "launch", launch)
    accounting = recovery.accounting
    output = snapshot.parent / "native-size-accounting"
    with accounting.network.pipeline(planning=[(snapshot, "humanize")], snapshots=[snapshot],
            authorization=authorized[0]), accounting.runtime.runtime_extension(), accounting.accounting_extension(), recovery.runtime():
        plan = manuscript.plan_for(snapshot, "humanize", 20, 0, recovery=True)
        plan.update(writer_size_extension=accounting.runtime.extension(), assembled_size_extension=recovery.extension())
        plan.pop("plan_identity")
        plan["plan_identity"] = digest(plan)
        review_scope = protocol.scope_for(snapshot)
        ledger = AllocationLedger(output / "allocation-ledger.json", plan)
        with accounting.accounted_model(output, plan, ledger), protocol.guarded_requests(snapshot, review_scope):
            assert protocol.run_consumer(output, snapshot, review_scope) == 0
        admission = audit_activity(snapshot, require_live=True)
        assert admission["status"] == "pass"
        assert all(count == 1 for count in admission["api_attempts"].values())
        protocol.retained_bytes(snapshot, review_scope, complete=True)
        ledger.reload()
        layout = recovery.attempt_layout(output, plan, ledger.record["calls"])
        assert len(layout["failures"]) == 1 and layout["child_calls"] == 2
        assert len(ledger.record["calls"]) == 5
        failed = [row for row in ledger.record["calls"] if row["status"] == "incomplete"]
        assert len(failed) == 1 and failed[0]["usage"] is None and failed[0]["reservation"] == 544000
        assert len(requests) == len(set(requests)) == 5
        replay = audit_activity(snapshot, require_live=True)
        assert replay["api_attempts"] == admission["api_attempts"] and len(requests) == 5
