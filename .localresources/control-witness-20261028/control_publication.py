"""Witness-first stop/resume publication and read-only runtime evidence.

No public CLI is enabled. The installer must pin this code, the anchor and the
writer action in protected storage. Tests use explicitly named fixture writers.
"""

import fcntl
import os
import secrets
import stat
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import control_files as files
import control_semantics as semantics
from control_service import (
    protected_database,
    protected_directory,
    protected_projection,
)
from control_witness import checksum, encode, identity, require


def encoded(value):
    return (encode(value) + "\n").encode()


def image(value):
    return None if value is None else value.encode("utf-8")


def head(anchor, sequence, committed, pending=None):
    return identity({"version": semantics.VERSION, "genesis": anchor["identity"],
                     "sequence": sequence, "committed_head": committed, "pending": pending})


def local_heads(anchor, snapshot):
    before = head(anchor, snapshot["sequence"], snapshot["committed_head"])
    pending = snapshot["pending"]
    if pending is None:
        return [before]
    return [before, head(anchor, snapshot["sequence"], snapshot["committed_head"], pending["identity"]),
            head(anchor, pending["sequence"], pending["identity"])]


def inspect_local(anchor, snapshot, *, allow_pending=False):
    root = Path(anchor["directory"])
    require(files.members(root) == ["events", "genesis.json", "head.json"],
            "Local control root membership changed")
    require(files.read(root / "genesis.json") == encoded(anchor), "Local control genesis changed")
    pending = snapshot["pending"] if allow_pending else None
    require(allow_pending or snapshot["pending"] is None, "Witness publication is pending")
    require(files.read(root / "head.json") in [encoded(value) for value in local_heads(anchor, snapshot)],
            "Local head is missing, rolled back or outside the witnessed transaction")
    names = {event["identity"] + ".json" for event in snapshot["events"]}
    actual = set(files.members(root / "events"))
    require(names <= actual <= names | ({pending["identity"] + ".json"} if pending else set()),
            "Local event membership changed or lost a committed event")
    for event in snapshot["events"] + ([pending] if pending else []):
        raw = files.read(root / "events" / (event["identity"] + ".json"))
        require(raw == encoded(event) or event is pending and raw is None,
                "Local event differs from the authenticated witness")


def inspect_projections(state):
    for path, content in semantics.projections(state).items():
        require(files.read(path) == image(content), "Stop/resume projection changed or rolled back")


