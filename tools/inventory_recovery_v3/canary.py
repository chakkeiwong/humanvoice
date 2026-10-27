"""Validate freshness and exact single-use scope of a retained canary."""

import math
from copy import deepcopy

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3.failures import RecoveryStop


def require_validation(record, expected, *, now):
    if (not isinstance(record, dict)
            or record.get("version") != "single-use-canary-validation-v1"
            or record.get("identity") != digest({key: value for key, value in record.items()
                                                 if key != "identity"})
            or record.get("authorizes_inference") is not False
            or any(record.get(name) != value for name, value in expected.items())
            or any(not isinstance(record.get(name), str) or not record[name] for name in
                   ("incident", "request_hash", "lineage", "profile_hash", "route_hash",
                    "source_hash", "policy_identity", "reservation_identity", "receipt_hash"))):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Retry lost its validated native canary binding")
    completed, expires = record.get("completed_at"), record.get("expires_at")
    if (any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
            for value in (now, completed, expires))
            or not completed <= now <= expires or not 0 < expires - completed <= 900):
        raise RecoveryStop("BLOCKED_EXTERNAL", "Canary expired or its validation clock is invalid")
    return deepcopy(record)


def validate_canary(proof, expected, *, now, maximum_age, verify):
    if (type(now) not in (int, float) or not math.isfinite(now)
            or type(maximum_age) is not int or not 0 < maximum_age <= 900):
        raise ValueError("Canary requires a finite clock and bounded freshness")
    checked = verify(deepcopy(proof))
    fields = ("incident", "request_hash", "lineage", "profile_hash",
              "route_hash", "source_hash", "policy_identity", "reservation_identity")
    if (not isinstance(checked, dict) or not isinstance(expected, dict)
            or any(not isinstance(expected.get(name), str) or not expected[name]
                   or checked.get(name) != expected[name] for name in fields)
            or checked.get("settled") is not True or checked.get("quiescent") is not True
            or checked.get("canary_valid") is not True
            or checked.get("later_failure") is not False
            or checked.get("retry_allocated") is not False
            or not isinstance(checked.get("receipt_hash"), str) or not checked["receipt_hash"]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Canary lost its exact unused recovery scope")
    failed, waited, completed = (checked.get(name) for name in
                                 ("failed_at", "wait_observed_at", "completed_at"))
    if (any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
            for value in (failed, waited, completed))
            or not failed + 900 <= waited <= completed <= now):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Canary clock or receipt-bound wait is invalid")
    if now - completed > maximum_age:
        raise RecoveryStop("BLOCKED_EXTERNAL", "Canary expired; reserve a fresh diagnostic sequence")
    original = checked.get("original_policy_identity", checked["policy_identity"])
    if original != checked["policy_identity"] and checked.get("migration_admitted") is not True:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Cross-version canary requires admitted adoption")
    value = {"version": "single-use-canary-validation-v1",
             **{name: checked[name] for name in fields}, "receipt_hash": checked["receipt_hash"],
             "completed_at": completed, "expires_at": completed + maximum_age,
             "authorizes_inference": False}
    return {**value, "identity": digest(value)}
