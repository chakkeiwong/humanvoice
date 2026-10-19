"""Independently probe the complete retained writer set without provider calls."""

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
from tools import writer_identifier_continuation as continuation
from tools.automatic_program_account import ACCOUNT, validate_account
from tools.inventory_transport_continuation import immutable, tree_hashes
from tools.parallel_verification_replay import cached_parallel_verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    continuation.ensure_execution_paths()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = Path(read_json(continuation.PRIOR / "plan.json")["snapshot"])
    grant = scope.BASE / "authorized-2000-call-budget-20261012.json"
    before = ACCOUNT.read_bytes(), grant.read_bytes(), tree_hashes(continuation.PRIOR)
    with scope.accounting_scope(), continuation.pipeline(planning=[(source, "reproduction")],
            snapshots=[output / "replica"]), scope.verification_only(), cached_parallel_verification(
                workers=16, progress=output / "parent-parallel.json"):
        account = validate_account(read_json(ACCOUNT))
        proof = continuation.predecessor_evidence()
        immutable(output / "predecessor-evidence.json", proof)
        plan = continuation.previous.previous.repair.manuscript.plan_for(
            source, "reproduction", proof["remaining_calls"], account["reservation_ceiling"],
            execution_snapshot=output / "replica", recovery=True, technical_predecessor=continuation.PRIOR,
            account_allowance=account["allowance"])
        immutable(output / "master-accounting-plan.json", plan)
        command = [sys.executable, "-I", "-B", str(ROOT / "tools/writer_identifier_worker.py"), str(output), "--probe"]
        print("Launching isolated native continuation to its first independent review; provider calls disabled.", flush=True)
        with (output / "stdout.log").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
            subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=3600, check=True)
        child = read_json(output / "identifier-execution.json")
        if (child["status"] != "pass" or not child["probe"] or child["independent_pid"] == os.getpid()
                or child["retained_writers"] != 13 or child["derived_writers"] != 1 or len(child["requests"]) != 1
                or before != (ACCOUNT.read_bytes(), grant.read_bytes(), tree_hashes(continuation.PRIOR))
                or continuation.previous.previous.repair.api_ids(output / "replica") !=
                   continuation.previous.previous.repair.api_ids(Path(proof["replica"]))):
            raise ValueError("Identifier probe changed accepted history, spending or provider activity")
        names = ("identifier-execution.json", "stdout.log", "stderr.log",
                 "master-accounting-plan.json", "predecessor-evidence.json")
        report = {"status": "pass", "model_calls": 0, "workers": 16, "independent_process": True,
                  "retained_writers": 13, "derived_writers": 1, "extension": continuation.extension(),
                  "predecessor_identity": digest(proof), "account_bytes_unchanged": True,
                  "grant_bytes_unchanged": True, "predecessor_bytes_unchanged": True, "command": command,
                  "process_evidence": {name: digest((output / name).read_bytes()) for name in names}}
        immutable(output / "verification.json", report)
        print(json.dumps({"status": "pass", "model_calls": 0, "retained_writers": 13, "derived_writers": 1}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
