"""Real offline Unix connections with explicitly nonproduction peer fixtures."""

import os
import socket
import struct
import threading
import time
from pathlib import Path

import pytest

from control_transport import (
    MAX_BYTES,
    MAX_REQUEST_BYTES,
    TIMEOUT,
    Reader,
    endpoint,
    peer_uid,
    receive,
    send,
    serve_connection,
)
from control_witness import VERSION, WitnessError, checksum, identity
from test_control_witness import CONFIG, GENESIS, NONCE, command, witness

__all__ = ["witness"]


class FixtureReader(Reader):
    """Same-user socket fixture; never usable as host admission evidence."""

    def _path(self):
        path = Path(self.path)
        assert not path.is_symlink() and path.is_socket()
        return path

    def _peer(self, connection):
        assert peer_uid(connection) == os.getuid()


def run_server(tmp_path, callback):
    path = tmp_path / "read.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    server.settimeout(8)
    errors = []

    def run():
        try:
            with server:
                connection, _ = server.accept()
                with connection:
                    callback(connection)
        except (OSError, ValueError, AssertionError) as error:
            errors.append(error)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return path, thread, errors


def test_real_readonly_service_returns_fresh_pending_snapshot(witness, tmp_path):
    event = witness.prepare(0, GENESIS, command())["event"]
    before = witness.path.read_bytes()
    path, thread, errors = run_server(tmp_path, lambda connection: serve_connection(connection, witness))
    value = FixtureReader(path, genesis=GENESIS, configuration=CONFIG).snapshot()
    thread.join(8)
    assert not thread.is_alive() and not errors
    assert value["pending"] == event
    assert value["nonce"] != NONCE
    assert witness.path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["nonce", "configuration", "genesis", "identity",
                                      "missing", "extra", "sequence"])
def test_replayed_or_rebound_response_is_rejected(witness, tmp_path, mutation):
    def forged(connection):
        deadline = time.monotonic() + TIMEOUT
        request = receive(connection, deadline, MAX_REQUEST_BYTES)
        response = witness.snapshot(request["nonce"])
        if mutation == "missing":
            response.pop("events")
        elif mutation == "extra":
            response["authorization"] = True
        elif mutation == "sequence":
            response["sequence"] = False
        else:
            response[mutation] = checksum({"forged": mutation})
        if mutation != "identity":
            response = identity({key: value for key, value in response.items() if key != "identity"})
        send(connection, response, deadline, MAX_BYTES)
    path, thread, errors = run_server(tmp_path, forged)
    with pytest.raises(WitnessError):
        FixtureReader(path, genesis=GENESIS, configuration=CONFIG).snapshot()
    thread.join(8)
    assert not thread.is_alive() and not errors


@pytest.mark.parametrize("action", ["initialize", "prepare", "commit", "resume", "repair", "stop"])
def test_read_socket_cannot_publish_or_repair(witness, action):
    before = witness.path.read_bytes()
    left, right = socket.socketpair()
    with left, right:
        request = {"action": action, "version": VERSION, "genesis": GENESIS,
                   "configuration": CONFIG, "nonce": NONCE}
        send(left, request, time.monotonic() + TIMEOUT, MAX_REQUEST_BYTES)
        with pytest.raises(WitnessError, match="Read-only"):
            serve_connection(right, witness)
    assert witness.path.read_bytes() == before


@pytest.mark.parametrize("kind", ["oversized", "truncated", "duplicate", "noncanonical", "nan"])
def test_framing_faults_fail_closed(kind):
    left, right = socket.socketpair()
    with left, right:
        if kind == "oversized":
            wire = struct.pack("!I", MAX_BYTES + 1)
        elif kind == "truncated":
            wire = struct.pack("!I", 100) + b"{}"
        else:
            raw = {"duplicate": b'{"a":1,"a":2}',
                   "noncanonical": b'{ "a":1}', "nan": b'{"a":NaN}'}[kind]
            wire = struct.pack("!I", len(raw)) + raw
        left.sendall(wire)
        left.shutdown(socket.SHUT_WR)
        with pytest.raises(WitnessError):
            receive(right, time.monotonic() + TIMEOUT, MAX_BYTES)


def test_peer_credentials_are_kernel_derived():
    left, right = socket.socketpair()
    with left, right:
        assert peer_uid(left) == peer_uid(right) == os.getuid()
        if os.getuid() != 0:
            with pytest.raises(WitnessError, match="host authority"):
                Reader("/run/not-installed", genesis=GENESIS, configuration=CONFIG)._peer(left)


def test_unprotected_endpoint_never_passes_production_reader(tmp_path):
    path = tmp_path / "read.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(path))
        with pytest.raises(WitnessError, match="host owned|untrusted"):
            endpoint(path)
        link = tmp_path / "alias.sock"
        link.symlink_to(path)
        with pytest.raises(WitnessError, match="symlink"):
            endpoint(link)


def test_total_read_deadline_is_bounded():
    left, right = socket.socketpair()
    with left, right:
        started = time.monotonic()
        with pytest.raises((TimeoutError, WitnessError)):
            receive(right, started + 0.02, MAX_BYTES)
        assert time.monotonic() - started < 1
