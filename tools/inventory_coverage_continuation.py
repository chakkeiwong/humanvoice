"""Continue a settled positive inventory prefix after a proven coverage repair."""

import fcntl
import shutil
from contextlib import contextmanager
from pathlib import Path

from humanvoice.artifacts import digest, implementation_hash, read_json, validate_snapshot, write_json
from humanvoice.automatic_evaluation import evidence_path
from humanvoice.automatic_settlement import completed_usage
from humanvoice.codex_runtime import validate_codex_record
from humanvoice.inference_settings import selected_profile
from humanvoice.model import ModelAdapter, ModelResponse
from humanvoice.response_schemas import parse_response
from tools import inventory_punctuation as punctuation
from tools import inventory_stage_runtime as inventory
from tools import inventory_transport_continuation as retained
from tools import zlb_ssd_workspace as workspace
from tools.automatic_call_grant import stage as grant_stage, status as grant_status
from tools.automatic_program_account import ACCOUNT, claim, settle, validate_account
from tools.ensemble_closure_contract import AllocationLedger

ROOT, BASE, PRIOR = workspace.ROOT, workspace.BASE, workspace.STAGE
EVIDENCE = BASE / "inventory-coverage-repair-20261022-final"
STAGE = BASE / "zlb-inventory-coverage-20261022-02"
SNAPSHOT = BASE / "zlb-inventory-coverage-20261022-02-snapshot"
PROBE = EVIDENCE / "probe"
VERSION = "inventory-positive-coverage-continuation-v1"
FILES = ("tools/inventory_coverage_continuation.py", *punctuation.FILES)
manuscript = retained.manuscript


def predecessor_evidence(output=PRIOR, *, account=ACCOUNT):
    output = Path(output).resolve()
    with (output / "execution.lock").open("a") as execution, (output / "executor.lock").open("a") as executor:
        for handle in (execution, executor):
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = inventory.validate_extension(read_json(output / "plan.json"))
        terminal = read_json(output / "execution.json")
        snapshot = Path(plan["snapshot"])
        result = read_json(snapshot / ".humanvoice/inventory/inventory_result.json")
        progress = result["window_progress"]
        if (terminal["status"] != "nonpass" or terminal.get("exit_code") != 1 or terminal.get("attempted") != 18
                or read_json(output / "executor.json")["status"] != "stopped"
                or plan["bindings"]["implementation"] != implementation_hash()
                or plan["bindings"]["instrumentation"] != digest(Path(manuscript.__file__).read_bytes())
                or plan["bindings"]["manifest"] != digest(validate_snapshot(snapshot))
                or plan["profile"] != selected_profile() or len(plan["calls"]) != 540
                or (snapshot / ".humanvoice/inventory/baseline.json").exists()
                or (snapshot / punctuation.MARKER).exists() or result["status"] != "blocked"
                or result["errors"][0] != "zlb_source.tex/7: incomplete or unresolved coverage"
                or any(not error.startswith("Uncovered prose: ") for error in result["errors"][1:])
                or progress["completed"] != [f"zlb_source.tex/{index}" for index in range(2, 8)]
                or len(progress["required"]) != 180 or len(result["model_calls"]) != 18):
            raise ValueError("Coverage continuation requires the exact stopped punctuation failure")
        usage = completed_usage(output)
        settlements = [event["usage"] for event in read_json(account)["events"]
                       if event["kind"] == "settle" and event["usage"]["plan_identity"] == plan["plan_identity"]]
        if settlements != [usage] or usage["allocated_calls"] != 18 or usage["unknown_calls"] != 0:
            raise ValueError("Coverage predecessor lacks its unique complete settlement")
        entries = read_json(output / "allocation-ledger.json")["calls"]
        if len(entries) != 18 or any(entry["status"] != "complete" for entry in entries):
            raise ValueError("Coverage repair cannot reinterpret transport or partial responses")
        prefix, requests, receipts = [], set(), set()
        for index, entry in enumerate(entries):
            path = output / f"calls/{index:04d}/call.json"
            journal = read_json(path)
            receipt = validate_codex_record(snapshot, journal["runtime_record"])
            payload = parse_response(journal["response_text"], journal["request"]["response_schema"])
            purpose = ("concept_extraction", "reconstruction_verification", "coverage_verification")[index % 3]
            expected = {"reconstruction_verification": "supported", "coverage_verification": "covered"}.get(purpose)
            if (journal["status"] != "complete" or receipt["termination"] != "complete"
                    or journal["request"]["purpose"] != purpose or not payload
                    or expected and any(row["verdict"] != expected for row in payload)
                    or journal["request_hash"] in requests or journal["runtime_record"]["hash"] in receipts):
                raise ValueError("Coverage prefix must contain unique complete positive judgments")
            requests.add(journal["request_hash"])
            receipts.add(journal["runtime_record"]["hash"])
            prefix.append({"output": str(output), "attempt": index, "logical": index,
                "request_hash": journal["request_hash"], "runtime_record": journal["runtime_record"],
                "call_sha256": digest(path.read_bytes())})
        return {"version": VERSION, "predecessor": str(output), "plan_identity": plan["plan_identity"],
                "prefix": prefix, "maximum_logical_calls": len(plan["calls"]), "remaining_calls": 522,
                "snapshot_hashes": retained.tree_hashes(snapshot), "usage": usage,
                "terminal_sha256": digest((output / "execution.json").read_bytes()),
                "inventory_sha256": digest(result), "ledger_sha256": digest((output / "allocation-ledger.json").read_bytes())}


