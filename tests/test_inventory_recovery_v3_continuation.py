"""Require exact independently verified evidence at fallback construction."""

from copy import deepcopy

import pytest
from test_qualification_capture import codex, profile_for

from humanvoice.artifacts import digest
from tools import sol_inventory_reconnect_routing as routing
from tools.inventory_recovery_v2 import qualification
from tools.inventory_recovery_v3 import continuation

__all__ = ["codex"]


@pytest.mark.parametrize("mutation", [None, "evaluation_hash", "plan_identity", "purposes", "output", "canary_only"])
def test_fallback_preserves_verified_proof_not_caller_fields(codex, monkeypatch, mutation):
    initial = profile_for(codex, monkeypatch)
    profile = routing.routing.candidate_profile(initial[routing.routing.FIELD]["base_profile"], 1)
    canonical = {"status": "QUALIFICATION_VERIFIED", "profile_hash": digest(profile),
        "purposes": ["concept_extraction", "coverage_verification", "reconstruction_verification"],
        "settled": True, "canary_only": False, "evaluation_hash": "verified-evaluation",
        "plan_identity": "verified-plan", "output": "fixture-qualification"}
    previous = continuation.identified({"profile": initial,
        "parent_failure": {"request": {"purpose": "concept_extraction"}}})
    observed = []

    def verify(output, candidate):
        observed.append((output, candidate))
        assert candidate == profile
        return deepcopy(canonical)

    monkeypatch.setattr(qualification, "verify", verify)
    supplied = deepcopy(canonical)
    if mutation:
        supplied[mutation] = (["concept_extraction"] if mutation == "purposes" else
                              True if mutation == "canary_only" else "changed")
        with pytest.raises(RuntimeError, match="independently verified qualification"):
            continuation.fallback_successor(previous, supplied)
    else:
        result = continuation.fallback_successor(previous, supplied)
        assert result["fallback_qualification"] == canonical
        assert result["profile"] == profile
        supplied["evaluation_hash"] = "changed after construction"
        assert result["fallback_qualification"] == canonical
    assert observed == [(supplied["output"], profile)]
