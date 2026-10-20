"""Completed review rejections receive bounded changed-candidate repair only."""

import json
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
from types import SimpleNamespace

import pytest

from humanvoice import automatic_reproduction, rewrite_engine
from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.model import ModelAdapter
from tools import reproduction_semantic_recovery as recovery
from tools.inventory_transport_continuation import canonical_request


@pytest.mark.parametrize("unknown", [0, 4, 14])
def test_semantic_bounds_preserve_spent_retry_allowance(unknown):
    parent = {"calls": [{}] * 41, "recovery": {"maximum_total": 14}}
    scope = {"units": {str(index): {} for index in range(14)}, "rejected": {"unit-003": {}, "unit-013": {}}}
    limits = recovery.bounds(parent, scope, {"allocated_calls": 14 + unknown, "unknown_calls": unknown})
    assert limits == {"remaining_logical_calls": 31, "remaining_calls": 59,
                      "remaining_transport_extras": 14 - unknown, "assembled_calls": 27}


@pytest.mark.parametrize("allocated,unknown,rejected", [(17, 4, 2), (29, 15, 2), (14, 0, 0)])
def test_semantic_bounds_reject_incomplete_reviews(allocated, unknown, rejected):
    parent = {"calls": [{}] * 41, "recovery": {"maximum_total": 14}}
    scope = {"units": {str(index): {} for index in range(14)}, "rejected": {str(index): {} for index in range(rejected)}}
    with pytest.raises(ValueError, match="complete reviews"):
        recovery.bounds(parent, scope, {"allocated_calls": allocated, "unknown_calls": unknown})


@pytest.fixture
def guarded(tmp_path, monkeypatch):
    context = {"source": "source", "concepts": [], "brief": {}, "candidate": "changed candidate"}
    writer = canonical_request(None, (), {"prompt": "CONTEXT_JSON:\n" + json.dumps({"unit_id": "unit-003",
        "previous_attempt_failures": [{"critic_unsupported_additions": ["retained feedback"]}]}),
        "purpose": "source_grounded_rewrite", "response_schema": "rewrite-response"})
    critic = canonical_request(None, (), {"prompt": "REVIEW_DATA:\n" + json.dumps(context),
        "purpose": "independent_rewrite_verification", "response_schema": "critic-response"})
    assembled = canonical_request(None, (), {"prompt": "assembled candidate", "purpose": "assembled_candidate_verification",
        "response_schema": "critic-response"})
    proof = {"completed": [], "scope": {"rejected": {"unit-003": {"request": writer}}, "units": {
        "unit-003": {"context": context, "output_hash": "original"}}}}
    calls = []
    native = ModelAdapter.invoke

    @wraps(native)
    def provider(model, *arguments, **keywords):
        calls.append(canonical_request(model, arguments, keywords))
        return "synthetic response"

    monkeypatch.setattr(ModelAdapter, "invoke", provider)
    monkeypatch.setattr(recovery.semantic, "retained_bytes", lambda *arguments, **keywords: None)
    monkeypatch.setattr(recovery.semantic, "unit_requests", lambda snapshot: {"unit-003": critic})
    monkeypatch.setattr(recovery.semantic, "assembled_requests", lambda snapshot: [assembled])
    monkeypatch.setattr(recovery.artifacts, "load_session", lambda snapshot: {})
    result = {"output_hash": "changed", "output_latex": context["candidate"]}
    monkeypatch.setattr(recovery.artifacts, "load_unit_result", lambda *arguments: result)
    return SimpleNamespace(snapshot=tmp_path, model=SimpleNamespace(snapshot_dir=tmp_path), proof=proof,
                           writer=writer, critic=critic, assembled=assembled, calls=calls, result=result)


@pytest.mark.parametrize("defect", ["completed", "prompt", "snapshot", "accepted_unit", "duplicate"])
def test_semantic_guard_rejects_completed_or_changed_work(guarded, defect):
    fixture = guarded
    request = deepcopy(fixture.writer)
    if defect == "completed":
        fixture.proof["completed"] = [{"request_hash": digest(request)}]
    if defect == "prompt":
        request["prompt"] += " "
    if defect == "snapshot":
        fixture.model.snapshot_dir = fixture.snapshot / "other"
    if defect == "accepted_unit":
        request["prompt"] = request["prompt"].replace("unit-003", "unit-001")
    with recovery.guarded_repairs(fixture.snapshot, fixture.proof):
        if defect == "duplicate":
            ModelAdapter.invoke(fixture.model, **request)
        with pytest.raises(ValueError):
            ModelAdapter.invoke(fixture.model, **request)
    assert len(fixture.calls) == (1 if defect == "duplicate" else 0)


