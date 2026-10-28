"""Verify borrowed ownership without acquiring, upgrading or releasing locks."""

import fcntl
import io
import multiprocessing
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_inventory_recovery_v3_campaign_history import campaign
from test_inventory_recovery_v3_handover import second_adoption
from test_inventory_recovery_v3_supervision import configured

from humanvoice.artifacts import digest, write_json
from tools import durable_program_supervisor as durable
from tools import inventory_history_job as historical
from tools.inventory_recovery_v3 import (
    campaign_initialization,
    descriptors,
    handover,
    job_ownership,
    launch_handoff,
)
from tools.inventory_recovery_v3.stage_authority import CampaignAuthority
from tools.inventory_recovery_v3.stage_owner import StageOwner


def forbid(*args, **keywords):
    raise AssertionError("Borrowed descriptor attempted a lock mutation")


def fdinfo(fd):
    return Path(f"/proc/self/fdinfo/{fd}").read_bytes()


@pytest.mark.parametrize("kind", ["exclusive", "duplicate", "unlocked", "shared", "fresh", "foreign",
                                   "closed", "replaced", "symlink", "directory"])
def test_descriptor_proof_never_changes_any_lock(tmp_path, monkeypatch, kind):
    path = tmp_path / "owner.lock"
    with path.open("a+") as handle, path.open("a+") as fresh, (tmp_path / "foreign.lock").open("a+") as foreign:
        fd = handle.fileno()
        if kind != "unlocked":
            fcntl.flock(fd, (fcntl.LOCK_SH if kind == "shared" else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        extra = None
        if kind == "duplicate":
            extra = fd = os.dup(fd)
        elif kind == "fresh":
            fd = fresh.fileno()
        elif kind == "foreign":
            fd = foreign.fileno()
        elif kind == "closed":
            fd = os.dup(fd)
            os.close(fd)
        elif kind == "replaced":
            path.rename(path.with_suffix(".old"))
            path.touch()
        elif kind == "symlink":
            alias = tmp_path / "alias"
            alias.symlink_to(path)
            path = alias
        elif kind == "directory":
            extra = fd = os.open(tmp_path, os.O_DIRECTORY)
            path = tmp_path
        before = fdinfo(handle.fileno()), fdinfo(fresh.fileno()), fdinfo(foreign.fileno())
        try:
            with monkeypatch.context() as patch:
                patch.setattr(fcntl, "flock", forbid)
                patch.setattr(historical, "exclusive_descriptor", forbid)
                if kind in {"exclusive", "duplicate"}:
                    assert descriptors.exclusive_descriptor(path, fd) is True
                else:
                    with pytest.raises(ValueError):
                        descriptors.exclusive_descriptor(path, fd)
            assert before == (fdinfo(handle.fileno()), fdinfo(fresh.fileno()), fdinfo(foreign.fileno()))
        finally:
            if extra is not None:
                os.close(extra)


@pytest.mark.parametrize("descriptor", [True, False, None, -1, 0, 1, 2, 3.0, "3"])
def test_descriptor_requires_exact_nonstdio_integer(tmp_path, descriptor):
    with pytest.raises(ValueError, match="integer descriptor"):
        descriptors.exclusive_descriptor(tmp_path / "lock", descriptor)


@pytest.mark.parametrize("defect", ["unreadable", "missing", "shared", "posix", "range", "inode",
                                     "duplicate", "blocked", "oversized", "nonascii"])
def test_unavailable_or_ambiguous_fdinfo_fails_without_locking(tmp_path, monkeypatch, defect):
    path = tmp_path / "owner.lock"
    with path.open("a+") as handle:
        fd = handle.fileno()
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        content = fdinfo(fd)
        row = next(line for line in content.splitlines() if line.startswith(b"lock:"))
        changed = {"missing": b"", "shared": row.replace(b"WRITE", b"READ"),
            "posix": row.replace(b"FLOCK", b"POSIX"), "range": row.replace(b"0 EOF", b"1 EOF"),
            "inode": row.replace(str(path.stat().st_ino).encode(), b"999"),
            "duplicate": row + b"\n" + row, "blocked": row.replace(b"FLOCK", b"-> FLOCK"),
            "oversized": b"x" * 65537, "nonascii": bytes([255])}.get(defect, row)
        native_open = Path.open

        def open_file(current, *args, **keywords):
            if str(current) == f"/proc/self/fdinfo/{fd}":
                if defect == "unreadable":
                    raise PermissionError("offline unreadable fdinfo")
                return io.BytesIO(changed)
            return native_open(current, *args, **keywords)

        with monkeypatch.context() as patch:
            patch.setattr(Path, "open", open_file)
            patch.setattr(fcntl, "flock", forbid)
            with pytest.raises(ValueError):
                descriptors.exclusive_descriptor(path, fd)
        assert fdinfo(fd) == content


@pytest.mark.parametrize("change", ["path", "unlock", "reuse"])
def test_late_fdinfo_observation_race_rejects_changed_owner(tmp_path, monkeypatch, change):
    path = tmp_path / "owner.lock"
    with path.open("a+") as handle, (tmp_path / "other.lock").open("a+") as other:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original, calls = descriptors.lock_record, []

        def observe(fd, expected):
            result = original(fd, expected)
            calls.append(True)
            if len(calls) == 2:
                if change == "path":
                    path.rename(path.with_suffix(".old"))
                    path.touch()
                elif change == "reuse":
                    os.dup2(other.fileno(), fd)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            return result

        monkeypatch.setattr(descriptors, "lock_record", observe)
        if change == "unlock":
            # A lock can change immediately after any completed observation.
            # The next check must reject it; path/FD replacement is caught now.
            descriptors.exclusive_descriptor(path, handle.fileno())
        with pytest.raises(ValueError):
            descriptors.exclusive_descriptor(path, handle.fileno())


def test_campaign_bootstrap_and_borrowed_history_never_relock(tmp_path, monkeypatch):
    current = campaign(tmp_path)
    with campaign_initialization.owned(current.root, lambda: True) as (fd, check):
        with monkeypatch.context() as patch:
            patch.setattr(fcntl, "flock", forbid)
            patch.setattr(historical, "exclusive_descriptor", forbid)
            assert check() is True
            with current.owned(descriptor=fd):
                assert current.guard() is True
                current.initialize()
            assert descriptors.exclusive_descriptor(current.root / "campaign.lock", fd)
        assert check() is True


def test_real_handoff_and_private_job_adapters_use_nonmutating_proof(tmp_path, monkeypatch):
    _live, _implementation, monitor, request, _ack = configured(tmp_path, monkeypatch)
    directory = monitor.root / "jobs/job-0001"
    (directory / "ack.json").unlink()
    native_binding = historical.prepare, historical.require, historical.binding
    with launch_handoff.prepare(monitor.root, "job-0001", request, owner_check=lambda: True,
                                stop_check=lambda: None) as handoff:
        monkeypatch.setenv(launch_handoff.CAPSULE, handoff["environment"][launch_handoff.CAPSULE])
        with monkeypatch.context() as patch:
            patch.setattr(fcntl, "flock", forbid)
            patch.setattr(historical, "exclusive_descriptor", forbid)
            with launch_handoff.inherited(monitor.root, "job-0001", request, stop_check=lambda: None) as handle:
                write_json(directory / "ack.json", {"phase": request["phase"],
                    "owner": durable.identity(os.getpid()), "request_identity": durable.fingerprint(request),
                    "ownership_protocol": "inherited-worker-lock-v1"})
                capsule = job_ownership.prepare(monitor.root, "job-0001", request, (handle.fileno(),))
                patch.setenv(job_ownership.CAPSULE, capsule)
                assert job_ownership.require(monitor.root, "job-0001", request)["descriptor"] == handle.fileno()
            assert descriptors.exclusive_descriptor(directory / "worker.lock", handoff["pass_fds"][0])
    assert (historical.prepare, historical.require, historical.binding) == native_binding


def test_campaign_authority_and_stage_borrowers_use_private_job_verifier(tmp_path, monkeypatch):
    root = tmp_path / "supervision"
    directory = root / "jobs/job-0001"
    directory.mkdir(parents=True)
    output = tmp_path / "stage"
    output.mkdir()
    config = {"stop_bindings": [], "execution_authority": {"program_base": str(tmp_path),
        "supervisor_root": str(root), "account": str(tmp_path / "account.json"),
        "grant": str(tmp_path / "grant.json"), "grant_identity": "fixture"}}
    request = {"job_id": "job-0001", "phase": "RUNNING", "command": ["offline"],
               "config_identity": digest(config)}
    write_json(root / "config.json", config)
    write_json(directory / "ack.json", {"phase": "RUNNING", "owner": durable.identity(os.getpid()),
        "request_identity": durable.fingerprint(request), "ownership_protocol": "inherited-worker-lock-v1"})
    implementation = SimpleNamespace(OUTPUT=root, config=lambda: config, checked_request=lambda *args: request)
    with (tmp_path / "active-session-program.lock").open("a") as program, (
            directory / "worker.lock").open("a") as job, (output / "executor.lock").open("a") as executor:
        for handle in (program, job, executor):
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setenv("HUMANVOICE_SUPERVISOR_JOB", "job-0001")
        monkeypatch.setenv(job_ownership.CAPSULE, job_ownership.prepare(root, "job-0001", request, (job.fileno(),)))
        plan = {"fixture": "borrow-only"}
        write_json(output / "plan.json", plan)
        with monkeypatch.context() as patch:
            patch.setattr(fcntl, "flock", forbid)
            patch.setattr(historical, "exclusive_descriptor", forbid)
            authority = CampaignAuthority(implementation, program_descriptor=program.fileno(), command=["offline"],
                require_admission=lambda: config, stop_check=lambda: None)
            assert authority.check() is True
            owner = StageOwner(output, plan, [(output / "executor.lock", executor)], authority)
            assert owner.check() is True


def test_chained_handover_borrowers_never_relock(tmp_path, monkeypatch):
    record = second_adoption(tmp_path, monkeypatch)
    with handover.lease(record) as owner:
        capsule = owner.capsule()
        monkeypatch.setenv(handover.DESCRIPTORS, capsule["environment"][handover.DESCRIPTORS])
        with monkeypatch.context() as patch:
            patch.setattr(fcntl, "flock", forbid)
            patch.setattr(historical, "exclusive_descriptor", forbid)
            assert owner.check() is True
            with handover.inherited(record) as child:
                assert child.check() is True
            assert owner.check() is True


def verify_grandchild_after_parent_death(tmp_path, failure=None):
    path = tmp_path / "owner.lock"
    ready_read, ready_write = os.pipe()
    stop_read, stop_write = os.pipe()
    root = Path(__file__).resolve().parents[1]
    source = ("import os,sys\nfrom pathlib import Path\n"
        f"sys.path[:0]={[str(root), str(root / 'src')]!r}\n"
        "from tools.inventory_recovery_v3.descriptors import exclusive_descriptor\n"
        "path,fd,ready,stop=sys.argv[1:];fd,ready,stop=map(int,(fd,ready,stop))\n"
        "os.write(ready,(str(os.getpid())+'\\n').encode())\n"
        "assert os.read(stop,1)==b'v'\n"
        f"failure={failure!r}\n"
        "if failure=='initial': raise ValueError('forced initial proof failure')\n"
        "exclusive_descriptor(path,fd)\n"
        "os.write(ready,b'verified\\n')\n"
        "assert os.read(stop,1)==b'r'\n"
        "if failure=='final': raise ValueError('forced final proof failure')\n"
        "exclusive_descriptor(path,fd);os.close(fd)\n"
        "os.write(ready,b'complete\\n');os.close(ready);os._exit(0)\n")

    def parent():
        os.close(ready_read)
        os.close(stop_write)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        subprocess.Popen([sys.executable, "-I", "-c", source, str(path), str(fd), str(ready_write), str(stop_read)],
            pass_fds=(fd, ready_write, stop_read), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        os._exit(73)

    process = multiprocessing.get_context("fork").Process(target=parent)
    child = None

    def message():
        result = b''
        deadline = time.monotonic() + 10
        while not result.endswith(b'\n'):
            assert select.select([ready_read], [], [], max(0, deadline - time.monotonic()))[0], (
                'Grandchild verification acknowledgement timed out')
            part = os.read(ready_read, 1)
            assert part, 'Grandchild verification acknowledgement missing'
            result += part
            assert len(result) <= 128
        return result.strip()

    try:
        process.start()
        os.close(ready_write)
        os.close(stop_read)
        process.join(10)
        assert process.exitcode == 73
        child = durable.identity(int(message()))
        assert child is not None
        # The proof cannot execute until the creator has definitely exited.
        os.write(stop_write, b'v')
        assert message() == b'verified'
        with path.open("a") as competitor:
            with pytest.raises(BlockingIOError):
                fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.write(stop_write, b'r')
            assert message() == b'complete'
            assert select.select([ready_read], [], [], 10)[0]
            assert os.read(ready_read, 1) == b''
            deadline = time.monotonic() + 10
            while True:
                try:
                    fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        pytest.fail("Grandchild did not release inherited reference")
                    time.sleep(0.02)
    finally:
        for fd in (ready_read, stop_write):
            os.close(fd)
        if process.is_alive():
            process.kill()
        process.join(10)
        if child is not None and durable.alive(child):
            try:
                os.kill(child['pid'], signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_grandchild_retains_verified_lock_after_parent_death(tmp_path):
    verify_grandchild_after_parent_death(tmp_path)


@pytest.mark.parametrize('failure', ['initial', 'final'])
def test_grandchild_proof_failure_cannot_pass_on_released_lock(tmp_path, failure):
    with pytest.raises(AssertionError, match='verification acknowledgement missing'):
        verify_grandchild_after_parent_death(tmp_path, failure)
