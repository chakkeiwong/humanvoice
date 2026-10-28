"""Process-local complete ownership leases; never a live admission grant."""

import fcntl
import json
import os
import threading
import uuid
from contextlib import contextmanager

from humanvoice.artifacts import digest
from tools import durable_program_supervisor as durable
from tools.inventory_recovery_v3.descriptors import exclusive_descriptor, identity
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.ownership_roles import Membership, distinct

CAPSULE = "HUMANVOICE_RECOVERY_OWNERSHIP"
VERSION = "inventory-complete-ownership-v1"
_consumed = set()
_consuming_process = None
_transfer_lock = threading.Lock()


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_OWNERSHIP", detail)


def close_all(descriptors):
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError:
            pass


class IncomingTransfer:
    """Own received references once, before any fallible admission callback."""

    def __init__(self, capsule, received):
        global _consuming_process

        # A raw JSON digest identifies malformed input too. A valid nonce is
        # additionally retired so rehashing/remapping the envelope cannot make
        # the same transferred capability new. Neither key grants admission.
        keys = {("envelope", digest(capsule))}
        nonce = capsule.get("nonce") if isinstance(capsule, dict) else None
        if isinstance(nonce, str) and nonce:
            keys.add(("nonce", nonce))
        process = durable.identity(os.getpid())
        require(process is not None, "Incoming transfer requires stable process identity")
        with _transfer_lock:
            if _consuming_process != process:
                _consumed.clear()
                _consuming_process = process
            require(not keys & _consumed, "Entrypoint capsule was already consumed")
            _consumed.update(keys)
        # Only the first claim reaches this assignment. A stale entry cannot
        # acquire cleanup ownership of FD numbers now belonging elsewhere.
        self.received = received

    def close(self):
        received, self.received = self.received, ()
        close_all(received)


class Lease:
    def __init__(self, derive, leaf):
        if not callable(derive) or not callable(leaf):
            raise TypeError("Ownership requires derivation and leaf admission predicates")
        self._derive, self._leaf = derive, leaf
        self.membership = derive()
        require(isinstance(self.membership, Membership), "Ownership requires canonical membership")
        distinct(self.membership.roles)
        self._process = durable.identity(os.getpid())
        require(self._process is not None, "Ownership requires a stable process identity")
        self._held = []
        self._active = False
        self._closed = False

    def _prefix(self):
        require(not self._closed and durable.identity(os.getpid()) == self._process,
                "Ownership lease ended or moved to another process")
        require(self._leaf() is True, "Leaf admission or stop predicate vetoed ownership")
        require(self._derive() == self.membership, "Canonical ownership membership changed")
        distinct(self.membership.roles)
        require(len(self._held) <= len(self.membership.roles), "Unexpected ownership prefix")
        for role, (descriptor, inode) in zip(self.membership.roles, self._held):
            exclusive_descriptor(role.path, descriptor)
            require(identity(os.fstat(descriptor)) == inode, "Owned descriptor was replaced")
        return True

    def check(self):
        require(self._active and len(self._held) == len(self.membership.roles),
                "Ownership lease is not complete and active")
        return self._prefix()

    def descriptor(self, name):
        self.check()
        for role, (descriptor, _inode) in zip(self.membership.roles, self._held):
            if role.name == name:
                return descriptor
        raise ValueError("Ownership lease lacks the requested role")

    def _append(self, descriptor):
        # Register the owned reference before any operation that can fail.
        self._held.append((descriptor, None))
        self._held[-1] = descriptor, identity(os.fstat(descriptor))
        self._prefix()

    def _activate(self):
        self._prefix()
        require(len(self._held) == len(self.membership.roles), "Ownership union is incomplete")
        self._active = True
        self.check()

    def capsule(self):
        self.check()
        rows = [{"role": role.name, "path": str(role.path), "descriptor": fd,
                 "device": inode[0], "inode": inode[1]}
                for role, (fd, inode) in zip(self.membership.roles, self._held)]
        record = {"version": VERSION, "membership": self.membership.record(),
                  "issuer": self._process, "nonce": uuid.uuid4().hex, "descriptors": rows}
        record["identity"] = digest(record)
        return {"pass_fds": tuple(row["descriptor"] for row in rows),
                "environment": {CAPSULE: json.dumps(record, sort_keys=True)}}

    def close(self):
        self._active, self._closed = False, True
        # Never LOCK_UN: descendants may still own the same open descriptions.
        close_all([fd for fd, _inode in self._held])
        self._held = []


