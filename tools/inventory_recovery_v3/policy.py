"""Calculate bounded capacity without renewing existing call or token authority."""

from copy import deepcopy

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3.failures import RecoveryStop

VERSION = "inventory-document-recovery-v3"
TOKEN_RESERVATION = 544000


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer at least {minimum}")
    return value


def proposal(*, remaining_requests, inherited_recovery, incident_allowance,
             split_allowance, qualification_calls, available_calls, available_tokens,
             lineage_sequences=3, model_count=3, root_sequences=3):
    values = locals().copy()
    for name, value in values.items():
        integer(value, name, 1 if name in {"lineage_sequences", "model_count", "root_sequences"} else 0)
    if model_count != 3 or lineage_sequences > model_count:
        raise ValueError("Lineage policy exceeds the three ordered qualified profiles")
    if not lineage_sequences <= root_sequences <= 12:
        raise ValueError("Shared root recovery ceiling must be between the lineage ceiling and twelve")
    diagnostic_calls = incident_allowance
    retry_calls = incident_allowance
    extra_calls = diagnostic_calls + retry_calls + split_allowance + qualification_calls
    planned_calls = remaining_requests + extra_calls
    required_tokens = planned_calls * TOKEN_RESERVATION
    value = {"version": VERSION, **values,
             "diagnostic_calls": diagnostic_calls, "retry_calls": retry_calls,
             "extra_calls": extra_calls, "planned_calls": planned_calls,
             "token_reservation_per_call": TOKEN_RESERVATION,
             "required_tokens": required_tokens,
             "recovery_ceiling": inherited_recovery + extra_calls,
             "maximum_generations": 1 + incident_allowance + split_allowance,
             "maximum_split_depth": 3, "maximum_lineage_children": 14,
             "backoff_seconds": 900, "invocation_seconds": 900,
             "authority_sufficient": (planned_calls <= available_calls
                                      and required_tokens <= available_tokens),
             "live_execution_enabled": False}
    return {**value, "identity": digest(value)}


def validate_policy(record):
    parameters = ("remaining_requests", "inherited_recovery", "incident_allowance",
                  "split_allowance", "qualification_calls", "available_calls",
                  "available_tokens", "lineage_sequences", "model_count", "root_sequences")
    if proposal(**{name: record[name] for name in parameters}) != record:
        raise ValueError("Document recovery policy changed")
    return deepcopy(record)


def require_capacity(record):
    validate_policy(record)
    if not record["authority_sufficient"]:
        raise RecoveryStop("BLOCKED_BUDGET", "Document recovery envelope exceeds authority",
                           evidence={name: record[name] for name in ("planned_calls",
                               "available_calls", "required_tokens", "available_tokens")})
    return record
