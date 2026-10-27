"""Prove pre-ack launch ownership survives death and rejects foreign handles."""

import fcntl
import json
import multiprocessing
import os

import pytest
from test_inventory_recovery_v3_supervision import configured, upgrade

from humanvoice.artifacts import digest, read_json, write_json
from tools import durable_program_supervisor as durable
from tools.inventory_recovery_v3 import launch_handoff, launcher


@pytest.mark.parametrize("defect", ["none", "missing", "foreign", "fresh", "request", "retired", "changed_inode"])
def test_inherited_launch_requires_actual_parent_lock(tmp_path, monkeypatch, defect):
    _live, _module, monitor, request, _ack = configured(tmp_path, monkeypatch)
    directory = monitor.root / "jobs/job-0001"
    (directory / "ack.json").unlink()
    with launch_handoff.prepare(monitor.root, "job-0001", request, owner_check=lambda: True,
                                 stop_check=lambda: None) as handoff:
        monkeypatch.setenv(launch_handoff.CAPSULE, handoff["environment"][launch_handoff.CAPSULE])
        if defect == "missing":
            monkeypatch.delenv(launch_handoff.CAPSULE)
        elif defect == "request":
            request = {**request, "command": ["foreign"]}
        elif defect == "retired":
            durable.save(directory / "recovery.json", {"retired": True})
        elif defect == "changed_inode":
            (directory / "worker.lock").rename(directory / "old-worker.lock")
            (directory / "worker.lock").touch()
        elif defect in {"fresh", "foreign"}:
            path = directory / "worker.lock" if defect == "fresh" else tmp_path / "foreign.lock"
            with path.open("a") as descriptor:
                capsule = json.loads(os.environ[launch_handoff.CAPSULE])
                capsule["descriptor"] = descriptor.fileno()
                capsule["identity"] = digest({key: value for key, value in capsule.items() if key != "identity"})
                monkeypatch.setenv(launch_handoff.CAPSULE, json.dumps(capsule))
                with pytest.raises((ValueError, RuntimeError)), launch_handoff.inherited(
                        monitor.root, "job-0001", request, stop_check=lambda: None):
                    pytest.fail("Foreign open-file description gained launch ownership")
            return
        if defect == "none":
            with launch_handoff.inherited(monitor.root, "job-0001", request, stop_check=lambda: None) as inherited:
                assert os.fstat(inherited.fileno()).st_ino == os.stat(directory / "worker.lock").st_ino
            with (directory / "worker.lock").open("a") as probe, pytest.raises(BlockingIOError):
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            with pytest.raises((ValueError, RuntimeError)), launch_handoff.inherited(
                    monitor.root, "job-0001", request, stop_check=lambda: None):
                pytest.fail("Invalid launch inherited ownership")


@pytest.mark.parametrize("budget", [0, 15])
def test_never_spawned_intent_recovers_only_after_parent_death(tmp_path, monkeypatch, budget):
    live, module, monitor, request, _ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    directory = monitor.root / "jobs/job-0001"
    (directory / "ack.json").unlink()

    def interrupted_parent():
        with launch_handoff.prepare(monitor.root, "job-0001", request, owner_check=lambda: True,
                                     stop_check=lambda: None):
            os._exit(73)

    process = multiprocessing.get_context("fork").Process(target=interrupted_parent)
    process.start()
    process.join(10)
    assert not process.is_alive() and process.exitcode == 73
    assert not durable.alive(read_json(directory / "launch-intent.json")["monitor_owner"])
    monitor.config["maximum_worker_restarts"] = budget
    monkeypatch.setattr(module.implementation, "checked_request", lambda root, job: request)
    with live.ownership_scope():
        monitor.tick()
    if budget:
        assert monitor.state["status"] == "RESUMING"
        assert monitor.state["worker_restarts"] == 1
        retained = read_json(directory / "recovery.json")
        assert retained["new_provider_calls"] == 0
        monitor.state.update(job="job-0001", status="RUNNING")
        monitor.publish()
        with live.ownership_scope():
            monitor.tick()
        assert read_json(directory / "recovery.json") == retained
    else:
        assert monitor.state["status"] == "BLOCKED_BUDGET"
        assert not (directory / "recovery.json").exists()


