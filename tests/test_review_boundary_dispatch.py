"""Separate native boundaries retain completed reviews and reject changed evidence."""

import runpy
import sys
from contextlib import contextmanager, nullcontext
from copy import deepcopy

import pytest
from test_writer_policy_campaign import campaign

from humanvoice.artifacts import read_json, write_json
from humanvoice.model import ModelAdapter
from tools import manuscript_transport_restart
from tools import reproduction_boundary_dispatch as boundary
from tools import reproduction_boundary_runner as runner
from tools import run_review_boundary_20261021 as controller


@pytest.fixture
def retained(tmp_path, monkeypatch):
    proof = {"version": boundary.continuation.VERSION, "predecessor": str(tmp_path / "prior"),
             "snapshot": str(tmp_path / "snapshot"), "remaining_calls": 3,
             "plan_identity": "prior-plan", "completed": [{"request_hash": "retained-review"}]}
    plan = {"technical_restart": proof, "snapshot": proof["snapshot"], "calls": [{}, {}, {}],
            "stage": "reproduction", "plan_identity": "current-plan", "bindings": {"implementation": "current"},
            "reproduction_comparison": "qualified-source-fidelity-v1",
            "assembled_input_budget_extension": {"authorization_path": "authorized"}}
    monkeypatch.setattr(boundary, "ACCOUNT", tmp_path / "account.json")
    monkeypatch.setattr(boundary.continuation, "validate_extension", lambda value: value)
    monkeypatch.setattr(boundary.continuation, "predecessor_evidence", lambda output: deepcopy(proof))
    return plan


@pytest.mark.parametrize("defect", [None, "snapshot", "account", "bound", "bool", "proof", "extension"])
def test_dispatch_checks_scope_and_evidence(retained, tmp_path, monkeypatch, defect):
    plan = retained
    snapshot, account, maximum = plan["snapshot"], boundary.ACCOUNT, len(plan["calls"])
    if defect == "snapshot":
        snapshot = tmp_path / "different"
    elif defect == "account":
        account = tmp_path / "different.json"
    elif defect == "bound":
        maximum += 1
    elif defect == "bool":
        maximum = True
    elif defect == "proof":
        monkeypatch.setattr(boundary.continuation, "predecessor_evidence", lambda output: {})
    elif defect == "extension":
        def refuse(value):
            raise ValueError("Frozen extension changed")

        monkeypatch.setattr(boundary.continuation, "validate_extension", refuse)
    native = manuscript_transport_restart.predecessor_evidence

    def exercise():
        with boundary.dispatch(plan):
            return manuscript_transport_restart.predecessor_evidence(
                plan["technical_restart"]["predecessor"], snapshot, maximum, account=account)

    if defect:
        with pytest.raises(ValueError):
            exercise()
    else:
        assert exercise() == plan["technical_restart"]
    assert manuscript_transport_restart.predecessor_evidence is native


def test_dispatch_delegates_unrelated_predecessor_and_restores(retained, tmp_path, monkeypatch):
    calls = []

    def native(*arguments, **keywords):
        calls.append((arguments, keywords))
        return "legacy-proof"

    monkeypatch.setattr(manuscript_transport_restart, "predecessor_evidence", native)
    with pytest.raises(RuntimeError, match="synthetic stop"):
        with boundary.dispatch(retained):
            assert manuscript_transport_restart.predecessor_evidence(
                tmp_path / "other", "snapshot", 7, account="account") == "legacy-proof"
            raise RuntimeError("synthetic stop")
    assert len(calls) == 1
    assert manuscript_transport_restart.predecessor_evidence is native
    with pytest.raises(ValueError, match="overload continuation"):
        with boundary.dispatch({"technical_restart": {"version": "unknown"}}):
            pytest.fail("Unknown continuation admitted")