def acquire_one(lease, role):
    lease._prefix()
    descriptor = os.open(role.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(descriptor)
        raise
    lease._append(descriptor)


@contextmanager
def acquire(derive, *, leaf):
    lease = Lease(derive, leaf)
    try:
        require(lease.membership.role == "monitor", "Only monitor entry acquires the base union")
        for role in lease.membership.roles:
            acquire_one(lease, role)
        lease._activate()
        yield lease
    finally:
        lease.close()


@contextmanager
def extend(parent, derive, *, leaf, borrowed=None):
    """Add checked job/stage roles; duplicate all ancestor references."""
    parent.check()
    lease = Lease(derive, leaf)
    borrowed = {} if borrowed is None else dict(borrowed)
    try:
        old, new = parent.membership, lease.membership
        allowed = {("monitor", "worker"), ("worker", "campaign"), ("campaign", "provider")}
        require((old.role, new.role) in allowed and old.configuration == new.configuration
                and new.roles[:len(old.roles)] == old.roles
                and (old.job_identity is None or old.job_identity == new.job_identity),
                "Ownership extension changed its ancestor roles or job")
        additions = new.roles[len(old.roles):]
        required = {"worker": ("job",), "campaign": (), "provider": ("execution", "executor")}[new.role]
        require(tuple(role.name for role in additions) == required
                and set(borrowed) <= set(required), "Ownership extension contains unexpected resources")
        for descriptor, _inode in parent._held:
            parent.check()
            lease._append(os.dup(descriptor))
        for role in additions:
            parent.check()
            if role.name in borrowed:
                exclusive_descriptor(role.path, borrowed[role.name])
                lease._append(os.dup(borrowed[role.name]))
            else:
                acquire_one(lease, role)
        parent.check()
        lease._activate()
        yield lease
    finally:
        lease.close()


def validate_capsule(lease, capsule):
    require(isinstance(capsule, dict) and set(capsule) == {"version", "membership", "issuer",
            "nonce", "descriptors", "identity"} and capsule.get("version") == VERSION
            and capsule.get("identity") == digest({k: v for k, v in capsule.items() if k != "identity"})
            and capsule.get("membership") == lease.membership.record()
            and isinstance(capsule.get("nonce"), str) and len(capsule["nonce"]) == 32,
            "Inherited capsule differs from canonical ownership")
    from tools.inventory_history_handover import owner

    require(owner(capsule["issuer"]) is not None, "Inherited capsule lost its issuer identity")
    rows = capsule["descriptors"]
    require(isinstance(rows, list) and len(rows) == len(lease.membership.roles),
            "Inherited capsule omits ownership roles")
    seen = set()
    for role, row in zip(lease.membership.roles, rows):
        require(isinstance(row, dict) and set(row) == {"role", "path", "descriptor", "device", "inode"}
                and row["role"] == role.name and row["path"] == str(role.path)
                and type(row["descriptor"]) is int and row["descriptor"] >= 3
                and type(row["device"]) is int and type(row["inode"]) is int
                and row["descriptor"] not in seen, "Inherited role or descriptor changed")
        descriptor = row["descriptor"]
        exclusive_descriptor(role.path, descriptor)
        require(identity(os.fstat(descriptor)) == (row["device"], row["inode"]),
                "Inherited capsule inode changed")
        seen.add(descriptor)
    return tuple(row["descriptor"] for row in rows)


@contextmanager
def inherit(derive, capsule, *, leaf, received=(), incoming_check=None):
    """Borrow by default; entrypoints explicitly transfer received FD ownership.

    A transferred entry capsule is single-use in this process, including on
    rejection. Only the explicit received tuple is ever closed on rejection.
    Borrowers never close the supplied references, even after validation fails.
    """
    require(isinstance(received, tuple) and all(type(fd) is int and fd >= 3 for fd in received)
            and len(set(received)) == len(received), "Invalid explicitly received descriptors")
    lease = None
    incoming = IncomingTransfer(capsule, received) if received else None
    try:
        if incoming_check is not None:
            require(bool(received) and callable(incoming_check),
                    "Incoming validation requires an explicit entrypoint transfer")
            incoming_check()
        lease = Lease(derive, leaf)
        lease._prefix()
        descriptors = validate_capsule(lease, capsule)
        if received:
            require(set(received) == set(descriptors), "Entrypoint received an incomplete or extra FD union")
        for descriptor in descriptors:
            lease._append(os.dup(descriptor))
        validate_capsule(lease, capsule)
        if incoming is not None:
            incoming.close()
        lease._activate()
        yield lease
    finally:
        if incoming is not None:
            incoming.close()
        if lease is not None:
            lease.close()
