"""Prospective bounded collector: final owned dispatch and complete FD union."""

import math
import os
import selectors
import signal
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from humanvoice.artifacts import digest
from tools import response_capture_observation as native
from tools.durable_program_supervisor import identity
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path

ENFORCEMENT = native.ENFORCEMENT
MAX_BYTES = native.MAX_BYTES
STREAMS = ("events.jsonl", "stderr.log", "response-envelope.json")


@dataclass(frozen=True)
class ZeroLaunch:
    error: BaseException
    cleanup_complete: bool


class OwnedPopen(subprocess.Popen):
    """Retain the object before __init__ can fork and then fail in the parent."""

    def __init__(self, *arguments, retain, **keywords):
        retain(self)
        super().__init__(*arguments, **keywords)


def launch(arguments, prompt, directory, *, lock_fd, before_spawn, deadline=900, byte_limit=MAX_BYTES):
    """Borrow verified descriptors; never close or unlock ancestor ownership."""
    directory = Path(directory)
    if (not callable(before_spawn) or type(byte_limit) is not int or byte_limit <= 0
            or type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= 0):
        raise ValueError("Collector requires a final dispatch guard and positive byte limit")
    for name in (*STREAMS, "response-capture.part", "stdin.txt", "process.json", "process-start.json"):
        if regular_path(directory / name).exists():
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Retained collector evidence requires reconciliation")
    started, wall_started = time.monotonic(), time.time()
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("OPENAI_", "ANTHROPIC_"))}
    process, reason, error, start_record = None, None, None, None
    spawn_attempted = False
    process_id = None
    remaining, quiescent = None, False
    sizes = {name: 0 for name in STREAMS}
    sinks, descriptors, cleanup_errors = {}, [], []
    selector = selectors.DefaultSelector()
    response = directory / "response-envelope.json"
    captured = directory / "response-capture.part"
    source, fifo_created = None, False

    def retain(child):
        nonlocal process
        process = child

    def observe_start():
        return {"owner": identity(process_id), "parent": identity(os.getpid()),
                "started_at": wall_started, "process_group": process_id}

    def cleanup_step(action):
        try:
            return action()
        except BaseException as exc:  # noqa: BLE001 -- attempt every cleanup step after interruption
            cleanup_errors.append(type(exc).__name__ + ": " + str(exc))
            return None

    def drain(timeout):
        nonlocal reason
        for selected, _mask in selector.select(timeout):
            name = selected.data
            try:
                chunk = os.read(selected.fd, 65536)
            except BlockingIOError:
                continue
            if not chunk:
                selector.unregister(selected.fd)
                continue
            available = max(0, byte_limit - sizes[name])
            sinks[name].write(chunk[:available])
            sinks[name].flush()
            sizes[name] += min(len(chunk), available)
            if len(chunk) > available or sizes[name] >= byte_limit:
                reason = "output_bytes"

    try:
        if arguments.count("--output-last-message") != 1 or Path(
                arguments[arguments.index("--output-last-message") + 1]) != response:
            raise ValueError("Native output path differs from owned response capture")
        os.mkfifo(response, 0o600)
        fifo_created = True
        descriptor = os.open(response, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW)
        descriptors.append(descriptor)
        source = (directory / "stdin.txt").open("xb+")
        source.write(prompt.encode())
        source.flush()
        source.seek(0)
        for name in STREAMS:
            sinks[name] = (captured if name == "response-envelope.json" else directory / name).open("xb")
        selector.register(descriptor, selectors.EVENT_READ, "response-envelope.json")
        selected = before_spawn()
        if (not isinstance(selected, tuple) or not selected or len(set(selected)) != len(selected)
                or any(type(fd) is not int or fd < 3 for fd in selected) or lock_fd not in selected):
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Provider lost its complete borrowed descriptor union")
        spawn_attempted = True
        OwnedPopen(arguments, retain=retain, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environment, start_new_session=True, pass_fds=selected)
        process_id = process.pid
        start_record = observe_start()
        persist(directory / "process-start.json", start_record)
        for stream, name in ((process.stdout, "events.jsonl"), (process.stderr, "stderr.log")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream.fileno(), selectors.EVENT_READ, name)
        while process.poll() is None:
            drain(0.1)
            persist(directory / "heartbeat.json", {"observed_at": time.time(), "bytes": sizes,
                "elapsed_seconds": time.monotonic() - started, "owner": start_record["owner"],
                "provider_progress_known": False})
            if reason:
                break
            if time.monotonic() - started >= deadline:
                reason = "deadline"
                break
    except BaseException as exc:  # noqa: BLE001 -- retain failure after bounded owned cleanup
        reason, error = "local_exception", exc
    finally:
        # Popen can raise after fork/exec but before its constructor returns.
        # Its retained object still carries the PID needed to kill and reap.
        # Missing PID is uncertainty, never proof that no child was launched.
        candidate_pid = getattr(process, "pid", None)
        if type(candidate_pid) is int and candidate_pid > 0:
            process_id = candidate_pid
        if process_id is not None:
            if start_record is None:
                start_record = cleanup_step(observe_start)

            def kill():
                try:
                    os.killpg(process_id, signal.SIGKILL)
                except ProcessLookupError:
                    pass

            cleanup_step(kill)
            # A constructor failure can precede the child's setsid. The owned
            # unreaped PID must also be terminated if its group is not ready.
            cleanup_step(process.kill)
            cleanup_step(lambda: process.wait(timeout=5))
            cleanup_deadline = time.monotonic() + 5
            while True:
                observed = cleanup_step(lambda: native.group_members(process_id))
                if observed is None:
                    remaining = None
                    break
                remaining = observed
                if not remaining or time.monotonic() >= cleanup_deadline:
                    break
                time.sleep(0.05)
            polled = cleanup_step(process.poll)
            quiescent = remaining == [] and polled is not None
            if not quiescent:
                reason = "group_cleanup_incomplete"
            for _index in range(512):
                before = dict(sizes)
                cleanup_step(lambda: drain(0))
                if before == sizes or reason == "output_bytes":
                    break
        cleanup_step(selector.close)
        for descriptor in descriptors:
            cleanup_step(lambda descriptor=descriptor: os.close(descriptor))
        if source is not None:
            cleanup_step(source.close)
        for handle in sinks.values():
            cleanup_step(handle.flush)
            cleanup_step(lambda handle=handle: os.fsync(handle.fileno()))
            cleanup_step(handle.close)
        if process is not None:
            for stream in (getattr(process, "stdout", None), getattr(process, "stderr", None)):
                if stream is not None:
                    cleanup_step(stream.close)
        if fifo_created:
            def remove_fifo():
                if not stat.S_ISFIFO(response.lstat().st_mode):
                    raise ValueError("Owned response FIFO changed before cleanup")
                response.unlink()

            cleanup_step(remove_fifo)
        if captured.exists():
            cleanup_step(lambda: os.replace(captured, response))
        if not spawn_attempted:
            for name in STREAMS:
                def empty(name=name):
                    path = regular_path(directory / name)
                    if not path.exists():
                        with path.open("xb") as handle:
                            handle.flush()
                            os.fsync(handle.fileno())
                    if path.read_bytes():
                        raise ValueError("Zero-launch output is not empty")

                cleanup_step(empty)
    if not spawn_attempted and not cleanup_errors:
        return ZeroLaunch(error or ValueError("Collector did not start a process"), True)
    if cleanup_errors and reason != "group_cleanup_incomplete":
        reason = "local_exception"
    receipt = {"status": "timeout" if reason == "deadline" else "error" if reason or (
        process_id is not None and getattr(process, "returncode", None) != 0) else "complete",
        "returncode": getattr(process, "returncode", None),
        "process_started": True if process_id is not None else None,
        "process_group": process_id,
        "elapsed_seconds": time.monotonic() - started, "group_quiescent": quiescent,
        "remaining_group_members": remaining, "deadline_seconds": deadline,
        "byte_limit": byte_limit, "limit_reason": reason, "launch_argv_hash": digest(arguments),
        "enforcement": ENFORCEMENT, "capture": {"mode": "parent-bounded-pipes-and-final-response-fifo",
            "bytes": sizes, "global_file_limit": False}, "ended_at": time.time()}
    if start_record is not None:
        receipt["observed_process_start"] = start_record
        if not (directory / "process-start.json").exists():
            cleanup_step(lambda: persist(directory / "process-start.json", start_record))
    if cleanup_errors:
        receipt["cleanup_errors"] = cleanup_errors
    persist(directory / "process.json", receipt)
    if error is not None:
        raise error
    if cleanup_errors:
        raise RecoveryStop("BLOCKED_ENGINEERING", "Provider cleanup or evidence publication was incomplete",
                           evidence={"cleanup_errors": cleanup_errors})
    return receipt
