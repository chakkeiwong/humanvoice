"""Prepare and replay a native budget successor without admitting live execution."""

import fcntl
import importlib.util
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import FunctionType

from humanvoice.artifacts import digest, read_json
from tools import sol_inventory_reconnect_runtime
from tools.inventory_history_handover import safe_path
from tools.inventory_recovery_v2 import continuation as historical_stage
from tools.inventory_recovery_v2 import execution as historical_execution
from tools.inventory_recovery_v2 import qualification
from tools.inventory_recovery_v2 import runtime as historical
from tools.inventory_recovery_v2.replay import replay as native_replay
from tools.inventory_recovery_v3 import continuation, runtime, semantics, successor
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path


def immutable(path, value):
    path = regular_path(path)
    if path.exists():
        if read_json(path) != value:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Frozen successor evidence changed: " + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        persist(path, value)


specification = importlib.util.spec_from_file_location("tools._budget_successor_stage", historical_stage.__file__)
bridge = importlib.util.module_from_spec(specification)
specification.loader.exec_module(bridge)
bridge.adapter = runtime
bridge.immutable = immutable


def reconstruct(output, plan, entries):
    with historical.runtime(plan, output):
        return historical_execution.layout(output, plan, entries)


class Stage(bridge.Stage):
    def __init__(self, output, transition):
        successor.require_transition(transition)
        super().__init__(safe_path(output), transition)
        self.preparing = False
        self.implementation.verify_membership = FunctionType(
            bridge.original.verify_membership.__code__, self.implementation.__dict__)

    @contextmanager
    def preparation(self):
        if self.preparing:
            yield
            return
        self.output.mkdir(parents=True, exist_ok=True)
        with regular_path(self.output / "prepare.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Another preparer owns this successor") from error
            self.preparing = True
            try:
                yield
            finally:
                self.preparing = False

    def source_gate(self):
        if self.transition.get("version") == continuation.VERSION:
            expected = continuation.require_transition(self.transition)
        else:
            expected = successor.budget_transition(self.transition["migration"], self.transition["policy"],
                account_path=bridge.original.account.ACCOUNT, verify_settlement=historical.verify_settlement,
                reconstruct=reconstruct, verify_qualification=qualification.verify)
        if expected != self.transition:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Prepared successor changed its independently replayed source")
        semantics.validate_rules(self.transition["rules"], policy=self.transition["policy"],
            inherited=self.transition["inherited_rules"], origin=self.transition["migration"])
        return expected

    def plan_for(self, snapshot, proof, current, authority, *, admission_report=None):
        return successor.plan_for(snapshot, self.transition, current, authority, proof=proof, admission_report=admission_report)

    def probed_proof(self, report):
        proof = deepcopy(self.transition["proof"])
        proof["failed_request"] = deepcopy(report["first_request"])
        return proof

    @contextmanager
    def replay(self, plan, output, proof, historical_validator):
        def validate(root, reference):
            folder = Path(root) / Path(reference["path"]).parent
            capture_path = folder / "qualification-capture.json"
            capture = read_json(capture_path) if capture_path.exists() else {}
            for adapter in (runtime, historical, sol_inventory_reconnect_runtime):
                if capture.get("contract") != adapter.contract():
                    continue
                source_profile = read_json(folder / "inputs/api-request.json")["profile"]
                implementation = adapter.implementation
                with implementation.qualified.routing.binding_scope(), (
                        implementation.qualified.stream.grammar_scope((source_profile,))), (
                        implementation.active.runtime(source_profile)):
                    return implementation.capture.validate_record(root, reference)
            return historical_validator(root, reference)

        with native_replay(plan, output, proof, validate) as checked:
            yield checked

    def probe(self, **keywords):
        from tools.inventory_recovery_v3 import probe

        with self.preparation():
            return probe.run(self, **keywords)

    def current_authority(self):
        with runtime.settlement_scope():
            current = bridge.original.account.validate_account(read_json(bridge.original.account.ACCOUNT))
            authority = bridge.original.grant_status(bridge.original.GRANT)
        grant = read_json(regular_path(bridge.original.GRANT))
        if (Path(grant["account"]).resolve() != Path(bridge.original.account.ACCOUNT).resolve()
                or grant["identity"] != authority["identity"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Preparation grant changed its canonical account")
        return current, authority

    def prepared_account(self, anchor, current, authority):
        before = deepcopy(current)
        for name in ("events", "plans"):
            if type(anchor[name]) is not int or not 0 <= anchor[name] <= len(current[name]):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Prepared authority lost its exact account prefix")
            before[name] = before[name][:anchor[name]]
        for name in ("reservation_ceiling", "gross_reservation_ceiling"):
            before[name] = anchor[name]
        if digest(before) != anchor["account_hash"] or authority["identity"] != anchor["grant"]["identity"]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Prepared authority changed after construction")
        return before

    def require_capacity(self, plan, current, authority):
        maximum = runtime.automatic_recovery.call_limit(plan)
        matches = [entry for entry in current["plans"] if entry["output"] == str(self.output)
                   or entry["plan_identity"] == plan["plan_identity"]]
        if matches:
            expected = {"plan_identity": plan["plan_identity"], "output": str(self.output),
                        "calls": maximum, "reserved_tokens": maximum * 544000,
                        "prior_reservation_ceiling": plan["prior_reservation_ceiling"],
                        "account_allowance": plan["account_allowance"]}
            if matches != [expected]:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Preparation changed its native reservation")
            return
        stages_path = regular_path(Path(bridge.original.GRANT).with_suffix(".stages.json"))
        stages = read_json(stages_path)["stages"] if stages_path.exists() else []
        held = [entry for entry in stages if entry["output"] == str(self.output)
                or entry["plan_identity"] == plan["plan_identity"]]
        expected = {"output": str(self.output), "plan_identity": plan["plan_identity"],
                    "grant_identity": authority["identity"], "maximum_calls": maximum}
        if held and held != [expected]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Preparation changed its retained call hold")
        if (maximum > authority["available"] + (maximum if held else 0)
                or current["reservation_ceiling"] + maximum * 544000 > current["allowance"]):
            raise RecoveryStop("BLOCKED_BUDGET", "Prepared successor no longer fits current authority")

    def prepare(self):
        with self.preparation():
            self.source_gate()
            if (self.output / "plan.json").exists():
                plan = self.validate(source_checked=True)
                self.prepared_execution(plan)
                return plan
            report = self.probe(source_checked=True)
            proof = self.probed_proof(report)
            self.copy_snapshot(self.snapshot, proof)
            current, authority = self.current_authority()
            intent_path = regular_path(self.output / "preparation-intent.json")
            if intent_path.exists():
                intent = read_json(intent_path)
                if (set(intent) != {"transition", "anchor", "plan", "identity"}
                        or intent["identity"] != digest({key: value for key, value in intent.items() if key != "identity"})
                        or intent["transition"] != self.transition["identity"]):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Preparation intent changed")
                anchor, plan = intent["anchor"], intent["plan"]
                before = self.prepared_account(anchor, current, authority)
                if self.plan_for(self.snapshot, proof, before, anchor["grant"], admission_report=report) != plan:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Preparation intent changed its native plan")
            else:
                if any((self.output / name).exists() for name in ("prepared-authority.json", "allocation-ledger.json")):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Prepared authority lost its publication intent")
                anchor = {"account_hash": digest(current), "events": len(current["events"]),
                          "plans": len(current["plans"]), "reservation_ceiling": current["reservation_ceiling"],
                          "gross_reservation_ceiling": current["gross_reservation_ceiling"],
                          "grant": {"identity": authority["identity"], "available": authority["available"]}}
                plan = self.plan_for(self.snapshot, proof, current, authority, admission_report=report)
                intent = {"transition": self.transition["identity"], "anchor": anchor, "plan": plan}
                immutable(intent_path, {**intent, "identity": digest(intent)})
            self.require_capacity(plan, current, authority)
            for name, value in (("transition.json", self.transition), ("admission-probe.json", report),
                    ("prepared-snapshot.json", bridge.original.lifecycle.retained.tree_hashes(self.snapshot)),
                    ("prepared-authority.json", anchor), ("plan.json", plan)):
                immutable(self.output / name, value)
            self.prepared_execution(plan)
            return self.validate(source_checked=True)

    def validate(self, *, source_checked=False):
        if not source_checked:
            self.source_gate()
        plan = runtime.validate_plan(read_json(regular_path(self.output / "plan.json")))
        report = self.probe(source_checked=True)
        if (read_json(regular_path(self.output / "transition.json")) != self.transition
                or read_json(regular_path(self.output / "admission-probe.json")) != report):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor changed its source transition or probe")
        anchor = read_json(regular_path(self.output / "prepared-authority.json"))
        current, authority = self.current_authority()
        before = self.prepared_account(anchor, current, authority)
        if self.plan_for(self.snapshot, self.probed_proof(report), before, anchor["grant"], admission_report=report) != plan:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor plan changed its exact native bindings")
        intent = {"transition": self.transition["identity"], "anchor": anchor, "plan": plan}
        if read_json(regular_path(self.output / "preparation-intent.json")) != {**intent, "identity": digest(intent)}:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Prepared successor lost its publication intent")
        self.require_capacity(plan, current, authority)
        if (not (self.output / "allocation-ledger.json").exists()
                and read_json(regular_path(self.output / "prepared-snapshot.json"))
                != bridge.original.lifecycle.retained.tree_hashes(self.snapshot)):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor snapshot changed before allocation")
        return plan

    def prepared_execution(self, plan):
        path = regular_path(self.output / "execution.json")
        if path.exists():
            retained = read_json(path)
            if retained.get("plan_identity") != plan["plan_identity"]:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Prepared terminal changed its plan")
            return
        if (self.output / "allocation-ledger.json").exists():
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Allocated successor lost its terminal state")
        immutable(path, {"status": "prepared", "plan_identity": plan["plan_identity"],
                        "model_calls": 0, "required": len(plan["calls"]), "human_evidence": False})

    def verify_membership(self, output, plan):
        with runtime.runtime(plan, output):
            return self.implementation.verify_membership(output, plan)

    def run(self, action):
        if action not in {"prepare", "probe", "validate"}:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Budget successor requires separate campaign admission")
        from tools.inventory_history_adoption import no_inference
        from tools.inventory_recovery_v3.accounting import history_scope

        with no_inference(), semantics.transition_runtime(self.transition), history_scope():
            return getattr(self, action)()
