"""Drive exact native requests with complete paired recovery reservations."""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from humanvoice.artifacts import (
    digest,
    implementation_hash,
    read_json,
    validate_snapshot,
)
from humanvoice.model import ModelAdapter
from tools import delayed_network_runtime as network
from tools.inventory_recovery_v3 import execution, journal_binding, runtime
from tools.inventory_recovery_v3.allocation import PairedLedger
from tools.inventory_recovery_v3.failures import RecoveryStop, failure_record
from tools.inventory_recovery_v3.lineage import validate_lineage
from tools.inventory_recovery_v3.native_canary import NativeCanaryCheck
from tools.inventory_recovery_v3.native_settlement import settle_pair
from tools.inventory_recovery_v3.reservations import persist, regular_path
from tools.inventory_recovery_v3.stage_capacity import earmark_pair

ACTIVE = ContextVar("document_recovery_dispatch", default=None)


def require_dispatch(plan, output, owner):
    active = ACTIVE.get()
    if (active is None or active["owner"] is not owner or active["plan"] != plan
            or active["output"] != Path(output).absolute()):
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Provider launch requires its owned paired dispatcher")
    owner.check()
    ledger = active["ledger"]
    ledger.reload()
    entries = ledger.record["calls"]
    if not entries or entries[-1]["status"] != "allocated_unknown":
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Provider launch lost its allocated tail")
    if isinstance(ledger, PairedLedger):
        selected = ledger.journal.read()["sequences"][ledger.sequence]
        slot = selected["slots"][ledger.role]
        if slot["state"] != "dispatching" or slot.get("invocation") != entries[-1]["invocation_id"]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Provider launch lost its paired native allocation")
    return True


def reconcile_pairs(journal, owner, ledger):
    from tools.inventory_recovery_v3.cancellation import evidence, require_resume
    from tools.inventory_recovery_v3.reconcile import pending_result

    owner.check()
    ledger.reload()
    calls = runtime.implementation.automatic_recovery.attempt_calls(owner.plan)
    indices = {call["key"]: index for index, call in enumerate(calls)}
    for entry in ledger.record["calls"]:
        if entry["status"] == "incomplete":
            index = indices[entry["key"]]
            retained = read_json(owner.output / f"calls/{index:04d}/call.json")
            cancellation = evidence(owner.plan, owner.output, entry, index, retained)
            if cancellation is not None:
                require_resume(owner, cancellation)
    for sequence in journal.read()["sequences"].values():
        if sequence.get("native_stage", {}).get("output") != str(owner.output):
            continue
        for role, slot in sequence["slots"].items():
            if slot["state"] == "dispatching":
                if slot.get("native_allocation") is None:
                    wrapper = PairedLedger(ledger, journal, sequence["identity"], role,
                                           owner_check=owner.check, stop_check=owner.stop_check)
                    if wrapper.reconcile_allocation() is None:
                        continue
                pending_result(owner.output, owner.plan, ledger, owner=owner)
                settle_pair(journal, sequence["identity"], role,
                            owner_check=owner.check, stop_check=owner.stop_check, owner=owner)
    pending_result(owner.output, owner.plan, ledger, owner=owner)


