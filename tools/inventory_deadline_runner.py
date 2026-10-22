"""Carry inventory deadline accounting through later native consumers."""

import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from tools import inventory_context_runner as previous
from tools import inventory_deadline_runtime as deadline


@contextmanager
def reproduction_dispatch():
    module = previous.automatic_reproduction
    native_launch, native_evaluate = module.launch, module.evaluate_reproduction

    @contextmanager
    def selected_command(source):
        command = module._command

        def worker(root, master_accounting=False):
            actual = command(root, master_accounting)
            if previous.context.selected_policy(source) is None:
                return actual
            expected = {str(ROOT / "tools" / name) for name in ("reproduction_overload_worker.py",
                        "inventory_coverage_worker.py", "inventory_context_worker.py", "inventory_deadline_worker.py")}
            if len(actual) != 5 or actual[3] not in expected:
                raise ValueError("Deadline reproduction requires its frozen accounted worker")
            return [*actual[:3], str(ROOT / "tools/inventory_deadline_worker.py"), actual[4]]

        module._command = worker
        try:
            yield
        finally:
            module._command = command

    def launch(*arguments, **keywords):
        source = Path(arguments[0] if arguments else keywords["snapshot"])
        with selected_command(source):
            return native_launch(*arguments, **keywords)

    def evaluate(root, *, require_live=True, source_override=None):
        source = Path(source_override if source_override is not None else
                      previous.read_json(Path(root) / "request.json")["manifest"]["snapshot_path"])
        with selected_command(source):
            return native_evaluate(root, require_live=require_live, source_override=source_override)

    with deadline.network.replaced_aliases(native_launch, launch), deadline.network.replaced_aliases(native_evaluate, evaluate):
        yield


def main():
    with previous.context.runtime(), deadline.runtime(), reproduction_dispatch():
        return previous.previous.main()


if __name__ == "__main__":
    with deadline.inventory.history.archive.access():
        deadline.inventory.scope.RUNNER = Path(__file__).resolve()
        raise SystemExit(main())
