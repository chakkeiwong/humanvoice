"""Import independently settled reconnect sequences without reserving them again."""

from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools import sol_inventory_reconnect_execution as reconnect_execution
from tools import sol_inventory_reconnect_runtime as reconnect_runtime
from tools.inventory_recovery_v2 import execution as historical_execution
from tools.inventory_recovery_v2 import runtime as historical_runtime
from tools.inventory_recovery_v2.cancellation import evidence as cancellation_evidence
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.migration import bound_record, verify_journal


def identified(value):
    return {**value, "identity": digest(value)}


def allocation(output, plan, index, journal):
    call, result, _record, entry = journal
    value = {"index": index, "invocation": entry["invocation_id"],
             "status": result["status"], "runtime_record": call["runtime_record"]}
    if result["status"] == "incomplete":
        cancelled = cancellation_evidence(output, output / f"calls/{index:04d}", plan, entry)
        if cancelled is not None:
            value["cancellation"] = cancelled
    return value


def collect(parent, *, account_path, verify_settlement):
    parent, output = Path(parent).absolute(), Path(parent).absolute()
    events = read_json(account_path)["events"]
    stages, sequences, visited, invocations, receipts = [], [], set(), set(), set()
    source = None
    boundary = None
    while True:
        if output.resolve() in visited:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Historical recovery ancestry contains a cycle")
        visited.add(output.resolve())
        plan = bound_record(output / "plan.json", "plan_identity")
        if source is None:
            source = plan["bindings"]["source"]
        if plan["bindings"]["source"] != source:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Historical recovery crossed manuscript sources")
        if historical_runtime.FIELD in plan:
            adapter, execution = historical_runtime, historical_execution
        elif reconnect_runtime.FIELD in plan:
            adapter, execution = reconnect_runtime, reconnect_execution
        else:
            boundary = {"output": str(output), "plan_identity": plan["plan_identity"]}
            break
        usage = verify_settlement(output)["report"]
        if [event["usage"] for event in events if event["kind"] == "settle"
                and event["usage"]["plan_identity"] == plan["plan_identity"]] != [usage]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Historical recovery lost its unique native settlement")
        entries = read_json(output / "allocation-ledger.json")["calls"]
        if any(entry["status"] not in {"complete", "incomplete"} for entry in entries):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Historical recovery has an unresolved allocation")
        with adapter.runtime(plan, output):
            state = execution.layout(output, plan, entries)
            if state["pending"] is not None:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Historical recovery is not fully reconciled")
            indices = state["indices"]
            journals = []
            for index in indices:
                journal, result, record, entry = verify_journal(output, index)
                if entry["invocation_id"] in invocations or journal["runtime_record"]["hash"] in receipts:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Historical recovery repeated a native invocation")
                invocations.add(entry["invocation_id"])
                receipts.add(journal["runtime_record"]["hash"])
                journals.append((journal, result, record, entry))
            stage_rows = []

            for position, index in enumerate(indices):
                descriptor = read_json(output / f"reconnect-attempts/{index:04d}.json")
                if descriptor["kind"] != "canary":
                    continue
                before = execution.layout(output, plan, entries[:position])
                incident = before["incident"]
                canary = allocation(output, plan, index, journals[position])
                retries = []
                for next_position in range(position + 1, len(indices)):
                    if canary.get("cancellation") is not None:
                        break
                    next_index = indices[next_position]
                    next_descriptor = read_json(output / f"reconnect-attempts/{next_index:04d}.json")
                    next_journal, _next_result, _next_record, _next_entry = journals[next_position]
                    if (next_descriptor["kind"] != "request"
                            or next_descriptor["logical"] != descriptor["logical"]
                            or next_descriptor["incident_hash"] != descriptor["incident_hash"]
                            or next_journal["request"] != incident["request"]):
                        raise RecoveryStop("BLOCKED_ACCOUNTING", "Historical canary lost its exact following retry")
                    retries.append(allocation(output, plan, next_index, journals[next_position]))
                    if retries[-1].get("cancellation") is None:
                        break
                retry = retries[-1] if retries else None
                row = identified({"output": str(output), "plan_identity": plan["plan_identity"],
                    "settlement_hash": digest(usage), "logical": descriptor["logical"],
                    "request": deepcopy(incident["request"]), "request_hash": digest(incident["request"]),
                    "profile_hash": digest(plan["profile"]), "incident_hash": digest(incident),
                    "failure_receipt_hash": incident["runtime_record_hash"],
                    "canary": canary, "retry": retry,
                    "retry_allocations": retries,
                    "diagnostic_only": retry is None and canary["status"] == "complete"})
                sequences.append(row)
                stage_rows.append(row["identity"])
        stages.append({"output": str(output), "plan_identity": plan["plan_identity"],
                       "settlement_hash": digest(usage), "ledger_hash": digest(read_json(output / "allocation-ledger.json")),
                       "sequences": stage_rows})
        proof = plan["sol_inventory_handoff"]["predecessor"]
        if not proof.get("predecessor"):
            boundary = {"output": str(output), "plan_identity": plan["plan_identity"]}
            break
        output = Path(proof["predecessor"]).absolute()
    return identified({"version": "inherited-reconnect-sequences-v1", "parent": str(parent),
                       "source": source, "boundary": boundary, "stages": stages,
                       "sequences": sequences, "new_reserved_calls": 0})


