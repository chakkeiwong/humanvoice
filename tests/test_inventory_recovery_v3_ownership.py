"""Offline role/lifetime component tests; no public launch permission."""

import fcntl
import json
import multiprocessing
import os
import select
import signal
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

import pytest

from humanvoice.artifacts import digest, write_json
from tools import durable_program_supervisor as durable
from tools.inventory_recovery_v3 import ownership
from tools.inventory_recovery_v3 import ownership_roles as roles
from tools.inventory_recovery_v3.failures import RecoveryStop


def configured(tmp_path):
    root = tmp_path / "supervision"
    campaign = tmp_path / "campaign"
    old = [tmp_path / "old0", tmp_path / "old1"]
    config = {"fixture": "ownership-component-only", "cwd": str(tmp_path),
        "run": ["offline-run"], "admission": ["offline-verify"],
        "campaign_root": str(campaign), "execution_authority": {
            "program_base": str(tmp_path), "supervisor_root": str(root)},
        "handover": {"replacement": str(root), "records": [
            {"predecessor": {"root": str(old[0]), "jobs": ["job-0001"]},
             "replacement": str(old[1])},
            {"predecessor": {"root": str(old[1]), "jobs": []}, "replacement": str(root)}],
            "installed": {"shared_locks": [str(tmp_path / "active-session-program.lock"),
                str(tmp_path / "sealed/executor.lock"), str(tmp_path / "sealed/execution.lock")]}}}
    for directory in (root, campaign, old[0] / "jobs/job-0001", old[1], tmp_path / "sealed"):
        directory.mkdir(parents=True)
    return config


def add_job(config, name="job-0001"):
    root = Path(config["execution_authority"]["supervisor_root"])
    directory = root / "jobs" / name
    directory.mkdir(parents=True)
    request = {"job_id": name, "phase": "RUNNING", "command": config["run"],
        "cwd": config["cwd"], "run_id": "component", "config_identity": durable.fingerprint(config)}
    write_json(directory / "request.json", request)
    return lambda selected_root, job: deepcopy(request)


def derive(config, role="monitor", **kwargs):
    return lambda: roles.expected(config, role, **kwargs)


def record(lease):
    return json.loads(lease.capsule()["environment"][ownership.CAPSULE])


def rehash(value):
    value["identity"] = digest({key: item for key, item in value.items() if key != "identity"})
    return value


def assert_available(membership):
    for role in membership.roles:
        with role.path.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_production_shaped_roles_acquire_program_once_in_fixed_order(tmp_path, monkeypatch):
    config = configured(tmp_path)
    expected = roles.expected(config, "monitor")
    assert [role.name for role in expected.roles] == ["predecessor:0:monitor",
        "predecessor:0:job-0001", "predecessor:1:monitor",
        "historical:3:execution.lock", "historical:4:executor.lock", "program", "campaign", "monitor"]
    native, trace = fcntl.flock, []

    def lock(fd, mode):
        assert mode == fcntl.LOCK_EX | fcntl.LOCK_NB
        trace.append(Path(os.readlink(f"/proc/self/fd/{fd}")))
        return native(fd, mode)

    monkeypatch.setattr(fcntl, "flock", lock)
    with ownership.acquire(derive(config), leaf=lambda: True) as lease:
        assert lease.check()
        assert trace == [role.path for role in expected.roles]
        assert len(lease.capsule()["pass_fds"]) == len(expected.roles)
    assert trace.count(tmp_path / "active-session-program.lock") == 1


@pytest.mark.parametrize("defect", ["program_missing", "program_duplicate", "stage_missing", "unknown",
                                     "chain", "job_duplicate", "alias", "symlink", "inode"])
