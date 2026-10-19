"""Identifier derivation preserves provider evidence and independent review gates."""

import json
from copy import deepcopy
from functools import wraps
from types import SimpleNamespace

import pytest

from humanvoice import artifacts, rewrite_engine
from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.model import ModelAdapter
from tools import writer_identifier_continuation as continuation
from tools import writer_identifier_repair as repair
from tools.inventory_transport_continuation import canonical_request

EXPECTED = "concept-b1b8a6d6d8bc3b81a6f13bf9"
WRONG = "concept-b1b8a6d8bc3b81a6f13bf9"
OTHER = "concept-" + "f" * 24


def payload():
    return {"replacement_latex": "Unchanged café $x=1$.",
            "output_spans": [{"span_id": "out-1", "text": "Unchanged café $x=1$."}],
            "concept_correspondences": [
                {"source_concept_id": WRONG, "output_span_ids": ["out-1"], "mapping_type": "retain",
                 "confidence": 0.99, "rationale": "Same source claim."},
                {"source_concept_id": OTHER, "output_span_ids": ["out-1"], "mapping_type": "retain"}]}


def test_identifier_correction_preserves_every_other_field():
    original = payload()
    before = deepcopy(original)
    changed, correction = repair.correct_payload(original, [EXPECTED, OTHER], [EXPECTED, OTHER])
    assert original == before
    assert correction == {"index": 0, "field": "source_concept_id", "original": WRONG, "corrected": EXPECTED}
    changed["concept_correspondences"][0]["source_concept_id"] = WRONG
    assert changed == original


def test_identifier_correction_rejects_ambiguous_ids():
    ambiguous = "concept-b1b8a6d0d8bc3b81a6f13bf9"
    with pytest.raises(ValueError, match="ambiguous"):
        repair.correct_payload(payload(), [EXPECTED, OTHER], [EXPECTED, OTHER, ambiguous])


@pytest.mark.parametrize("wrong", [EXPECTED, "concept-" + "e" * 24, WRONG[:-1],
                                   WRONG.replace("b1", "c1"), WRONG.upper(), None])
def test_identifier_correction_rejects_overreach(wrong):
    value = payload()
    value["concept_correspondences"][0]["source_concept_id"] = wrong
    with pytest.raises(ValueError):
        repair.correct_payload(value, [EXPECTED, OTHER], [EXPECTED, OTHER])


@pytest.mark.parametrize("change", ["duplicate", "missing", "two_errors", "extra"])
def test_identifier_correction_rejects_changed_membership(change):
    value = payload()
    if change == "duplicate":
        value["concept_correspondences"][1]["source_concept_id"] = WRONG
    elif change == "missing":
        value["concept_correspondences"].pop()
    elif change == "two_errors":
        value["concept_correspondences"][1]["source_concept_id"] = OTHER[:-1]
    else:
        value["concept_correspondences"].append(deepcopy(value["concept_correspondences"][0]))
    with pytest.raises(ValueError):
        repair.correct_payload(value, [EXPECTED, OTHER], [EXPECTED, OTHER])


@pytest.fixture
def native_case(snapshot_factory, monkeypatch):
    fixture = snapshot_factory(through="rewrite")
    session = artifacts.load_session(fixture.snapshot)
    unit = fixture.plan.units[0]
    context = rewrite_engine.build_rewrite_context(unit, fixture.baseline, fixture.plan,
        fixture.texts, {}, fixture.brief, fixture.policy)
    request = canonical_request(None, (), {"prompt": rewrite_engine.build_rewrite_prompt(context),
        "purpose": "source_grounded_rewrite", "response_schema": "rewrite-response"})
    record = {"replacement_latex": context["source_text_for_model"],
              "output_spans": [{"span_id": "out", "text": context["source_text_for_model"]}],
              "concept_correspondences": [{"source_concept_id": identifier,
                  "output_span_ids": ["out"], "mapping_type": "retain"} for identifier in unit.concept_ids]}
    record["concept_correspondences"][0]["source_concept_id"] = unit.concept_ids[0][:-2]
    folder = fixture.snapshot / ".humanvoice/runtime/synthetic-identifier"
    call = {"status": "complete", "request": request, "request_hash": digest(request),
            "prompt_hash": digest(request["prompt"]), "response_text": json.dumps(record),
            "runtime_record": {"path": ".humanvoice/runtime/synthetic-identifier/record.json", "hash": "synthetic"},
            "input_tokens": 100, "output_tokens": 100}
    write_json(folder / "response.json", {"text": call["response_text"], "input_tokens": 100, "output_tokens": 100})
    (folder / "inputs").mkdir()
    (folder / "inputs/prompt.txt").write_text(request["prompt"])
    monkeypatch.setattr(repair, "original_call", lambda: call)
    monkeypatch.setattr(repair.codex_runtime, "validate_codex_record",
                        lambda *arguments, **keywords: {"termination": "complete", "request_id_if_available": "synthetic"})
    monkeypatch.setattr(ModelAdapter, "invoke", lambda *arguments, **keywords: pytest.fail("No provider call allowed"))
    return SimpleNamespace(fixture=fixture, session=session, call=call, folder=folder, record=record)


