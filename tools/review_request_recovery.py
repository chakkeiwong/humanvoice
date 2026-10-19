"""Retain failed review evidence and admit one unchanged diagnostic retry."""

import fcntl
import json
import os
import shutil
import sys
from contextlib import ExitStack, contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path

from humanvoice import artifacts, automatic_reproduction
from humanvoice.artifacts import digest, implementation_hash, read_json, validated_session, write_json
from humanvoice.codex_runtime import validate_codex_record
from humanvoice.model import ModelAdapter
from tools import critic_transport_continuation as critic
from tools import delayed_network_runtime as network
from tools import process_accounting_scope as scope
from tools import semantic_repair_protocol as semantic
from tools import writer_identifier_continuation as previous
from tools.inventory_transport_continuation import canonical_request, immutable, tree_hashes
from tools.math_redline_continuation import require_settled

ROOT, BASE = previous.ROOT, previous.BASE
PRIOR = BASE / "held-out-reproduction-writer-identifier-20261019-01"
EVIDENCE = BASE / "review-request-recovery-20261020"
DIAGNOSTIC = EVIDENCE / "diagnostic.json"
VERSION = "review-request-recovery-v1"
MESSAGE = "stream disconnected before completion: The request could not be processed. Please check the request parameters."
POLICY = {"diagnostic_retries": 1, "backoff_seconds": 900, "request_changed": False,
          "proven_transient": False, "completed_responses_repeated": False,
          "unknown_tokens_released": False, "repeat_unprocessed_error": "stop"}
FILES = ("tools/review_request_recovery.py", "tools/review_request_worker.py", "tools/review_request_runner.py")
MANUSCRIPT = previous.previous.previous.repair.manuscript
authority = previous.authority
SETTLEMENT_READER = (previous.verify_settlement,)


def request_contract(request):
    names = ("event_protocol", "profile", "purpose", "system_prompt", "schema", "response_schema",
             "timeout_seconds", "output_acceptance_limit", "reservation_tokens", "implementation", "fresh_session")
    return {name: request[name] for name in names}


def diagnostic_retry(proof, events, stderr):
    messages = [event.get("message") for event in events if event.get("type") == "error"]
    messages += [event.get("error", {}).get("message") for event in events if event.get("type") == "turn.failed"]
    return (proof.get("reason") == "unclassified_provider_failure" and not proof.get("eligible")
            and bool(proof.get("provider_receipt")) and not stderr.strip()
            and messages == [MESSAGE, MESSAGE])


def failed_process(plan):
    root = PRIOR / "reproduction"
    request, process = read_json(root / "request.json"), read_json(root / "process.json")
    command = [sys.executable, "-I", "-B", str(ROOT / "tools/writer_identifier_worker.py"), str(root)]
    if (request["manifest"] != plan["reproduction_manifest"] or request["accounting_plan_hash"] != digest(plan)
            or read_json(root / "master-accounting-plan.json") != plan or request["output"] != str(root)
            or request["master_accounting"] != {"output": str(PRIOR), "plan_identity": plan["plan_identity"]}
            or request["implementation"] != implementation_hash() or request["mode"] != "fresh-inference"
            or request["comparison_contract"] != plan["reproduction_comparison"]
            or request["timeout_seconds"] != plan["reproduction_timeout_seconds"]
            or process["status"] != "failed" or process["returncode"] != 1 or process["command"] != command
            or process["worker_hash"] != digest(Path(command[3]).read_bytes())
            or process["implementation"] != implementation_hash() or process["request_hash"] != digest(request)
            or process["initially_empty"] is not True or type(process["child_pid"]) is not int
            or process["child_pid"] <= 0 or process["child_pid"] == process["parent_pid"]
            or process["parent_pid"] != request["parent_pid"] or Path(process["working_directory"]).is_relative_to(root)
            or not 0 <= process["elapsed_seconds"] < request["timeout_seconds"]
            or any(process[name + "_hash"] != digest((root / (name + ".txt")).read_bytes()) for name in ("stdout", "stderr"))):
        raise ValueError("Review recovery lost its independent failed-process evidence")
    return process