@pytest.mark.parametrize("defect", ["unchanged", "unsubmitted", "wrong_candidate", "duplicate"])
def test_semantic_guard_requires_changed_candidate(guarded, defect):
    fixture = guarded
    with recovery.guarded_repairs(fixture.snapshot, fixture.proof):
        if defect != "unsubmitted":
            ModelAdapter.invoke(fixture.model, **fixture.writer)
        if defect == "unchanged":
            fixture.result["output_hash"] = "original"
        if defect == "wrong_candidate":
            fixture.result["output_latex"] = "different candidate"
        if defect == "duplicate":
            ModelAdapter.invoke(fixture.model, **fixture.critic)
        with pytest.raises(ValueError):
            ModelAdapter.invoke(fixture.model, **fixture.critic)
    assert len(fixture.calls) == (0 if defect == "unsubmitted" else 2 if defect == "duplicate" else 1)


@pytest.mark.parametrize("defect", [None, "unsubmitted", "bad_parent", "cap"])
def test_semantic_guard_binds_split_children(guarded, monkeypatch, defect):
    fixture = guarded
    verified = []

    def verify(snapshot, request):
        verified.append(request)
        if defect == "bad_parent":
            raise ValueError("split parent changed")

    monkeypatch.setattr(recovery.sizing, "verify_child", verify)
    with recovery.guarded_repairs(fixture.snapshot, fixture.proof):
        if defect != "unsubmitted":
            ModelAdapter.invoke(fixture.model, **fixture.writer)
        for position in range(15 if defect == "cap" else 1):
            token = {"root_unit": "unit-003", "unit_id": f"unit-003.split-{position}"}
            request = dict(fixture.writer, prompt="CONTEXT_JSON:\n" + json.dumps({
                "previous_attempt_failures": [{"writer_size_split": token}]}))
            if defect in {"unsubmitted", "bad_parent"} or defect == "cap" and position == 14:
                with pytest.raises(ValueError):
                    ModelAdapter.invoke(fixture.model, **request)
            else:
                ModelAdapter.invoke(fixture.model, **request)
    assert len(fixture.calls) == (0 if defect == "unsubmitted" else 1 if defect == "bad_parent" else 15 if defect == "cap" else 2)
    assert len(verified) == (0 if defect == "unsubmitted" else 14 if defect == "cap" else 1)


def test_semantic_guard_reaches_assembly_only_after_changed_reviews(guarded):
    fixture = guarded
    with recovery.guarded_repairs(fixture.snapshot, fixture.proof):
        with pytest.raises(ValueError, match="declared scope"):
            ModelAdapter.invoke(fixture.model, **fixture.assembled)
        with pytest.raises(recovery.previous.critic.CriticTransportStop, match="already stopped"):
            ModelAdapter.invoke(fixture.model, **fixture.writer)
    with recovery.guarded_repairs(fixture.snapshot, fixture.proof) as (activity, boundary):
        ModelAdapter.invoke(fixture.model, **fixture.writer)
        ModelAdapter.invoke(fixture.model, **fixture.critic)
        ModelAdapter.invoke(fixture.model, **fixture.assembled)
    assert activity["writers"] == activity["critics"] == {"unit-003"}
    assert len(fixture.calls) == len(activity["requests"]) == 3


def test_semantic_guard_stops_after_failed_review(guarded, monkeypatch):
    fixture = guarded
    native = ModelAdapter.invoke

    @wraps(native)
    def provider(model, *arguments, **keywords):
        if keywords["purpose"] == "independent_rewrite_verification":
            model.last_runtime_record = {"path": "retained/record.json", "hash": "original"}
            raise RuntimeError("provider stopped")
        return native(model, *arguments, **keywords)

    monkeypatch.setattr(ModelAdapter, "invoke", provider)
    with recovery.guarded_repairs(fixture.snapshot, fixture.proof):
        ModelAdapter.invoke(fixture.model, **fixture.writer)
        with pytest.raises(recovery.previous.critic.CriticTransportStop, match="provider stopped"):
            ModelAdapter.invoke(fixture.model, **fixture.critic)
        with pytest.raises(recovery.previous.critic.CriticTransportStop, match="already stopped"):
            ModelAdapter.invoke(fixture.model, **fixture.assembled)
    assert len(fixture.calls) == 1 and ModelAdapter.invoke is provider


def test_semantic_probe_makes_no_provider_call(guarded):
    fixture = guarded
    with recovery.guarded_repairs(fixture.snapshot, fixture.proof, probe=True) as (activity, boundary):
        with pytest.raises(boundary):
            ModelAdapter.invoke(fixture.model, **fixture.writer)
    assert activity["requests"] == [digest(fixture.writer)] and fixture.calls == []


def test_semantic_writer_failure_stops_after_size_recovery(monkeypatch):
    native = lambda *arguments, **keywords: SimpleNamespace(is_acceptable=False, rejection_reasons=["rejected candidate"])
    monkeypatch.setattr(rewrite_engine, "rewrite_unit", native)
    with recovery.fail_fast_writers():
        with pytest.raises(recovery.previous.critic.CriticTransportStop, match="rejected candidate"):
            rewrite_engine.rewrite_unit()
    assert rewrite_engine.rewrite_unit is native


