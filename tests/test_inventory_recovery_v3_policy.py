"""Exercise prospective capacity, typed failures and paired reservations offline."""

import json

import pytest

from humanvoice.artifacts import digest
from tools.inventory_context import InvocationStopped, PromptModel
from tools.inventory_recovery_v2.execution import RecoveryBlocked
from tools.inventory_recovery_v3.canary import validate_canary
from tools.inventory_recovery_v3.failures import (
    RecoveryStop,
    failure_record,
    terminal_decision,
    validate_failure,
)
from tools.inventory_recovery_v3.policy import (
    proposal,
    require_capacity,
    validate_policy,
)
from tools.inventory_recovery_v3.reservations import RecoveryReservations


def policy(**changes):
    return proposal(**{"remaining_requests": 439, "inherited_recovery": 17,
                       "incident_allowance": 32, "split_allowance": 32,
                       "qualification_calls": 0, "available_calls": 1000,
                       "available_tokens": 544000000, **changes})


def reservations(tmp_path, **changes):
    journal = RecoveryReservations(tmp_path, policy(**changes), {
        "document": "source", "migration": "sealed-parent", "authority": "existing-grant"})
    journal.initialize()
    return journal


def reserve(journal, **changes):
    arguments = {"lineage": "first", "incident": "timeout",
                 "request_hash": "request", "profile_hash": "qualified-profile", **changes}
    root = journal.register_root(purpose="concept_extraction", owned=[arguments["lineage"]])
    arguments["lineage"] = root["identity"]
    return journal.reserve(**arguments)


def dispatch(journal, sequence, role):
    return journal.dispatch(sequence["identity"], role, sequence["identity"] + role,
                            owner_check=lambda: True, stop_check=lambda: None,
                            canary_check=canary_check, clock=lambda: 2000)


def canary_check(sequence, record):
    binding = {name: sequence[name] for name in
               ("incident", "request_hash", "lineage", "profile_hash")}
    binding.update(route_hash="route", source_hash="source",
                   policy_identity=record["policy"]["identity"],
                   reservation_identity=sequence["identity"])
    proof = {**binding, "settled": True, "quiescent": True, "canary_valid": True,
             "later_failure": False, "retry_allocated": False,
             "receipt_hash": sequence["slots"]["canary"]["proof"]["receipt_hash"],
             "failed_at": 1000, "wait_observed_at": 1900, "completed_at": 1950}
    return validate_canary(proof, binding, now=2000, maximum_age=900,
                           verify=lambda retained: retained)


def settle(journal, sequence, role, **changes):
    proof = {"invocation": sequence["identity"] + role, "quiescent": True,
             "outcome": "complete", "receipt_hash": sequence["identity"] + role,
             "reported_tokens": 12, "canary_valid": True, **changes}
    return journal.settle(sequence["identity"], role, receipt=proof,
                          verify=lambda receipt, binding, kind: receipt)


def test_policy_counts_all_capacity_without_renewal():
    record = policy()
    assert record["planned_calls"] == 535
    assert record["recovery_ceiling"] == 113
    assert record["maximum_generations"] == 65
    assert record["required_tokens"] == 535 * 544000
    assert record["live_execution_enabled"] is False
    assert validate_policy(record) == record


@pytest.mark.parametrize("field,value", [("remaining_requests", True),
    ("incident_allowance", -1), ("available_tokens", 1.2), ("lineage_sequences", 4),
    ("model_count", 4), ("split_allowance", "16")])
def test_invalid_policy_values_rejected(field, value):
    with pytest.raises(ValueError):
        policy(**{field: value})


@pytest.mark.parametrize("changes", [{"available_calls": 534}, {"available_tokens": 1}])
def test_authority_shortage_is_explicit(changes):
    with pytest.raises(RecoveryStop) as caught:
        require_capacity(policy(**changes))
    assert caught.value.category == "BLOCKED_BUDGET"


def test_rehashed_derived_policy_mutation_rejected():
    record = policy()
    record["maximum_generations"] += 1
    record["identity"] = digest({key: value for key, value in record.items() if key != "identity"})
    with pytest.raises(ValueError):
        validate_policy(record)


@pytest.mark.parametrize("category", ["BLOCKED_BUDGET", "BLOCKED_ACCOUNTING",
    "BLOCKED_OWNERSHIP", "USER_STOPPED", "BLOCKED_EXTERNAL", "BLOCKED_AUTHENTICATION"])
def test_actual_invocation_wrapper_preserves_typed_cause(category):
    class BrokenModel:
        def invoke(self, **keywords):
            raise RecoveryBlocked(category, "bound cause")

    with pytest.raises(InvocationStopped) as caught:
        PromptModel(BrokenModel(), "suffix").invoke(prompt="source")
    record = failure_record(caught.value, phase="request")
    terminal = json.loads(json.dumps({"status": "nonpass", "failure": record}))
    assert terminal_decision(terminal)["status"] == category
    assert record["retry_authorized"] is False


def test_phase_and_error_text_do_not_create_a_category():
    record = failure_record(RuntimeError("BLOCKED_BUDGET"), phase="request")
    assert record["category"] == "BLOCKED_ENGINEERING"