def known_good(source, failed_request, failed_folder):
    for path in sorted(Path(source).glob(".humanvoice/runtime/critic-*/inputs/api-request.json")):
        request = read_json(path)
        try:
            contract = request_contract(request)
        except KeyError:
            continue
        if contract != request_contract(failed_request):
            continue
        folder = path.parent.parent
        record = read_json(folder / "record.json")
        if record["termination"] != "complete":
            continue
        names = ("inputs/transport-schema.json", "inputs/instructions.txt")
        if any((folder / name).read_bytes() != (failed_folder / name).read_bytes() for name in names):
            continue
        reference = {"path": str((folder / "record.json").relative_to(source)), "hash": digest(record)}
        validate_codex_record(source, reference)
        return {"snapshot": str(source), "runtime_record": reference, "contract_hash": digest(request_contract(request)),
                "request_sha256": digest(request), "transport_hashes": {name: digest((folder / name).read_bytes()) for name in names}}
    raise ValueError("Unprocessed review request has no independently validated successful transport contract")


def denial_journals(snapshot, failed):
    rows, transmitted = [], []
    denied = {"New request cannot follow an unresolved non-size failure",
              "Frozen continuation evidence changed: " + str(PRIOR / "size-intents/0001.json")}
    requests = semantic.unit_requests(snapshot)
    for path in sorted(snapshot.glob(".humanvoice/preflight/attempts/**/*-call.json")):
        journal = read_json(path)
        unit = journal.get("unit_id")
        if unit not in requests or canonical_request(None, (), journal["request"]) != requests[unit]:
            raise ValueError("Failed review journal changed its native source or candidate")
        if journal.get("runtime_record"):
            if (journal["runtime_record"] != failed["runtime_record"] or journal["status"] != "failed"
                    or requests[unit] != failed["request"]):
                raise ValueError("Review recovery cannot discard another transmitted judgment")
            transmitted.append(unit)
            continue
        if (journal.get("status") != "failed" or journal.get("error") not in denied
                or any(journal.get(key) for key in ("raw_response", "response_text", "raw_transport", "request_id"))
                or any(journal.get(key) is not None for key in ("input_tokens", "output_tokens"))):
            raise ValueError("Review denial lacks proof that it stopped before transmission")
        rows.append({"path": str(path.relative_to(snapshot)), "sha256": digest(path.read_bytes())})
    if transmitted != ["unit-001"] or len(rows) != 13:
        raise ValueError("Review recovery requires one transmitted failure and thirteen unsubmitted units")
    for unit in requests:
        review = read_json(snapshot / ".humanvoice/preflight" / (unit + ".json"))
        if review.get("is_acceptable") or review.get("failure_stage") != "critic_transport":
            raise ValueError("Review recovery cannot repeat a substantive judgment")
    return rows


