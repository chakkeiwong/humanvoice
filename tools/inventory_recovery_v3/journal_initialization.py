"""Recover only the exact empty bootstrap without recreating committed usage."""

import json

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3 import journal_history
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist as atomic_persist
from tools.inventory_recovery_v3.reservations import regular_path

VERSION = "recovery-journal-initialization-v1"
FILES = ("consumption-head.json", "initialization-intent.json",
         "initialized.json", "reservations.json")
TEMPORARY = ".journal-initialization-"


def intent(journal):
    return journal_history.identified({"version": VERSION,
        "binding": journal_history.binding(journal), "record": {
            "version": "paired-recovery-reservations-v1", "policy": journal.policy,
            "binding": journal.binding, "sequences": {}, "lineages": {}, "splits": {}}})


def empty(journal):
    value = intent(journal)
    return journal_history.identified({**value["record"], "initialization_identity": value["identity"]})


def marker(journal, status):
    return {"version": VERSION, "policy": journal.policy["identity"],
            "binding": journal.binding, "initialization_identity": intent(journal)["identity"],
            "status": status}


def reader(journal):
    def read(name):
        path = regular_path(journal.root / name)
        return read_json(path) if path.exists() else None

    return read


def require_complete(journal, read=None):
    read = read or reader(journal)
    retained, observed = read("initialization-intent.json"), read("initialized.json")
    if digest(observed) == digest({"policy": journal.policy["identity"], "binding": journal.binding}):
        journal_history.require(retained is None, "New journal initialization cannot downgrade to legacy")
        return None
    journal_history.require(observed is not None, "Recovery initialization marker disappeared or changed")
    journal_history.require(digest(retained) == digest(intent(journal)), "Recovery initialization intent disappeared or changed")
    journal_history.require(digest(observed) == digest(marker(journal, "complete")),
                            "Recovery initialization incomplete or changed; use explicit offline initialization")
    return retained["identity"]


def publications(journal):
    record = empty(journal)
    head = {"version": "recovery-consumption-head-v1", "binding": journal_history.binding(journal),
            "committed": None, "pending": record}
    return [("initialization-intent.json", intent(journal)),
            ("initialized.json", marker(journal, "pending")),
            ("consumption-head.json", journal_history.identified(head)),
            ("reservations.json", record),
            ("consumption-head.json", journal_history.identified({**head, "committed": record, "pending": None})),
            ("initialized.json", marker(journal, "complete"))]


def members(journal):
    if not journal.root.exists():
        return []
    return sorted(path.name for path in journal.root.iterdir()
                  if not path.name.startswith(TEMPORARY) and path.name != "reservations.lock")


def inspect(journal, read, names):
    values = {name: read(name) for name in FILES}
    observed = values["initialized.json"]
    if (digest(observed) == digest({"policy": journal.policy["identity"], "binding": journal.binding})
            or digest(observed) == digest(marker(journal, "complete"))):
        require_complete(journal, read)
        head, current = journal_history.inspect(journal, read=read)
        journal_history.require(current is not None, "Committed recovery journal disappeared")
        return {"status": "READY", "step": 6, "head": head, "record": current,
                "dispatch_allowed": False, "live_authority": False}
    expected = dict.fromkeys(FILES)
    for step, (name, value) in enumerate([*publications(journal), (None, None)]):
        if digest(values) == digest(expected):
            journal_history.require(set(names) <= {key for key, item in expected.items() if item is not None},
                                    "Journal bootstrap contains unbound or spending evidence")
            return {"status": "UNINITIALIZED" if step == 0 else "INITIALIZING",
                    "step": step, "dispatch_allowed": False, "live_authority": False}
        if name is not None:
            expected[name] = value
    raise RecoveryStop("BLOCKED_ACCOUNTING", "Journal bootstrap lost its exact empty publication order")


def observe(journal):
    for _attempt in range(3):
        names, observed = members(journal), {}
        for name in FILES:
            path = regular_path(journal.root / name)
            observed[name] = path.read_bytes() if path.exists() else None

        def read(name, observed=observed):
            if observed[name] is None:
                return None
            value = json.loads(observed[name])
            if not isinstance(value, dict):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Journal artifact must contain a JSON object: " + name)
            return value

        error = None
        try:
            result = inspect(journal, read, names)
        except (ValueError, KeyError, TypeError, OSError, RecoveryStop) as caught:
            error = caught
        stable = names == members(journal)
        for name in (*FILES[1:], FILES[0]):
            path = regular_path(journal.root / name)
            stable = stable and (path.read_bytes() if path.exists() else None) == observed[name]
        if stable:
            if error is not None:
                raise error
            return result
    return {"status": "PUBLICATION_IN_PROGRESS", "dispatch_allowed": False, "live_authority": False}


def initialize(journal):
    journal.check()
    observe(journal)
    with journal.locked(reconcile=False):
        state = observe(journal)
        journal.check()
        if state["status"] == "READY":
            journal_history.reconcile(journal, journal.check)
            return journal.read()
        journal_history.require(state["status"] in {"UNINITIALIZED", "INITIALIZING"},
                                "Journal initialization changed during observation")
        for step in range(state["step"], 6):
            journal.check()
            retained = observe(journal)
            journal_history.require(retained == state, "Journal initialization changed before publication")
            name, value = publications(journal)[step]
            journal.check()
            atomic_persist(regular_path(journal.root / name), value, temporary_prefix=TEMPORARY)
            state = observe(journal)
        return journal.read()
