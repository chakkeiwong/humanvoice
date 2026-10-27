"""Enforce one admitted journal and sealed cross-generation consumption."""

from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path

FIELD = "inventory_document_recovery"
CHECKPOINT = "recovery-journal-checkpoint.json"
VERSION = "document-journal-checkpoint-v1"


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_ACCOUNTING", detail)


def descriptor(journal):
    journal.read()
    return {"path": str(regular_path(journal.path)), "binding": deepcopy(journal.binding),
            "policy_identity": journal.policy["identity"],
            "initialization_sha256": digest(regular_path(journal.root / "initialized.json").read_bytes())}


def reconcile_journal(authority, journal):
    authority.check()
    expected = authority.configuration.get("recovery_journal", {})
    require(expected.get("path") == str(regular_path(journal.path))
            and expected.get("binding") == journal.binding
            and expected.get("policy_identity") == journal.policy["identity"]
            and expected.get("initialization_sha256")
            == digest(regular_path(journal.root / "initialized.json").read_bytes()),
            "Reconciliation requires the admitted canonical recovery journal")
    journal.publication_check = authority.check
    with journal.locked():
        return journal.read()


def require_journal(authority, journal, plan=None):
    authority.check()
    expected = authority.configuration.get("recovery_journal")
    require(isinstance(expected, dict) and expected == descriptor(journal),
            "Execution requires its admitted canonical recovery journal")
    if plan is not None:
        marker = plan[FIELD]
        require(journal.policy == marker["policy"]
                and journal.binding["document"] == plan["bindings"]["source"]
                and journal.binding["migration"] == marker["migration_identity"],
                "Canonical journal differs from the native document plan")
    return journal.read()


def require_extension(previous, current):
    require(isinstance(previous, dict) and isinstance(current, dict),
            "Journal checkpoint lost its recorded consumption")
    for record in (previous, current):
        require(record.get("identity") == digest({key: value for key, value in record.items()
                                                  if key != "identity"}),
                "Journal checkpoint consumption identity changed")
        for sequence in record.get("sequences", {}).values():
            slots = sequence.get("slots", {})
            cancelled = [slot for slot in slots.values() if slot.get("state") == "cancelled"]
            require(set(slots) == {"canary", "retry"}, "Recovery sequence lost exact slot membership")
            if sequence.get("cancelled") is not None or cancelled:
                require(len(cancelled) == 1 and sequence.get("cancelled")
                        == cancelled[0].get("proof", {}).get("cancellation_identity")
                        and cancelled[0]["proof"].get("outcome") == "cancelled"
                        and cancelled[0]["proof"].get("resume_authorizations")
                        and cancelled[0]["proof"].get("quiescent") is True
                        and cancelled[0]["proof"].get("reported_tokens") is None
                        and cancelled[0]["proof"].get("invocation") == cancelled[0].get("invocation")
                        and all(slot.get("state") != "retired" or slot.get("cancellation_identity")
                                == sequence["cancelled"] for slot in slots.values()),
                        "Recovery cancellation flag lacks matching cancelled slot proof")
    for name, retained in previous.items():
        if name in {"identity", "sequences"}:
            continue
        observed = current.get(name)
        if name in {"lineages", "splits", "source_scopes"}:
            require(isinstance(observed, dict) and all(observed.get(key) == value
                    for key, value in retained.items()), "Committed journal membership disappeared or changed")
        else:
            require(observed == retained, "Committed journal binding or history changed")
    require(isinstance(current.get("sequences"), dict), "Journal lost its recovery sequences")
    advances = {"reserved": {"reserved", "dispatching", "complete", "incomplete", "cancelled", "retired"},
                "dispatching": {"dispatching", "complete", "incomplete", "cancelled"}}
    for identity, retained in previous.get("sequences", {}).items():
        observed = current["sequences"].get(identity)
        require(isinstance(observed, dict) and all(observed.get(key) == value
                for key, value in retained.items() if key != "slots"),
                "Committed recovery sequence disappeared or changed")
        require(set(observed) - set(retained) <= {"native_stage", "native_capacity", "cancelled"},
                "Recovery sequence acquired unsupported metadata")
        require(set(observed.get("slots", {})) == set(retained["slots"]),
                "Committed recovery slot membership changed")
        for role, slot in retained["slots"].items():
            selected = observed["slots"][role]
            def same(key, value, selected=selected):
                if key == "invocation" and isinstance(value, str) and value.startswith("native-intent:"):
                    allocation = selected.get("native_allocation", {})
                    if allocation.get("intent_identity") == value.removeprefix("native-intent:"):
                        return isinstance(selected.get("invocation"), str) and bool(selected["invocation"])
                return selected.get(key) == value

            require(isinstance(selected, dict) and selected.get("state")
                    in advances.get(slot["state"], {slot["state"]})
                    and all(same(key, value) for key, value in slot.items() if key != "state")
                    and (slot["state"] in advances or selected == slot),
                    "Committed recovery slot rolled back or changed")
    return current


