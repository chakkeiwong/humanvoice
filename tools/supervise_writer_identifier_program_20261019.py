"""Durably supervise identifier recovery and the remaining master program."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import supervise_assembled_budget_20261016 as supervisor

supervisor.EVIDENCE = supervisor.BASE / "writer-identifier-recovery-20261019"
supervisor.STATE = supervisor.EVIDENCE / "activation-supervisor.json"
supervisor.CONTROLLER = ROOT / "tools/run_writer_identifier_program_20261019.py"
supervisor.__file__ = __file__


if __name__ == "__main__":
    raise SystemExit(supervisor.main())
