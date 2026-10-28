"""Service lifecycle fixtures do not assert production root isolation."""

import json
import socket
import sqlite3
import struct
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import control_diagnostics as diagnostics
from control_diagnostics import ServiceFailure
from control_service import ReadService, protected_database, protected_directory
from control_transport import MAX_REQUEST_BYTES
from control_witness import WitnessError
from test_control_transport import FixtureReader
from test_control_witness import CONFIG, GENESIS, witness

__all__ = ["witness"]


class FixtureService(ReadService):
    def _check(self):
        assert self.path.parent.is_dir() and self.witness.path.is_file()
        return True

    def _diagnostic_check(self):
        # Explicit same-user fixture; never production protection evidence.
        assert self.diagnostic_path.parent.is_dir()


def test_real_daemon_survives_malformed_clients_and_stops_cleanly(witness, tmp_path):
    path = tmp_path / "daemon.sock"
    stop, errors = threading.Event(), []

    def serve():
        try:
            FixtureService(path, witness).serve(stop)
        except (OSError, ValueError) as error:
            errors.append(error)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        assert path.is_socket()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(str(path))
            client.sendall(struct.pack("!I", MAX_REQUEST_BYTES + 1))
            assert client.recv(1) == b""
        reader = FixtureReader(path, genesis=GENESIS, configuration=CONFIG)
        assert reader.snapshot()["sequence"] == 0
        assert not FixtureService(path, witness).diagnostic_path.exists()
        with pytest.raises(ServiceFailure):
            FixtureService(path, witness).serve(threading.Event())
        assert reader.snapshot()["sequence"] == 0
    finally:
        stop.set()
        thread.join(8)
    assert not thread.is_alive() and not errors and not path.exists()


def test_production_service_rejects_unprotected_workspace(witness, tmp_path):
    with pytest.raises(ServiceFailure) as failure:
        ReadService(tmp_path / "host.sock", witness).serve(threading.Event())
    assert failure.value.diagnostic_error == "WitnessError"
    assert not (tmp_path / "state.sqlite.read-failure.json").exists()
    assert not (tmp_path / "host.sock").exists()


def test_production_directory_check_rejects_workspace_and_symlink(tmp_path):
    with pytest.raises(WitnessError):
        protected_directory(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(WitnessError):
        protected_directory(alias)


@pytest.mark.parametrize("defect", ["uid", "mode", "link_count", "symlink", "missing", "journal_uid"])
def test_protected_database_permission_matrix(monkeypatch, defect):
    import stat

    path = Path("/fixed-witness/state.sqlite")

    def metadata(selected):
        if selected in (Path("/"), path.parent):
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0, st_nlink=1)
        if selected == path:
            if defect == "missing":
                raise FileNotFoundError(selected)
            return SimpleNamespace(st_mode=(stat.S_IFLNK if defect == "symlink" else stat.S_IFREG)
                                   | (0o644 if defect == "mode" else 0o600),
                                   st_uid=1000 if defect == "uid" else 0,
                                   st_nlink=2 if defect == "link_count" else 1)
        if defect == "journal_uid" and selected.name.endswith("-journal"):
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=1000, st_nlink=1)
        raise FileNotFoundError(selected)

    monkeypatch.setattr(Path, "lstat", metadata)
    with pytest.raises(WitnessError):
        protected_database(path)


@pytest.mark.parametrize("path", ["relative/state", "/run/../state", "/run//witness", "/run/./witness"])
def test_noncanonical_host_paths_are_rejected(path):
    from control_transport import endpoint
    from control_witness import canonical

    for check in (canonical, endpoint, protected_directory):
        with pytest.raises(WitnessError, match="canonical"):
            check(path)
    with pytest.raises(WitnessError, match="canonical"):
        ReadService(path, None)


@pytest.mark.parametrize("error,category", [
    (OSError(28, "secret-manuscript-content"), "BLOCKED_EXTERNAL"),
    (sqlite3.OperationalError("secret-database-path"), "BLOCKED_EXTERNAL"),
    (WitnessError("secret-corrupt-record"), "BLOCKED_ACCOUNTING"),
    (RuntimeError("secret-unexpected-failure"), "BLOCKED_ENGINEERING"),
])
def test_witness_failure_stops_service_and_persists_sanitized_diagnostic(
        witness, tmp_path, monkeypatch, error, category):
    path = tmp_path / "failure.sock"
    service = FixtureService(path, witness)
    errors, stop = [], threading.Event()
    initial = witness.path.read_bytes()

    def fail(_nonce):
        raise error

    monkeypatch.setattr(witness, "snapshot", fail)

    def serve():
        try:
            service.serve(stop)
        except ServiceFailure as failure:
            errors.append(failure)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        with pytest.raises((OSError, WitnessError)):
            FixtureReader(path, genesis=GENESIS, configuration=CONFIG).snapshot()
        thread.join(8)
    finally:
        stop.set()
        thread.join(8)
    assert not thread.is_alive() and len(errors) == 1
    assert not path.exists()
    retained = json.loads(service.diagnostic_path.read_bytes())
    assert errors[0].record == retained
    assert retained["phase"] == "request" and retained["category"] == category
    assert retained["error_type"] == type(error).__name__
    assert errors[0].diagnostic_error is None
    assert retained["dispatch_allowed"] is retained["automatic_repair"] is False
    assert "secret" not in service.diagnostic_path.read_text()
    assert witness.path.read_bytes() == initial


