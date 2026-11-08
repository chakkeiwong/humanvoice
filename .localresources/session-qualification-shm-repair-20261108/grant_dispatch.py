"""Bind the sealed-plan dispatcher before a grant reader copies its globals."""

from contextlib import contextmanager

from tools import automatic_call_grant as grants
from tools.delayed_network_runtime import replaced_aliases
from tools.inventory_recovery_v3 import accounting


def settled_usage(output):
    # Keep a distinct callable identity: native scopes replace grant aliases.
    # Aliasing accounting.completed_usage directly would replace that dispatch
    # function too and make a nested scope call itself recursively.
    return accounting.completed_usage(output)


@contextmanager
def scope():
    # grant_extension.reader constructs a FunctionType with copied globals.
    # Installing the native history scope later cannot update that dictionary.
    # Select the existing versioned verifier before constructing the extension;
    # native status still compares its result with the retained settlement event.
    with replaced_aliases(grants.settled_usage, settled_usage):
        yield
