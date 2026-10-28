"""Inspect prospective public configuration; unadmitted execution stays blocked."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from tools.inventory_recovery_v3 import configuration
from tools.inventory_recovery_v3.failures import RecoveryStop


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("configuration", "status", "monitor", "worker",
                        "campaign-execute", "campaign-verify", "campaign-repair"))
    parser.add_argument("--job")
    selected = parser.parse_args(arguments)
    try:
        if selected.action not in {"configuration", "status"}:
            raise RecoveryStop("BLOCKED_OWNERSHIP",
                "Public execution requires reviewed runtime composition and external host admission")
        if selected.job is not None:
            parser.error("Read-only inspection does not accept caller-selected jobs")
        result = configuration.status()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (RecoveryStop, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": getattr(error, "category", "BLOCKED_ACCOUNTING"),
            "error": type(error).__name__ + ": " + str(error), "model_calls": 0,
            "account_writes": 0, "grant_writes": 0, "live_execution_enabled": False,
            "dispatch_allowed": False}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
