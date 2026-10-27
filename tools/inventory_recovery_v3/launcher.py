"""Prospective native launch adapter with continuous pre-ack job ownership."""

import os
import subprocess
import time
from pathlib import Path

from tools import durable_program_supervisor as durable
from tools import inventory_history_job as job_ownership
from tools.inventory_recovery_v3 import launch_handoff
from tools.inventory_recovery_v3.failures import RecoveryStop


def launch(monitor, implementation, command, *, spawn, owner_check, stop_check):
    if implementation.config() != monitor.config:
        raise ValueError("Prospective supervisor sources changed before launch")
    if owner_check() is not True:
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Launch requires admitted native monitor ownership")
    stop_check()
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
        with (monitor.root / "workers.log").open("ab") as log:
            child = spawn([*command, "worker", "--job", job], cwd=monitor.config["cwd"],
                          stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
                          pass_fds=handoff["pass_fds"], env={**os.environ, **handoff["environment"]})
        monitor.state["launcher"] = durable.identity(child.pid)
        monitor.publish()


def worker(implementation, job, *, spawn, stop_check):
    request = implementation.checked_request(implementation.OUTPUT, job)
    directory = Path(implementation.OUTPUT) / "jobs" / job
    with launch_handoff.inherited(implementation.OUTPUT, job, request, stop_check=stop_check) as lock:
        state = {"owner": durable.identity(os.getpid()), "acknowledged_at": time.time(),
                 "request_identity": durable.fingerprint(request), "phase": request["phase"],
                 "ownership_protocol": "inherited-worker-lock-v1"}
        durable.save(directory / "ack.json", state)
        try:
            implementation.checked_request(implementation.OUTPUT, job)
            stop_check()
            with (directory / "output.log").open("ab") as log:
                environment = {key: value for key, value in os.environ.items() if key != launch_handoff.CAPSULE}
                environment[job_ownership.CAPSULE] = job_ownership.prepare(
                    implementation.OUTPUT, job, request, (lock.fileno(),))
                child = spawn(request["command"], cwd=request["cwd"], stdin=subprocess.DEVNULL,
                              stdout=log, stderr=log, pass_fds=(lock.fileno(),),
                              env={**environment, "HUMANVOICE_SUPERVISOR_JOB": job})
                state["child_owner"] = durable.identity(child.pid)
                durable.save(directory / "ack.json", state)
                while child.poll() is None:
                    durable.save(directory / "heartbeat.json", {
                        "at": time.time(), "owner": state["owner"], "child_owner": state["child_owner"],
                        "request_identity": state["request_identity"]})
                    time.sleep(request["poll_seconds"])
            result = {"exit_code": child.returncode}
            if child.returncode:
                with (directory / "output.log").open("rb") as log:
                    log.seek(max(0, log.seek(0, os.SEEK_END) - 4000))
                    lines = log.read().decode("utf-8", errors="replace").strip().splitlines()
                result["error"] = lines[-1][:1500] if lines else "Owned worker failed without output"
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
            if getattr(error, "category", None) == "USER_STOPPED":
                raise
            result = {"exit_code": 90, "error": type(error).__name__ + ": " + str(error)}
        durable.save(directory / "result.json", {**result, "finished_at": time.time(),
                     "request_identity": state["request_identity"], "owner": state["owner"]})
        return result["exit_code"]
