"""Crash-safe empty journal bootstrap without recreating consumed authority."""

import multiprocessing
import os
import stat
from copy import deepcopy

import pytest
from test_inventory_recovery_v3_policy import policy, reserve

from humanvoice.artifacts import read_json, write_json
from tools.inventory_recovery_v3 import journal_history
from tools.inventory_recovery_v3 import journal_initialization as bootstrap
from tools.inventory_recovery_v3 import reservations as storage
from tools.inventory_recovery_v3.failures import RecoveryStop


def fresh(root):
    return storage.RecoveryReservations(root, policy(), {
        "document": "source", "migration": "sealed-parent", "authority": "existing-grant"})


def snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            if path.is_file() else None for path in root.rglob("*")} if root.exists() else {}


def partial(journal, step):
    journal.root.mkdir(parents=True, exist_ok=True)
    for name, value in bootstrap.publications(journal)[:step]:
        write_json(journal.root / name, value)


def crash(root, boundary, after):
    journal = fresh(root)
    native, count = bootstrap.atomic_persist, [0]

    def persist(*arguments, **keywords):
        selected = count[0] == boundary
        count[0] += 1
        if selected and not after:
            os._exit(73)
        native(*arguments, **keywords)
        if selected:
            os._exit(73)

    bootstrap.atomic_persist = persist
    journal.initialize()
    os._exit(74)


@pytest.mark.parametrize("boundary", range(6))
@pytest.mark.parametrize("after", [False, True])
def test_initial_publication_death_reopens_exact_empty_tail(tmp_path, boundary, after):
    root = tmp_path / "journal"
    worker = multiprocessing.get_context("fork").Process(target=crash, args=(root, boundary, after))
    worker.start()
    worker.join(10)
    if worker.is_alive():
        worker.kill()
        worker.join(5)
    assert worker.exitcode == 73
    journal = fresh(root)
    before = snapshot(root)
    state = bootstrap.observe(journal)
    assert state["step"] == boundary + int(after)
    assert not state["dispatch_allowed"] and before == snapshot(root)
    if state["step"] < 6:
        with pytest.raises(RecoveryStop), journal.locked():
            pytest.fail("Ordinary entry repaired incomplete initialization")
        assert before == snapshot(root)
    assert journal.initialize() == bootstrap.empty(journal)
    retained = snapshot(root)
    reopened = fresh(root)
    assert reopened.initialize() == journal.read()
    assert retained == snapshot(root)
    reserve(reopened)
    assert len(journal.read()["sequences"]) == 1


@pytest.mark.parametrize("boundary", range(6))
@pytest.mark.parametrize("operation", ["file_sync", "replace", "directory_sync"])
@pytest.mark.parametrize("after", [False, True])
def test_initialization_handles_real_atomic_io_errors(tmp_path, monkeypatch, boundary, operation, after):
    journal = fresh(tmp_path / "journal")
    native_publish, native_sync, native_replace = bootstrap.atomic_persist, os.fsync, os.replace
    publishing, count, failed = [-1], [0], []

    def invoke(native, selected, *arguments):
        trigger = selected and publishing[0] == boundary and not failed
        if trigger:
            failed.append(True)
            if not after:
                raise OSError("injected bootstrap storage failure")
        result = native(*arguments)
        if trigger:
            raise OSError("injected post-publication storage failure")
        return result

    def publish(*arguments, **keywords):
        publishing[0] = count[0]
        count[0] += 1
        return native_publish(*arguments, **keywords)

    def sync(descriptor):
        kind = "directory_sync" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file_sync"
        return invoke(native_sync, operation == kind, descriptor)

    with monkeypatch.context() as injected:
        injected.setattr(bootstrap, "atomic_persist", publish)
        injected.setattr(os, "fsync", sync)
        injected.setattr(os, "replace", lambda *arguments: invoke(native_replace, operation == "replace", *arguments))
        with pytest.raises(OSError, match="storage failure"):
            journal.initialize()
    assert failed == [True]
    before = snapshot(journal.root)
    bootstrap.observe(journal)
    assert before == snapshot(journal.root)
    assert journal.initialize() == bootstrap.empty(journal)
    retained = snapshot(journal.root)
    assert fresh(journal.root).initialize() == journal.read()
    assert retained == snapshot(journal.root)


