"""Durably supervise verification, bounded review recovery and the ZLB sequence."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import supervise_assembled_budget_20261016 as supervisor

supervisor.EVIDENCE = supervisor.BASE / "review-request-recovery-20261020"
supervisor.STATE = supervisor.EVIDENCE / "activation-supervisor.json"
supervisor.CONTROLLER = ROOT / "tools/run_review_request_program_20261020.py"
supervisor.__file__ = __file__


if __name__ == "__main__":
    raise SystemExit(supervisor.main())
