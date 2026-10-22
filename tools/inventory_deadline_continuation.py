"""Resume the settled inventory deadline without repurchasing accepted responses."""

import fcntl
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from humanvoice.artifacts import digest, implementation_hash, read_json, validate_snapshot
from humanvoice.automatic_evaluation import evidence_path
from humanvoice.automatic_settlement import completed_usage
from humanvoice.codex_runtime import validate_codex_record
from humanvoice.inference_settings import selected_profile
from humanvoice.model import ModelAdapter
from humanvoice.response_schemas import parse_response
from tools import inventory_context_continuation as previous
from tools import inventory_deadline_runtime as deadline

ROOT, BASE, inventory, retained = previous.ROOT, previous.BASE, previous.inventory, previous.retained
context, coverage, manuscript = previous.context, previous.previous, previous.manuscript
ACCOUNT, grant_status, grant_stage = previous.ACCOUNT, previous.grant_status, previous.grant_stage
PRIOR = previous.STAGE
EVIDENCE = BASE / "inventory-deadline-repair-20261022"
STAGE = BASE / "zlb-inventory-deadline-20261022-01"
SNAPSHOT = BASE / "zlb-inventory-deadline-20261022-01-snapshot"
PROBE = EVIDENCE / "probe-02"
VERSION = "inventory-deadline-continuation-v1"
FILES = ("tools/inventory_deadline_continuation.py", "tools/inventory_deadline_runtime.py")
NATIVE_PLAN = coverage.plan_for


def predecessor_evidence(*, account=ACCOUNT):
    original = previous.predecessor_evidence(account=account)
    with (PRIOR / "execution.lock").open("a") as execution, (PRIOR / "executor.lock").open("a") as executor:
        for handle in (execution, executor):
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = inventory.validate_extension(read_json(PRIOR / "plan.json"))
        terminal, snapshot = read_json(PRIOR / "execution.json"), Path(plan["snapshot"])
        log = read_json(PRIOR / "replay-log.json")
        if (plan["inventory_coverage_repair"]["evidence"] != original
                or plan["bindings"]["implementation"] != implementation_hash()
                or plan["bindings"]["manifest"] != digest(validate_snapshot(snapshot))
                or plan["profile"] != selected_profile() or terminal["status"] != "nonpass"
                or terminal.get("error") != "InvocationStopped: Inventory provider invocation stopped: Codex process exceeded its deadline"
                or terminal.get("attempted") != 4 or terminal.get("inherited_calls") != 24
                or read_json(PRIOR / "executor.json") != {"status": "stopped"}
                or log["inherited"] != original["prefix"] or log["new_requests"] != 4
                or not log["reached_unrun_request"] or (snapshot / ".humanvoice/inventory/baseline.json").exists()
                or context.selected_policy(snapshot) != plan["inventory_context_repair"]["policy"]):
            raise ValueError("Deadline continuation requires the exact unchanged stopped inventory")
        usage = completed_usage(PRIOR)
        settlements = [event["usage"] for event in read_json(account)["events"]
                       if event["kind"] == "settle" and event["usage"]["plan_identity"] == plan["plan_identity"]]
        entries = read_json(PRIOR / "allocation-ledger.json")["calls"]
        if (settlements != [usage] or usage["allocated_calls"] != 4 or usage["unknown_calls"] != 1
                or len(entries) != 4 or [entry["status"] for entry in entries] != ["complete"] * 3 + ["incomplete"]):
            raise ValueError("Deadline predecessor lost a completed response or unknown charge")
        added = []
        for index in range(3):
            path = PRIOR / f"calls/{index:04d}/call.json"
            journal = read_json(path)
            record = validate_codex_record(snapshot, journal["runtime_record"])
            payload = parse_response(journal["response_text"], journal["request"]["response_schema"])
            purpose = ("concept_extraction", "reconstruction_verification", "coverage_verification")[index]
            verdict = {1: "supported", 2: "covered"}.get(index)
            if (record["termination"] != "complete" or journal["status"] != "complete" or not payload
                    or journal["request"]["purpose"] != purpose
                    or verdict and any(row["verdict"] != verdict for row in payload)):
                raise ValueError("Deadline continuation cannot reuse a rejected window")
            added.append({"output": str(PRIOR), "attempt": index, "logical": 24 + index,
                "request_hash": journal["request_hash"], "runtime_record": journal["runtime_record"],
                "call_sha256": digest(path.read_bytes())})
        directory = PRIOR / "calls/0003"
        failure = deadline.classify(PRIOR, directory, deadline.NATIVE[0](PRIOR, directory, plan, entries[-1]))
        journal = read_json(directory / "call.json")
        record = validate_codex_record(snapshot, journal["runtime_record"])
        if not failure["eligible"] or failure["reason"] != "response_free_process_deadline":
            raise ValueError("Deadline continuation lacks exact response-free evidence")
        prefix = original["prefix"] + added
        if len({row["request_hash"] for row in prefix}) != 27 or len({row["runtime_record"]["hash"] for row in prefix}) != 27:
            raise ValueError("Deadline continuation duplicates accepted requests")
        return {"version": VERSION, "predecessor": str(PRIOR), "plan_identity": plan["plan_identity"],
            "prefix": prefix, "superseded_window_calls": original["superseded_window_calls"],
            "maximum_logical_calls": 540, "remaining_base_calls": 513, "remaining_calls": 537,
            "snapshot_hashes": retained.tree_hashes(snapshot), "usage": usage,
            "deadline_failure": failure, "failed_request": journal["request"],
            "failed_at": datetime.fromisoformat(record["created_at"]).timestamp(),
            "failure_hash": digest(journal), "terminal_sha256": digest((PRIOR / "execution.json").read_bytes()),
            "ledger_sha256": digest((PRIOR / "allocation-ledger.json").read_bytes()),
            "replay_log_sha256": digest((PRIOR / "replay-log.json").read_bytes())}


