"""Real cold launch edges with offline processes and complete lock ownership."""

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import FunctionType, SimpleNamespace

import pytest
from test_inventory_recovery_v3_campaign_history import campaign
from test_inventory_recovery_v3_ownership import configured, derive

from humanvoice.artifacts import digest, read_json, write_json
from tools import durable_program_supervisor as durable
from tools import sol_inventory_supervisor_v2 as historical
from tools.inventory_recovery_v3 import (
    campaign_history,
    job_ownership,
    launch_handoff,
    launch_ownership,
    launcher,
    ownership,
    ownership_roles,
)
from tools.inventory_recovery_v3.failures import RecoveryStop


def wait_for(predicate, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("Cold ownership condition timed out")


def implementation(root):
    config = read_json(root / "fixture.json")
    supervision = Path(config["execution_authority"]["supervisor_root"])

    def immutable(path, value):
        if path.exists():
            assert read_json(path) == value
        else:
            write_json(path, value)

    namespace = {**historical.__dict__, "config": lambda: config}
    checked = FunctionType(historical.checked_request.__code__, namespace)
    return SimpleNamespace(config=lambda: config, OUTPUT=supervision, immutable=immutable, checked_request=checked)


def leaf(root):
    if (root / "stop").exists():
        raise RecoveryStop("USER_STOPPED", "offline explicit stop")
    return True


def fixture(tmp_path, cut="none"):
    config = configured(tmp_path)
    command = [sys.executable, "-I", str(tmp_path / "entry.py")]
    config.update(run=command + ["campaign"], admission=command + ["campaign"], poll_seconds=0.02)
    write_json(tmp_path / "fixture.json", config)
    write_json(tmp_path / "cut.json", {"cut": cut})
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "entry.py").write_text("import sys\nfrom pathlib import Path\n"
        f"sys.path[:0]={[str(root / 'tests'),str(root),str(root / 'src')]!r}\n"
        "from test_inventory_recovery_v3_launch_ownership import cold_entry\n"
        f"cold_entry(Path({str(tmp_path)!r}),sys.argv[1])\n")
    return config, command


def cold_entry(root, action):
    module = implementation(root)
    config = module.config()
    cut = read_json(root / "cut.json")["cut"]
    if action == "monitor":
        state = {"sequence": 0, "phase": "RUNNING", "status": "RUNNING",
                 "run_id": "cold-complete-union", "config_identity": durable.fingerprint(config)}
        monitor = SimpleNamespace(config=config, root=module.OUTPUT, state=state)
        monitor.publish = lambda: write_json(module.OUTPUT / "state.json", monitor.state)
        with ownership.acquire(derive(config), leaf=lambda: leaf(root)) as held:
            def spawn(*args, **kwargs):
                if cut == "missing":
                    kwargs["pass_fds"] = kwargs["pass_fds"][1:]
                elif cut == "legacy":
                    capsule = json.loads(kwargs["env"][launch_handoff.CAPSULE])
                    capsule["descriptor"] = kwargs["pass_fds"][0]
                    capsule["identity"] = digest({key: value for key, value in capsule.items() if key != "identity"})
                    kwargs["env"][launch_handoff.CAPSULE] = json.dumps(capsule)
                child = subprocess.Popen(*args, **kwargs)
                write_json(root / "worker-created.json", {"owner": durable.identity(child.pid)})
                return child

            launcher.launch(monitor, module, config["run"][:-1], spawn=spawn,
                owner_check=held.check, stop_check=lambda: leaf(root), lease=held, leaf=lambda: leaf(root))
            if cut in {"monitor", "pre_ack"}:
                os._exit(73)
            wait_for(lambda: (root / "release-monitor").exists())
    elif action == "worker":
        if cut == "pre_ack":
            write_json(root / "pre-ack.json", {"owner": durable.identity(os.getpid())})
            wait_for(lambda: (root / "release-worker").exists())
        with launch_ownership.entry(module, "job-0001", "worker", leaf=lambda: leaf(root)) as held:
            write_json(root / "worker-entered.json", {"owner": durable.identity(os.getpid()),
                "roles": [role.name for role in held.membership.roles]})
            if cut in {"ack_io", "heartbeat_io", "heartbeat_outage"}:
                original_save, failures = durable.save, []

                def save(path, value):
                    target = path.name == ("ack.json" if cut == "ack_io" else "heartbeat.json")
                    outage = cut == "heartbeat_outage" and not (root / "restore-reporting").exists()
                    if target and (cut != "ack_io" or value.get("child_owner")) and (not failures or outage):
                        wait_for(lambda: (root / "campaign-entered.json").exists())
                        failures.append(True)
                        write_json(root / "reporting-failure.json", {"injected": cut})
                        raise OSError(5, "offline transient reporting failure")
                    return original_save(path, value)

                durable.save = save

            def spawn(*args, **kwargs):
                if cut == "campaign_missing":
                    kwargs["pass_fds"] = kwargs["pass_fds"][1:]
                child = subprocess.Popen(*args, **kwargs)
                write_json(root / "campaign-created.json", {"owner": durable.identity(child.pid)})
                if cut == "worker":
                    os._exit(74)
                return child

            code = launcher.worker(module, "job-0001", spawn=spawn, stop_check=lambda: leaf(root),
                                   lease=held, leaf=lambda: leaf(root))
            raise SystemExit(code)
    else:
        with launch_ownership.entry(module, "job-0001", "campaign", leaf=lambda: leaf(root)) as held:
            request = module.checked_request(module.OUTPUT, "job-0001")
            assert job_ownership.require(module.OUTPUT, "job-0001", request)["descriptor"] == held.descriptor("job")
            history_root = Path(config["campaign_root"])
            current = campaign_history.CampaignHistory(history_root, read_json(history_root / "seed.json"),
                                                       check=held.check)
            with current.owned(descriptor=held.descriptor("campaign")):
                assert current.guard()
            write_json(root / "campaign-entered.json", {"owner": durable.identity(os.getpid()),
                "roles": [role.name for role in held.membership.roles],
                "descriptors": held.capsule()["pass_fds"]})
            if cut == "surviving_descendant":
                source = ("import time,sys\nfrom pathlib import Path\n"
                    "root=Path(sys.argv[1]);deadline=time.monotonic()+15\n"
                    "while not (root/'release-campaign').exists():\n"
                    " assert time.monotonic()<deadline;time.sleep(.02)\n"
                    "(root/'campaign-complete.json').write_text('{\"verified\":true}')\n")
                child = subprocess.Popen([sys.executable, "-I", "-c", source, str(root)],
                                         pass_fds=held.capsule()["pass_fds"])
                write_json(root / "descendant-created.json", {"owner": durable.identity(child.pid)})
                os._exit(0)
            wait_for(lambda: (root / "release-campaign").exists())
            assert held.check()
            write_json(root / "campaign-complete.json", {"verified": True})