def diagnose():
    from tools import run_writer_identifier_program_20261019 as controller
    from tools.automatic_program_account import ACCOUNT

    before = tree_hashes(PRIOR), ACCOUNT.read_bytes()
    upstream = controller.verify()
    plan = previous.validate_extension(read_json(PRIOR / "plan.json"))
    for path in (PRIOR / "executor.json", PRIOR / "reproduction/executor.json"):
        if read_json(path)["status"] != "stopped":
            raise ValueError("Review recovery requires stopped executors")
    if read_json(PRIOR / "execution.json")["status"] != "nonpass":
        raise ValueError("Review recovery requires its original failed stage")
    process = failed_process(plan)
    usage = require_settled(PRIOR, plan, ACCOUNT)
    ledger = read_json(PRIOR / "allocation-ledger.json")
    if (len(ledger["calls"]) != 1 or len(list(PRIOR.glob("calls/*/call.json"))) != 1
            or usage["allocated_calls"] != 1 or usage["unknown_calls"] != 1
            or usage["reported_tokens"] != 0 or usage["retained_tokens"] != 544000):
        raise ValueError("Review recovery changed its single unknown charge")
    call, result = read_json(PRIOR / "calls/0000/call.json"), read_json(PRIOR / "calls/0000/result.json")
    replica = PRIOR / "reproduction/replica"
    native = network.failure_evidence(PRIOR, PRIOR / "calls/0000", plan, ledger["calls"][0], runtime_snapshot=replica)
    folder = replica / Path(call["runtime_record"]["path"]).parent
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines() if line.strip()]
    if not diagnostic_retry(native, events, (folder / "stderr.log").read_text()):
        raise ValueError("Review failure is outside the one-attempt diagnostic recovery")
    if (call["request"]["purpose"] != "independent_rewrite_verification" or result["status"] != "incomplete"
            or read_json(PRIOR / "reproduction/master-accounting-calls.json") != {
                "plan_identity": plan["plan_identity"], "ledger": ledger, "calls": [{"journal": call, "result": result}]}):
        raise ValueError("Review process omitted or changed its failed allocation")
    good = known_good(Path(plan["snapshot"]), read_json(folder / "inputs/api-request.json"), folder)
    inherited = previous.predecessor_evidence()
    if inherited != plan["technical_restart"]:
        raise ValueError("Review recovery lost its retained writer lineage")
    session, baseline, units, _ = validated_session(replica)
    previous.verify_history(replica, inherited)
    if (session["status"] != "complete" or len(units.units) != 14 or len(session["results"]) != 14
            or len(baseline.concept_entries) != 443):
        raise ValueError("Review recovery requires all fourteen accepted writers")
    retained = [{"unit_id": unit.unit_id, "reference": session["results"][unit.unit_id],
                 "result_sha256": digest(artifacts.load_unit_result(replica, session, unit.unit_id))} for unit in units.units]
    previous.repair.validate_result(replica, artifacts.load_unit_result(replica, session, "unit-014"))
    denials = denial_journals(replica, call)
    fresh = set(inherited["all_fresh_runtime_ids"]) | {folder.name}
    if previous.previous.previous.repair.api_ids(replica, validate_local=True) - previous.previous.previous.repair.api_ids(
            Path(plan["snapshot"])) != fresh:
        raise ValueError("Review recovery has unaccounted provider activity")
    if (replica / "release").exists() or (replica / ".humanvoice/assembled").exists():
        raise ValueError("Review recovery cannot discard later workflow evidence")
    proof = {"version": VERSION, "predecessor": str(PRIOR), "plan_identity": plan["plan_identity"],
             "snapshot": plan["snapshot"], "replica": str(replica), "replica_hashes": tree_hashes(replica),
             "retained_units": retained, "no_transmission": denials, "completed": inherited["completed"],
             "all_fresh_runtime_ids": sorted(fresh), "remaining_calls": inherited["remaining_calls"],
             "remaining_transport_extras": inherited["remaining_transport_extras"] - 1,
             "interrupted_request": call["request"], "failure_hash": digest(call),
             "failed_at": datetime.fromisoformat(read_json(folder / "record.json")["created_at"]).timestamp(),
             "classification": native, "policy": POLICY, "known_good": good,
             "completed_responses_repeated": False, "unknown_tokens_released": False}
    if proof["remaining_calls"] != 41 or proof["remaining_transport_extras"] != 14:
        raise ValueError("Review recovery changed the original finite attempt allowance")
    if before != (tree_hashes(PRIOR), ACCOUNT.read_bytes()):
        raise ValueError("Review diagnosis changed predecessor evidence or accounting")
    report = {"status": "pass", "version": VERSION, "policy": POLICY, "predecessor": proof,
              "stage_hashes_identity": digest(before[0]), "settlement": usage, "process_hash": digest(process),
              "upstream_identity": upstream["identity"], "upstream_files": upstream["files"],
              "model_calls": 0, "phase_admitted": False}
    report["identity"] = digest(report)
    immutable(DIAGNOSTIC, report)
    return report


