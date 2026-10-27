"""Preserve exact restart membership through publication cuts and missing history."""

import multiprocessing
import os
from copy import deepcopy
from types import SimpleNamespace

import pytest

from humanvoice.artifacts import read_json, write_json
from tools import durable_program_supervisor as durable
from tools.inventory_recovery_v3 import restart_history
from tools.inventory_recovery_v3.failures import RecoveryStop


def monitor_for(root, ceiling=2):
    configuration = {"maximum_worker_restarts": ceiling}
    state_path = root / "state.json"
    state = read_json(state_path) if state_path.exists() else {
        "config_identity": durable.fingerprint(configuration), "run_id": "offline-restarts",
        "job": "job-0001", "worker_restarts": 0}
    return SimpleNamespace(root=root, config=configuration, state=state)


def next_receipt(monitor, ordinal):
    job = f"job-{ordinal:04d}"
    monitor.state["job"] = job
    request = {"job_id": job, "run_id": monitor.state["run_id"],
               "config_identity": monitor.state["config_identity"], "command": ["offline"]}
    write_json(monitor.root / "jobs" / job / "request.json", request)
    durable.save(monitor.root / "state.json", monitor.state)
    return restart_history.identified({"job": job, "run_id": monitor.state["run_id"],
        "config_identity": monitor.state["config_identity"], "worker_restart": ordinal,
        "request_identity": durable.fingerprint(request), "new_provider_calls": 0,
        "action": "resume-with-native-reconciliation", "cursor": {"generation": 0},
        "ack_sha256": None, "result_sha256": None})


def publish(monitor, receipt):
    monitor.state.update(worker_restarts=receipt["worker_restart"], worker_recovery=receipt,
                         last_job=receipt["job"], job=None)
    durable.save(monitor.root / "state.json", monitor.state)


