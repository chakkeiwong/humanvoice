"""Independently replay accepted responses to the exact timed-out request."""

import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import write_json
from tools import inventory_deadline_continuation as continuation


def main():
    continuation.EVIDENCE.mkdir(parents=True, exist_ok=True)
    grant = continuation.BASE / "authorized-2000-call-budget-20261012.json"
    with (continuation.EVIDENCE / (continuation.PROBE.name + ".stdout.log")).open("x") as stdout, (
            continuation.EVIDENCE / (continuation.PROBE.name + ".stderr.log")).open("x") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr), continuation.inventory.history.archive.access(), (
                continuation.inventory.scope.accounting_scope()), continuation.inventory.pipeline():
            report = continuation.probe(grant=grant)
    write_json(continuation.PROBE / "process.json", {"pid": os.getpid(), "parent_pid": os.getppid(),
                                                    "model_calls": 0, "status": report["status"]})
    print(json.dumps({key: report[key] for key in ("status", "model_calls", "inherited_calls")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
