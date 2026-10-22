"""Deadline recovery conserves source evidence, responses, limits and accounting."""

import json
import sys
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest
import test_automatic_manuscript_stage
import test_codex_runtime
import test_assembled_budget_runtime

from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.model import ModelAdapter
from humanvoice import codex_runtime
from tools import inventory_deadline_continuation as continuation
from tools import inventory_deadline_runtime as deadline
from tools import inventory_deadline_runner as runner
from tools import run_inventory_deadline_20261022 as controller
from tools.ensemble_closure_contract import AllocationLedger
from tools import automatic_program_account as account

ledger_setup = test_automatic_manuscript_stage.setup
codex = test_codex_runtime.codex
authorized = test_assembled_budget_runtime.authorized


def test_deadline_lineage_preserves_positive_prefix_and_unknown_charge():
    before = continuation.ACCOUNT.read_bytes()
    with continuation.inventory.history.archive.access(), continuation.inventory.scope.accounting_scope(), continuation.inventory.pipeline():
        proof = continuation.predecessor_evidence()
    assert len(proof["prefix"]) == 27 and len(proof["superseded_window_calls"]) == 3
    assert proof["usage"]["unknown_calls"] == 1 and proof["usage"]["allocated_calls"] == 4
    assert proof["remaining_base_calls"] == 513 and proof["remaining_calls"] == 537
    assert proof["deadline_failure"]["reason"] == "response_free_process_deadline"
    assert continuation.ACCOUNT.read_bytes() == before


def test_real_deadline_is_prospectively_recoverable():
    root = continuation.PRIOR
    plan = read_json(root / "plan.json")
    entry = read_json(root / "allocation-ledger.json")["calls"][-1]
    directory = root / "calls/0003"
    with continuation.inventory.history.archive.access(), continuation.inventory.scope.accounting_scope(), continuation.inventory.pipeline():
        native = deadline.failure_evidence(root, directory, plan, entry)
        assert not native["eligible"] and native["reason"] == "unproven_transport_failure"
        prospective = {**plan, deadline.FIELD: deadline.policy()}
        proof = deadline.failure_evidence(root, directory, prospective, entry)
        assert proof["eligible"] and proof["reason"] == "response_free_process_deadline"
        assert deadline.failure_evidence(root, directory, prospective, entry,
            raw=lambda name: (root / name).read_bytes()) == proof
        with deadline.runtime():
            assert deadline.network.recovery.failure_evidence(root, directory, prospective, entry) == proof
    assert read_json(root / "plan.json") == plan


@pytest.mark.parametrize("defect", [None, "partial", "reasoning", "usage", "refusal", "unknown_warning",
    "unknown_event", "extra_turn", "short_deadline", "long_delay", "not_killed", "not_started", "bad_scope"])
def test_deadline_classifier_refuses_ambiguous_evidence(tmp_path, defect):
    proof = {"eligible": False, "reason": "unproven_transport_failure", "provider_receipt": "codex:synthetic"}
    directory = tmp_path / "calls/0000"
    write_json(directory / "call.json", {"runtime_record": {"path": ".humanvoice/runtime/synthetic/record.json"}})
    folder = tmp_path / "snapshots/primary/snapshot/.humanvoice/runtime/synthetic"
    process = {"status": "timeout", "returncode": -9, "process_started": True, "deadline_seconds": 900,
               "elapsed_seconds": 900.03, "enforcement": "process-group-deadline-only"}
    events = [{"type": "thread.started", "thread_id": "synthetic"}, {"type": "turn.started"}]
    if defect in {"partial", "reasoning", "usage", "refusal"}:
        proof["reason"] = "provider_rejection" if defect == "refusal" else "response_or_usage_present"
    elif defect == "unknown_warning":
        events.insert(1, {"type": "item.completed", "item": {"id": "one", "type": "error", "message": "unknown"}})
    elif defect == "unknown_event":
        events.insert(1, {"type": "tool.started"})
    elif defect == "extra_turn":
        events.insert(1, {"type": "turn.started"})
    elif defect == "short_deadline":
        process["elapsed_seconds"] = 899
    elif defect == "long_delay":
        process["elapsed_seconds"] = 961
    elif defect == "not_killed":
        process["returncode"] = 1
    elif defect == "not_started":
        process["process_started"] = False
    elif defect == "bad_scope":
        proof.pop("provider_receipt")
    write_json(folder / "process.json", process)
    (folder / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events))
    assert deadline.classify(tmp_path, directory, proof)["eligible"] is (defect is None)