def copy_snapshot(snapshot, proof):
    parent = read_json(Path(proof["predecessor"]) / "plan.json")
    shutil.copytree(parent["snapshot"], snapshot)
    if retained.tree_hashes(snapshot) != proof["snapshot_hashes"]:
        raise ValueError("Coverage continuation changed inherited snapshot evidence")
    punctuation.enable(snapshot)


def probe(output=PROBE, *, account=ACCOUNT, grant):
    output = Path(output).resolve()
    proof = predecessor_evidence(account=account)
    before = Path(account).read_bytes(), Path(grant).read_bytes(), retained.tree_hashes(PRIOR)
    snapshot = output / "snapshot"
    copy_snapshot(snapshot, proof)
    parent = read_json(PRIOR / "plan.json")
    captured = []
    native = ModelAdapter.invoke

    def boundary(model, *arguments, **keywords):
        captured.append(retained.canonical_request(model, arguments, keywords))
        raise retained.ReplayBoundary()

    plan = {**parent, "snapshot": str(snapshot)}
    ModelAdapter.invoke = boundary
    try:
        with punctuation.runtime() as derivations:
            try:
                with replay(output, plan, proof, first_request=None):
                    manuscript.run_manuscript_consumer(output, snapshot, "inventory")
            except retained.ReplayBoundary:
                pass
        log = read_json(output / "replay-log.json")
        if (len(captured) != 1 or captured[0]["purpose"] != "concept_extraction"
                or len(derivations) != 1 or derivations[0]["span_id"] != "span-62039de336488637"
                or derivations[0]["mapped_concept_ids"] != ["concept-006"]
                or log["inherited"] != proof["prefix"] or log["new_requests"] != 1):
            raise ValueError("Coverage probe did not replay all responses and repair only the retained colon")
        if before != (Path(account).read_bytes(), Path(grant).read_bytes(), retained.tree_hashes(PRIOR)):
            raise ValueError("Coverage probe modified authority or predecessor evidence")
        if retained.tree_hashes(Path(parent["snapshot"])) != proof["snapshot_hashes"]:
            raise ValueError("Coverage probe changed the predecessor snapshot")
        result = {"version": VERSION, "status": "pass", "model_calls": 0,
                  "predecessor_identity": digest(proof), "inherited_calls": len(proof["prefix"]),
                  "first_request": captured[0], "derivations": derivations,
                  "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
                  "replay_sha256": digest((output / "replay-log.json").read_bytes()),
                  "authority_unchanged": True, "predecessor_unchanged": True,
                  "policy": punctuation.policy(snapshot)}
        retained.immutable(output / "verification.json", result)
        return result
    finally:
        ModelAdapter.invoke = native


