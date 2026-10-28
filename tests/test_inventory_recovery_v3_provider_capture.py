import fcntl
import multiprocessing
import os
import select
import signal
import stat
import sys
import time
from contextlib import ExitStack

import pytest

from humanvoice.artifacts import read_json
from tools.inventory_recovery_v3 import provider_capture as capture
from tools.inventory_recovery_v3.failures import RecoveryStop


def run(tmp_path, program, *, guard=None, deadline=2, byte_limit=1024, executable=sys.executable):
    with ExitStack() as stack:
        handles = [stack.enter_context((tmp_path / f"owner-{i}.lock").open("a")) for i in range(4)]
        for handle in handles:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        descriptors = tuple(handle.fileno() for handle in handles)
        selected = lambda: guard(descriptors) if guard else descriptors
        result = capture.launch([executable, "-c", program, "--output-last-message",
            str(tmp_path / "response-envelope.json")], "synthetic", tmp_path,
            lock_fd=descriptors[-1], before_spawn=selected, deadline=deadline, byte_limit=byte_limit)
        for descriptor in descriptors:
            os.fstat(descriptor)
        return result


@pytest.mark.parametrize("category", ["USER_STOPPED", "BLOCKED_OWNERSHIP"])
def test_last_veto_cleans_fifo_and_keeps_ancestors(tmp_path, monkeypatch, category):
    def veto(descriptors):
        assert len(descriptors) == 4
        assert stat.S_ISFIFO((tmp_path / "response-envelope.json").stat().st_mode)
        assert (tmp_path / "response-capture.part").is_file()
        raise RecoveryStop(category, "last guard")

    monkeypatch.setattr(capture, "OwnedPopen", lambda *a, **k: pytest.fail("veto spawned"))
    result = run(tmp_path, "pass", guard=veto)
    assert isinstance(result, capture.ZeroLaunch)
    assert result.error.category == category and result.cleanup_complete
    assert not (tmp_path / "process-start.json").exists()
    assert not (tmp_path / "process.json").exists()
    for name in capture.STREAMS:
        assert (tmp_path / name).is_file() and (tmp_path / name).read_bytes() == b""


def test_actual_child_inherits_complete_union(tmp_path, monkeypatch):
    native = capture.OwnedPopen
    observations = []

    def spawn(args, **kwargs):
        observations.append(kwargs["pass_fds"])
        return native(args, **kwargs)

    monkeypatch.setattr(capture, "OwnedPopen", spawn)
    program = "import fcntl; from pathlib import Path; import sys\n"
    program += f"root=Path({str(tmp_path)!r})\n"
    program += "for i in range(4):\n h=(root/f'owner-{i}.lock').open('a')\n try: fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB)\n except BlockingIOError: pass\n else: raise AssertionError('lost ancestor')\n"
    program += "Path(sys.argv[-1]).write_text('complete')"
    receipt = run(tmp_path, program)
    assert receipt["status"] == "complete" and receipt["group_quiescent"]
    assert len(observations) == 1 and len(observations[0]) == 4


@pytest.mark.parametrize("channel", ["stdout", "stderr", "final"])
def test_oversized_streams_remain_bounded(tmp_path, channel):
    program = "import sys; from pathlib import Path; " + {
        "stdout": "sys.stdout.buffer.write(b'x'*100000)",
        "stderr": "sys.stderr.buffer.write(b'x'*100000)",
        "final": "Path(sys.argv[-1]).write_bytes(b'x'*100000)"}[channel]
    receipt = run(tmp_path, program)
    assert receipt["status"] == "error" and receipt["limit_reason"] == "output_bytes"
    assert receipt["group_quiescent"] and receipt["process_started"]
    assert all((tmp_path / name).stat().st_size <= 1024 for name in capture.STREAMS)


def test_deadline_and_descendant_cleanup(tmp_path):
    receipt = run(tmp_path, "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);time.sleep(30)", deadline=.2)
    assert receipt["status"] == "timeout" and receipt["group_quiescent"]
    assert capture.native.group_members(receipt["process_group"]) == []


@pytest.mark.parametrize("publication", ["process-start.json", "heartbeat.json"])
def test_post_spawn_publication_failure_is_never_zero_launch(tmp_path, monkeypatch, publication):
    native, failed = capture.persist, []

    def persist(path, value):
        if path.name == publication and not failed:
            failed.append(True)
            raise OSError("publication cut")
        return native(path, value)

    monkeypatch.setattr(capture, "persist", persist)
    with pytest.raises(OSError, match="publication cut"):
        run(tmp_path, "import time; print('data',flush=True); time.sleep(30)")
    receipt = read_json(tmp_path / "process.json")
    assert receipt["process_started"] is True and receipt["group_quiescent"]
    assert receipt["process_group"] == read_json(tmp_path / "process-start.json")["process_group"]


def test_conflicting_evidence_is_not_overwritten(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"retained")
    with pytest.raises(RecoveryStop, match="reconciliation"):
        run(tmp_path, "pass")
    assert path.read_bytes() == b"retained"


