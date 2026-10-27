"""Reject substituted journals and lost sealed consumption across generations."""

import multiprocessing
import os
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_inventory_recovery_v3_policy import dispatch, reservations, reserve, settle

from humanvoice.artifacts import digest, read_json, write_json
from tools.inventory_recovery_v3 import journal_binding, journal_history
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import RecoveryReservations


def setup(tmp_path):
    journal = reservations(tmp_path / "pairs")
    authority = SimpleNamespace(configuration={"recovery_journal": journal_binding.descriptor(journal)},
                                check=lambda: True)
    plan = {"plan_identity": "first", "bindings": {"source": journal.binding["document"]},
            journal_binding.FIELD: {"policy": journal.policy,
                "migration_identity": journal.binding["migration"], "transition": {"version": "initial"}}}
    output = tmp_path / "generation-00"
    write_json(output / "plan.json", plan)
    write_json(output / "execution.json", {"status": "executing", "plan_identity": plan["plan_identity"]})
    return journal, authority, plan, output


def finish(output, plan, authority, journal):
    checkpoint = journal_binding.checkpoint(output, plan, authority, journal, lambda: True)
    terminal = {"status": "nonpass", "plan_identity": plan["plan_identity"],
                "recovery_journal_checkpoint": digest(checkpoint)}
    write_json(output / "execution.json", terminal)
    write_json(output / "allocation-seal.json", {"terminal_hash": digest(terminal)})
    return checkpoint


def successor(tmp_path, plan, output):
    following = deepcopy(plan)
    following["plan_identity"] = "next"
    following[journal_binding.FIELD]["transition"] = {"version": "inventory-settled-successor-v3",
        "parent_plan_identity": plan["plan_identity"], "proof": {"predecessor": str(output)}}
    directory = tmp_path / "generation-01"
    write_json(directory / "plan.json", following)
    write_json(directory / "execution.json", {"status": "prepared", "plan_identity": following["plan_identity"]})
    return following, directory


@pytest.mark.parametrize("defect", ["replacement", "authority", "marker", "marker_binding",
                                     "marker_bytes", "journal", "admission"])
def test_admitted_canonical_journal_is_mandatory(tmp_path, defect):
    journal, authority, plan, _output = setup(tmp_path)
    if defect == "replacement":
        journal = RecoveryReservations(tmp_path / "replacement", journal.policy, journal.binding)
        journal.initialize()
    elif defect == "authority":
        authority.configuration["recovery_journal"]["binding"]["authority"] = "foreign"
    elif defect == "admission":
        authority.configuration.clear()
    elif defect == "journal":
        journal.path.unlink()
    else:
        marker = journal.root / "initialized.json"
        if defect == "marker":
            marker.unlink()
        elif defect == "marker_bytes":
            marker.write_text(marker.read_text() + " ")
        else:
            write_json(marker, {"policy": journal.policy["identity"],
                                "binding": {**journal.binding, "authority": "foreign"}})
    before = {str(path): path.read_bytes() for path in tmp_path.rglob("*.json")}
    with pytest.raises(RecoveryStop):
        journal_binding.require_journal(authority, journal, plan)
    assert before == {str(path): path.read_bytes() for path in tmp_path.rglob("*.json")}


@pytest.mark.parametrize("missing", ["sequence", "unused_retry", "split", "lineage", "checkpoint",
                                     "checkpoint_rehashed", "seal", "cancelled"])
