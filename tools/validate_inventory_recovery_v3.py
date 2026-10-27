"""Run fixed offline recovery regressions with exact source and test membership."""

import argparse
import json
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as element_tree
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import digest, read_json
from tools import inventory_history_live as historical
from tools import review_inventory_recovery_v3 as review
from tools import validate_inventory_history as validation
from tools.inventory_recovery_v3.reservations import persist

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
    "tests/test_inventory_recovery_v3_initialization.py",
    "tests/test_inventory_recovery_v3_bootstrap.py",
    "tests/test_inventory_campaign_progress.py",
    "tests/test_failure_first_native.py",
    "tests/test_inventory_history_live.py",
    "tests/test_inventory_history_current_stage.py",
    "tests/test_inventory_history_integration.py",
)


def binding():
    paths = set(TESTS) | {"tools/validate_inventory_recovery_v3.py",
        "tools/inventory_history_test_guard.py", "tools/validate_inventory_history.py",
        "tools/validate_failure_first.py", "pyproject.toml"}
    paths.update(str(path.relative_to(ROOT)) for path in (ROOT / "tests").rglob("*.py"))
    return {"candidate": review.sources(), "historical": historical.contract(),
            "dependencies": {name: digest((ROOT / name).read_bytes()) for name in sorted(paths)},
            "tests": list(TESTS), "workers": 16, "live_execution_enabled": False}


def run():
    sources = binding()
    output = review.OUTPUT / "validation" / digest(sources)[:20] / uuid.uuid4().hex[:12]
    output.mkdir(parents=True, exist_ok=False)
    authority = {str(path): digest(path.read_bytes()) for path in
                 (review.program.predecessor.account.ACCOUNT, review.program.GRANT,
                  review.program.GRANT.with_suffix(".stages.json"))}
    initial = {"status": "running", "binding": sources, "authority": authority,
               "started_at": time.time(), "live_execution_enabled": False}
    persist(output / "validation.json", initial)
    print(json.dumps({"status": "OFFLINE_TESTS_RUNNING", "workers": 16,
                      "output": str(output)}), flush=True)
    command = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=",
               "-p", "xdist.plugin", "-p", "tools.inventory_history_test_guard", *TESTS]
    try:
        with (output / "tests.log").open("wb") as log:
            subprocess.run(command + ["--collect-only", "--history-membership=" + str(output / "collected.json")],
                cwd=ROOT, env=validation.environment(), stdout=log, stderr=subprocess.STDOUT,
                timeout=300, check=True)
            subprocess.run(command + ["-n", "16", "--tb=short", "--show-capture=no",
                "--history-membership=" + str(output / "executed.json"),
                "--junitxml=" + str(output / "tests.xml")],
                cwd=ROOT, env=validation.environment(), stdout=log, stderr=subprocess.STDOUT,
                timeout=1800, check=True)
        membership = validation.verify_membership(read_json(output / "collected.json"),
                                                  read_json(output / "executed.json"), TESTS)
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
    except (OSError, ValueError, subprocess.SubprocessError, element_tree.ParseError) as error:
        result = {**initial, "status": "fail", "error": type(error).__name__ + ": " + str(error),
                  "finished_at": time.time()}
    persist(output / "validation.json", result)
    print(json.dumps({"status": result["status"], "cases": result.get("cases"),
                      "output": str(output)}), flush=True)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run",))
    parser.parse_args()
    raise SystemExit(run())