def test_role_mapping_rejects_resource_conflicts(tmp_path, defect):
    config = configured(tmp_path)
    shared = config["handover"]["installed"]["shared_locks"]
    if defect == "program_missing":
        shared.pop(0)
    elif defect == "program_duplicate":
        shared.append(shared[0])
    elif defect == "stage_missing":
        shared.pop()
    elif defect == "unknown":
        shared.append(str(tmp_path / "unrecognized.lock"))
    elif defect == "chain":
        config["handover"]["records"][0]["replacement"] = str(tmp_path)
    elif defect == "job_duplicate":
        config["handover"]["records"][0]["predecessor"]["jobs"] *= 2
    elif defect == "alias":
        shared[0] = str(tmp_path) + "/../" + tmp_path.name + "/active-session-program.lock"
    elif defect == "symlink":
        (tmp_path / "active-session-program.lock").symlink_to(tmp_path / "missing")
    else:
        program = tmp_path / "active-session-program.lock"
        program.touch()
        os.link(program, tmp_path / "campaign/campaign.lock")
    with pytest.raises(ValueError):
        roles.expected(config, "monitor")


@pytest.mark.parametrize("boundary", range(18))
def test_veto_at_every_acquisition_prefix_unwinds_all_references(tmp_path, boundary):
    config = configured(tmp_path)
    expected = roles.expected(config, "monitor")
    calls = 0

    def leaf():
        nonlocal calls
        current = calls
        calls += 1
        return current != boundary

    with pytest.raises(RecoveryStop), ownership.acquire(derive(config), leaf=leaf):
        pytest.fail("Vetoed prefix became active")
    assert_available(expected)


def test_busy_late_lock_releases_prefix_and_preserves_competitor(tmp_path):
    config = configured(tmp_path)
    expected = roles.expected(config, "monitor")
    with expected.roles[-1].path.open("a") as competitor:
        fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError), ownership.acquire(derive(config), leaf=lambda: True):
            pytest.fail("Competing monitor admitted")
        for role in expected.roles[:-1]:
            with role.path.open("a") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert ownership.exclusive_descriptor(expected.roles[-1].path, competitor.fileno())


def test_borrowed_inheritance_remaps_every_role_without_locking_or_closing_parent(tmp_path, monkeypatch):
    config = configured(tmp_path)
    with ownership.acquire(derive(config), leaf=lambda: True) as parent:
        capsule = record(parent)
        before = parent.capsule()["pass_fds"]

        def forbid(*args):
            pytest.fail("Borrowed ownership mutated a lock")

        monkeypatch.setattr(fcntl, "flock", forbid)
        with ownership.inherit(derive(config), capsule, leaf=lambda: True) as child:
            after = child.capsule()["pass_fds"]
            assert set(before).isdisjoint(after)
            assert child.check() and parent.check()
        assert parent.check()
    with pytest.raises(RecoveryStop):
        child.check()


@pytest.mark.parametrize("defect", ["missing", "extra", "duplicate", "swapped", "fresh", "unlocked",
                                     "path", "inode", "configuration", "pid"])
def test_inherited_capsule_rejects_corruption_without_mutation(tmp_path, defect):
    config = configured(tmp_path)
    with ownership.acquire(derive(config), leaf=lambda: True) as parent:
        capsule = record(parent)
        rows = capsule["descriptors"]
        extra = None
        if defect == "missing":
            rows.pop()
        elif defect == "extra":
            rows.append(deepcopy(rows[-1]))
        elif defect == "duplicate":
            rows[1]["descriptor"] = rows[0]["descriptor"]
        elif defect == "swapped":
            rows.reverse()
        elif defect == "fresh":
            extra = os.open(rows[0]["path"], os.O_RDWR)
            rows[0]["descriptor"] = extra
        elif defect == "unlocked":
            fcntl.flock(rows[0]["descriptor"], fcntl.LOCK_UN)
        elif defect == "path":
            rows[0]["path"] = rows[1]["path"]
        elif defect == "inode":
            rows[0]["inode"] += 1
        elif defect == "configuration":
            capsule["membership"]["configuration"] = "other"
        else:
            capsule["issuer"]["pid"] = True
        rehash(capsule)
        try:
            with pytest.raises((ValueError, RecoveryStop)), ownership.inherit(
                    derive(config), capsule, leaf=lambda: True):
                pytest.fail("Corrupt inherited union accepted")
            if defect != "unlocked":
                assert parent.check()
        finally:
            if extra is not None:
                os.close(extra)