def validate(history):
    if (not isinstance(history, dict) or history.get("version") != "inherited-reconnect-sequences-v1"
            or history.get("identity") != digest({key: value for key, value in history.items() if key != "identity"})
            or history.get("new_reserved_calls") != 0):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited recovery history changed")
    rows = history["sequences"]
    identities = [row["identity"] for row in rows]
    if (len(set(identities)) != len(identities)
            or [identity for stage in history["stages"] for identity in stage["sequences"]] != identities):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited recovery membership is incomplete or repeated")
    for row in rows:
        if (row["identity"] != digest({key: value for key, value in row.items() if key != "identity"})
                or row["request_hash"] != digest(row["request"])
                or row["diagnostic_only"] is not (row["retry"] is None and row["canary"]["status"] == "complete")
                or row["canary"]["status"] not in {"complete", "incomplete"}
                or row["retry"] is not None and row["retry"]["status"] not in {"complete", "incomplete"}):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited recovery lost its allocated retry state")
        if "retry_allocations" in row:
            retries = row["retry_allocations"]
            if (not isinstance(retries, list) or row["retry"] != (retries[-1] if retries else None)
                    or any(item.get("cancellation") is None for item in retries[:-1])
                    or row["canary"].get("cancellation") is not None and retries):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited recovery changed cancelled allocation membership")
        for item in [row["canary"], *row.get("retry_allocations", [])]:
            cancellation = item.get("cancellation")
            if cancellation is not None and (item["status"] != "incomplete"
                    or cancellation.get("reason") != "explicit_user_cancelled_before_launch"
                    or cancellation.get("new_provider_calls") != 0
                    or cancellation.get("runtime_record_hash") != item["runtime_record"]["hash"]):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited recovery changed zero-launch evidence")
    return history


def handoff(history, failure, profile_hash, canary_reference):
    validate(history)
    selected = [row for row in history["sequences"] if row["canary"]["runtime_record"] == canary_reference]
    if (len(selected) != 1 or selected[0]["diagnostic_only"] is not True
            or selected[0]["output"] != failure["parent_output"]
            or selected[0]["failure_receipt_hash"] != failure["runtime_record_hash"]
            or selected[0]["request"] != failure["request"] or selected[0]["profile_hash"] != profile_hash):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Budget continuation lacks its exact unallocated historical retry")
    return {"sequence_identity": selected[0]["identity"], "incident_hash": digest(failure)}
