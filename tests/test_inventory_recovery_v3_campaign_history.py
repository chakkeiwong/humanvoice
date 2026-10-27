"""Crash and corruption cuts for prospective campaign publication mechanics."""

import multiprocessing
import os
from copy import deepcopy
from pathlib import Path

import pytest

from humanvoice.artifacts import digest, read_json, write_json
from tools.inventory_recovery_v3 import campaign_history as history
from tools.inventory_recovery_v3.failures import RecoveryStop


def campaign(tmp_path, maximum=3, check=lambda: True):
    root = tmp_path / "campaign"
    seed = history.identified({"version": history.VERSION, "root": str(root),
        "binding": {"fixture": "offline-component-only"}, "maximum_generations": maximum,
        "journal": {"fixture": "canonical-pair-journal"}, "initial": {"generation": 0,
            "output": str(root / "generation-00"), "plan_identity": "initial", "transition_identity": "initial"}})
    return history.CampaignHistory(root, seed, check=check)


def transition(current):
    cursor = current.status()["cursor"]
    return history.identified({"parent_plan_identity": cursor["plan_identity"],
                               "proof": {"predecessor": cursor["output"]}})


def validated(intent, check):
    assert check() is True
    output = Path(intent["output"])
    plan = {"fixture_generation": intent["generation"]}
    plan["plan_identity"] = digest(plan)
    for name, value in (("plan.json", plan), ("admission-probe.json", {"status": "pass",
            "model_calls": 0, "transition": intent["transition"]["identity"]})):
        if not (output / name).exists():
            check()
            write_json(output / name, value)
    return {"plan_identity": plan["plan_identity"], "plan_sha256": digest((output / "plan.json").read_bytes()),
            "probe_sha256": digest((output / "admission-probe.json").read_bytes()),
            "validation_identity": "validated-fixture"}


def snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()} if root.exists() else {}


def cut_worker(root, seed, operation, boundary, after):
    current = history.CampaignHistory(root, seed, check=lambda: True)
    native = history.persist

    def persist(path, value):
        label = path.name
        if label == "head.json" and operation == "advance":
            label = "pending" if value["revision"] == 1 else "head" if value["pending"] else "clear"
        if label == boundary and not after:
            os._exit(73)
        native(path, value)
        if label == boundary:
            os._exit(73)

    history.persist = persist
    with current.owned():
        if operation == "initialize":
            current.initialize()
        else:
            current.begin(transition(current))
            current.reconcile(validated)
    os._exit(74)


@pytest.mark.parametrize("boundary", ["initialization-intent.json", "seed.json", "head.json",
                                      "cursor.json", "initialized.json"])
@pytest.mark.parametrize("after", [False, True])
def test_initialization_process_death_is_exactly_resumable(tmp_path, boundary, after):
    current = campaign(tmp_path)
    process = multiprocessing.get_context("fork").Process(
        target=cut_worker, args=(current.root, current.seed, "initialize", boundary, after))
    process.start()
    process.join(10)
    assert not process.is_alive() and process.exitcode == 73
    before = snapshot(current.root)
    assert current.status()["status"] in {"UNINITIALIZED", "INITIALIZING", "READY"}
    assert before == snapshot(current.root)
    with current.owned():
        assert current.initialize()["status"] == "READY"
        retained = snapshot(current.root)
        current.initialize()
        assert retained == snapshot(current.root)


@pytest.mark.parametrize("boundary", ["pending", "transition-01.json", "head",
                                      "cursor.json", "repair-01.json", "clear"])
@pytest.mark.parametrize("after", [False, True])
def test_successor_process_death_preserves_one_transaction(tmp_path, boundary, after):
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
    following = transition(current)
    process = multiprocessing.get_context("fork").Process(
        target=cut_worker, args=(current.root, current.seed, "advance", boundary, after))
    process.start()
    process.join(10)
    assert not process.is_alive() and process.exitcode == 73
    before = snapshot(current.root)
    current.status()
    assert before == snapshot(current.root)
    with current.owned():
        if current.status()["cursor"]["generation"] == 0 and current.status()["status"] == "READY":
            current.begin(following)
        result = current.reconcile(validated)
        assert result["status"] == "READY" and result["cursor"]["generation"] == 1
        retained = snapshot(current.root)
        assert current.reconcile(validated) == result
        assert retained == snapshot(current.root)
        assert len(result["head"]["committed"]) == 1


