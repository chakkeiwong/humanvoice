"""Retain initial campaign floors across interrupted binding publication."""

import json

from tools.inventory_recovery_v3.campaign_history import identified
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import regular_path

INTENT = "binding-intent.json"
MARKER = "binding-initialized.json"
TARGET = "campaign-binding.json"
VERSION = "campaign-binding-publication-v1"


def require(condition):
    if not condition:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Campaign binding lost its owned publication anchor")


def intent(binding):
    return identified({"version": VERSION, "binding": binding})


def marker(binding, status):
    return identified({"version": VERSION, "intent_identity": intent(binding)["identity"],
                       "binding_identity": binding["identity"], "status": status})


def observe(root):
    observed = {}
    for name in (INTENT, MARKER, TARGET):
        path = regular_path(root / name)
        observed[name] = path.read_bytes() if path.exists() else None
    values = {}
    for name, content in observed.items():
        values[name] = json.loads(content) if content is not None else None
        require(content is None or isinstance(values[name], dict))
    retained = values[INTENT]
    if retained is None:
        require(all(value is None for value in values.values()))
        return None, 0, observed
    binding = retained.get("binding")
    require(isinstance(binding, dict) and binding == identified(binding) and retained == intent(binding))
    steps = ((INTENT, retained), (MARKER, marker(binding, "pending")),
             (TARGET, binding), (MARKER, marker(binding, "complete")))
    expected = dict.fromkeys(values)
    for step, (name, value) in enumerate(steps, 1):
        expected[name] = value
        if expected == values:
            return binding, step, observed
    require(False)


def stable(root, observed):
    require(all((regular_path(root / name).read_bytes() if (root / name).exists() else None) == content
                for name, content in observed.items()))


def publish(root, binding, *, persist, check):
    retained, step, observed = observe(root)
    require(retained is None or retained == binding)
    steps = ((INTENT, intent(binding)), (MARKER, marker(binding, "pending")),
             (TARGET, binding), (MARKER, marker(binding, "complete")))
    for name, value in steps[step:]:
        check()
        stable(root, observed)
        persist(regular_path(root / name), value, temporary_prefix=".campaign-publication-")
        retained, step, observed = observe(root)
        require(retained == binding)
    check()
    require(step == 4)
