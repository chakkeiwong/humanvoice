"""Independently reach the exact interrupted review without provider calls."""

import os
import subprocess
import sys
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools import reproduction_overload_recovery as continuation
from tools.automatic_program_account import ACCOUNT, validate_account
from tools.inventory_transport_continuation import immutable, tree_hashes


def probe(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = Path(read_json(continuation.PRIOR / "plan.json")["snapshot"])
    grant = continuation.BASE / "authorized-2000-call-budget-20261012.json"
    before = ACCOUNT.read_bytes(), grant.read_bytes(), tree_hashes(continuation.PRIOR)
    with continuation.scope.accounting_scope(), continuation.pipeline(planning=[(source, "reproduction")],
            snapshots=[output / "replica"]), continuation.scope.verification_only():
        account = validate_account(read_json(ACCOUNT))
        proof = continuation.predecessor_evidence()
        immutable(output / "predecessor-evidence.json", proof)
        plan = continuation.MANUSCRIPT.plan_for(source, "reproduction", proof["remaining_calls"],
            account["reservation_ceiling"], execution_snapshot=output / "replica", recovery=True,
            technical_predecessor=continuation.PRIOR, account_allowance=account["allowance"])
        immutable(output / "master-accounting-plan.json", plan)
        command = [sys.executable, "-I", "-B", str(continuation.ROOT / "tools/reproduction_overload_worker.py"), str(output), "--probe"]
        with (output / "stdout.log").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
            subprocess.run(command, cwd=continuation.ROOT, stdout=stdout, stderr=stderr, timeout=3600, check=True)
        child = read_json(output / "review-size-execution.json")
        expected = proof["first_request_hash"]
        if (child["status"] != "pass" or not child["probe"] or child["independent_pid"] == os.getpid()
                or child["requests"] != [expected]
                or before != (ACCOUNT.read_bytes(), grant.read_bytes(), tree_hashes(continuation.PRIOR))
                or continuation.writer_repair.api_ids(output / "replica") !=
                   continuation.writer_repair.api_ids(Path(proof["replica"]))):
            raise ValueError("Overload probe changed its exact request, evidence or accounting")
        names = ("review-size-execution.json", "stdout.log", "stderr.log",
                 "master-accounting-plan.json", "predecessor-evidence.json")
        result = {"status": "pass", "model_calls": 0, "workers": 16, "independent_process": True,
                  "extension": continuation.extension(), "predecessor_identity": digest(proof),
                  "first_request_hash": expected, "command": command,
                  "retained_assembled_reviews": proof["retained_assembled_reviews"],
                  "account_bytes_unchanged": True, "grant_bytes_unchanged": True, "predecessor_bytes_unchanged": True,
                  "process_evidence": {name: digest((output / name).read_bytes()) for name in names}}
        immutable(output / "verification.json", result)
        return result