@pytest.mark.parametrize("changed", [False, True])
def test_native_boundary_consumes_matching_predecessor(retained, tmp_path, monkeypatch, changed):
    namespace = runpy.run_path(str(boundary.BASE / boundary.NATIVE))
    native = namespace["main"]
    globals_ = native.__globals__
    output = tmp_path / "held-out-reproduction"
    plan = deepcopy(retained)
    if changed:
        plan["technical_restart"]["completed"] = []
    write_json(output / "plan.json", plan)
    write_json(output / "execution.json", {"status": "pass"})
    write_json(output / "allocation-ledger.json", {"calls": []})
    write_json(output / "calls/0000/call.json", {"runtime_record": {"path": "receipt.json"},
        "request": {"purpose": "assembled_candidate_verification"}})
    usage = {"plan_identity": plan["plan_identity"], "calls": 3, "allocated_calls": 3,
             "unknown_calls": 0, "unallocated_calls": 0, "reported_tokens": 100, "retained_tokens": 100}
    account = {"reservation_ceiling": 100, "gross_reservation_ceiling": 100,
               "plans": [{"plan_identity": plan["plan_identity"], "reserved_tokens": 100}],
               "events": [{"kind": "settle", "usage": usage}]}
    write_json(boundary.ACCOUNT, account)
    write_json(tmp_path / "status.json", {"boundaries": [], "phases": [], "resource_policy": {}})
    checks = []

    def reproduction(root, *, require_live):
        assert root == output / "reproduction" and require_live
        checks.append("reproduction")
        return {"status": "pass"}

    def legacy(*arguments, **keywords):
        raise ValueError("Checkpoint cannot discard a critic or assembled judgment")

    replacements = {"__file__": str(tmp_path / boundary.NATIVE), "ACCOUNT": boundary.ACCOUNT,
                    "runtime": lambda *args: nullcontext(), "implementation_hash": lambda: "current",
                    "uses_recovery": lambda plan: False,
                    "validate_codex_record": lambda *args: {"termination": "complete"},
                    "validate_reproduction": reproduction, "settle": lambda output: {"usage": usage},
                    "completed_usage": lambda output: usage, "validate_account": lambda record: record}
    for name, value in replacements.items():
        monkeypatch.setitem(globals_, name, value)
    monkeypatch.setattr(manuscript_transport_restart, "predecessor_evidence", legacy)
    monkeypatch.setattr(sys, "argv", [boundary.NATIVE, output.name, "--phase", "E7-RB-held-out", "--next", "Continue"])
    with pytest.raises(ValueError, match="cannot discard"):
        native()
    assert not (output / "boundary-checkpoint.json").exists()
    with boundary.dispatch(plan):
        if changed:
            with pytest.raises(ValueError, match="evidence changed"):
                native()
        else:
            native()
    assert checks == ["reproduction", "reproduction"]
    assert manuscript_transport_restart.predecessor_evidence is legacy
    if changed:
        assert not (output / "boundary-checkpoint.json").exists()
    else:
        report = read_json(output / "boundary-checkpoint.json")
        assert report["status"] == "pass_settled_and_separately_verified"
        assert report["details"]["technical_restart_verification"] == "pass"
        assert report["details"]["predecessor_remains_nonpass"] is True
        assert report["human_evidence"] is False


@pytest.mark.parametrize("interrupted", [False, True])
def test_runner_scopes_native_boundary(retained, tmp_path, monkeypatch, interrupted):
    output = tmp_path / "stage"
    write_json(output / "plan.json", retained)
    write_json(output / "execution.json", {"status": "pass"})
    monkeypatch.setattr(runner.scope, "BASE", tmp_path)
    monkeypatch.setattr(boundary, "EVIDENCE", tmp_path / "evidence")
    monkeypatch.setattr(runner.scope, "accounting_scope", nullcontext)
    monkeypatch.setattr(runner.continuation, "pipeline", lambda **kwargs: nullcontext())
    monkeypatch.setattr(runner.continuation.network.budget, "plan_scope", lambda plan: ([], []))
    monkeypatch.setattr(runner, "cached_parallel_verification", lambda **kwargs: nullcontext())
    original_argv = ["runner", boundary.NATIVE, output.name, "--phase", "E7-RB-held-out", "--next", "Continue"]
    monkeypatch.setattr(sys, "argv", original_argv)
    original_predecessor, original_invoke = manuscript_transport_restart.predecessor_evidence, ModelAdapter.invoke

    def native(path, *, run_name):
        assert path == str(tmp_path / boundary.NATIVE) and run_name == "__main__"
        assert sys.argv == [path, *original_argv[2:]]
        proof = manuscript_transport_restart.predecessor_evidence(retained["technical_restart"]["predecessor"],
            retained["snapshot"], len(retained["calls"]), account=boundary.ACCOUNT)
        assert proof == retained["technical_restart"]
        with pytest.raises(RuntimeError, match="cannot transmit"):
            ModelAdapter.invoke(None, "forbidden")
        if interrupted:
            raise RuntimeError("synthetic stop")

    monkeypatch.setattr(runner.runpy, "run_path", native)
    if interrupted:
        with pytest.raises(RuntimeError, match="synthetic stop"):
            runner.main()
    else:
        assert runner.main() == 0
    assert sys.argv is original_argv
    assert manuscript_transport_restart.predecessor_evidence is original_predecessor
    assert ModelAdapter.invoke is original_invoke
    report = read_json(next(boundary.EVIDENCE.glob("boundary-*.json")))
    assert report["status"] == ("nonpass" if interrupted else "pass") and report["model_calls"] == 0


