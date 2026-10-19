"""Resume review of retained writers after a verified identifier-only derivation."""

import fcntl
import os
import shutil
import sys
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from functools import wraps
from pathlib import Path

from humanvoice import artifacts, automatic_reproduction
from humanvoice.artifacts import digest, load_session, read_json, validated_session, write_json
from humanvoice.model import ModelAdapter
from tools import archive_evidence as archive
from tools import process_accounting_scope as scope
from tools import writer_identifier_repair as repair
from tools import writer_size_continuation as previous
from tools.inventory_transport_continuation import canonical_request, immutable, tree_hashes
from tools.math_redline_continuation import require_settled

ROOT, BASE, PRIOR, EVIDENCE = repair.ROOT, repair.BASE, repair.PRIOR, repair.EVIDENCE
authority = previous.authority
VERSION = "writer-identifier-continuation-v1"
FILES = ("tools/archive_evidence.py", "tools/writer_identifier_repair.py", "tools/writer_identifier_continuation.py",
         "tools/writer_identifier_worker.py", "tools/writer_identifier_runner.py")
SETTLEMENT_READER = (previous.verify_settlement,)


def ensure_execution_paths(base=BASE):
    with archive.access():
        unverified = sorted(path.name for path in Path(base).iterdir() if path.is_symlink())
        if unverified:
            raise ValueError("Execution contains unverified archive aliases: " + ", ".join(unverified[:3]))


def extension():
    return {"version": VERSION, "policy": repair.POLICY, "diagnostic_identity": repair.report()["identity"],
            "archive": archive.identity(),
            "files": {name: digest((ROOT / name).read_bytes()) for name in FILES}}


def failed_process(plan):
    root = PRIOR / "reproduction"
    request, process = read_json(root / "request.json"), read_json(root / "process.json")
    command = [sys.executable, "-I", "-B", str(ROOT / "tools/writer_size_worker.py"), str(root)]
    if (process["status"] != "failed" or process["returncode"] != 3 or process["command"] != command
            or process["worker_hash"] != digest(Path(command[3]).read_bytes())
            or process["request_hash"] != digest(request) or request["accounting_plan_hash"] != digest(plan)
            or read_json(root / "master-accounting-plan.json") != plan
            or request["master_accounting"] != {"output": str(PRIOR), "plan_identity": plan["plan_identity"]}
            or request["manifest"] != plan["reproduction_manifest"] or not process["initially_empty"]
            or process["parent_pid"] != request["parent_pid"] or process["child_pid"] == process["parent_pid"]
            or not 0 <= process["elapsed_seconds"] < request["timeout_seconds"]
            or any(process[stream + "_hash"] != digest((root / (stream + ".txt")).read_bytes()) for stream in ("stdout", "stderr"))):
        raise ValueError("Identifier predecessor lost its failed independent process")


