"""Pair dispatch intent must precede actual native invocation allocation."""

import multiprocessing
import os
import time
from contextlib import ExitStack

import pytest
from test_failure_first_native import baseline, codex, prepared

from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.model import ModelAdapter, ModelConfig
from tools import automatic_call_grant as grants
from tools import sol_inventory_program as original
from tools.inventory_recovery_v2 import execution
from tools.inventory_recovery_v2 import runtime as adapter
from tools.inventory_recovery_v3.allocation import PairedLedger
from tools.inventory_recovery_v3.migration import verify_journal
from tools.inventory_recovery_v3.native_canary import NativeCanaryCheck
from tools.inventory_recovery_v3.native_settlement import settle_pair
from tools.inventory_recovery_v3.policy import proposal
from tools.inventory_recovery_v3.reservations import RecoveryReservations
from tools.inventory_recovery_v3.stage_capacity import earmark_pair

__all__ = ["baseline", "codex", "prepared"]


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("crash_after_allocation", ["none", "canary", "retry"])
def test_pair_and_native_receipts_share_real_invocations(prepared, tmp_path, monkeypatch, crash_after_allocation):
    codex, account_path, plan, output, request = prepared
    policy = proposal(remaining_requests=2, inherited_recovery=1, incident_allowance=1,
                      split_allowance=0, qualification_calls=0,
                      available_calls=4, available_tokens=2176000)
    journal = RecoveryReservations(tmp_path / "pairs", policy, {
        "document": plan["bindings"]["source"], "migration": "fixture", "authority": "fixture"})
    journal.initialize()
    root = journal.register_root(purpose="concept_extraction", owned=["source-member"])
    sequence = journal.reserve(lineage=root["identity"], incident=digest(plan[adapter.FIELD]["parent_failure"]),
                               request_hash=digest(request), profile_hash=digest(plan["profile"]))
    journal.bind_native_stage(sequence["identity"], output, owner_check=lambda: True, stop_check=lambda: None)
    native_attempt = execution.predecessor.attempt
    observed = []

    class CrashBoundary(BaseException):
        pass

    def attempt(output, frozen, ledger, model, actual, index, key, native):
        role = "canary" if actual == execution.CANARY else "retry"
        canary_index = len(frozen["calls"])
        wrapper = PairedLedger(ledger, journal, sequence["identity"], role,
            owner_check=lambda: True, stop_check=lambda: None,
            canary_check=NativeCanaryCheck(output, frozen["plan_identity"], canary_index, clock=time.time))
        wrong = PairedLedger(ledger, journal, sequence["identity"],
                             "retry" if role == "canary" else "canary",
                             owner_check=lambda: True, stop_check=lambda: None)
        before = journal.path.read_bytes(), ledger.path.read_bytes()
        with pytest.raises(RuntimeError, match="role or incident"):
            wrong.reserve(frozen["stage"], key)
        assert before == (journal.path.read_bytes(), ledger.path.read_bytes())
        if crash_after_allocation == role:
            original_save = journal.save

            def save(record):
                slot = record["sequences"][sequence["identity"]]["slots"][role]
                if slot.get("native_allocation") is not None:
                    raise CrashBoundary()
                original_save(record)

            monkeypatch.setattr(journal, "save", save)
            with pytest.raises(CrashBoundary):
                wrapper.reserve(frozen["stage"], key)
            monkeypatch.setattr(journal, "save", original_save)
            before = len(ledger.record["calls"])
            entry = wrapper.reconcile_allocation()
            assert journal.read()["sequences"][sequence["identity"]]["slots"][role]["invocation"] == entry["invocation_id"]
            with pytest.raises(RuntimeError, match="requires reconciliation"):
                wrapper.reserve(frozen["stage"], key)
            assert len(ledger.record["calls"]) == before == (1 if role == "canary" else 2)
            observed.append(role)
            raise CrashBoundary()

        def invoke(model, **keywords):
            slot = journal.read()["sequences"][sequence["identity"]]["slots"][role]
            ledger.reload()
            assert slot["invocation"] == ledger.record["calls"][-1]["invocation_id"]
            assert slot["state"] == "dispatching"
            return native(model, **keywords)

        response = native_attempt(output, frozen, wrapper, model, actual, index, key, invoke)

        def verify(_receipt, selected, selected_role):
            retained, result, runtime, entry = verify_journal(output, index)
            assert selected_role == role
            assert selected["slots"][role]["invocation"] == entry["invocation_id"]
            process = read_json(codex.snapshot / retained["runtime_record"]["path"]).get("termination")
            assert process == "complete"
            return {"invocation": entry["invocation_id"], "quiescent": True,
                    "outcome": result["status"], "receipt_hash": retained["runtime_record"]["hash"],
                    "reported_tokens": runtime["input_tokens"] + runtime["output_tokens"],
                    "canary_valid": role == "canary"}

        journal.settle(sequence["identity"], role, receipt={"index": index}, verify=verify)
        observed.append(role)
        return response

    monkeypatch.setattr(execution.predecessor, "attempt", attempt)
    with ExitStack() as stack, original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        grant_path = tmp_path / "grant.json"
        grants.create(grant_path, original.epoch.call_limit(plan), "offline fixture", account=account_path)
        stack.enter_context(grants.stage(grant_path, output))
        original.epoch.claim(plan, output, account_path=account_path)
        earmark_pair(journal, sequence["identity"], output, account_path=account_path, grant_path=grant_path,
                     owner_check=lambda: True, stop_check=lambda: None)
        ledger = original.epoch.EpochLedger(output / "allocation-ledger.json", plan)
        with adapter.implementation.automatic_recovery.exclusive_execution(output), adapter.runtime(
                plan, output, live=True, lock_fd=adapter.implementation.automatic_recovery.execution_fds()[0]):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            with execution.accounted_model(output, plan, ledger):
                if crash_after_allocation != "none":
                    with pytest.raises(CrashBoundary):
                        model.invoke(**request)
                    assert observed == (["canary"] if crash_after_allocation == "canary" else ["canary", "retry"])
                else:
                    model.invoke(**request)
                    assert observed == ["canary", "retry"]
                    assert journal.status()["completed"] == 2
                    slots = journal.read()["sequences"][sequence["identity"]]["slots"]
                    assert {slot["invocation"] for slot in slots.values()} == {entry["invocation_id"] for entry in ledger.record["calls"]}
                fresh = RecoveryReservations(tmp_path / "fresh-pair", policy, journal.binding)
                fresh.initialize()
                fresh_root = fresh.register_root(purpose="concept_extraction", owned=["source-member"])
                fresh_sequence = fresh.reserve(lineage=fresh_root["identity"], incident=sequence["incident"],
                    request_hash=sequence["request_hash"], profile_hash=sequence["profile_hash"])
                fresh.bind_native_stage(fresh_sequence["identity"], output,
                                        owner_check=lambda: True, stop_check=lambda: None)
                wrapper = PairedLedger(ledger, fresh, fresh_sequence["identity"], "canary",
                                      owner_check=lambda: True, stop_check=lambda: None)
                before = fresh.path.read_bytes()
                with pytest.raises(RuntimeError, match="requires reconciliation"):
                    wrapper.reserve(plan["stage"], ledger.record["calls"][0]["case_id"])
                assert fresh.path.read_bytes() == before
                assert list(fresh.root.glob("*-allocation.json")) == []


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("role", ["canary", "retry"])
@pytest.mark.parametrize("cut", ["allocation", "settlement"])
def test_native_pair_cold_mapping_and_result_settlement(prepared, tmp_path, monkeypatch, role, cut):
    codex, account_path, plan, output, request = prepared
    policy = proposal(remaining_requests=2, inherited_recovery=1, incident_allowance=1,
                      split_allowance=0, qualification_calls=0, available_calls=4, available_tokens=2176000)
    journal = RecoveryReservations(tmp_path / "pairs", policy, {"document": plan["bindings"]["source"],
                                   "migration": "fixture", "authority": "fixture"})
    journal.initialize()
    root = journal.register_root(purpose="concept_extraction", owned=["source-member"])
    sequence = journal.reserve(lineage=root["identity"], incident=digest(plan[adapter.FIELD]["parent_failure"]),
                               request_hash=digest(request), profile_hash=digest(plan["profile"]))
    journal.bind_native_stage(sequence["identity"], output, owner_check=lambda: True, stop_check=lambda: None)
    native_attempt = execution.predecessor.attempt

    def attempt(output, frozen, ledger, model, actual, index, key, native):
        selected_role = "canary" if actual == execution.CANARY else "retry"
        wrapper = PairedLedger(ledger, journal, sequence["identity"], selected_role,
            owner_check=lambda: True, stop_check=lambda: None,
            canary_check=NativeCanaryCheck(output, frozen["plan_identity"], len(frozen["calls"]), clock=time.time))
        if selected_role == role:
            save = journal.save

            def crash(record):
                slot = record["sequences"][sequence["identity"]]["slots"][role]
                if (cut == "allocation" and slot.get("native_allocation") is not None
                        or cut == "settlement" and slot["state"] in {"complete", "incomplete"}):
                    os._exit(73)
                return save(record)

            journal.save = crash
        return native_attempt(output, frozen, wrapper, model, actual, index, key, native)

    monkeypatch.setattr(execution.predecessor, "attempt", attempt)
    with ExitStack() as stack, original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        grant_path = tmp_path / "grant.json"
        grants.create(grant_path, original.epoch.call_limit(plan), "offline fixture", account=account_path)
        stack.enter_context(grants.stage(grant_path, output))
        original.epoch.claim(plan, output, account_path=account_path)
        earmark_pair(journal, sequence["identity"], output, account_path=account_path, grant_path=grant_path,
                     owner_check=lambda: True, stop_check=lambda: None)

        def worker():
            ledger = original.epoch.EpochLedger(output / "allocation-ledger.json", plan)
            with adapter.implementation.automatic_recovery.exclusive_execution(output), adapter.runtime(
                    plan, output, live=True, lock_fd=adapter.implementation.automatic_recovery.execution_fds()[0]):
                model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
                with execution.accounted_model(output, plan, ledger):
                    model.invoke(**request)

        process = multiprocessing.get_context("fork").Process(target=worker)
        process.start()
        process.join(30)
        assert not process.is_alive() and process.exitcode == 73
        before = [path.read_bytes() for path in (account_path, grant_path, output / "allocation-ledger.json")]
        reopened = RecoveryReservations(journal.root, policy, journal.binding)
        ledger = original.epoch.EpochLedger(output / "allocation-ledger.json", plan)
        wrapper = PairedLedger(ledger, reopened, sequence["identity"], role,
                              owner_check=lambda: True, stop_check=lambda: None)
        with adapter.implementation.automatic_recovery.exclusive_execution(output), adapter.runtime(
                plan, output, live=True, lock_fd=adapter.implementation.automatic_recovery.execution_fds()[0]):
            entry = wrapper.reconcile_allocation()
            if cut == "allocation":
                assert entry["status"] == "allocated_unknown"
                with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
                    settle_pair(reopened, sequence["identity"], role, owner_check=lambda: True, stop_check=lambda: None)
            else:
                retained = settle_pair(reopened, sequence["identity"], role, owner_check=lambda: True, stop_check=lambda: None)
                assert retained["state"] == "complete"
                assert settle_pair(reopened, sequence["identity"], role,
                                   owner_check=lambda: True, stop_check=lambda: None) == retained
            assert len(ledger.record["calls"]) == (1 if role == "canary" else 2)
            with pytest.raises(RuntimeError, match="requires reconciliation"):
                wrapper.reserve(plan["stage"], entry["case_id"])
        assert before == [path.read_bytes() for path in (account_path, grant_path, output / "allocation-ledger.json")]


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("target_role", ["canary", "retry"])
def test_settlement_rejects_genuine_foreign_runtime_request(prepared, tmp_path, monkeypatch, target_role):
    from tools.inventory_recovery_v3 import native_settlement

    codex, account_path, plan, output, request = prepared
    policy = proposal(remaining_requests=2, inherited_recovery=1, incident_allowance=1,
                      split_allowance=0, qualification_calls=0, available_calls=4, available_tokens=2176000)
    journal = RecoveryReservations(tmp_path / "pairs", policy, {"document": plan["bindings"]["source"],
                                   "migration": "fixture", "authority": "fixture"})
    journal.initialize()
    root = journal.register_root(purpose="concept_extraction", owned=["source-member"])
    sequence = journal.reserve(lineage=root["identity"], incident=digest(plan[adapter.FIELD]["parent_failure"]),
                               request_hash=digest(request), profile_hash=digest(plan["profile"]))
    journal.bind_native_stage(sequence["identity"], output, owner_check=lambda: True, stop_check=lambda: None)
    native_attempt = execution.predecessor.attempt
    delayed = []

    def defer(journal, identity, role, **keywords):
        if role == target_role:
            delayed.append(role)
            return None
        return settle_pair(journal, identity, role, **keywords)

    def attempt(output, frozen, ledger, model, actual, index, key, native):
        if delayed:
            return native_attempt(output, frozen, ledger, model, actual, index, key, native)
        role = "canary" if actual == execution.CANARY else "retry"
        wrapper = PairedLedger(ledger, journal, sequence["identity"], role,
            owner_check=lambda: True, stop_check=lambda: None,
            canary_check=NativeCanaryCheck(output, frozen["plan_identity"], len(frozen["calls"]), clock=time.time))
        return native_attempt(output, frozen, wrapper, model, actual, index, key, native)

    monkeypatch.setattr(native_settlement, "settle_pair", defer)
    monkeypatch.setattr(execution.predecessor, "attempt", attempt)
    with ExitStack() as stack, original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        grant_path = tmp_path / "grant.json"
        grants.create(grant_path, original.epoch.call_limit(plan), "offline fixture", account=account_path)
        stack.enter_context(grants.stage(grant_path, output))
        original.epoch.claim(plan, output, account_path=account_path)
        earmark_pair(journal, sequence["identity"], output, account_path=account_path, grant_path=grant_path,
                     owner_check=lambda: True, stop_check=lambda: None)
        ledger = original.epoch.EpochLedger(output / "allocation-ledger.json", plan)
        with adapter.implementation.automatic_recovery.exclusive_execution(output), adapter.runtime(
                plan, output, live=True, lock_fd=adapter.implementation.automatic_recovery.execution_fds()[0]):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            with execution.accounted_model(output, plan, ledger):
                model.invoke(**request)
                model.invoke(**{**request, "prompt": "Genuine unrelated receipt returning an empty array"})
            assert delayed == [target_role]
            index = len(plan["calls"]) if target_role == "canary" else 0
            target_path = output / f"calls/{index:04d}/call.json"
            retained = read_json(target_path)
            foreign, _result, record, _entry = verify_journal(output, 1)
            assert retained["request"] != foreign["request"]
            assert foreign["response_text"] == "[]"
            assert adapter.implementation.capture.validate_record(codex.snapshot, foreign["runtime_record"]) == record
            substituted = {**retained, **{name: foreign[name] for name in
                           ("runtime_record", "response_text", "input_tokens", "output_tokens")}}
            write_json(target_path, substituted)
            assert verify_journal(output, index)[0] == substituted
            paths = [journal.path, account_path, grant_path, output / "allocation-ledger.json"]
            before = [path.read_bytes() for path in paths]
            with pytest.raises(RuntimeError, match="runtime request differs"):
                settle_pair(journal, sequence["identity"], target_role, owner_check=lambda: True, stop_check=lambda: None)
            assert before == [path.read_bytes() for path in paths]
            write_json(target_path, retained)
            assert settle_pair(journal, sequence["identity"], target_role,
                               owner_check=lambda: True, stop_check=lambda: None)["state"] == "complete"
