"""Run an admitted native inventory stage and finalize only verified artifacts."""

import fcntl
import importlib.util
from contextlib import contextmanager

from humanvoice import codex_runtime
from humanvoice.artifacts import digest, read_json
from tools import sol_inventory_program as original
from tools.inventory_recovery_v2 import stage_execution as historical
from tools.inventory_recovery_v3 import (
    claim_tail,
    dispatcher,
    execution,
    journal_binding,
    native_consumption,
    runtime,
    schema_replay,
    semantics,
)
from tools.inventory_recovery_v3.failures import RecoveryStop, failure_record
from tools.inventory_recovery_v3.reservations import persist, regular_path
from tools.inventory_recovery_v3.stage_authority import CampaignAuthority, grant_stage
from tools.inventory_recovery_v3.stage_owner import owned_stage
from tools.inventory_recovery_v3.terminal import finalize_failure

specification = importlib.util.spec_from_file_location("tools._document_bundle_validation", historical.__file__)
bundle = importlib.util.module_from_spec(specification)
specification.loader.exec_module(bundle)
bundle.execution = execution


@contextmanager
def report_pause(output, plan, refresh):
    try:
        yield
    except BaseException as error:
        failure = failure_record(error, phase="executor_pause")
        if failure["category"] == "USER_STOPPED":
            path = regular_path(output / "execution.json")
            terminal = read_json(path)
            if terminal.get("plan_identity") != plan["plan_identity"]:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Pause cannot replace another plan's execution") from error
            committed = terminal.get("status") in {"pass", "nonpass"}
            sealed = regular_path(output / "allocation-seal.json").exists()
            if not committed and not sealed:
                terminal = {**terminal, "status": "paused_user", "failure": failure}
                persist(path, terminal)
            state = {"status": "USER_STOPPED", "plan_identity": plan["plan_identity"],
                     "failure": failure, "terminal_status": terminal["status"],
                     "terminal_hash": digest(terminal), "settlement_reconciliation_required": committed or sealed}
            persist(regular_path(output / "progress.json"), state)
            refresh(state)
        raise


def reconcile_terminal(current, plan, authority, refresh):
    path = regular_path(current.output / "execution.json")
    if not path.exists() or read_json(path).get("status") not in {"pass", "nonpass"}:
        return None
    with regular_path(current.output / "execution.lock").open("a") as execution_owner, (
            regular_path(current.output / "executor.lock").open("a")) as provider_owner, (
            report_pause(current.output, plan, refresh)):
        for handle in (execution_owner, provider_owner):
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        authority.check()
        terminal = read_json(path)
        if terminal.get("plan_identity") != plan["plan_identity"]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Retained terminal changed its admitted plan")
        before = path.read_bytes()
        if terminal["status"] == "pass":
            ledger = current.implementation.epoch.EpochLedger(current.output / "allocation-ledger.json", plan)
            with semantics.transition_runtime(current.transition), current.replay(
                    plan, current.output, plan[original.adapter.FIELD]["predecessor"], codex_runtime.validate_codex_record) as checked, (
                    runtime.runtime(plan, current.output, historical_validate=checked)), current.implementation.lifecycle.runtime():
                bundle.completed_bundle(current.implementation, plan, ledger)
        with grant_stage(authority, current.output):
            native_consumption.settle(current.implementation.account.settle, current.output, authority)
        if path.read_bytes() != before:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Terminal reconciliation changed retained evidence")
        return terminal


