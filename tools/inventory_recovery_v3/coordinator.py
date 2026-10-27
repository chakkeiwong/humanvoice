"""Choose bounded recovery actions from independently validated evidence."""

import math
from copy import deepcopy

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3.failures import CATEGORIES
from tools.inventory_recovery_v3.policy import integer, validate_policy


def decide(policy, observation, *, now):
    validate_policy(policy)
    if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
        raise ValueError("Decision requires a finite observation time")
    if not isinstance(observation, dict):
        raise TypeError("Decision requires bound observation evidence")
    observation = deepcopy(observation)
    if observation.get("identity") != digest({key: value for key, value in observation.items()
                                              if key != "identity"}):
        raise ValueError("Recovery observation identity changed")

    def action(status, next_action, **details):
        result = {"status": status, "next_action": next_action,
                  "observation_identity": observation["identity"],
                  "policy_identity": policy["identity"], "observed_at": now,
                  "authorizes_inference": False, **details}
        return {**result, "identity": digest(result)}

    if observation.get("user_stopped") is True:
        return action("USER_STOPPED", "await_explicit_resume")
    if observation.get("exclusive_owner") is not True:
        return action("BLOCKED_OWNERSHIP", "observe_owned_process")
    if observation.get("unresolved_allocation") is not False:
        return action("BLOCKED_ACCOUNTING", "reconcile_before_spending")
    category = observation.get("category")
    if category not in CATEGORIES:
        return action("BLOCKED_ENGINEERING", "inspect_unclassified_evidence")
    if category not in {"BLOCKED_EXTERNAL", "BLOCKED_DECOMPOSITION"}:
        return action(category, "retain_terminal_failure")
    if observation.get("failure_verified") is not True:
        return action("BLOCKED_ENGINEERING", "verify_native_failure")
    if observation.get("process_quiescent") is not True:
        return action("BLOCKED_OWNERSHIP", "reconcile_process_group")
    if observation.get("failure_kind") not in {"response_free_timeout", "transient_provider", "output_limit"}:
        return action("BLOCKED_ENGINEERING", "inspect_partial_or_unclassified_failure")
    generation = integer(observation.get("generation"), "generation")
    if generation >= policy["maximum_generations"]:
        return action("BLOCKED_BUDGET", "generation_limit_reached")
    attempts = integer(observation.get("exact_retries"), "exact_retries")
    split_depth = integer(observation.get("split_depth"), "split_depth")
    lineage_children = integer(observation.get("lineage_children"), "lineage_children")
    next_children = integer(observation.get("next_children"), "next_children")
    profile_index = integer(observation.get("profile_index"), "profile_index")
    if profile_index >= policy["model_count"]:
        raise ValueError("Profile index left the ordered model policy")
    failed_at = observation.get("failed_at")
    if type(failed_at) not in (int, float) or not math.isfinite(failed_at) or failed_at < 0 or failed_at > now:
        return action("BLOCKED_ACCOUNTING", "reconcile_receipt_clock")
    due = failed_at + policy["backoff_seconds"]
    if observation.get("canary_failed") is True or attempts > 0 or observation["failure_kind"] == "output_limit":
        if observation.get("canary_failed") is True:
            canary_failed_at = observation.get("canary_failed_at")
            if (type(canary_failed_at) not in (int, float) or not math.isfinite(canary_failed_at)
                    or not failed_at <= canary_failed_at <= now):
                return action("BLOCKED_ACCOUNTING", "reconcile_canary_failure_clock")
            due = canary_failed_at + policy["backoff_seconds"]
        if generation + 1 >= policy["maximum_generations"]:
            return action("BLOCKED_BUDGET", "generation_limit_reached")
        if (observation.get("canary_failed") is not True
                and observation.get("split_legal") is True
                and observation.get("split_capacity_reserved") is True
                and split_depth < policy["maximum_split_depth"]
                and 2 <= next_children
                and lineage_children + next_children <= policy["maximum_lineage_children"]):
            return action("REPAIR_READY", "prepare_verified_split", eligible_after=due)
        if profile_index + 1 < policy["model_count"]:
            if policy["incident_allowance"] == 0 or observation.get("fallback_capacity_reserved") is not True:
                return action("BLOCKED_BUDGET", "reserve_fallback_transition")
            if observation.get("next_profile_qualified") is True:
                return action("REPAIR_READY", "prepare_qualified_fallback",
                              next_profile_index=profile_index + 1, eligible_after=due)
            return action("BLOCKED_BUDGET" if observation.get("qualification_capacity") is not True
                          else "QUALIFICATION_REQUIRED", "reserve_and_qualify_next_profile",
                          next_profile_index=profile_index + 1, eligible_after=due)
        return action("BLOCKED_EXTERNAL", "ordered_profiles_exhausted")
    if observation.get("sequence_reserved") is not True:
        return action("RESERVATION_REQUIRED", "reserve_canary_and_retry")
    if now < due:
        return action("RETRY_WAIT", "receipt_bound_backoff", eligible_after=due)
    if observation.get("canary_valid") is True:
        return action("RETRY_READY", "retry_exact_bound_request", eligible_after=due)
    return action("CANARY_READY", "run_bound_canary", eligible_after=due)