def test_provider_retains_all_locks_after_collector_parent_dies(tmp_path):
    from tools import durable_program_supervisor as durable

    read_fd, write_fd = os.pipe()
    marker, release, finished = (tmp_path / name for name in ("ready", "release", "finished"))
    program = ("import sys,time,fcntl; from pathlib import Path; "
        f"root=Path({str(tmp_path)!r}); root.joinpath('ready').write_text('ready')\n"
        "while not root.joinpath('release').exists(): time.sleep(.02)\n"
        "for i in range(4):\n h=root.joinpath(f'owner-{i}.lock').open('a')\n"
        " try: fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB)\n except BlockingIOError: pass\n"
        " else: raise AssertionError('lost inherited lock')\n"
        "root.joinpath('finished').write_text('verified')")

    def parent():
        os.close(read_fd)
        native = capture.persist

        def persist(path, value):
            native(path, value)
            if path.name == "process-start.json":
                os.write(write_fd, str(value["process_group"]).encode() + b"\n")
                os._exit(73)

        capture.persist = persist
        run(tmp_path, program)
        os._exit(74)

    parent_process = multiprocessing.get_context("fork").Process(target=parent)
    child = None
    try:
        parent_process.start()
        os.close(write_fd)
        parent_process.join(10)
        assert parent_process.exitcode == 73
        assert select.select([read_fd], [], [], 10)[0]
        child = int(os.read(read_fd, 128).strip())
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert marker.read_text() == "ready"
        for i in range(4):
            with (tmp_path / f"owner-{i}.lock").open("a") as handle, pytest.raises(BlockingIOError):
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release.touch()
        while not finished.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert finished.read_text() == "verified"
        while durable.alive(durable.identity(child)) and time.monotonic() < deadline:
            time.sleep(.02)
        for i in range(4):
            with (tmp_path / f"owner-{i}.lock").open("a") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(read_fd)
        if parent_process.is_alive():
            parent_process.kill()
        parent_process.join(10)
        if child is not None:
            try:
                os.killpg(child, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_missing_executable_does_not_fabricate_zero_launch(tmp_path):
    with pytest.raises(FileNotFoundError):
        run(tmp_path, "pass", executable=str(tmp_path / "missing-executable"))
    receipt = read_json(tmp_path / "process.json")
    assert receipt["process_started"] is True and receipt["group_quiescent"]
    assert receipt["returncode"] is not None
    assert all((tmp_path / name).read_bytes() == b"" for name in capture.STREAMS)


def test_constructor_failure_without_pid_retains_uncertainty(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("constructor before child identity")

    monkeypatch.setattr(capture.subprocess.Popen, "_execute_child", fail)
    with pytest.raises(OSError, match="before child identity"):
        run(tmp_path, "pass")
    receipt = read_json(tmp_path / "process.json")
    assert receipt["process_started"] is None
    assert receipt["process_group"] is None and receipt["group_quiescent"] is False
    assert receipt["remaining_group_members"] is None


@pytest.mark.parametrize("boundary", ["exec-pipe-read", "constructor-return"])
@pytest.mark.parametrize("error_type", [OSError, ValueError, KeyboardInterrupt])
def test_real_postfork_constructor_failure_kills_and_reaps(tmp_path, monkeypatch, boundary, error_type):
    marker = tmp_path / "spawned.pid"
    program = ("import os,time;from pathlib import Path;"
               f"Path({str(marker)!r}).write_text(str(os.getpid()));time.sleep(30)")
    injected = []

    def cut():
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert marker.exists(), "Real child must run before parent-side failure"
        injected.append(int(marker.read_text()))
        raise error_type("post-fork observation cut")

    if boundary == "exec-pipe-read":
        native = capture.os.read

        def read(fd, length):
            if length == 50000 and not injected:
                cut()
            return native(fd, length)

        monkeypatch.setattr(capture.os, "read", read)
    else:
        native = capture.OwnedPopen.__init__

        def initialize(self, *args, **kwargs):
            native(self, *args, **kwargs)
            cut()

        monkeypatch.setattr(capture.OwnedPopen, "__init__", initialize)
    started = time.monotonic()
    try:
        with pytest.raises(error_type, match="post-fork observation cut"):
            run(tmp_path, program, deadline=.2)
        assert time.monotonic() - started < 12
        assert len(injected) == 1
        receipt = read_json(tmp_path / "process.json")
        assert receipt["process_started"] is True and receipt["group_quiescent"] is True
        assert receipt["process_group"] == injected[0]
        assert read_json(tmp_path / "process-start.json")["process_group"] == injected[0]
        assert not (tmp_path / "prelaunch-intent.json").exists()
        assert capture.native.group_members(injected[0]) == []
        with pytest.raises(ChildProcessError):
            os.waitpid(injected[0], os.WNOHANG)
    finally:
        for pid in injected:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass


@pytest.mark.parametrize("failure", ["read", "process_observation"])
def test_collector_errors_retain_started_identity_and_bound_cleanup(tmp_path, monkeypatch, failure):
    native = capture.os.read

    def read(fd, length):
        if length == 65536:
            raise OSError("collector read cut")
        return native(fd, length)

    def observe(pid):
        raise OSError("observation cut")

    if failure == "read":
        monkeypatch.setattr(capture.os, "read", read)
    else:
        monkeypatch.setattr(capture.native, "group_members", observe)
    started = time.monotonic()
    with pytest.raises((OSError, RecoveryStop)):
        run(tmp_path, "import time; print('data',flush=True);time.sleep(30)", deadline=.2)
    assert time.monotonic() - started < 12
    receipt = read_json(tmp_path / "process.json")
    assert receipt["process_started"] is True
    if failure == "process_observation":
        assert receipt["group_quiescent"] is False and receipt["remaining_group_members"] is None
    else:
        assert receipt["group_quiescent"] is True
"""Real local subprocesses exercise full-union bounded response capture."""

