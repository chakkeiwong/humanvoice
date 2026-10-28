"""Private legacy job readers using nonmutating inherited-lock verification."""

from types import FunctionType

from tools import inventory_history_job as historical
from tools.inventory_recovery_v3.descriptors import exclusive_descriptor

CAPSULE = historical.CAPSULE
_namespace = {**historical.__dict__, "exclusive_descriptor": exclusive_descriptor}


def _clone(function):
    result = FunctionType(function.__code__, _namespace, function.__name__,
                          function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


binding = _clone(historical.binding)
_namespace["binding"] = binding
prepare = _clone(historical.prepare)
require = _clone(historical.require)

__all__ = ["CAPSULE", "binding", "exclusive_descriptor", "prepare", "require"]
