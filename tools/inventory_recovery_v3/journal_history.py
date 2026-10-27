"""Keep a write-ahead consumption floor before native allocation or checkpoints."""

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path


def identified(value):
    value = {key: item for key, item in value.items() if key != "identity"}
    return {**value, "identity": digest(value)}


def binding(journal):
    return {"path": str(regular_path(journal.path)), "policy": journal.policy["identity"],
            "binding": journal.binding}


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_ACCOUNTING", detail)


def inspect(journal, *, read=None):
    from tools.inventory_recovery_v3.journal_binding import require_extension
    from tools.inventory_recovery_v3.journal_initialization import (
        reader,
        require_complete,
    )

    read = read or reader(journal)
    initialization = require_complete(journal, read)
    head = read("consumption-head.json")
    require(head is not None, "Recovery journal consumption head disappeared")
    require(isinstance(head, dict) and head == identified(head)
            and set(head) == {"version", "binding", "committed", "pending", "identity"}
            and head.get("version") == "recovery-consumption-head-v1"
            and head.get("binding") == binding(journal), "Recovery consumption head changed its binding")
    prior, pending = head["committed"], head["pending"]
    require(prior is not None or pending is not None, "Consumption head lost initial publication")
    require(initialization is None or prior is not None,
            "Complete journal initialization lost its committed initial head")
    for record in (prior, pending):
        if record is not None:
            require(isinstance(record, dict) and record.get("policy") == journal.policy
                    and record.get("binding") == journal.binding, "Consumption head changed document policy")
            require(record.get("initialization_identity") == initialization,
                    "Consumption head changed its permanent initialization identity")
            require_extension(record, record)
    if prior is not None and pending is not None:
        require_extension(prior, pending)
    current = read("reservations.json")
    require(current is not None, "Committed recovery journal disappeared")
    require(current == prior or pending is not None and current == pending,
            "Recovery journal lost write-ahead consumption membership")
    return head, current


def read(journal):
    head, current = inspect(journal)
    if head["pending"] is not None and current != head["pending"]:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Recovery journal has pending publication; reconcile under ownership")
    return current


def reconcile(journal, check):
    head, current = inspect(journal)
    if head["pending"] is None:
        return current
    if current != head["pending"]:
        check()
        persist(regular_path(journal.path), head["pending"])
    check()
    persist(regular_path(journal.root / "consumption-head.json"),
            identified({**head, "committed": head["pending"], "pending": None}))
    return read(journal)


def save(journal, record, check):
    from tools.inventory_recovery_v3.journal_binding import require_extension

    path = regular_path(journal.root / "consumption-head.json")
    require(path.exists(), "Cannot recreate a lost consumption head")
    current = reconcile(journal, check)
    require_extension(current or record, record)
    if current == record:
        return
    head = {"version": "recovery-consumption-head-v1", "binding": binding(journal),
            "committed": current, "pending": record}
    check()
    persist(path, identified(head))
    reconcile(journal, check)
