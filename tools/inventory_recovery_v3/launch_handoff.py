"""Hold per-job ownership continuously from durable intent through acknowledgement."""

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools import durable_program_supervisor as durable
from tools.inventory_history_handover import owner
from tools.inventory_recovery_v3.descriptors import exclusive_descriptor
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path

CAPSULE = "HUMANVOICE_RECOVERY_LAUNCH_OWNER"
VERSION = "parent-held-job-launch-v1"


def request_binding(root, job, request):
    root = Path(root).absolute()
    if (not isinstance(job, str) or not job.startswith("job-") or not job[4:].isdigit()
            or len(job) > 16 or request.get("job_id") != job
            or request.get("phase") not in {"RUNNING", "ADMITTING"}
            or not request.get("run_id") or not request.get("config_identity")):
        raise ValueError("Launch handoff requires a source-bound supervised request")
    path = regular_path(root / "jobs" / job / "request.json")
    if read_json(path) != request:
        raise ValueError("Launch request differs from durable dispatch")
    return {"root": str(root), "job": job, "request_identity": durable.fingerprint(request),
            "config_identity": request["config_identity"], "run_id": request["run_id"]}


def validate(root, job, request):
    binding = request_binding(root, job, request)
    directory = Path(binding["root"]) / "jobs" / job
    record = read_json(regular_path(directory / "launch-intent.json"))
    lock = regular_path(directory / "worker.lock").stat()
    if (record.get("version") != VERSION
            or record.get("identity") != digest({key: value for key, value in record.items()
                                                  if key != "identity"})
            or any(record.get(key) != value for key, value in binding.items())
            or record.get("lock_device") != lock.st_dev or record.get("lock_inode") != lock.st_ino
            or record.get("monitor_owner") is None):
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Pre-ack launch intent lost its ownership binding")
    owner(record["monitor_owner"])
    return record


@contextmanager
def prepare(root, job, request, *, owner_check, stop_check):
    binding = request_binding(root, job, request)
    directory = Path(binding["root"]) / "jobs" / job
    path = regular_path(directory / "worker.lock")
    with os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Existing launch or child owns the job") from error
        if owner_check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Parent launch requires the current monitor owner")
        stop_check()
        if any((directory / name).exists() for name in
               ("ack.json", "result.json", "recovery.json", "launch-intent.json")):
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Existing launch intent cannot be retransmitted")
        stat = os.fstat(handle.fileno())
        record = {**binding, "version": VERSION, "monitor_owner": durable.identity(os.getpid()),
                  "lock_device": stat.st_dev, "lock_inode": stat.st_ino}
        record["identity"] = digest(record)
        persist(regular_path(directory / "launch-intent.json"), record)
        capsule = {"intent_identity": record["identity"], "descriptor": handle.fileno(), **binding}
        capsule["identity"] = digest(capsule)
        if owner_check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Monitor ownership changed before child launch")
        stop_check()
        yield {"pass_fds": (handle.fileno(),), "environment": {CAPSULE: json.dumps(capsule, sort_keys=True)},
               "intent": record}


def require_inherited(root, job, request, capsule, *, stop_check):
    binding = request_binding(root, job, request)
    record = validate(root, job, request)
    if (not isinstance(capsule, dict)
            or set(capsule) != {*binding, "intent_identity", "descriptor", "identity"}
            or capsule.get("identity") != digest({key: value for key, value in capsule.items()
                                                   if key != "identity"})
            or capsule.get("intent_identity") != record["identity"]
            or any(capsule.get(key) != value for key, value in binding.items())):
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Worker lacks inherited launch authority")
    directory = Path(binding["root"]) / "jobs" / job
    if any((directory / name).exists() for name in ("ack.json", "result.json", "recovery.json")):
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Worker launch has already been acknowledged or retired")
    descriptor = capsule["descriptor"]
    exclusive_descriptor(directory / "worker.lock", descriptor)
    stop_check()
    return descriptor


@contextmanager
def inherited(root, job, request, *, stop_check):
    capsule = json.loads(os.environ.get(CAPSULE, "null"))
    descriptor = require_inherited(root, job, request, capsule, stop_check=stop_check)
    directory = Path(root) / "jobs" / job
    with os.fdopen(os.dup(descriptor), "a") as handle:
        exclusive_descriptor(directory / "worker.lock", handle.fileno())
        yield handle