def report():
    value = read_json(DIAGNOSTIC)
    if (value["identity"] != digest({key: item for key, item in value.items() if key != "identity"})
            or value["policy"] != POLICY or value["status"] != "pass"
            or any(digest((ROOT / name).read_bytes()) != expected for name, expected in value["upstream_files"].items())):
        raise ValueError("Review diagnostic or its frozen predecessor implementation changed")
    return value


def predecessor_evidence(output=PRIOR):
    from tools.automatic_program_account import ACCOUNT

    if Path(output).resolve() != PRIOR:
        raise ValueError("Review diagnostic retry cannot replenish another stage")
    value = report()
    with ExitStack() as locks:
        for name in ("execution.lock", "executor.lock", "reproduction/accounting-worker.lock", "reproduction/executor.lock"):
            handle = locks.enter_context((PRIOR / name).open("rb"))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = previous.validate_extension(read_json(PRIOR / "plan.json"))
        if (digest(tree_hashes(PRIOR)) != value["stage_hashes_identity"]
                or require_settled(PRIOR, plan, ACCOUNT) != value["settlement"]):
            raise ValueError("Review predecessor changed after independent diagnosis")
    return value["predecessor"]


def extension():
    return {"version": VERSION, "policy": POLICY, "diagnostic_identity": report()["identity"],
            "files": {name: digest((ROOT / name).read_bytes()) for name in FILES}}


def validate_extension(plan):
    previous.validate_extension(plan)
    if plan.get("review_request_extension") != extension():
        raise ValueError("Review recovery implementation changed")
    proof = plan.get("technical_restart", {})
    if proof.get("version") == VERSION and (proof != report()["predecessor"]
            or len(plan["calls"]) != proof["remaining_calls"]
            or plan["recovery"] != network.policy(proof["remaining_transport_extras"])):
        raise ValueError("Review recovery changed retained work or replenished retries")
    return plan


def verify_history(snapshot, proof):
    files = semantic.immutable_history(proof["replica_hashes"])
    for row in proof["no_transmission"]:
        destination = ".humanvoice/preflight/denied-history/" + row["path"].split("/preflight/", 1)[1]
        if (snapshot / row["path"]).exists():
            raise ValueError("Unsubmitted critic denial remains active")
        files[destination] = files.pop(row["path"])
    semantic.verify_history(snapshot, files)
    session = previous.previous.previous.repair.writer.verify_inherited(snapshot, proof)
    previous.repair.validate_result(snapshot, artifacts.load_unit_result(snapshot, session, "unit-014"))
    return session


@contextmanager
def guarded_reviews(snapshot, proof, *, probe=False):
    original = ModelAdapter.invoke
    requests = []
    halted = False

    class ProbeBoundary(KeyboardInterrupt):
        pass

    @wraps(original)
    def invoke(model, *arguments, **keywords):
        nonlocal halted
        if halted:
            raise critic.CriticTransportStop(RuntimeError("Review invocation already stopped this workflow"), None)
        request = canonical_request(model, arguments, keywords)
        verify_history(snapshot, proof)
        if (Path(model.snapshot_dir).resolve() != snapshot
                or request["purpose"] not in {"independent_rewrite_verification", "assembled_candidate_verification"}
                or digest(request) in requests or digest(request) in {row["request_hash"] for row in proof["completed"]}
                or not requests and request != proof["interrupted_request"]):
            raise ValueError("Review recovery changed its first request or repeated completed work")
        requests.append(digest(request))
        if probe:
            raise ProbeBoundary()
        try:
            return original(model, *arguments, **keywords)
        except (ValueError, RuntimeError, OSError) as error:
            halted = True
            reference = getattr(error, "runtime_record", None) or getattr(model, "last_runtime_record", None)
            raise critic.CriticTransportStop(error, reference) from error

    ModelAdapter.invoke = invoke
    try:
        yield requests, ProbeBoundary
    finally:
        ModelAdapter.invoke = original


