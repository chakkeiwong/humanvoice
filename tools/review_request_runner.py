"""Carry prospective review recovery through native subprocess boundaries."""

import runpy
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import read_json
from tools import process_accounting_scope as scope
from tools import review_request_recovery as continuation
from tools import writer_identifier_runner as previous
from tools.parallel_verification_replay import cached_parallel_verification


def main():
    name, arguments = sys.argv[1], sys.argv[2:]
    if name not in scope.NATIVE:
        return previous.main()
    if name.startswith("run-manuscript") and arguments[0] == "prepare":
        snapshot = arguments[arguments.index("--snapshot") + 1]
        stage = arguments[arguments.index("--stage") + 1]
        planning, snapshots = [(snapshot, stage)], [snapshot]
        authorization = continuation.network.budget.authority.AUTHORITY
    else:
        output = Path(arguments[arguments.index("--output") + 1]) if name.startswith("run-manuscript") else scope.BASE / arguments[0]
        plan = read_json(output / "plan.json")
        if "review_request_extension" not in plan:
            return previous.main()
        continuation.validate_extension(plan)
        planning, snapshots = continuation.network.budget.plan_scope(plan)
        authorization = plan["assembled_input_budget_extension"]["authorization_path"]
    original = sys.argv
    sys.argv = [str(scope.BASE / name), *arguments]
    try:
        with scope.accounting_scope(), continuation.pipeline(planning=planning, snapshots=snapshots,
                authorization=authorization), cached_parallel_verification(
                    workers=16, progress=continuation.EVIDENCE / f"child-{time.time_ns()}.json"):
            runpy.run_path(str(scope.BASE / name), run_name="__main__")
    finally:
        sys.argv = original
    return 0


if __name__ == "__main__":
    with continuation.previous.archive.access():
        scope.RUNNER = Path(__file__).resolve()
        raise SystemExit(main())
