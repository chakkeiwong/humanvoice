"""Missing reviews retain spent evidence and never turn rejection into acceptance."""

import json
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_codex_runtime

from humanvoice import automatic_reproduction
from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.commands.preflight_v2_command import JournaledCritic
from humanvoice.model import ModelAdapter
from tools import review_request_recovery as recovery
from tools.inventory_transport_continuation import canonical_request

codex = test_codex_runtime.codex


@pytest.mark.parametrize("defect", [None, "rejection", "response", "usage", "receipt", "message", "stderr", "mixed"])
def test_diagnostic_retry_never_overrides_native_rejection(defect):
    proof = {"eligible": False, "reason": "unclassified_provider_failure", "provider_receipt": "codex:synthetic"}
    events = [{"type": "error", "message": recovery.MESSAGE},
              {"type": "turn.failed", "error": {"message": recovery.MESSAGE}}]
    if defect in {"rejection", "response", "usage"}:
        proof["reason"] = "provider_rejection" if defect == "rejection" else "response_or_usage_present"
    if defect == "receipt":
        proof.pop("provider_receipt")
    if defect == "message":
        events[0]["message"] += " extra"
    if defect == "mixed":
        events.append({"type": "error", "message": "unexpected status 400"})
    assert recovery.diagnostic_retry(proof, events, "unknown error" if defect == "stderr" else "") is (defect is None)


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("message,response", [(recovery.MESSAGE, None), (recovery.MESSAGE, "partial answer"),
    ("unexpected status 400", None), ("stream disconnected before completion: invalid request", None)])
def test_native_receipt_classifies_without_enabling_general_retry(codex, tmp_path, message, response):
    request = canonical_request(None, (), {"prompt": "Synthetic independent review.",
        "purpose": "independent_rewrite_verification", "response_schema": "critic-response"})
    failure = {"purpose": request["purpose"], "message": message}
    if response:
        failure["response"] = response
    write_json(codex.settings, {"response": [], "transport_failures": [failure]})
    with pytest.raises(RuntimeError):
        codex.adapter.invoke(**request)
    reference = codex.adapter.last_runtime_record
    record, retained = recovery.MANUSCRIPT.capture_runtime(codex.snapshot, reference, tmp_path / "output")
    entry = {"invocation_id": "synthetic-allocation", "input_hash": "synthetic-contract"}
    call = {"status": "failed", "failure_kind": "invocation", "invocation_id": entry["invocation_id"],
            "request": request, "request_hash": digest(request), "call_contract_hash": entry["input_hash"],
            "runtime_record": reference, "response_text": retained["text"], "input_tokens": None, "output_tokens": None}
    output = tmp_path / "output"
    write_json(output / "calls/0000/call.json", call)
    plan = {"version": recovery.network.recovery.MANUSCRIPT_VERSION, "profile": codex.profile,
            "bindings": {"implementation": record["extensions"]["implementation"], "source": record["extensions"]["source_hash"]},
            "recovery": recovery.network.policy(14)}
    proof = recovery.network.failure_evidence(output, output / "calls/0000", plan, entry, runtime_snapshot=codex.snapshot)
    folder = codex.snapshot / Path(reference["path"]).parent
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
    assert not proof["eligible"]
    assert recovery.diagnostic_retry(proof, events, (folder / "stderr.log").read_text()) is (message == recovery.MESSAGE and response is None)


def review_proof():
    return {"interrupted_request": canonical_request(None, (), {"prompt": "retained candidate",
                "purpose": "independent_rewrite_verification", "response_schema": "critic-response"}),
            "completed": []}