def diagnose():
    from tools import run_writer_size_program_20261019 as controller
    from tools.automatic_program_account import ACCOUNT

    before = tree_hashes(PRIOR), ACCOUNT.read_bytes()
    print("Verify frozen size-recovery implementation and predecessor.", flush=True)
    upstream = controller.verify()
    plan = previous.validate_extension(read_json(PRIOR / "plan.json"))
    if (read_json(PRIOR / "execution.json")["status"] != "nonpass"
            or read_json(PRIOR / "executor.json")["status"] != "stopped"):
        raise ValueError("Identifier repair requires a stopped predecessor")
    failed_process(plan)
    usage = require_settled(PRIOR, plan, ACCOUNT)
    inherited = previous.predecessor_evidence()
    if inherited != plan["technical_restart"]:
        raise ValueError("Identifier predecessor lost its original proof")
    snapshot = PRIOR / "reproduction/replica"
    session, baseline, units, _ = validated_session(snapshot, require_complete=False)
    if (session["status"] != "interrupted" or len(units.units) != 14
            or set(session["results"]) != {unit.unit_id for unit in units.units[:-1]}):
        raise ValueError("Identifier repair requires exactly thirteen retained native results")
    current = previous.retained_proof(snapshot, inherited)
    previous.previous.repair.verify_history(snapshot, current)
    previous.previous.repair.writer.verify_inherited(snapshot, current)
    ledger = read_json(PRIOR / "allocation-ledger.json")
    calls = [read_json(path) for path in sorted(PRIOR.glob("calls/*/call.json"))]
    layout = previous.accounting.attempt_layout(PRIOR, plan, ledger["calls"], runtime_snapshot=snapshot)
    if (len(calls) != 9 or layout["indices"] != list(range(9)) or layout["recoveries"] or layout["child_calls"]
            or [call["request"] for call in calls] != list(inherited["requests"].values())
            or any(call["status"] != "complete" for call in calls)
            or usage["allocated_calls"] != 9 or usage["unknown_calls"] != 0):
        raise ValueError("Identifier repair changed spent writer membership or charges")
    accepted = list(current["retained_units"])
    for unit, call in zip(units.units[5:-1], calls[:-1], strict=True):
        data = artifacts.load_unit_result(snapshot, session, unit.unit_id)
        receipt = previous.previous.repair.validate_codex_record(snapshot, call["runtime_record"])
        result = repair.replay.replay(snapshot, call, receipt, session, baseline, units)
        if not result.is_acceptable or asdict(result) != data:
            raise ValueError("Identifier predecessor changed a completed writer judgment")
        accepted.append({"unit_id": unit.unit_id, "reference": session["results"][unit.unit_id], "result_sha256": digest(data)})
    result, original, payload, correction = repair.derive(snapshot, session, baseline, units)
    saved = list(snapshot.glob(".humanvoice/writer-size-splits/*/unit-014/result.json"))
    if len(saved) != 1 or previous.splitting.unbound(previous.splitting.restore_result(read_json(saved[0]))) != {
            key: value for key, value in original.items() if key != "bindings"}:
        raise ValueError("Identifier failure differs from its retained native checkpoint")
    journals = [read_json(path) for path in snapshot.glob(".humanvoice/rewrites/attempts/**/*.json")]
    if any(row.get("runtime_record") == calls[-1]["runtime_record"] for row in journals):
        raise ValueError("Identifier writer already has an attempt journal")
    fresh = set(inherited["all_fresh_runtime_ids"]) | {Path(call["runtime_record"]["path"]).parent.name for call in calls}
    native = previous.previous.repair
    if native.api_ids(snapshot, validate_local=True) - native.api_ids(Path(plan["snapshot"])) != fresh:
        raise ValueError("Identifier predecessor has omitted or unexplained provider activity")
    remaining = inherited["remaining_logical_calls"] - len(calls)
    if remaining != 41:
        raise ValueError("Identifier review bound changed")
    proof = {"version": VERSION, "predecessor": str(PRIOR), "plan_identity": plan["plan_identity"],
             "snapshot": plan["snapshot"], "replica": str(snapshot), "replica_hashes": tree_hashes(snapshot),
             "retained_units": accepted, "no_transmission": previous.no_transmission_journals(snapshot, inherited),
             "completed": [*inherited["completed"], *[
                 {"request_hash": call["request_hash"], "runtime_record": call["runtime_record"]} for call in calls]],
             "all_fresh_runtime_ids": sorted(fresh), "remaining_calls": remaining,
             "remaining_transport_extras": inherited["remaining_transport_extras"],
             "completed_responses_repeated": False, "unknown_tokens_released": False, "model_calls": 0}
    if before != (tree_hashes(PRIOR), ACCOUNT.read_bytes()):
        raise ValueError("Identifier diagnosis changed retained history or accounting")
    report = {"version": repair.VERSION, "instruction": repair.INSTRUCTION, "policy": repair.POLICY,
              "status": "pass", "upstream_identity": upstream["identity"], "upstream_files": upstream["files"],
              "stage_hashes_identity": digest(before[0]), "predecessor": proof, "result_hash": digest(result),
              "original_result_hash": digest(original), "call_hash": digest(calls[-1]),
              "response_hash": digest(calls[-1]["response_text"]), "corrected_payload_hash": digest(payload),
              "correction": correction, "phase_admitted": False, "model_calls": 0,
              "settlement": {key: usage[key] for key in ("allocated_calls", "unknown_calls", "reported_tokens", "retained_tokens")}}
    report["identity"] = digest(report)
    immutable(repair.DIAGNOSTIC, report)
    print("Identifier-only native replay passes; thirteen writers remain unchanged.", flush=True)
    return report