@contextmanager
def accounted_model(output, plan, ledger, *, journal, owner, lineages=None, publish=lambda state: None):
    runtime.validate_plan(plan)
    output, snapshot = Path(output).absolute(), Path(plan["snapshot"])
    if (owner.plan != plan or owner.output != output or ledger.plan != plan
            or journal.policy != plan[runtime.FIELD]["policy"]
            or journal.binding["document"] != plan["bindings"]["source"]
            or journal.binding["migration"] != plan[runtime.FIELD]["migration_identity"]
            or lineages is not None and (len(lineages) != len(plan["calls"]) or len(set(lineages)) != len(lineages))):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Dispatcher lost its document or lineage scope")
    owner.check()
    record = journal_binding.require_journal(owner.authority, journal, plan)
    journal.publication_check = owner.check
    for identity in lineages or ():
        lineage = record["lineages"][identity]
        validate_lineage(lineage, ancestors=record["lineages"])
        if lineage["source_hash"] != plan["bindings"]["source"] or identity in record["splits"]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Dispatcher cannot execute retired or foreign lineage")
    from tools.inventory_recovery_v3.requests import NativeRequests

    resolver = None
    native, cursor, seen = ModelAdapter.invoke, 0, set()

    def sleep(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            owner.check()
            time.sleep(min(10, max(0, deadline - time.monotonic())))
        owner.check()

    def invoke(model, *arguments, **keywords):
        nonlocal cursor, resolver
        request = execution.predecessor.retained.canonical_request(model, arguments, keywords)
        runtime.validate_plan(plan)
        owner.check()
        if (model.mock_mode or Path(model.snapshot_dir).resolve() != snapshot.resolve()
                or request["purpose"] not in plan["purposes"] or cursor >= len(plan["calls"])
                or execution.predecessor.manuscript.selected_profile() != plan["profile"]
                or implementation_hash() != plan["bindings"]["implementation"]
                or digest(validate_snapshot(snapshot)) != plan["bindings"]["manifest"]
                or digest(request) in seen):
            raise ValueError("Document request changed its frozen native scope")
        logical = cursor
        if resolver is None and lineages is None:
            resolver = NativeRequests(plan, output, journal, owner)
        lineage = resolver.resolve(logical, request) if resolver is not None else lineages[logical]
        if journal.read()["lineages"][lineage]["purpose"] != request["purpose"]:
            raise ValueError("Document request changed its frozen lineage purpose")
        cursor += 1
        seen.add(digest(request))
        while True:
            owner.check()
            reconcile_pairs(journal, owner, ledger)
            ledger.reload()
            state = execution.layout(output, plan, ledger.record["calls"])
            if logical < state["logical"]:
                retained = read_json(output / f"calls/{state['selected'][logical]:04d}/call.json")
                if retained["request"] != request:
                    raise ValueError("Restart changed a retained manuscript request")
                response = execution.predecessor.restored_response(snapshot, plan["profile"], retained)
                model.last_runtime_record = response.runtime_record
                return response
            if logical != state["logical"]:
                raise ValueError("Document request skipped its unfinished logical slot")
            mode, incident = state["mode"], state["incident"]
            blocked = {"ambiguous": "BLOCKED_ACCOUNTING", "external_block": "BLOCKED_EXTERNAL",
                       "protocol_block": "BLOCKED_ENGINEERING", "engineering_block": "BLOCKED_ENGINEERING",
                       "size_decomposition_required": "BLOCKED_DECOMPOSITION",
                       "decomposition_required": "BLOCKED_DECOMPOSITION"}
            if mode in blocked:
                raise RecoveryStop(blocked[mode], mode, evidence={"incident": incident})
            ordinal = state["attempts"].get(logical, 0) + 1 if (
                mode == "canary" or logical in state["selected"]) else 0
            if (ordinal > plan["recovery"]["maximum_per_case"]
                    or ordinal and state["recoveries"] >= plan["recovery"]["maximum_total"]):
                raise RecoveryStop("BLOCKED_BUDGET", "Stage recovery allowance exhausted")
            active_ledger = ledger
            if incident:
                if request != incident["request"]:
                    raise ValueError("Recovery changed its exact failed request")
                sequence = journal.reserve(lineage=lineage, incident=digest(incident),
                    request_hash=digest(request), profile_hash=digest(plan["profile"]),
                    inherited_diagnostic=resolver.diagnostic_handoff(incident) if resolver is not None else None)
                if mode == "canary":
                    journal.bind_native_stage(sequence["identity"], output,
                                              owner_check=owner.check, stop_check=owner.stop_check)
                    if sequence.get("native_capacity") is None:
                        earmark_pair(journal, sequence["identity"], output,
                            account_path=owner.authority.account_path, grant_path=owner.authority.grant_path,
                            owner_check=owner.check, stop_check=owner.stop_check)
                    publish({"status": "RETRY_WAIT", "logical": logical, "eligible_after": incident["eligible_after"]})
                    network.wait_until(output / "reconnect-waits" / (digest(incident) + ".json"),
                                       digest(incident), incident["eligible_after"] - 900, sleep=sleep)
                sequence = journal.read()["sequences"][sequence["identity"]]
                role = "canary" if mode == "canary" else "retry"
                canary = sequence["slots"]["canary"].get("native_allocation")
                check = NativeCanaryCheck(output, plan["plan_identity"], canary["index"], clock=time.time) if canary else None
                active_ledger = PairedLedger(ledger, journal, sequence["identity"], role,
                    owner_check=owner.check, stop_check=owner.stop_check, canary_check=check)
            owner.check()
            index = logical + ordinal * len(plan["calls"])
            actual = execution.CANARY if mode == "canary" else request
            descriptor = {"plan_identity": plan["plan_identity"], "logical": logical, "index": index,
                          "kind": mode, "request": actual, "request_hash": digest(actual),
                          "incident_hash": digest(incident) if incident else None}
            path = regular_path(output / f"reconnect-attempts/{index:04d}.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and read_json(path) != descriptor:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Existing attempt descriptor changed")
            if not path.exists():
                persist(path, descriptor)
            key = f"{logical:04d}" + ("" if not ordinal else ":recovery" if ordinal == 1 else f":recovery-{ordinal}")
            publish({"status": "CANARY" if mode == "canary" else "EXECUTING", "logical": logical,
                     "attempt_index": index, "recoveries": state["recoveries"]})
            before = len(ledger.record["calls"])
            token = ACTIVE.set({"owner": owner, "plan": plan, "output": output, "ledger": active_ledger})
            try:
                response = execution.predecessor.attempt(output, plan, active_ledger, model, actual, index, key, native)
            except (ValueError, RuntimeError, OSError) as error:
                classified = failure_record(error, phase="native_attempt")
                if classified["category"] in {"USER_STOPPED", "BLOCKED_ACCOUNTING", "BLOCKED_OWNERSHIP"}:
                    raise RecoveryStop(classified["category"], classified["detail"], evidence=classified) from error
                ledger.reload()
                if len(ledger.record["calls"]) != before + 1:
                    raise
                continue
            finally:
                ACTIVE.reset(token)
            if mode == "request":
                ledger.reload()
                checked = execution.layout(output, plan, ledger.record["calls"])
                if checked["logical"] != logical + 1:
                    continue
                publish({"status": "VALIDATING", "logical": logical})
                return response

    ModelAdapter.invoke = invoke
    try:
        yield
    finally:
        ModelAdapter.invoke = native
        journal.publication_check = owner.authority.check
