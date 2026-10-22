"""Preserve the settled inventory prefix and replace only the rejected source window."""

import fcntl
from contextlib import contextmanager
from pathlib import Path

from humanvoice.artifacts import digest, implementation_hash, read_json, validate_snapshot
from humanvoice.automatic_settlement import completed_usage
from humanvoice.codex_runtime import validate_codex_record
from humanvoice.inference_settings import selected_profile
from humanvoice.model import ModelAdapter
from humanvoice.response_schemas import parse_response
from tools import inventory_context as context
from tools import inventory_coverage_continuation as previous
from tools.automatic_program_account import ACCOUNT

ROOT, BASE, inventory, retained = previous.ROOT, previous.BASE, previous.inventory, previous.retained
manuscript, punctuation = previous.manuscript, previous.punctuation
PRIOR = previous.STAGE
EVIDENCE = BASE / "inventory-context-repair-20261022"
STAGE = BASE / "zlb-inventory-context-20261022-01"
SNAPSHOT = BASE / "zlb-inventory-context-20261022-01-snapshot"
PROBE = EVIDENCE / "probe"
VERSION = "inventory-context-continuation-v1"
STARTS = {"zlb_source.tex": 10}
FILES = ("tools/inventory_context_continuation.py", *context.FILES)
grant_status, grant_stage = previous.grant_status, previous.grant_stage
replay = previous.replay
NATIVE_PREDECESSOR = previous.predecessor_evidence
NATIVE_COPY = previous.copy_snapshot
NATIVE_PLAN = previous.plan_for


def predecessor_evidence(*, account=ACCOUNT):
    original = NATIVE_PREDECESSOR(account=account)
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
                or terminal.get("exit_code") != 3 or terminal.get("logical_calls") != 9
                or terminal.get("attempted") != 10 or terminal.get("recoveries") != 1
                or read_json(PRIOR / "executor.json") != {"status": "stopped"}
                or log["inherited"] != original["prefix"] or log["new_requests"] != 9
                or not log["reached_unrun_request"] or (snapshot / ".humanvoice/inventory/baseline.json").exists()
                or read_json(snapshot / punctuation.MARKER) != punctuation.policy(snapshot)):
            raise ValueError("Context repair requires the exact stopped and unchanged inventory")
        usage = completed_usage(PRIOR)
        settlements = [event["usage"] for event in read_json(account)["events"]
                       if event["kind"] == "settle" and event["usage"]["plan_identity"] == plan["plan_identity"]]
        if settlements != [usage] or usage["allocated_calls"] != 10 or usage["unknown_calls"] != 1:
            raise ValueError("Context predecessor lost its complete settlement including the network failure")
        entries = read_json(PRIOR / "allocation-ledger.json")["calls"]
        layout = inventory.network.attempt_layout(PRIOR, plan, entries)
        if sorted(layout["selected"]) != list(range(9)) or layout["recoveries"] != 1 or len(layout["failures"]) != 1:
            raise ValueError("Context predecessor lost its ordered responses or charged network recovery")
        added = []
        for logical, attempt in sorted(layout["selected"].items()):
            path = PRIOR / f"calls/{attempt:04d}/call.json"
            journal = read_json(path)
            receipt = validate_codex_record(snapshot, journal["runtime_record"])
            payload = parse_response(journal["response_text"], journal["request"]["response_schema"])
            purpose = ("concept_extraction", "reconstruction_verification", "coverage_verification")[logical % 3]
            expected = {"reconstruction_verification": "supported", "coverage_verification": "covered"}.get(purpose)
            if (journal["status"] != "complete" or receipt["termination"] != "complete" or not payload
                    or journal["request"]["purpose"] != purpose
                    or logical != 8 and expected and any(row["verdict"] != expected for row in payload)):
                raise ValueError("Context predecessor has an unexpected incomplete or rejected request")
            if logical == 8:
                rejected = {row["span_id"] for row in payload if row["verdict"] == "unresolved"}
                if rejected != {"span-170be5d8eff5e252", "span-6b1ab08b9a6f2aa2"} or any(
                        row["verdict"] not in {"covered", "unresolved"} for row in payload):
                    raise ValueError("Context repair does not match the retained missing-context failure")
            added.append({"output": str(PRIOR), "attempt": attempt, "logical": 18 + logical,
                "request_hash": journal["request_hash"], "runtime_record": journal["runtime_record"],
                "call_sha256": digest(path.read_bytes())})
        all_calls = original["prefix"] + added
        if len({row["request_hash"] for row in all_calls}) != 27 or len({row["runtime_record"]["hash"] for row in all_calls}) != 27:
            raise ValueError("Context lineage duplicates completed requests or receipts")
        return {"version": VERSION, "predecessor": str(PRIOR), "plan_identity": plan["plan_identity"],
            "prefix": all_calls[:24], "superseded_window_calls": all_calls[24:], "transport_failures": layout["failures"],
            "maximum_logical_calls": 540, "remaining_base_calls": 516,
            "remaining_calls": 516 + 3 * context.MAX_REPAIRS, "usage": usage,
            "snapshot_hashes": retained.tree_hashes(snapshot), "first_windows": STARTS,
            "terminal_sha256": digest((PRIOR / "execution.json").read_bytes()),
            "ledger_sha256": digest((PRIOR / "allocation-ledger.json").read_bytes()),
            "replay_log_sha256": digest((PRIOR / "replay-log.json").read_bytes())}


