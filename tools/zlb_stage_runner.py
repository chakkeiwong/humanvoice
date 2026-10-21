"""Dispatch prospective inventory separately from frozen candidate stages."""

import runpy
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import read_json
from tools import inventory_stage_runtime as inventory
from tools import reproduction_boundary_runner as previous
from tools import zlb_ssd_workspace as workspace
from tools.parallel_verification_replay import cached_parallel_verification

scope = inventory.scope


def main():
    name, arguments = sys.argv[1], sys.argv[2:]
    if name not in scope.NATIVE:
        return previous.main()
    if name.startswith("run-manuscript") and arguments[0] == "prepare":
        stage = arguments[arguments.index("--stage") + 1]
        if stage != "inventory":
            return previous.main()
        snapshot = arguments[arguments.index("--snapshot") + 1]
        authorization = inventory.network.budget.authority.AUTHORITY
    else:
        output = Path(arguments[arguments.index("--output") + 1]) if name.startswith("run-manuscript") else scope.BASE / arguments[0]
        plan = read_json(output / "plan.json")
        if "inventory_stage_extension" not in plan:
            return previous.main()
        inventory.validate_extension(plan)
        stage, snapshot = plan["stage"], plan["snapshot"]
        authorization = plan["assembled_input_budget_extension"]["authorization_path"]
    original = sys.argv
    sys.argv = [str(scope.BASE / name), *arguments]
    try:
        with scope.accounting_scope(), inventory.pipeline(planning=[(snapshot, stage)], authorization=authorization), cached_parallel_verification(
                workers=16, progress=workspace.EVIDENCE / f"inventory-{time.time_ns()}.json"):
            if name.startswith("verify-") or arguments[0] == "prepare":
                with scope.verification_only():
                    runpy.run_path(str(scope.BASE / name), run_name="__main__")
            else:
                runpy.run_path(str(scope.BASE / name), run_name="__main__")
    finally:
        sys.argv = original
    return 0


if __name__ == "__main__":
    with inventory.history.archive.access():
        scope.RUNNER = Path(__file__).resolve()
        raise SystemExit(main())