@contextmanager
def replay(output, plan, proof, *, first_request):
    native = ModelAdapter.invoke
    position, seen, inherited = 0, set(), []
    snapshot = Path(plan["snapshot"])

    def invoke(model, *arguments, **keywords):
        nonlocal position
        request = retained.canonical_request(model, arguments, keywords)
        if (model.mock_mode or Path(model.snapshot_dir).resolve() != snapshot
                or selected_profile() != plan["profile"] or implementation_hash() != plan["bindings"]["implementation"]
                or digest(validate_snapshot(snapshot)) != plan["bindings"]["manifest"] or digest(request) in seen):
            raise ValueError("Coverage replay left its frozen scope or repeated a completed request")
        seen.add(digest(request))
        if position < len(proof["prefix"]):
            row = proof["prefix"][position]
            journal = retained.retained_journal(row)
            if request != journal["request"]:
                raise ValueError("Coverage consumer request differs from its exact retained prefix")
            receipt = validate_codex_record(snapshot, journal["runtime_record"])
            folder = evidence_path(snapshot, journal["runtime_record"]["path"]).parent
            response = read_json(folder / "response.json")
            if receipt["termination"] != "complete" or response["text"] != journal["response_text"]:
                raise ValueError("Inherited coverage response differs from its verified receipt")
            position += 1
            inherited.append(row)
            write_json(output / "replay-log.json", {"version": VERSION, "inherited": inherited,
                                                    "reached_unrun_request": False, "new_requests": 0})
            model.last_runtime_record = journal["runtime_record"]
            return ModelResponse(text=response["text"], prompt_hash=digest(request["prompt"]),
                model_version=model.config.model_version, temperature=model.config.temperature,
                input_tokens=journal["input_tokens"], output_tokens=journal["output_tokens"],
                runtime_record=journal["runtime_record"], request_id=receipt["request_id_if_available"],
                raw_transport=(folder / "response-envelope.json").read_text())
        if position == len(proof["prefix"]) and first_request is not None and request != first_request:
            raise ValueError("First unrun inventory request differs from the independent probe")
        position += 1
        write_json(output / "replay-log.json", {"version": VERSION, "inherited": inherited,
            "reached_unrun_request": True, "new_requests": position - len(proof["prefix"])})
        return native(model, *arguments, **keywords)

    ModelAdapter.invoke = invoke
    try:
        yield
        if position <= len(proof["prefix"]):
            raise ValueError("Coverage replay did not reach its first unrun request")
    finally:
        ModelAdapter.invoke = native


def plan_for(snapshot, prior, proof, grant, *, allowance, probe_report):
    plan = manuscript.plan_for(snapshot, "inventory", proof["remaining_calls"], prior, account_allowance=allowance)
    parent = read_json(Path(proof["predecessor"]) / "plan.json")
    if any(parent["bindings"][key] != plan["bindings"][key]
           for key in ("manifest", "source", "policy", "rights", "implementation", "stage", "profile")):
        raise ValueError("Coverage continuation changed the qualified manuscript scope")
    plan["inventory_coverage_repair"] = {"version": VERSION, "predecessor": proof["predecessor"],
        "evidence": proof, "probe_sha256": digest(probe_report), "first_request": probe_report["first_request"],
        "policy": punctuation.policy(snapshot), "grant_identity": grant["identity"],
        "files": {name: digest((ROOT / name).read_bytes()) for name in FILES}}
    plan.pop("plan_identity")
    plan["plan_identity"] = digest(plan)
    inventory.validate_extension(plan)
    return plan


def prepare(*, grant, account=ACCOUNT):
    proof = predecessor_evidence(account=account)
    report = read_json(PROBE / "verification.json")
    if (report["status"] != "pass" or report["model_calls"] != 0 or report["predecessor_identity"] != digest(proof)
            or report["replay_sha256"] != digest((PROBE / "replay-log.json").read_bytes())):
        raise ValueError("Coverage preparation requires the independent exact replay probe")
    authority, record = grant_status(grant), validate_account(read_json(account))
    if STAGE.exists() or SNAPSHOT.exists():
        raise ValueError("Coverage preparation needs fresh stage and snapshot paths")
    maximum = proof["remaining_calls"] + 16
    if maximum > authority["available"] or record["reservation_ceiling"] + maximum * 544000 > record["allowance"]:
        raise ValueError("Coverage continuation exceeds existing call or token authority")
    copy_snapshot(SNAPSHOT, proof)
    with inventory.pipeline(planning=[(SNAPSHOT, "inventory")]):
        plan = plan_for(SNAPSHOT, record["reservation_ceiling"], proof, authority,
                        allowance=record["allowance"], probe_report=report)
    retained.immutable(STAGE / "prepared-snapshot.json", retained.tree_hashes(SNAPSHOT))
    retained.immutable(STAGE / "plan.json", plan)
    return plan


