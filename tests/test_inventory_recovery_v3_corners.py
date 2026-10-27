"""Exercise decision, freshness, ancestry and native capacity corner cases."""

from copy import deepcopy

import pytest
from test_inventory_recovery_v3_policy import policy

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3.canary import validate_canary
from tools.inventory_recovery_v3.coordinator import decide
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.lineage import root_lineage, split_lineage
from tools.inventory_recovery_v3.progress import watch_config
from tools.inventory_recovery_v3.stage_capacity import pair_capacity


def observation(**changes):
    value = {"user_stopped": False, "exclusive_owner": True, "unresolved_allocation": False,
             "category": "BLOCKED_EXTERNAL", "failure_verified": True,
             "process_quiescent": True, "failure_kind": "response_free_timeout",
             "exact_retries": 0, "split_depth": 0, "lineage_children": 0,
             "next_children": 2, "profile_index": 1, "failed_at": 1000,
             "sequence_reserved": True, "canary_valid": False,
             "fallback_capacity_reserved": True, "generation": 0, "canary_failed_at": 1000, **changes}
    return {**value, "identity": digest(value)}


@pytest.mark.parametrize("changes,status,action", [
    ({"user_stopped": True}, "USER_STOPPED", "await_explicit_resume"),
    ({"exclusive_owner": False}, "BLOCKED_OWNERSHIP", "observe_owned_process"),
    ({"unresolved_allocation": True}, "BLOCKED_ACCOUNTING", "reconcile_before_spending"),
    ({"category": "BLOCKED_BUDGET"}, "BLOCKED_BUDGET", "retain_terminal_failure"),
    ({"category": "BLOCKED_SEMANTIC"}, "BLOCKED_SEMANTIC", "retain_terminal_failure"),
    ({"category": "BLOCKED_AUTHENTICATION"}, "BLOCKED_AUTHENTICATION", "retain_terminal_failure"),
    ({"failure_kind": "partial_response"}, "BLOCKED_ENGINEERING", "inspect_partial_or_unclassified_failure"),
    ({"failure_verified": False}, "BLOCKED_ENGINEERING", "verify_native_failure"),
    ({"process_quiescent": False}, "BLOCKED_OWNERSHIP", "reconcile_process_group"),
    ({"sequence_reserved": False}, "RESERVATION_REQUIRED", "reserve_canary_and_retry"),
    ({}, "CANARY_READY", "run_bound_canary"),
    ({"canary_valid": True}, "RETRY_READY", "retry_exact_bound_request"),
    ({"exact_retries": 1, "split_legal": True, "split_capacity_reserved": True},
     "REPAIR_READY", "prepare_verified_split"),
    ({"exact_retries": 1, "next_profile_qualified": True}, "REPAIR_READY", "prepare_qualified_fallback"),
    ({"exact_retries": 1}, "BLOCKED_BUDGET", "reserve_and_qualify_next_profile"),
    ({"exact_retries": 1, "qualification_capacity": True}, "QUALIFICATION_REQUIRED", "reserve_and_qualify_next_profile"),
    ({"exact_retries": 1, "profile_index": 2}, "BLOCKED_EXTERNAL", "ordered_profiles_exhausted"),
    ({"canary_failed": True, "split_legal": True, "split_capacity_reserved": True,
      "next_profile_qualified": True}, "REPAIR_READY", "prepare_qualified_fallback"),
])
def test_recovery_decisions(changes, status, action):
    result = decide(policy(), observation(**changes), now=1900)
    assert result["status"] == status
    assert result["next_action"] == action
    assert result["authorizes_inference"] is False


def test_wait_uses_receipt_not_process_restart_time():
    record = observation()
    assert decide(policy(), record, now=1899)["status"] == "RETRY_WAIT"
    assert decide(policy(), record, now=1900)["status"] == "CANARY_READY"


@pytest.mark.parametrize("clock", [float("inf"), float("nan"), -1, True])
def test_invalid_decision_clocks(clock):
    with pytest.raises(ValueError):
        decide(policy(), observation(), now=clock)


@pytest.mark.parametrize("changes", [{"split_depth": 3}, {"lineage_children": 13}])
def test_root_guards_do_not_scale_with_document(changes):
    record = observation(exact_retries=1, split_legal=True, split_capacity_reserved=True, **changes)
    assert decide(policy(), record, now=1900)["next_action"] != "prepare_verified_split"


