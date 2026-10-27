"""Deterministic ownership races and cold-process candidate supervision."""

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_inventory_history_live import clone_case, history, wait_for

from humanvoice.artifacts import read_json, write_json
from tools import durable_program_supervisor as durable
from tools import inventory_history_handover as handover
from tools.inventory_recovery_v3 import supervision


def configured(tmp_path, monkeypatch):
    live, module, monitor, _expected, _arguments = clone_case(tmp_path, monkeypatch)
    request = read_json(monitor.root / "jobs/job-0001/request.json")
    ack = {"owner": durable.identity(os.getpid()), "phase": request["phase"],
           "request_identity": durable.fingerprint(request),
           "ownership_protocol": "inherited-worker-lock-v1"}
    write_json(monitor.root / "jobs/job-0001/ack.json", ack)
    return live, module, monitor, request, ack


def upgrade(module, monitor):
    monitor.__class__ = supervision.monitor_class(
        module.InventoryMonitor, module.implementation, module.supervisor_recovery)
    return monitor


@pytest.mark.parametrize("missing", ["receipt", "head", "marker"])
def test_supervisor_lost_committed_restart_blocks_before_launch(tmp_path, monkeypatch, missing):
    live, module, monitor, _request, _ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    monkeypatch.setattr(durable, "alive", lambda owner: False)
    launches = []
    monkeypatch.setattr(monitor, "launch", lambda: launches.append(True))
    with live.ownership_scope():
        monitor.tick()
    assert monitor.state["worker_restarts"] == 1 and monitor.state["job"] is None
    receipt = monitor.state["worker_recovery"]
    path = {"receipt": monitor.root / "jobs/job-0001/recovery.json",
            "head": monitor.root / "restart-head.json",
            "marker": monitor.root / "restart-initialization.json"}[missing]
    path.unlink()
    with live.ownership_scope():
        monitor.tick()
    assert monitor.state["status"] == "BLOCKED_ACCOUNTING"
    assert monitor.state["worker_restarts"] == 1 and monitor.state["worker_recovery"] == receipt
    assert not launches and not path.exists()


@pytest.mark.parametrize("boundary", ["head-pending", "recovery.json", "head-committed", "state"])
def test_supervisor_pending_restart_reopens_once(tmp_path, monkeypatch, boundary):
    from test_inventory_recovery_v3_restart import publication_name

    from tools.inventory_recovery_v3 import restart_history

    live, module, monitor, _request, _ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    monkeypatch.setattr(durable, "alive", lambda owner: False)
    native = restart_history.persist

    def cut(path, value):
        native(path, value)
        if publication_name(path, value) == boundary:
            raise SystemExit(73)

    def notify(reason):
        raise SystemExit(73)

    with monkeypatch.context() as interrupted, live.ownership_scope():
        interrupted.setattr(restart_history, "persist", cut)
        if boundary == "state":
            interrupted.setattr(monitor, "notify", notify)
        with pytest.raises(SystemExit):
            monitor.tick()
    reopened = module.InventoryMonitor(monitor.root, monitor.config)
    upgrade(module, reopened)
    with live.ownership_scope():
        reopened.tick()
    assert reopened.state["status"] == "RESUMING"
    assert reopened.state["worker_restarts"] == 1
    assert len(restart_history.read(reopened)["committed"]) == 1
    assert read_json(reopened.root / "jobs/job-0001/recovery.json") == reopened.state["worker_recovery"]


@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("boundary", ["initialization-pending", "head-empty", "initialization-complete",
    "head-pending", "recovery.json", "head-committed", "state.json"])