def copy_snapshot(snapshot, proof):
    NATIVE_COPY(snapshot, proof)
    context.enable(snapshot, proof["first_windows"])


def probe(*, grant, account=ACCOUNT):
    proof = predecessor_evidence(account=account)
    before = Path(account).read_bytes(), Path(grant).read_bytes(), retained.tree_hashes(PRIOR)
    snapshot = PROBE / "snapshot"
    copy_snapshot(snapshot, proof)
    plan = {**read_json(PRIOR / "plan.json"), "snapshot": str(snapshot)}
    captured, native = [], ModelAdapter.invoke

    def boundary(model, *arguments, **keywords):
        captured.append(retained.canonical_request(model, arguments, keywords))
        raise retained.ReplayBoundary()

    ModelAdapter.invoke = boundary
    try:
        with context.runtime():
            try:
                with replay(PROBE, plan, proof, first_request=None):
                    manuscript.run_manuscript_consumer(PROBE, snapshot, "inventory")
            except retained.ReplayBoundary:
                pass
        log = read_json(PROBE / "replay-log.json")
        failed = retained.retained_journal(proof["superseded_window_calls"][0])
        if (len(captured) != 1 or captured[0]["purpose"] != "concept_extraction"
                or captured[0] == failed["request"] or log["inherited"] != proof["prefix"] or log["new_requests"] != 1
                or not all(identifier in captured[0]["prompt"] for identifier in
                           ("span-1e61f81460033391", "span-170be5d8eff5e252", "span-6b1ab08b9a6f2aa2", "span-46958969962c3bcf"))):
            raise ValueError("Context probe did not reach the repaired window after exactly 24 retained requests")
        if before != (Path(account).read_bytes(), Path(grant).read_bytes(), retained.tree_hashes(PRIOR)):
            raise ValueError("Context probe changed authority or predecessor evidence")
        if retained.tree_hashes(Path(read_json(PRIOR / "plan.json")["snapshot"])) != proof["snapshot_hashes"]:
            raise ValueError("Context probe changed the predecessor snapshot")
        result = {"version": VERSION, "status": "pass", "model_calls": 0, "inherited_calls": 24,
            "superseded_calls_retained": 3, "predecessor_identity": digest(proof), "first_request": captured[0],
            "replay_sha256": digest((PROBE / "replay-log.json").read_bytes()),
            "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
            "policy": context.policy(snapshot, STARTS), "authority_unchanged": True, "predecessor_unchanged": True}
        retained.immutable(PROBE / "verification.json", result)
        return result
    finally:
        ModelAdapter.invoke = native


