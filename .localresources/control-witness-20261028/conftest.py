"""Expose native consumer fixtures only inside the offline candidate suite."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "tests")]

pytest_plugins = ["test_inventory_recovery_v3_runtime_predicates"]