def test_supervisor_disk_error_reopens_once_without_terminal_block(tmp_path, monkeypatch, boundary, after):
    from test_inventory_recovery_v3_restart import publication_name

    from tools.inventory_recovery_v3 import restart_history
    from tools.inventory_recovery_v3.failures import RecoveryStop

    live, module, monitor, _request, _ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    monkeypatch.setattr(durable, "alive", lambda owner: False)
    failures, launches = [], []
    native_persist, native_save = restart_history.persist, durable.save

    def inject(native, path, value):
        selected = (publication_name(path, value) == boundary and not failures
                    and (boundary != "state.json" or value.get("worker_restarts") == 1))
        if selected:
            failures.append(True)
            if not after:
                raise OSError("one-shot disk failure")
        native(path, value)
        if selected:
            raise OSError("one-shot disk failure")

    with monkeypatch.context() as interrupted, live.ownership_scope():
        interrupted.setattr(restart_history, "persist", lambda path, value: inject(native_persist, path, value))
        interrupted.setattr(durable, "save", lambda path, value: inject(native_save, path, value))
        monitor.tick()
    assert failures == [True]
    assert read_json(monitor.root / "state.json")["status"] != "BLOCKED_ENGINEERING"
    reopened = upgrade(module, module.InventoryMonitor(monitor.root, monitor.config))
    monkeypatch.setattr(reopened, "launch", lambda: launches.append(True))
    before = {str(path): path.read_bytes() for path in monitor.root.glob("restart-*.json")}

    def stopped():
        raise RecoveryStop("USER_STOPPED", "stop during storage recovery")

    with monkeypatch.context() as paused, live.ownership_scope():
        paused.setattr(module.supervisor_recovery.control, "require_running", stopped)
        reopened.tick()
    assert reopened.state["status"] == "USER_STOPPED" and not launches
    assert before == {str(path): path.read_bytes() for path in monitor.root.glob("restart-*.json")}
    with live.ownership_scope():
        reopened.tick()
    head = restart_history.read(reopened)
    assert reopened.state["worker_restarts"] == 1 and reopened.state["job"] is None
    assert len(head["committed"]) == 1 and head["pending"] is None
    retained = (monitor.root / "jobs/job-0001/recovery.json").read_bytes()
    with live.ownership_scope():
        reopened.tick()
    assert retained == (monitor.root / "jobs/job-0001/recovery.json").read_bytes()
    assert len(restart_history.read(reopened)["committed"]) == 1


@pytest.mark.parametrize("failures", [1, 4, 12])
def test_repeated_reporting_errors_reopen_without_losing_restart(tmp_path, monkeypatch, failures):
    from tools.inventory_recovery_v3 import restart_history

    live, module, monitor, _request, _ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    monkeypatch.setattr(durable, "alive", lambda owner: False)
    reporter = module.implementation.reporting.reporting
    native_save, attempts, launches = reporter.save, [], []

    def save(path, value):
        if Path(path).parent.name == "outbox" and len(attempts) < failures:
            attempts.append(True)
            raise OSError("finite outbox failure burst")
        return native_save(path, value)

    monkeypatch.setattr(reporter, "save", save)
    for _entry in range(failures + 3):
        monitor = upgrade(module, module.InventoryMonitor(monitor.root, monitor.config))
        monkeypatch.setattr(monitor, "launch", lambda: launches.append(True))
        with live.ownership_scope():
            monitor.tick()
        state = read_json(monitor.root / "state.json")
        assert state["status"] != "BLOCKED_ENGINEERING"
        assert state["worker_restarts"] == 1
        assert len(restart_history.read(monitor)["committed"]) == 1
        if launches:
            break
    assert len(attempts) == failures and launches == [True]
    assert state.get("reporting_intent") is None
    assert len(list((monitor.root / "reporting/outbox").glob("*.json"))) == 1


def test_persistent_reporting_fault_retains_intent_and_stop(tmp_path, monkeypatch):
    from tools.inventory_recovery_v3 import restart_history
    from tools.inventory_recovery_v3.failures import RecoveryStop

    live, module, monitor, _request, _ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    monkeypatch.setattr(durable, "alive", lambda owner: False)
    reporter = module.implementation.reporting.reporting
    native_save, launches = reporter.save, []

    def fail(path, value):
        if Path(path).parent.name == "outbox":
            raise OSError("outbox remains unavailable")
        return native_save(path, value)

    with monkeypatch.context() as broken:
        broken.setattr(reporter, "save", fail)
        with live.ownership_scope():
            monitor.tick()
        original = read_json(monitor.root / "state.json")["reporting_intent"]

        def stop():
            raise RecoveryStop("USER_STOPPED", "retained user stop")

        for _entry in range(3):
            monitor = upgrade(module, module.InventoryMonitor(monitor.root, monitor.config))
            monkeypatch.setattr(monitor, "launch", lambda: launches.append(True))
            with monkeypatch.context() as stopped, live.ownership_scope():
                stopped.setattr(module.supervisor_recovery.control, "require_running", stop)
                monitor.tick()
            assert read_json(monitor.root / "state.json")["reporting_intent"] == original
            assert not launches
    with monkeypatch.context() as stopped, live.ownership_scope():
        stopped.setattr(module.supervisor_recovery.control, "require_running", stop)
        monitor.tick()
    assert monitor.state["status"] == "USER_STOPPED" and not launches
    assert len(restart_history.read(monitor)["committed"]) == 1