def test_review_guard_stops_later_transmissions(tmp_path, monkeypatch):
    proof = review_proof()
    model = SimpleNamespace(snapshot_dir=tmp_path, last_runtime_record=None)
    calls = []
    native = ModelAdapter.invoke

    @wraps(native)
    def provider(model, *arguments, **keywords):
        calls.append(canonical_request(model, arguments, keywords))
        model.last_runtime_record = {"path": ".humanvoice/runtime/failed/record.json", "hash": "retained"}
        raise RuntimeError("retained provider failure")

    monkeypatch.setattr(ModelAdapter, "invoke", provider)
    monkeypatch.setattr(recovery, "verify_history", lambda *arguments: None)
    path = tmp_path / "journal.json"
    journal = JournaledCritic(SimpleNamespace(invoke=lambda **keywords: ModelAdapter.invoke(model, **keywords)), path, {})
    with recovery.guarded_reviews(tmp_path, proof):
        with pytest.raises(recovery.critic.CriticTransportStop, match="retained provider failure"):
            journal.invoke(**proof["interrupted_request"])
        with pytest.raises(recovery.critic.CriticTransportStop, match="already stopped"):
            ModelAdapter.invoke(model, **{**proof["interrupted_request"], "prompt": "next unit"})
    assert len(calls) == 1 and ModelAdapter.invoke is provider
    assert read_json(path)["status"] == "interrupted"
    assert read_json(path)["runtime_record"] == model.last_runtime_record


@pytest.mark.parametrize("change", ["prompt", "purpose", "snapshot", "completed"])
def test_review_guard_requires_exact_first_request(tmp_path, monkeypatch, change):
    proof = review_proof()
    request = deepcopy(proof["interrupted_request"])
    model = SimpleNamespace(snapshot_dir=tmp_path)
    if change == "prompt":
        request["prompt"] += " changed"
    if change == "purpose":
        request["purpose"] = "source_grounded_rewrite"
    if change == "snapshot":
        model.snapshot_dir = tmp_path / "other"
    if change == "completed":
        proof["completed"] = [{"request_hash": digest(request)}]
    monkeypatch.setattr(recovery, "verify_history", lambda *arguments: None)
    native = ModelAdapter.invoke

    @wraps(native)
    def provider(*arguments, **keywords):
        pytest.fail("Changed or completed request reached the provider")

    monkeypatch.setattr(ModelAdapter, "invoke", provider)
    with recovery.guarded_reviews(tmp_path, proof):
        with pytest.raises(ValueError, match="changed its first request"):
            ModelAdapter.invoke(model, **request)


@pytest.mark.parametrize("defect", [None, "transmitted", "answer", "usage", "semantic"])
def test_review_denials_preserve_failed_receipt(tmp_path, monkeypatch, defect):
    requests = {f"unit-{index:03d}": canonical_request(None, (), {"prompt": f"candidate {index}",
        "purpose": "independent_rewrite_verification", "response_schema": "critic-response"}) for index in range(1, 15)}
    reference = {"path": ".humanvoice/runtime/failed/record.json", "hash": "original"}
    failed = {"request": requests["unit-001"], "runtime_record": reference}
    for position, (unit, request) in enumerate(requests.items()):
        path = tmp_path / ".humanvoice/preflight/attempts" / unit / "001-call.json"
        journal = {"unit_id": unit, "request": request, "status": "failed", "prompt_hash": digest(request["prompt"]),
                   "runtime_record": reference if position == 0 else None,
                   "error": "New request cannot follow an unresolved non-size failure"}
        if position == 1:
            if defect == "transmitted":
                journal["runtime_record"] = reference
            if defect == "answer":
                journal["raw_response"] = "judgment"
            if defect == "usage":
                journal["input_tokens"] = 0
        write_json(path, journal)
        write_json(tmp_path / ".humanvoice/preflight" / (unit + ".json"),
                   {"is_acceptable": False, "failure_stage": "critic_semantic" if defect == "semantic" else "critic_transport"})
    monkeypatch.setattr(recovery.semantic, "unit_requests", lambda snapshot: requests)
    if defect:
        with pytest.raises(ValueError):
            recovery.denial_journals(tmp_path, failed)
        return
    paid = tmp_path / ".humanvoice/preflight/attempts/unit-001/001-call.json"
    original = paid.read_bytes()
    rows = recovery.denial_journals(tmp_path, failed)
    assert len(rows) == 13
    recovery.critic.archive_denials(tmp_path / "evidence", tmp_path, {"no_transmission": rows})
    assert paid.read_bytes() == original
    for row in rows:
        destination = tmp_path / ".humanvoice/preflight/denied-history" / Path(row["path"]).relative_to(".humanvoice/preflight")
        assert digest(destination.read_bytes()) == row["sha256"] and not (tmp_path / row["path"]).exists()