def test_successor_rejects_rehashed_loss_of_committed_consumption(tmp_path, missing):
    journal, authority, plan, output = setup(tmp_path)
    sequence = reserve(journal)
    dispatch(journal, sequence, "canary")
    settle(journal, sequence, "canary", outcome="cancelled", reported_tokens=None,
           cancellation_identity="explicit-cancellation", resume_authorizations=["exact-resume"])
    root = journal.register_root(purpose="concept_extraction", owned=["split-a", "split-b"])
    journal.split(root["identity"], [["split-a"], ["split-b"]])
    finish(output, plan, authority, journal)
    following, directory = successor(tmp_path, plan, output)
    record = journal.read()
    if missing == "sequence":
        record["sequences"].clear()
    elif missing == "unused_retry":
        record["sequences"][sequence["identity"]]["slots"].pop("retry")
    elif missing == "cancelled":
        del record["sequences"][sequence["identity"]]["cancelled"]
    elif missing in {"split", "lineage"}:
        record["splits" if missing == "split" else "lineages"].clear()
    elif missing in {"checkpoint", "seal"}:
        (output / (journal_binding.CHECKPOINT if missing == "checkpoint" else "allocation-seal.json")).unlink()
    else:
        checkpoint = read_json(output / journal_binding.CHECKPOINT)
        checkpoint["record"]["sequences"].clear()
        retained = checkpoint["record"]
        retained["identity"] = digest({key: value for key, value in retained.items() if key != "identity"})
        checkpoint["identity"] = digest({key: value for key, value in checkpoint.items() if key != "identity"})
        write_json(output / journal_binding.CHECKPOINT, checkpoint)
    write_json(journal.path, journal_history.identified(record))
    before = {str(path): path.read_bytes() for path in tmp_path.rglob("*.json")}
    with pytest.raises(RecoveryStop):
        journal_binding.require_history(directory, following, authority, journal)
    assert before == {str(path): path.read_bytes() for path in tmp_path.rglob("*.json")}


def test_journal_append_and_unsealed_checkpoint_progress_are_monotonic(tmp_path):
    journal, authority, plan, output = setup(tmp_path)
    first = reserve(journal)
    initial = journal_binding.checkpoint(output, plan, authority, journal, lambda: True)
    dispatch(journal, first, "canary")
    settle(journal, first, "canary")
    advanced = journal_binding.checkpoint(output, plan, authority, journal, lambda: True)
    assert initial != advanced
    retained = (output / journal_binding.CHECKPOINT).read_bytes()
    assert journal_binding.checkpoint(output, plan, authority, journal, lambda: True) == advanced
    assert (output / journal_binding.CHECKPOINT).read_bytes() == retained
    finish(output, plan, authority, journal)
    following, directory = successor(tmp_path, plan, output)
    reserve(journal, lineage="second", incident="second")
    assert journal_binding.require_history(directory, following, authority, journal) == journal.read()
    with pytest.raises(RecoveryStop, match="cannot be replaced"):
        journal_binding.checkpoint(output, plan, authority, journal, lambda: True)
    assert (output / journal_binding.CHECKPOINT).read_bytes() == retained


@pytest.mark.parametrize("condition", ["stop", "owner", "changed"])
def test_checkpoint_rechecks_ownership_and_journal_before_write(tmp_path, condition):
    journal, authority, plan, output = setup(tmp_path)
    observations = []

    def owner():
        observations.append(True)
        if len(observations) == 2:
            if condition == "stop":
                raise RecoveryStop("USER_STOPPED", "late stop")
            if condition == "changed":
                reserve(journal)
            else:
                return False
        return True

    with pytest.raises(RecoveryStop):
        journal_binding.checkpoint(output, plan, authority, journal, owner)
    assert not (output / journal_binding.CHECKPOINT).exists()


def test_forged_cancellation_never_renews_a_consumed_profile(tmp_path):
    journal, authority, plan, output = setup(tmp_path)
    sequence = reserve(journal)
    for role in ("canary", "retry"):
        dispatch(journal, sequence, role)
        settle(journal, sequence, role)
    finish(output, plan, authority, journal)
    following, directory = successor(tmp_path, plan, output)
    record = journal.read()
    record["sequences"][sequence["identity"]]["cancelled"] = "fabricated"
    with pytest.raises(RecoveryStop, match="cancellation flag"):
        journal.save(record)
    write_json(journal.path, journal_history.identified(record))
    with pytest.raises(RecoveryStop, match="consumption membership"):
        journal_binding.require_history(directory, following, authority, journal)


