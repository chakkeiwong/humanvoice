"""Probe the exact missing review in an independent process without spending."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import digest, read_json
from tools import process_accounting_scope as scope
from tools import review_request_recovery as continuation
from tools.automatic_program_account import ACCOUNT, validate_account
from tools.inventory_transport_continuation import immutable, tree_hashes
from tools.parallel_verification_replay import cached_parallel_verification


def probe(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = Path(read_json(continuation.PRIOR / "plan.json")["snapshot"])
    grant = scope.BASE / "authorized-2000-call-budget-20261012.json"
    before = ACCOUNT.read_bytes(), grant.read_bytes(), tree_hashes(continuation.PRIOR)
    with scope.accounting_scope(), continuation.pipeline(planning=[(source, "reproduction")],
            snapshots=[output / "replica"]), scope.verification_only():
        account = validate_account(read_json(ACCOUNT))
        proof = continuation.predecessor_evidence()
        immutable(output / "predecessor-evidence.json", proof)
        plan = continuation.MANUSCRIPT.plan_for(source, "reproduction", proof["remaining_calls"],
            account["reservation_ceiling"], execution_snapshot=output / "replica", recovery=True,
            technical_predecessor=continuation.PRIOR, account_allowance=account["allowance"])
        immutable(output / "master-accounting-plan.json", plan)
        command = [sys.executable, "-I", "-B", str(ROOT / "tools/review_request_worker.py"), str(output), "--probe"]
        print("Probe exact first review in a separate process; provider calls disabled.", flush=True)
        with (output / "stdout.log").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
            subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=3600, check=True)
        child = read_json(output / "review-request-execution.json")
        if (child["status"] != "pass" or not child["probe"] or child["independent_pid"] == os.getpid()
                or child["retained_writers"] != 14 or child["requests"] != [digest(proof["interrupted_request"])]
                or before != (ACCOUNT.read_bytes(), grant.read_bytes(), tree_hashes(continuation.PRIOR))
                or continuation.previous.previous.previous.repair.api_ids(output / "replica") !=
                   continuation.previous.previous.previous.repair.api_ids(Path(proof["replica"]))):
            raise ValueError("Review probe changed retained results, exact request, accounting or provider activity")
        names = ("review-request-execution.json", "stdout.log", "stderr.log", "denial-archive.json",
                 "master-accounting-plan.json", "predecessor-evidence.json")
        report = {"status": "pass", "model_calls": 0, "workers": 16, "independent_process": True,
                  "retained_writers": 14, "extension": continuation.extension(), "predecessor_identity": digest(proof),
                  "account_bytes_unchanged": True, "grant_bytes_unchanged": True, "predecessor_bytes_unchanged": True,
                  "first_request_hash": digest(proof["interrupted_request"]), "command": command,
                  "process_evidence": {name: digest((output / name).read_bytes()) for name in names}}
        immutable(output / "verification.json", report)
        print(json.dumps({"status": "pass", "model_calls": 0, "retained_writers": 14}), flush=True)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    with scope.accounting_scope(), continuation.pipeline(), cached_parallel_verification(
            workers=16, progress=continuation.EVIDENCE / "probe-parent-parallel.json"):
        probe(arguments.output)
    return 0


if __name__ == "__main__":
    with continuation.previous.archive.access():
        raise SystemExit(main())