@pytest.mark.parametrize("replay_leaf", [True, False])
def test_entrypoint_closes_originals_and_rejects_replayed_capsule(tmp_path, replay_leaf):
    config = configured(tmp_path)
    with ownership.acquire(derive(config), leaf=lambda: True) as parent:
        capsule = record(parent)
        received = tuple(os.dup(row["descriptor"]) for row in capsule["descriptors"])
        for row, fd in zip(capsule["descriptors"], received):
            row["descriptor"] = fd
        rehash(capsule)
        with ownership.inherit(derive(config), capsule, leaf=lambda: True, received=received) as child:
            for fd in received:
                with pytest.raises(OSError):
                    os.fstat(fd)
            assert child.check() and parent.check()
            with ownership.inherit(derive(config), record(child), leaf=lambda: True) as survivor:
                assert survivor.capsule()["pass_fds"] == received
                child.close()
                parent.close()
                with pytest.raises(RecoveryStop, match="already consumed"), ownership.inherit(
                        derive(config), capsule, leaf=lambda: replay_leaf, received=received):
                    pytest.fail("Consumed capsule reopened")
                assert survivor.check()
                assert survivor.capsule()["pass_fds"] == received
                for role in survivor.membership.roles:
                    with role.path.open("a") as competitor, pytest.raises(BlockingIOError):
                        fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            assert_available(roles.expected(config, "monitor"))


@pytest.mark.parametrize("which", ["leaf", "membership", "duplicate", "derive", "malformed"])
def test_entrypoint_rejection_closes_only_explicit_incoming_references(tmp_path, which):
    config = configured(tmp_path)
    with ownership.acquire(derive(config), leaf=lambda: True) as parent:
        capsule = record(parent)
        received = tuple(os.dup(row["descriptor"]) for row in capsule["descriptors"])
        for row, fd in zip(capsule["descriptors"], received):
            row["descriptor"] = fd
        if which == "membership":
            capsule["membership"]["role"] = "provider"
        elif which == "duplicate":
            capsule["descriptors"][1]["descriptor"] = received[0]
        rehash(capsule)
        if which == "malformed":
            capsule = [capsule]

        def failed_derive():
            raise ValueError("offline derivation failure")

        with pytest.raises((RecoveryStop, ValueError)), ownership.inherit(
                failed_derive if which == "derive" else derive(config), capsule,
                leaf=lambda: which != "leaf", received=received):
            pytest.fail("Invalid entrypoint accepted")
        for fd in received:
            with pytest.raises(OSError):
                os.fstat(fd)
        assert parent.check()
        restored = tuple(os.dup(fd) for fd in parent.capsule()["pass_fds"])
        assert restored == received
        try:
            with pytest.raises(RecoveryStop, match="already consumed"), ownership.inherit(
                    derive(config), capsule, leaf=lambda: True, received=received):
                pytest.fail("Rejected transfer became reusable")
            for role, fd in zip(parent.membership.roles, restored):
                assert ownership.exclusive_descriptor(role.path, fd)
            assert parent.check()
        finally:
            ownership.close_all(restored)


def test_stale_entry_cleanup_cannot_close_unrelated_reused_descriptors(tmp_path):
    config = configured(tmp_path)
    with ownership.acquire(derive(config), leaf=lambda: True) as parent:
        capsule = record(parent)
        received = tuple(os.dup(row["descriptor"]) for row in capsule["descriptors"])
        for row, fd in zip(capsule["descriptors"], received):
            row["descriptor"] = fd
        rehash(capsule)
        with ownership.inherit(derive(config), capsule, leaf=lambda: True, received=received):
            sentinels = tuple(os.open(tmp_path / "sentinel", os.O_CREAT | os.O_RDWR, 0o600) for _ in received)
            assert sentinels == received
            try:
                with pytest.raises(RecoveryStop, match="already consumed"), ownership.inherit(
                        derive(config), capsule, leaf=lambda: False, received=received):
                    pytest.fail("Stale transfer was accepted")
                assert all(os.fstat(fd).st_ino == (tmp_path / "sentinel").stat().st_ino for fd in sentinels)
            finally:
                ownership.close_all(sentinels)
        assert parent.check()


