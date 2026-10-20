"""Overload retries retain native evidence, finite bounds and completed work."""

import json
from contextlib import contextmanager

import pytest
import test_codex_runtime
from live_admission_fixture import responder
from test_assembled_budget_runtime import authorized
from test_assembled_size_recovery import review_job

from humanvoice import automatic_reproduction, codex_runtime
from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.model import ModelAdapter, ModelConfig
from tools import assembled_size_recovery as recovery
from tools import automatic_manuscript_stage as manuscript
from tools import overload_network_runtime as overload
from tools import reproduction_overload_recovery as continuation
from tools.ensemble_closure_contract import AllocationLedger
from tools.inventory_transport_continuation import canonical_request

codex = test_codex_runtime.codex


def test_overload_first_request_checked_before_transmission(monkeypatch):
    calls = []
    monkeypatch.setattr(ModelAdapter, "invoke", lambda *args, **kwargs: calls.append(kwargs))
    request = {"prompt": "interrupted", "purpose": "assembled_candidate_verification", "response_schema": "critic-response"}
    proof = {"first_request_hash": digest(canonical_request(None, (), request))}
    original = ModelAdapter.invoke
    with continuation.interrupted_request(proof):
        with pytest.raises(ValueError, match="exact interrupted"):
            ModelAdapter.invoke(None, **(request | {"prompt": "different"}))
        assert not calls
        ModelAdapter.invoke(None, **request)
        ModelAdapter.invoke(None, **(request | {"prompt": "subsequent"}))
    assert len(calls) == 2 and ModelAdapter.invoke is original


@pytest.mark.parametrize("defect", [None, "legacy", "changed", "near_match", "mixed", "warning", "receipt",
                                    "response", "usage", "reasoning", "auth", "process"])
