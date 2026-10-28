"""Forward complete leases and consume entry capsules at the two job edges."""

import json
import os
from contextlib import contextmanager

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3 import (
    job_ownership,
    launch_handoff,
    ownership,
    ownership_roles,
)
from tools.inventory_recovery_v3.failures import RecoveryStop

RECEIVED = "HUMANVOICE_RECOVERY_RECEIVED_FDS"
ENVIRONMENT_KEYS = (ownership.CAPSULE, RECEIVED, launch_handoff.CAPSULE, job_ownership.CAPSULE,
                    "HUMANVOICE_CHAINED_HANDOVER_FDS", "HUMANVOICE_HISTORY_HANDOVER_FDS")


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_OWNERSHIP", detail)


def require_lease(lease, configuration, role):
    require(isinstance(lease, ownership.Lease) and lease.membership.role == role
            and lease.membership.configuration == digest(configuration),
            "Launch lease differs from its admitted role or configuration")
    lease.check()


def options(lease):
    selected = lease.capsule()
    environment = {key: value for key, value in os.environ.items() if key not in ENVIRONMENT_KEYS}
    return {"pass_fds": selected["pass_fds"], "env": {**environment, **selected["environment"],
            RECEIVED: json.dumps(selected["pass_fds"])}}


@contextmanager
def worker_launch(parent, implementation, job, handoff, *, leaf):
    configuration = implementation.config()
    require_lease(parent, configuration, "monitor")
    request = implementation.checked_request(implementation.OUTPUT, job)
    original = json.loads(handoff["environment"][launch_handoff.CAPSULE])
    descriptor = launch_handoff.require_inherited(implementation.OUTPUT, job, request, original,
                                                  stop_check=leaf)
    derive = lambda: ownership_roles.expected(configuration, "worker", job=job,
                                               checked_request=implementation.checked_request)
    with ownership.extend(parent, derive, leaf=leaf, borrowed={"job": descriptor}) as lease:
        remapped = {key: value for key, value in original.items() if key != "identity"}
        remapped["descriptor"] = lease.descriptor("job")
        remapped["identity"] = digest(remapped)
        selected = options(lease)
        selected["env"][launch_handoff.CAPSULE] = json.dumps(remapped, sort_keys=True)
        yield lease, selected


@contextmanager
def campaign_launch(parent, implementation, job, request, *, leaf):
    configuration = implementation.config()
    require_lease(parent, configuration, "worker")
    derive = lambda: ownership_roles.expected(configuration, "campaign", job=job,
                                               checked_request=implementation.checked_request)
    with ownership.extend(parent, derive, leaf=leaf) as lease:
        selected = options(lease)
        selected["env"]["HUMANVOICE_SUPERVISOR_JOB"] = job
        selected["env"][job_ownership.CAPSULE] = job_ownership.prepare(
            implementation.OUTPUT, job, request, (lease.descriptor("job"),))
        yield lease, selected


@contextmanager
def entry(implementation, job, role, *, leaf):
    """Only executable entry owns received originals; no borrowed use here."""
    require(role in {"worker", "campaign"} and callable(leaf), "Unknown owned child entry")
    # The fixed launcher supplies a separate cleanup inventory matching its
    # Popen pass_fds. Malformed/duplicate capsule rows cannot redefine it.
    inventory = json.loads(os.environ.get(RECEIVED, "null"))
    require(isinstance(inventory, list) and bool(inventory)
            and all(type(fd) is int and fd >= 3 for fd in inventory)
            and len(set(inventory)) == len(inventory), "Owned child lacks its explicit received FD inventory")
    received = tuple(inventory)
    raw = os.environ.get(ownership.CAPSULE, "null")
    try:
        capsule = json.loads(raw)
    except ValueError:
        capsule = raw
    configuration = None

    def incoming():
        nonlocal configuration

        require(isinstance(capsule, dict) and isinstance(capsule.get("descriptors"), list),
                "Owned child lacks its complete incoming capsule")
        configuration = implementation.config()
        request = implementation.checked_request(implementation.OUTPUT, job)
        if role == "worker":
            legacy = json.loads(os.environ.get(launch_handoff.CAPSULE, "null"))
            descriptor = launch_handoff.require_inherited(implementation.OUTPUT, job, request,
                                                          legacy, stop_check=leaf)
        else:
            descriptor = job_ownership.require(implementation.OUTPUT, job, request)["descriptor"]
        matches = [row for row in capsule["descriptors"] if isinstance(row, dict) and row.get("role") == "job"]
        require(len(matches) == 1 and matches[0]["descriptor"] == descriptor,
                "Legacy child capsule differs from complete job ownership")

    def derive():
        require(implementation.config() == configuration, "Child configuration changed")
        return ownership_roles.expected(configuration, role, job=job,
                                        checked_request=implementation.checked_request)

    with ownership.inherit(derive, capsule, leaf=leaf, received=received, incoming_check=incoming) as lease:
        for key in ENVIRONMENT_KEYS:
            os.environ.pop(key, None)
        if role == "campaign":
            request = implementation.checked_request(implementation.OUTPUT, job)
            _directory, _ack, binding = job_ownership.binding(implementation.OUTPUT, job, request)
            remapped = {**binding, "descriptor": lease.descriptor("job")}
            remapped["identity"] = digest(remapped)
            os.environ[job_ownership.CAPSULE] = json.dumps(remapped, sort_keys=True)
        try:
            yield lease
        finally:
            for key in ENVIRONMENT_KEYS:
                os.environ.pop(key, None)
