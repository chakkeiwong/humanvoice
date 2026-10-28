"""Bounded offline validation terminates its workers and fixes test membership."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import validate_inventory_recovery_v3 as validation


@pytest.fixture
def receipt_run(tmp_path, monkeypatch):
    """Exercise real receipt acceptance with temporary authority and test evidence."""
    output = tmp_path / "validation-output"
    account, grant = tmp_path / "account.json", tmp_path / "grant.json"
    for path in (account, grant, grant.with_suffix(".stages.json")):
        path.write_text("{}")
    monkeypatch.setattr(validation.review, "OUTPUT", output)
    monkeypatch.setattr(validation.review, "program", SimpleNamespace(
        predecessor=SimpleNamespace(account=SimpleNamespace(ACCOUNT=account)), GRANT=grant))
    monkeypatch.setattr(validation, "binding", lambda: {"source": "fixed"})
    tests = validation.SCOPES["executor"]
    nodes = [tests[0] + "::test_fixture"]

    def command_run(command, *, log, timeout):
        path = Path(next(arg.split("=", 1)[1] for arg in command
                         if arg.startswith("--history-membership=")))
        record = {"collected": nodes, "exit_code": 0}
        if "--collect-only" not in command:
            record["executed"] = nodes
            xml = Path(next(arg.split("=", 1)[1] for arg in command
                            if arg.startswith("--junitxml=")))
            xml.write_text('<testsuites><testsuite><testcase name="fixture"/></testsuite></testsuites>')
        path.write_text(json.dumps(record))

    monkeypatch.setattr(validation, "command_run", command_run)

    def execute():
        code = validation.run("executor")
        receipts = list(output.rglob("validation.json"))
        assert len(receipts) == 1
        return code, json.loads(receipts[0].read_text())

    return SimpleNamespace(execute=execute, account=account)


def test_receipt_accepts_complete_unchanged_evidence(receipt_run):
    code, receipt = receipt_run.execute()
    assert code == 0 and receipt["status"] == "pass"
    assert receipt["cases"] == 1 and receipt["phase"] == "finished"
    assert receipt["source_unchanged"] and receipt["authority_unchanged"]
    assert not receipt["release_acceptance"] and not receipt["live_execution_enabled"]


@pytest.mark.parametrize("changed", ["source", "authority"])
def test_final_comparison_alone_cannot_publish_pass(receipt_run, monkeypatch, changed):
    calls = 0
    original = Path.read_bytes

    def binding():
        nonlocal calls
        calls += 1
        return {"source": "changed" if calls == 3 else "fixed"}

    def read_bytes(path):
        nonlocal calls
        if path == receipt_run.account:
            calls += 1
            if calls == 3:
                return b'{"changed":true}'
        return original(path)

    if changed == "source":
        monkeypatch.setattr(validation, "binding", binding)
    else:
        monkeypatch.setattr(Path, "read_bytes", read_bytes)
    code, receipt = receipt_run.execute()
    assert calls == 3
    assert code == 1 and receipt["status"] == "fail"
    assert receipt["phase"] == "finished"
    assert receipt[changed + "_unchanged"] is False
    assert "Final source or authority comparison failed" in receipt["finalization_error"]


@pytest.mark.parametrize("failed_read", ["source", "authority"])
def test_final_read_error_preserves_original_command_failure(receipt_run, monkeypatch, failed_read):
    original = Path.read_bytes
    calls = 0

    def command_run(command, *, log, timeout):
        raise subprocess.CalledProcessError(23, command)

    def binding():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("final source read failed")
        return {"source": "fixed"}

    def read_bytes(path):
        nonlocal calls
        if path == receipt_run.account:
            calls += 1
            if calls == 2:
                raise OSError("final authority read failed")
        return original(path)

    monkeypatch.setattr(validation, "command_run", command_run)
    if failed_read == "source":
        monkeypatch.setattr(validation, "binding", binding)
    else:
        monkeypatch.setattr(Path, "read_bytes", read_bytes)
    code, receipt = receipt_run.execute()
    assert code == 1 and receipt["status"] == "fail" and receipt["phase"] == "finished"
    assert "CalledProcessError" in receipt["error"] and "23" in receipt["error"]
    assert "final " + failed_read + " read failed" in receipt["finalization_error"]


def test_scoped_validation_cannot_omit_its_fixed_members():
    assert validation.SCOPES["full"] == validation.TESTS
    assert set(validation.SCOPES) == {"full", "floors", "executor"}
    assert validation.SCOPES["executor"] == ("tests/test_inventory_recovery_v3_executor.py",)
    assert "tests/test_inventory_recovery_v3_floor_followup.py" in validation.SCOPES["floors"]
    assert "tests/test_inventory_recovery_v3_validation.py" in validation.SCOPES["floors"]
    for members in validation.SCOPES.values():
        assert len(members) == len(set(members)) and set(members) <= set(validation.TESTS)


def test_offline_command_failure_is_not_a_passing_receipt(tmp_path):
    with (tmp_path / "test.log").open("wb") as log:
        validation.command_run([sys.executable, "-c", "print('offline')"], log=log, timeout=10)
        with pytest.raises(subprocess.CalledProcessError) as failure:
            validation.command_run([sys.executable, "-c", "raise SystemExit(23)"], log=log, timeout=10)
    assert failure.value.returncode == 23


@pytest.mark.parametrize("ignore", [False, True])
def test_timeout_kills_child_even_when_group_leader_exits(tmp_path, ignore):
    marker = tmp_path / "child.pid"
    source = ("import os,signal,time;from pathlib import Path;"
        "child=os.fork();"
        "signal.signal(signal.SIGINT,signal.SIG_IGN) if child==0 and " + repr(ignore) + " else None;"
        "Path(" + repr(str(marker)) + ").write_text(str(os.getpid())) if child==0 else None;"
        "time.sleep(30)")
    with (tmp_path / "test.log").open("wb") as log, pytest.raises(subprocess.TimeoutExpired):
        validation.command_run([sys.executable, "-c", source], log=log, timeout=1)
    pid = int(marker.read_text())
    deadline = time.monotonic() + 5
    try:
        while time.monotonic() < deadline:
            status = Path(f"/proc/{pid}/stat")
            if not status.exists() or status.read_text().split(")", 1)[1].strip().startswith("Z"):
                break
            time.sleep(0.02)
        else:
            pytest.fail("Validation timeout left a running descendant")
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


@pytest.mark.parametrize("returncode", [0, 23])
def test_normal_leader_exit_cleans_synchronized_surviving_child(tmp_path, returncode):
    marker = tmp_path / "child.pid"
    source = f"""
