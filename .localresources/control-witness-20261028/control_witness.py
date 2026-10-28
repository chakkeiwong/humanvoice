"""Durable witness transactions; host authentication belongs to the broker.

This storage core is not a public authority or a deployment entrypoint. Only
an authenticated host writer may call initialize/prepare/commit in production.
The runtime broker exposes snapshot only, with a fresh authenticated nonce.
Storage must be protected from the workspace UID; no trust callback can make
an ordinary workspace database a production witness.
"""

import hashlib
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

VERSION = "inventory-control-witness-v2"
MAX_COMMAND_BYTES = 1_048_576


class WitnessError(ValueError):
    """Missing, stale or incoherent witness evidence cannot authorize dispatch."""


def require(condition, message):
    if not condition:
        raise WitnessError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def checksum(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def identity(value):
    return {**value, "identity": checksum(value)}


def hash_value(value):
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def canonical(path):
    original = str(path)
    path = Path(path)
    require(path.is_absolute() and str(path) == original and ".." not in path.parts,
            "Witness path must be canonical")
    require(not any(p.is_symlink() for p in (path, *path.parents)),
            "Witness path cannot traverse a symlink")
    if path.exists():
        require(stat.S_ISREG(path.stat().st_mode), "Witness must be a regular database")
    for suffix in ("-journal", "-wal", "-shm"):
        extra = path.with_name(path.name + suffix)
        require(not extra.is_symlink(), "Witness journal cannot be a symlink")
        if extra.exists():
            require(stat.S_ISREG(extra.stat().st_mode), "Witness journal is not regular")
    return path


class Witness:
    """One pinned genesis, compare-and-swap preparation and idempotent commit."""

    def __init__(self, path, *, genesis, configuration):
        require(hash_value(genesis) and hash_value(configuration), "Invalid witness binding")
        self.path = canonical(path)
        self.genesis = genesis
        self.configuration = configuration

    @contextmanager
    def _connect(self, *, write=False):
        path = canonical(self.path)
        require(path.is_file(), "Initialized witness is missing; never recreate it")
        observed = path.stat()
        connection = sqlite3.connect(path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                     uri=True, timeout=1, isolation_level=None)
        try:
            current = canonical(path).stat()
            require((current.st_dev, current.st_ino) == (observed.st_dev, observed.st_ino),
                    "Witness path changed while opening")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            if write:
                connection.commit()
            else:
                connection.rollback()
        finally:
            connection.close()

    def initialize(self):
        """Host-only initial provision; existing or partial stores are never reset."""
        path = canonical(self.path)
        require(path.parent.is_dir(), "Host must provision witness directory")
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        with self._connect(write=True) as connection:
            connection.execute("CREATE TABLE binding (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                               "version TEXT NOT NULL, genesis TEXT NOT NULL, configuration TEXT NOT NULL)")
            connection.execute("CREATE TABLE head (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                               "sequence INTEGER NOT NULL, identity TEXT NOT NULL, pending TEXT)")
            connection.execute("CREATE TABLE events (sequence INTEGER PRIMARY KEY, identity TEXT UNIQUE NOT NULL, "
                               "request_id TEXT UNIQUE NOT NULL, body TEXT NOT NULL)")
            connection.execute("CREATE TABLE publication (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                               "phase TEXT NOT NULL)")
            connection.execute("INSERT INTO binding VALUES (1,?,?,?)",
                               (VERSION, self.genesis, self.configuration))
            connection.execute("INSERT INTO head VALUES (1,0,?,NULL)", (self.genesis,))
            connection.execute("INSERT INTO publication VALUES (1,'absent')")
        directory = os.open(path.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def event(self, sequence, previous, command):
        require(type(sequence) is int and sequence > 0 and hash_value(previous),
                "Invalid witness sequence or predecessor")
        require(isinstance(command, dict) and command
                and isinstance(command.get("request_id"), str)
                and 0 < len(command["request_id"]) <= 256, "Missing exact command request ID")
        try:
            content = encode(command)
        except (ValueError, TypeError) as error:
            raise WitnessError("Command is not a finite JSON object") from error
        require(len(content.encode()) <= MAX_COMMAND_BYTES, "Control command exceeds bounded storage")
        canonical_command = json.loads(content)
        require(canonical_command == command, "Command must use JSON-native values")
        return identity({"version": VERSION, "genesis": self.genesis,
                         "configuration": self.configuration, "sequence": sequence,
                         "previous": previous, "command": canonical_command})

    def _read(self, connection):
        require(connection.execute("PRAGMA quick_check").fetchall() == [("ok",)],
                "Witness database integrity check failed")
        require(connection.execute("SELECT singleton,version,genesis,configuration FROM binding").fetchall()
                == [(1, VERSION, self.genesis, self.configuration)], "Witness genesis/configuration changed")
        publication = connection.execute("SELECT singleton,phase FROM publication").fetchall()
        require(len(publication) == 1 and publication[0][0] == 1
                and publication[0][1] in {"absent", "pending", "ready"},
                "Witness publication initialization state is missing or malformed")
        heads = connection.execute("SELECT singleton,sequence,identity,pending FROM head").fetchall()
        require(len(heads) == 1 and heads[0][0] == 1, "Witness head is missing or ambiguous")
        _, sequence, committed, pending_raw = heads[0]
        require(type(sequence) is int and sequence >= 0 and hash_value(committed), "Malformed witness head")
        rows = connection.execute("SELECT sequence,identity,request_id,body FROM events ORDER BY sequence").fetchall()
        require(len(rows) == sequence, "Witness lost committed event membership")
        previous, events, requests = self.genesis, [], set()
        for expected, (number, event_id, request_id, raw) in enumerate(rows, 1):
            value = json.loads(raw)
            require(number == expected and isinstance(value, dict)
                    and value == self.event(number, previous, value["command"])
                    and raw == encode(value) and event_id == value["identity"]
                    and request_id == value["command"]["request_id"] and request_id not in requests,
                    "Witness committed event chain changed")
            previous = event_id
            requests.add(request_id)
            events.append(value)
        require(committed == previous, "Witness head differs from committed prefix")
        pending = json.loads(pending_raw) if pending_raw is not None else None
        if pending_raw is not None:
            require(isinstance(pending, dict)
                    and pending == self.event(sequence + 1, committed, pending["command"])
                    and pending_raw == encode(pending)
                    and pending["command"]["request_id"] not in requests,
                    "Witness pending command changed or was reused")
        return {"sequence": sequence, "committed_head": committed,
                "pending": pending, "events": events, "publication": publication[0][1]}

    def begin_publication(self):
        """Host-only durable initialization intent, never resets ready state."""
        with self._connect(write=True) as connection:
            state = self._read(connection)
            require(state["sequence"] == 0 and state["pending"] is None
                    and state["publication"] in {"absent", "pending"},
                    "Witness publication is already initialized or consumed")
            if state["publication"] == "absent":
                connection.execute("UPDATE publication SET phase='pending' WHERE singleton=1")

    def finish_publication(self):
        """Host-only completion after exact local genesis/head are durable."""
        with self._connect(write=True) as connection:
            state = self._read(connection)
            require(state["sequence"] == 0 and state["pending"] is None
                    and state["publication"] in {"pending", "ready"},
                    "Publication completion lacks its retained initialization intent")
            if state["publication"] == "pending":
                connection.execute("UPDATE publication SET phase='ready' WHERE singleton=1")

    def snapshot(self, nonce):
        """Read only. Broker authenticates this fresh nonce-bound response."""
        require(hash_value(nonce), "A fresh 256-bit client challenge is required")
        with self._connect() as connection:
            state = self._read(connection)
        return identity({"version": VERSION, "genesis": self.genesis,
                         "configuration": self.configuration, "nonce": nonce, **state})

    def prepare(self, expected_sequence, expected_head, command):
        """Host-only prepare retains the full command before workspace mutation."""
        require(type(expected_sequence) is int and expected_sequence >= 0
                and hash_value(expected_head), "Invalid compare-and-swap predecessor")
        event = self.event(expected_sequence + 1, expected_head, command)
        with self._connect(write=True) as connection:
            state = self._read(connection)
            for committed in state["events"]:
                if committed["command"]["request_id"] == command["request_id"]:
                    require(committed == event, "Request ID cannot name a different control command")
                    return {"status": "committed", "event": committed}
            require(state["sequence"] == expected_sequence
                    and state["committed_head"] == expected_head, "Stale witness compare-and-swap")
            if state["pending"] is not None:
                require(state["pending"] == event, "Another control command is pending")
            else:
                connection.execute("UPDATE head SET pending=? WHERE singleton=1", (encode(event),))
        return {"status": "pending", "event": event}

    def commit(self, sequence, event_identity):
        """Host-only commit after the exact event/workspace projections are durable."""
        require(type(sequence) is int and sequence > 0 and hash_value(event_identity),
                "Invalid witness commit identity")
        with self._connect(write=True) as connection:
            state = self._read(connection)
            if sequence <= state["sequence"]:
                require(state["events"][sequence - 1]["identity"] == event_identity,
                        "Commit retry differs from retained event")
                return state["events"][sequence - 1]
            event = state["pending"]
            require(event is not None and sequence == state["sequence"] + 1
                    and event["identity"] == event_identity, "Commit lacks the exact pending command")
            connection.execute("INSERT INTO events VALUES (?,?,?,?)",
                (sequence, event_identity, event["command"]["request_id"], encode(event)))
            connection.execute("UPDATE head SET sequence=?,identity=?,pending=NULL WHERE singleton=1",
                               (sequence, event_identity))
        return event