def excluded(config, module):
    expected = ownership_roles.expected(config, "worker", job="job-0001", checked_request=module.checked_request)
    for role in expected.roles:
        with role.path.open("a") as competitor, pytest.raises(BlockingIOError):
            fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize("cut", ["none", "monitor", "worker", "pre_ack", "missing", "legacy",
                                 "campaign_missing", "ack_io", "heartbeat_io", "heartbeat_outage",
                                 "surviving_descendant"])
def test_real_launcher_edges_retain_complete_union_and_reject_omission(tmp_path, cut):
    config, command = fixture(tmp_path, cut)
    processes = []
    try:
        with (tmp_path / "monitor.log").open("wb") as log:
            monitor = subprocess.Popen(command + ["monitor"], stdout=log, stderr=log)
            processes.append(monitor)
            wait_for(lambda: (tmp_path / "worker-created.json").exists())
            module = implementation(tmp_path)
            if cut in {"missing", "legacy"}:
                worker = read_json(tmp_path / "worker-created.json")["owner"]
                wait_for(lambda: not durable.alive(worker))
                assert not (module.OUTPUT / "jobs/job-0001/ack.json").exists()
                assert not (tmp_path / "campaign-created.json").exists()
                (tmp_path / "release-monitor").touch()
                assert monitor.wait(10) == 0
                return
            if cut == "campaign_missing":
                wait_for(lambda: (module.OUTPUT / "jobs/job-0001/result.json").exists())
                assert read_json(module.OUTPUT / "jobs/job-0001/result.json")["exit_code"] != 0
                assert not (tmp_path / "campaign-entered.json").exists()
                (tmp_path / "release-monitor").touch()
                assert monitor.wait(10) == 0
                return
            if cut == "pre_ack":
                wait_for(lambda: (tmp_path / "pre-ack.json").exists())
                assert monitor.wait(10) == 73
                assert not (module.OUTPUT / "jobs/job-0001/ack.json").exists()
                excluded(config, module)
                (tmp_path / "release-worker").touch()
            wait_for(lambda: (tmp_path / "campaign-entered.json").exists())
            if cut == "surviving_descendant":
                wait_for(lambda: (tmp_path / "descendant-created.json").exists())
                leader = read_json(tmp_path / "campaign-created.json")["owner"]
                wait_for(lambda: not durable.alive(leader))
                assert durable.alive(read_json(tmp_path / "descendant-created.json")["owner"])
                assert not (module.OUTPUT / "jobs/job-0001/result.json").exists()
            if cut in {"ack_io", "heartbeat_io", "heartbeat_outage"}:
                wait_for(lambda: (tmp_path / "reporting-failure.json").exists())
                ack_path = module.OUTPUT / "jobs/job-0001/ack.json"
                wait_for(lambda: read_json(ack_path).get("reporting_failures", 0) >= (3 if cut == "heartbeat_outage" else 1))
                assert durable.alive(read_json(tmp_path / "campaign-entered.json")["owner"])
                assert not (module.OUTPUT / "jobs/job-0001/result.json").exists()
                if cut == "heartbeat_outage":
                    excluded(config, module)
                    (tmp_path / "restore-reporting").touch()
                    wait_for(lambda: (module.OUTPUT / "jobs/job-0001/heartbeat.json").exists())
            if cut == "monitor":
                assert monitor.wait(10) == 73
            elif cut == "worker":
                worker = read_json(tmp_path / "worker-entered.json")["owner"]
                wait_for(lambda: not durable.alive(worker))
                (tmp_path / "release-monitor").touch()
                assert monitor.wait(10) == 0
            excluded(config, module)
            (tmp_path / "release-campaign").touch()
            wait_for(lambda: (tmp_path / "campaign-complete.json").exists())
            (tmp_path / "release-monitor").touch()
            if monitor.poll() is None:
                assert monitor.wait(10) == 0
            if cut != "worker":
                result = wait_for(lambda: (module.OUTPUT / "jobs/job-0001/result.json").exists())
                assert result
                assert read_json(module.OUTPUT / "jobs/job-0001/result.json")["exit_code"] == 0
    finally:
        for name in ("release-campaign", "release-worker", "release-monitor"):
            (tmp_path / name).touch()
        for name in ("descendant-created.json", "campaign-created.json", "worker-created.json"):
            if (tmp_path / name).exists():
                owner = read_json(tmp_path / name)["owner"]
                if durable.alive(owner):
                    try:
                        os.kill(owner["pid"], 9)
                    except ProcessLookupError:
                        pass
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(10)