def predecessor_evidence(output=PRIOR, *, account=previous.previous.repair.manuscript.ACCOUNT):
    ensure_execution_paths()
    if Path(output).resolve() != PRIOR:
        raise ValueError("Identifier continuation has an unrelated predecessor")
    report = repair.report()
    with ExitStack() as locks:
        for name in ("execution.lock", "executor.lock", "reproduction/accounting-worker.lock", "reproduction/executor.lock"):
            handle = locks.enter_context((PRIOR / name).open("rb"))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = previous.validate_extension(read_json(PRIOR / "plan.json"))
        usage = require_settled(PRIOR, plan, account)
        if (digest(tree_hashes(PRIOR)) != report["stage_hashes_identity"]
                or {key: usage[key] for key in report["settlement"]} != report["settlement"]
                or any(digest((ROOT / name).read_bytes()) != expected for name, expected in report["upstream_files"].items())):
            raise ValueError("Identifier predecessor changed after independent native verification")
    return report["predecessor"]


def validate_extension(plan):
    previous.validate_extension(plan)
    if plan.get("writer_identifier_extension") != extension():
        raise ValueError("Identifier continuation implementation changed")
    proof = plan.get("technical_restart", {})
    if proof.get("version") == VERSION and (proof != repair.report()["predecessor"]
            or len(plan["calls"]) != proof["remaining_calls"]
            or plan["recovery"] != previous.previous.repair.network.policy(proof["remaining_transport_extras"])):
        raise ValueError("Identifier continuation changed retained work or its finite bound")
    return plan


def verify_history(snapshot, proof):
    previous.previous.repair.verify_history(Path(snapshot), proof)
    return previous.previous.repair.writer.verify_inherited(Path(snapshot), proof)


@contextmanager
def review_only(root, snapshot, proof, *, probe=False):
    from humanvoice.commands import preflight_v2_command

    native_invoke, native_preflight = ModelAdapter.invoke, preflight_v2_command.run
    requests = []

    class ProbeBoundary(KeyboardInterrupt):
        pass

    @wraps(native_invoke)
    def invoke(model, *arguments, **keywords):
        request = canonical_request(model, arguments, keywords)
        if Path(model.snapshot_dir).resolve() != Path(snapshot).resolve():
            raise ValueError("Identifier continuation left its independent replica")
        verify_history(snapshot, proof)
        if (request["purpose"] not in {"independent_rewrite_verification", "assembled_candidate_verification"}
                or digest(request) in {row["request_hash"] for row in proof["completed"]}):
            raise ValueError("Identifier continuation cannot repeat a retained writer")
        requests.append(digest(request))
        if probe:
            raise ProbeBoundary()
        return native_invoke(model, *arguments, **keywords)

    def preflight(arguments):
        previous.previous.repair.writer.archive_denials(root, Path(snapshot), proof)
        return native_preflight(arguments)

    ModelAdapter.invoke, preflight_v2_command.run = invoke, preflight
    try:
        yield requests, ProbeBoundary
    finally:
        ModelAdapter.invoke, preflight_v2_command.run = native_invoke, native_preflight


def resume(root, *, probe=False):
    root = Path(root).resolve()
    plan = validate_extension(read_json(root / "master-accounting-plan.json"))
    proof, snapshot = plan["technical_restart"], root / "replica"
    if snapshot.exists() or tree_hashes(Path(proof["replica"])) != proof["replica_hashes"]:
        raise ValueError("Identifier continuation requires unchanged history and a fresh replica")
    shutil.copytree(proof["replica"], snapshot)
    derived = repair.materialize(snapshot)
    current = dict(proof, retained_units=[*proof["retained_units"], derived])
    with review_only(root, snapshot, current, probe=probe) as (requests, boundary):
        try:
            code = previous.previous.repair.manuscript.run_manuscript_consumer(root, snapshot, "humanize")
        except boundary:
            if not probe or len(requests) != 1:
                raise
            code = 0
    session = verify_history(snapshot, current)
    if code == 0 and session["status"] != "complete":
        raise ValueError("Identifier continuation lost complete native rewriting")
    write_json(root / "identifier-execution.json", {"status": "pass" if code == 0 else "nonpass",
        "probe": probe, "retained_writers": 13, "derived_writers": 1, "requests": requests,
        "independent_pid": os.getpid(), "completed_responses_repeated": False})
    write_json(root / "execution.json", {"writer_identifier": VERSION, "exit_code": code})
    return code