def plan_for(snapshot, prior, proof, grant, *, allowance, probe_report):
    plan = NATIVE_PLAN(snapshot, prior, proof, grant, allowance=allowance, probe_report=probe_report)
    plan["inventory_context_repair"] = {"version": VERSION, "policy": context.policy(snapshot, STARTS),
        "files": {name: digest((ROOT / name).read_bytes()) for name in FILES}, "remaining_base_calls": 516,
        "maximum_repair_calls": 3 * context.MAX_REPAIRS, "superseded_calls_retained": 3}
    plan.pop("plan_identity")
    plan["plan_identity"] = digest(plan)
    return plan


@contextmanager
def bindings():
    values = {"STAGE": STAGE, "SNAPSHOT": SNAPSHOT, "PROBE": PROBE, "predecessor_evidence": predecessor_evidence,
              "plan_for": plan_for, "copy_snapshot": copy_snapshot}
    originals = {name: getattr(previous, name) for name in values}
    try:
        for name, value in values.items():
            setattr(previous, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(previous, name, value)


def prepare(*, grant, account=ACCOUNT):
    with bindings():
        return previous.prepare(grant=grant, account=account)


def execute(*, grant, account=ACCOUNT):
    with context.runtime(), bindings():
        return previous.execute(grant=grant, account=account)


def verify_completed(*, account=ACCOUNT):
    from humanvoice.automatic_evaluation import evidence_path
    from humanvoice.commands.plan_v2_command import validate_inventory
    from humanvoice.concept_baseline import load_baseline

    plan = inventory.validate_extension(read_json(STAGE / "plan.json"))
    proof, usage = predecessor_evidence(account=account), completed_usage(STAGE)
    log, result = read_json(STAGE / "replay-log.json"), read_json(SNAPSHOT / ".humanvoice/inventory/inventory_result.json")
    layout = inventory.network.attempt_layout(STAGE, plan, read_json(STAGE / "allocation-ledger.json")["calls"])
    count = len(layout["selected"])
    if (read_json(STAGE / "execution.json")["status"] != "pass" or proof != plan["inventory_coverage_repair"]["evidence"]
            or log["inherited"] != proof["prefix"] or log["new_requests"] != count
            or not 516 <= count <= 516 + 3 * context.MAX_REPAIRS or (count - 516) % 3
            or not any(event["kind"] == "settle" and event["usage"] == usage for event in read_json(account)["events"])):
        raise ValueError("Context inventory lost exact prefix, bounded repairs or settlement")
    journals = [retained.retained_journal(row) for row in proof["prefix"]]
    journals.extend(read_json(STAGE / f"calls/{index:04d}/call.json") for index in layout["selected"].values())
    receipts = set()
    for reference, journal in zip(result["model_calls"], journals, strict=True):
        observed = read_json(evidence_path(SNAPSHOT / ".humanvoice/inventory", reference["path"]))
        if (digest(observed) != reference["hash"] or observed.get("runtime_record") != journal["runtime_record"]
                or observed.get("response_text") != journal["response_text"]
                or retained.canonical_request(None, (), observed["request"]) != journal["request"]
                or journal["runtime_record"]["hash"] in receipts):
            raise ValueError("Context inventory lost exact accepted and rejected attempt journals")
        receipts.add(journal["runtime_record"]["hash"])
    with context.runtime(), inventory.scope.verification_only():
        validate_inventory(SNAPSHOT, load_baseline(SNAPSHOT / ".humanvoice/inventory/baseline.json"))
    report = {"status": "pass", "version": VERSION, "inherited_calls": 24, "superseded_calls_retained": 3,
              "repair_calls": count - 516, "model_calls": 0, "new_calls": usage["allocated_calls"]}
    retained.immutable(STAGE / "coverage-verification.json", report)
    return report