@pytest.mark.parametrize("earlier_checkpoint", [False, True])
def test_uncheckpointed_consumption_loss_cannot_become_canonical(tmp_path, earlier_checkpoint):
    journal, authority, plan, output = setup(tmp_path)
    if earlier_checkpoint:
        journal_binding.checkpoint(output, plan, authority, journal, lambda: True)
    sequence = reserve(journal)
    dispatch(journal, sequence, "canary")
    settle(journal, sequence, "canary")
    record = journal.read()
    record["sequences"].clear()
    with pytest.raises(RecoveryStop, match="sequence disappeared"):
        journal.save(record)
    write_json(journal.path, journal_history.identified(record))
    with pytest.raises(RecoveryStop, match="consumption membership"):
        journal_binding.checkpoint(output, plan, authority, journal, lambda: True)
    assert not (output / "allocation-seal.json").exists()


def journal_cut(root, boundary, after):
    from test_inventory_recovery_v3_policy import policy

    journal = RecoveryReservations(root, policy(),
        {"document": "source", "migration": "sealed-parent", "authority": "existing-grant"})
    native = journal_history.persist

    def write(path, value):
        selected = ("journal" if path.name == "reservations.json" else
                    "pending" if value["pending"] is not None else "committed") == boundary
        if selected and not after:
            os._exit(73)
        native(path, value)
        if selected:
            os._exit(73)

    journal_history.persist = write
    reserve(journal)
    os._exit(74)


@pytest.mark.parametrize("boundary", ["pending", "journal", "committed"])
@pytest.mark.parametrize("after", [False, True])
def test_write_ahead_journal_survives_process_death(tmp_path, boundary, after):
    journal = reservations(tmp_path)
    root = journal.register_root(purpose="concept_extraction", owned=["first"])
    process = multiprocessing.get_context("fork").Process(target=journal_cut, args=(tmp_path, boundary, after))
    process.start()
    process.join(10)
    if process.is_alive():
        process.kill()
        process.join(5)
    assert process.exitcode == 73
    reopened = RecoveryReservations(tmp_path, journal.policy, journal.binding)
    sequence = reserve(reopened)
    assert sequence["lineage"] == root["identity"]
    assert len(reopened.read()["sequences"]) == 1
    before = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}
    assert reserve(reopened) == sequence
    assert before == {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}


def test_lost_head_or_marker_does_not_reconcile_pending_journal(tmp_path, monkeypatch):
    journal = reservations(tmp_path)
    journal.register_root(purpose="concept_extraction", owned=["first"])
    native = journal_history.persist

    def fail(path, value):
        if path == journal.path:
            raise OSError("journal publication failed")
        native(path, value)

    with monkeypatch.context() as interrupted:
        interrupted.setattr(journal_history, "persist", fail)
        with pytest.raises(OSError):
            reserve(journal)
    snapshot = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}
    with pytest.raises(RecoveryStop, match="pending publication"):
        journal.status()
    assert snapshot == {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}
    marker = journal.root / "initialized.json"
    retained = marker.read_bytes()
    marker.unlink()
    before = journal.path.read_bytes()
    with pytest.raises(RecoveryStop, match="marker disappeared"), journal.locked():
        pytest.fail("Missing initialization was ignored")
    assert journal.path.read_bytes() == before
    marker.write_bytes(retained)
    journal.publication_check = lambda: (_ for _ in ()).throw(RecoveryStop("USER_STOPPED", "stop"))
    with pytest.raises(RecoveryStop, match="stop"), journal.locked():
        pytest.fail("Pending publication ignored user stop")
    assert journal.path.read_bytes() == before
    journal.publication_check = lambda: True
    with journal.locked():
        assert len(journal.read()["sequences"]) == 1
    (journal.root / "consumption-head.json").unlink()
    with pytest.raises(RecoveryStop, match="head disappeared"):
        journal.initialize()
