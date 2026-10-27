"""Build later document successors from uniquely settled native parent evidence."""

import fcntl
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools import sol_inventory_program as original
from tools.inventory_recovery_v3 import accounting, execution, runtime, semantics
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.migration import verify_journal

VERSION = "inventory-settled-successor-v3"


def identified(value):
    value = {key: item for key, item in value.items() if key != "identity"}
    return {**value, "identity": digest(value)}


def retained(output):
    from tools.inventory_recovery_v3 import ancestry

    output = Path(output).absolute()
    initial_plan = runtime.validate_plan(read_json(output / "plan.json"))
    ancestry.validate(output, initial_plan)
    with ExitStack() as stack:
        for name in ("execution.lock", "executor.lock"):
            handle = stack.enter_context((output / name).open("rb"))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = runtime.validate_plan(read_json(output / "plan.json"))
        if plan != initial_plan:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native parent changed during ancestor validation")
        marker = plan[runtime.FIELD]
        initial = marker["transition"]
        terminal = read_json(output / "execution.json")
        if (terminal.get("status") != "nonpass" or terminal.get("plan_identity") != plan["plan_identity"]
                or read_json(output / "executor.json").get("status") != "stopped"):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor requires a stopped native nonpass")
        usage = accounting.verify_settlement(output)["report"]
        account = read_json(original.account.ACCOUNT)
        if [event["usage"] for event in account["events"] if event["kind"] == "settle"
                and event["usage"]["plan_identity"] == plan["plan_identity"]] != [usage]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor lost unique independent native settlement")
        entries = read_json(output / "allocation-ledger.json")["calls"]
        with runtime.runtime(plan, output):
            state = execution.layout(output, plan, entries)
        if state["pending"] is not None or state["mode"] not in {
                "decomposition_required", "size_decomposition_required", "external_block"}:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native failure is not eligible for a settled successor")
        proof = deepcopy(plan[original.adapter.FIELD]["predecessor"])
        prefix = proof["prefix"]
        receipts, invocations, requests = set(), set(), set()
        for row in prefix:
            journal, result, _record, entry = verify_journal(row["output"], row["attempt"], expected=row)
            if (result["status"] != "complete" or row["logical"] != len(receipts)
                    or journal["runtime_record"]["hash"] in receipts or entry["invocation_id"] in invocations
                    or journal["request_hash"] in requests):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Retained prefix changed native completion or membership")
            receipts.add(journal["runtime_record"]["hash"])
            invocations.add(entry["invocation_id"])
            requests.add(journal["request_hash"])
        for logical in range(state["logical"]):
            index = state["selected"][logical]
            journal, result, _record, entry = verify_journal(output, index)
            if (result["status"] != "complete" or journal["runtime_record"]["hash"] in receipts
                    or entry["invocation_id"] in invocations or journal["request_hash"] in requests):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor repeats or omits a completed native response")
            prefix.append({"output": str(output), "attempt": index, "logical": len(prefix),
                "request_hash": journal["request_hash"], "runtime_record": journal["runtime_record"],
                "call_sha256": digest((output / f"calls/{index:04d}/call.json").read_bytes())})
            receipts.add(journal["runtime_record"]["hash"])
            invocations.add(entry["invocation_id"])
            requests.add(journal["request_hash"])
        index = state["indices"][-1]
        journal, _result, record, _entry = verify_journal(output, index)
        with runtime.runtime(plan, output):
            failed = execution._failed(output, index, plan, entries[-1], None)
        target = state["incident"]["request"] if state["mode"] == "external_block" else journal["request"]
        created = datetime.fromisoformat(record["created_at"])
        if created.tzinfo is None or digest(target) in requests:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor lost its new unfinished request or receipt clock")
        inherited = marker["recovery_sessions_used"] + len(entries) - state["logical"]
        if inherited >= marker["policy"]["recovery_ceiling"]:
            raise RecoveryStop("BLOCKED_BUDGET", "Settled allocations exhausted the document recovery envelope")
        parent = {"eligible": True, "runtime_record_hash": journal["runtime_record"]["hash"],
            "request": target, "request_hash": digest(target), "eligible_after": created.timestamp() + 900,
            "parent_output": str(output), "settlement_hash": digest(usage), "diagnosis_hash": digest(failed)}
        snapshot = Path(plan["snapshot"])
        proof.update(predecessor=str(output), plan_identity=plan["plan_identity"], prefix=prefix,
            remaining_calls=len(plan["calls"]) - state["logical"],
            maximum_logical_calls=len(prefix) + len(plan["calls"]) - state["logical"],
            failed_request=target, transport_failure=failed, usage=usage,
            snapshot_hashes=original.lifecycle.retained.tree_hashes(snapshot),
            terminal_sha256=digest((output / "execution.json").read_bytes()),
            ledger_sha256=digest((output / "allocation-ledger.json").read_bytes()))
        value = {"version": VERSION, "mode": state["mode"], "proof": proof,
            "parent_failure": parent, "profile": deepcopy(plan["profile"]),
            "recovery_sessions_used": inherited, "rules": deepcopy(marker.get("split_rules", [])),
            "parent_plan_identity": plan["plan_identity"], "settlement_hash": digest(usage),
            "migration": deepcopy(initial["migration"]), "policy": deepcopy(initial["policy"]),
            "source_gate": deepcopy(initial["source_gate"]), "recovery_history": deepcopy(initial["recovery_history"]),
            "diagnostic_handoff": deepcopy(initial["diagnostic_handoff"]),
            "inherited_rules": deepcopy(initial.get("inherited_rules", initial["rules"])),
            "semantic_version": semantics.VERSION}
        if marker.get("fallback_qualification") is not None:
            value["fallback_qualification"] = deepcopy(marker["fallback_qualification"])
    if state["mode"] in {"decomposition_required", "size_decomposition_required"}:
        value["split_failure"] = semantics.settled_failure(output)
    return identified(value)


