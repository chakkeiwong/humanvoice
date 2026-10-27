"""Enforce reviewed canary and generation boundaries at dispatch time."""

import pytest
from test_inventory_recovery_v3_corners import observation
from test_inventory_recovery_v3_policy import (
    canary_check,
    dispatch,
    policy,
    reservations,
    reserve,
    settle,
)

from tools.inventory_recovery_v3.coordinator import decide
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.progress import watch_config
from tools.inventory_recovery_v3.reservations import RecoveryReservations


def passing_canary(tmp_path):
    journal = reservations(tmp_path)
    sequence = reserve(journal)
    dispatch(journal, sequence, "canary")
    settle(journal, sequence, "canary")
    return journal, sequence


def test_completed_canary_does_not_survive_newer_failure(tmp_path):
    journal, first = passing_canary(tmp_path)
    second = reserve(journal, lineage="other", incident="newer")
    dispatch(journal, second, "canary")
    settle(journal, second, "canary", outcome="incomplete", reported_tokens=None)
    with pytest.raises(RecoveryStop, match="superseded"):
        dispatch(journal, first, "retry")
    assert journal.status()["unresolved_dispatches"] == 0
    assert journal.status()["calls_reserved"] == 4


@pytest.mark.parametrize("clock", [2851, 1949, float("nan"), float("inf"), True])
def test_restart_rechecks_expiry_before_allocating(tmp_path, clock):
    journal, sequence = passing_canary(tmp_path)
    restarted = RecoveryReservations(tmp_path, journal.policy, journal.binding)
    before = restarted.path.read_bytes()
    with pytest.raises(RecoveryStop):
        restarted.dispatch(sequence["identity"], "retry", "next",
                           owner_check=lambda: True, stop_check=lambda: None,
                           canary_check=canary_check, clock=lambda: clock)
    assert restarted.path.read_bytes() == before


def test_fresh_restart_consumes_canary_once_at_boundary(tmp_path):
    journal, sequence = passing_canary(tmp_path)
    restarted = RecoveryReservations(tmp_path, journal.policy, journal.binding)
    arguments = {"owner_check": lambda: True, "stop_check": lambda: None,
                 "canary_check": canary_check, "clock": lambda: 2850}
    slot = restarted.dispatch(sequence["identity"], "retry", "next", **arguments)
    assert slot["canary_validation"]["expires_at"] == 2850
    with pytest.raises(RecoveryStop, match="never purchase twice"):
        restarted.dispatch(sequence["identity"], "retry", "another", **arguments)


@pytest.mark.parametrize("condition", ["stop", "ownership", "expiry"])
def test_validation_does_not_bypass_late_veto(tmp_path, condition):
    journal, sequence = passing_canary(tmp_path)
    validated = []
    clock = [2000]

    def check(selected, record):
        validated.append(True)
        return canary_check(selected, record)

    def owner():
        return not (condition == "ownership" and validated)

    def stop():
        if validated:
            if condition == "stop":
                raise RecoveryStop("USER_STOPPED", "stop during validation")
            if condition == "expiry":
                clock[0] = 2851

    before = journal.path.read_bytes()
    with pytest.raises(RecoveryStop):
        journal.dispatch(sequence["identity"], "retry", "next", owner_check=owner,
                         stop_check=stop, canary_check=check, clock=lambda: clock[0])
    assert journal.path.read_bytes() == before


def test_boolean_canary_approval_is_not_evidence(tmp_path):
    journal, sequence = passing_canary(tmp_path)
    with pytest.raises(RecoveryStop, match="native canary binding"):
        journal.dispatch(sequence["identity"], "retry", "next",
                         owner_check=lambda: True, stop_check=lambda: None,
                         canary_check=lambda *arguments: True, clock=lambda: 2000)


@pytest.mark.parametrize("allowance,generation,ready", [(0, 0, False), (1, 0, True),
                                                        (1, 1, False), (1, 2, False)])
def test_fallback_and_last_watched_generation_agree(tmp_path, allowance, generation, ready):
    selected = policy(incident_allowance=allowance, split_allowance=0)
    result = decide(selected, observation(failure_kind="output_limit",
                    next_profile_qualified=True, generation=generation), now=2000)
    assert (result["next_action"] == "prepare_qualified_fallback") is ready
    if ready:
        paths = watch_config({"progress_files": []}, tmp_path, selected)["progress_files"]
        assert str(tmp_path / f"generation-{generation + 1:02d}/allocation-ledger.json") in paths
    else:
        assert result["status"] == "BLOCKED_BUDGET"


def test_fallback_requires_earmarked_capacity():
    result = decide(policy(), observation(failure_kind="output_limit",
                    next_profile_qualified=True, fallback_capacity_reserved=False), now=2000)
    assert result["status"] == "BLOCKED_BUDGET"


def test_failed_canary_sets_its_own_cooldown():
    result = decide(policy(), observation(canary_failed=True, canary_failed_at=1950,
                                         next_profile_qualified=True), now=2000)
    assert result["eligible_after"] == 2850
