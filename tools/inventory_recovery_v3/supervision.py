"""Single-decision supervision with quiescent, source-bound crash recovery."""

import math
import os
import time
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools import durable_program_supervisor as durable
from tools.inventory_recovery_v3 import restart_history
from tools.inventory_recovery_v3.failures import RecoveryStop


class RestartPublicationError(RuntimeError):
    pass


class ReportingPublicationError(RuntimeError):
    pass


def acknowledgement(directory, request):
    path = directory / "ack.json"
    record = read_json(path) if path.exists() else None
    if record is not None and (
        record.get("request_identity") != durable.fingerprint(request)
        or record.get("phase") != request["phase"]
        or record.get("ownership_protocol") != "inherited-worker-lock-v1"
        or not isinstance(record.get("owner"), dict)
        or not record["owner"]
    ):
        raise ValueError("Worker acknowledgement lost its bound ownership identity")
    return record


def result_record(directory, request, ack):
    path = directory / "result.json"
    result = read_json(path) if path.exists() else None
    if result is not None:
        ack = acknowledgement(directory, request)
    if result is not None and (
        type(result.get("exit_code")) is not int or not ack
        or result.get("request_identity") != durable.fingerprint(request)
        or result.get("owner") != ack["owner"]
    ):
        raise ValueError("Worker result differs from its acknowledged immutable request")
    return result


def recover(monitor, implementation, recovery):
    directory = monitor.root / "jobs" / monitor.state["job"]
    request = implementation.checked_request(monitor.root, monitor.state["job"])
    ack = acknowledgement(directory, request)
    owners = [(ack or {}).get("owner"), (ack or {}).get("child_owner"),
              monitor.state.get("launcher")]
    if any(durable.alive(owner) for owner in owners):
        recovery.observe(monitor)
        return
    if ack is None and monitor.state.get("launcher") is None:
        from tools.inventory_recovery_v3 import launch_handoff

        intent = directory / "launch-intent.json"
        if intent.exists():
            handoff = launch_handoff.validate(monitor.root, monitor.state["job"], request)
            if (durable.alive(handoff["monitor_owner"])
                    and handoff["monitor_owner"] != durable.identity(os.getpid())):
                recovery.observe(monitor)
                return
        else:
            recovery.observe(monitor)
            monitor.state.update(ownership_phase="UNRESOLVED_LAUNCH_OWNERSHIP",
                                 next_action="Await authenticated launch acknowledgement; do not seize job lock or charge restart")
            monitor.publish()
            return
    value = recovery.campaign.cursor()
    try:
        with recovery.ownership(directory, value):
            recovery.control.require_running()
            recovery.campaign.require_admission()
            request = implementation.checked_request(monitor.root, monitor.state["job"])
            ack = acknowledgement(directory, request)
            result = result_record(directory, request, ack)
            if result is not None and result["exit_code"] >= 0 and not recovery.paused_result(
                    monitor, directory, result):
                monitor.transition(result)
                return
            owners = [(ack or {}).get("owner"), (ack or {}).get("child_owner"),
                      monitor.state.get("launcher")]
            if any(durable.alive(owner) for owner in owners):
                recovery.observe(monitor)
                return
            if recovery.campaign.cursor() != value:
                raise ValueError("Recovery cursor changed under exclusive ownership")
            def check():
                recovery.control.require_running()
                recovery.campaign.require_admission()
                if recovery.campaign.cursor() != value:
                    raise ValueError("Recovery cursor changed during restart publication")
                if implementation.checked_request(monitor.root, monitor.state["job"]) != request:
                    raise ValueError("Recovery request changed during restart publication")

            head = restart_history.read(monitor)
            receipts = [row["receipt"] for row in head["committed"]] if head else []
            ack_path, result_path = directory / "ack.json", directory / "result.json"
            evidence = {"cursor": value,
                        "ack_sha256": digest(ack_path.read_bytes()) if ack_path.exists() else None,
                        "result_sha256": digest(result_path.read_bytes()) if result_path.exists() else None}
            record = next((row for row in receipts if row["job"] == monitor.state["job"]), None)
            if record is None and head and head["pending"] is not None:
                record = head["pending"]
            if record is None:
                if len(receipts) >= monitor.config["maximum_worker_restarts"]:
                    raise RecoveryStop("BLOCKED_BUDGET", "Cumulative worker restart allowance exhausted")
                record = {**evidence, "job": monitor.state["job"], "run_id": monitor.state["run_id"],
                          "config_identity": monitor.state["config_identity"],
                          "request_identity": durable.fingerprint(request),
                          "worker_restart": len(receipts) + 1, "new_provider_calls": 0,
                          "action": "resume-with-native-reconciliation"}
                record["identity"] = digest(record)
            if any(record[key] != expected for key, expected in evidence.items()):
                raise ValueError("Pending recovery lost its exact cursor or process evidence")
            try:
                record = restart_history.commit(monitor, record, check)
                check()
                monitor.state.update(worker_restarts=max(len(receipts), record["worker_restart"]),
                                     last_job=monitor.state["job"], job=None, status="RESUMING",
                                     recovery_phase="RECONCILED_OWNERSHIP", worker_recovery=record)
                monitor.state.pop("restart_publication_error", None)
                monitor.notify("Dead worker is quiescent; reconcile native receipts before allocation")
                monitor.publish()
            except OSError as error:
                raise RestartPublicationError(str(error)) from error
    except BlockingIOError:
        recovery.observe(monitor)


