"""Carry source-bound punctuation ownership through native stage consumers."""

import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice import automatic_reproduction
from humanvoice.artifacts import read_json
from tools import inventory_coverage_continuation as continuation
from tools import inventory_punctuation as punctuation
from tools import zlb_stage_runner as previous


@contextmanager
def reproduction_dispatch():
    native_launch = automatic_reproduction.launch
    native_evaluate = automatic_reproduction.evaluate_reproduction

    @contextmanager
    def selected_command(source):
        command = automatic_reproduction._command

        def worker(root, master_accounting=False):
            actual = command(root, master_accounting)
            if not (source / punctuation.MARKER).exists():
                return actual
            if read_json(source / punctuation.MARKER) != punctuation.policy(source):
                raise ValueError("Reproduction punctuation policy changed")
            expected = {str(ROOT / "tools/reproduction_overload_worker.py"), str(ROOT / "tools/inventory_coverage_worker.py")}
            if len(actual) != 5 or actual[3] not in expected:
                raise ValueError("Punctuation reproduction requires its frozen accounted worker")
            return [*actual[:3], str(ROOT / "tools/inventory_coverage_worker.py"), actual[4]]

        automatic_reproduction._command = worker
        try:
            yield
        finally:
            automatic_reproduction._command = command

    def launch(*arguments, **keywords):
        source = Path(arguments[0] if arguments else keywords["snapshot"])
        with selected_command(source):
            return native_launch(*arguments, **keywords)

    def evaluate(root, *, require_live=True, source_override=None):
        source = Path(source_override if source_override is not None else
                      read_json(Path(root) / "request.json")["manifest"]["snapshot_path"])
        with selected_command(source):
            return native_evaluate(root, require_live=require_live, source_override=source_override)

    network = continuation.inventory.network
    with network.replaced_aliases(native_launch, launch), network.replaced_aliases(native_evaluate, evaluate):
        yield


def main():
    with punctuation.runtime(), reproduction_dispatch():
        return previous.main()


if __name__ == "__main__":
    with continuation.inventory.history.archive.access():
        continuation.inventory.scope.RUNNER = Path(__file__).resolve()
        raise SystemExit(main())
