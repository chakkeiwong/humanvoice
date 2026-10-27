"""Settle paired allocations only from intact quiescent native result receipts."""

import json
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.migration import child, verify_journal


def settle_pair(journal, identity, role, *, owner_check, stop_check, owner=None):
    from tools.inventory_recovery_v3.native_dispatch import modules

    if role not in {"canary", "retry"}:
        raise ValueError("Native settlement requires an exact pair role")
    if owner_check() is not True:
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Pair settlement requires the exclusive native owner")
    stop_check()

    def verify(_receipt, sequence, selected_role):
        slot = sequence["slots"][selected_role]
        allocation = slot.get("native_allocation")
        scope = sequence.get("native_stage", {})
        if allocation is None or allocation.get("output") != scope.get("output"):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native settlement lacks its mapped allocation")
        output = Path(allocation["output"])
        plan = read_json(output / "plan.json")
        execution, runtime = modules(plan)
        intent = read_json(journal.root / (identity + "-" + role + "-allocation.json"))
        value = {key: item for key, item in intent.items() if key != "identity"}
        if (intent.get("identity") != digest(value)
                or allocation != {**value, "intent_identity": intent["identity"]}
                or intent.get("sequence") != identity or intent.get("role") != selected_role
                or plan.get("plan_identity") != scope.get("plan_identity")
                or digest(plan["profile"]) != sequence["profile_hash"]
                or plan["bindings"]["source"] != journal.binding["document"]
                or scope.get("policy_identity") != journal.policy["identity"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native settlement changed allocation or source scope")
        index = intent["index"]
        retained, result, receipt, entry = verify_journal(output, index)
        if "inventory_document_recovery" in plan:
            from tools.inventory_recovery_v3.runtime_binding import (
                verify as verify_runtime,
            )

            verify_runtime(plan, output, entry, index, retained)
        entries = read_json(output / "allocation-ledger.json")["calls"]
        prefix = intent["prefix_count"]
        descriptor = read_json(output / f"reconnect-attempts/{index:04d}.json")
        if (type(prefix) is not int or prefix < 0 or len(entries) <= prefix or entries[prefix] != entry
                or digest(entries[:prefix]) != intent["prefix_hash"]
                or digest(descriptor) != intent["descriptor_hash"]
                or entry["invocation_id"] != slot["invocation"]
                or entry["key"] != intent["key"] or entry["input_hash"] != intent["input_hash"]
                or descriptor["incident_hash"] != sequence["incident"]
                or descriptor["kind"] != ("canary" if selected_role == "canary" else "request")
                or digest(retained["request"]) != intent["request_hash"]
                or selected_role == "retry" and retained["request_hash"] != sequence["request_hash"]
                or selected_role == "canary" and retained["request"] != execution.CANARY):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native result differs from the exact pair allocation")
        checked = runtime.implementation.capture.validate_record(Path(plan["snapshot"]), retained["runtime_record"])
        folder = child(plan["snapshot"], retained["runtime_record"]["path"]).parent
        process = read_json(folder / "process.json")
        request = read_json(folder / "inputs/api-request.json")
        prompt = (folder / "inputs/prompt.txt").read_bytes()
        expected_request = retained["request"]
        if (prompt != expected_request["prompt"].encode("utf-8")
                or request.get("prompt_hash") != digest(expected_request["prompt"])
                or any(request.get(name) != expected_request.get(name)
                       for name in ("purpose", "response_schema", "system_prompt"))
                or request.get("profile") != plan["profile"]
                or request.get("source_hash") != plan["bindings"]["source"]
                or request.get("implementation") != plan["bindings"]["implementation"]
                or request.get("timeout_seconds") != plan["recovery"]["deadline_seconds"]
                or process.get("deadline_seconds") != request["timeout_seconds"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native runtime request differs from allocated request")
        if checked != receipt or process.get("group_quiescent") is not True or process.get("remaining_group_members") != []:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Native result has no quiescent process proof")
        if "inventory_document_recovery" in plan and result["status"] == "incomplete":
            from tools.inventory_recovery_v3.cancellation import (
                evidence,
                require_resume,
            )
            from tools.inventory_recovery_v3.stage_owner import StageOwner

            cancellation = evidence(plan, output, entry, index, retained)
            if cancellation is not None:
                if not isinstance(owner, StageOwner) or owner.output != output or owner.plan != plan:
                    raise RecoveryStop("BLOCKED_OWNERSHIP", "Cancellation requires its admitted native owner")
                authorizations = require_resume(owner, cancellation)
                return {"invocation": entry["invocation_id"], "quiescent": True,
                    "outcome": "cancelled", "receipt_hash": retained["runtime_record"]["hash"],
                    "reported_tokens": None, "canary_valid": False,
                    "cancellation_identity": cancellation["identity"], "resume_authorizations": authorizations}
        usage = None
        if receipt.get("input_tokens") is not None and receipt.get("output_tokens") is not None:
            usage = receipt["input_tokens"] + receipt["output_tokens"]
        canary_valid = selected_role == "canary" and result["status"] == "complete" and json.loads(retained["response_text"]) == []
        if owner_check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Native owner changed before pair settlement")
        stop_check()
        return {"invocation": entry["invocation_id"], "quiescent": True,
                "outcome": result["status"], "receipt_hash": retained["runtime_record"]["hash"],
                "reported_tokens": usage, "canary_valid": canary_valid}

    return journal.settle(identity, role, receipt={}, verify=verify)
