"""Replay native history without publishing shared warmup diagnostics."""

from contextlib import contextmanager

from tools import parallel_verification_replay as verification
from tools.delayed_network_runtime import replaced_aliases


@contextmanager
def nonpublishing():
    native = verification.warm_settlements

    def warm(record, *, workers=16, progress=None):
        return native(record, workers=workers, progress=None)

    with replaced_aliases(native, warm):
        yield
