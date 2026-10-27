"""Preserve typed recovery stops across invocation and process boundaries."""

from copy import deepcopy

from humanvoice.artifacts import digest

CATEGORIES = frozenset({
    "BLOCKED_BUDGET", "BLOCKED_ACCOUNTING", "BLOCKED_OWNERSHIP",
    "BLOCKED_EXTERNAL", "BLOCKED_DECOMPOSITION", "BLOCKED_ENGINEERING",
    "BLOCKED_SEMANTIC", "BLOCKED_AUTHENTICATION", "BLOCKED_REFUSAL",
    "USER_STOPPED",
})
PRIORITY = {
    "USER_STOPPED": 0, "BLOCKED_OWNERSHIP": 1, "BLOCKED_ACCOUNTING": 2,
    "BLOCKED_AUTHENTICATION": 3, "BLOCKED_REFUSAL": 4, "BLOCKED_BUDGET": 5,
    "BLOCKED_SEMANTIC": 6, "BLOCKED_ENGINEERING": 7,
    "BLOCKED_DECOMPOSITION": 8, "BLOCKED_EXTERNAL": 9,
}


class RecoveryStop(RuntimeError):
    def __init__(self, category, detail, *, evidence=None):
        if category not in CATEGORIES:
            raise ValueError("Unknown recovery stop category")
        self.category = category
        self.evidence = deepcopy(evidence or {})
        super().__init__(detail)


def failure_record(error, *, phase, request_hash=None, evidence=None):
    if not isinstance(error, BaseException) or not isinstance(phase, str) or not phase:
        raise ValueError("Failure requires an exception and originating phase")
    seen, pending, candidates = set(), [error], []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        category = getattr(current, "category", None)
        if category in CATEGORIES:
            candidates.append((PRIORITY[category], current))
        pending.extend(child for child in (current.__cause__, current.__context__)
                       if child is not None)
    selected = min(candidates, key=lambda item: item[0])[1] if candidates else error
    category = getattr(selected, "category", "BLOCKED_ENGINEERING")
    if category not in CATEGORIES:
        category = "BLOCKED_ENGINEERING"
    proof = deepcopy(evidence or {})
    proof["origin"] = deepcopy(getattr(selected, "evidence", {}) or {})
    if category == "BLOCKED_SEMANTIC" and not proof.get("validator_receipt"):
        category = "BLOCKED_ENGINEERING"
    value = {"version": "inventory-typed-failure-v1", "category": category,
             "phase": phase, "request_hash": request_hash,
             "error_type": type(selected).__name__, "detail": str(selected),
             "evidence": proof, "retry_authorized": False}
    return {**value, "identity": digest(value)}


def validate_failure(record):
    if (not isinstance(record, dict)
            or record.get("version") != "inventory-typed-failure-v1"
            or record.get("category") not in CATEGORIES
            or not isinstance(record.get("phase"), str) or not record["phase"]
            or record.get("retry_authorized") is not False
            or record.get("identity") != digest({key: value for key, value in record.items()
                                                  if key != "identity"})
            or record["category"] == "BLOCKED_SEMANTIC"
            and not record.get("evidence", {}).get("validator_receipt")):
        raise ValueError("Failure record lost its typed evidence binding")
    return deepcopy(record)


def terminal_decision(terminal):
    if terminal.get("status") != "nonpass":
        raise ValueError("Failure diagnosis requires a terminal nonpass")
    record = validate_failure(terminal["failure"])
    return {"status": record["category"], "failure_identity": record["identity"],
            "reason": record["detail"], "automatic_repair": False,
            "final_zlb_acceptance": False}