import os, signal, time
from pathlib import Path
reader, writer = os.pipe()
child = os.fork()
if child == 0:
    os.close(reader)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    Path({str(marker)!r}).write_text(str(os.getpid()))
    os.write(writer, b'ready')
    os.close(writer)
    time.sleep(30)
    os._exit(0)
os.close(writer)
assert os.read(reader, 5) == b'ready'
os.close(reader)
os._exit({returncode})
"""
    started = time.monotonic()
    try:
        with (tmp_path / "test.log").open("wb") as log:
            if returncode:
                with pytest.raises(subprocess.CalledProcessError) as failure:
                    validation.command_run([sys.executable, "-c", source], log=log, timeout=10)
                assert failure.value.returncode == returncode
            else:
                validation.command_run([sys.executable, "-c", source], log=log, timeout=10)
        assert time.monotonic() - started < 8
        pid = int(marker.read_text())
        assert validation.durable.identity(pid) is None
    finally:
        if marker.exists():
            try:
                os.kill(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("fault", ["none", "signal_interrupt", "observe_oserror", "kill_observe_interrupt"])
def test_nonreaping_process_cleanup_is_bounded_and_preserves_failure(tmp_path, monkeypatch, fault):
    clock, waits, sent = [0.0], [], []
    original = subprocess.TimeoutExpired(["offline-fixture"], 7)

    class Process:
        pid = 987654321

        def wait(self, timeout=None):
            assert timeout is not None, "cleanup attempted an unbounded wait"
            waits.append(timeout)
            raise original

        def poll(self):
            return None

        def __enter__(self):
            pytest.fail("Popen context would introduce an implicit exit wait")

        def __exit__(self, *args):
            pytest.fail("Popen context attempted implicit cleanup")

    def killpg(pid, selected):
        assert pid == Process.pid
        sent.append(selected)
        if fault == "signal_interrupt" and selected == signal.SIGINT:
            raise KeyboardInterrupt("cleanup interrupted")

    def group_members(pid):
        assert pid == Process.pid
        if fault == "observe_oserror":
            raise PermissionError("unrelated process stat is unreadable")
        if fault == "kill_observe_interrupt" and clock[0] >= 2 and signal.SIGKILL not in sent:
            raise KeyboardInterrupt("hard-stop observation interrupted")
        return [owner]

    def sleep(seconds):
        assert 0 <= seconds <= 0.05
        clock[0] += seconds

    owner = {"pid": Process.pid, "start_ticks": "fixture", "boot_id": "fixture"}
    monkeypatch.setattr(validation.subprocess, "Popen", lambda *a, **kw: Process())
    monkeypatch.setattr(validation.durable, "identity", lambda pid: owner)
    monkeypatch.setattr(validation, "group_members", group_members)
    monkeypatch.setattr(validation.os, "killpg", killpg)
    monkeypatch.setattr(validation.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(validation.time, "sleep", sleep)
    with (tmp_path / "test.log").open("wb") as log, pytest.raises(validation.CommandCleanupError) as failure:
        validation.command_run(["offline-fixture"], log=log, timeout=7)
    assert waits == [7] and clock[0] <= 5.01
    assert sent == [signal.SIGINT, signal.SIGKILL]
    assert failure.value.__cause__ is original
    evidence = failure.value.evidence
    assert not evidence["complete"] and not evidence["leader_reaped"]
    assert not evidence["group_quiescent"]
    assert evidence["remaining"] == (None if fault == "observe_oserror" else [owner])
    assert evidence["owner"] == owner and "TimeoutExpired" in evidence["original_error"]
    assert bool(evidence["errors"]) is (fault != "none")
    if fault == "signal_interrupt":
        assert "KeyboardInterrupt: cleanup interrupted" in evidence["errors"]
    elif fault == "observe_oserror":
        assert "PermissionError: unrelated process stat is unreadable" in evidence["errors"]
    elif fault == "kill_observe_interrupt":
        assert "KeyboardInterrupt: hard-stop observation interrupted" in evidence["errors"]