def test_two_successors_share_seed_and_finish_last_generation(tmp_path):
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
        for generation in (1, 2):
            current.begin(transition(current))
            result = current.reconcile(validated)
            assert result["cursor"]["generation"] == generation
        before = snapshot(current.root)
        with pytest.raises(RecoveryStop, match="allowance exhausted"):
            current.begin(transition(current))
        assert before == snapshot(current.root)
    reopened = history.CampaignHistory(current.root, current.seed, check=lambda: True)
    assert reopened.status() == result


@pytest.mark.parametrize("boundary", ["transition-01.json", "head", "cursor.json", "repair-01.json", "clear"])
@pytest.mark.parametrize("after", [False, True])
def test_repeated_publication_errors_and_stop_preserve_intent(tmp_path, monkeypatch, boundary, after):
    blocked, failures = [], []

    def check():
        if blocked:
            raise RecoveryStop("USER_STOPPED", "retained user stop")
        return True

    current = campaign(tmp_path, check=check)
    with current.owned():
        current.initialize()
        current.begin(transition(current))
    native = history.persist

    def persist(path, value):
        label = path.name if path.name != "head.json" else "head" if value["pending"] else "clear"
        if label == boundary and len(failures) < 3:
            failures.append(True)
            if after:
                native(path, value)
            raise OSError("publication storage fault")
        native(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(history, "persist", persist)
        for _attempt in range(4):
            try:
                with current.owned():
                    current.reconcile(validated)
            except OSError as error:
                assert str(error) == "publication storage fault"
                blocked.append(True)
                before = snapshot(current.root)
                with pytest.raises(RecoveryStop, match="retained user stop"), current.owned():
                    pytest.fail("Stopped campaign recovered")
                assert before == snapshot(current.root)
                blocked.clear()
            else:
                break
    assert failures
    with current.owned():
        result = current.reconcile(validated)
    assert result["cursor"]["generation"] == 1
    assert len(result["head"]["committed"]) == 1


@pytest.mark.parametrize("defect", ["head", "cursor", "repair", "transition", "extra",
                                    "seed", "marker", "previous_cursor", "missing_previous_repair"])
def test_missing_committed_evidence_is_not_repairable_pending_work(tmp_path, defect):
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
        old_cursor = read_json(current.root / "cursor.json")
        current.begin(transition(current))
        current.reconcile(validated)
        if defect == "missing_previous_repair":
            current.begin(transition(current))
            (current.root / "repair-01.json").unlink()
        elif defect == "extra":
            (current.root / "generation-09").mkdir()
        elif defect == "previous_cursor":
            write_json(current.root / "cursor.json", old_cursor)
        else:
            name = {"head": "head.json", "cursor": "cursor.json", "repair": "repair-01.json",
                    "transition": "transition-01.json", "seed": "seed.json", "marker": "initialized.json"}[defect]
            (current.root / name).unlink()
        before = snapshot(current.root)
        for operation in (current.status, current.initialize, lambda: current.reconcile(validated)):
            with pytest.raises((RecoveryStop, ValueError)):
                operation()
            assert before == snapshot(current.root)


@pytest.mark.parametrize("defect", ["lost_committed_transition", "repair_old_cursor", "cursor_before_head"])
def test_pending_artifact_order_rejects_impossible_combinations(tmp_path, defect):
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
        previous = read_json(current.root / "cursor.json")
        current.begin(transition(current))
        pending_head = read_json(current.root / "head.json")
        current.reconcile(validated)
        complete = read_json(current.root / "head.json")
        head = history.identified({**complete, "revision": 2, "pending": pending_head["pending"]})
        if defect == "lost_committed_transition":
            (current.root / "transition-01.json").unlink()
        elif defect == "repair_old_cursor":
            write_json(current.root / "cursor.json", previous)
        else:
            head = pending_head
            (current.root / "repair-01.json").unlink()
        write_json(current.root / "head.json", head)
        before = snapshot(current.root)
        with pytest.raises(RecoveryStop):
            current.reconcile(validated)
        assert before == snapshot(current.root)


def test_status_is_read_only_and_retries_a_concurrent_publication(tmp_path, monkeypatch):
    current = campaign(tmp_path)
    assert current.status()["status"] == "UNINITIALIZED"
    assert not current.root.exists()
    with current.owned():
        current.initialize()
        current.begin(transition(current))
        old_head = (current.root / "head.json").read_bytes()
        current.reconcile(validated)
    native, sampled = Path.read_bytes, []

    def read(path):
        if path == current.root / "head.json" and not sampled:
            sampled.append(True)
            return old_head
        return native(path)

    before = snapshot(current.root)
    monkeypatch.setattr(Path, "read_bytes", read)
    result = current.status()
    assert result["status"] == "READY" and result["cursor"]["generation"] == 1
    assert result["dispatch_allowed"] is False
    assert before == snapshot(current.root)


def test_changed_pending_and_competing_owner_cannot_publish(tmp_path):
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
        intent = current.begin(transition(current))
        other = history.CampaignHistory(current.root, current.seed, check=lambda: True)
        with pytest.raises(RecoveryStop, match="Another owner"), other.owned():
            pytest.fail("Concurrent campaign owner admitted")
        changed = deepcopy(intent["transition"])
        changed["foreign"] = True
        with pytest.raises(RecoveryStop, match="replace a pending"):
            current.begin(history.identified(changed))
        with pytest.raises(RecoveryStop, match="descriptor differs"):
            current.reconcile(lambda intent, check: {**validated(intent, check), "plan_identity": "initial"})
        assert not (current.root / "transition-01.json").exists()
    with pytest.raises(RecoveryStop, match="current owner"):
        current.reconcile(validated)


@pytest.mark.parametrize("name", ["initialization-intent.json", "seed.json", "initialized.json"])
def test_stable_malformed_initialization_is_not_publication_progress(tmp_path, name):
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
    (current.root / name).write_bytes(b"{")
    before = snapshot(current.root)
    for _attempt in range(2):
        with pytest.raises(ValueError):
            current.status()
        assert snapshot(current.root) == before


@pytest.mark.parametrize("phase", ["first_settled", "second_pending", "second_settled"])
@pytest.mark.parametrize("name", ["plan.json", "admission-probe.json"])
@pytest.mark.parametrize("mutation", ["missing", "changed"])
def test_committed_preparation_is_required_through_second_successor(tmp_path, phase, name, mutation):
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
        current.begin(transition(current))
        current.reconcile(validated)
        next_transition = transition(current)
        if phase != "first_settled":
            current.begin(next_transition)
        if phase == "second_settled":
            current.reconcile(validated)
        path = current.root / "generation-01" / name
        if mutation == "missing":
            path.unlink()
        else:
            path.write_bytes(path.read_bytes() + b" ")
        before = snapshot(current.root)
        for operation in (current.status, lambda: current.begin(next_transition), lambda: current.reconcile(validated)):
            with pytest.raises(RecoveryStop):
                operation()
            assert before == snapshot(current.root)


def replace_cut_worker(root, seed, destination, ready, release, killed):
    from tools.inventory_recovery_v3 import reservations

    current = history.CampaignHistory(root, seed, check=lambda: True)
    native = reservations.os.replace

    def replace(source, target):
        if Path(target).name == destination:
            ready.set()
            if killed:
                os._exit(73)
            assert release.wait(10)
        native(source, target)

    reservations.os.replace = replace
    with current.owned():
        current.reconcile(validated)


@pytest.mark.parametrize("generation", [1, 2])
@pytest.mark.parametrize("receipt", ["transition", "repair"])
@pytest.mark.parametrize("killed", [False, True])
def test_atomic_temporary_files_never_become_committed_membership(tmp_path, generation, receipt, killed):
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
        if generation == 2:
            current.begin(transition(current))
            current.reconcile(validated)
        current.begin(transition(current))
    context = multiprocessing.get_context("fork")
    ready, release = context.Event(), context.Event()
    process = context.Process(target=replace_cut_worker, args=(current.root, current.seed,
        f"{receipt}-{generation:02d}.json", ready, release, killed))
    process.start()
    assert ready.wait(10)
    assert list(current.root.glob(".campaign-publication-*"))
    before = snapshot(current.root)
    assert current.status()["status"] == "PENDING"
    assert before == snapshot(current.root)
    release.set()
    process.join(10)
    assert not process.is_alive() and process.exitcode == (73 if killed else 0)
    with current.owned():
        result = current.reconcile(validated)
        assert result["cursor"]["generation"] == generation
        assert len(result["head"]["committed"]) == generation
        before = snapshot(current.root)
        assert current.reconcile(validated) == result
        assert before == snapshot(current.root)


def test_guard_returns_true_only_for_valid_owner(tmp_path):
    current = campaign(tmp_path)
    with pytest.raises(RecoveryStop):
        current.guard()
    with current.owned():
        assert current.guard() is True
        current.initialize()
        current.begin(transition(current))
        assert current.reconcile(validated)["status"] == "READY"
