"""Reproduce the actual exhausted-canary failure using native receipt accounting."""

import time
from contextlib import contextmanager
from datetime import datetime

import pytest
from test_failure_first_native import baseline, codex, prepared

from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.model import ModelAdapter, ModelConfig
from tools import sol_inventory_program as original
from tools.inventory_context import InvocationStopped, PromptModel
from tools.inventory_recovery_v2 import campaign, execution
from tools.inventory_recovery_v2 import runtime as adapter
from tools.inventory_recovery_v3.failures import failure_record, terminal_decision
from tools.inventory_recovery_v3.migration import inspect_parent
from tools.inventory_recovery_v3.native_canary import NativeCanaryCheck
from tools.inventory_recovery_v3.policy import proposal
from tools.inventory_recovery_v3.reservations import RecoveryReservations
from tools.inventory_recovery_v3.source_gate import budget_source_gate
from tools.inventory_recovery_v3.terminal import finalize_failure

__all__ = ["baseline", "codex", "prepared"]


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_exact_exhaustion_wrapper_settlement_and_campaign(prepared, monkeypatch, tmp_path):
    codex, account_path, plan, output, request = prepared
    plan[adapter.FIELD]["recovery_sessions_used"] = 14
    plan["recovery"] = adapter.policy(14)
    plan["plan_identity"] = digest({key: value for key, value in plan.items() if key != "plan_identity"})
    write_json(output / "plan.json", plan)
    native = ModelAdapter.invoke
    failed_once = []

    def provider(model, *arguments, **keywords):
        if keywords["prompt"] == "Next unfinished request" and not failed_once:
            failed_once.append(True)
            write_json(codex.settings, {"transport_failures": [
                {"purpose": "concept_extraction", "status": 504}]})
        else:
            write_json(codex.settings, {"response": []})
        return native(model, *arguments, **keywords)

    monkeypatch.setattr(ModelAdapter, "invoke", provider)
    native_wait = execution.network.wait_until

    @contextmanager
    def history():
        with original.epoch.accounting_scope(), adapter.settlement_scope(), (
                adapter.implementation.qualified.accounting.accounting_scope()):
            yield

    with history():
        original.epoch.claim(plan, output, account_path=account_path)
        ledger = original.epoch.EpochLedger(output / "allocation-ledger.json", plan)
        with adapter.implementation.automatic_recovery.exclusive_execution(output), adapter.runtime(
                plan, output, live=True, lock_fd=adapter.implementation.automatic_recovery.execution_fds()[0]):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            with execution.accounted_model(output, plan, ledger):
                model.invoke(**request)
                real_time, offset = time.time, [0]
                monkeypatch.setattr(time, "time", lambda: real_time() + offset[0])
                class ReceiptClock(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return datetime.fromtimestamp(time.time(), tz)

                from humanvoice import codex_runtime

                monkeypatch.setattr(codex_runtime, "datetime", ReceiptClock)
                def wait(path, identity, failed_at, **keywords):
                    offset[0] += max(0, failed_at + 900 - time.time())
                    return native_wait(path, identity, failed_at, clock=time.time)

                monkeypatch.setattr(execution.network, "wait_until", wait)
                with pytest.raises(InvocationStopped) as caught:
                    PromptModel(model, "").invoke(**{**request, "prompt": "Next unfinished request"})
            ledger.reload()
            assert [row["status"] for row in ledger.record["calls"]] == [
                "complete", "complete", "incomplete", "complete"]
            terminal = {"status": "nonpass", "plan_identity": plan["plan_identity"],
                        "required": 2, "attempted": 4,
                        "error": type(caught.value).__name__ + ": " + str(caught.value)}
            write_json(output / "execution.json", terminal)
            original.account.settle(output, account=account_path)
        monkeypatch.setattr(campaign.program, "history_scope", history)
        old = campaign.diagnose_terminal({"output": str(output)})
        assert old["status"] == "BLOCKED_SEMANTIC"
        typed = {**terminal, "failure": failure_record(caught.value, phase="request")}
        assert terminal_decision(typed)["status"] == "BLOCKED_BUDGET"
        before = account_path.read_bytes(), (output / "execution.json").read_bytes()

        def reconstruct(root, frozen_plan, entries):
            with adapter.runtime(frozen_plan, root):
                return execution.layout(root, frozen_plan, entries)

        report = inspect_parent(output, account_path, verify_settlement=adapter.verify_settlement,
                                reconstruct=reconstruct, verify_qualification=lambda *arguments: None)
        assert report["retained_responses"] == report["remaining_requests"] == 1
        assert report["in_stage_extra_charge"] == 2
        assert report["inherited_before_stage"] + report["in_stage_extra_charge"] == report["cumulative_recovery_charge"] == 16
        assert report["legacy_successor_charge"] == 17
        assert report["unfinished_request"]["prompt"] == "Next unfinished request"
        assert report["live_execution_enabled"] is False
        candidate = proposal(remaining_requests=1, inherited_recovery=17, incident_allowance=1,
                             split_allowance=0, qualification_calls=0,
                             available_calls=3, available_tokens=1632000)
        source = budget_source_gate(report, candidate, account_path=account_path,
            verify_settlement=adapter.verify_settlement, reconstruct=reconstruct,
            verify_qualification=lambda *arguments: None)
        assert source["profile"] == plan["profile"]
        assert source["legacy_successor_charge"] == 17
        assert source["new_qualification_calls"] == 0
        assert source["live_execution_enabled"] is False
        from tools.inventory_recovery_v2.continuation import predecessor_evidence

        with pytest.raises(ValueError, match="classified decomposition or availability"):
            predecessor_evidence(output)
        assert before == (account_path.read_bytes(), (output / "execution.json").read_bytes())
        assert read_json(output / "allocation-seal.json")["terminal_hash"] == digest(terminal)
        from copy import deepcopy

        from tools.inventory_recovery_v2.continuation import copy_snapshot
        from tools.inventory_recovery_v3 import runtime as document_runtime
        from tools.inventory_recovery_v3 import successor

        arguments = {"account_path": account_path, "verify_settlement": adapter.verify_settlement,
                     "reconstruct": reconstruct, "verify_qualification": lambda *arguments: None}
        transition = successor.budget_transition(report, candidate, **arguments)
        assert transition["proof"]["prefix"] == report["retained_prefix"]
        assert transition["parent_failure"]["request"] == report["unfinished_request"]
        assert transition["recovery_sessions_used"] == 17
        destination = tmp_path / "document-successor"
        snapshot = destination / "snapshot"
        copy_snapshot(snapshot, transition["proof"], transition["profile"])
        current = read_json(account_path)
        authority = {"available": 3, "identity": "fixture"}
        next_plan = successor.plan_for(snapshot, transition, current, authority)
        assert len(next_plan["calls"]) == 1
        assert next_plan["recovery"]["maximum_total"] == 2
        assert next_plan[document_runtime.FIELD]["recovery_sessions_used"] == 17
        assert next_plan[document_runtime.FIELD]["migration_identity"] == report["identity"]
        assert next_plan["profile"] == plan["profile"]
        assert (output / "execution.json").read_bytes() == before[1]
        assert account_path.read_bytes() == before[0]
        for defect in ("calls", "tokens", "prefix", "profile", "failure_time", "failure_receipt", "split_rules"):
            changed, funds, grant = deepcopy(transition), deepcopy(current), deepcopy(authority)
            if defect == "calls":
                grant["available"] -= 1
            elif defect == "tokens":
                funds["reservation_ceiling"] = funds["allowance"] - 3 * 544000 + 1
            elif defect == "prefix":
                changed["proof"]["prefix"] = []
            elif defect == "profile":
                changed["profile"]["model"]["version_string"] = "foreign"
            elif defect == "failure_time":
                changed["parent_failure"]["eligible_after"] = 900
            elif defect == "failure_receipt":
                changed["parent_failure"]["runtime_record_hash"] = "foreign"
            else:
                changed["rules"] = [{"foreign": True}]
            changed["identity"] = digest({key: value for key, value in changed.items() if key != "identity"})
            with pytest.raises((ValueError, RuntimeError)):
                successor.plan_for(snapshot, changed, funds, grant)
        write_json(destination / "plan.json", next_plan)
        with document_runtime.settlement_scope():
            original.epoch.claim(next_plan, destination, account_path=account_path)
        retained_account = account_path.read_bytes()
        assert retained_account != before[0]
        assert successor.budget_transition(report, candidate, **arguments) == transition
        assert account_path.read_bytes() == retained_account
        for defect in ("reservation_ceiling", "gross_reservation_ceiling", "unknown_event", "unmatched_plan"):
            changed = read_json(account_path)
            if defect.endswith("ceiling"):
                changed[defect] -= 1
            elif defect == "unknown_event":
                changed["events"].append({"kind": "unsupported"})
            else:
                changed["plans"].append({**changed["plans"][-1], "plan_identity": "unmatched"})
            write_json(account_path, changed)
            with pytest.raises((ValueError, RuntimeError)):
                successor.budget_transition(report, candidate, **arguments)
            account_path.write_bytes(retained_account)
        changed = read_json(account_path)
        changed["events"][0] = {"kind": "foreign"}
        write_json(account_path, changed)
        with pytest.raises((ValueError, RuntimeError)):
            successor.budget_transition(report, candidate, **arguments)
        account_path.write_bytes(retained_account)
        write_json(destination / "execution.json", {"status": "nonpass", "plan_identity": next_plan["plan_identity"],
                                                   "required": 1, "attempted": 0})
        with document_runtime.settlement_scope():
            original.account.settle(destination, account=account_path)
            released = read_json(account_path)
            assert released["reservation_ceiling"] == current["reservation_ceiling"]
            assert adapter.verify_settlement(output)["report"] == next(
                event["usage"] for event in released["events"] if event["kind"] == "settle"
                and event["usage"]["plan_identity"] == plan["plan_identity"])
            assert successor.budget_transition(report, candidate, **arguments) == transition


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_canary_evidence_drives_dispatch_once(prepared, monkeypatch, tmp_path):
    codex, account_path, plan, output, request = prepared
    native_attempt = execution.predecessor.attempt
    policy = proposal(remaining_requests=2, inherited_recovery=1, incident_allowance=1,
                      split_allowance=0, qualification_calls=0,
                      available_calls=4, available_tokens=2176000)
    journal = RecoveryReservations(tmp_path / "pairs", policy, {
        "document": plan["bindings"]["source"], "migration": "offline-fixture",
        "authority": "offline-fixture"})
    journal.initialize()
    incident = plan[adapter.FIELD]["parent_failure"]
    root = journal.register_root(purpose="concept_extraction", owned=["fixture-root"])
    sequence = journal.reserve(lineage=root["identity"], incident=digest(incident),
                               request_hash=digest(request), profile_hash=digest(plan["profile"]))
    journal.bind_native_stage(sequence["identity"], output, owner_check=lambda: True, stop_check=lambda: None)
    seen = []

    def attempt(*arguments):
        if arguments[4] == execution.CANARY:
            native_attempt(*arguments)
            index = arguments[5]
            native_journal = read_json(output / f"calls/{index:04d}/call.json")
            journal.dispatch(sequence["identity"], "canary", native_journal["invocation_id"],
                             owner_check=lambda: True, stop_check=lambda: None)
            journal.settle(sequence["identity"], "canary", receipt={
                "invocation": native_journal["invocation_id"], "quiescent": True,
                "outcome": "complete", "receipt_hash": native_journal["runtime_record"]["hash"],
                "reported_tokens": native_journal["input_tokens"] + native_journal["output_tokens"],
                "canary_valid": True}, verify=lambda receipt, binding, role: receipt)
            check = NativeCanaryCheck(output, plan["plan_identity"], index, clock=time.time)
            selected = journal.read()
            checked = check(selected["sequences"][sequence["identity"]], selected)
            assert checked["receipt_hash"] == native_journal["runtime_record"]["hash"]
            for field in ("authority", "migration"):
                from copy import deepcopy

                changed = deepcopy(selected)
                changed["binding"][field] = "changed"
                with pytest.raises(RuntimeError, match="bound execution scope"):
                    check(changed["sequences"][sequence["identity"]], changed)
            write_json(output / "execution.json", {"status": "nonpass",
                       "plan_identity": plan["plan_identity"], "required": len(plan["calls"]),
                       "attempted": 1})
            original.account.settle(output, account=account_path)
            with pytest.raises(RuntimeError, match="bound execution scope"):
                check(selected["sequences"][sequence["identity"]], selected)
            with pytest.raises(RuntimeError, match="active same-source stage"):
                journal.bind_native_stage(sequence["identity"], output,
                                          owner_check=lambda: True, stop_check=lambda: None)
            seen.append(check)
            raise FixtureSealed()
        return native_attempt(*arguments)

    class FixtureSealed(BaseException):
        pass

    monkeypatch.setattr(execution.predecessor, "attempt", attempt)
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        original.epoch.claim(plan, output, account_path=account_path)
        ledger = original.epoch.EpochLedger(output / "allocation-ledger.json", plan)
        with adapter.implementation.automatic_recovery.exclusive_execution(output), adapter.runtime(
                plan, output, live=True, lock_fd=adapter.implementation.automatic_recovery.execution_fds()[0]):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            with execution.accounted_model(output, plan, ledger), pytest.raises(FixtureSealed):
                model.invoke(**request)
            assert len(seen) == 1
            selected = journal.read()
            with pytest.raises((ValueError, RuntimeError)):
                seen[0](selected["sequences"][sequence["identity"]], selected)


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_typed_terminal_precedes_native_seal_and_resumes_after_crash(prepared):
    codex, account_path, plan, output, request = prepared
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        original.epoch.claim(plan, output, account_path=account_path)
        ledger = original.epoch.EpochLedger(output / "allocation-ledger.json", plan)
        with adapter.implementation.automatic_recovery.exclusive_execution(output), adapter.runtime(
                plan, output, live=True, lock_fd=adapter.implementation.automatic_recovery.execution_fds()[0]):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            with execution.accounted_model(output, plan, ledger):
                model.invoke(**request)
            summary = {"plan_identity": plan["plan_identity"]}
            error = execution.RecoveryBlocked("BLOCKED_BUDGET", "fixture limit")

            def interrupted(root):
                raise OSError("crash after terminal")

            with pytest.raises(OSError, match="crash after terminal"):
                finalize_failure(output, summary, error, phase="request",
                                 owner_check=lambda: True, stop_check=lambda: None, settle=interrupted)
            terminal = read_json(output / "execution.json")
            assert terminal["failure"]["category"] == "BLOCKED_BUDGET"
            assert not (output / "allocation-seal.json").exists()
            settle = lambda root: original.account.settle(root, account=account_path)
            result = finalize_failure(output, summary, error, phase="request",
                                      owner_check=lambda: True, stop_check=lambda: None, settle=settle)
            assert result["diagnosis"]["status"] == "BLOCKED_BUDGET"
            before = account_path.read_bytes(), (output / "execution.json").read_bytes()
            assert finalize_failure(output, summary, error, phase="request",
                                    owner_check=lambda: True, stop_check=lambda: None, settle=settle) == result
            assert before == (account_path.read_bytes(), (output / "execution.json").read_bytes())
            assert adapter.verify_settlement(output)["report"]["allocated_calls"] == 2
