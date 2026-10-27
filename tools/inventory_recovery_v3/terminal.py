"""Persist a typed terminal before native sealing without changing sealed history."""

from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.failures import (
    RecoveryStop,
    failure_record,
    terminal_decision,
)
from tools.inventory_recovery_v3.reservations import persist, regular_path


def finalize_failure(output, summary, error, *, phase, settle, owner_check, stop_check,
                     request_hash=None, evidence=None):
    output = Path(output)
    path = regular_path(output / "execution.json")
    seal_path = regular_path(output / "allocation-seal.json")
    if owner_check() is not True:
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Terminal commit requires exclusive execution ownership")
    stop_check()
    failure = failure_record(error, phase=phase, request_hash=request_hash, evidence=evidence)
    if failure["category"] == "USER_STOPPED":
        raise RecoveryStop("USER_STOPPED", "User pause cannot become a sealed nonpass") from error
    plan = read_json(output / "plan.json")
    ledger = read_json(output / "allocation-ledger.json")
    if (plan.get("plan_identity") != digest({key: value for key, value in plan.items()
                                            if key != "plan_identity"})
            or summary.get("plan_identity") != plan["plan_identity"]
            or ledger.get("plan_identity") != plan["plan_identity"]
            or any(entry.get("status") not in {"complete", "incomplete"}
                   for entry in ledger["calls"])):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Terminal requires reconciled exact native allocations")
    terminal = {**summary, "status": "nonpass", "failure": failure,
                "required": len(plan["calls"]), "attempted": len(ledger["calls"]),
                "reported_tokens": ledger["reported_tokens"]}
    if path.exists():
        retained = read_json(path)
        if retained.get("status") == "paused_user":
            raise RecoveryStop("USER_STOPPED", "Retained user pause cannot become a sealed nonpass")
        if retained.get("status") in {"pass", "nonpass"} and retained != terminal:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Retained terminal cannot be rewritten")
    if seal_path.exists():
        if not path.exists() or read_json(path) != terminal:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Sealed terminal cannot be reconstructed from guesses")
    elif not path.exists() or read_json(path) != terminal:
        if owner_check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Terminal ownership changed before persistence")
        stop_check()
        persist(path, terminal)
    before = path.read_bytes()
    stop_check()
    settle(output)
    if (path.read_bytes() != before
            or read_json(seal_path).get("terminal_hash") != digest(terminal)):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native settlement changed the typed terminal")
    return {"terminal": terminal, "diagnosis": terminal_decision(terminal)}
