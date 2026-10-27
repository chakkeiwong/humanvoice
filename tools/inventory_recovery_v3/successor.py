"""Construct a document-budget successor from independently replayed sealed work."""

from copy import deepcopy
from datetime import datetime
from pathlib import Path

from humanvoice.artifacts import (
    digest,
    implementation_hash,
    policy_hash,
    read_json,
    validate_snapshot,
)
from humanvoice.automatic_qualification import schema_hash
from humanvoice.corpus_rights import require_rights
from tools import sol_inventory_program as original
from tools.inventory_recovery_v2 import runtime as historical
from tools.inventory_recovery_v3 import inheritance, runtime, semantics
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.migration import verify_journal
from tools.inventory_recovery_v3.policy import integer, require_capacity
from tools.inventory_recovery_v3.source_gate import budget_source_gate


def budget_transition(report, policy, *, account_path, verify_settlement, reconstruct, verify_qualification):
    gate = budget_source_gate(report, policy, account_path=account_path,
                             verify_settlement=verify_settlement, reconstruct=reconstruct,
                             verify_qualification=verify_qualification)
    output = Path(report["parent"])
    plan = historical.validate_plan(read_json(output / "plan.json"))
    entries = read_json(output / "allocation-ledger.json")["calls"]
    state = reconstruct(output, plan, entries)
    index = state["selected"][state["logical"]]
    failed, _result, record, _entry = verify_journal(output, index)
    created = datetime.fromisoformat(record["created_at"])
    if (created.tzinfo is None or failed["request"] != report["unfinished_request"]
            or gate["profile"] != plan["profile"]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor lost its exact failed request or receipt clock")
    parent = {"eligible": True, "runtime_record_hash": failed["runtime_record"]["hash"],
              "request": deepcopy(failed["request"]), "request_hash": failed["request_hash"],
              "eligible_after": created.timestamp() + policy["backoff_seconds"],
              "parent_output": str(output), "settlement_hash": report["settlement_hash"],
              "diagnosis_hash": digest(state["incident"])}
    history = inheritance.collect(output, account_path=account_path, verify_settlement=verify_settlement)
    diagnostic_handoff = inheritance.handoff(history, parent, digest(plan["profile"]), report["canary_receipt"])
    proof = deepcopy(plan[original.adapter.FIELD]["predecessor"])
    proof.update(predecessor=str(output), plan_identity=plan["plan_identity"],
        prefix=deepcopy(report["retained_prefix"]), remaining_calls=report["remaining_requests"],
        maximum_logical_calls=report["retained_responses"] + report["remaining_requests"],
        failed_request=deepcopy(failed["request"]), transport_failure=deepcopy(state["incident"]),
        usage=verify_settlement(output)["report"],
        snapshot_hashes=original.lifecycle.retained.tree_hashes(Path(plan["snapshot"])),
        terminal_sha256=digest((output / "execution.json").read_bytes()),
        ledger_sha256=digest((output / "allocation-ledger.json").read_bytes()))
    value = {"version": "inventory-budget-successor-v1", "mode": "budget_continuation",
             "migration": deepcopy(report), "policy": deepcopy(policy), "source_gate": gate,
             "recovery_history": history, "diagnostic_handoff": diagnostic_handoff,
             "proof": proof, "parent_failure": parent, "profile": deepcopy(plan["profile"]),
             "rules": deepcopy(plan[historical.FIELD].get("split_rules", [])),
             "inherited_rules": deepcopy(plan[historical.FIELD].get("split_rules", [])),
             "semantic_version": semantics.VERSION,
             "recovery_sessions_used": report["legacy_successor_charge"],
             "parent_plan_identity": plan["plan_identity"], "settlement_hash": report["settlement_hash"]}
    if report["qualification"] is not None:
        value["fallback_qualification"] = deepcopy(report["qualification"])
    return {**value, "identity": digest(value)}


def require_transition(transition):
    from tools.inventory_recovery_v3 import continuation

    if isinstance(transition, dict) and transition.get("version") == continuation.VERSION:
        return continuation.require_transition(transition)
    if (not isinstance(transition, dict)
            or transition.get("version") != "inventory-budget-successor-v1"
            or transition.get("identity") != digest({name: value for name, value in transition.items()
                                                       if name != "identity"})):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor transition identity changed")
    policy = require_capacity(transition["policy"])
    report, gate, proof = (transition[name] for name in ("migration", "source_gate", "proof"))
    history = inheritance.validate(transition["recovery_history"])
    if (any(record.get("identity") != digest({name: value for name, value in record.items() if name != "identity"})
            for record in (report, gate))
            or transition["mode"] != "budget_continuation"
            or transition["recovery_sessions_used"] != report["legacy_successor_charge"]
            or report["legacy_successor_charge"] != policy["inherited_recovery"]
            or transition["parent_plan_identity"] != report["parent_plan_identity"]
            or transition["settlement_hash"] != report["settlement_hash"]
            or digest(proof["usage"]) != report["settlement_hash"]
            or proof["predecessor"] != report["parent"]
            or proof["plan_identity"] != report["parent_plan_identity"]
            or proof["prefix"] != report["retained_prefix"]
            or proof["remaining_calls"] != report["remaining_requests"]
            or proof["maximum_logical_calls"] != len(proof["prefix"]) + proof["remaining_calls"]
            or proof["failed_request"] != report["unfinished_request"]
            or transition["parent_failure"]["request"] != report["unfinished_request"]
            or transition["profile"] != gate["profile"]
            or digest(transition["profile"]) != report["profile_hash"]
            or gate["policy_identity"] != policy["identity"]
            or gate["migration_identity"] != report["identity"]
            or gate["canary_reuse_authorized"] is not False
            or transition.get("fallback_qualification") != report["qualification"]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor changed retained work, profile or cumulative budget")
    if (history["parent"] != report["parent"] or history["source"] != gate["source_hash"]
            or transition["diagnostic_handoff"] != inheritance.handoff(history,
                transition["parent_failure"], digest(transition["profile"]), report["canary_receipt"])):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor changed inherited root consumption or diagnostic handoff")
    output = Path(report["parent"])
    if history != inheritance.collect(output, account_path=original.account.ACCOUNT,
                                      verify_settlement=historical.verify_settlement):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor omitted or changed native historical recovery")
    parent_plan = historical.validate_plan(read_json(output / "plan.json"))
    entries = read_json(output / "allocation-ledger.json")["calls"]
    from tools.inventory_recovery_v2 import execution

    with historical.runtime(parent_plan, output):
        state = execution.layout(output, parent_plan, entries)
    failed, _result, record, _entry = verify_journal(output, state["selected"][state["logical"]])
    created = datetime.fromisoformat(record["created_at"])
    expected = {"eligible": True, "runtime_record_hash": failed["runtime_record"]["hash"],
        "request": failed["request"], "request_hash": failed["request_hash"],
        "eligible_after": created.timestamp() + policy["backoff_seconds"],
        "parent_output": str(output), "settlement_hash": report["settlement_hash"],
        "diagnosis_hash": digest(state["incident"])}
    if (created.tzinfo is None or expected != transition["parent_failure"]
            or transition["rules"] != parent_plan[historical.FIELD].get("split_rules", [])
            or transition.get("inherited_rules") != transition["rules"]
            or transition.get("semantic_version") != semantics.VERSION):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor changed sealed failure timing, receipt or split rules")
    return transition


def plan_for(snapshot, transition, current, authority, *, proof=None, admission_report=None):
    transition = require_transition(transition)
    return _plan_for_verified(snapshot, transition, current, authority, proof=proof, admission_report=admission_report)


def _plan_for_verified(snapshot, transition, current, authority, *, proof=None, admission_report=None):
    document = transition["policy"]
    proof = deepcopy(transition["proof"] if proof is None else proof)
    expected = {**proof, "failed_request": transition["proof"]["failed_request"]}
    if (expected != transition["proof"] or proof != transition["proof"]
            and not transition.get("first_request_requires_probe")):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor changed its exact retained replay proof")
    parent_failure = {**deepcopy(transition["parent_failure"]),
                      "request": deepcopy(proof["failed_request"]),
                      "request_hash": digest(proof["failed_request"])}
    profile, inherited = transition["profile"], transition["recovery_sessions_used"]
    original.epoch.validate_account(current)
    recovery = runtime.policy(document, inherited)
    maximum = proof["remaining_calls"] + recovery["maximum_total"]
    integer(authority["available"], "available calls")
    integer(current["reservation_ceiling"], "reservation ceiling")
    integer(current["allowance"], "account allowance")
    if (maximum > authority["available"] or maximum > document["planned_calls"]
            or current["reservation_ceiling"] + maximum * document["token_reservation_per_call"] > current["allowance"]):
        raise RecoveryStop("BLOCKED_BUDGET", "Successor exceeds remaining call or token authority")
    snapshot = Path(snapshot).absolute()
    manifest = validate_snapshot(snapshot)
    if manifest["source_hash"] != transition["source_gate"]["source_hash"]:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor snapshot changed the frozen manuscript")
    rights = require_rights(snapshot, "remote-inference", destination=profile["runtime"]["responses_url"],
                            provider=profile["runtime"]["provider"])
    _baseline, token_grant, _position = original.epoch.baseline_for(current)
    parent = read_json(Path(proof["predecessor"]) / "plan.json")
    qualification = transition.get("fallback_qualification", parent[original.adapter.FIELD]["qualification"])
    bindings = {"snapshot": str(snapshot), "manifest": digest(manifest), "source": manifest["source_hash"],
                "policy": policy_hash(snapshot), "rights": digest(rights), "implementation": implementation_hash(),
                "profile": digest(profile), "stage": "inventory",
                "instrumentation": digest(Path(original.lifecycle.previous.manuscript.__file__).read_bytes())}
    value = {"version": runtime.automatic_recovery.MANUSCRIPT_VERSION,
        "snapshot": str(snapshot), "profile": deepcopy(profile), "bindings": bindings, "stage": "inventory",
        "purposes": sorted(original.lifecycle.previous.manuscript.PURPOSES["inventory"]),
        "prior_reservation_ceiling": current["reservation_ceiling"], "account_allowance": original.epoch.ALLOWANCE,
        original.epoch.FIELD: token_grant["identity"], "qualification": False, "human_evidence": False,
        "technical_retries": 1, "recovery": recovery,
        "calls": [{"key": f"inventory:{index:04d}", "input_hash": digest({"binding": bindings, "slot": index})}
                  for index in range(proof["remaining_calls"])],
        original.adapter.FIELD: {"contract": runtime.contract(), "qualification": qualification,
            "predecessor": deepcopy(proof), "logical_limit": proof["remaining_calls"],
            "maximum_transport_retries": recovery["maximum_total"], "grant_identity": authority["identity"],
            "response_schemas": schema_hash(), "authorization": original.AUTHORIZATION},
        runtime.FIELD: {"contract": runtime.contract(), "policy": deepcopy(document),
            "parent_failure": parent_failure, "recovery_sessions_used": inherited,
            "migration_identity": transition["migration"]["identity"], "profile_hash": digest(profile),
            "source_hash": manifest["source_hash"], "split_rules": deepcopy(transition["rules"]),
            "semantic_version": transition["semantic_version"],
            "inherited_rules": deepcopy(transition["inherited_rules"]),
            "transition": deepcopy(transition)}}
    if transition.get("fallback_qualification") is not None:
        value[runtime.FIELD]["fallback_qualification"] = deepcopy(transition["fallback_qualification"])
    if admission_report is not None:
        if (admission_report.get("status") != "pass" or admission_report.get("model_calls") != 0
                or admission_report.get("transition") != transition["identity"]
                or admission_report.get("contract") != runtime.contract()
                or admission_report.get("first_request") != proof["failed_request"]
                or not admission_report.get("observations_hash")):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Admitted plan lost its verified probe report")
        value[runtime.FIELD]["admission_probe_hash"] = digest(admission_report)
    value["plan_identity"] = digest(value)
    return runtime.validate_plan(value)