@pytest.mark.parametrize("edge", ["monitor", "worker"])
def test_actual_launcher_final_stop_after_log_setup_vetoes_spawn(tmp_path, monkeypatch, edge):
    config, command = fixture(tmp_path)
    module = implementation(tmp_path)
    state = {"sequence": 0, "phase": "RUNNING", "status": "RUNNING",
             "run_id": "final-veto", "config_identity": durable.fingerprint(config)}
    monitor = SimpleNamespace(config=config, root=module.OUTPUT, state=state)
    monitor.publish = lambda: write_json(module.OUTPUT / "state.json", state)
    native_open, fired, spawned = Path.open, [], []
    with ownership.acquire(derive(config), leaf=lambda: leaf(tmp_path)) as held:
        if edge == "monitor":
            target = module.OUTPUT / "workers.log"
        else:
            # Obtain a real durable intent and complete child union without
            # invoking a process; duplicate the explicit transfer references.
            def retain(args, **kwargs):
                capsule = json.loads(kwargs["env"][ownership.CAPSULE])
                mapping = {fd: os.dup(fd) for fd in kwargs["pass_fds"]}
                for row in capsule["descriptors"]:
                    row["descriptor"] = mapping[row["descriptor"]]
                capsule["identity"] = digest({key: value for key, value in capsule.items() if key != "identity"})
                legacy = json.loads(kwargs["env"][launch_handoff.CAPSULE])
                legacy["descriptor"] = mapping[legacy["descriptor"]]
                legacy["identity"] = digest({key: value for key, value in legacy.items() if key != "identity"})
                monkeypatch.setenv(ownership.CAPSULE, json.dumps(capsule))
                monkeypatch.setenv(launch_handoff.CAPSULE, json.dumps(legacy))
                monkeypatch.setenv(launch_ownership.RECEIVED, json.dumps(list(mapping.values())))
                return SimpleNamespace(pid=os.getpid())

            launcher.launch(monitor, module, command, spawn=retain, owner_check=held.check,
                            stop_check=lambda: leaf(tmp_path), lease=held, leaf=lambda: leaf(tmp_path))
            target = module.OUTPUT / "jobs/job-0001/output.log"

        def open_file(path, *args, **kwargs):
            result = native_open(path, *args, **kwargs)
            if path == target and not fired:
                fired.append(True)
                (tmp_path / "stop").touch()
            return result

        def spawn(*args, **kwargs):
            spawned.append(True)
            raise AssertionError("Spawn after final stop")

        monkeypatch.setattr(Path, "open", open_file)
        with pytest.raises(RecoveryStop) as stopped:
            if edge == "monitor":
                launcher.launch(monitor, module, command, spawn=spawn, owner_check=held.check,
                    stop_check=lambda: leaf(tmp_path), lease=held, leaf=lambda: leaf(tmp_path))
            else:
                with launch_ownership.entry(module, "job-0001", "worker", leaf=lambda: leaf(tmp_path)) as worker:
                    launcher.worker(module, "job-0001", spawn=spawn, stop_check=lambda: leaf(tmp_path),
                                    lease=worker, leaf=lambda: leaf(tmp_path))
        assert stopped.value.category == "USER_STOPPED"
        assert fired and not spawned
        assert not (module.OUTPUT / "jobs/job-0001/result.json").exists()