def test_incoming_callback_failure_retires_transfer_before_any_lease(tmp_path):
    config = configured(tmp_path)
    with ownership.acquire(derive(config), leaf=lambda: True) as parent:
        capsule = record(parent)
        received = tuple(os.dup(row["descriptor"]) for row in capsule["descriptors"])
        for row, fd in zip(capsule["descriptors"], received):
            row["descriptor"] = fd
        rehash(capsule)
        calls = []

        def reject():
            calls.append(True)
            raise ValueError("incoming legacy proof rejected")

        with pytest.raises(ValueError, match="incoming legacy proof"), ownership.inherit(
                derive(config), capsule, leaf=lambda: True, received=received, incoming_check=reject):
            pytest.fail("Invalid legacy proof activated")
        assert calls == [True]
        for fd in received:
            with pytest.raises(OSError):
                os.fstat(fd)
        restored = tuple(os.dup(fd) for fd in parent.capsule()["pass_fds"])
        assert restored == received
        try:
            with pytest.raises(RecoveryStop, match="already consumed"), ownership.inherit(
                    derive(config), capsule, leaf=lambda: True, received=received, incoming_check=reject):
                pytest.fail("Rejected incoming callback was retried")
            assert calls == [True]
            assert all(os.fstat(fd) for fd in restored)
        finally:
            ownership.close_all(restored)


def test_extensions_preserve_union_and_reject_changed_or_retired_job(tmp_path):
    config = configured(tmp_path)
    checked = add_job(config)
    child = derive(config, "worker", job="job-0001", checked_request=checked)
    campaign = derive(config, "campaign", job="job-0001", checked_request=checked)
    with ownership.acquire(derive(config), leaf=lambda: True) as monitor:
        with ownership.extend(monitor, child, leaf=lambda: True) as worker:
            assert len(worker.capsule()["pass_fds"]) == len(monitor.capsule()["pass_fds"]) + 1
            with ownership.extend(worker, campaign, leaf=lambda: True) as active:
                assert [row["role"] for row in record(active)["descriptors"]][-1] == "job"
                assert active.check()
            write_json(Path(config["execution_authority"]["supervisor_root"]) / "jobs/job-0001/result.json", {})
            with pytest.raises(ValueError):
                worker.check()
        assert monitor.check()


@pytest.mark.parametrize("defect", ["pending", "swapped", "sealed", "changed"])
def test_stage_roles_require_current_committed_plan(tmp_path, defect):
    from test_inventory_recovery_v3_campaign_history import campaign

    config = configured(tmp_path)
    checked = add_job(config)
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
    output = current.root / "generation-00"
    plan = {"plan_identity": "initial", "fixture": "offline"}
    write_json(output / "plan.json", plan)
    args = {"job": "job-0001", "checked_request": checked,
            "history": current, "stage": {"output": str(output), "plan": plan}}
    valid = roles.expected(config, "provider", **args)
    assert [item.name for item in valid.roles][-3:] == ["job", "execution", "executor"]
    if defect == "pending":
        from test_inventory_recovery_v3_campaign_history import transition

        with current.owned():
            current.begin(transition(current))
    elif defect == "swapped":
        args["stage"]["output"] = str(current.root / "generation-01")
    elif defect == "sealed":
        write_json(output / "allocation-seal.json", {})
    else:
        write_json(output / "plan.json", {**plan, "changed": True})
    with pytest.raises(ValueError):
        roles.expected(config, "provider", **args)


def test_live_lease_cannot_be_used_in_forked_process(tmp_path):
    config = configured(tmp_path)
    with ownership.acquire(derive(config), leaf=lambda: True) as parent:
        def child():
            try:
                parent.check()
            except RecoveryStop:
                os._exit(0)
            os._exit(91)

        process = multiprocessing.get_context("fork").Process(target=child)
        process.start()
        process.join(10)
        if process.is_alive():
            process.kill()
            process.join(10)
        assert process.exitcode == 0
        assert parent.check()