def validate_accounted_calls(root, plan, new_calls):
    validate_extension(plan)
    proof = predecessor_evidence(plan["technical_restart"]["predecessor"])
    snapshot = Path(root) / "replica"
    session = verify_history(snapshot, proof)
    repair.validate_result(snapshot, artifacts.load_unit_result(snapshot, session, "unit-014"))
    inherited = set(proof["all_fresh_runtime_ids"])
    if not inherited < set(new_calls):
        raise ValueError("Identifier successor lacks inherited writers and fresh independent reviews")
    result = previous.previous.repair.NATIVES[0](root, plan, set(new_calls) - inherited)
    if any(row["journal"]["request"]["purpose"] not in {
            "independent_rewrite_verification", "assembled_candidate_verification"} for row in result["calls"]):
        raise ValueError("Identifier successor repeated a writer")
    return result


def verify_settlement(output):
    with archive.access():
        if "writer_identifier_extension" not in read_json(Path(output) / "plan.json"):
            return SETTLEMENT_READER[0](output)
        with scope.accounting_scope(), pipeline(), scope.verification_only():
            return previous.previous.repair.network.SETTLEMENT_READER[0](output)


@contextmanager
def pipeline(*, planning=(), snapshots=(), authorization=previous.previous.repair.network.budget.authority.AUTHORITY):
    from tools import automatic_reproduction_worker, parallel_verification_replay

    enabled = {(str(Path(snapshot).resolve()), stage) for snapshot, stage in planning}
    with archive.access(), previous.pipeline(planning=planning, snapshots=snapshots,
            authorization=authorization), repair.consumer_validation():
        native_plan = previous.previous.repair.manuscript.plan_for
        native_worker_plan = automatic_reproduction_worker.plan_for
        native_command, native_verifier = automatic_reproduction._command, automatic_reproduction.validate_accounted_calls
        native_settlement = parallel_verification_replay.verify_settlement

        def plan_for(snapshot, stage, *arguments, **options):
            parent = options.get("technical_predecessor")
            continued = parent is not None and Path(parent).resolve() == PRIOR
            selected = (str(Path(snapshot).resolve()), stage) in enabled
            proof = predecessor_evidence(parent) if continued else None
            if continued:
                if not selected or stage != "reproduction":
                    raise ValueError("Identifier successor requires an explicitly scoped reproduction")
                options.pop("technical_predecessor")
            result = native_plan(snapshot, stage, *arguments, **options)
            if proof:
                predecessor = read_json(PRIOR / "plan.json")
                if (len(result["calls"]) != proof["remaining_calls"] or result["snapshot"] != proof["snapshot"]
                        or any(result["bindings"][key] != predecessor["bindings"][key] for key in
                               ("manifest", "source", "policy", "rights", "implementation", "stage", "profile"))):
                    raise ValueError("Identifier successor changed its qualified source or review bounds")
                result.update(technical_restart=proof,
                    recovery=previous.previous.repair.network.policy(proof["remaining_transport_extras"]))
                result["bindings"]["restart_verifier"] = digest(Path(__file__).read_bytes())
                result["reproduction_timeout_seconds"] = min(86400, 900 * (proof["remaining_calls"]
                    + 2 * proof["remaining_transport_extras"]) + 300)
            if selected:
                result["writer_identifier_extension"] = extension()
                result.pop("plan_identity")
                result["plan_identity"] = digest(result)
            return result

        def command(root, master_accounting=False):
            path = Path(root) / "master-accounting-plan.json"
            if master_accounting and path.exists() and "writer_identifier_extension" in read_json(path):
                validate_extension(read_json(path))
                return [sys.executable, "-I", "-B", str(ROOT / "tools/writer_identifier_worker.py"), str(Path(root).resolve())]
            return native_command(root, master_accounting)

        def verifier(root, plan, new_calls):
            if plan.get("technical_restart", {}).get("version") == VERSION:
                return validate_accounted_calls(root, plan, new_calls)
            return native_verifier(root, plan, new_calls)

        previous.previous.repair.manuscript.plan_for = automatic_reproduction_worker.plan_for = plan_for
        automatic_reproduction._command = command
        try:
            with previous.runtime.previous.replaced_aliases(native_verifier, verifier), previous.runtime.previous.replaced_aliases(
                    native_settlement, verify_settlement):
                yield
        finally:
            previous.previous.repair.manuscript.plan_for, automatic_reproduction_worker.plan_for = native_plan, native_worker_plan
            automatic_reproduction._command = native_command
