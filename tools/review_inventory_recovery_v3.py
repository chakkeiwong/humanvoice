"""Run the fixed offline migration and capacity audit without live permission."""

import argparse
import json
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import digest, read_json
from tools.inventory_history_adoption import no_inference
from tools.inventory_recovery_v2 import program
from tools.inventory_recovery_v3.migration import inspect_production
from tools.inventory_recovery_v3.policy import proposal
from tools.inventory_recovery_v3.reservations import persist

OUTPUT = program.OUTPUT / "recovery-policy-repair-20261027-01"


def sources():
    paths = sorted((ROOT / "tools/inventory_recovery_v3").glob("*.py"))
    paths.append(Path(__file__).resolve())
    paths.append(ROOT / "tools/prepare_inventory_recovery_v3.py")
    return {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in paths}


def audit():
    binding = sources()
    output = OUTPUT / "migration" / digest(binding)[:20]
    output.mkdir(parents=True, exist_ok=True)
    authority_paths = (program.predecessor.account.ACCOUNT, program.GRANT,
                       program.GRANT.with_suffix(".stages.json"))
    before = {str(path): digest(path.read_bytes()) for path in authority_paths}
    started = time.time()
    print(json.dumps({"phase": "OFFLINE_RECONCILIATION", "output": str(output),
                      "live_execution_enabled": False}), flush=True)
    try:
        with (output / "native-replay.log").open("a") as log, redirect_stdout(log), redirect_stderr(log):
            report = inspect_production()
            with no_inference(), program.history_scope():
                account = program.predecessor.account.validate_account(read_json(program.predecessor.account.ACCOUNT))
                grant = program.predecessor.grant_status(program.GRANT)
        capacity = proposal(remaining_requests=report["remaining_requests"],
                            inherited_recovery=report["legacy_successor_charge"],
                            incident_allowance=32, split_allowance=32, qualification_calls=0, root_sequences=12,
                            available_calls=grant["available"],
                            available_tokens=account["allowance"] - account["reservation_ceiling"])
        if sources() != binding or any(digest(Path(path).read_bytes()) != value for path, value in before.items()):
            raise ValueError("Source or authority changed during offline migration audit")
        persist(output / "migration.json", report)
        persist(output / "capacity-proposal.json", capacity)
        summary = {"status": "OFFLINE_AUDIT_PASS", "sources": binding,
                   "authority": before, "migration_identity": report["identity"],
                   "policy_identity": capacity["identity"], "retained_responses": report["retained_responses"],
                   "remaining_requests": report["remaining_requests"],
                   "authority_sufficient": capacity["authority_sufficient"],
                   "model_calls": 0, "account_writes": 0, "live_execution_enabled": False,
                   "started_at": started, "finished_at": time.time()}
        persist(output / "audit.json", summary)
        print(json.dumps({**summary, "sources": len(binding), "authority": "unchanged",
                          "output": str(output)}), flush=True)
        return 0
    except BaseException as error:
        summary = {"status": "OFFLINE_AUDIT_FAILED", "error": type(error).__name__ + ": " + str(error),
                   "sources_unchanged": sources() == binding,
                   "authority_unchanged": all(digest(Path(path).read_bytes()) == value for path, value in before.items()),
                   "model_calls": 0, "account_writes": 0, "live_execution_enabled": False,
                   "started_at": started, "finished_at": time.time()}
        persist(output / "audit.json", summary)
        print(json.dumps({**summary, "output": str(output)}), flush=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit",))
    parser.parse_args()
    return audit()


if __name__ == "__main__":
    raise SystemExit(main())
