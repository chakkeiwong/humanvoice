"""Run overload continuation inside an independent accounted process."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import read_json
from tools import automatic_reproduction_worker
from tools import reproduction_overload_recovery as continuation
from tools.parallel_verification_replay import cached_parallel_verification


def execute(root, *, probe=False):
    root = Path(root).resolve()
    plan = continuation.validate_extension(read_json(root / "master-accounting-plan.json"))
    planning, snapshots = continuation.network.budget.plan_scope(plan)
    with continuation.scope.accounting_scope(), continuation.pipeline(planning=planning, snapshots=snapshots,
            authorization=plan["assembled_input_budget_extension"]["authorization_path"]), cached_parallel_verification(
                workers=16, progress=root / "parallel-verification.json"):
        if plan.get("technical_restart", {}).get("version") == continuation.VERSION:
            if probe:
                with continuation.scope.verification_only():
                    return continuation.resume(root, probe=True)
            return automatic_reproduction_worker.execute(root, worker=lambda: continuation.resume(root))
        if probe:
            raise ValueError("Overload probe requires its frozen stopped predecessor")
        with continuation.size.sized_writers(root / "replica"):
            return automatic_reproduction_worker.execute(root)


if __name__ == "__main__":
    with continuation.archive.access():
        raise SystemExit(execute(sys.argv[1], probe="--probe" in sys.argv[2:]))