def canary():
    binding = {name: name for name in ("incident", "request_hash", "lineage", "profile_hash",
               "route_hash", "source_hash", "policy_identity", "reservation_identity")}
    proof = {**binding, "settled": True, "quiescent": True, "canary_valid": True,
             "later_failure": False, "retry_allocated": False, "receipt_hash": "receipt",
             "failed_at": 1000, "wait_observed_at": 1900, "completed_at": 1950}
    return binding, proof


def test_canary_freshness_and_no_implicit_live_authority():
    binding, proof = canary()
    checked = validate_canary(proof, binding, now=2000, maximum_age=900, verify=deepcopy)
    assert checked["expires_at"] == 2850
    assert checked["authorizes_inference"] is False
    with pytest.raises(RecoveryStop, match="expired"):
        validate_canary(proof, binding, now=2851, maximum_age=900, verify=deepcopy)


@pytest.mark.parametrize("field,value", [("lineage", "other"), ("route_hash", "other"),
    ("profile_hash", "other"), ("request_hash", "other"), ("retry_allocated", True),
    ("later_failure", True), ("completed_at", 2001), ("failed_at", float("nan")),
    ("wait_observed_at", 1899), ("original_policy_identity", "old")])
def test_reject_unsafe_canary_reuse(field, value):
    binding, proof = canary()
    proof[field] = value
    with pytest.raises(RecoveryStop):
        validate_canary(proof, binding, now=2000, maximum_age=900, verify=deepcopy)


def test_exact_stage_suballocation_with_no_global_free_capacity():
    stage = {"plan_identity": "stage", "native_verified": True,
             "maximum_calls": 10, "allocated_calls": 8, "held_calls": 2,
             "held_tokens": 1088000, "global_available": 0}
    result = pair_capacity(stage, earmarked_calls=0, unfinished_base_calls=0)
    assert result["native_claims"] == result["native_refunds"] == 0
    assert result["pair_tokens"] == 1088000


def test_base_reserved_retry_differs_from_additional_retry():
    stage = {"plan_identity": "stage", "native_verified": True,
             "maximum_calls": 10, "allocated_calls": 8, "held_calls": 2,
             "held_tokens": 1088000}
    assert pair_capacity(stage, earmarked_calls=0, unfinished_base_calls=1, retry_is_base=True)["extra_calls"] == 1
    with pytest.raises(RecoveryStop, match="cannot fit"):
        pair_capacity(stage, earmarked_calls=0, unfinished_base_calls=1)


def test_stage_token_shortage_does_not_refund_unknown_calls():
    stage = {"plan_identity": "stage", "native_verified": True,
             "maximum_calls": 10, "allocated_calls": 8, "held_calls": 2,
             "held_tokens": 1087999}
    with pytest.raises(RecoveryStop):
        pair_capacity(stage, earmarked_calls=0, unfinished_base_calls=0)


def test_source_lineage_survives_split_and_slot_renumbering():
    root = root_lineage("source", "concept_extraction", ["second", "first", "third"])
    assert root == root_lineage("source", "concept_extraction", ["first", "second", "third"])
    children = split_lineage(root, [["first"], ["second", "third"]])
    descendants = split_lineage(children[1], [["second"], ["third"]],
                                ancestors={root["identity"]: root})
    assert all(child["root"] == root["identity"] for child in children + descendants)
    assert descendants[0]["depth"] == 2


@pytest.mark.parametrize("children", [[["first"], ["first"]], [["first"], []],
    [["first"], ["other"]], [["first", "second"]]])
def test_invalid_ownership_split_rejected(children):
    root = root_lineage("source", "concept_extraction", ["first", "second"])
    with pytest.raises(ValueError):
        split_lineage(root, children)


def test_progress_covers_last_generation_without_heartbeat(tmp_path):
    configuration = {"progress_files": [str(tmp_path / "existing.json")]}
    original = deepcopy(configuration)
    record = policy()
    selected = watch_config(configuration, tmp_path, record)
    assert str(tmp_path / "generation-64/allocation-ledger.json") in selected["progress_files"]
    assert str(tmp_path / "generation-65/allocation-ledger.json") not in selected["progress_files"]
    assert not any("heartbeat" in path for path in selected["progress_files"])
    assert watch_config(selected, tmp_path, record) == selected
    assert configuration == original