@pytest.mark.parametrize("interrupted", [False, True])
def test_controller_preserves_completed_stage_identity(monkeypatch, interrupted):
    monkeypatch.setattr(controller, "refresh", lambda *args: None)
    review_size = controller.previous.previous
    original = controller.scope.RUNNER, review_size.continuation, controller.sized.benchmark_chain, controller.sized.SUFFIX

    def sequence():
        assert controller.ACTIVE
        assert controller.scope.RUNNER.name == "reproduction_boundary_runner.py"
        assert controller.sized.SUFFIX == controller.previous.SUFFIX == "review-overload-20261021-01"
        assert review_size.continuation is controller.identifier.continuation is controller.sized.continuation is boundary.continuation
        command = [sys.executable, str(controller.ROOT / "tools/assembled_budget_runner.py"), boundary.NATIVE, boundary.STAGE.name]
        actual = controller.sized.recovery_command(command)
        assert actual[1] == str(controller.scope.RUNNER) and actual[2:] == command[2:]
        if interrupted:
            raise RuntimeError("synthetic stop")

    monkeypatch.setattr(controller.sized, "run", sequence)
    if interrupted:
        with pytest.raises(RuntimeError, match="synthetic stop"):
            controller.run()
    else:
        controller.run()
    assert original == (controller.scope.RUNNER, review_size.continuation, controller.sized.benchmark_chain, controller.sized.SUFFIX)
    assert not controller.ACTIVE


def test_native_campaign_resumes_only_missing_boundary(campaign):
    campaign.SUFFIX = controller.previous.SUFFIX
    snapshot = campaign.BASE / "snapshot"
    output = campaign.BASE / boundary.STAGE.name
    write_json(output / "plan.json", {"stage": "reproduction", "snapshot": str(snapshot), "calls": [{}, {}, {}]})
    write_json(output / "execution.json", {"status": "pass"})
    campaign.manuscript("held-out", "reproduction", snapshot, 3, "E7-RB-held-out")
    campaign.script.assert_called_once_with(boundary.NATIVE, output.name, "--phase", "E7-RB-held-out",
        "--next", "Continue the current writer-policy manuscript sequence.")
    campaign.boundary.assert_called_once_with(output)


def test_refresh_uses_accounting_and_cache_scopes(tmp_path, monkeypatch):
    active = set()

    @contextmanager
    def scope(name):
        active.add(name)
        try:
            yield
        finally:
            active.remove(name)

    def refresh(*arguments):
        assert active == {"accounting", "continuation", "settlements"}

    monkeypatch.setattr(controller, "BASE", tmp_path)
    monkeypatch.setattr(controller, "EVIDENCE", tmp_path / "evidence")
    monkeypatch.setattr(controller.scope, "accounting_scope", lambda: scope("accounting"))
    monkeypatch.setattr(controller.continuation, "pipeline", lambda: scope("continuation"))
    monkeypatch.setattr(controller, "cached_parallel_verification", lambda **kwargs: scope("settlements"))
    monkeypatch.setattr(controller, "refresh", refresh)
    monkeypatch.setattr(sys, "argv", ["controller", "refresh"])
    assert controller.main() == 0
    assert not active
