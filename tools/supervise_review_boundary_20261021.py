"""Durably supervise retained-review boundary verification and continuation."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import supervise_assembled_budget_20261016 as supervisor

supervisor.EVIDENCE = supervisor.BASE / "review-boundary-dispatch-20261021"
supervisor.STATE = supervisor.EVIDENCE / "activation-supervisor.json"
supervisor.CONTROLLER = ROOT / "tools/run_review_boundary_20261021.py"
supervisor.__file__ = __file__


if __name__ == "__main__":
    raise SystemExit(supervisor.main())