def execute(*, grant, account=ACCOUNT):
    with (STAGE / "execution.lock").open("a") as execution, (STAGE / "executor.lock").open("a") as executor:
        for handle in (execution, executor):
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = read_json(STAGE / "plan.json")
        proof = predecessor_evidence(account=account)
        with inventory.pipeline(planning=[(SNAPSHOT, "inventory")]):
            expected = plan_for(SNAPSHOT, plan["prior_reservation_ceiling"], proof, grant_status(grant),
                allowance=plan["account_allowance"], probe_report=read_json(PROBE / "verification.json"))
        if plan != expected or retained.tree_hashes(SNAPSHOT) != read_json(STAGE / "prepared-snapshot.json"):
            raise ValueError("Coverage continuation inputs changed before execution")
        manuscript.require_qualified_stage(plan)
        with grant_stage(grant, STAGE):
            reservation = claim_lineage(plan, proof, account=account)
            ledger = AllocationLedger(STAGE / "allocation-ledger.json", plan)
            summary = {"status": "executing", "required": len(plan["calls"]), "attempted": 0,
                "plan_identity": plan["plan_identity"], "qualification": False, "human_evidence": False,
                "inherited_calls": len(proof["prefix"])}
            write_json(STAGE / "executor.json", {"status": "executing"})
            write_json(STAGE / "execution.json", summary)
            try:
                with punctuation.runtime(), manuscript.accounted_model(STAGE, plan, ledger), replay(
                        STAGE, plan, proof, first_request=plan["inventory_coverage_repair"]["first_request"]):
                    code = manuscript.run_manuscript_consumer(STAGE, SNAPSHOT, "inventory")
                layout = inventory.network.attempt_layout(STAGE, plan, ledger.record["calls"])
                complete = bool(layout["selected"]) and all(read_json(STAGE / f"calls/{index:04d}/result.json")["status"]
                    == "complete" for index in layout["selected"].values())
                summary.update(status="pass" if code == 0 and complete else "nonpass", exit_code=code,
                               logical_calls=len(layout["selected"]), recoveries=layout["recoveries"])
            except BaseException as error:
                summary.update(status="nonpass", error=type(error).__name__ + ": " + str(error))
                raise
            finally:
                ledger.reload()
                summary.update(attempted=len(ledger.record["calls"]), reported_tokens=ledger.record["reported_tokens"])
                write_json(STAGE / "execution.json", summary)
                write_json(STAGE / "executor.json", {"status": "stopped"})
                settle(STAGE, account=reservation["account"])
    return summary


def claim_lineage(plan, proof, *, account=ACCOUNT):
    lineage = manuscript.lineage_for(plan)
    lineage.parent.mkdir(parents=True, exist_ok=True)
    parent = {"plan_identity": proof["plan_identity"], "output": proof["predecessor"]}
    expected = {"plan_identity": plan["plan_identity"], "output": str(STAGE)}
    with lineage.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not lineage.exists() or read_json(lineage) not in (parent, expected):
            raise ValueError("Coverage continuation lost its unique source-stage predecessor")
        if any((STAGE / name).exists() for name in ("execution.json", "allocation-ledger.json", "allocation-seal.json")):
            raise ValueError("Spent or terminal coverage continuation cannot execute again")
        reservation = claim(plan, STAGE, account=account)
        pending = lineage.with_suffix(".next")
        write_json(pending, expected)
        pending.replace(lineage)
        return reservation


def verify_completed(*, account=ACCOUNT):
    from humanvoice.commands.plan_v2_command import validate_inventory
    from humanvoice.concept_baseline import load_baseline

    plan = inventory.validate_extension(read_json(STAGE / "plan.json"))
    proof = predecessor_evidence(account=account)
    log, result = read_json(STAGE / "replay-log.json"), read_json(SNAPSHOT / ".humanvoice/inventory/inventory_result.json")
    usage = completed_usage(STAGE)
    layout = inventory.network.attempt_layout(STAGE, plan, read_json(STAGE / "allocation-ledger.json")["calls"])
    if (read_json(STAGE / "execution.json")["status"] != "pass"
            or proof != plan["inventory_coverage_repair"]["evidence"] or log["inherited"] != proof["prefix"]
            or log["new_requests"] != len(layout["selected"]) or not log["reached_unrun_request"]
            or len(proof["prefix"]) + len(layout["selected"]) != proof["maximum_logical_calls"]
            or not any(event["kind"] == "settle" and event["usage"] == usage for event in read_json(account)["events"])):
        raise ValueError("Completed inventory lost exact prefix, logical bounds or settlement")
    journals = [retained.retained_journal(row) for row in proof["prefix"]]
    journals.extend(read_json(STAGE / f"calls/{index:04d}/call.json") for index in layout["selected"].values())
    seen = set()
    for reference, journal in zip(result["model_calls"], journals, strict=True):
        observed = read_json(evidence_path(SNAPSHOT / ".humanvoice/inventory", reference["path"]))
        if (digest(observed) != reference["hash"] or observed.get("runtime_record") != journal["runtime_record"]
                or observed.get("response_text") != journal["response_text"]
                or retained.canonical_request(None, (), observed["request"]) != journal["request"]
                or journal["runtime_record"]["hash"] in seen):
            raise ValueError("Coverage inventory did not retain every exact response and receipt")
        seen.add(journal["runtime_record"]["hash"])
    with punctuation.runtime(), inventory.scope.verification_only():
        validate_inventory(SNAPSHOT, load_baseline(SNAPSHOT / ".humanvoice/inventory/baseline.json"))
    report = {"status": "pass", "version": VERSION, "inherited_calls": 18,
              "new_calls": usage["allocated_calls"], "predecessor_remains_nonpass": True, "model_calls": 0}
    retained.immutable(STAGE / "coverage-verification.json", report)
    return report