def test_failed_diagnostic_storage_still_reaches_service_owner(witness, tmp_path, monkeypatch):
    service = FixtureService(tmp_path / "diagnostic.sock", witness)

    def unavailable(*_args, **_kwargs):
        raise OSError(28, "secret-full-disk")

    monkeypatch.setattr(diagnostics, "retain", unavailable)
    monkeypatch.setattr(service, "_check", lambda: unavailable())
    with pytest.raises(ServiceFailure) as failed:
        service.serve(threading.Event())
    assert failed.value.record["phase"] == "startup"
    assert failed.value.record["category"] == "BLOCKED_EXTERNAL"
    assert failed.value.diagnostic_error == "OSError"
    assert not service.path.exists() and not service.diagnostic_path.exists()


def test_repeated_failures_preserve_first_bound_diagnostic(witness, tmp_path):
    service = FixtureService(tmp_path / "repeat.sock", witness)
    first = service._report(OSError(28, "first"), "request")
    retained = service.diagnostic_path.read_bytes()
    for _ in range(3):
        later = service._report(WitnessError("later"), "startup")
        assert later.diagnostic_error is None
    assert service.diagnostic_path.read_bytes() == retained
    assert json.loads(retained) == first.record
    assert later.record["category"] == "BLOCKED_ACCOUNTING"


def test_foreign_diagnostic_is_not_overwritten(witness, tmp_path):
    service = FixtureService(tmp_path / "foreign.sock", witness)
    service.diagnostic_path.write_text('{"foreign":true}')
    error = service._report(WitnessError("broken witness"), "request")
    assert error.diagnostic_error == "WitnessError"
    assert service.diagnostic_path.read_text() == '{"foreign":true}'


def test_diagnostic_fsync_failure_can_be_retried(witness, tmp_path, monkeypatch):
    service = FixtureService(tmp_path / "fsync.sock", witness)
    real = diagnostics.files.os.fsync

    def fail(_fd):
        raise OSError("fsync unavailable")

    monkeypatch.setattr(diagnostics.files.os, "fsync", fail)
    assert service._report(OSError(28, "full"), "request").diagnostic_error == "OSError"
    monkeypatch.setattr(diagnostics.files.os, "fsync", real)
    assert service._report(OSError(28, "full"), "request").diagnostic_error is None
    assert json.loads(service.diagnostic_path.read_text())["category"] == "BLOCKED_EXTERNAL"


@pytest.mark.parametrize("error,category", [
    (OSError(28, "disk full"), "BLOCKED_EXTERNAL"),
    (WitnessError("corrupt"), "BLOCKED_ACCOUNTING"),
    (RuntimeError("unexpected"), "BLOCKED_ENGINEERING"),
])
def test_native_failure_record_retains_service_category_and_evidence(witness, tmp_path, error, category):
    from tools.inventory_recovery_v3.failures import failure_record, validate_failure

    service = FixtureService(tmp_path / "native.sock", witness)
    stopped = service._report(error, "request")
    record = failure_record(stopped, phase="control-reader")
    assert validate_failure(record) == record
    assert record["category"] == category
    assert record["evidence"]["origin"]["control_service"] == stopped.record
    assert record["retry_authorized"] is False


def test_protection_drift_after_listener_start_is_reported(witness, tmp_path, monkeypatch):
    service = FixtureService(tmp_path / "drift.sock", witness)
    stop, ready, failures = threading.Event(), threading.Event(), []
    original = service._check

    def check():
        original()
        if ready.is_set():
            raise WitnessError("permission drift")

    monkeypatch.setattr(service, "_check", check)

    def run():
        try:
            service.serve(stop)
        except ServiceFailure as error:
            failures.append(error)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not service.path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    ready.set()
    try:
        with pytest.raises((OSError, WitnessError)):
            FixtureReader(service.path, genesis=GENESIS, configuration=CONFIG).snapshot()
        thread.join(8)
    finally:
        stop.set()
        thread.join(8)
    assert not thread.is_alive() and len(failures) == 1
    assert failures[0].category == "BLOCKED_ACCOUNTING"
    assert json.loads(service.diagnostic_path.read_text())["phase"] == "request"
