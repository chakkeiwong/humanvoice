"""Persist shared source scopes and split charges across crash boundaries."""

import multiprocessing
import os

import pytest
from test_inventory_recovery_v3_policy import reservations

from humanvoice.artifacts import read_json
from tools.inventory_recovery_v3 import registration


def root(journal, **changes):
    scope = {"source_file": "main.tex", "window": "window-0000", "purpose": "concept_extraction", **changes}
    owned = [str(scope) + f"/{index}" for index in range(16)]
    return registration.scoped_root(journal, scope=scope, owned=owned)


def test_scope_cannot_renew_with_disjoint_critic_concepts(tmp_path):
    journal = reservations(tmp_path)
    scope = {"source_file": "main.tex", "window": "window-0000", "purpose": "reconstruction_verification"}
    first = registration.scoped_root(journal, scope=scope, owned=["original-a", "original-b"])
    before = journal.path.read_bytes()
    assert registration.scoped_root(journal, scope=scope, owned=["original-b", "original-a"]) == first
    with pytest.raises(RuntimeError, match="root membership"):
        registration.scoped_root(journal, scope=scope, owned=["changed-a", "changed-b"])
    assert journal.path.read_bytes() == before


@pytest.mark.parametrize("remove", ["map", "entry"])
def test_lost_scope_registry_never_renews_root_allowance(tmp_path, remove):
    journal = reservations(tmp_path)
    scope = {"source_file": "main.tex", "window": "window-0000", "purpose": "reconstruction_verification"}
    parent = registration.scoped_root(journal, scope=scope, owned=["original-a", "original-b"])
    registration.register_split(journal, parent["identity"], [["original-a"], ["original-b"]],
        evidence="spent", inherited=False)
    record = read_json(journal.path)
    if remove == "map":
        del record["source_scopes"]
    else:
        record["source_scopes"].clear()
    before = journal.path.read_bytes()
    with pytest.raises(RuntimeError, match="membership disappeared"):
        journal.save(record)
    assert journal.path.read_bytes() == before


def test_combined_inherited_prospective_tree_charges_exactly_once(tmp_path):
    journal = reservations(tmp_path, split_allowance=6)
    original = root(journal)
    children = [original["owned"][:8], original["owned"][8:]]
    current = registration.register_split(journal, original["identity"], children, evidence="old-size", inherited=True)
    for depth in range(2):
        following = []
        for index, parent in enumerate(current):
            half = len(parent["owned"]) // 2
            partitions = [parent["owned"][:half], parent["owned"][half:]]
            evidence = f"new-{depth}-{index}"
            descendants = registration.register_split(journal, parent["identity"], partitions,
                evidence=evidence, inherited=False)
            assert registration.register_split(journal, parent["identity"], partitions,
                evidence=evidence, inherited=False) == descendants
            following.extend(descendants)
        current = following
    record = journal.read()
    assert len(record["lineages"]) == 15 and len(current) == 8
    assert sum(row["extra_calls"] for row in record["splits"].values()) == 6
    assert sum(len(row["children"]) for row in record["splits"].values()) == 14
    before = journal.path.read_bytes()
    with pytest.raises(ValueError, match="depth"):
        registration.register_split(journal, current[0]["identity"], [[current[0]["owned"][0]], [current[0]["owned"][1]]],
            evidence="too-deep", inherited=False)
    assert journal.path.read_bytes() == before
    other = root(journal, source_file="other.tex")
    with pytest.raises(RuntimeError, match="Document split expansion"):
        registration.register_split(journal, other["identity"], [other["owned"][:8], other["owned"][8:]],
            evidence="different-root", inherited=False)


@pytest.mark.parametrize("change", ["free", "evidence", "children"])
def test_registered_split_cannot_change_origin_or_ownership(tmp_path, change):
    journal = reservations(tmp_path)
    parent = root(journal)
    children = [parent["owned"][:8], parent["owned"][8:]]
    registration.register_split(journal, parent["identity"], children, evidence="new-rule", inherited=False)
    before = journal.path.read_bytes()
    with pytest.raises(RuntimeError, match="ancestry, origin or charge"):
        registration.register_split(journal, parent["identity"], list(reversed(children)) if change == "children" else children,
            evidence="changed-rule" if change == "evidence" else "new-rule", inherited=change == "free")
    assert journal.path.read_bytes() == before


@pytest.mark.parametrize("kind", ["root", "split"])
@pytest.mark.parametrize("cut", ["before", "after"])
def test_process_death_never_separates_ownership_from_charge(tmp_path, monkeypatch, kind, cut):
    journal = reservations(tmp_path)
    parent = root(journal) if kind == "split" else None

    def action():
        if kind == "root":
            return root(journal)
        return registration.register_split(journal, parent["identity"], [parent["owned"][:8], parent["owned"][8:]],
            evidence="durable", inherited=False)

    def worker():
        native = journal.save

        def save(value):
            if cut == "before":
                os._exit(73)
            native(value)
            os._exit(73)

        monkeypatch.setattr(journal, "save", save)
        action()

    child = multiprocessing.get_context("fork").Process(target=worker)
    child.start()
    child.join(30)
    if child.is_alive():
        child.kill()
        child.join(5)
    assert child.exitcode == 73
    action()
    before = journal.path.read_bytes()
    action()
    assert before == journal.path.read_bytes()
    record = journal.read()
    assert len(record["source_scopes"]) == 1
    assert len(record["lineages"]) == (3 if kind == "split" else 1)
    assert sum(row["extra_calls"] for row in record["splits"].values()) == (1 if kind == "split" else 0)
