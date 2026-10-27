"""Durable paired recovery reservations under exclusive document ownership."""

import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3.canary import require_validation
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.lineage import (
    root_lineage,
    split_lineage,
    validate_lineage,
)
from tools.inventory_recovery_v3.policy import integer, require_capacity


def regular_path(path):
    path = Path(path).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("Mutable recovery state cannot use symlinks")
    if path.exists() and not path.is_file():
        raise ValueError("Recovery state must be a regular file")
    return path


def persist(path, record, *, temporary_prefix=None):
    path = regular_path(path)
    descriptor, name = tempfile.mkstemp(prefix=temporary_prefix or path.name + ".", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(record, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        regular_path(path)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class RecoveryReservations:
    def __init__(self, root, policy, binding):
        self.root = Path(root).absolute()
        regular_path(self.root / "reservations.json")
        self.policy = deepcopy(require_capacity(policy))
        if (not isinstance(binding, dict) or set(binding) != {"document", "migration", "authority"}
                or any(not isinstance(value, str) or not value for value in binding.values())):
            raise ValueError("Reservations require document, migration and authority identities")
        self.binding = deepcopy(binding)
        self.path = self.root / "reservations.json"

    @contextmanager
    def locked(self, *, reconcile=True):
        self.check()
        if reconcile:
            self.require_marker()
        self.root.mkdir(parents=True, exist_ok=True)
        lock = regular_path(self.root / "reservations.lock")
        with os.fdopen(os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Document reservation owner is active") from error
            self.check()
            if reconcile:
                from tools.inventory_recovery_v3 import journal_history

                self.require_marker()
                journal_history.reconcile(self, self.check)
            yield

    def check(self):
        guard = getattr(self, "publication_check", None)
        if guard is not None and guard() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Journal publication ownership was vetoed")
        return True

    def require_marker(self):
        from tools.inventory_recovery_v3.journal_initialization import require_complete

        return require_complete(self)

    def read(self):
        regular_path(self.path)
        if not self.path.exists():
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Recovery reservation journal is missing")
        self.require_marker()
        from tools.inventory_recovery_v3 import journal_history

        record = journal_history.read(self)
        if (record.get("policy") != self.policy or record.get("binding") != self.binding
                or record.get("version") != "paired-recovery-reservations-v1"
                or record.get("identity") != digest({key: value for key, value in record.items()
                                                       if key != "identity"})):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Recovery reservation binding changed")
        return record

    def save(self, record):
        from tools.inventory_recovery_v3 import journal_history

        record = {key: value for key, value in record.items() if key != "identity"}
        journal_history.save(self, {**record, "identity": digest(record)}, self.check)

    def initialize(self):
        from tools.inventory_recovery_v3.journal_initialization import initialize

        return initialize(self)

    def register_root(self, *, purpose, owned):
        lineage = root_lineage(self.binding["document"], purpose, owned)
        with self.locked():
            record = self.read()
            for selected in record["lineages"].values():
                validate_lineage(selected, ancestors=record["lineages"])
                if selected["identity"] == lineage["identity"]:
                    return deepcopy(selected)
                if (selected["parent"] is None and selected["purpose"] == purpose
                        and set(selected["owned"]) & set(lineage["owned"])):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Independent request roots overlap ownership")
            record["lineages"][lineage["identity"]] = lineage
            self.save(record)
            return deepcopy(lineage)

    def inherit_split(self, identity, children, *, evidence):
        if not isinstance(evidence, str) or not evidence:
            raise ValueError("Inherited split requires its source-bound rule identity")
        with self.locked():
            record = self.read()
            parent = record["lineages"][identity]
            descendants = split_lineage(parent, children, ancestors=record["lineages"],
                                        maximum_depth=self.policy["maximum_split_depth"])
            value = {"parent": identity, "root": parent["root"],
                     "children": [child["identity"] for child in descendants],
                     "extra_calls": 0, "inherited_evidence": evidence}
            previous = record["splits"].get(identity)
            if previous is not None:
                if previous != value or any(record["lineages"].get(child["identity"]) != child for child in descendants):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited split changed its frozen ancestry")
                return deepcopy(descendants)
            if any(slot["state"] == "dispatching" for row in record["sequences"].values()
                   for slot in row["slots"].values()):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Cannot import ancestry during unresolved dispatch")
            count = sum(len(row["children"]) for row in record["splits"].values() if row["root"] == parent["root"])
            if count + len(descendants) > self.policy["maximum_lineage_children"]:
                raise RecoveryStop("BLOCKED_DECOMPOSITION", "Inherited root child allowance is exhausted")
            record["splits"][identity] = value
            record["lineages"].update({child["identity"]: child for child in descendants})
            self.save(record)
            return deepcopy(descendants)

    def split(self, identity, children):
        with self.locked():
            record = self.read()
            parent = record["lineages"][identity]
            descendants = split_lineage(parent, children, ancestors=record["lineages"],
                                        maximum_depth=self.policy["maximum_split_depth"])
            value = {"parent": identity, "root": parent["root"],
                     "children": [child["identity"] for child in descendants],
                     "extra_calls": len(descendants) - 1}
            previous = record["splits"].get(identity)
            if previous is not None:
                if previous != value or any(record["lineages"].get(child["identity"]) != child
                                            for child in descendants):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Persisted split cannot change membership")
                return deepcopy(descendants)
            if any(slot["state"] == "dispatching" for row in record["sequences"].values()
                   for slot in row["slots"].values()):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Cannot split an unresolved native allocation")
            root_children = sum(len(row["children"]) for row in record["splits"].values()
                                if row["root"] == parent["root"])
            expansion = sum(row["extra_calls"] for row in record["splits"].values())
            if root_children + len(descendants) > self.policy["maximum_lineage_children"]:
                raise RecoveryStop("BLOCKED_DECOMPOSITION", "Root child limit cannot renew after splitting")
            if expansion + value["extra_calls"] > self.policy["split_allowance"]:
                raise RecoveryStop("BLOCKED_BUDGET", "Document split expansion exceeds reserved capacity")
            record["splits"][identity] = value
            record["lineages"].update({child["identity"]: child for child in descendants})
            self.save(record)
            return deepcopy(descendants)

    def inherit_history(self, history, lineages, handoff):
        from tools.inventory_recovery_v3.inheritance import validate

        validate(history)
        if history["source"] != self.binding["document"] or set(lineages) != {
                row["identity"] for row in history["sequences"]}:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited recovery lacks complete native ownership")
        with self.locked():
            record = self.read()
            rows = {}
            for row in history["sequences"]:
                lineage = record["lineages"][lineages[row["identity"]]]
                validate_lineage(lineage, ancestors=record["lineages"])
                if lineage["purpose"] != row["request"]["purpose"]:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited recovery changed its native purpose")
                rows[row["identity"]] = {"lineage": lineage["identity"], "root": lineage["root"],
                    "profile_hash": row["profile_hash"], "request_hash": row["request_hash"],
                    "retry_allocated": row["retry"] is not None, "diagnostic_only": row["diagnostic_only"],
                    "evidence_identity": row["identity"]}
            expected = {"history_identity": history["identity"], "sequences": rows, "handoff": deepcopy(handoff)}
            if handoff["sequence_identity"] not in rows or not rows[handoff["sequence_identity"]]["diagnostic_only"]:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited handoff does not identify an unused retry")
            if record.get("inherited_recovery") is not None:
                if record["inherited_recovery"] != expected:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited recovery membership or handoff changed")
                return deepcopy(expected)
            if record["sequences"]:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Cannot import or replace history after prospective reservation")
            record["inherited_recovery"] = expected
            self.save(record)
            return deepcopy(expected)

    def reserve(self, *, lineage, incident, request_hash, profile_hash, inherited_diagnostic=None, check_only=False):
        if type(check_only) is not bool:
            raise TypeError("Reservation check mode must be boolean")
        fields = {"lineage": lineage, "incident": incident,
                  "request_hash": request_hash, "profile_hash": profile_hash}
        if inherited_diagnostic is not None:
            fields["inherited_diagnostic"] = inherited_diagnostic
        if any(not isinstance(value, str) or not value for value in fields.values()):
            raise ValueError("Recovery sequence requires exact nonempty identities")
        key = digest(fields)
        with self.locked():
            record = self.read()
            selected = record["lineages"].get(lineage)
            if selected is None:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Recovery requires a registered source lineage")
            validate_lineage(selected, ancestors=record["lineages"])
            if lineage in record["splits"]:
                raise RecoveryStop("BLOCKED_DECOMPOSITION", "Split parent cannot renew its exact retry")
            sequences = record["sequences"]
            if key in sequences:
                return deepcopy(sequences[key])
            for sequence in sequences.values():
                if any(slot["state"] == "dispatching" for slot in sequence["slots"].values()):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Unresolved dispatch retains its reservation")
                if sequence["incident"] == incident:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Incident was already bound to another recovery")
            lineage_rows = [row for row in sequences.values() if row["lineage"] == lineage]
            root_rows = [row for row in sequences.values() if row["root"] == selected["root"]]
            inherited = record.get("inherited_recovery", {})
            legacy = inherited.get("sequences", {})
            legacy_lineage = [row for row in legacy.values() if row["lineage"] == lineage]
            legacy_root = [row for row in legacy.values() if row["root"] == selected["root"]]
            consumed = {row.get("inherited_diagnostic") for row in sequences.values()}
            if inherited_diagnostic is not None:
                previous = legacy.get(inherited_diagnostic)
                if (previous is None or not previous["diagnostic_only"] or previous["retry_allocated"]
                        or inherited.get("handoff") != {"sequence_identity": inherited_diagnostic,
                                                       "incident_hash": incident}
                        or previous["lineage"] != lineage or previous["request_hash"] != request_hash
                        or previous["profile_hash"] != profile_hash or inherited_diagnostic in consumed):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Historical diagnostic continuation changed or was already consumed")
            elif any(row["diagnostic_only"] and row["evidence_identity"] not in consumed
                     and row["request_hash"] == request_hash and row["profile_hash"] == profile_hash
                     for row in legacy_lineage):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Unused historical retry requires its exact diagnostic handoff")
            if (len(lineage_rows) + len(legacy_lineage) >= self.policy["lineage_sequences"]
                    or len(root_rows) + len(legacy_root) >= self.policy["root_sequences"]
                    or any(row["retry_allocated"] and row["profile_hash"] == profile_hash for row in legacy_lineage)
                    or any(row["profile_hash"] == profile_hash and not row.get("cancelled") for row in lineage_rows)):
                raise RecoveryStop("BLOCKED_DECOMPOSITION", "Lineage requires a qualified split or fallback")
            if len(sequences) >= self.policy["incident_allowance"]:
                raise RecoveryStop("BLOCKED_BUDGET", "Cannot reserve a complete canary and retry sequence")
            sequence = {**fields, "root": selected["root"], "identity": key, "slots": {
                role: {"state": "reserved", "tokens": self.policy["token_reservation_per_call"]}
                for role in ("canary", "retry")}}
            if check_only:
                return deepcopy(sequence)
            sequences[key] = sequence
            self.save(record)
            return deepcopy(sequence)

    def bind_native_stage(self, identity, output, *, owner_check, stop_check):
        from humanvoice.artifacts import read_json
        from tools.inventory_recovery_v3.native_dispatch import validate_plan

        output = Path(output).absolute()
        with self.locked():
            if owner_check() is not True:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Binding requires exclusive stage ownership")
            stop_check()
            record = self.read()
            sequence = record["sequences"][identity]
            plan = validate_plan(read_json(regular_path(output / "plan.json")))
            terminal_path = regular_path(output / "execution.json")
            terminal = read_json(terminal_path) if terminal_path.exists() else {}
            if ((output / "allocation-seal.json").exists()
                    or terminal.get("status") not in {None, "prepared", "executing"}
                    or terminal and terminal.get("plan_identity") != plan["plan_identity"]
                    or plan["bindings"]["source"] != self.binding["document"]
                    or digest(plan["profile"]) != sequence["profile_hash"]):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Native pair requires an active same-source stage")
            binding = {"output": str(output), "plan_identity": plan["plan_identity"],
                       "native_policy_identity": digest(plan["recovery"]),
                       "policy_identity": self.policy["identity"], **self.binding}
            if sequence.get("native_stage") is not None:
                if sequence["native_stage"] != binding:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Native stage binding cannot change")
                return deepcopy(binding)
            if any(slot["state"] != "reserved" for slot in sequence["slots"].values()):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Native scope must be bound before dispatch")
            sequence["native_stage"] = binding
            self.save(record)
            return deepcopy(binding)

    def dispatch(self, identity, role, invocation, *, owner_check, stop_check, canary_check=None,
                 clock=time.time):
        if role not in {"canary", "retry"} or not isinstance(invocation, str) or not invocation:
            raise ValueError("Dispatch requires a role and native allocation identity")
        with self.locked():
            if owner_check() is not True:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Dispatch requires the exclusive spending owner")
            stop_check()
            record = self.read()
            sequence = record["sequences"][identity]
            lineage = record["lineages"].get(sequence["lineage"])
            if lineage is None or lineage["root"] != sequence["root"]:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Dispatch lost its registered ancestry")
            validate_lineage(lineage, ancestors=record["lineages"])
            if sequence["lineage"] in record["splits"]:
                raise RecoveryStop("BLOCKED_DECOMPOSITION", "Split parent cannot dispatch reserved work")
            slot = sequence["slots"][role]
            if slot["state"] != "reserved":
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Dispatch requires reconciliation; never purchase twice")
            for other in record["sequences"].values():
                for existing in other["slots"].values():
                    if existing["state"] == "dispatching" or existing.get("invocation") == invocation:
                        raise RecoveryStop("BLOCKED_ACCOUNTING", "Pending or repeated native invocation")
            if role == "retry" and sequence["slots"]["canary"]["state"] != "complete":
                raise RecoveryStop("BLOCKED_EXTERNAL", "Manuscript retry requires its completed canary")
            if role == "retry":
                canary = sequence["slots"]["canary"]
                latest = max(existing.get("dispatch_order", 0)
                             for other in record["sequences"].values()
                             for existing in other["slots"].values())
                if not canary.get("dispatch_order") or canary["dispatch_order"] != latest:
                    raise RecoveryStop("BLOCKED_EXTERNAL", "Canary superseded by another native dispatch")
                if not callable(canary_check):
                    raise RecoveryStop("BLOCKED_EXTERNAL", "Retry requires a fresh unsuperseded canary")
                validation = canary_check(deepcopy(sequence), deepcopy(record))
                expected = {name: sequence[name] for name in
                            ("incident", "request_hash", "lineage", "profile_hash")}
                expected.update(policy_identity=self.policy["identity"],
                                reservation_identity=sequence["identity"],
                                receipt_hash=canary["proof"]["receipt_hash"])
                require_validation(validation, expected, now=clock())
                if owner_check() is not True:
                    raise RecoveryStop("BLOCKED_OWNERSHIP", "Spending ownership changed during canary validation")
                stop_check()
                require_validation(validation, expected, now=clock())
                slot["canary_validation"] = deepcopy(validation)
            order = 1 + max((existing.get("dispatch_order", 0)
                             for other in record["sequences"].values()
                             for existing in other["slots"].values()), default=0)
            slot.update(state="dispatching", invocation=invocation, dispatch_order=order)
            self.save(record)
            return deepcopy(slot)

    def settle(self, identity, role, *, receipt, verify):
        if role not in {"canary", "retry"}:
            raise ValueError("Unknown recovery role")
        with self.locked():
            record = self.read()
            sequence = record["sequences"][identity]
            slot = sequence["slots"][role]
            proof = verify(deepcopy(receipt), deepcopy(sequence), role)
            if (not isinstance(proof, dict) or proof.get("invocation") != slot.get("invocation")
                    or proof.get("quiescent") is not True
                    or proof.get("outcome") not in {"complete", "incomplete", "cancelled"}
                    or not isinstance(proof.get("receipt_hash"), str) or not proof["receipt_hash"]):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Settlement lacks a verified unique quiescent receipt")
            usage = proof.get("reported_tokens")
            if usage is not None:
                integer(usage, "reported_tokens")
                if usage > slot["tokens"]:
                    raise RecoveryStop("BLOCKED_BUDGET", "Native usage exceeds its reservation")
            if proof["outcome"] == "complete" and (usage is None or role == "canary"
                    and proof.get("canary_valid") is not True):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Completed receipt lacks usage or canary validation")
            if proof["outcome"] == "cancelled" and (not proof.get("cancellation_identity")
                    or not proof.get("resume_authorizations") or usage is not None):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Cancellation lacks exact authorized zero-launch evidence")
            if slot["state"] in {"complete", "incomplete", "cancelled"}:
                if slot.get("proof") != proof:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Settled receipt changed")
                return deepcopy(slot)
            if slot["state"] != "dispatching":
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Unallocated slot cannot be settled")
            for other in record["sequences"].values():
                if any(existing.get("proof", {}).get("receipt_hash") == proof["receipt_hash"]
                       for existing in other["slots"].values()):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Runtime receipt was already consumed")
            slot.update(state=proof["outcome"], proof=deepcopy(proof))
            if proof["outcome"] == "cancelled":
                sequence["cancelled"] = proof["cancellation_identity"]
                for sibling in sequence["slots"].values():
                    if sibling["state"] == "reserved":
                        sibling.update(state="retired", cancellation_identity=proof["cancellation_identity"])
            self.save(record)
            return deepcopy(slot)

    def status(self):
        from tools.inventory_recovery_v3.journal_initialization import observe

        state = observe(self)
        if state["status"] != "READY":
            return state
        record, head = state["record"], state["head"]
        if head["pending"] is not None and record != head["pending"]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Recovery journal has pending publication; reconcile under ownership")
        slots = [slot for row in record["sequences"].values() for slot in row["slots"].values()]
        return {"sequences_reserved": len(record["sequences"]),
                "sequences_available": self.policy["incident_allowance"] - len(record["sequences"]),
                "calls_reserved": len(slots), "tokens_reserved": sum(slot["tokens"] for slot in slots),
                "unresolved_dispatches": sum(slot["state"] == "dispatching" for slot in slots),
                "completed": sum(slot["state"] == "complete" for slot in slots),
                "live_authority": False, "dispatch_allowed": False}