@schema_replay.scope()
def execute(current, *, authority, journal, refresh):
    if not isinstance(authority, CampaignAuthority) or not callable(refresh):
        raise TypeError("Native execution requires admitted ownership and durable status publication")
    authority.check()
    journal_binding.reconcile_journal(authority, journal)
    journal_binding.require_journal(authority, journal)
    with runtime.settlement_scope():
        claim_tail.reconcile(authority, current.output)
        plan = current.validate()
        journal_binding.require_history(current.output, plan, authority, journal)
        terminal = reconcile_terminal(current, plan, authority, refresh)
        if terminal is not None:
            refresh(terminal)
            return terminal
        output, snapshot = current.output, current.snapshot
        proof = plan[original.adapter.FIELD]["predecessor"]
        with owned_stage(output, plan, authority=authority) as (owner, ledger, _reservation), (
                report_pause(output, plan, refresh)):
            summary = {"status": "executing", "plan_identity": plan["plan_identity"],
                       "required": len(plan["calls"]), "maximum_calls": runtime.automatic_recovery.call_limit(plan),
                       "inherited_calls": len(proof["prefix"]), "qualification": False, "human_evidence": False}

            def publish(state):
                owner.check()
                value = {**state, "plan_identity": plan["plan_identity"], "inherited_calls": len(proof["prefix"])}
                persist(regular_path(output / "progress.json"), value)
                refresh(value)

            try:
                with semantics.transition_runtime(current.transition), dispatcher.accounted_model(
                        output, plan, ledger, journal=journal, owner=owner, publish=publish), current.replay(
                        plan, output, proof, codex_runtime.validate_codex_record) as checked, runtime.runtime(
                        plan, output, live=True, owner=owner, historical_validate=checked), (
                        current.implementation.lifecycle.runtime()):
                    dispatcher.reconcile_pairs(journal, owner, ledger)
                    frozen = (snapshot / ".humanvoice/inventory/baseline.json").exists()
                    if not frozen:
                        persist(regular_path(output / "execution.json"), summary)
                        code = current.implementation.lifecycle.previous.manuscript.run_manuscript_consumer(
                            output, snapshot, "inventory")
                        if code != 0 and not (snapshot / ".humanvoice/inventory/baseline.json").exists():
                            raise RecoveryStop("BLOCKED_ENGINEERING", "Native consumer stopped before a complete inventory bundle",
                                               evidence={"exit_code": code})
                    state = bundle.completed_bundle(current.implementation, plan, ledger)
                    summary.update(status="pass", exit_code=0, logical_calls=state["logical"],
                                   recoveries=state["recoveries"], offline_finalization=frozen,
                                   attempted=len(ledger.record["calls"]), reported_tokens=ledger.record["reported_tokens"])
                    owner.check()
                    summary["recovery_journal_checkpoint"] = digest(journal_binding.checkpoint(
                        output, plan, authority, journal, owner.check))
                    persist(regular_path(output / "execution.json"), summary)
            except BaseException as error:
                ledger.reload()
                failure = failure_record(error, phase="native_inventory")
                state = {**summary, "failure": failure, "attempted": len(ledger.record["calls"]),
                         "reported_tokens": ledger.record["reported_tokens"]}
                if failure["category"] == "USER_STOPPED":
                    raise
                if (isinstance(error, (KeyboardInterrupt, SystemExit))
                        or failure["category"] in {"BLOCKED_OWNERSHIP", "BLOCKED_ACCOUNTING"}
                        or any(entry["status"] == "allocated_unknown" for entry in ledger.record["calls"])):
                    state["status"] = "blocked_reconciliation"
                    persist(regular_path(output / "execution.json"), state)
                    refresh(state)
                    raise
                if (snapshot / ".humanvoice/inventory/baseline.json").exists():
                    state["status"] = "blocked_finalization"
                    persist(regular_path(output / "execution.json"), state)
                    refresh(state)
                    raise
                summary["recovery_journal_checkpoint"] = digest(journal_binding.checkpoint(
                    output, plan, authority, journal, owner.check))
                result = finalize_failure(output, summary, error, phase="native_inventory",
                    settle=lambda folder: native_consumption.settle(current.implementation.account.settle, folder, authority),
                    owner_check=owner.check, stop_check=owner.stop_check)
                refresh(result["terminal"])
                return result["terminal"]
            authority.check()
            native_consumption.settle(current.implementation.account.settle, output, authority)
            refresh(summary)
            return summary