@pytest.mark.parametrize("borrowed", [False, True])
def test_full_provider_union_and_real_campaign_consumer(tmp_path, monkeypatch, borrowed):
    from contextlib import ExitStack

    from test_inventory_recovery_v3_campaign_history import campaign

    config = configured(tmp_path)
    checked = add_job(config)
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
    output = current.root / "generation-00"
    plan = {"plan_identity": "initial", "fixture": "offline"}
    write_json(output / "plan.json", plan)
    job_args = {"job": "job-0001", "checked_request": checked}
    stage_args = {**job_args, "history": current, "stage": {"output": str(output), "plan": plan}}
    with ExitStack() as stack:
        monitor = stack.enter_context(ownership.acquire(derive(config), leaf=lambda: True))
        worker = stack.enter_context(ownership.extend(monitor, derive(config, "worker", **job_args),
                                                       leaf=lambda: True))
        active = stack.enter_context(ownership.extend(worker, derive(config, "campaign", **job_args),
                                                       leaf=lambda: True))
        owned = {}
        if borrowed:
            for name in ("execution", "executor"):
                handle = stack.enter_context((output / (name + ".lock")).open("a"))
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                owned[name] = handle.fileno()

            def forbid(*args):
                pytest.fail("Borrowed provider or campaign lock was relocked")

            monkeypatch.setattr(fcntl, "flock", forbid)
        with current.owned(descriptor=active.descriptor("campaign")):
            assert current.guard()
        with ownership.extend(active, derive(config, "provider", **stage_args),
                              leaf=lambda: True, borrowed=owned) as provider:
            assert provider.check() and active.check()
            assert len(provider.capsule()["pass_fds"]) == len(monitor.capsule()["pass_fds"]) + 3
            assert provider.descriptor("executor") != owned.get("executor")
        for name, fd in owned.items():
            assert ownership.exclusive_descriptor(output / (name + ".lock"), fd)
        assert active.check()


def test_successive_jobs_retain_base_and_cannot_swap_live_job(tmp_path):
    config = configured(tmp_path)
    first, second = add_job(config), add_job(config, "job-0002")
    with ownership.acquire(derive(config), leaf=lambda: True) as monitor:
        with ownership.extend(monitor, derive(config, "worker", job="job-0001",
                checked_request=first), leaf=lambda: True) as worker:
            with pytest.raises(RecoveryStop), ownership.extend(worker, derive(config, "campaign",
                    job="job-0002", checked_request=second), leaf=lambda: True):
                pytest.fail("Live ancestor job swapped")
            assert worker.check()
        with ownership.extend(monitor, derive(config, "worker", job="job-0002",
                checked_request=second), leaf=lambda: True) as worker:
            assert worker.check()
        assert monitor.check()


@pytest.mark.parametrize("failure", ["dup", "leaf"])
def test_partial_inheritance_failure_closes_duplicates_preserving_parent(tmp_path, monkeypatch, failure):
    config = configured(tmp_path)
    with ownership.acquire(derive(config), leaf=lambda: True) as parent:
        capsule = record(parent)
        duplicated, calls = [], []
        native_dup = os.dup

        def duplicate(fd):
            if len(duplicated) == 3 and failure == "dup":
                raise OSError("offline descriptor exhaustion")
            result = native_dup(fd)
            duplicated.append(result)
            return result

        def leaf():
            calls.append(True)
            return not (failure == "leaf" and len(duplicated) == 3)

        monkeypatch.setattr(os, "dup", duplicate)
        with pytest.raises((OSError, RecoveryStop)), ownership.inherit(derive(config), capsule, leaf=leaf):
            pytest.fail("Partial descriptor copy activated")
        assert len(duplicated) == 3
        for fd in duplicated:
            with pytest.raises(OSError):
                os.fstat(fd)
        assert parent.check()


