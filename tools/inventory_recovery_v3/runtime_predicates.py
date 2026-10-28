"""Acyclic admission leaf, owned write guard and read-only dispatch floors."""

from contextvars import ContextVar
from copy import deepcopy

from humanvoice.artifacts import digest
from tools import durable_program_supervisor as durable
from tools.inventory_recovery_v3 import (
    installed_authority,
    runtime_closure,
    stop_authority,
)
from tools.inventory_recovery_v3.failures import RecoveryStop

ACTIVE = ContextVar("inventory_runtime_leaf_active", default=False)


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_OWNERSHIP", detail)


class RuntimeLeaf:
    """External admission must already verify release/preflight/host authority."""

    def __init__(self, configuration, *, require_admission, require_controls):
        if not callable(require_admission) or not callable(require_controls):
            raise TypeError("Runtime leaf requires external admission and monotonic control authority")
        self._configuration = deepcopy(configuration)
        self._identity = digest(configuration)
        self._admission = require_admission
        self._controls = require_controls

    @property
    def configuration(self):
        return deepcopy(self._configuration)

    def __call__(self):
        require(not ACTIVE.get(), "Runtime admission leaf cannot recursively enter authority")
        token = ACTIVE.set(True)
        try:
            configuration = self._configuration
            require(digest(configuration) == self._identity
                    and digest(self._admission()) == self._identity,
                    "External admission differs from the retained configuration")
            adoption = configuration["handover"]
            runtime_closure.verify(configuration["runtime_closure"], adoption=adoption)
            installed_authority.require_environment(adoption["installed"])
            expected_stops = [*adoption["stop_bindings"],
                {"root": configuration["campaign_root"], "contract": configuration["contract"]}]
            require(configuration["stop_bindings"] == expected_stops
                    and len({row["root"] for row in expected_stops}) == len(expected_stops),
                    "Runtime leaf lost inherited or prospective stop authority")
            try:
                stop_authority.verify(configuration, self._controls(deepcopy(configuration)))
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise RecoveryStop("USER_STOPPED", "Retained stop control evidence is unavailable or malformed") from error
            require(not any(durable.alive(owner) for record in adoption["records"]
                            for owner in record["predecessor"]["owners"]),
                    "A retained predecessor process is still alive")
            return True
        finally:
            ACTIVE.reset(token)


class OwnedPredicates:
    """Native writers use check; dispatch additionally validates mutable floors."""

    def __init__(self, leaf, lease):
        self.leaf, self.lease = leaf, lease

    def check(self):
        require(self.leaf() is True, "Runtime leaf vetoed execution")
        require(self.lease.membership.configuration == digest(self.leaf.configuration)
                and self.lease.check() is True, "Execution requires the complete admitted lease")
        return True

    def dispatch(self, floors):
        self.check()
        configuration = self.leaf.configuration
        scope = configuration["execution_authority"]
        require(floors.seed["configuration"] == digest(configuration)
                and str(floors.path("account")) == scope["account"]
                and floors.seed["grant"] == scope["grant"]
                and floors.seed["grant_identity"] == scope["grant_identity"],
                "Dispatch floors differ from the admitted authority")
        for resource in ("account", "stages"):
            state = floors.status(resource)
            if state["status"] not in {"READY", "EXTENDED"}:
                raise RecoveryStop("BLOCKED_EXTERNAL",
                                   "Reconcile native consumption before dispatch")
        self.check()
        return True
