"""Private native runtime dependencies and one prospective launch boundary."""

import sys
from contextlib import contextmanager
from pathlib import Path
from types import FunctionType, SimpleNamespace

from humanvoice.artifacts import read_json
from tools.inventory_recovery_v3 import provider_capture, rejection
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import regular_path


class NativeRejected(Exception):
    def __init__(self, original):
        self.original = original
        super().__init__(str(original))


def require_fresh(plan, output, directory):
    from humanvoice.automatic_recovery import attempt_calls

    entries = read_json(regular_path(Path(output) / "allocation-ledger.json"))["calls"]
    if not entries or entries[-1]["status"] != "allocated_unknown":
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Launch requires one pending native allocation")
    index = next(index for index, call in enumerate(attempt_calls(plan)) if call["key"] == entries[-1]["key"])
    paths = [Path(output) / f"calls/{index:04d}/runtime-binding.json",
        *(directory / name for name in ("allocation-binding.json", "process-start.json", "process.json",
            "record.json", "qualification-capture.json", "prelaunch-rejection.json", "local-cancellation.json",
            "events.jsonl", "stderr.log", "response-envelope.json", "response-capture.part", "stdin.txt"))]
    if any(regular_path(path).exists() for path in paths):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Retained launch requires reconciliation without retransmission")


def private_runtime(native, *, owner, plan, output):
    function = native.__wrapped__
    namespace = dict(function.__globals__)
    qualified = SimpleNamespace(**vars(namespace["qualified"]))
    capture = SimpleNamespace(**vars(qualified.capture))
    qualified.capture = capture
    namespace["qualified"] = qualified
    writer = namespace["write_json"]

    def write(path, value):
        if Path(path).name == "qualification-capture.json" and value.get("status") == "rejected_before_process_start":
            error = sys.exception()
            if error is None:
                raise RecoveryStop("BLOCKED_ENGINEERING", "Native rejection lost its original exception")
            raise NativeRejected(error) from error
        return writer(path, value)

    def launch(arguments, prompt, directory, *, lock_fd, deadline, **kwargs):
        from tools.inventory_recovery_v3.dispatcher import require_dispatch

        def before_spawn():
            require_dispatch(plan, output, owner)
            if lock_fd != owner.executor_descriptor:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Native collector changed the executor role")
            descriptors = owner.execution_descriptors
            require_dispatch(plan, output, owner)
            return descriptors

        return provider_capture.launch(arguments, prompt, directory, lock_fd=lock_fd,
            deadline=deadline, before_spawn=before_spawn, **kwargs)

    capture.launch = launch
    namespace["write_json"] = write
    invoke = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    invoke.__kwdefaults__ = function.__kwdefaults__
    return contextmanager(invoke)


def launch_boundary(native, *, plan, output, owner):
    def launch(arguments, prompt, directory, timeout):
        from tools.inventory_recovery_v3.dispatcher import require_dispatch
        from tools.inventory_recovery_v3.runtime_binding import bind

        directory = Path(directory)
        retained = rejection.replay(plan, output, directory, owner=owner, arguments=arguments, timeout=timeout)
        if retained is not None:
            raise RecoveryStop(retained["category"], retained["detail"], evidence=retained["evidence"])
        # A binding without rejection intent is an uncertain prior invocation.
        # It is never converted to no-launch evidence or sent a second time.
        require_fresh(plan, output, directory)
        try:
            require_dispatch(plan, output, owner)
        except BaseException as error:
            rejection.publish(plan, output, directory, owner=owner, arguments=arguments, timeout=timeout, error=error)
            raise
        # Publication failure is ambiguous after the first binding write; only
        # a durable rejection intent can later establish zero-launch evidence.
        bind(plan, output, directory, owner=owner)
        try:
            result = native(arguments, prompt, directory, timeout)
        except NativeRejected as rejected:
            rejection.publish(plan, output, directory, owner=owner, arguments=arguments, timeout=timeout,
                              error=rejected.original)
            raise rejected.original
        if isinstance(result, provider_capture.ZeroLaunch):
            if not result.cleanup_complete:
                raise RecoveryStop("BLOCKED_ENGINEERING", "Unstarted collector cleanup is incomplete")
            rejection.publish(plan, output, directory, owner=owner, arguments=arguments, timeout=timeout, error=result.error)
            raise result.error
        return result

    return launch