def progress(monitor):
    observed = []
    for name in monitor.config["progress_files"]:
        path = Path(name)
        if path.is_file():
            stat = path.stat()
            observed.append([name, stat.st_mtime_ns, stat.st_size])
    signature = durable.fingerprint(observed)
    now = time.time()
    if signature != monitor.state.get("progress_signature"):
        monitor.state.update(progress_signature=signature, last_progress_at=now)
    monitor.state["progress_age_seconds"] = now - monitor.state.get("last_progress_at", now)
    warning = monitor.state["progress_age_seconds"] > monitor.config.get("progress_warning_seconds", 1800)
    if warning and not monitor.state.get("progress_warning"):
        monitor.notify("No observed progress; inspect the owned worker without terminating validation")
    monitor.state["progress_warning"] = warning
    monitor.publish()


def tick(monitor, implementation, recovery):
    try:
        recovery.control.require_running()
        monitor.flush_reporting_intent()
        restart_history.read(monitor)
        if monitor.state["status"] == "USER_STOPPED":
            monitor.state["status"] = monitor.state["phase"]
            monitor.publish()
        if monitor.state["status"] == "INVENTORY_VERIFIED" and not implementation.terminal_binding(monitor.state):
            raise ValueError("Retained inventory success lost its exact evidence")
        if monitor.state["status"] in implementation.TERMINAL:
            monitor.publish()
            return
        if monitor.state["job"] is None:
            recovery.control.require_running()
            monitor.launch()
            return
        directory = monitor.root / "jobs" / monitor.state["job"]
        request = implementation.checked_request(monitor.root, monitor.state["job"])
        ack = acknowledgement(directory, request)
        result = result_record(directory, request, ack)
        crashed = result is not None and (result["exit_code"] < 0 or recovery.paused_result(
            monitor, directory, result))
        if result is not None and not crashed:
            recovery.control.require_running()
            monitor.transition(result)
            return
        if crashed or ack and not durable.alive(ack["owner"]):
            recover(monitor, implementation, recovery)
            return
        if not ack and time.time() - monitor.state["dispatched_at"] > monitor.config["acknowledgement_seconds"]:
            recover(monitor, implementation, recovery)
            return
        if ack:
            heartbeat_path = directory / "heartbeat.json"
            if heartbeat_path.exists():
                heartbeat = read_json(heartbeat_path)
                stamp = heartbeat.get("at")
                if (heartbeat.get("request_identity") != durable.fingerprint(request)
                        or heartbeat.get("owner") != ack["owner"]
                        or type(stamp) not in (int, float) or not math.isfinite(stamp)):
                    raise ValueError("Worker heartbeat lost its acknowledged identity or timestamp")
                monitor.state["heartbeat_age_seconds"] = time.time() - stamp
                if monitor.state["heartbeat_age_seconds"] > monitor.config.get("heartbeat_warning_seconds", 120):
                    monitor.notify("Worker heartbeat stalled; preserve ownership without duplicate launch")
            monitor.state.update(status=monitor.state["phase"], worker_owner=ack["owner"])
        recovery.control.require_running()
        progress(monitor)
    except RestartPublicationError as error:
        monitor.state = read_json(restart_history.regular_path(monitor.root / "state.json"))
        restart_history.read(monitor)
        if monitor.state.get("job") is not None:
            monitor.state.update(recovery_phase="RESTART_PUBLICATION_RETRY",
                                 restart_publication_error=str(error))
        try:
            monitor.publish()
        except OSError as publication_error:
            raise RestartPublicationError(str(publication_error)) from publication_error
    except (RecoveryStop, recovery.program.execution.RecoveryBlocked) as error:
        monitor.state.update(status=error.category, blocker=str(error))
        monitor.notify(str(error))
        monitor.publish()
    except (OSError, ValueError, KeyError, TypeError) as error:
        monitor.block("Worker recovery requires reconciliation: " + str(error))


def monitor_class(base, implementation, recovery):
    class InventoryMonitor(base):
        def flush_reporting_intent(self):
            try:
                return super().flush_reporting_intent()
            except OSError as error:
                raise ReportingPublicationError(str(error)) from error

        def notify(self, reason):
            self.flush_reporting_intent()
            return super().notify(reason)

        def tick(self):
            try:
                return tick(self, implementation, recovery)
            except (RestartPublicationError, ReportingPublicationError) as error:
                self.state = read_json(restart_history.regular_path(self.root / "state.json"))
                restart_history.read(self)
                print("Publication retry deferred; durable state retained: " + str(error), flush=True)
            finally:
                try:
                    implementation.reporting.reporting.observe(self.root / "reporting", self.root)
                except OSError as error:
                    print("Reporting observation deferred: " + str(error), flush=True)

    return InventoryMonitor