def test_failure_summary_preserves_provider_cause(tmp_path):
    write_json(tmp_path / "allocation-ledger.json", {"calls": [{"invocation_id": "failed", "status": "incomplete", "usage": None}]})
    reference = {"path": ".humanvoice/runtime/failed/record.json", "hash": "retained"}
    write_json(tmp_path / "calls/0000/call.json", {"invocation_id": "failed", "request_hash": "original",
        "request": {"purpose": "independent_rewrite_verification"}, "runtime_record": reference})
    folder = tmp_path / "reproduction/replica/.humanvoice/runtime/failed"
    folder.mkdir(parents=True)
    (folder / "events.jsonl").write_text(json.dumps({"type": "error", "message": recovery.MESSAGE}) + "\n")
    summary = recovery.failure_summary(tmp_path)
    assert summary["diagnostics"] == [recovery.MESSAGE]
    assert summary["unknown_charge_retained"] and summary["runtime_record"] == reference


def test_review_pipeline_restores_native_functions(monkeypatch, tmp_path):
    from tools import automatic_reproduction_worker, parallel_verification_replay

    @contextmanager
    def prior(**keywords):
        yield

    monkeypatch.setattr(recovery.previous, "pipeline", prior)
    before = (recovery.MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for,
              automatic_reproduction._command, automatic_reproduction._observations,
              automatic_reproduction.validate_accounted_calls, parallel_verification_replay.verify_settlement)
    with pytest.raises(RuntimeError, match="synthetic stop"):
        with recovery.pipeline():
            assert automatic_reproduction._command is not before[2]
            raise RuntimeError("synthetic stop")
    assert before == (recovery.MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for,
              automatic_reproduction._command, automatic_reproduction._observations,
              automatic_reproduction.validate_accounted_calls, parallel_verification_replay.verify_settlement)


def test_review_controller_preserves_successor_bound(tmp_path, monkeypatch):
    from tools import run_review_request_program_20261020 as controller

    source = tmp_path / "snapshot"
    (source / "release/immutable-packet").mkdir(parents=True)
    evidence = tmp_path / "evidence"
    monkeypatch.setattr(controller, "BASE", tmp_path)
    monkeypatch.setattr(controller, "EVIDENCE", evidence)
    monkeypatch.setattr(controller, "PROGRESS", tmp_path / "progress.json")
    monkeypatch.setattr(controller, "refresh", lambda *arguments: None)
    monkeypatch.setattr(recovery, "predecessor_evidence", lambda: {"snapshot": str(source), "remaining_calls": 41})
    write_json(controller.PROGRESS, {})
    calls = []
    campaign = SimpleNamespace(SUFFIX="retained", script=lambda *arguments: calls.append(arguments),
        manuscript=lambda *arguments: calls.append(arguments))
    result = controller.benchmark_chain("held-out", {}, campaign, None)
    prepare, execute = calls
    assert prepare[prepare.index("--max-calls") + 1] == 41
    assert prepare[prepare.index("--technical-predecessor") + 1] == recovery.PRIOR
    assert execute[3] == 41 and campaign.SUFFIX == "retained"
    assert result["snapshot"] == source
    assert read_json(controller.PROGRESS)["reproductions"]["held-out"]["full_call_bound"] == 55


@pytest.mark.parametrize("interrupted", [False, True])
def test_review_controller_routes_and_restores(monkeypatch, interrupted):
    from tools import run_review_request_program_20261020 as controller

    previous, scope = controller.previous, controller.scope
    monkeypatch.setattr(controller, "refresh", lambda *arguments: None)
    before = (scope.RUNNER, previous.continuation, previous.EVIDENCE, previous.SUFFIX,
              previous.previous.continuation, previous.previous.benchmark_chain)

    def sequence():
        assert controller.ACTIVE
        assert scope.RUNNER.name == "review_request_runner.py"
        assert previous.previous.continuation is recovery
        assert previous.previous.benchmark_chain is controller.benchmark_chain
        assert previous.continuation.authority is recovery.previous.authority
        if interrupted:
            raise RuntimeError("synthetic stop")

    monkeypatch.setattr(previous.previous, "run", sequence)
    if interrupted:
        with pytest.raises(RuntimeError, match="synthetic stop"):
            controller.run()
    else:
        controller.run()
    assert before == (scope.RUNNER, previous.continuation, previous.EVIDENCE, previous.SUFFIX,
                      previous.previous.continuation, previous.previous.benchmark_chain)
    assert not controller.ACTIVE