@pytest.mark.parametrize("defect", ["terminal", "scope", "settlement", "negative", "replay"])
def test_changed_deadline_predecessor_is_rejected_without_new_calls(monkeypatch, defect):
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
        elif defect == "negative" and path == continuation.PRIOR / "calls/0002/call.json":
            result["response_text"] = result["response_text"].replace('"covered"', '"gap"')
        elif defect == "replay" and path == continuation.PRIOR / "replay-log.json":
            result["inherited"] = []
        return result

    monkeypatch.setattr(continuation, "read_json", read)
    with continuation.inventory.history.archive.access(), continuation.inventory.scope.accounting_scope(), continuation.inventory.pipeline():
        with pytest.raises(ValueError):
            continuation.predecessor_evidence()
    assert continuation.ACCOUNT.read_bytes() == before


@pytest.mark.parametrize("success", [False, True])
def test_deadline_retries_are_bounded_and_accounted(ledger_setup, monkeypatch, tmp_path, success):
    network = deadline.network
    plan = {**ledger_setup.plan, "version": network.recovery.MANUSCRIPT_VERSION,
            "recovery": network.policy(1), "technical_retries": 1, "delayed_network_extension": network.extension()}
    plan["plan_identity"] = digest({key: value for key, value in plan.items() if key != "plan_identity"})
    output = tmp_path / "bounded"
    ledger = AllocationLedger(output / "allocation-ledger.json", plan)
    model = ledger_setup.model
    model.test_plan = plan
    monkeypatch.setattr(network, "validate_snapshot", network.manuscript.validate_snapshot)
    calls, waits = [], []

    def provider(model, prompt, purpose=None, response_schema=None):
        calls.append(prompt)
        if success and len(calls) == 2:
            return test_automatic_manuscript_stage.synthetic_provider(model, prompt, purpose, response_schema)
        relative = f".humanvoice/runtime/deadline-{len(calls)}/record.json"
        folder = model.snapshot_dir / Path(relative).parent
        record = {"termination": "timeout", "created_at": "1970-01-01T00:16:40+00:00"}
        write_json(folder / "record.json", record)
        write_json(folder / "response.json", {"text": ""})
        model.last_runtime_record = {"path": relative, "hash": digest(record)}
        raise RuntimeError("Codex process exceeded its deadline")

    def failure(*arguments, **keywords):
        return {"eligible": True, "reason": "response_free_process_deadline"}

    monkeypatch.setattr(ModelAdapter, "invoke", provider)
    monkeypatch.setattr(network, "failure_evidence", failure)
    monkeypatch.setattr(network.recovery, "failure_evidence", failure)
    monkeypatch.setattr(network, "wait_until", lambda *arguments: waits.append(arguments))
    with network.pipeline(), network.accounted_model(output, plan, ledger):
        if success:
            ModelAdapter.invoke(model, "same-request", purpose="concept_extraction")
        else:
            with pytest.raises(RuntimeError, match="deadline"):
                ModelAdapter.invoke(model, "same-request", purpose="concept_extraction")
    assert calls == ["same-request", "same-request"] and len(waits) == 1
    assert sum(entry["usage"] is None for entry in ledger.record["calls"]) == (1 if success else 2)
    assert len(ledger.record["calls"]) <= ledger.record["max_calls"]


def test_deadline_bindings_restore_frozen_functions():
    previous = continuation.coverage
    before = previous.STAGE, previous.plan_for, previous.predecessor_evidence
    with continuation.bindings():
        assert previous.STAGE == continuation.STAGE
        assert previous.plan_for is continuation.plan_for
        assert continuation.NATIVE_PLAN is before[1]
    assert (previous.STAGE, previous.plan_for, previous.predecessor_evidence) == before


def test_deadline_controller_routes_only_zlb(monkeypatch):
    boundary = controller.previous.previous.previous.previous
    engine = boundary.identifier.previous.previous.previous.parallel.previous.engine
    prefix = engine.previous.previous.previous.previous.previous
    original = prefix.inventory, controller.scope.command
    calls = []
    monkeypatch.setattr(controller, "run_inventory", lambda *arguments: calls.append(arguments) or "deadline")

    def run():
        assert prefix.inventory("zlb", "snapshot", 540, "campaign", "refresh") == "deadline"
        command = controller.scope.command("verify-manuscript-boundary-20261007.py", "stage", "--phase", "test", "--next", "test")
        assert command[1] == str(controller.ROOT / "tools/inventory_deadline_runner.py")
        assert boundary.refresh is controller.refresh

    monkeypatch.setattr(boundary, "run", run)
    controller.run()
    assert calls == [("zlb", "snapshot", 540, "campaign", "refresh")]
    assert (prefix.inventory, controller.scope.command) == original and not controller.ACTIVE