@pytest.mark.parametrize("step", range(7))
def test_status_is_read_only_for_virgin_and_every_bootstrap_cut(tmp_path, step):
    root = tmp_path / "journal"
    journal = fresh(root)
    assert not root.exists()
    if step:
        partial(journal, step)
    before = snapshot(tmp_path)
    state = bootstrap.observe(journal)
    assert state["step"] == step and not state["dispatch_allowed"]
    status = fresh(root).status()
    assert not status["live_authority"] and not status["dispatch_allowed"]
    assert before == snapshot(tmp_path)
    assert not (root / "reservations.lock").exists()


@pytest.mark.parametrize("step", range(6))
@pytest.mark.parametrize("condition", ["false", "stop"])
def test_veto_never_publishes_initialization(tmp_path, step, condition):
    journal = fresh(tmp_path / "journal")
    if step:
        partial(journal, step)
    before = snapshot(tmp_path)

    def check():
        if condition == "stop":
            raise RecoveryStop("USER_STOPPED", "initialization stopped")
        return False

    journal.publication_check = check
    with pytest.raises(RecoveryStop):
        journal.initialize()
    assert before == snapshot(tmp_path)


@pytest.mark.parametrize("boundary", range(6))
@pytest.mark.parametrize("condition", ["false", "stop"])
@pytest.mark.parametrize("observation", [2, 3])
def test_late_veto_after_observation_prevents_next_publication(tmp_path, monkeypatch, boundary, condition, observation):
    journal = fresh(tmp_path / "journal")
    partial(journal, boundary)
    native, revoked, observations = bootstrap.observe, [False], []

    def observe(selected):
        result = native(selected)
        observations.append(True)
        if len(observations) == observation:
            revoked[0] = True
        return result

    def check():
        if revoked[0] and condition == "stop":
            raise RecoveryStop("USER_STOPPED", "late initialization stop")
        return not revoked[0]

    journal.publication_check = check
    before = {path.name: path.read_bytes() for path in journal.root.glob("*.json")}
    monkeypatch.setattr(bootstrap, "observe", observe)
    with pytest.raises(RecoveryStop):
        journal.initialize()
    assert len(observations) == observation
    assert before == {path.name: path.read_bytes() for path in journal.root.glob("*.json")}


@pytest.mark.parametrize("defect", ["intent", "marker", "head", "journal", "downgrade", "rehashed_intent"])
def test_complete_initialization_never_recreates_lost_evidence(tmp_path, defect):
    journal = fresh(tmp_path / "journal")
    journal.initialize()
    reserve(journal)
    paths = {"intent": "initialization-intent.json", "marker": "initialized.json",
             "head": "consumption-head.json", "journal": "reservations.json"}
    if defect in paths:
        (journal.root / paths[defect]).unlink()
    elif defect == "downgrade":
        (journal.root / "initialization-intent.json").unlink()
        write_json(journal.root / "initialized.json", {"policy": journal.policy["identity"], "binding": journal.binding})
    else:
        value = bootstrap.intent(journal)
        value["binding"]["path"] += "-foreign"
        write_json(journal.root / "initialization-intent.json", journal_history.identified(value))
    before = snapshot(journal.root)
    for action in (journal.initialize, journal.status, journal.read):
        with pytest.raises((RecoveryStop, ValueError)):
            action()
        assert before == snapshot(journal.root)


@pytest.mark.parametrize("defect", ["extra", "nonempty", "lost_head", "journal_before_head", "missing_marker", "missing_journal"])
def test_pending_initialization_rejects_impossible_or_spent_state(tmp_path, defect):
    journal = fresh(tmp_path / "journal")
    partial(journal, 5)
    if defect == "extra":
        write_json(journal.root / "allocation-ledger.json", {"calls": []})
    elif defect == "nonempty":
        record = bootstrap.empty(journal)
        record["inherited_recovery"] = {"spent": 1}
        record = journal_history.identified(record)
        head = read_json(journal.root / "consumption-head.json")
        write_json(journal.path, record)
        write_json(journal.root / "consumption-head.json", journal_history.identified({**head, "committed": record}))
    elif defect in {"lost_head", "journal_before_head"}:
        (journal.root / "consumption-head.json").unlink()
    elif defect == "missing_marker":
        (journal.root / "initialized.json").unlink()
    else:
        journal.path.unlink()
    before = snapshot(journal.root)
    for action in (journal.initialize, journal.status):
        with pytest.raises(RecoveryStop):
            action()
        assert before == snapshot(journal.root)


