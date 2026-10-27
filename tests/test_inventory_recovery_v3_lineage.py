"""Keep split ancestry and root budgets stable across durable restarts."""

from copy import deepcopy

import pytest
from test_inventory_recovery_v3_policy import dispatch, reservations, settle

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.lineage import (
    root_lineage,
    split_lineage,
    validate_lineage,
)
from tools.inventory_recovery_v3.reservations import RecoveryReservations


@pytest.mark.parametrize("field,value", [("root", "other"), ("depth", 0),
    ("source_hash", "other"), ("parent", "missing"), ("owned", ["outside"])])
@pytest.mark.parametrize("rehash", [False, True])
def test_child_cannot_change_root_or_registered_parent(field, value, rehash):
    root = root_lineage("source", "concept_extraction", ["first", "second"])
    child = split_lineage(root, [["first"], ["second"]])[0]
    child[field] = value
    if rehash:
        child["identity"] = digest({key: item for key, item in child.items() if key != "identity"})
    with pytest.raises(ValueError):
        validate_lineage(child, ancestors={root["identity"]: root})


def test_more_than_sixteen_independent_splits_survive_restarts(tmp_path):
    journal = reservations(tmp_path)
    for index in range(32):
        root = journal.register_root(purpose="concept_extraction", owned=[f"{index}-a", f"{index}-b"])
        children = journal.split(root["identity"], [[f"{index}-a"], [f"{index}-b"]])
        assert journal.split(root["identity"], [[f"{index}-a"], [f"{index}-b"]]) == children
        journal = RecoveryReservations(tmp_path, journal.policy, journal.binding)
        for child in children:
            validate_lineage(child, ancestors=journal.read()["lineages"])
    record = journal.read()
    assert len(record["splits"]) == 32
    assert sum(row["extra_calls"] for row in record["splits"].values()) == 32
    root = journal.register_root(purpose="concept_extraction", owned=["last-a", "last-b"])
    with pytest.raises(RecoveryStop, match="expansion"):
        journal.split(root["identity"], [["last-a"], ["last-b"]])


def test_split_children_cannot_reset_root_incident_limit(tmp_path):
    journal = reservations(tmp_path)
    root = journal.register_root(purpose="concept_extraction", owned=["first", "second", "third", "fourth"])
    first, second = journal.split(root["identity"], [["first", "second"], ["third", "fourth"]])
    children = journal.split(first["identity"], [["first"], ["second"]])
    children += journal.split(second["identity"], [["third"], ["fourth"]])
    for index, child in enumerate(children[:3]):
        sequence = journal.reserve(lineage=child["identity"], incident=f"incident-{index}",
                                   request_hash=f"request-{index}", profile_hash="profile")
        for role in ("canary", "retry"):
            dispatch(journal, sequence, role)
            settle(journal, sequence, role)
    before = journal.path.read_bytes()
    with pytest.raises(RecoveryStop, match="split or fallback"):
        journal.reserve(lineage=children[3]["identity"], incident="fourth",
                        request_hash="fourth", profile_hash="profile")
    assert journal.path.read_bytes() == before


def test_root_requires_unique_source_membership_and_exact_split(tmp_path):
    journal = reservations(tmp_path)
    root = journal.register_root(purpose="concept_extraction", owned=["first", "second", "third"])
    with pytest.raises(RecoveryStop, match="overlap"):
        journal.register_root(purpose="concept_extraction", owned=["second"])
    children = journal.split(root["identity"], [["first"], ["second", "third"]])
    with pytest.raises(RecoveryStop, match="cannot change"):
        journal.split(root["identity"], [["first", "second"], ["third"]])
    with pytest.raises(RecoveryStop, match="Split parent"):
        journal.reserve(lineage=root["identity"], incident="incident", request_hash="request", profile_hash="profile")
    with pytest.raises(ValueError, match="registered ancestry"):
        split_lineage(deepcopy(children[1]), [["second"], ["third"]])


@pytest.mark.parametrize("role", ["canary", "retry"])
def test_split_retires_previously_reserved_parent_dispatch(tmp_path, role):
    journal = reservations(tmp_path)
    root = journal.register_root(purpose="concept_extraction", owned=["first", "second"])
    sequence = journal.reserve(lineage=root["identity"], incident="parent",
                               request_hash="request", profile_hash="profile")
    if role == "retry":
        dispatch(journal, sequence, "canary")
        settle(journal, sequence, "canary")
    children = journal.split(root["identity"], [["first"], ["second"]])
    restarted = RecoveryReservations(tmp_path, journal.policy, journal.binding)
    before = restarted.path.read_bytes()
    with pytest.raises(RecoveryStop, match="Split parent cannot dispatch"):
        dispatch(restarted, sequence, role)
    assert restarted.path.read_bytes() == before
    child = restarted.reserve(lineage=children[0]["identity"], incident="child",
                              request_hash="child-request", profile_hash="profile")
    dispatch(restarted, child, "canary")


def test_thousand_registered_roots_keep_sparse_split_state(tmp_path):
    journal = reservations(tmp_path, remaining_requests=1000, available_calls=1200, available_tokens=652800000)
    roots = []
    for index in range(1000):
        root = journal.register_root(purpose="concept_extraction", owned=[f"{index}-a", f"{index}-b"])
        roots.append(root)
        if index < 32:
            journal.split(root["identity"], [[f"{index}-a"], [f"{index}-b"]])
        if index % 200 == 199:
            journal = RecoveryReservations(tmp_path, journal.policy, journal.binding)
    record = journal.read()
    assert len(record["lineages"]) == 1064
    assert len(record["splits"]) == 32
    assert len({root["identity"] for root in roots}) == 1000
    assert journal.status()["calls_reserved"] == 0
    assert journal.path.stat().st_size < 1000000
