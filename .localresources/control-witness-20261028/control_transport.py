"""Bounded read-only Unix witness protocol; no publish operation is exposed.

Reader authenticates kernel peer credentials and a fresh challenge. Production
construction must pin root ownership and a host-approved fixed endpoint. The
test-only FixtureReader explicitly relaxes ownership in its separate module.
This file does not install a daemon or supply runtime admission.
"""

import json
import secrets
import socket
import stat
import struct
import time
from pathlib import Path

from control_witness import VERSION, WitnessError, checksum, encode, hash_value, require

MAX_BYTES = 8_388_608
MAX_REQUEST_BYTES = 4096
TIMEOUT = 5.0


def canonical_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate protocol field")
            result[key] = value
        return result

    def nonfinite(_value):
        raise WitnessError("Nonfinite protocol value")

    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=nonfinite)
    require(encode(value).encode() == raw, "Noncanonical witness protocol bytes")
    return value


def read_exact(connection, count, deadline):
    parts = []
    while count:
        remaining = deadline - time.monotonic()
        require(remaining > 0, "Witness read deadline exceeded")
        connection.settimeout(remaining)
        piece = connection.recv(min(count, 65536))
        require(bool(piece), "Incomplete witness frame")
        parts.append(piece)
        count -= len(piece)
    return b"".join(parts)


def receive(connection, deadline, maximum):
    size = struct.unpack("!I", read_exact(connection, 4, deadline))[0]
    require(0 < size <= maximum, "Witness frame exceeds its bound")
    return canonical_json(read_exact(connection, size, deadline))


def send(connection, value, deadline, maximum):
    raw = encode(value).encode()
    require(0 < len(raw) <= maximum, "Witness frame exceeds its bound")
    remaining = deadline - time.monotonic()
    require(remaining > 0, "Witness write deadline exceeded")
    connection.settimeout(remaining)
    connection.sendall(struct.pack("!I", len(raw)) + raw)


def endpoint(path, *, owner=0):
    original = str(path)
    path = Path(path)
    require(path.is_absolute() and str(path) == original and ".." not in path.parts,
            "Witness endpoint is not canonical")
    for selected in (path, *path.parents):
        metadata = selected.lstat()
        require(not stat.S_ISLNK(metadata.st_mode), "Witness endpoint contains a symlink")
        require(metadata.st_uid == owner, "Witness endpoint is not host owned")
        if selected == path:
            require(stat.S_ISSOCK(metadata.st_mode), "Witness endpoint is not a socket")
            # Socket access may be broad: the service exposes read only. Its
            # parent must prevent untrusted replacement of the listening name.
        else:
            require(stat.S_ISDIR(metadata.st_mode) and metadata.st_mode & 0o022 == 0,
                    "Witness endpoint parent is writable by an untrusted user")
    return path


def peer_uid(connection):
    credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", credentials)[1]


class Reader:
    """Root-pinned read-only transport. It has no write or reconnect fallback."""

    def __init__(self, path, *, genesis, configuration):
        require(hash_value(genesis) and hash_value(configuration), "Reader binding is invalid")
        self.path = str(path)
        self.genesis = genesis
        self.configuration = configuration

    def _path(self):
        return endpoint(self.path)

    def _peer(self, connection):
        require(peer_uid(connection) == 0, "Witness peer is not the host authority")

    def snapshot(self):
        nonce = secrets.token_hex(32)
        request = {"action": "snapshot", "version": VERSION,
                   "genesis": self.genesis, "configuration": self.configuration, "nonce": nonce}
        path = self._path()
        before = path.lstat()
        deadline = time.monotonic() + TIMEOUT
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(TIMEOUT)
            connection.connect(str(path))
            self._peer(connection)
            after = self._path().lstat()
            require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
                    "Witness endpoint changed during connection")
            send(connection, request, deadline, MAX_REQUEST_BYTES)
            response = receive(connection, deadline, MAX_BYTES)
            self._peer(connection)
        require(isinstance(response, dict) and set(response) == {"version", "genesis",
            "configuration", "nonce", "sequence", "committed_head", "pending", "events", "identity"}
            and response["version"] == VERSION and response["genesis"] == self.genesis
            and response["configuration"] == self.configuration and response["nonce"] == nonce
            and response["identity"] == checksum({k: v for k, v in response.items() if k != "identity"})
            and type(response["sequence"]) is int and response["sequence"] >= 0
            and hash_value(response["committed_head"]) and isinstance(response["events"], list)
            and len(response["events"]) == response["sequence"]
            and (response["pending"] is None or isinstance(response["pending"], dict)),
            "Witness response lost its fresh challenge or exact binding")
        return response


def serve_connection(connection, witness):
    """One bounded request; only read-only snapshots are reachable."""
    deadline = time.monotonic() + TIMEOUT
    request = receive(connection, deadline, MAX_REQUEST_BYTES)
    require(isinstance(request, dict) and set(request) == {"action", "version",
        "genesis", "configuration", "nonce"} and request["action"] == "snapshot"
        and request["version"] == VERSION and request["genesis"] == witness.genesis
        and request["configuration"] == witness.configuration and hash_value(request["nonce"]),
        "Read-only witness service rejects this request")
    response = witness.snapshot(request["nonce"])
    send(connection, response, deadline, MAX_BYTES)