def failure_summary(output):
    output = Path(output)
    ledger_path = output / "allocation-ledger.json"
    if not ledger_path.exists():
        return None
    entries = read_json(ledger_path)["calls"]
    if not entries or entries[-1]["status"] == "complete":
        return None
    matches = [path for path in output.glob("calls/*/call.json")
               if read_json(path).get("invocation_id") == entries[-1]["invocation_id"]]
    if len(matches) != 1:
        return {"reason": "incomplete_call_without_unique_journal"}
    call = read_json(matches[0])
    result = {"reason": "independent_review_invocation_failed", "purpose": call["request"]["purpose"],
              "request_hash": call["request_hash"], "runtime_record": call.get("runtime_record"),
              "journal": str(matches[0]), "unknown_charge_retained": entries[-1]["usage"] is None}
    if call.get("runtime_record"):
        folder = output / "reproduction/replica" / Path(call["runtime_record"]["path"]).parent
        events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines() if line.strip()]
        messages = [event.get("message", "") for event in events if event.get("type") == "error"]
        messages += [event.get("error", {}).get("message", "") for event in events if event.get("type") == "turn.failed"]
        result["diagnostics"] = list(dict.fromkeys(message[:500] for message in messages))[:3]
    return result


def resume(root, *, probe=False):
    root = Path(root).resolve()
    plan = validate_extension(read_json(root / "master-accounting-plan.json"))
    proof, snapshot = plan["technical_restart"], root / "replica"
    if snapshot.exists() or tree_hashes(Path(proof["replica"])) != proof["replica_hashes"]:
        raise ValueError("Review recovery requires unchanged history and a fresh replica")
    shutil.copytree(proof["replica"], snapshot)
    critic.archive_denials(root, snapshot, proof)
    verify_history(snapshot, proof)
    if not probe:
        network.wait_until(root / "diagnostic-retry-wait.json", proof["failure_hash"], proof["failed_at"])
    stop = None
    with guarded_reviews(snapshot, proof, probe=probe) as (requests, boundary):
        try:
            code = MANUSCRIPT.run_manuscript_consumer(root, snapshot, "humanize")
        except boundary:
            if not probe or len(requests) != 1:
                raise
            code = 0
        except critic.CriticTransportStop as error:
            code, stop = 1, str(error)
    verify_history(snapshot, proof)
    summary = None if probe else failure_summary(root.parent)
    write_json(root / "review-request-execution.json", {"status": "pass" if code == 0 else "nonpass", "probe": probe,
               "retained_writers": 14, "requests": requests, "independent_pid": os.getpid(), "stop": stop,
               "failure": summary, "completed_responses_repeated": False})
    write_json(root / "execution.json", {"review_request_recovery": VERSION, "exit_code": code, "failure": summary})
    return code


def validate_accounted_calls(root, plan, new_calls):
    validate_extension(plan)
    proof = predecessor_evidence(plan["technical_restart"]["predecessor"])
    verify_history(Path(root) / "replica", proof)
    inherited = set(proof["all_fresh_runtime_ids"])
    if not inherited < set(new_calls):
        raise ValueError("Review successor lost inherited receipts or fresh independent reviews")
    result = previous.previous.previous.repair.NATIVES[0](root, plan, set(new_calls) - inherited)
    if (result["calls"][0]["journal"]["request"] != proof["interrupted_request"]
            or any(row["journal"]["request"]["purpose"] not in {
                "independent_rewrite_verification", "assembled_candidate_verification"} for row in result["calls"])):
        raise ValueError("Review successor changed its diagnostic request or repeated a writer")
    return result


