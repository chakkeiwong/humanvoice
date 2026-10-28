"""Wrap native account writes without changing frozen accounting implementations."""

from pathlib import Path
from types import FunctionType

from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import regular_path


def wrap(function, *, floors, operation, check):
    namespace = dict(function.__globals__)
    path = floors.path("account")

    def read(target):
        if Path(target).absolute() == path:
            check()
            state = floors.reconcile("account")
            pending = state["head"]["pending"]
            if pending is not None and pending["operation"] != operation:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Reconcile the exact pending account operation first")
        return function.__globals__["read_json"](target)

    def write(target, value):
        check()
        if regular_path(target) == path:
            return floors.write("account", value, operation=operation, writer=function.__globals__["write_json"])
        return function.__globals__["write_json"](target, value)

    namespace.update(read_json=read, write_json=write)
    if "save" in namespace:
        def save(target, value):
            check()
            return function.__globals__["save"](target, value)

        namespace["save"] = save
    invoke = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    invoke.__kwdefaults__ = function.__kwdefaults__
    return invoke


def settle(function, output, authority):
    authority.owned_check()
    if authority.consumption is None:
        return function(output, account=authority.account_path)
    native = wrap(function, floors=authority.consumption, operation="settle", check=authority.owned_check)
    return native(output, account=authority.account_path)
