"""The context continuation preserves lineage, accounting and worker routing."""

import sys
from pathlib import Path

import pytest

from humanvoice.artifacts import read_json, write_json
from tools import inventory_context_continuation as continuation
from tools import inventory_context_runner as runner
from tools import run_inventory_context_20261022 as controller


def test_context_lineage_retains_all_responses_and_network_charge():
    before = continuation.ACCOUNT.read_bytes()
    with continuation.inventory.history.archive.access(), continuation.inventory.scope.accounting_scope(), continuation.inventory.pipeline():
        proof = continuation.predecessor_evidence()
    assert len(proof["prefix"]) == 24 and len(proof["superseded_window_calls"]) == 3
    assert len(proof["transport_failures"]) == 1
    assert proof["usage"]["unknown_calls"] == 1 and proof["usage"]["allocated_calls"] == 10
    assert proof["remaining_base_calls"] == 516 and proof["remaining_calls"] == 540
    assert proof["prefix"][19]["attempt"] == 523
    assert continuation.ACCOUNT.read_bytes() == before


@pytest.mark.parametrize("defect", ["terminal", "scope", "settlement", "negative", "replay"])
def test_changed_context_predecessor_is_rejected_without_new_calls(monkeypatch, defect):
    native = continuation.read_json
    before = continuation.ACCOUNT.read_bytes()

    def read(path):
        result = native(path)
        if defect == "terminal" and path == continuation.PRIOR / "execution.json":
            result["status"] = "executing"
        elif defect == "scope" and path == continuation.PRIOR / "plan.json":
            result["profile"] = {}
        elif defect == "settlement" and path == continuation.ACCOUNT:
            result["events"] = []
        elif defect == "negative" and path == continuation.PRIOR / "calls/0008/call.json":
            result["response_text"] = result["response_text"].replace('"unresolved"', '"gap"')
        elif defect == "replay" and path == continuation.PRIOR / "replay-log.json":
            result["inherited"] = []
        return result

    monkeypatch.setattr(continuation, "read_json", read)
    with continuation.inventory.history.archive.access(), continuation.inventory.scope.accounting_scope(), continuation.inventory.pipeline():
        with pytest.raises(ValueError):
            continuation.predecessor_evidence()
    assert continuation.ACCOUNT.read_bytes() == before


def test_continuation_bindings_restore_frozen_functions():
    previous = continuation.previous
    before = previous.STAGE, previous.plan_for, previous.copy_snapshot, previous.predecessor_evidence
    with continuation.bindings():
        assert previous.STAGE == continuation.STAGE
        assert previous.plan_for is continuation.plan_for
        assert continuation.NATIVE_PLAN is before[1]
        assert continuation.NATIVE_COPY is before[2]
    assert (previous.STAGE, previous.plan_for, previous.copy_snapshot, previous.predecessor_evidence) == before


def test_context_controller_routes_only_zlb(monkeypatch):
    boundary = controller.previous.previous.previous
    engine = boundary.identifier.previous.previous.previous.parallel.previous.engine
    prefix = engine.previous.previous.previous.previous.previous
    original = prefix.inventory, controller.scope.command
    calls = []
    monkeypatch.setattr(controller, "run_inventory", lambda *arguments: calls.append(arguments) or "context")

    def run():
        assert prefix.inventory("zlb", "snapshot", 540, "campaign", "refresh") == "context"
        command = controller.scope.command("verify-manuscript-boundary-20261007.py", "stage", "--phase", "test", "--next", "test")
        assert command[1] == str(controller.ROOT / "tools/inventory_context_runner.py")
        assert boundary.refresh is controller.refresh

    monkeypatch.setattr(boundary, "run", run)
    controller.run()
    assert calls == [("zlb", "snapshot", 540, "campaign", "refresh")]
    assert (prefix.inventory, controller.scope.command) == original and not controller.ACTIVE


def test_context_worker_used_for_launch_and_verification(tmp_path, monkeypatch):
    module = runner.automatic_reproduction
    source = tmp_path / "source"
    monkeypatch.setattr(runner.context, "selected_policy", lambda snapshot: {} if snapshot == source else None)
    command = [sys.executable, "-I", "-B", str(runner.ROOT / "tools/reproduction_overload_worker.py"), str(tmp_path / "worker")]
    monkeypatch.setattr(module, "_command", lambda *arguments: command)
    monkeypatch.setattr(module, "launch", lambda snapshot, output: module._command(output, True))
    monkeypatch.setattr(module, "evaluate_reproduction", lambda root, **keywords: module._command(root, True))
    write_json(tmp_path / "request.json", {"manifest": {"snapshot_path": str(source)}})
    native = module._command, module.launch, module.evaluate_reproduction
    with runner.reproduction_dispatch():
        assert module.launch(source, tmp_path)[3] == str(runner.ROOT / "tools/inventory_context_worker.py")
        assert module.evaluate_reproduction(tmp_path)[3] == str(runner.ROOT / "tools/inventory_context_worker.py")
        assert module.evaluate_reproduction(tmp_path, source_override=tmp_path) == command
    assert (module._command, module.launch, module.evaluate_reproduction) == native
