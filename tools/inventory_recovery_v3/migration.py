"""Read sealed legacy evidence without rewriting history or granting authority."""

import fcntl
import json
from contextlib import ExitStack
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.failures import RecoveryStop


def account_boundary(path):
    account = read_json(path)
    return {"path": str(Path(path).absolute()),
            "events": len(account["events"]), "events_hash": digest(account["events"]),
            "plans": len(account["plans"]), "plans_hash": digest(account["plans"]),
            "fixed": {name: value for name, value in account.items() if name not in {
                "events", "plans", "reservation_ceiling", "gross_reservation_ceiling"}}}


def require_account_extension(boundary, path):
    account = read_json(path)
    current = account_boundary(path)
    if (boundary.get("path") != current["path"] or boundary.get("fixed") != current["fixed"]
            or any(type(boundary.get(name)) is not int or not 0 <= boundary[name] <= current[name]
                   or digest(account[name][:boundary[name]]) != boundary.get(name + "_hash")
                   for name in ("events", "plans"))):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Migration account history or authority changed")


def child(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("Evidence reference escaped its bound directory")
    return Path(root) / relative


def bound_record(path, identity_field):
    record = read_json(path)
    if record.get(identity_field) != digest({key: value for key, value in record.items()
                                            if key != identity_field}):
        raise ValueError("Evidence identity changed: " + str(path))
    return record


def verify_journal(output, index, *, expected=None):
    output = Path(output)
    plan = bound_record(output / "plan.json", "plan_identity")
    path = output / f"calls/{index:04d}/call.json"
    journal = read_json(path)
    result = read_json(path.with_name("result.json"))
    reference = journal["runtime_record"]
    record_path = child(plan["snapshot"], reference["path"])
    record = read_json(record_path)
    if (journal.get("request_hash") != digest(journal["request"])
            or digest(record) != reference["hash"]
            or result.get("request_hash") != journal["request_hash"]
            or result.get("evidence_error") is not None):
        raise ValueError("Retained call lost its request, result or runtime binding")
    for name, expected_hash in record["extensions"]["evidence_hashes"].items():
        if digest(child(record_path.parent, name).read_bytes()) != expected_hash:
            raise ValueError("Retained runtime payload changed")
    response = read_json(record_path.parent / "response.json")
    if (response.get("text") != journal.get("response_text")
            or any(record.get(name) != journal.get(name) for name in ("input_tokens", "output_tokens"))
            or result.get("status") == "complete" and (record.get("termination") != "complete"
                                                       or journal.get("status") != "complete")):
        raise ValueError("Retained response differs from its runtime receipt")
    ledger = read_json(output / "allocation-ledger.json")
    entries = [entry for entry in ledger["calls"]
               if entry["invocation_id"] == journal["invocation_id"]]
    if (len(entries) != 1 or entries[0].get("result_hash") != digest(result)
            or entries[0].get("status") != result.get("status")
            or entries[0].get("input_hash") != journal.get("call_contract_hash")):
        raise ValueError("Retained call lost its unique ledger allocation")
    if expected is not None and (expected.get("call_sha256") != digest(path.read_bytes())
            or expected.get("runtime_record") != reference
            or expected.get("request_hash") != journal["request_hash"]):
        raise ValueError("Retained prefix changed")
    return journal, result, record, entries[0]


def inspect_parent(output, account, *, verify_settlement, reconstruct, verify_qualification):
    output, account = Path(output), Path(account)
    names = ("plan.json", "execution.json", "allocation-ledger.json",
             "allocation-seal.json", "executor.json", "account-reservation.json")
    paths = [output / name for name in names] + [account]
    before = {str(path): digest(path.read_bytes()) for path in paths}
    plan = bound_record(output / "plan.json", "plan_identity")
    terminal = read_json(output / "execution.json")
    ledger = read_json(output / "allocation-ledger.json")
    seal = read_json(output / "allocation-seal.json")
    if (terminal.get("status") != "nonpass" or terminal.get("plan_identity") != plan["plan_identity"]
            or read_json(output / "executor.json").get("status") != "stopped"
            or ledger.get("plan_identity") != plan["plan_identity"]
            or seal.get("plan_identity") != plan["plan_identity"]
            or seal.get("ledger_hash") != digest(ledger)
            or seal.get("terminal_hash") != digest(terminal)):
        raise ValueError("Budget migration requires a sealed stopped nonpass")
    if any(entry.get("status") == "allocated_unknown" for entry in ledger["calls"]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Migration has unresolved allocations")
    usage = verify_settlement(output)["report"]
    events = read_json(account)["events"]
    settlements = [event["usage"] for event in events if event["kind"] == "settle"
                   and event["usage"]["plan_identity"] == plan["plan_identity"]]
    if settlements != [usage]:
        raise ValueError("Migration requires unique independently replayed settlement")
    state = reconstruct(output, plan, ledger["calls"])
    marker = plan["inventory_failure_first"]
    consumed = marker["recovery_sessions_used"] + state["recoveries"]
    limit = marker["contract"]["maximum_recovery_sessions"]
    if (state.get("pending") is not None or state["mode"] != "request"
            or state["logical"] not in state["selected"] or consumed != limit
            or not state.get("incident", {}).get("eligible")):
        raise ValueError("Sealed layout does not prove refusal of an unaffordable retry")
    rows = list(plan["sol_inventory_handoff"]["predecessor"]["prefix"])
    invocations, receipts = set(), set()
    for position, row in enumerate(rows):
        journal, result, _record, entry = verify_journal(row["output"], row["attempt"], expected=row)
        if (row["logical"] != position or result["status"] != "complete"
                or entry["invocation_id"] in invocations or journal["runtime_record"]["hash"] in receipts):
            raise ValueError("Prefix order, completion or receipt uniqueness changed")
        invocations.add(entry["invocation_id"])
        receipts.add(journal["runtime_record"]["hash"])
    for logical in range(state["logical"]):
        index = state["selected"][logical]
        journal, result, _record, entry = verify_journal(output, index)
        if (result["status"] != "complete" or entry["invocation_id"] in invocations
                or journal["runtime_record"]["hash"] in receipts):
            raise ValueError("New retained response is not uniquely completed")
        rows.append({"output": str(output), "attempt": index, "logical": len(rows),
                     "request_hash": journal["request_hash"], "runtime_record": journal["runtime_record"],
                     "call_sha256": digest((output / f"calls/{index:04d}/call.json").read_bytes())})
        invocations.add(entry["invocation_id"])
        receipts.add(journal["runtime_record"]["hash"])
    failed_index = state["selected"][state["logical"]]
    failed, failed_result, _record, _entry = verify_journal(output, failed_index)
    canary_index = state["indices"][-1]
    canary, canary_result, _record, _entry = verify_journal(output, canary_index)
    descriptor = read_json(output / f"reconnect-attempts/{canary_index:04d}.json")
    if (failed_result["status"] != "incomplete" or canary_result["status"] != "complete"
            or descriptor.get("kind") != "canary"
            or descriptor.get("incident_hash") != digest(state["incident"])
            or json.loads(canary["response_text"]) != []
            or failed["request_hash"] != state["incident"]["request_hash"]):
        raise ValueError("Budget migration lost its failed request or passing canary")
    qualification = marker.get("fallback_qualification")
    if qualification is not None and verify_qualification(qualification["output"], plan["profile"]) != qualification:
        raise ValueError("Retained qualification changed")
    value = {"version": "inventory-budget-migration-v1", "status": "OFFLINE_RECONCILED",
             "parent": str(output), "parent_plan_identity": plan["plan_identity"],
             "evidence": before, "account_boundary": account_boundary(account), "settlement_hash": digest(usage),
             "retained_prefix": rows, "retained_responses": len(rows),
             "remaining_requests": len(plan["calls"]) - state["logical"],
             "unfinished_request": failed["request"],
             "unfinished_request_hash": failed["request_hash"],
             "inherited_before_stage": marker["recovery_sessions_used"],
             "in_stage_extra_charge": state["recoveries"],
             "cumulative_recovery_charge": consumed,
             "legacy_successor_charge": marker["recovery_sessions_used"] + len(ledger["calls"]) - state["logical"],
             "profile_hash": digest(plan["profile"]), "qualification": qualification,
             "canary_receipt": canary["runtime_record"],
             "canary_reuse_authorized": False,
             "derived_category": "BLOCKED_BUDGET",
             "model_calls": 0, "account_writes": 0, "live_execution_enabled": False}
    if any(digest(Path(path).read_bytes()) != expected for path, expected in before.items()):
        raise ValueError("Historical evidence or authority changed during inspection")
    return {**value, "identity": digest(value)}


def inspect_production():
    from tools.inventory_history_adoption import no_inference
    from tools.inventory_recovery_v2 import campaign, execution, program, qualification

    value = campaign.cursor()
    output = Path(value["output"])
    with ExitStack() as stack:
        for path in (program.BASE / "active-session-program.lock",
                     output / "execution.lock", output / "executor.lock"):
            handle = stack.enter_context(path.open("rb"))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stack.enter_context(no_inference())
        stack.enter_context(program.history_scope())

        def reconstruct(root, plan, entries):
            with program.adapter.runtime(plan, root):
                return execution.layout(root, plan, entries)

        return inspect_parent(output, program.predecessor.account.ACCOUNT,
                              verify_settlement=program.adapter.verify_settlement,
                              reconstruct=reconstruct, verify_qualification=qualification.verify)
