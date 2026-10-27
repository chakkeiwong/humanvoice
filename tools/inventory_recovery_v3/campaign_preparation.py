"""Verify persisted native preparation before campaign history publication."""

import json
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3 import accounting, ancestry, runtime
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import regular_path

FILES = ("plan.json", "transition.json", "admission-probe.json", "preparation-intent.json",
         "prepared-authority.json", "prepared-snapshot.json", "execution.json")


def evidence(intent):
    from tools.inventory_recovery_v3.stage import bridge

    output = Path(intent["output"])
    contract = runtime.contract()
    folder = Path("probe") / digest(contract)[:16]
    names = (*FILES, *(str(folder / name) for name in
                      ("observations.json", "replay-log.json", "probe-intent.json", "verification.json")))
    files = {name: regular_path(output / name).read_bytes() for name in names}
    snapshot = bridge.original.lifecycle.retained.tree_hashes(output / "snapshot")
    return files, snapshot, contract


def descriptor(intent, captured):
    files, snapshot, contract = captured
    plan = json.loads(files["plan.json"])
    return {"plan_identity": plan["plan_identity"], "plan_sha256": digest(files["plan.json"]),
            "probe_sha256": digest(files["admission-probe.json"]),
            "validation_identity": digest({"intent": intent, "files": {name: digest(value)
                for name, value in files.items()}, "snapshot": snapshot, "contract": contract, "model_calls": 0})}


def require_unallocated(output):
    if any(regular_path(output / name).exists() for name in
           ("account-reservation.json", "allocation-ledger.json", "allocation-seal.json", "calls")):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Campaign publication requires unallocated native preparation")


def require_prepared(intent, prepared):
    require_unallocated(Path(intent["output"]))
    if digest(descriptor(intent, evidence(intent))) != digest(prepared):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native preparation changed after independent verification")
    return True


def verify_prepared(intent, check):
    from tools.inventory_history_adoption import no_inference
    from tools.inventory_recovery_v3.stage import bridge

    if check() is not True:
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Native preparation verification requires campaign ownership")
    output = Path(intent["output"])
    paths = {name: regular_path(output / name) for name in FILES}
    before = evidence(intent)
    plan = read_json(paths["plan.json"])
    transition = intent["transition"]
    with no_inference(), accounting.document_scope(transition):
        runtime.validate_plan(plan)
        if (read_json(paths["transition.json"]) != transition
                or plan[runtime.FIELD]["transition"] != transition
                or plan["snapshot"] != str(output / "snapshot")):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Campaign publication requires its exact unallocated native preparation")
        require_unallocated(output)
        ancestry.validate(output, plan)
        expected = {"status": "prepared", "plan_identity": plan["plan_identity"],
                    "model_calls": 0, "required": len(plan["calls"]), "human_evidence": False}
        if (digest(read_json(paths["execution.json"])) != digest(expected)
                or read_json(paths["prepared-snapshot.json"]) != bridge.original.lifecycle.retained.tree_hashes(
                    output / "snapshot")):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native preparation changed its snapshot or prepared marker")
    if check() is not True:
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign ownership changed during native preparation replay")
    require_unallocated(output)
    if evidence(intent) != before:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native preparation changed during read-only verification")
    return descriptor(intent, before)