def test_nonpublication_disk_error_stays_terminal(tmp_path, monkeypatch):
    live, module, monitor, _request, _ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    launches = []
    monkeypatch.setattr(monitor, "launch", lambda: launches.append(True))

    def fail(*arguments):
        raise OSError("unrelated evidence read failed")

    with monkeypatch.context() as interrupted, live.ownership_scope():
        interrupted.setattr(supervision, "acknowledgement", fail)
        monitor.tick()
    assert monitor.state["status"] == "BLOCKED_ENGINEERING"
    with live.ownership_scope():
        monitor.tick()
    assert monitor.state["status"] == "BLOCKED_ENGINEERING" and not launches
    assert not (monitor.root / "jobs/job-0001/recovery.json").exists()


@pytest.mark.parametrize("candidate", [False, True])
def test_live_to_dead_between_checks_with_inherited_lock(tmp_path, monkeypatch, candidate):
    live, module, monitor, request, _ack = configured(tmp_path, monkeypatch)
    observations = []

    def alive(owner):
        observations.append(owner)
        return len(observations) == 1

    monkeypatch.setattr(durable, "alive", alive)
    if candidate:
        upgrade(module, monitor)
    directory = monitor.root / "jobs/job-0001"
    with live.ownership_scope(), (directory / "worker.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monitor.tick()
        if not candidate:
            assert monitor.state["status"] == "BLOCKED_ENGINEERING"
            assert len(observations) == 2
            return
        assert len(observations) == 1
        assert monitor.state["status"] == "RUNNING"
        assert module.implementation.checked_request(monitor.root, "job-0001") == request
        monitor.tick()
        assert monitor.state["ownership_phase"] == "OBSERVING_OWNED_PROCESS"
        assert monitor.state["job"] == "job-0001"
        assert not (directory / "recovery.json").exists()
    with live.ownership_scope():
        monitor.tick()
        assert monitor.state["status"] == "RESUMING"
        assert monitor.state["worker_restarts"] == 1
        record = read_json(directory / "recovery.json")
        monitor.state.update(job="job-0001", status="RUNNING")
        monitor.publish()
        monitor.tick()
        assert read_json(directory / "recovery.json") == record
        assert monitor.state["worker_restarts"] == 1


@pytest.mark.parametrize("exit_code", [0, 1, -9])
def test_result_arrives_after_initial_read(tmp_path, monkeypatch, exit_code):
    live, module, monitor, request, ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    directory = monitor.root / "jobs/job-0001"
    result = {"owner": ack["owner"], "request_identity": durable.fingerprint(request),
              "exit_code": exit_code, "finished_at": time.time()}

    def alive(owner):
        write_json(directory / "result.json", result)
        return False

    monkeypatch.setattr(durable, "alive", alive)
    with live.ownership_scope():
        monitor.tick()
    if exit_code >= 0:
        assert not (directory / "recovery.json").exists()
        assert monitor.state["last_result"] == result
        assert monitor.state["phase"] == ("ADMITTING" if exit_code == 0 else "RUNNING")
    else:
        assert monitor.state["status"] == "RESUMING"
        assert monitor.state["worker_restarts"] == 1


@pytest.mark.parametrize("defect", ["ack_identity", "ack_protocol", "request", "heartbeat",
                                  "heartbeat_nan", "result_owner", "stop"])
def test_invalid_ownership_or_stop_never_launches(tmp_path, monkeypatch, defect):
    live, module, monitor, request, ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    directory = monitor.root / "jobs/job-0001"
    if defect.startswith("ack_"):
        ack["request_identity" if defect == "ack_identity" else "ownership_protocol"] = "foreign"
        write_json(directory / "ack.json", ack)
    elif defect == "request":
        write_json(directory / "request.json", {**request, "command": ["foreign"]})
    elif defect.startswith("heartbeat"):
        write_json(directory / "heartbeat.json", {"owner": ack["owner"],
                   "request_identity": "foreign" if defect == "heartbeat" else durable.fingerprint(request),
                   "at": float("nan") if defect == "heartbeat_nan" else time.time()})
    elif defect == "result_owner":
        write_json(directory / "result.json", {"owner": {}, "exit_code": 0,
                   "request_identity": durable.fingerprint(request)})
    else:
        module.supervisor_recovery.control.stop()
    with live.ownership_scope():
        monitor.tick()
    assert monitor.state["status"] == ("USER_STOPPED" if defect == "stop" else "BLOCKED_ENGINEERING")
    assert not (directory / "recovery.json").exists()
    assert monitor.state["sequence"] == 1


def configure_candidate_cold(root):
    from test_inventory_history_live import configure_cold

    from tools import inventory_history_live as live

    configure_cold(root)
    configuration = read_json(root / "fixture.json")
    if "worker" in sys.argv and (root / "hold-worker").exists():
        write_json(root / "worker-waiting.json", {"owner": durable.identity(os.getpid())})
        while not (root / "release-worker").exists():
            time.sleep(0.02)
    factory = live.supervisor

    def supervisor():
        module = factory()
        module.InventoryMonitor = supervision.monitor_class(
            module.InventoryMonitor, module.implementation, module.supervisor_recovery)
        module.implementation.InventoryMonitor = module.InventoryMonitor
        if configuration.get("handoff"):
            from tools.inventory_recovery_v3 import launcher

            def owner_check():
                live.require_admission()
                if live.ACTIVE_LEASE is None:
                    return False
                live.ACTIVE_LEASE.check(live.shared_locks())
                return True

            def spawn(command, **keywords):
                assert owner_check()
                descriptors = live.ACTIVE_LEASE.descriptors()
                keywords["pass_fds"] = tuple(sorted(set(keywords["pass_fds"]) | set(descriptors)))
                keywords["env"][handover.DESCRIPTORS] = json.dumps(descriptors)
                return subprocess.Popen(command, **keywords)

            def launch(monitor):
                return launcher.launch(monitor, module.implementation,
                    ["/home/ubuntu/miniforge3/bin/python", "-I", str(root / "launcher.py")],
                    spawn=spawn, owner_check=owner_check, stop_check=module.supervisor_recovery.control.require_running)

            def worker(job):
                return launcher.worker(module.implementation, job, spawn=live.launch_process,
                                       stop_check=module.supervisor_recovery.control.require_running)

            module.InventoryMonitor.launch = launch
            module.worker = worker
            module.implementation.worker = worker
        return module

    live.supervisor = supervisor


@pytest.mark.parametrize("cut", ["monitor", "pre_launcher", "pre_child_ack", "unpublished_worker",
                                 "handoff_monitor", "handoff_pre_child_ack", "handoff_unpublished"])
def test_candidate_cold_process_preserves_inherited_child(tmp_path, cut):
    from tools import inventory_history_live as live

    root, original, replacement, contract = history(tmp_path)
    (tmp_path / "stage").mkdir()
    command = ["/home/ubuntu/miniforge3/bin/python", "-I", str(tmp_path / "launcher.py")]
    expected = {**original, "maximum_repairs": 0, "maximum_worker_restarts": 15,
                "poll_seconds": 0.05, "acknowledgement_seconds": 0.2,
                "progress_files": [str(tmp_path / "stage/progress.json")],
                "run": command + ["campaign-execute"], "admission": command + ["campaign-verify"],
                "repair": command + ["campaign-repair"], "verify": command + ["campaign-verify"],
                "diagnose": command + ["status"]}
    unpublished = cut in {"unpublished_worker", "handoff_unpublished"}
    native_cut = "pre_launcher" if unpublished else cut.removeprefix("handoff_")
    write_json(tmp_path / "fixture.json", {"contract": contract, "config": expected,
               "old_config": original, "cut": native_cut, "handoff": cut.startswith("handoff_")})
    if unpublished:
        (tmp_path / "hold-worker").touch()
    write_json(tmp_path / "adoption.json", handover.proposal(root, original, replacement, contract))
    (tmp_path / "launcher.py").write_text(
        "import runpy, sys\nfrom pathlib import Path\n"
        f"sys.path[:0] = {[str(live.ROOT / 'tests'), str(live.ROOT), str(live.ROOT / 'src')]!r}\n"
        "from test_inventory_recovery_v3_supervision import configure_candidate_cold\n"
        f"configure_candidate_cold(Path({str(tmp_path)!r}))\n"
        f"runpy.run_path({str(Path(live.__file__).resolve())!r}, run_name='__main__')\n")
    processes = []
    child_owner = None
    try:
        with (tmp_path / "cold.log").open("wb") as log:
            first = subprocess.Popen(command + ["monitor"], stdout=log, stderr=log)
            processes.append(first)
            if unpublished:
                wait_for(lambda: (tmp_path / "worker-waiting.json").exists())
                wait_for(lambda: first.poll() is not None)
                assert not (replacement / "jobs/job-0001/ack.json").exists()
            else:
                wait_for(lambda: (tmp_path / "campaign-entered.json").exists())
                child_owner = read_json(tmp_path / "campaign-entered.json")["owner"]
            if first.poll() is None:
                first.kill()
            first.wait(5)
            restarted = subprocess.Popen(command + ["monitor"], stdout=log, stderr=log)
            processes.append(restarted)
            wait_for(lambda: read_json(replacement / "state.json").get("monitor_owner", {}).get("pid") == restarted.pid)
            if unpublished:
                expected_phase = "OBSERVING_OWNED_PROCESS" if cut == "handoff_unpublished" else "UNRESOLVED_LAUNCH_OWNERSHIP"
                wait_for(lambda: read_json(replacement / "state.json").get("ownership_phase") == expected_phase)
                assert not list(replacement.glob("jobs/*/recovery.json"))
                (tmp_path / "release-worker").touch()
                wait_for(lambda: (tmp_path / "campaign-entered.json").exists())
                child_owner = read_json(tmp_path / "campaign-entered.json")["owner"]
            state = read_json(replacement / "state.json")
            assert state["job"] == "job-0001" and state["sequence"] == 1
            assert state["status"] in {"RUNNING", "DISPATCHING"}
            assert not list(replacement.glob("jobs/*/recovery.json"))
            with (replacement / "jobs/job-0001/worker.lock").open("a") as held, pytest.raises(BlockingIOError):
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        (tmp_path / "release-worker").touch()
        (tmp_path / "release").touch()
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(5)
    if child_owner:
        wait_for(lambda: not durable.alive(child_owner))


@pytest.mark.parametrize("exit_code", [0, 1, -9])
def test_ack_and_result_appear_after_absent_ack_snapshot(tmp_path, monkeypatch, exit_code):
    live, module, monitor, request, ack = configured(tmp_path, monkeypatch)
    upgrade(module, monitor)
    directory = monitor.root / "jobs/job-0001"
    (directory / "ack.json").unlink()
    native_ack = supervision.acknowledgement
    observations = []
    result = {"owner": ack["owner"], "request_identity": durable.fingerprint(request),
              "exit_code": exit_code, "finished_at": time.time()}

    def interleave(folder, frozen):
        record = native_ack(folder, frozen)
        if not observations:
            assert record is None
            observations.append(True)
            write_json(folder / "ack.json", ack)
            write_json(folder / "result.json", result)
        return record

    monkeypatch.setattr(supervision, "acknowledgement", interleave)
    monkeypatch.setattr(durable, "alive", lambda owner: False)
    with live.ownership_scope():
        monitor.tick()
    if exit_code >= 0:
        assert monitor.state["last_result"] == result
        assert not (directory / "recovery.json").exists()
        assert "acknowledg" not in monitor.state.get("blocker", "")
    else:
        assert monitor.state["worker_restarts"] == 1
        assert monitor.state["status"] == "RESUMING"