@pytest.mark.parametrize("missing", [None, "head", "journal"])
def test_legacy_journal_reopens_without_upgrade_or_history_recreation(tmp_path, missing):
    journal = fresh(tmp_path / "journal")
    journal.root.mkdir()
    record = journal_history.identified(bootstrap.intent(journal)["record"])
    write_json(journal.root / "initialized.json", {"policy": journal.policy["identity"], "binding": journal.binding})
    write_json(journal.path, record)
    write_json(journal.root / "consumption-head.json", journal_history.identified({
        "version": "recovery-consumption-head-v1", "binding": journal_history.binding(journal),
        "committed": record, "pending": None}))
    with journal.locked():
        pass
    if missing:
        (journal.root / ("consumption-head.json" if missing == "head" else "reservations.json")).unlink()
    before = snapshot(journal.root)
    if missing:
        with pytest.raises(RecoveryStop):
            journal.initialize()
    else:
        assert journal.initialize() == record
    assert before == snapshot(journal.root)
    assert not (journal.root / "initialization-intent.json").exists()


@pytest.mark.parametrize("name", bootstrap.FILES)
def test_stable_malformed_journal_status_is_not_transient(tmp_path, name):
    journal = fresh(tmp_path / "journal")
    journal.initialize()
    (journal.root / name).write_text("{")
    before = snapshot(journal.root)
    for _attempt in range(2):
        with pytest.raises(ValueError):
            journal.status()
    assert before == snapshot(journal.root)


def test_readonly_observation_retries_concurrent_publication(tmp_path, monkeypatch):
    journal = fresh(tmp_path / "journal")
    partial(journal, 2)
    native, seen = bootstrap.inspect, []

    def inspect(*arguments):
        result = native(*arguments)
        if not seen:
            seen.append(True)
            partial(journal, 6)
        return result

    monkeypatch.setattr(bootstrap, "inspect", inspect)
    state = journal.status()
    assert state["sequences_reserved"] == 0
    assert not (journal.root / "reservations.lock").exists()


def test_competing_initializer_cannot_publish(tmp_path):
    journal = fresh(tmp_path / "journal")
    with journal.locked(reconcile=False):
        before = snapshot(journal.root)
        with pytest.raises(RecoveryStop, match="owner is active"):
            fresh(journal.root).initialize()
        assert before == snapshot(journal.root)


def test_consumption_cannot_remove_initialization_identity(tmp_path):
    journal = fresh(tmp_path / "journal")
    journal.initialize()
    record = deepcopy(journal.read())
    record.pop("initialization_identity")
    with pytest.raises(RecoveryStop, match="binding or history changed"):
        journal.save(record)


@pytest.mark.parametrize("step", [1, 2, 3, 4, 5, 6])
def test_boolean_alias_cannot_change_retained_intent(tmp_path, step):
    journal = fresh(tmp_path / "journal")
    partial(journal, step)
    path = journal.root / "initialization-intent.json"
    record = read_json(path)
    record["record"]["policy"]["qualification_calls"] = False
    write_json(path, record)
    before = snapshot(journal.root)
    for action in (journal.initialize, journal.status):
        with pytest.raises(RecoveryStop):
            action()
        assert before == snapshot(journal.root)