def probe(*, grant, account=ACCOUNT):
    proof = predecessor_evidence(account=account)
    before = Path(account).read_bytes(), Path(grant).read_bytes(), retained.tree_hashes(PRIOR)
    snapshot = PROBE / "snapshot"
    coverage.copy_snapshot(snapshot, proof)
    plan = {**read_json(PRIOR / "plan.json"), "snapshot": str(snapshot)}
    captured, native = [], ModelAdapter.invoke

    def boundary(model, *arguments, **keywords):
        captured.append(retained.canonical_request(model, arguments, keywords))
        raise retained.ReplayBoundary()

    ModelAdapter.invoke = boundary
    try:
        with context.runtime():
            try:
                with coverage.replay(PROBE, plan, proof, first_request=proof["failed_request"]):
                    manuscript.run_manuscript_consumer(PROBE, snapshot, "inventory")
            except retained.ReplayBoundary:
                pass
        log = read_json(PROBE / "replay-log.json")
        if (captured != [proof["failed_request"]] or log["inherited"] != proof["prefix"] or log["new_requests"] != 1
                or not log["reached_unrun_request"]):
            raise ValueError("Deadline probe did not replay exactly 27 requests to the identical interrupted request")
        if before != (Path(account).read_bytes(), Path(grant).read_bytes(), retained.tree_hashes(PRIOR)):
            raise ValueError("Deadline probe modified authority or predecessor")
        if retained.tree_hashes(Path(read_json(PRIOR / "plan.json")["snapshot"])) != proof["snapshot_hashes"]:
            raise ValueError("Deadline probe changed the predecessor snapshot")
        report = {"version": VERSION, "status": "pass", "model_calls": 0, "inherited_calls": 27,
            "predecessor_identity": digest(proof), "first_request": captured[0], "policy": deadline.policy(),
            "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
            "replay_sha256": digest((PROBE / "replay-log.json").read_bytes()),
            "authority_unchanged": True, "predecessor_unchanged": True}
        retained.immutable(PROBE / "verification.json", report)
        return report
    finally:
        ModelAdapter.invoke = native


