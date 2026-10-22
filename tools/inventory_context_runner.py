"""Carry sentence context and bounded repairs through every native consumer."""

import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice import automatic_reproduction
from humanvoice.artifacts import read_json
from tools import inventory_context as context
from tools import inventory_stage_runtime as inventory
from tools import zlb_stage_runner as previous


@contextmanager
def reproduction_dispatch():
    native_launch, native_evaluate = automatic_reproduction.launch, automatic_reproduction.evaluate_reproduction

    @contextmanager
    def selected_command(source):
        command = automatic_reproduction._command

        def worker(root, master_accounting=False):
            actual = command(root, master_accounting)
            if context.selected_policy(source) is None:
                return actual
            expected = {str(ROOT / "tools" / name) for name in
                        ("reproduction_overload_worker.py", "inventory_coverage_worker.py", "inventory_context_worker.py")}
            if len(actual) != 5 or actual[3] not in expected:
                raise ValueError("Context reproduction requires its frozen accounted worker")
            return [*actual[:3], str(ROOT / "tools/inventory_context_worker.py"), actual[4]]

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

    with inventory.network.replaced_aliases(native_launch, launch), inventory.network.replaced_aliases(native_evaluate, evaluate):
        yield


def main():
    with context.runtime(), reproduction_dispatch():
        return previous.main()


if __name__ == "__main__":
    with inventory.history.archive.access():
        inventory.scope.RUNNER = Path(__file__).resolve()
        raise SystemExit(main())
