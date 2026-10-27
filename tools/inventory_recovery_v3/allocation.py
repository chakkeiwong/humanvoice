"""Bind paired recovery intents to real native allocation identities before launch."""

import time
from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.canary import require_validation
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path
from tools.inventory_recovery_v3.stage_capacity import require_earmark


class PairedLedger:
    def __init__(self, ledger, journal, sequence, role, *, owner_check, stop_check,
                 canary_check=None):
        self.native = ledger
        self.journal = journal
        self.sequence = sequence
        self.role = role
        self.owner_check = owner_check
        self.stop_check = stop_check
        self.canary_check = canary_check
        if role not in {"canary", "retry"}:
            raise ValueError("Paired native ledger requires a recovery role")

    def __getattr__(self, name):
        return getattr(self.native, name)

    def finish(self, entry, result, path):
        from tools.inventory_recovery_v3.native_settlement import settle_pair

        self.native.finish(entry, result, path)
        return settle_pair(self.journal, self.sequence, self.role,
                           owner_check=self.owner_check, stop_check=self.stop_check,
                           owner=getattr(self.owner_check, "__self__", None))

    def request_binding(self, key, entries, selected):
        from tools.inventory_recovery_v3.native_dispatch import modules

        plan, output = self.native.plan, self.native.path.parent
        execution, adapter = modules(plan)
        state = execution.layout(output, plan, entries)
        calls = adapter.implementation.automatic_recovery.attempt_calls(plan)
        index = next((index for index, call in enumerate(calls) if call["key"] == key), None)
        if index is None or state["pending"] is not None:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native allocation requires an exact reconciled request")
        descriptor = read_json(output / f"reconnect-attempts/{index:04d}.json")
        kind = "canary" if self.role == "canary" else "request"
        request = descriptor.get("request")
        ordinal = state["attempts"].get(state["logical"], 0) + 1 if (
            kind == "canary" or state["logical"] in state["selected"]) else 0
        if (state["mode"] != kind or descriptor.get("kind") != kind
                or descriptor.get("plan_identity") != plan["plan_identity"]
                or descriptor.get("index") != index or descriptor.get("logical") != state["logical"]
                or index != state["logical"] + ordinal * len(plan["calls"])
                or not state["incident"] or digest(state["incident"]) != selected["incident"]
                or descriptor.get("incident_hash") != selected["incident"]
                or state["incident"].get("request_hash") != selected["request_hash"]
                or descriptor.get("request_hash") != digest(request)
                or kind == "canary" and request != execution.CANARY
                or kind == "request" and digest(request) != selected["request_hash"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Pair role or incident differs from native request")
        return {"index": index, "descriptor_hash": digest(descriptor),
                "request_hash": digest(request), "incident_hash": selected["incident"]}

    def require_unallocated_intent(self, intent, record, slot):
        output = self.native.path.parent
        selected = record["sequences"][self.sequence]
        key = intent["key"]
        if (key not in self.native.allowed
                or intent["input_hash"] != self.native.allowed[key]["input_hash"]
                or selected.get("native_stage", {}).get("output") != str(output.absolute())
                or slot.get("native_allocation") is not None
                or slot.get("invocation") != "native-intent:" + intent["identity"]
                or slot.get("dispatch_order") != max(
                    existing.get("dispatch_order", 0) for sequence in record["sequences"].values()
                    for existing in sequence["slots"].values())):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Unallocated intent lost its exact dispatch scope")
        directory = output / f"calls/{intent['index']:04d}"
        regular_path(directory / "call.json")
        if directory.exists() and any(directory.iterdir()):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Unallocated intent has conflicting call evidence")
        for path in (Path(self.native.plan["snapshot"]) / ".humanvoice/runtime").glob("*/allocation-binding.json"):
            binding = read_json(regular_path(path))
            if binding.get("output") == str(output.absolute()) and (
                    binding.get("key") == key or binding.get("index") == intent["index"]):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Unallocated intent has conflicting runtime evidence")
        require_earmark(self.journal, record, self.sequence)

    def reserve(self, arm, case_id):
        journal = self.journal
        output = self.native.path.parent.absolute()
        intent_path = regular_path(journal.root / (self.sequence + "-" + self.role + "-allocation.json"))
        key = arm + ":" + case_id
        self.native.reload()
        selected = journal.read()["sequences"][self.sequence]
        scope = selected.get("native_stage", {})
        if (scope.get("output") != str(output)
                or scope.get("plan_identity") != self.native.plan["plan_identity"]
                or key not in self.native.allowed):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Pair allocation left its exact native stage membership")
        if any(entry["key"] == key for entry in self.native.record["calls"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Existing native allocation requires reconciliation, not a new intent")
        native_binding = self.request_binding(key, self.native.record["calls"], selected)
        with journal.locked():
            require_earmark(journal, journal.read(), self.sequence)
        value = {"version": "paired-native-allocation-v1", "sequence": self.sequence,
                 "role": self.role, "plan_identity": self.native.plan["plan_identity"],
                 "output": str(output), "key": key,
                 "input_hash": self.native.allowed[key]["input_hash"], **native_binding,
                 "prefix_count": len(self.native.record["calls"]),
                 "prefix_hash": digest(self.native.record["calls"])}
        identity = digest(value)
        if intent_path.exists():
            if read_json(intent_path) != {**value, "identity": identity}:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Pair allocation intent changed native membership")
        else:
            if selected["slots"][self.role]["state"] != "reserved":
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Dispatched pair lost its allocation intent")
            persist(intent_path, {**value, "identity": identity})
        pending = "native-intent:" + identity
        if selected["slots"][self.role]["state"] == "reserved":
            journal.dispatch(self.sequence, self.role, pending, owner_check=self.owner_check,
                             stop_check=self.stop_check, canary_check=self.canary_check)
        with journal.locked():
            record = journal.read()
            selected = record["sequences"][self.sequence]
            slot = selected["slots"][self.role]
            if (slot["state"] != "dispatching"
                    or slot.get("invocation") != pending):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Existing native dispatch requires reconciliation, not retransmission")
            if self.owner_check() is not True:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Native allocation requires exclusive ownership")
            self.stop_check()
            require_earmark(journal, record, self.sequence)
            self.require_unallocated_intent({**value, "identity": identity}, record, slot)
            if self.role == "retry":
                if not callable(self.canary_check):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Native retry requires current canary evidence")
                validation = self.canary_check(deepcopy(selected), deepcopy(record))
                expected = {name: selected[name] for name in
                            ("incident", "request_hash", "lineage", "profile_hash")}
                expected.update(policy_identity=journal.policy["identity"],
                                reservation_identity=self.sequence,
                                receipt_hash=selected["slots"]["canary"]["proof"]["receipt_hash"])
                require_validation(validation, expected, now=time.time())
                if self.owner_check() is not True:
                    raise RecoveryStop("BLOCKED_OWNERSHIP", "Native retry lost ownership during revalidation")
                self.stop_check()
                require_validation(validation, expected, now=time.time())
            if self.native.allocated(key) is not None:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Native allocation already exists; reconcile its intent")
            self.native.reload()
            if (len(self.native.record["calls"]) != value["prefix_count"]
                    or digest(self.native.record["calls"]) != value["prefix_hash"]
                    or self.request_binding(key, self.native.record["calls"], selected) != native_binding):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Native prefix changed after pair intent")
            entry = self.native.reserve(arm, case_id)
            slot.update(invocation=entry["invocation_id"], native_allocation={**value, "intent_identity": identity})
            journal.save(record)
            return entry

    def reconcile_allocation(self):
        journal = self.journal
        path = regular_path(journal.root / (self.sequence + "-" + self.role + "-allocation.json"))
        with journal.locked():
            if self.owner_check() is not True:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Allocation reconciliation requires exclusive ownership")
            self.stop_check()
            record = journal.read()
            selected = record["sequences"][self.sequence]
            slot = selected["slots"][self.role]
            intent = read_json(path)
            identity = intent["identity"]
            value = {key: item for key, item in intent.items() if key != "identity"}
            if (identity != digest(value) or intent["sequence"] != self.sequence or intent["role"] != self.role
                    or intent["plan_identity"] != self.native.plan["plan_identity"]
                    or intent["output"] != str(self.native.path.parent.absolute())
                    or selected.get("native_stage", {}).get("plan_identity") != intent["plan_identity"]
                    or slot["state"] != "dispatching"
                    or (self.native.path.parent / "allocation-seal.json").exists()):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Interrupted native allocation lost its exact intent")
            entry = self.native.allocated(intent["key"])
            self.native.reload()
            entries = self.native.record["calls"]
            count = intent.get("prefix_count")
            if (type(count) is not int or count < 0 or len(entries) not in {count, count + 1}
                    or digest(entries[:count]) != intent.get("prefix_hash")):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Native allocation does not follow its exact intent prefix")
            binding = self.request_binding(intent["key"], entries[:count], selected)
            if any(intent.get(name) != value for name, value in binding.items()):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Native allocation changed its request descriptor")
            if len(entries) == count:
                if entry is not None:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Unallocated intent already has a native invocation")
                self.require_unallocated_intent(intent, record, slot)
                return None
            if (entry is None or entry["input_hash"] != intent["input_hash"]
                    or entries[-1] != entry
                    or slot["invocation"] not in {"native-intent:" + identity, entry["invocation_id"]}):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Allocation silence cannot establish a safe retransmission")
            for other in record["sequences"].values():
                for other_role, existing in other["slots"].items():
                    if (other["identity"] != self.sequence or other_role != self.role) and (
                            existing.get("invocation") == entry["invocation_id"]):
                        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native invocation already belongs to another pair")
            slot.update(invocation=entry["invocation_id"], native_allocation={**value, "intent_identity": identity})
            journal.save(record)
            return deepcopy(entry)
