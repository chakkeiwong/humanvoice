"""Bounded first-failure evidence; observations never authorize a restart."""

import json
import sqlite3
import time
from copy import deepcopy

import control_files as files
from control_witness import WitnessError, encode, identity, require

VERSION = "control-read-service-failure-v1"
PHASES = {"startup", "listener", "request"}


def failure_record(witness, error, phase):
    require(phase in PHASES, "Unknown read-service failure phase")
    original = error.__cause__ if error.__cause__ is not None else error
    if isinstance(original, (OSError, sqlite3.OperationalError)):
        category = "BLOCKED_EXTERNAL"
    elif isinstance(original, (WitnessError, ValueError, KeyError, TypeError, sqlite3.DatabaseError)):
        category = "BLOCKED_ACCOUNTING"
    else:
        category = "BLOCKED_ENGINEERING"
    # Exception text may contain request bytes, paths or credentials. Retain
    # only a bounded exception class and a numeric errno in this public record.
    return identity({"version": VERSION, "genesis": witness.genesis,
        "configuration": witness.configuration, "phase": phase, "category": category,
        "error_type": type(original).__name__[:80],
        "errno": original.errno if isinstance(original, OSError) and type(original.errno) is int else None,
        "observed_at": time.time(), "dispatch_allowed": False,
        "automatic_repair": False, "release_acceptance": False})


def retain(path, record):
    """Caller owns protected-path checks; preserve the first exact bound failure.

    A single service owner publishes after worker join. The immutable incident
    survives restart and is not erased by a later successful read. It is status
    evidence only, not latest-state admission. Host installation must provide
    separately approved incident acknowledgement/rotation.
    """
    raw = files.read(path)
    if raw is not None:
        previous = json.loads(raw)
        require(isinstance(previous, dict) and set(previous) == set(record)
                and previous == identity({k: v for k, v in previous.items() if k != "identity"})
                and all(previous.get(k) == record[k] for k in
                        ("version", "genesis", "configuration", "dispatch_allowed",
                         "automatic_repair", "release_acceptance")),
                "Retained service incident changed or belongs to another witness")
        # Retry both file and parent fsync, including a prior failed fsync.
        files.write(path, raw, expected=[raw])
        return previous
    files.write(path, (encode(record) + "\n").encode(), expected=[None])
    return record


class ServiceFailure(RuntimeError):
    """Owner-visible failure, including evidence when diagnostic storage fails."""

    def __init__(self, record, *, diagnostic_error=None):
        self.record = deepcopy(record)
        self.category = record["category"]
        self.diagnostic_error = diagnostic_error
        self.evidence = {"control_service": deepcopy(record), "diagnostic_error": diagnostic_error}
        super().__init__("Witness read service stopped: " + record["category"])
