"""Exercise the new reproduction guard through native multi-unit repair."""

from contextlib import contextmanager
from pathlib import Path

import pytest
import test_codex_runtime

from test_settled_semantic_batch_repair import additional_rejection, settled_reviews
from humanvoice.artifacts import read_json
from tools import reproduction_semantic_recovery as recovery
from tools import settled_semantic_batch_repair as batch
from tools.inventory_transport_continuation import tree_hashes

pytest_plugins = ("test_semantic_repair_protocol",)
codex = test_codex_runtime.codex


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("rejected", [True], indirect=True)
def test_native_reproduction_guard_preserves_accepted_results(settled_reviews, monkeypatch):
    fixture = settled_reviews
    predecessor = fixture.completed_reviews
    original = tree_hashes(Path(read_json(predecessor / "plan.json")["snapshot"]))
    output = predecessor.parent / "reproduction-guard"
    plan = batch.prepare(output, predecessor, fixture.grant, account=fixture.account)
    scope = plan["semantic_batch"]["evidence"]["scope"]
    activity = []

    @contextmanager
    def guarded(snapshot, review_scope):
        proof = {"scope": review_scope, "completed": [
            {"request_hash": identity} for identity in review_scope["completed_critic_requests"]]}
        with recovery.guarded_repairs(snapshot, proof) as (observed, boundary):
            yield observed
        activity.append(observed)

    monkeypatch.setattr(batch.protocol, "guarded_requests", guarded)
    with recovery.fail_fast_writers():
        assert batch.execute(output, fixture.grant, account=fixture.account)["status"] == "pass"
    assert batch.verify_completed(output, account=fixture.account)["new_calls"] == 5
    assert activity[0]["writers"] == activity[0]["critics"] == set(scope["rejected"])
    assert len(activity[0]["requests"]) == 5
    assert tree_hashes(Path(read_json(predecessor / "plan.json")["snapshot"])) == original