def test_semantic_category_requires_validator_evidence():
    error = RecoveryStop("BLOCKED_SEMANTIC", "rejected")
    assert failure_record(error, phase="validation")["category"] == "BLOCKED_ENGINEERING"
    record = failure_record(error, phase="validation", evidence={"validator_receipt": "bound"})
    assert validate_failure(record)["category"] == "BLOCKED_SEMANTIC"


def test_user_stop_takes_priority_and_cycles_terminate():
    error = RecoveryStop("BLOCKED_BUDGET", "budget")
    stopped = RecoveryStop("USER_STOPPED", "stop")
    error.__cause__, stopped.__context__ = stopped, error
    assert failure_record(error, phase="request")["category"] == "USER_STOPPED"


def test_complete_sequence_reserved_before_canary(tmp_path):
    journal = reservations(tmp_path, incident_allowance=1)
    sequence = reserve(journal)
    assert journal.status()["calls_reserved"] == 2
    assert journal.status()["tokens_reserved"] == 1088000
    assert reserve(journal) == sequence
    with pytest.raises(RecoveryStop, match="complete canary"):
        reserve(journal, lineage="second", incident="second")


def test_cannot_dispatch_retry_before_canary(tmp_path):
    journal = reservations(tmp_path)
    sequence = reserve(journal)
    with pytest.raises(RecoveryStop, match="completed canary"):
        dispatch(journal, sequence, "retry")


@pytest.mark.parametrize("role", ["canary", "retry"])
def test_restart_requires_receipt_not_repeat_purchase(tmp_path, role):
    journal = reservations(tmp_path)
    sequence = reserve(journal)
    dispatch(journal, sequence, "canary")
    if role == "retry":
        settle(journal, sequence, "canary")
        dispatch(journal, sequence, role)
    restarted = RecoveryReservations(tmp_path, journal.policy, journal.binding)
    assert restarted.initialize() == journal.read()
    with pytest.raises(RecoveryStop, match="never purchase twice"):
        dispatch(restarted, sequence, role)
    with pytest.raises(RecoveryStop, match="Unresolved dispatch"):
        reserve(restarted, lineage="second", incident="next")
    assert settle(restarted, sequence, role)["state"] == "complete"
    assert settle(restarted, sequence, role)["state"] == "complete"


def test_lost_journal_cannot_reset_usage(tmp_path):
    journal = reservations(tmp_path)
    reserve(journal)
    journal.path.unlink()
    with pytest.raises(RecoveryStop, match="disappeared"):
        journal.initialize()


def test_lineage_and_profile_prevent_retry_renewal(tmp_path):
    journal = reservations(tmp_path)
    reserve(journal)
    with pytest.raises(RecoveryStop, match="split or fallback"):
        reserve(journal, incident="later-timeout")


def test_changed_incident_binding_rejected(tmp_path):
    journal = reservations(tmp_path)
    reserve(journal)
    with pytest.raises(RecoveryStop, match="another recovery"):
        reserve(journal, request_hash="different")


@pytest.mark.parametrize("changes", [{"quiescent": False}, {"canary_valid": False},
    {"invocation": "other"}, {"reported_tokens": None}, {"reported_tokens": 544001}])
def test_invalid_receipt_retains_reservation(tmp_path, changes):
    journal = reservations(tmp_path)
    sequence = reserve(journal)
    dispatch(journal, sequence, "canary")
    with pytest.raises(RecoveryStop):
        settle(journal, sequence, "canary", **changes)
    assert journal.status()["unresolved_dispatches"] == 1


def test_unknown_usage_stays_reserved_and_failed_canary_blocks_retry(tmp_path):
    journal = reservations(tmp_path)
    sequence = reserve(journal)
    dispatch(journal, sequence, "canary")
    settle(journal, sequence, "canary", outcome="incomplete", reported_tokens=None)
    assert journal.status()["tokens_reserved"] == 1088000
    with pytest.raises(RecoveryStop, match="completed canary"):
        dispatch(journal, sequence, "retry")


def test_more_than_sixteen_independent_incidents(tmp_path):
    journal = reservations(tmp_path)
    for index in range(32):
        sequence = reserve(journal, lineage=f"lineage-{index}", incident=f"incident-{index}")
        for role in ("canary", "retry"):
            dispatch(journal, sequence, role)
            settle(journal, sequence, role)
        journal = RecoveryReservations(tmp_path, journal.policy, journal.binding)
    assert journal.status()["completed"] == 64
    assert journal.status()["sequences_available"] == 0


def test_user_stop_and_ownership_checked_before_dispatch(tmp_path):
    journal = reservations(tmp_path)
    sequence = reserve(journal)
    with pytest.raises(RecoveryStop, match="exclusive"):
        journal.dispatch(sequence["identity"], "canary", "native",
                         owner_check=lambda: False, stop_check=lambda: None)

    def stopped():
        raise RecoveryStop("USER_STOPPED", "explicit stop")

    with pytest.raises(RecoveryStop, match="explicit stop"):
        journal.dispatch(sequence["identity"], "canary", "native",
                         owner_check=lambda: True, stop_check=stopped)
    assert journal.status()["unresolved_dispatches"] == 0