@pytest.mark.parametrize("child_role", ["monitor", "worker", "campaign", "provider"])
def test_complete_union_survives_parent_death_until_grandchild_finishes(tmp_path, child_role):
    from contextlib import ExitStack

    from test_inventory_recovery_v3_campaign_history import campaign

    config = configured(tmp_path)
    checked = add_job(config)
    current = campaign(tmp_path)
    with current.owned():
        current.initialize()
    output = current.root / "generation-00"
    plan = {"plan_identity": "initial", "fixture": "offline"}
    write_json(output / "plan.json", plan)
    job_args = {"job": "job-0001", "checked_request": checked}
    stage_args = {**job_args, "history": current, "stage": {"output": str(output), "plan": plan}}
    config_path = tmp_path / "configuration.json"
    write_json(config_path, config)
    ready_read, ready_write = os.pipe()
    signal_read, signal_write = os.pipe()
    root = Path(__file__).resolve().parents[1]
    source = ("import json,os,sys\nfrom pathlib import Path\n"
        f"sys.path[:0]={[str(root),str(root / 'src')]!r}\n"
        "from humanvoice.artifacts import read_json\n"
        "from tools.inventory_recovery_v3 import ownership,ownership_roles,campaign_history\n"
        "path,ready,signal=sys.argv[1:];ready,signal=int(ready),int(signal)\n"
        "config=json.loads(Path(path).read_text());capsule=json.loads(os.environ[ownership.CAPSULE])\n"
        "received=tuple(row['descriptor'] for row in capsule['descriptors'])\n"
        f"role={child_role!r};args={{}}\n"
        "if role!='monitor':args={'job':'job-0001','checked_request':lambda root,job:read_json(root/'jobs'/job/'request.json')}\n"
        "if role=='provider':\n"
        " root=Path(config['campaign_root']);history=campaign_history.CampaignHistory(root,read_json(root/'seed.json'),check=lambda:True)\n"
        " output=root/'generation-00';args.update(history=history,stage={'output':str(output),'plan':read_json(output/'plan.json')})\n"
        "os.write(ready,(str(os.getpid())+'\\n').encode());assert os.read(signal,1)==b'v'\n"
        "with ownership.inherit(lambda:ownership_roles.expected(config,role,**args),capsule,leaf=lambda:True,received=received) as lease:\n"
        " assert lease.check();os.write(ready,b'verified\\n');assert os.read(signal,1)==b'r';assert lease.check()\n"
        "os.write(ready,b'complete\\n');os.close(ready);os._exit(0)\n")

    def parent():
        os.close(ready_read)
        os.close(signal_write)
        with ExitStack() as stack:
            lease = stack.enter_context(ownership.acquire(derive(config), leaf=lambda: True))
            for role in ("worker", "campaign", "provider"):
                if lease.membership.role == child_role:
                    break
                lease = stack.enter_context(ownership.extend(lease,
                    derive(config, role, **(stage_args if role == "provider" else job_args)), leaf=lambda: True))
            options = lease.capsule()
            subprocess.Popen([sys.executable, "-I", "-c", source, str(config_path), str(ready_write), str(signal_read)],
                pass_fds=(*options["pass_fds"], ready_write, signal_read),
                env={**os.environ, **options["environment"]}, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os._exit(73)

    def message():
        result, deadline = b"", time.monotonic() + 10
        while not result.endswith(b"\n"):
            assert select.select([ready_read], [], [], max(0, deadline - time.monotonic()))[0]
            part = os.read(ready_read, 1)
            assert part, "Child ownership verification failed"
            result += part
            assert len(result) <= 128
        return result.strip()

    process, child = multiprocessing.get_context("fork").Process(target=parent), None
    try:
        process.start()
        os.close(ready_write)
        os.close(signal_read)
        process.join(10)
        assert process.exitcode == 73
        child = durable.identity(int(message()))
        assert child is not None
        os.write(signal_write, b"v")
        assert message() == b"verified"
        expected = roles.expected(config, child_role, **(stage_args if child_role == "provider" else
            {} if child_role == "monitor" else job_args))
        for role in expected.roles:
            with role.path.open("a") as competitor, pytest.raises(BlockingIOError):
                fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.write(signal_write, b"r")
        assert message() == b"complete"
        assert_available(expected)
    finally:
        os.close(ready_read)
        os.close(signal_write)
        if process.is_alive():
            process.kill()
        process.join(10)
        if child and durable.alive(child):
            try:
                os.kill(child["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
