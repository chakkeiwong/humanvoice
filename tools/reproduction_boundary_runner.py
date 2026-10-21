"""Run the frozen native boundary with the matching retained-review verifier."""

import runpy
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import read_json, write_json
from tools import reproduction_boundary_dispatch as boundary
from tools import reproduction_overload_runner as previous
from tools.parallel_verification_replay import cached_parallel_verification

continuation, scope = boundary.continuation, boundary.continuation.scope


def main():
    name, arguments = sys.argv[1], sys.argv[2:]
    if name != boundary.NATIVE:
        return previous.main()
    output = scope.BASE / arguments[0]
    plan = read_json(output / "plan.json")
    if not boundary.selected(plan):
        return previous.main()
    continuation.validate_extension(plan)
    planning, snapshots = continuation.network.budget.plan_scope(plan)
    authorization = plan["assembled_input_budget_extension"]["authorization_path"]
    original = sys.argv
    sys.argv = [str(scope.BASE / name), *arguments]
    started = time.monotonic()
    progress = boundary.EVIDENCE / f"boundary-{time.time_ns()}.json"
    record = {"status": "verifying_predecessor", "stage": str(output), "model_calls": 0}

    def publish(status, **details):
        record.update(status=status, elapsed_seconds=time.monotonic() - started, **details)
        write_json(progress, record)

    try:
        publish("verifying_predecessor")
        with scope.accounting_scope(), continuation.pipeline(planning=planning, snapshots=snapshots,
                authorization=authorization), scope.verification_only():
            boundary.preflight(output)
            publish("verifying_settlements")
            with boundary.dispatch(plan), cached_parallel_verification(
                    workers=16, progress=progress.with_name(progress.stem + "-settlements.json")):
                publish("verifying_native_boundary")
                runpy.run_path(str(scope.BASE / name), run_name="__main__")
            publish("pass")
    except BaseException as error:
        publish("nonpass", error=type(error).__name__ + ": " + str(error)[:2000])
        raise
    finally:
        sys.argv = original
    return 0


if __name__ == "__main__":
    with continuation.archive.access():
        scope.RUNNER = Path(__file__).resolve()
        raise SystemExit(main())