def test_native_identifier_replay_retains_original_response(native_case):
    fixture = native_case.fixture
    before = native_case.folder.joinpath("response.json").read_bytes()
    result, original, corrected, correction = repair.derive(fixture.snapshot, native_case.session, fixture.baseline, fixture.plan)
    assert not original["is_acceptable"] and result["is_acceptable"]
    assert result["output_latex"] == original["output_latex"]
    assert result["raw_response"] == original["raw_response"] == native_case.call["response_text"]
    assert result["runtime_record"] == original["runtime_record"] == native_case.call["runtime_record"]
    assert corrected["output_spans"] == native_case.record["output_spans"]
    assert corrected["replacement_latex"] == native_case.record["replacement_latex"]
    assert correction["corrected"] == fixture.plan.units[0].concept_ids[0]
    assert native_case.folder.joinpath("response.json").read_bytes() == before


def test_identifier_correction_cannot_hide_bad_output_evidence(native_case):
    fixture = native_case.fixture
    native_case.record["output_spans"][0]["text"] = "Invented quote absent from output."
    native_case.call["response_text"] = json.dumps(native_case.record)
    write_json(native_case.folder / "response.json", {"text": native_case.call["response_text"],
               "input_tokens": 100, "output_tokens": 100})
    with pytest.raises(ValueError, match="another native writer failure"):
        repair.derive(fixture.snapshot, native_case.session, fixture.baseline, fixture.plan)


@pytest.mark.parametrize("tamper", [None, "text", "mapping", "raw", "receipt", "admission", "payload", "journal"])
def test_identifier_consumer_rejects_changed_derivation(native_case, monkeypatch, tamper):
    fixture = native_case.fixture
    result, original, corrected, correction = repair.derive(fixture.snapshot, native_case.session, fixture.baseline, fixture.plan)
    report = {"identity": "synthetic-report", "call_hash": digest(native_case.call),
              "correction": correction, "response_hash": digest(native_case.call["response_text"]),
              "corrected_payload_hash": digest(corrected), "result_hash": digest(result), "original_result_hash": digest(original)}
    monkeypatch.setattr(repair, "report", lambda: report)
    admission = repair.admission_for(report, result)
    relative = ".humanvoice/writer-identifier-admissions/" + native_case.call["request_hash"] + ".json"
    write_json(fixture.snapshot / relative, admission)
    write_json(fixture.snapshot / relative.replace(".json", "-payload.json"), corrected)
    journal = fixture.snapshot / (".humanvoice/rewrites/attempts/identifier-retained-" + native_case.call["request_hash"] + "/unit-014/001.json")
    write_json(journal, original)
    result["writer_identifier_admission"] = {"path": relative, "hash": digest(admission)}
    if tamper == "text":
        result["output_latex"] += "Extra claim."
    elif tamper == "mapping":
        result["concept_correspondences"].pop()
    elif tamper == "raw":
        result["raw_response"] = json.dumps(corrected)
    elif tamper == "receipt":
        response = read_json(native_case.folder / "response.json")
        response["text"] = json.dumps(corrected)
        write_json(native_case.folder / "response.json", response)
    elif tamper == "admission":
        admission["model_calls"] = 1
        write_json(fixture.snapshot / relative, admission)
    elif tamper == "payload":
        corrected["replacement_latex"] += "Injected claim."
        write_json(fixture.snapshot / relative.replace(".json", "-payload.json"), corrected)
    elif tamper == "journal":
        original["is_acceptable"] = True
        write_json(journal, original)
    if tamper:
        with pytest.raises(ValueError, match="admission"):
            repair.validate_result(fixture.snapshot, result)
    else:
        assert repair.validate_result(fixture.snapshot, result) == result


@pytest.mark.parametrize("purpose", ["source_grounded_rewrite", "concept_extraction"])
def test_identifier_continuation_never_repeats_writer(tmp_path, monkeypatch, purpose):
    monkeypatch.setattr(continuation, "verify_history", lambda *arguments: None)
    model = SimpleNamespace(snapshot_dir=tmp_path)
    with continuation.review_only(tmp_path, tmp_path, {"completed": []}):
        with pytest.raises(ValueError, match="cannot repeat"):
            ModelAdapter.invoke(model, "same request", purpose=purpose, response_schema="rewrite-response")


def test_identifier_probe_stops_before_independent_review(tmp_path, monkeypatch):
    monkeypatch.setattr(continuation, "verify_history", lambda *arguments: None)
    original = ModelAdapter.invoke

    @wraps(original)
    def reject(*arguments, **keywords):
        pytest.fail("Probe transmitted a request")

    monkeypatch.setattr(ModelAdapter, "invoke", reject)
    with continuation.review_only(tmp_path, tmp_path, {"completed": []}, probe=True) as (requests, boundary):
        with pytest.raises(boundary):
            ModelAdapter.invoke(SimpleNamespace(snapshot_dir=tmp_path), "review", purpose="independent_rewrite_verification",
                                response_schema="critic-response")
    assert len(requests) == 1