def atomic_crash(root, boundary, operation):
    journal = fresh(root)
    partial(journal, boundary)
    if operation == "replace":
        def replace(*arguments):
            os._exit(73)

        storage.os.replace = replace
    else:
        native = storage.os.fsync

        def sync(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                os._exit(73)
            return native(descriptor)

        storage.os.fsync = sync
    journal.initialize()
    os._exit(74)


@pytest.mark.parametrize("boundary", range(6))
@pytest.mark.parametrize("operation", ["replace", "directory_sync"])
def test_death_inside_atomic_bootstrap_handles_retained_temporary(tmp_path, boundary, operation):
    root = tmp_path / "journal"
    worker = multiprocessing.get_context("fork").Process(target=atomic_crash, args=(root, boundary, operation))
    worker.start()
    worker.join(10)
    if worker.is_alive():
        worker.kill()
        worker.join(5)
    assert worker.exitcode == 73
    if operation == "replace":
        assert list(root.glob(bootstrap.TEMPORARY + "*"))
    journal = fresh(root)
    before = snapshot(root)
    state = bootstrap.observe(journal)
    assert state["step"] == boundary + int(operation == "directory_sync")
    assert before == snapshot(root)
    assert journal.initialize() == bootstrap.empty(journal)
    retained = snapshot(root)
    assert fresh(root).initialize() == journal.read()
    assert retained == snapshot(root)


def test_status_reports_publishing_after_bounded_unstable_reads(tmp_path, monkeypatch):
    journal = fresh(tmp_path / "journal")
    partial(journal, 2)
    native, calls = bootstrap.inspect, []

    def inspect(*arguments):
        result = native(*arguments)
        path = journal.root / "initialization-intent.json"
        path.write_bytes(path.read_bytes() + b" ")
        calls.append(True)
        return result

    monkeypatch.setattr(bootstrap, "inspect", inspect)
    status = journal.status()
    assert status["status"] == "PUBLICATION_IN_PROGRESS"
    assert len(calls) == 3 and not status["dispatch_allowed"]
    assert not (journal.root / "reservations.lock").exists()


@pytest.mark.parametrize("boundary", range(6))
@pytest.mark.parametrize("condition", ["false", "stop"])
def test_stop_after_durable_publication_prevents_later_tail(tmp_path, monkeypatch, boundary, condition):
    journal = fresh(tmp_path / "journal")
    partial(journal, boundary)
    native, revoked = bootstrap.atomic_persist, [False]

    def publish(*arguments, **keywords):
        result = native(*arguments, **keywords)
        revoked[0] = True
        return result

    def check():
        if revoked[0] and condition == "stop":
            raise RecoveryStop("USER_STOPPED", "stop after durable bootstrap publication")
        return not revoked[0]

    journal.publication_check = check
    with monkeypatch.context() as injected:
        injected.setattr(bootstrap, "atomic_persist", publish)
        if boundary < 5:
            with pytest.raises(RecoveryStop):
                journal.initialize()
        else:
            assert journal.initialize() == bootstrap.empty(journal)
    assert bootstrap.observe(journal)["step"] == boundary + 1
    before = snapshot(journal.root)
    with pytest.raises(RecoveryStop):
        journal.initialize()
    assert before == snapshot(journal.root)
    journal.publication_check = lambda: True
    assert journal.initialize() == bootstrap.empty(journal)


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("present", [False, True])
def test_normal_entry_cannot_complete_uncommitted_initial_head(tmp_path, legacy, present):
    journal = fresh(tmp_path / "journal")
    journal.initialize()
    record = bootstrap.empty(journal)
    if legacy:
        (journal.root / "initialization-intent.json").unlink()
        write_json(journal.root / "initialized.json", {"policy": journal.policy["identity"], "binding": journal.binding})
        record = journal_history.identified(bootstrap.intent(journal)["record"])
    write_json(journal.root / "consumption-head.json", journal_history.identified({
        "version": "recovery-consumption-head-v1", "binding": journal_history.binding(journal),
        "committed": None, "pending": record}))
    if present:
        write_json(journal.path, record)
    else:
        journal.path.unlink()
    before = snapshot(journal.root)
    if legacy and present:
        assert journal.status()["calls_reserved"] == 0
        assert before == snapshot(journal.root)
        with journal.locked():
            assert journal.read() == record
        assert read_json(journal.root / "consumption-head.json")["committed"] == record
    else:
        for action in (journal.initialize, journal.status, journal.read):
            with pytest.raises(RecoveryStop):
                action()
            assert before == snapshot(journal.root)
        with pytest.raises(RecoveryStop), journal.locked():
            pytest.fail("Normal entry completed an unadmitted bootstrap")
        assert before == snapshot(journal.root)


@pytest.mark.parametrize("value", ["null", "[]", "false", "0", '"intent"'])
def test_legacy_nonobject_intent_is_present_and_corrupt(tmp_path, value):
    journal = fresh(tmp_path / "journal")
    journal.initialize()
    record = journal_history.identified(bootstrap.intent(journal)["record"])
    write_json(journal.root / "initialized.json", {"policy": journal.policy["identity"], "binding": journal.binding})
    write_json(journal.path, record)
    write_json(journal.root / "consumption-head.json", journal_history.identified({
        "version": "recovery-consumption-head-v1", "binding": journal_history.binding(journal),
        "committed": record, "pending": None}))
    (journal.root / "initialization-intent.json").write_text(value)
    before = snapshot(journal.root)
    for action in (lambda: bootstrap.observe(journal), journal.status, journal.read, journal.initialize):
        with pytest.raises((ValueError, RecoveryStop)):
            action()
        assert before == snapshot(journal.root)
