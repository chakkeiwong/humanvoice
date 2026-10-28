"""Prospective native launch adapter with continuous pre-ack job ownership."""

import os
import subprocess
import time
from contextlib import ExitStack, nullcontext
from pathlib import Path
from types import SimpleNamespace

from tools import durable_program_supervisor as durable
from tools.inventory_recovery_v3 import (
    job_ownership,
    launch_handoff,
    launch_ownership,
    ownership,
)
from tools.inventory_recovery_v3.failures import RecoveryStop


def launch(monitor, implementation, command, *, spawn, owner_check, stop_check, lease=None, leaf=None):
    if lease is None and any(key in os.environ for key in launch_ownership.ENVIRONMENT_KEYS):
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Fallback launch cannot consume ambient ownership capsules")
    if implementation.config() != monitor.config:
        raise ValueError("Prospective supervisor sources changed before launch")
    if owner_check() is not True:
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Launch requires admitted native monitor ownership")
    stop_check()
    if lease is not None:
        launch_ownership.require_lease(lease, monitor.config, "monitor")
        if not callable(leaf):
            raise TypeError("Complete launch ownership requires a leaf predicate")
    sequence = monitor.state["sequence"] + 1
    job = f"job-{sequence:04d}"
    phase = monitor.state["phase"]
    action = {"RUNNING": "run", "ADMITTING": "admission"}[phase]
    request = {"phase": phase, "run_id": monitor.state["run_id"], "job_id": job,
               "command": monitor.config[action], "cwd": monitor.config["cwd"],
               "poll_seconds": monitor.config["poll_seconds"],
               "config_identity": durable.fingerprint(monitor.config)}
    directory = monitor.root / "jobs" / job
    implementation.immutable(monitor.root / "config.json", monitor.config)
    implementation.immutable(directory / "request.json", request)

    def publish():
        monitor.state.update(sequence=sequence, job=job, status="DISPATCHING",
                             dispatched_at=time.time(), launcher=None,
                             request_identity=durable.fingerprint(request))
        monitor.publish()

    if (directory / "launch-intent.json").exists():
        launch_handoff.validate(monitor.root, job, request)
        stop_check()
        publish()
        return
    with launch_handoff.prepare(monitor.root, job, request, owner_check=owner_check,
                                stop_check=stop_check) as handoff:
        publish()
        if implementation.checked_request(monitor.root, job) != request:
            raise ValueError("Launch changed its durable dispatch")
        if owner_check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Monitor ownership changed before spawn")
        stop_check()
        selected = {"pass_fds": handoff["pass_fds"], "env": {**os.environ, **handoff["environment"]}}
        scope = launch_ownership.worker_launch(lease, implementation, job, handoff, leaf=leaf) if (
            lease is not None) else nullcontext((None, selected))
        with scope as (child_owner, selected), (monitor.root / "workers.log").open("ab") as log:
            if child_owner is not None:
                child_owner.check()
            if owner_check() is not True:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Monitor lost ownership immediately before spawn")
            stop_check()
            child = spawn([*command, "worker", "--job", job], cwd=monitor.config["cwd"],
                          stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
                          **selected)
        monitor.state["launcher"] = durable.identity(child.pid)
        monitor.publish()


def worker(implementation, job, *, spawn, stop_check, lease=None, leaf=None):
    request = implementation.checked_request(implementation.OUTPUT, job)
    directory = Path(implementation.OUTPUT) / "jobs" / job
    with ExitStack() as stack:
        if lease is None:
            if ownership.CAPSULE in os.environ:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Complete incoming ownership must be consumed at entry")
            lock = stack.enter_context(launch_handoff.inherited(implementation.OUTPUT, job, request,
                                                               stop_check=stop_check))
        else:
            launch_ownership.require_lease(lease, implementation.config(), "worker")
            if not callable(leaf):
                raise TypeError("Complete worker ownership requires a leaf predicate")
            lock = SimpleNamespace(fileno=lambda: lease.descriptor("job"))
        state = {"owner": durable.identity(os.getpid()), "acknowledged_at": time.time(),
                 "request_identity": durable.fingerprint(request), "phase": request["phase"],
                 "ownership_protocol": "inherited-worker-lock-v1"}
        durable.save(directory / "ack.json", state)
        child, spawn_attempted, child_finished = None, False, False
        try:
            implementation.checked_request(implementation.OUTPUT, job)
            stop_check()
            with (directory / "output.log").open("ab") as log:
                environment = {key: value for key, value in os.environ.items() if key != launch_handoff.CAPSULE}
                environment[job_ownership.CAPSULE] = job_ownership.prepare(
                    implementation.OUTPUT, job, request, (lock.fileno(),))
                selected = {"pass_fds": (lock.fileno(),),
                            "env": {**environment, "HUMANVOICE_SUPERVISOR_JOB": job}}
                scope = launch_ownership.campaign_launch(lease, implementation, job, request, leaf=leaf) if (
                    lease is not None) else nullcontext((None, selected))
                with scope as (child_owner, selected):
                    if child_owner is not None:
                        child_owner.check()
                    stop_check()
                    spawn_attempted = True
                    child = spawn(request["command"], cwd=request["cwd"], stdin=subprocess.DEVNULL,
                                  stdout=log, stderr=log, start_new_session=True, **selected)
                state["child_owner"] = durable.identity(child.pid)
                ack_pending = True
                while True:
                    if ack_pending:
                        try:
                            durable.save(directory / "ack.json", state)
                            ack_pending = False
                        except OSError as error:
                            state["reporting_failures"] = state.get("reporting_failures", 0) + 1
                            state["last_reporting_error"] = type(error).__name__ + ": " + str(error)
                    if child.poll() is not None:
                        from tools.recovery_observation import group_members

                        # The leader may exit while descendants still retain
                        # the job. Only an empty owned process group is final.
                        if not group_members(child.pid):
                            child_finished = True
                            break
                    try:
                        durable.save(directory / "heartbeat.json", {
                            "at": time.time(), "owner": state["owner"], "child_owner": state["child_owner"],
                            "request_identity": state["request_identity"]})
                    except OSError as error:
                        state["reporting_failures"] = state.get("reporting_failures", 0) + 1
                        state["last_reporting_error"] = type(error).__name__ + ": " + str(error)
                        ack_pending = True
                    time.sleep(request["poll_seconds"])
                if ack_pending:
                    # A failed terminal acknowledgement leaves recovery work;
                    # it cannot invent a successful reporting publication.
                    durable.save(directory / "ack.json", state)
            result = {"exit_code": child.returncode}
            if child.returncode:
                with (directory / "output.log").open("rb") as log:
                    log.seek(max(0, log.seek(0, os.SEEK_END) - 4000))
                    lines = log.read().decode("utf-8", errors="replace").strip().splitlines()
                result["error"] = lines[-1][:1500] if lines else "Owned worker failed without output"
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
            if getattr(error, "category", None) == "USER_STOPPED":
                raise
            if spawn_attempted and not child_finished:
                # Unknown spawn/observation state retains ack and child locks.
                # Cold supervision must prove quiescence before retiring it.
                raise
            result = {"exit_code": 90, "error": type(error).__name__ + ": " + str(error)}
        durable.save(directory / "result.json", {**result, "finished_at": time.time(),
                     "request_identity": state["request_identity"], "owner": state["owner"]})
        return result["exit_code"]