class Publisher:
    """Host-writer operations; ordinary workspace execution fails before writes."""

    def __init__(self, anchor, witness):
        self.anchor = deepcopy(semantics.validate_anchor(anchor))
        self.witness = witness
        require(witness.genesis == anchor["identity"] and witness.configuration == anchor["configuration"],
                "Publisher differs from its pinned witness")

    def _authority(self):
        require(os.geteuid() == 0, "Control publication requires the protected host writer")
        protected_database(self.witness.path)
        protected_directory(self.witness.path.parent)
        root = Path(self.anchor["directory"])
        protected_directory(root.parent)
        events = root / "events"
        for selected in (root, events):
            if os.path.lexists(selected):
                protected_directory(selected)
        if os.path.lexists(events):
            for name in files.members(events):
                protected_projection(str(events / name))
        for binding in self.anchor["bindings"]:
            for name in ("user-stop.json", "resume-authorization.json"):
                protected_projection(str(Path(binding["root"]) / name))
        # Before provision the local root may be absent. Its existing parent
        # is already protected; only inspect child leaves once it exists.
        if os.path.lexists(root):
            for name in ("genesis.json", "head.json"):
                protected_projection(str(root / name))
        return True

    def _clock(self):
        return time.time()

    def _cut(self, _name):
        """Explicit deterministic offline crash hooks; production does nothing."""

    @contextmanager
    def _locked(self):
        self._authority()
        path = self.witness.path.with_name("publication.lock")
        with files.directory(path.parent) as parent:
            descriptor = os.open(path.name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            with os.fdopen(descriptor, "a") as handle:
                info = os.fstat(handle.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                        and info.st_uid == os.geteuid() and info.st_mode & 0o077 == 0,
                        "Host publication lock is not private and regular")
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._authority()
                yield

    def _snapshot(self):
        self._authority()
        value = self.witness.snapshot(secrets.token_hex(32))
        semantics.replay(self.anchor, value)
        return value

    def provision(self):
        """Host-only initialization; only retained pending intent can be repaired."""
        with self._locked():
            observed = self._snapshot()
            if observed["publication"] == "ready":
                return self._repair(observed)
            if observed["publication"] == "absent":
                require(not os.path.lexists(self.anchor["directory"]),
                        "Fresh publication cannot replace existing local state")
                inspect_projections(self.anchor["initial"])
                self.witness.begin_publication()
                self._cut("initialize-witness")
            return self._provision(self._snapshot())

    def _provision(self, observed):
        require(observed["publication"] == "pending" and observed["sequence"] == 0
                and observed["pending"] is None, "Local initialization lacks retained pending intent")
        inspect_projections(self.anchor["initial"])
        root = Path(self.anchor["directory"])
        if not os.path.lexists(root):
            files.mkdir(root)
        require(set(files.members(root)) <= {"events", "genesis.json", "head.json"},
                "Pending local initialization has foreign members")
        if not os.path.lexists(root / "events"):
            files.mkdir(root / "events")
        require(not files.members(root / "events"), "Pending initialization already contains events")
        self._cut("initialize-directories")
        files.write(root / "genesis.json", encoded(self.anchor), expected=[None, encoded(self.anchor)])
        self._cut("initialize-genesis")
        initial = encoded(local_heads(self.anchor, observed)[0])
        files.write(root / "head.json", initial, expected=[None, initial])
        self._cut("initialize-head")
        inspect_local(self.anchor, observed)
        inspect_projections(self.anchor["initial"])
        self._authority()
        self.witness.finish_publication()
        self._cut("initialize-complete")
        return self._snapshot()

    def _repair(self, observed):
        if observed["publication"] == "pending":
            return self._provision(observed)
        require(observed["publication"] == "ready", "No host-approved publication initialization exists")
        state, following = semantics.replay(self.anchor, observed)
        pending = observed["pending"]
        inspect_local(self.anchor, observed, allow_pending=True)
        if pending is None:
            inspect_projections(state)
            return observed
        root = Path(self.anchor["directory"])
        candidates = [encoded(value) for value in local_heads(self.anchor, observed)]
        current = files.read(root / "head.json")
        # Never regress a local committed head when recovery reopens after its
        # publication but before witness commit.
        if current != candidates[-1]:
            files.write(root / "head.json", candidates[1], expected=candidates[:2])
        self._cut("local-intent")
        event_path = root / "events" / (pending["identity"] + ".json")
        files.write(event_path, encoded(pending), expected=[None, encoded(pending)])
        self._cut("local-event")
        prior, desired = semantics.projections(state), semantics.projections(following)
        for index, (path, content) in enumerate(desired.items()):
            files.write(path, image(content), expected=[image(prior[path]), image(content)])
            self._cut("projection-" + str(index))
        inspect_projections(following)
        files.write(root / "head.json", candidates[-1], expected=candidates)
        self._cut("local-commit")
        self._authority()
        inspect_local(self.anchor, observed, allow_pending=True)
        self.witness.commit(pending["sequence"], pending["identity"])
        self._cut("witness-commit")
        final = self._snapshot()
        require(final["pending"] is None and final["sequence"] == pending["sequence"]
                and final["committed_head"] == pending["identity"], "Witness changed during host publication")
        inspect_local(self.anchor, final)
        inspect_projections(following)
        return final

    def repair(self):
        with self._locked():
            return self._repair(self._snapshot())

    def publish(self, action, root, request_id):
        with self._locked():
            observed = self._snapshot()
            require(observed["publication"] == "ready", "Complete pending initialization before a control action")
            for event in observed["events"] + ([observed["pending"]] if observed["pending"] else []):
                command = event["command"]
                if command["request_id"] == request_id:
                    require(command["action"] == action and command["root"] == root,
                            "Host request ID cannot be repurposed")
                    if event is observed["pending"]:
                        return self._repair(observed)
                    inspect_local(self.anchor, observed, allow_pending=True)
                    if observed["pending"] is None:
                        state, _ = semantics.replay(self.anchor, observed)
                        inspect_projections(state)
                    return observed
            require(observed["pending"] is None, "Repair the retained pending command before a new action")
            state, _ = semantics.replay(self.anchor, observed)
            inspect_local(self.anchor, observed)
            inspect_projections(state)
            command = semantics.command(self.anchor, state, action, root, request_id, now=self._clock())
            self.witness.prepare(observed["sequence"], observed["committed_head"], command)
            self._cut("witness-prepare")
            return self._repair(self._snapshot())


class EvidenceReader:
    """Read-only before/after authenticated snapshots; never repairs projections."""

    def __init__(self, anchor, reader):
        self.anchor = deepcopy(semantics.validate_anchor(anchor))
        self.reader = reader
        require(reader.genesis == anchor["identity"] and reader.configuration == anchor["configuration"],
                "Control reader differs from its pinned witness")

    def __call__(self, configuration):
        require(semantics.native_digest(configuration) == self.anchor["configuration"],
                "Runtime configuration differs from host control genesis")
        before = self.reader.snapshot()
        state, _ = semantics.replay(self.anchor, before)
        require(before["publication"] == "ready", "Host publication initialization is incomplete")
        require(before["pending"] is None, "Witness publication is pending")
        inspect_local(self.anchor, before)
        inspect_projections(state)
        after = self.reader.snapshot()
        semantics.replay(self.anchor, after)
        projection = lambda value: {key: item for key, item in value.items() if key not in {"nonce", "identity"}}
        require(checksum(projection(before)) == checksum(projection(after)),
                "Witness advanced during read-only control inspection")
        return semantics.evidence(self.anchor, state)
