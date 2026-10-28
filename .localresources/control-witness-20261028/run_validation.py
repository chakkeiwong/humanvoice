"""Fixed offline candidate gate; never installs services or calls a provider."""

import argparse
import hashlib
import json
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from tools import validate_inventory_recovery_v3 as runner
from tools.validate_inventory_history import verify_membership

FILES = tuple(str((HERE / name).relative_to(ROOT)) for name in (
    "test_control_witness.py", "test_control_transport.py",
    "test_control_service.py", "test_control_publication.py"))
BASELINE = ROOT / ("docs/audits/2026-10-05/master-program/automatic-execution/"
    "sol-inventory-failure-first-20261026-01/recovery-policy-repair-20261027-01/"
    "validation/bf6525157a631b6918e6/floors-3ca2d2557dfe/validation.json")
RUFF = "/home/ubuntu/miniforge3/envs/tf-gpu/bin/ruff"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_binding():
    # Include native consumer/fixture and harness dependencies. This is an
    # offline gate and does not establish release dependency completeness.
    selected = set(HERE.glob("*.py")) | {HERE / "ruff.toml", ROOT / "pyproject.toml"}
    for directory in ("tools", "src/humanvoice", "tests"):
        selected.update((ROOT / directory).rglob("*.py"))
    if (ROOT / "conftest.py").exists():
        selected.add(ROOT / "conftest.py")
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(selected)}


def run():
    output = HERE / "validation" / ("projection-" + uuid.uuid4().hex[:12])
    output.mkdir(parents=True, exist_ok=False)
    record = {"status": "running", "started_at": time.time(), "workers": 16,
              "files": FILES, "release_acceptance": False, "model_calls": 0,
              "source_unchanged": False, "authority_unchanged": False,
              "host_service_installed": False, "production_integration": False}

    def save():
        target = output / "validation.json"
        temporary = output / "validation.tmp"
        temporary.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
        temporary.replace(target)

    save()
    print(json.dumps({"output": str(output.relative_to(ROOT)), "status": "running"}), flush=True)
    try:
        before = source_binding()
        expected = json.loads(BASELINE.read_text())["authority"]
        authority = {name: sha(Path(name)) for name in expected}
        if authority != expected:
            raise ValueError("Production authority differs from retained baseline")
        record.update(source_before=before, authority_before=authority)
        save()
        base = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=",
                "-p", "xdist.plugin", "-p", "tools.inventory_history_test_guard", *FILES]
        commands = [
            ("ruff", [RUFF, "check", str(HERE)], 120),
            ("collected", [*base, "--collect-only",
                           "--history-membership=" + str(output / "collected.json")], 120),
            ("executed", [*base, "-n", "16", "--tb=short", "--show-capture=no",
                          "--history-membership=" + str(output / "executed.json"),
                          "--junitxml=" + str(output / "tests.xml")], 180),
        ]
        record["commands"] = commands
        for phase, command, timeout in commands:
            record["phase"] = phase
            save()
            with (output / (phase + ".log")).open("wb") as log:
                runner.command_run(command, log=log, timeout=timeout)
        collected = json.loads((output / "collected.json").read_text())
        executed = json.loads((output / "executed.json").read_text())
        membership = verify_membership(collected, executed, FILES)
        document = ET.parse(output / "tests.xml")
        cases = document.findall(".//testcase")
        if len(cases) != len(membership) or any(document.findall(".//" + tag)
                for tag in ("failure", "error", "skipped")):
            raise ValueError("JUnit does not prove complete passing membership")
        record.update(status="pass", cases=len(cases), exact_membership=True,
                      ruff_pass=True, test_seconds=sum(float(s.get("time", 0))
                          for s in document.findall(".//testsuite")))
    except BaseException as error:  # noqa: BLE001 -- retain failures and interruptions; return failure below
        record.update(status="fail", error=type(error).__name__ + ": " + str(error))
    finally:
        # A finalization error must never leave a passing receipt behind.
        try:
            record["source_after"] = source_binding()
            record["authority_after"] = {name: sha(Path(name))
                                         for name in record.get("authority_before", {})}
            record["source_unchanged"] = record["source_after"] == record.get("source_before")
            record["authority_unchanged"] = bool(record.get("authority_before")) and (
                record["authority_after"] == record["authority_before"])
            if not record["source_unchanged"] or not record["authority_unchanged"]:
                raise ValueError("Source or production authority changed during validation")
            record["evidence"] = {p.name: sha(p) for p in sorted(output.iterdir())
                                  if p.suffix in {".log", ".xml"}
                                  or p.name in {"collected.json", "executed.json"}}
        except BaseException as error:  # noqa: BLE001 -- finalization can never preserve a false pass
            record.update(status="fail", finalization_error=type(error).__name__ + ": " + str(error))
        record.update(phase="finished", finished_at=time.time())
        save()
    print(json.dumps({key: record.get(key) for key in (
        "status", "cases", "test_seconds", "source_unchanged", "authority_unchanged",
        "error", "finalization_error")}), flush=True)
    return 0 if record["status"] == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run",))
    parser.parse_args()
    raise SystemExit(run())