def plan_for(snapshot, prior, proof, grant, *, allowance, probe_report):
    plan = NATIVE_PLAN(snapshot, prior, proof, grant, allowance=allowance, probe_report=probe_report)
    plan[deadline.FIELD] = deadline.policy()
    plan["inventory_deadline_repair"] = {"version": VERSION, "files": {
        name: digest((ROOT / name).read_bytes()) for name in FILES}, "remaining_base_calls": 513,
        "maximum_repair_calls": 24, "context_policy": context.selected_policy(snapshot)}
    plan.pop("plan_identity")
    plan["plan_identity"] = digest(plan)
    return plan


@contextmanager
def bindings():
    values = {"STAGE": STAGE, "SNAPSHOT": SNAPSHOT, "PROBE": PROBE,
              "predecessor_evidence": predecessor_evidence, "plan_for": plan_for}
    originals = {name: getattr(coverage, name) for name in values}
    try:
        for name, value in values.items():
            setattr(coverage, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(coverage, name, value)


def prepare(*, grant, account=ACCOUNT):
    with bindings():
        return coverage.prepare(grant=grant, account=account)


def execute(*, grant, account=ACCOUNT):
    proof = predecessor_evidence(account=account)
    deadline.network.wait_until(STAGE / "initial-retry-wait.json", proof["failure_hash"], proof["failed_at"])
    with context.runtime(), deadline.runtime(), bindings():
        return coverage.execute(grant=grant, account=account)


def verify_completed(*, account=ACCOUNT):
    from humanvoice.commands.plan_v2_command import validate_inventory
    from humanvoice.concept_baseline import load_baseline

    plan = inventory.validate_extension(read_json(STAGE / "plan.json"))
    proof, usage = predecessor_evidence(account=account), completed_usage(STAGE)
    log, result = read_json(STAGE / "replay-log.json"), read_json(SNAPSHOT / ".humanvoice/inventory/inventory_result.json")
    with deadline.runtime():
        layout = inventory.network.attempt_layout(STAGE, plan, read_json(STAGE / "allocation-ledger.json")["calls"])
    count = len(layout["selected"])
    if (read_json(STAGE / "execution.json")["status"] != "pass" or proof != plan["inventory_coverage_repair"]["evidence"]
            or log["inherited"] != proof["prefix"] or log["new_requests"] != count
            or not 513 <= count <= 537 or (count - 513) % 3
            or not any(event["kind"] == "settle" and event["usage"] == usage for event in read_json(account)["events"])):
        raise ValueError("Deadline inventory lost its prefix, bounded repairs or settlement")
    journals = [retained.retained_journal(row) for row in proof["prefix"]]
    journals.extend(read_json(STAGE / f"calls/{index:04d}/call.json") for index in layout["selected"].values())
    receipts = set()
    for reference, journal in zip(result["model_calls"], journals, strict=True):
        observed = read_json(evidence_path(SNAPSHOT / ".humanvoice/inventory", reference["path"]))
        if (digest(observed) != reference["hash"] or observed.get("runtime_record") != journal["runtime_record"]
                or observed.get("response_text") != journal["response_text"]
                or retained.canonical_request(None, (), observed["request"]) != journal["request"]
                or journal["runtime_record"]["hash"] in receipts):
            raise ValueError("Deadline inventory lost exact response membership")
        receipts.add(journal["runtime_record"]["hash"])
    with context.runtime(), inventory.scope.verification_only():
        validate_inventory(SNAPSHOT, load_baseline(SNAPSHOT / ".humanvoice/inventory/baseline.json"))
    report = {"status": "pass", "version": VERSION, "inherited_calls": 27, "repair_calls": count - 513,
              "superseded_calls_retained": 3, "model_calls": 0, "new_calls": usage["allocated_calls"]}
    retained.immutable(STAGE / "coverage-verification.json", report)
    return report