@pytest.mark.parametrize("key", launch_ownership.ENVIRONMENT_KEYS)
def test_fallback_monitor_rejects_ambient_capsules_before_dispatch(tmp_path, monkeypatch, key):
    config, command = fixture(tmp_path)
    module = implementation(tmp_path)
    monitor = SimpleNamespace(config=config, root=module.OUTPUT, state={"sequence": 0})
    monkeypatch.setenv(key, "stale-capsule")
    calls = []
    with pytest.raises(RecoveryStop, match="ambient ownership"):
        launcher.launch(monitor, module, command, spawn=lambda *args, **kw: calls.append(True),
                        owner_check=lambda: True, stop_check=lambda: None)
    assert not calls and monitor.state == {"sequence": 0}
    assert not (module.OUTPUT / "jobs").exists()


@pytest.mark.parametrize("defect", ["duplicate", "row", "fd_type", "not_json"])
def test_entry_malformed_rows_close_explicit_inventory_once(tmp_path, monkeypatch, defect):
    config, command = fixture(tmp_path)
    module = implementation(tmp_path)
    state = {"sequence": 0, "phase": "RUNNING", "status": "RUNNING",
             "run_id": "malformed-entry", "config_identity": durable.fingerprint(config)}
    monitor = SimpleNamespace(config=config, root=module.OUTPUT, state=state)
    monitor.publish = lambda: write_json(module.OUTPUT / "state.json", state)
    received = []
    with ownership.acquire(derive(config), leaf=lambda: True) as parent:
        def retain(args, **kwargs):
            capsule = json.loads(kwargs["env"][ownership.CAPSULE])
            mapping = {fd: os.dup(fd) for fd in kwargs["pass_fds"]}
            received.extend(mapping.values())
            for row in capsule["descriptors"]:
                row["descriptor"] = mapping[row["descriptor"]]
            legacy = json.loads(kwargs["env"][launch_handoff.CAPSULE])
            legacy["descriptor"] = mapping[legacy["descriptor"]]
            legacy["identity"] = digest({key: value for key, value in legacy.items() if key != "identity"})
            if defect == "duplicate":
                capsule["descriptors"].append(dict(capsule["descriptors"][0]))
            elif defect == "row":
                capsule["descriptors"][0] = None
            elif defect == "fd_type":
                capsule["descriptors"][0]["descriptor"] = str(capsule["descriptors"][0]["descriptor"])
            capsule["identity"] = digest({key: value for key, value in capsule.items() if key != "identity"})
            monkeypatch.setenv(ownership.CAPSULE, "{broken" if defect == "not_json" else json.dumps(capsule))
            monkeypatch.setenv(launch_handoff.CAPSULE, json.dumps(legacy))
            monkeypatch.setenv(launch_ownership.RECEIVED, json.dumps(received))
            return SimpleNamespace(pid=os.getpid())

        launcher.launch(monitor, module, command, spawn=retain, owner_check=parent.check,
                        stop_check=lambda: True, lease=parent, leaf=lambda: True)
        with pytest.raises((RecoveryStop, ValueError)), launch_ownership.entry(
                module, "job-0001", "worker", leaf=lambda: True):
            pytest.fail("Malformed entry admitted")
        for fd in received:
            with pytest.raises(OSError):
                os.fstat(fd)
        sentinels = []
        try:
            # The parent launch scopes released other numbers too. Explicitly
            # duplicate sentinel ownership onto the formerly incoming tuple.
            for fd in received:
                source = os.open(tmp_path / "sentinel", os.O_CREAT | os.O_RDWR, 0o600)
                if source != fd:
                    os.dup2(source, fd)
                    os.close(source)
                sentinels.append(fd)
            with pytest.raises(RecoveryStop, match="already consumed"), launch_ownership.entry(
                    module, "job-0001", "worker", leaf=lambda: True):
                pytest.fail("Malformed retired entry replayed")
            assert all(os.fstat(fd).st_ino == (tmp_path / "sentinel").stat().st_ino for fd in sentinels)
            assert parent.check()
        finally:
            ownership.close_all(sentinels)