def verify_settlement(output):
    with previous.archive.access():
        if "review_request_extension" not in read_json(Path(output) / "plan.json"):
            return SETTLEMENT_READER[0](output)
        with scope.accounting_scope(), pipeline(), scope.verification_only():
            return network.SETTLEMENT_READER[0](output)


@contextmanager
def pipeline(*, planning=(), snapshots=(), authorization=network.budget.authority.AUTHORITY):
    from tools import automatic_reproduction_worker, parallel_verification_replay

    enabled = {(str(Path(snapshot).resolve()), stage) for snapshot, stage in planning}
    with previous.pipeline(planning=planning, snapshots=snapshots, authorization=authorization):
        native_plan, native_worker_plan = MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for
        native_command, native_verifier = automatic_reproduction._command, automatic_reproduction.validate_accounted_calls
        native_settlement, native_observations = parallel_verification_replay.verify_settlement, automatic_reproduction._observations

        def plan_for(snapshot, stage, *arguments, **options):
            parent = options.get("technical_predecessor")
            selected = (str(Path(snapshot).resolve()), stage) in enabled
            continued = parent is not None and Path(parent).resolve() == PRIOR
            proof = predecessor_evidence(parent) if continued else None
            if continued:
                if not selected or stage != "reproduction":
                    raise ValueError("Review successor requires an explicitly scoped reproduction")
                options.pop("technical_predecessor")
            result = native_plan(snapshot, stage, *arguments, **options)
            if proof:
                predecessor = read_json(PRIOR / "plan.json")
                if (len(result["calls"]) != proof["remaining_calls"] or result["snapshot"] != proof["snapshot"]
                        or any(result["bindings"][key] != predecessor["bindings"][key] for key in
                               ("manifest", "source", "policy", "rights", "implementation", "stage", "profile"))):
                    raise ValueError("Review successor changed its qualified source or remaining work")
                result.update(technical_restart=proof, recovery=network.policy(proof["remaining_transport_extras"]))
                result["bindings"]["restart_verifier"] = digest(Path(__file__).read_bytes())
                result["reproduction_timeout_seconds"] = min(86400, 900 * (proof["remaining_calls"]
                    + 2 * proof["remaining_transport_extras"]) + 300)
            if selected:
                result["review_request_extension"] = extension()
                result.pop("plan_identity")
                result["plan_identity"] = digest(result)
            return result

        def command(root, master_accounting=False):
            path = Path(root) / "master-accounting-plan.json"
            if master_accounting and path.exists() and "review_request_extension" in read_json(path):
                validate_extension(read_json(path))
                return [sys.executable, "-I", "-B", str(ROOT / "tools/review_request_worker.py"), str(Path(root).resolve())]
            return native_command(root, master_accounting)

        def verifier(root, plan, new_calls):
            if plan.get("technical_restart", {}).get("version") == VERSION:
                return validate_accounted_calls(root, plan, new_calls)
            return native_verifier(root, plan, new_calls)

        def observations(root, *arguments, **keywords):
            try:
                return native_observations(root, *arguments, **keywords)
            except ValueError as error:
                path = Path(root) / "review-request-execution.json"
                if str(error) != "Reproduction lacks current independent process execution evidence" or not path.exists():
                    raise
                detail = read_json(path).get("failure")
                if not detail:
                    raise
                raise ValueError("Independent review failed: " + "; ".join(detail.get("diagnostics") or [detail["reason"]])) from error

        MANUSCRIPT.plan_for = automatic_reproduction_worker.plan_for = plan_for
        automatic_reproduction._command, automatic_reproduction._observations = command, observations
        try:
            with network.replaced_aliases(native_verifier, verifier), network.replaced_aliases(native_settlement, verify_settlement):
                yield
        finally:
            MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for = native_plan, native_worker_plan
            automatic_reproduction._command, automatic_reproduction._observations = native_command, native_observations
