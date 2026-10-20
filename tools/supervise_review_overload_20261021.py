"""Durably supervise overload recovery and the remaining master program."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import supervise_assembled_budget_20261016 as supervisor

supervisor.EVIDENCE = supervisor.BASE / "review-overload-recovery-20261021"
supervisor.STATE = supervisor.EVIDENCE / "activation-supervisor.json"
supervisor.CONTROLLER = ROOT / "tools/run_review_overload_20261021.py"
supervisor.__file__ = __file__


if __name__ == "__main__":
    raise SystemExit(supervisor.main())