def bytes_before(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*.json")}


@pytest.mark.parametrize("missing", ["last", "all", "head", "marker"])
def test_lost_committed_restart_never_renews_allowance(tmp_path, missing):
    monitor = monitor_for(tmp_path)
    for ordinal in (1, 2):
        receipt = next_receipt(monitor, ordinal)
        assert restart_history.commit(monitor, receipt, lambda: None) == receipt
        publish(monitor, receipt)
    next_receipt(monitor, 3)
    targets = {"last": [tmp_path / "jobs/job-0002/recovery.json"],
        "all": list(tmp_path.glob("jobs/*/recovery.json")),
        "head": [tmp_path / "restart-head.json"],
        "marker": [tmp_path / "restart-initialization.json"]}[missing]
    for path in targets:
        path.unlink()
    before = bytes_before(tmp_path)
    with pytest.raises(RecoveryStop, match="disappeared"):
        restart_history.read(monitor_for(tmp_path))
    assert bytes_before(tmp_path) == before
    assert monitor.state["worker_restarts"] == 2


def publication_name(path, value):
    if path.name == "restart-initialization.json":
        return "initialization-" + value["status"]
    if path.name == "restart-head.json":
        return "head-pending" if value["pending"] else "head-committed" if value["committed"] else "head-empty"
    return path.name


def crash(root, receipt, boundary, after):
    native = restart_history.persist

    def write(path, value):
        selected = publication_name(path, value) == boundary
        if selected and not after:
            os._exit(73)
        native(path, value)
        if selected:
            os._exit(73)

    restart_history.persist = write
    monitor = monitor_for(root)
    restart_history.commit(monitor, receipt, lambda: None)
    if boundary == "state.json" and not after:
        os._exit(73)
    publish(monitor, receipt)
    os._exit(73 if boundary == "state.json" else 74)


@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("boundary", ["initialization-pending", "head-empty", "initialization-complete",
    "head-pending", "recovery.json", "head-committed", "state.json"])
def test_restart_publication_process_death_is_exactly_once(tmp_path, boundary, after):
    monitor = monitor_for(tmp_path)
    receipt = next_receipt(monitor, 1)
    process = multiprocessing.get_context("fork").Process(target=crash, args=(tmp_path, receipt, boundary, after))
    process.start()
    process.join(10)
    if process.is_alive():
        process.kill()
        process.join(5)
    assert process.exitcode == 73
    reopened = monitor_for(tmp_path)
    assert restart_history.commit(reopened, receipt, lambda: None) == receipt
    publish(reopened, receipt)
    before = bytes_before(tmp_path)
    assert restart_history.commit(monitor_for(tmp_path), receipt, lambda: None) == receipt
    assert bytes_before(tmp_path) == before
    assert len(restart_history.read(reopened)["committed"]) == 1
    assert len(list(tmp_path.glob("jobs/*/recovery.json"))) == 1


@pytest.mark.parametrize("boundary", ["initialization-pending", "head-empty", "initialization-complete",
    "head-pending", "recovery.json", "head-committed"])
def test_restart_disk_failure_retains_recoverable_intent(tmp_path, monkeypatch, boundary):
    monitor = monitor_for(tmp_path)
    receipt = next_receipt(monitor, 1)
    native = restart_history.persist

    def fail(path, value):
        if publication_name(path, value) == boundary:
            raise OSError("disk failure")
        native(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(restart_history, "persist", fail)
        with pytest.raises(OSError, match="disk failure"):
            restart_history.commit(monitor, receipt, lambda: None)
    assert restart_history.commit(monitor_for(tmp_path), receipt, lambda: None) == receipt
    assert len(restart_history.read(monitor)["committed"]) == 1


@pytest.mark.parametrize("cut", range(1, 7))
def test_stop_before_each_restart_write_preserves_pending_history(tmp_path, cut):
    monitor = monitor_for(tmp_path)
    receipt = next_receipt(monitor, 1)
    calls = []

    def stop():
        calls.append(True)
        if len(calls) == cut:
            raise RecoveryStop("USER_STOPPED", "pause")

    with pytest.raises(RecoveryStop, match="pause"):
        restart_history.commit(monitor, receipt, stop)
    before = bytes_before(tmp_path)
    restart_history.read(monitor)
    assert before == bytes_before(tmp_path)
    assert restart_history.commit(monitor, receipt, lambda: None) == receipt


@pytest.mark.parametrize("defect", ["run", "source", "ceiling", "published", "ordinal",
    "receipt", "missing_request", "orphan", "pending_job", "symlink", "malformed"])
def test_restart_corruption_fails_without_writes(tmp_path, defect):
    monitor = monitor_for(tmp_path)
    receipt = next_receipt(monitor, 1)
    restart_history.commit(monitor, receipt, lambda: None)
    publish(monitor, receipt)
    if defect == "run":
        monitor.state["run_id"] = "foreign"
    elif defect == "source":
        monitor.state["config_identity"] = "foreign"
    elif defect == "ceiling":
        monitor.config["maximum_worker_restarts"] = 3
    elif defect == "published":
        monitor.state["worker_restarts"] = 2
    elif defect == "ordinal":
        head = read_json(tmp_path / "restart-head.json")
        head["committed"][0]["receipt"]["worker_restart"] = 2
        write_json(tmp_path / "restart-head.json", restart_history.identified(head))
    elif defect == "receipt":
        changed = {**receipt, "cursor": {"generation": 1}}
        write_json(tmp_path / "jobs/job-0001/recovery.json", restart_history.identified(changed))
    elif defect == "missing_request":
        (tmp_path / "jobs/job-0001/request.json").unlink()
    elif defect == "orphan":
        write_json(tmp_path / "jobs/job-0002/recovery.json", receipt)
    elif defect == "pending_job":
        monitor.state.update(worker_restarts=0, worker_recovery=None, job="job-0002")
    elif defect == "symlink":
        path = tmp_path / "restart-head.json"
        path.rename(tmp_path / "archived.json")
        path.symlink_to(tmp_path / "archived.json")
    else:
        (tmp_path / "restart-head.json").write_text("{")
    before = bytes_before(tmp_path)
    with pytest.raises((ValueError, RuntimeError, OSError)):
        restart_history.read(monitor)
    assert bytes_before(tmp_path) == before


def test_pending_restart_cannot_change_evidence_or_exceed_limit(tmp_path, monkeypatch):
    monitor = monitor_for(tmp_path, ceiling=1)
    receipt = next_receipt(monitor, 1)
    native = restart_history.persist

    def cut(path, value):
        native(path, value)
        if publication_name(path, value) == "head-pending":
            raise OSError("cut")

    with monkeypatch.context() as patch:
        patch.setattr(restart_history, "persist", cut)
        with pytest.raises(OSError, match="cut"):
            restart_history.commit(monitor, receipt, lambda: None)
    changed = deepcopy(receipt)
    changed["cursor"] = {"generation": 2}
    with pytest.raises(RuntimeError, match="pending intent"):
        restart_history.commit(monitor, restart_history.identified(changed), lambda: None)
    restart_history.commit(monitor, receipt, lambda: None)
    publish(monitor, receipt)
    second = next_receipt(monitor, 2)
    before = bytes_before(tmp_path)
    with pytest.raises(RecoveryStop, match="allowance exhausted"):
        restart_history.commit(monitor, second, lambda: None)
    assert before == bytes_before(tmp_path)