def test_live_parent_intent_never_becomes_dead_worker_restart(tmp_path, monkeypatch):
    live, module, monitor, request, _ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    directory = monitor.root / "jobs/job-0001"
    (directory / "ack.json").unlink()
    with launch_handoff.prepare(monitor.root, "job-0001", request, owner_check=lambda: True,
                                 stop_check=lambda: None), live.ownership_scope():
        monitor.tick()
        assert monitor.state["job"] == "job-0001"
        assert monitor.state["ownership_phase"] == "OBSERVING_OWNED_PROCESS"
        assert not (directory / "recovery.json").exists()


def test_current_monitor_recovers_quiescent_intent_without_self_wait(tmp_path, monkeypatch):
    live, module, monitor, request, _ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    directory = monitor.root / "jobs/job-0001"
    (directory / "ack.json").unlink()
    with launch_handoff.prepare(monitor.root, "job-0001", request, owner_check=lambda: True,
                                 stop_check=lambda: None):
        pass
    with live.ownership_scope():
        monitor.tick()
    assert monitor.state["status"] == "RESUMING"
    assert monitor.state["worker_restarts"] == 1
    assert read_json(directory / "recovery.json")["new_provider_calls"] == 0


@pytest.mark.parametrize("budget", [0, 15])
def test_actual_worker_stop_after_ack_requires_exact_resume(tmp_path, monkeypatch, budget):
    live, module, monitor, request, _ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    directory = monitor.root / "jobs/job-0001"
    (directory / "ack.json").unlink()
    control = module.supervisor_recovery.control

    def worker(handoff):
        os.environ.update(handoff["environment"])
        checks = []

        def stop_check():
            checks.append(True)
            if len(checks) == 2:
                control.stop()
            control.require_running()

        def forbidden(*arguments, **keywords):
            (tmp_path / "unexpected-spawn").touch()
            raise AssertionError("Campaign spawned after prelaunch user stop")

        try:
            launcher.worker(module.implementation, "job-0001", spawn=forbidden, stop_check=stop_check)
        except RuntimeError as error:
            if getattr(error, "category", None) == "USER_STOPPED":
                os._exit(73)
            raise

    with launch_handoff.prepare(monitor.root, "job-0001", request, owner_check=lambda: True,
                                 stop_check=lambda: None) as handoff:
        process = multiprocessing.get_context("fork").Process(target=worker, args=(handoff,))
        process.start()
        process.join(10)
        assert not process.is_alive() and process.exitcode == 73
    assert (directory / "ack.json").exists()
    assert not (directory / "result.json").exists()
    assert not (tmp_path / "unexpected-spawn").exists()
    with live.ownership_scope():
        monitor.tick()
    assert monitor.state["status"] == "USER_STOPPED"
    campaign = module.supervisor_recovery.campaign
    stop_path = campaign.ROOT / "user-stop.json"
    authorization = {"stop_sha256": "wrong", "contract": campaign.contract(),
                     "authorized_by": "user", "action": "explicit-resume"}
    write_json(campaign.ROOT / "resume-authorization.json", authorization)
    with live.ownership_scope():
        monitor.tick()
    assert monitor.state["status"] == "USER_STOPPED"
    write_json(campaign.ROOT / "resume-authorization.json",
               {**authorization, "stop_sha256": digest(stop_path.read_bytes())})
    monitor.config["maximum_worker_restarts"] = budget
    monkeypatch.setattr(module.implementation, "checked_request", lambda root, job: request)
    with live.ownership_scope():
        monitor.tick()
    assert monitor.state["status"] == ("RESUMING" if budget else "BLOCKED_BUDGET")
    assert monitor.state["sequence"] == 1
    assert (directory / "recovery.json").exists() is bool(budget)
