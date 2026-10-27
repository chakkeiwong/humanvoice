"""Revalidate retained native canaries immediately before paired retry dispatch."""

from datetime import datetime
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.canary import validate_canary
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.migration import bound_record, child, verify_journal


class NativeCanaryCheck:
    def __init__(self, output, plan_identity, index, *, clock):
        if type(index) is not int or index < 0 or not callable(clock):
            raise ValueError("Native canary requires an allocated index and a clock")
        self.output = Path(output)
        self.plan_identity = plan_identity
        self.index = index
        self.clock = clock

    def __call__(self, sequence, reservations):
        from tools.inventory_recovery_v3.native_dispatch import modules

        output = self.output
        plan = bound_record(output / "plan.json", "plan_identity")
        execution, runtime = modules(plan)
        terminal_path = output / "execution.json"
        terminal = read_json(terminal_path) if terminal_path.exists() else {}
        scope = {"output": str(output.absolute()), "plan_identity": plan["plan_identity"],
                 "native_policy_identity": digest(plan["recovery"]),
                 "policy_identity": reservations["policy"]["identity"], **reservations["binding"]}
        if (sequence.get("native_stage") != scope
                or (output / "allocation-seal.json").exists()
                or terminal.get("status") not in {None, "prepared", "executing"}
                or terminal and terminal.get("plan_identity") != plan["plan_identity"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native canary requires its unsealed bound execution scope")
        ledger = read_json(output / "allocation-ledger.json")
        journal, result, receipt, entry = verify_journal(output, self.index)
        descriptor = read_json(output / f"reconnect-attempts/{self.index:04d}.json")
        with runtime.runtime(plan, output):
            state = execution.layout(output, plan, ledger["calls"])
        incident = state.get("incident")
        if (plan["plan_identity"] != self.plan_identity
                or ledger["plan_identity"] != self.plan_identity
                or not ledger["calls"] or ledger["calls"][-1] != entry
                or state.get("pending") is not None or state["mode"] != "request"
                or not incident or digest(incident) != sequence["incident"]
                or incident["request_hash"] != sequence["request_hash"]
                or descriptor.get("kind") != "canary"
                or descriptor.get("incident_hash") != sequence["incident"]
                or journal["request"] != execution.CANARY or result["status"] != "complete"
                or digest(plan["profile"]) != sequence["profile_hash"]
                or plan["bindings"]["source"] != reservations["binding"]["document"]
                or entry["invocation_id"] != sequence["slots"]["canary"]["invocation"]
                or receipt.get("termination") != "complete"
                or journal["runtime_record"]["hash"] !=
                   sequence["slots"]["canary"]["proof"]["receipt_hash"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native canary no longer owns the unfinished request")
        folder = child(plan["snapshot"], journal["runtime_record"]["path"]).parent
        process = read_json(folder / "process.json")
        checked = runtime.implementation.capture.validate_record(
            Path(plan["snapshot"]), journal["runtime_record"])
        if checked != receipt or process.get("group_quiescent") is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Canary process is not verifiably quiescent")
        wait = read_json(output / "reconnect-waits" / (sequence["incident"] + ".json"))
        completed = datetime.fromisoformat(receipt["created_at"])
        if completed.tzinfo is None:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Canary receipt lacks an absolute clock")
        binding = {name: sequence[name] for name in
                   ("incident", "request_hash", "lineage", "profile_hash")}
        binding.update(route_hash=digest(plan["profile"]["runtime"]),
                       source_hash=plan["bindings"]["source"],
                       policy_identity=reservations["policy"]["identity"],
                       reservation_identity=sequence["identity"])
        proof = {**binding, "settled": True, "quiescent": True, "canary_valid": True,
                 "later_failure": False, "retry_allocated": False,
                 "receipt_hash": journal["runtime_record"]["hash"],
                 "failed_at": wait["failed_at"], "wait_observed_at": wait["observed_at"],
                 "completed_at": completed.timestamp()}
        return validate_canary(proof, binding, now=self.clock(), maximum_age=900,
                               verify=lambda retained: retained)