def test_overload_requires_exact_prospective_native_evidence(tmp_path, monkeypatch, defect):
    native = {"eligible": False, "reason": "unclassified_provider_failure", "provider_receipt": "codex:synthetic"}
    if defect == "receipt":
        native.pop("provider_receipt")
    if defect in {"response", "usage", "reasoning", "auth", "process"}:
        native["reason"] = "provider_rejection" if defect == "auth" else "response_or_usage_present" if defect != "process" else "unproven_transport_failure"
    monkeypatch.setattr(overload, "NATIVES", (lambda *args, **kwargs: native,))
    directory = tmp_path / "calls/0000"
    write_json(directory / "call.json", {"runtime_record": {"path": ".humanvoice/runtime/synthetic/record.json"}})
    folder = tmp_path / "snapshots/primary/snapshot/.humanvoice/runtime/synthetic"
    folder.mkdir(parents=True)
    message = overload.DIAGNOSTIC + (" extra" if defect == "near_match" else "")
    events = [{"type": "error", "message": message},
              {"type": "turn.failed", "error": {"message": "unknown failure" if defect == "mixed" else message}}]
    if defect == "warning":
        events.append({"type": "item.completed", "item": {"type": "error", "message": "unexpected diagnostic"}})
    (folder / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n")
    plan = {} if defect == "legacy" else {"overload_network_extension": overload.extension()}
    if defect == "changed":
        plan["overload_network_extension"]["backoff_seconds"] = 0
        with pytest.raises(ValueError, match="prospective policy"):
            overload.failure_evidence(tmp_path, directory, plan, {})
        return
    for keywords in ({}, {"raw": lambda name: (tmp_path / name).read_bytes()}):
        proof = overload.failure_evidence(tmp_path, directory, plan, {}, **keywords)
        assert proof["eligible"] is (defect is None)


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("defect", [None, "response", "usage", "reasoning", "auth", "warning", "near_match", "legacy"])
def test_native_overload_retry_preserves_failed_charge(codex, authorized, monkeypatch, defect):
    injection = "    events += failure.get('extra_events', [])\n    events.extend(["
    codex.executable.write_text(codex.executable.read_text().replace("    events.extend([", injection))
    codex.profile["runtime"]["codex"]["executable_sha256"] = digest(codex.executable.read_bytes())
    codex.adapter.config = ModelConfig.from_profile()
    job = review_job()
    payload = json.loads(responder(codex.snapshot, {"messages": [{"content": job["prompt"]}]}))
    failure = {"purpose": "assembled_candidate_verification", "message": overload.DIAGNOSTIC}
    if defect == "response":
        failure["response"] = "Partial substantive answer"
    if defect == "usage":
        failure["extra_events"] = [{"type": "error", "message": overload.DIAGNOSTIC, "usage": {"input_tokens": 1}}]
    if defect in {"reasoning", "warning"}:
        failure["extra_events"] = [{"type": "item.completed", "item": {
            "type": "reasoning" if defect == "reasoning" else "error", "text": "Some reasoning", "message": "unknown diagnostic"}}]
    if defect == "auth":
        failure["message"] += " Authentication failed"
    if defect == "near_match":
        failure["message"] += " extra"
    write_json(codex.settings, {"response": payload, "transport_failures": [failure]})
    accounting, calls, waits = recovery.accounting, [], []
    original_launch, original_wait = codex_runtime.launch, accounting.network.wait_until

    def launch(arguments, prompt, directory, timeout):
        calls.append(digest(prompt))
        return original_launch(arguments, prompt, directory, timeout)

    def wait(path, failure_hash, failed_at):
        now = [failed_at]
        delays = []

        def sleep(seconds):
            now[0] += seconds
            delays.append(seconds)

        original_wait(path, failure_hash, failed_at, clock=lambda: now[0], sleep=sleep)
        waits.append(sum(delays))

    monkeypatch.setattr(codex_runtime, "launch", launch)
    monkeypatch.setattr(accounting.network, "wait_until", wait)
    monkeypatch.setattr(manuscript, "selected_profile", lambda: codex.profile)
    with accounting.network.pipeline(planning=[(codex.snapshot, "humanize")], snapshots=[codex.snapshot],
            authorization=authorized[0]), accounting.runtime.runtime_extension(), accounting.accounting_extension(), recovery.runtime(), overload.runtime():
        plan = manuscript.plan_for(codex.snapshot, "humanize", 15, 0, recovery=True)
        plan.update(writer_size_extension=accounting.runtime.extension(), assembled_size_extension=recovery.extension())
        if defect != "legacy":
            plan["overload_network_extension"] = overload.extension()
        plan.pop("plan_identity")
        plan["plan_identity"] = digest(plan)
        output = codex.snapshot.parent / "overload-accounting"
        ledger = AllocationLedger(output / "allocation-ledger.json", plan)
        with accounting.accounted_model(output, plan, ledger):
            if defect:
                with pytest.raises(RuntimeError):
                    codex.adapter.invoke(job["prompt"], purpose="assembled_candidate_verification", response_schema="critic-response")
            else:
                response = codex.adapter.invoke(job["prompt"], purpose="assembled_candidate_verification", response_schema="critic-response")
                assert not response.abstention
        ledger.reload()
        assert len(calls) == len(ledger.record["calls"]) == (1 if defect else 2)
        assert len(set(calls)) == 1
        assert waits == ([] if defect else [900])
        failed = ledger.record["calls"][0]
        assert failed["status"] == "incomplete" and failed["usage"] is None and failed["reservation"] == 544000
        proof = overload.failure_evidence(output, output / "calls/0000", plan, failed)
        assert proof["eligible"] is (defect is None)
        replay = recovery.attempt_layout(output, plan, ledger.record["calls"])
        assert replay["recoveries"] == (0 if defect else 1)
        if not defect:
            assert ledger.record["calls"][1]["status"] == "complete"
            retained = read_json(output / "retry-waits/0000.json")
            assert retained["eligible_after"] - retained["failed_at"] == 900


@pytest.mark.parametrize("roots,failures,maximum,valid", [(3, 2, 5, True), (0, 2, 5, False),
    (3, 0, 5, False), (3, 5, 5, False), (3, 6, 5, False), (True, 2, 5, False)])
def test_overload_bound_does_not_replenish(roots, failures, maximum, valid):
    if not valid:
        with pytest.raises(ValueError, match="inherited retry"):
            continuation.bounds(roots, failures, maximum)
    else:
        assert continuation.bounds(roots, failures, maximum) == {
            "remaining_calls": 45, "remaining_transport_extras": 3, "remaining_roots": 3}


def test_overload_pipeline_restores_functions(monkeypatch):
    from tools import automatic_reproduction_worker, parallel_verification_replay

    @contextmanager
    def prior(**keywords):
        yield

    monkeypatch.setattr(continuation.previous, "pipeline", prior)
    before = (continuation.MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for,
              automatic_reproduction._command, ModelAdapter.invoke,
              automatic_reproduction.validate_accounted_calls, parallel_verification_replay.verify_settlement,
              overload.network.failure_evidence)
    with pytest.raises(RuntimeError, match="synthetic stop"):
        with continuation.pipeline():
            assert overload.network.failure_evidence is overload.failure_evidence
            raise RuntimeError("synthetic stop")
    assert before == (continuation.MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for,
              automatic_reproduction._command, ModelAdapter.invoke,
              automatic_reproduction.validate_accounted_calls, parallel_verification_replay.verify_settlement,
              overload.network.failure_evidence)


@pytest.mark.parametrize("defect", [None, "phantom", "duplicate", "completed", "writer", "first"])
def test_overload_accounting_requires_exact_activity(tmp_path, monkeypatch, defect):
    proof = {"all_fresh_runtime_ids": ["inherited"], "completed": [{"request_hash": "old"}], "first_request_hash": "new"}
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
    elif defect == "first":
        proof["first_request_hash"] = "different"
    write_json(tmp_path / "review-size-execution.json", activity)
    monkeypatch.setattr(continuation, "validate_extension", lambda plan: plan)
    monkeypatch.setattr(continuation, "predecessor_evidence", lambda output: proof)
    monkeypatch.setattr(continuation.previous, "verify_retained", lambda *args: None)
    monkeypatch.setattr(continuation.writer_repair, "NATIVES", (lambda *args: evidence,))
    plan = {"technical_restart": {"predecessor": "frozen"}}
    if defect:
        with pytest.raises(ValueError, match="review-only activity"):
            continuation.validate_accounted_calls(tmp_path, plan, {"inherited", "new"})
    else:
        assert continuation.validate_accounted_calls(tmp_path, plan, {"inherited", "new"}) == evidence


@pytest.mark.parametrize("interrupted", [False, True])
def test_overload_controller_routes_and_restores(monkeypatch, interrupted):
    from tools import run_review_overload_20261021 as controller

    identifier, sized = controller.previous.previous.previous.previous, controller.previous.previous.previous.previous.previous
    monkeypatch.setattr(controller, "refresh", lambda *args: None)
    before = (controller.scope.RUNNER, controller.previous.continuation, identifier.continuation,
              sized.continuation, sized.benchmark_chain, sized.split_bound)

    def sequence():
        assert controller.ACTIVE
        assert controller.scope.RUNNER.name == "reproduction_overload_runner.py"
        assert controller.previous.continuation is identifier.continuation is sized.continuation is continuation
        assert sized.benchmark_chain is controller.previous.benchmark_chain
        if interrupted:
            raise RuntimeError("synthetic stop")

    monkeypatch.setattr(sized, "run", sequence)
    if interrupted:
        with pytest.raises(RuntimeError, match="synthetic stop"):
            controller.run()
    else:
        controller.run()
    assert before == (controller.scope.RUNNER, controller.previous.continuation, identifier.continuation,
              sized.continuation, sized.benchmark_chain, sized.split_bound)
    assert not controller.ACTIVE
