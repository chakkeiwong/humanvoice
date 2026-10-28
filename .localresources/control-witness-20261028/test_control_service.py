"""Service lifecycle fixtures do not assert production root isolation."""

import socket
import struct
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

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
        with pytest.raises(WitnessError, match="exists"):
            FixtureService(path, witness).serve(threading.Event())
        assert reader.snapshot()["sequence"] == 0
    finally:
        stop.set()
        thread.join(8)
    assert not thread.is_alive() and not errors and not path.exists()


def test_production_service_rejects_unprotected_workspace(witness, tmp_path):
    with pytest.raises(WitnessError, match="protected|host"):
        ReadService(tmp_path / "host.sock", witness).serve(threading.Event())
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
