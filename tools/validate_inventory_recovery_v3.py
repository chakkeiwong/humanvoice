"""Run fixed offline recovery regressions with exact source and test membership."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as element_tree
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import digest, read_json
from tools import durable_program_supervisor as durable
from tools import inventory_history_live as historical
from tools import review_inventory_recovery_v3 as review
from tools import validate_inventory_history as validation
from tools.inventory_recovery_v3.reservations import persist
from tools.recovery_observation import group_members

TESTS = (
    "tests/test_inventory_recovery_v3_policy.py",
    "tests/test_inventory_recovery_v3_corners.py",
    "tests/test_inventory_recovery_v3_dispatch.py",
    "tests/test_inventory_recovery_v3_native.py",
    "tests/test_inventory_recovery_v3_claim.py",
    "tests/test_inventory_recovery_v3_lineage.py",
    "tests/test_inventory_recovery_v3_capacity.py",
    "tests/test_inventory_recovery_v3_handover.py",
    "tests/test_inventory_recovery_v3_installed_authority.py",
    "tests/test_inventory_recovery_v3_terminal.py",
    "tests/test_inventory_recovery_v3_crash.py",
    "tests/test_inventory_recovery_v3_allocation.py",
    "tests/test_inventory_recovery_v3_settlement.py",
    "tests/test_inventory_recovery_v3_supervision.py",
    "tests/test_inventory_recovery_v3_launch.py",
    "tests/test_inventory_recovery_v3_owner.py",
    "tests/test_inventory_recovery_v3_native_ownership.py",
    "tests/test_inventory_recovery_v3_provider_capture.py",
    "tests/test_inventory_recovery_v3_provider_runtime.py",
    "tests/test_inventory_recovery_v3_runtime.py",
    "tests/test_inventory_recovery_v3_execution.py",
    "tests/test_inventory_recovery_v3_resume.py",
    "tests/test_inventory_recovery_v3_stage.py",
    "tests/test_inventory_recovery_v3_requests.py",
    "tests/test_inventory_recovery_v3_executor.py",
    "tests/test_inventory_recovery_v3_inheritance.py",
    "tests/test_inventory_recovery_v3_probe.py",
    "tests/test_inventory_recovery_v3_semantics.py",
    "tests/test_inventory_recovery_v3_registration.py",
    "tests/test_inventory_recovery_v3_continuation.py",
    "tests/test_inventory_recovery_v3_restart.py",
    "tests/test_inventory_recovery_v3_journal.py",
    "tests/test_inventory_recovery_v3_campaign_history.py",
    "tests/test_inventory_recovery_v3_campaign_binding.py",
    "tests/test_inventory_recovery_v3_configuration.py",
    "tests/test_inventory_recovery_v3_inspection.py",
    "tests/test_inventory_recovery_v3_consumption_floors.py",
    "tests/test_inventory_recovery_v3_floor_followup.py",
    "tests/test_inventory_recovery_v3_validation.py",
    "tests/test_inventory_recovery_v3_schema_replay.py",
    "tests/test_inventory_recovery_v3_descriptors.py",
    "tests/test_inventory_recovery_v3_ownership.py",
    "tests/test_inventory_recovery_v3_launch_ownership.py",
    "tests/test_inventory_recovery_v3_runtime_closure.py",
    "tests/test_inventory_recovery_v3_runtime_predicates.py",
    "tests/test_inventory_recovery_v3_initialization.py",
    "tests/test_inventory_recovery_v3_bootstrap.py",
    "tests/test_inventory_recovery_v3_receipt_bootstrap.py",
    "tests/test_inventory_campaign_progress.py",
    "tests/test_failure_first_native.py",
    "tests/test_inventory_history_live.py",
    "tests/test_inventory_history_current_stage.py",
    "tests/test_inventory_history_integration.py",
)

SCOPES = {
    "full": TESTS,
    "floors": tuple(name for name in TESTS if name in {
        "tests/test_inventory_recovery_v3_campaign_binding.py",
        "tests/test_inventory_recovery_v3_configuration.py",
        "tests/test_inventory_recovery_v3_inspection.py",
        "tests/test_inventory_recovery_v3_bootstrap.py",
        "tests/test_inventory_recovery_v3_campaign_history.py",
        "tests/test_inventory_recovery_v3_initialization.py",
        "tests/test_inventory_recovery_v3_owner.py",
        "tests/test_inventory_recovery_v3_native_ownership.py",
        "tests/test_inventory_recovery_v3_claim.py",
        "tests/test_inventory_recovery_v3_journal.py",
        "tests/test_inventory_recovery_v3_handover.py",
        "tests/test_inventory_recovery_v3_installed_authority.py",
        "tests/test_inventory_recovery_v3_stage.py",
        "tests/test_inventory_recovery_v3_receipt_bootstrap.py",
        "tests/test_inventory_recovery_v3_runtime.py",
        "tests/test_inventory_recovery_v3_consumption_floors.py",
        "tests/test_inventory_recovery_v3_floor_followup.py",
        "tests/test_inventory_recovery_v3_validation.py",
    }),
    "executor": ("tests/test_inventory_recovery_v3_executor.py",),
}


class CommandCleanupError(subprocess.SubprocessError):
    def __init__(self, evidence):
        self.evidence = evidence
        super().__init__("Offline command cleanup failed: " + json.dumps(evidence, sort_keys=True))


def cleanup(process, *, grace_seconds=2, kill_seconds=3):
    evidence = {"process_group": process.pid, "group_quiescent": False,
                "leader_reaped": False, "remaining": None, "errors": []}

    def observe():
        evidence.update(leader_reaped=False, remaining=None, group_quiescent=False)
        try:
            evidence["leader_reaped"] = process.poll() is not None
            evidence["remaining"] = group_members(process.pid)
            evidence["group_quiescent"] = not evidence["remaining"]
        except (OSError, ValueError, KeyboardInterrupt) as error:
            description = type(error).__name__ + ": " + str(error)
            if description not in evidence["errors"]:
                evidence["errors"].append(description)
            return False
        return evidence["leader_reaped"] and evidence["group_quiescent"]

    for selected, seconds in ((signal.SIGINT, grace_seconds), (signal.SIGKILL, kill_seconds)):
        deadline = time.monotonic() + seconds
        try:
            if observe():
                break
            try:
                os.killpg(process.pid, selected)
            except ProcessLookupError:
                pass
            while not observe() and time.monotonic() < deadline:
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        except (OSError, ValueError, KeyboardInterrupt) as error:
            evidence["errors"].append(type(error).__name__ + ": " + str(error))
    observe()
    evidence["complete"] = evidence["leader_reaped"] and evidence["group_quiescent"] and not evidence["errors"]
    return evidence


def command_run(command, *, log, timeout):
    process = subprocess.Popen(command, cwd=ROOT, env=validation.environment(),
                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    failure, owner = None, None
    try:
        owner = durable.identity(process.pid)
        return_code = process.wait(timeout=timeout)
        if return_code:
            raise subprocess.CalledProcessError(return_code, command)
    except BaseException as error:  # noqa: BLE001 -- clean owned workers, then re-raise the original failure
        failure = error
    evidence = {**cleanup(process), "owner": owner,
                "original_error": None if failure is None else type(failure).__name__ + ": " + str(failure)}
    if not evidence["complete"]:
        raise CommandCleanupError(evidence) from failure
    if failure is not None:
        raise failure


def binding():
    paths = set(TESTS) | {"tools/validate_inventory_recovery_v3.py",
        "tools/inventory_history_test_guard.py", "tools/validate_inventory_history.py",
        "tools/validate_failure_first.py", "pyproject.toml"}
    paths.update(str(path.relative_to(ROOT)) for path in (ROOT / "tests").rglob("*.py"))
    return {"candidate": review.sources(), "historical": historical.contract(),
            "dependencies": {name: digest((ROOT / name).read_bytes()) for name in sorted(paths)},
            "tests": list(TESTS), "workers": 16, "live_execution_enabled": False}


def run(scope="full"):
    tests = SCOPES[scope]
    sources = binding()
    output = review.OUTPUT / "validation" / digest(sources)[:20] / (scope + "-" + uuid.uuid4().hex[:12])
    output.mkdir(parents=True, exist_ok=False)
    authority = {str(path): digest(path.read_bytes()) for path in
                 (review.program.predecessor.account.ACCOUNT, review.program.GRANT,
                  review.program.GRANT.with_suffix(".stages.json"))}
    initial = {"status": "running", "binding": sources, "authority": authority,
               "started_at": time.time(), "live_execution_enabled": False, "scope": scope,
               "tests": list(tests), "release_acceptance": False, "runner_pid": os.getpid(),
               "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
               "phase": "collecting"}
    persist(output / "validation.json", initial)
    print(json.dumps({"status": "OFFLINE_TESTS_RUNNING", "workers": 16,
                      "output": str(output)}), flush=True)
    command = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=",
               "-p", "xdist.plugin", "-p", "tools.inventory_history_test_guard", *tests]
    try:
        with (output / "tests.log").open("wb") as log:
            command_run(command + ["--collect-only", "--history-membership=" + str(output / "collected.json")],
                log=log, timeout=300)
            initial["phase"] = "executing"
            persist(output / "validation.json", initial)
            command_run(command + ["-n", "16", "--tb=short", "--show-capture=no",
                "--history-membership=" + str(output / "executed.json"),
                "--junitxml=" + str(output / "tests.xml")],
                log=log, timeout=1800)
        membership = validation.verify_membership(read_json(output / "collected.json"),
                                                  read_json(output / "executed.json"), tests)
        document = element_tree.parse(output / "tests.xml")
        if (len(document.findall(".//testcase")) != len(membership)
                or any(document.findall(".//" + tag) for tag in ("failure", "error", "skipped"))
                or sources != binding()
                or any(digest(Path(path).read_bytes()) != expected for path, expected in authority.items())):
            raise ValueError("Exact regression membership, source or authority changed")
        result = {**initial, "status": "pass", "cases": len(membership),
                  "source_unchanged": True, "authority_unchanged": True,
                  "evidence": {name: digest((output / name).read_bytes())
                               for name in ("collected.json", "executed.json", "tests.xml")},
                  "finished_at": time.time()}
    except (OSError, ValueError, subprocess.SubprocessError, element_tree.ParseError, KeyboardInterrupt) as error:
        result = {**initial, "status": "fail", "error": type(error).__name__ + ": " + str(error),
                  "finished_at": time.time()}
        if isinstance(error, CommandCleanupError):
            result["cleanup"] = error.evidence
    result.update(phase="finished", source_unchanged=False, authority_unchanged=False)
    try:
        result["source_unchanged"] = sources == binding()
        result["authority_unchanged"] = all(
            digest(Path(path).read_bytes()) == expected for path, expected in authority.items())
        if not result["source_unchanged"] or not result["authority_unchanged"]:
            raise ValueError("Final source or authority comparison failed")
    except (OSError, ValueError, KeyError, TypeError, KeyboardInterrupt) as error:
        result.update(status="fail", finalization_error=type(error).__name__ + ": " + str(error))
    result["finished_at"] = time.time()
    persist(output / "validation.json", result)
    print(json.dumps({"status": result["status"], "cases": result.get("cases"),
                      "output": str(output)}), flush=True)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "floors", "executor"))
    arguments = parser.parse_args()
    raise SystemExit(run("full" if arguments.action == "run" else arguments.action))