def read_checkpoint(output, plan, journal_descriptor):
    path = regular_path(Path(output) / CHECKPOINT)
    require(path.exists(), "Committed stage recovery journal checkpoint disappeared")
    record = read_json(path)
    require(isinstance(record, dict) and set(record) == {"version", "output", "plan_identity",
            "descriptor", "record", "identity"}
            and record.get("identity") == digest({key: value for key, value in record.items() if key != "identity"})
            and record.get("version") == VERSION and record.get("output") == str(Path(output).absolute())
            and record.get("plan_identity") == plan["plan_identity"]
            and record.get("descriptor") == journal_descriptor, "Stage journal checkpoint changed its authority")
    require_extension(record["record"], record["record"])
    return record


def require_history(output, plan, authority, journal):
    current = require_journal(authority, journal, plan)
    bound = descriptor(journal)
    visited = set()
    while True:
        output = regular_path(Path(output) / "plan.json").parent
        require(str(output) not in visited and len(visited) < journal.policy["maximum_generations"],
                "Journal history repeats or exceeds document generations")
        visited.add(str(output))
        terminal_path = regular_path(output / "execution.json")
        terminal = read_json(terminal_path) if terminal_path.exists() else {}
        committed = terminal.get("status") in {"pass", "nonpass"}
        checkpoint_path = regular_path(output / CHECKPOINT)
        seal_path = regular_path(output / "allocation-seal.json")
        require(not seal_path.exists() or committed, "Sealed journal stage lost its terminal")
        if committed or checkpoint_path.exists():
            checkpoint = read_checkpoint(output, plan, bound)
            require_extension(checkpoint["record"], current)
            if committed:
                require(terminal.get("recovery_journal_checkpoint") == digest(checkpoint)
                        and terminal.get("plan_identity") == plan["plan_identity"],
                        "Terminal lost its sealed recovery journal checkpoint")
                require(not seal_path.exists() or read_json(seal_path).get("terminal_hash") == digest(terminal),
                        "Recovery journal terminal differs from native seal")
        transition = plan[FIELD]["transition"]
        if transition.get("version") != "inventory-settled-successor-v3":
            break
        output = regular_path(Path(transition["proof"]["predecessor"]) / "plan.json").parent
        plan = read_json(output / "plan.json")
        require(FIELD in plan and plan["plan_identity"] == transition["parent_plan_identity"]
                and regular_path(output / "allocation-seal.json").exists(),
                "Successor journal lost its sealed native predecessor")
    authority.check()
    return current


def checkpoint(output, plan, authority, journal, owner_check):
    require(owner_check() is True, "Journal checkpoint requires its exclusive stage owner")
    current = require_history(output, plan, authority, journal)
    path = regular_path(Path(output) / CHECKPOINT)
    value = {"version": VERSION, "output": str(Path(output).absolute()),
             "plan_identity": plan["plan_identity"], "descriptor": descriptor(journal), "record": current}
    value["identity"] = digest(value)
    if path.exists() and read_json(path) == value:
        return value
    terminal_path = regular_path(Path(output) / "execution.json")
    terminal = read_json(terminal_path) if terminal_path.exists() else {}
    require(terminal.get("status") not in {"pass", "nonpass"}
            and not regular_path(Path(output) / "allocation-seal.json").exists(),
            "Committed stage journal checkpoint cannot be replaced")
    require(owner_check() is True, "Journal checkpoint lost its stage owner before publication")
    require(require_journal(authority, journal, plan) == current,
            "Journal changed during checkpoint publication")
    persist(path, value)
    return value