def test_semantic_failure_reports_actual_rejections(tmp_path):
    preflight = tmp_path / "reproduction/replica/.humanvoice/preflight"
    write_json(preflight / "summary.json", {"blocked_units": ["unit-003", "unit-013"]})
    for unit in ("unit-003", "unit-013"):
        write_json(preflight / (unit + ".json"), {"failure_stage": "critic_semantic", "critic_record": {
            "verdict": {"unsupported_additions": [unit + " unsupported addition"]}}})
    result = recovery.failure_summary(tmp_path)
    assert result["reason"] == "unit_review_rejections"
    assert [row["unit_id"] for row in result["units"]] == ["unit-003", "unit-013"]
    assert result["units"][0]["unsupported_additions"] == ["unit-003 unsupported addition"]


def test_semantic_pipeline_restores_functions(monkeypatch):
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


@pytest.mark.parametrize("interrupted", [False, True])
def test_semantic_controller_routes_and_restores(monkeypatch, interrupted):
    from tools import run_reproduction_semantic_20261020 as controller

    identifier, sized = controller.previous.previous, controller.previous.previous.previous
    monkeypatch.setattr(controller, "refresh", lambda *arguments: None)
    before = (controller.scope.RUNNER, identifier.continuation, sized.continuation, sized.benchmark_chain)

    def sequence():
        assert controller.ACTIVE
        assert controller.scope.RUNNER.name == "reproduction_semantic_runner.py"
        assert identifier.continuation is sized.continuation is recovery
        assert sized.benchmark_chain is controller.benchmark_chain
        if interrupted:
            raise RuntimeError("synthetic stop")

    monkeypatch.setattr(sized, "run", sequence)
    if interrupted:
        with pytest.raises(RuntimeError, match="synthetic stop"):
            controller.run()
    else:
        controller.run()
    assert before == (controller.scope.RUNNER, identifier.continuation, sized.continuation, sized.benchmark_chain)
    assert not controller.ACTIVE


def test_semantic_controller_preserves_successor_bound(tmp_path, monkeypatch):
    from tools import run_reproduction_semantic_20261020 as controller

    source = tmp_path / "snapshot"
    (source / "release/immutable-packet").mkdir(parents=True)
    monkeypatch.setattr(controller, "BASE", tmp_path)
    monkeypatch.setattr(controller, "EVIDENCE", tmp_path / "evidence")
    monkeypatch.setattr(controller, "PROGRESS", tmp_path / "progress.json")
    monkeypatch.setattr(controller, "refresh", lambda *arguments: None)
    monkeypatch.setattr(recovery, "predecessor_evidence", lambda: {
        "snapshot": str(source), "remaining_calls": 59, "remaining_transport_extras": 10})
    write_json(controller.PROGRESS, {})
    calls = []
    campaign = SimpleNamespace(SUFFIX="original", script=lambda *arguments: calls.append(arguments),
                               manuscript=lambda *arguments: calls.append(arguments))
    controller.benchmark_chain("held-out", {}, campaign, None)
    assert calls[0][calls[0].index("--max-calls") + 1] == 59
    assert calls[1][3] == 59 and campaign.SUFFIX == "original"
    assert read_json(controller.PROGRESS)["reproductions"]["held-out"]["full_call_bound"] == 69


@pytest.mark.parametrize("defect", [None, "hidden_allocation", "phantom_request", "duplicate_request", "completed_request"])
def test_semantic_accounting_requires_exact_guarded_activity(tmp_path, monkeypatch, defect):
    proof = {"scope": {"rejected": {"unit-003": {}}}, "all_fresh_runtime_ids": ["inherited"],
             "completed": [{"request_hash": "old"}]}
    activity = {"status": "pass", "probe": False, "writers": ["unit-003"], "critics": ["unit-003"],
                "requests": ["new"]}
    evidence = {"calls": [{"journal": {"request_hash": "new"}}]}
    if defect == "hidden_allocation":
        evidence["calls"].append({"journal": {"request_hash": "unreported"}})
    if defect == "phantom_request":
        activity["requests"].append("unallocated")
    if defect == "duplicate_request":
        activity["requests"].append("new")
    if defect == "completed_request":
        activity["requests"] = ["old"]
        evidence["calls"][0]["journal"]["request_hash"] = "old"
    write_json(tmp_path / "semantic-repair-execution.json", activity)
    monkeypatch.setattr(recovery, "validate_extension", lambda plan: plan)
    monkeypatch.setattr(recovery, "predecessor_evidence", lambda output: proof)
    monkeypatch.setattr(recovery.semantic, "retained_bytes", lambda *arguments, **keywords: None)
    monkeypatch.setattr(recovery.writer_repair, "NATIVES", (lambda *arguments: evidence,))
    plan = {"technical_restart": {"predecessor": "frozen"}}
    if defect:
        with pytest.raises(ValueError, match="bounded repair activity"):
            recovery.validate_accounted_calls(tmp_path, plan, {"inherited", "new"})
    else:
        assert recovery.validate_accounted_calls(tmp_path, plan, {"inherited", "new"}) == evidence