def test_deadline_worker_used_for_launch_and_verification(tmp_path, monkeypatch):
    module = runner.previous.automatic_reproduction
    source = tmp_path / "source"
    monkeypatch.setattr(runner.previous.context, "selected_policy", lambda snapshot: {} if snapshot == source else None)
    command = [sys.executable, "-I", "-B", str(runner.ROOT / "tools/reproduction_overload_worker.py"), str(tmp_path / "worker")]
    monkeypatch.setattr(module, "_command", lambda *arguments: command)
    monkeypatch.setattr(module, "launch", lambda snapshot, output: module._command(output, True))
    monkeypatch.setattr(module, "evaluate_reproduction", lambda root, **keywords: module._command(root, True))
    write_json(tmp_path / "request.json", {"manifest": {"snapshot_path": str(source)}})
    native = module._command, module.launch, module.evaluate_reproduction
    with runner.reproduction_dispatch():
        assert module.launch(source, tmp_path)[3] == str(runner.ROOT / "tools/inventory_deadline_worker.py")
        assert module.evaluate_reproduction(tmp_path)[3] == str(runner.ROOT / "tools/inventory_deadline_worker.py")
        assert module.evaluate_reproduction(tmp_path, source_override=tmp_path) == command
    assert (module._command, module.launch, module.evaluate_reproduction) == native


def test_deadline_settlement_reader_survives_nested_scopes_and_spawn():
    inventory = continuation.inventory
    native = deadline.verification.verify_settlement
    with inventory.history.archive.access(), inventory.scope.accounting_scope(), deadline.runtime():
        with inventory.pipeline(), deadline.runtime(), inventory.pipeline():
            assert deadline.verification.verify_settlement is deadline.verify_settlement
            with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
                result = pool.submit(deadline.verification.verify_settlement, str(continuation.PRIOR)).result(timeout=60)
            assert result["report"]["allocated_calls"] == 4
            assert result["report"]["unknown_calls"] == 1
    assert deadline.verification.verify_settlement is native


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_deadline_recovery_settlement_replays_raw_receipts(codex, authorized, tmp_path, monkeypatch):
    inventory, network = continuation.inventory, deadline.network
    stage = continuation.manuscript
    authorization, _ = authorized
    monkeypatch.setattr(stage, "selected_profile", lambda: codex.profile)
    native_launch = codex_runtime.launch
    attempts, waits = [], []

    def launch(arguments, prompt, directory, timeout):
        attempts.append(prompt)
        if len(attempts) > 1:
            return native_launch(arguments, prompt, directory, timeout)
        (directory / "stderr.log").write_text("")
        (directory / "events.jsonl").write_text(json.dumps({"type": "thread.started", "thread_id": "synthetic-deadline"})
            + "\n" + json.dumps({"type": "turn.started"}) + "\n")
        write_json(directory / "process.json", {"status": "timeout", "returncode": -9, "process_started": True,
            "elapsed_seconds": 900.01, "deadline_seconds": timeout, "enforcement": "process-group-deadline-only"})

    monkeypatch.setattr(codex_runtime, "launch", launch)
    monkeypatch.setattr(network, "wait_until", lambda *arguments: waits.append(arguments))
    output = tmp_path / "stage"
    account_path = tmp_path / "account.json"
    with inventory.pipeline(planning=[(codex.snapshot, "inventory")], authorization=authorization), deadline.runtime():
        plan = stage.plan_for(codex.snapshot, "inventory", 1, account.HISTORICAL_CEILING)
        plan[deadline.FIELD] = deadline.policy()
        plan.pop("plan_identity")
        plan["plan_identity"] = digest(plan)
        write_json(output / "plan.json", plan)
        account.claim(plan, output, account=account_path)
        ledger = AllocationLedger(output / "allocation-ledger.json", plan)
        with stage.accounted_model(output, plan, ledger):
            assert codex.adapter.invoke("Synthetic same request.", purpose="concept_extraction", response_schema="extraction-response").text == "[]"
        write_json(output / "execution.json", {"status": "nonpass", "required": 1,
            "attempted": len(ledger.record["calls"]), "plan_identity": plan["plan_identity"]})
        usage = account.settle(output, account=account_path)["usage"]
        assert usage["allocated_calls"] == 2 and usage["unknown_calls"] == 1
        assert usage["retained_tokens"] == account.RESERVATION + 150
        assert deadline.verify_settlement(output)["report"] == usage
        layout = network.attempt_layout(output, plan, ledger.record["calls"], raw=lambda name: (output / name).read_bytes())
        assert layout["recoveries"] == 1 and layout["failures"][0]["reason"] == "response_free_process_deadline"
    assert attempts == ["Synthetic same request."] * 2 and len(waits) == 1