def test_identifier_plan_rejects_replaced_diagnostic(monkeypatch):
    diagnostic = {"identity": "original"}
    monkeypatch.setattr(repair, "report", lambda: diagnostic)
    monkeypatch.setattr(continuation.previous, "validate_extension", lambda plan: plan)
    plan = {"writer_identifier_extension": continuation.extension()}
    assert continuation.validate_extension(plan) == plan
    diagnostic["identity"] = "changed"
    with pytest.raises(ValueError, match="implementation changed"):
        continuation.validate_extension(plan)


def test_relocated_execution_dependencies_stop_before_spending(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    stages = tmp_path / "stages"
    stages.mkdir()
    continuation.ensure_execution_paths(stages)
    (stages / "held-out-history").symlink_to(archive, target_is_directory=True)
    with pytest.raises(ValueError, match="restore original SSD directories"):
        continuation.ensure_execution_paths(stages)


def test_storage_stop_refresh_preserves_original_failure(tmp_path, monkeypatch):
    from tools import run_writer_identifier_program_20261019 as controller

    base, root = tmp_path / "execution", tmp_path / "checkout"
    evidence = base / "identifier"
    for name in ("humanvoice_master_program_v2.md", "ENSEMBLE_MASTER_PROGRAM_2026-09-30.md"):
        path = root / "docs/plans" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Master\n<!-- end-current-benchmark-execution -->\nRetained history.\n")
    state = {"phases": [{"id": "E7-RB", "status": "running"}],
             "current_call_grant": {"identity": "grant", "used": 694, "available": 1306, "reserved_remaining": 0}}
    write_json(base / "status.json", state)
    write_json(tmp_path / "account.json", {"events": [], "plans": [], "reservation_ceiling": 274048487, "allowance": 600000000})
    write_json(tmp_path / "grant.json", {"maximum_new_calls": 2000})
    for name, value in (("BASE", base), ("ROOT", root), ("EVIDENCE", evidence),
                        ("PROOF", evidence / "verification.json"), ("PROGRESS", tmp_path / "progress.json"),
                        ("ACCOUNT", tmp_path / "account.json"), ("GRANT", tmp_path / "grant.json")):
        monkeypatch.setattr(controller, name, value)

    def unavailable(path):
        raise ValueError("Plan allowance differs from its account reservation")

    monkeypatch.setattr(controller, "grant_status", unavailable)
    controller.refresh("Restore original SSD paths.", "Archived symlinks block execution.")
    current = read_json(base / "status.json")
    assert current["status"] == "writer_identifier_stopped"
    assert current["stop"] == "Archived symlinks block execution."
    assert current["current_call_grant"] == state["current_call_grant"]
    assert current["current_budget_verification_error"] == "Plan allowance differs from its account reservation"
    assert "last verified" in (evidence / "STATUS.md").read_text()
    assert "Retained history." in (root / "docs/plans/humanvoice_master_program_v2.md").read_text()


@pytest.mark.parametrize("interrupted", [False, True])
def test_identifier_controller_routes_and_restores(tmp_path, monkeypatch, interrupted):
    from tools import run_writer_identifier_program_20261019 as controller
    from contextlib import contextmanager

    monkeypatch.setattr(controller, "EVIDENCE", tmp_path)
    monkeypatch.setattr(controller, "refresh", lambda *arguments: None)
    previous = controller.previous
    parallel = previous.previous.previous
    engine = parallel.parallel.previous.engine
    campaign = SimpleNamespace(script=lambda *arguments: pytest.fail("unscoped native command"))
    monkeypatch.setattr(engine.previous, "stack", lambda: SimpleNamespace(campaign=campaign))
    calls = []
    monkeypatch.setattr(parallel.subprocess, "run", lambda command, **keywords: calls.append(command))
    native_pipeline = continuation.pipeline

    @contextmanager
    def scoped():
        with native_pipeline():
            yield

    monkeypatch.setattr(continuation, "pipeline", scoped)

    def sequence():
        assert controller.ACTIVE and engine.benchmark_chain is controller.benchmark_chain
        active = engine.previous.stack().campaign
        active.script("run-manuscript-with-300-grant-20261008.py", "execute", "--output", tmp_path, "--live")
        active.script("verify-manuscript-boundary-20261007.py", tmp_path.name, "--phase", "E7-RB-held-out", "--next", "Continue")
        assert len(calls) == 2
        assert all(command[1].endswith("writer_identifier_runner.py") for command in calls)
        if interrupted:
            raise RuntimeError("synthetic stop")

    monkeypatch.setattr(engine, "run", sequence)
    before = previous.refresh, previous.continuation, previous.EVIDENCE, engine.benchmark_chain, campaign.script
    if interrupted:
        with pytest.raises(RuntimeError, match="synthetic stop"):
            controller.run()
    else:
        controller.run()
    assert before == (previous.refresh, previous.continuation, previous.EVIDENCE, engine.benchmark_chain, campaign.script)
    assert not controller.ACTIVE