def split_successor(previous, observation):
    if previous != identified(previous) or previous["mode"] not in {"decomposition_required", "size_decomposition_required"}:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Split requires its exact settled failure transition")
    selected = semantics.rule(observation, previous["split_failure"])
    rules = [*previous["rules"], selected]
    semantics.validate_rules(rules, policy=previous["policy"], inherited=previous["inherited_rules"], origin=previous["migration"])
    extra = len(selected["recipe"]["children"]) - 1
    value = deepcopy(previous)
    value.update(retained_identity=previous["identity"], split_observation=deepcopy(observation),
                 first_request_requires_probe=True, rules=rules)
    value["proof"]["remaining_calls"] += extra
    value["proof"]["maximum_logical_calls"] += extra
    value["recovery_sessions_used"] += extra
    if value["recovery_sessions_used"] >= value["policy"]["recovery_ceiling"]:
        raise RecoveryStop("BLOCKED_BUDGET", "Split leaves no capacity for its required fresh canary")
    return identified(value)


def fallback_successor(previous, qualification):
    from tools import sol_inventory_reconnect_routing as routing
    from tools.inventory_recovery_v2 import qualification as native_qualification

    if previous != identified(previous):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Fallback requires exact settled failure evidence")
    selected = routing.next_profile(previous["profile"], previous["parent_failure"]["request"]["purpose"],
        {qualification["profile_hash"]: qualification},
        lambda evidence, profile: native_qualification.verify(evidence["output"], profile))
    if selected["status"] != "FALLBACK_QUALIFIED":
        raise RecoveryStop("BLOCKED_BUDGET", "Next ordered profile lacks funded native qualification")
    if qualification != selected["qualification"]:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Fallback changed its independently verified qualification")
    return identified({**previous, "retained_identity": previous["identity"], "profile": selected["profile"],
                       "fallback_qualification": deepcopy(selected["qualification"]), "fallback_selected": True})


def require_transition(transition):
    if transition.get("version") != VERSION or transition != identified(transition):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native successor identity changed")
    previous = retained(transition["proof"]["predecessor"])
    if transition.get("first_request_requires_probe"):
        expected = split_successor(previous, transition["split_observation"])
    elif transition.get("fallback_selected"):
        expected = fallback_successor(previous, transition["fallback_qualification"])
    else:
        expected = previous
    if expected != transition:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native successor changed its independently settled parent or budget")
    return transition
