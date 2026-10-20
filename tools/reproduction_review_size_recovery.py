"""Continue only the missing assembled reviews after a settled size failure."""

import fcntl
import json
import os
import shutil
import sys
from contextlib import ExitStack, contextmanager
from functools import wraps
from pathlib import Path
from types import SimpleNamespace

from humanvoice import artifacts, automatic_reproduction
from humanvoice.artifacts import confined_path, digest, implementation_hash, read_json, write_json
from humanvoice.codex_runtime import validate_codex_record
from humanvoice.model import ModelAdapter
from tools import assembled_size_recovery as recovery
from tools import reproduction_semantic_recovery as previous
from tools.inventory_transport_continuation import canonical_request, immutable, tree_hashes
from tools.math_redline_continuation import require_settled

ROOT, BASE = previous.ROOT, previous.BASE
PRIOR = BASE / "held-out-reproduction-semantic-repair-20261020-01"
EVIDENCE = BASE / "assembled-review-size-recovery-20261020"
DIAGNOSTIC = EVIDENCE / "diagnostic.json"
VERSION = "reproduction-review-size-recovery-v1"
FILES = ("tools/assembled_size_recovery.py", "tools/reproduction_review_size_recovery.py",
         "tools/reproduction_review_size_worker.py", "tools/reproduction_review_size_runner.py")
MANUSCRIPT, network, scope = previous.MANUSCRIPT, previous.network, previous.scope
archive, size, authority = previous.archive, previous.size, previous.authority
writer_repair, semantic = previous.writer_repair, previous.semantic
SETTLEMENT_READER = (previous.verify_settlement,)


def failed_process(plan):
    root = PRIOR / "reproduction"
    request, process = read_json(root / "request.json"), read_json(root / "process.json")
    command = [sys.executable, "-I", "-B", str(ROOT / "tools/reproduction_semantic_worker.py"), str(root)]
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
        raise ValueError("Review size recovery lost its stopped independent process")
    return process


def jobs_for(snapshot):
    session, baseline, _, _ = artifacts.validated_session(Path(snapshot))
    assembly = read_json(Path(snapshot) / ".humanvoice/assembled/assembly_result.json")
    candidate = confined_path(snapshot, assembly["candidate_directory"])
    jobs, files = recovery.NATIVES[0](Path(snapshot), session, baseline, candidate, 180000)
    return session, baseline, candidate, jobs, files


def bounds(root_count, complete_count, network_spent, network_maximum):
    remaining = root_count - complete_count - 1
    extras = network_maximum - network_spent
    if remaining < 0 or extras < 0:
        raise ValueError("Review size recovery lost its finite remaining allowance")
    maximum = recovery.POLICY["maximum_child_calls_per_root"]
    return {"remaining_calls": maximum + (maximum + 1) * remaining,
            "remaining_transport_extras": extras, "remaining_roots": remaining,
            "retained_assembled_reviews": complete_count, "root_windows": root_count}


def retained_files(tree):
    return {name: value for name, value in tree.items() if name.startswith((
        "source/", ".humanvoice/runtime/", ".humanvoice/preflight/assembled/",
        ".humanvoice/preflight/attempts/", ".humanvoice/preflight/canonical/"))}


def verify_retained(snapshot, proof):
    semantic.retained_bytes(snapshot, proof["semantic_scope"], complete=True)
    semantic.verify_history(snapshot, proof["retained_files"])
    session = artifacts.load_session(Path(snapshot))
    if session["results"] != proof["unit_results"]:
        raise ValueError("Review-only recovery changed a completed writer")
    current = ".humanvoice/rewrites/current.json"
    names = [current, ".humanvoice/assembled/assembly_result.json",
             ".humanvoice/rewrites/" + read_json(Path(snapshot) / current)["path"]]
    if any(digest(confined_path(snapshot, name).read_bytes()) != proof["replica_hashes"].get(name) for name in names):
        raise ValueError("Review-only recovery changed its retained session or assembly")
    return session


def diagnose():
    from tools import run_reproduction_semantic_20261020 as controller
    from tools.automatic_program_account import ACCOUNT

    before = tree_hashes(PRIOR), ACCOUNT.read_bytes()
    upstream = controller.verify()
    plan = previous.validate_extension(read_json(PRIOR / "plan.json"))
    if (read_json(PRIOR / "execution.json")["status"] != "nonpass"
            or any(read_json(PRIOR / name)["status"] != "stopped" for name in
                   ("executor.json", "reproduction/executor.json"))):
        raise ValueError("Review size recovery requires a stopped and settled predecessor")
    process = failed_process(plan)
    usage = require_settled(PRIOR, plan, ACCOUNT)
    replica = PRIOR / "reproduction/replica"
    old = plan["technical_restart"]
    semantic.retained_bytes(replica, old["scope"], complete=True)
    evidence = read_json(PRIOR / "reproduction/master-accounting-calls.json")
    ledger = read_json(PRIOR / "allocation-ledger.json")
    if evidence["plan_identity"] != plan["plan_identity"] or evidence["ledger"] != ledger:
        raise ValueError("Review size recovery lost native accounting evidence")
    allowed = network.recovery.attempt_calls(plan)
    indices = {row["key"]: index for index, row in enumerate(allowed)}
    session, baseline, candidate, jobs, files = jobs_for(replica)
    completed, failed, network_spent, identifiers = [], [], 0, set()
    for entry, row in zip(ledger["calls"], evidence["calls"], strict=True):
        index = indices[entry["key"]]
        call, result = row["journal"], row["result"]
        directory = PRIOR / f"calls/{index:04d}"
        reference = call["runtime_record"]
        record = validate_codex_record(replica, reference)
        runtime = confined_path(replica, reference["path"]).parent
        request = read_json(runtime / "inputs/api-request.json")
        if (call != read_json(directory / "call.json") or result != read_json(directory / "result.json")
                or digest(result) != entry["result_hash"] or entry["invocation_id"] != call["invocation_id"]
                or entry["input_hash"] != allowed[index]["input_hash"]
                or call["request_hash"] != digest(call["request"])
                or call["prompt_hash"] != request["prompt_hash"] or request["profile"] != plan["profile"]
                or (runtime / "inputs/prompt.txt").read_text() != call["request"]["prompt"]
                or runtime.name in identifiers or result["status"] != entry["status"]):
            raise ValueError("Review size predecessor allocation differs from actual invocation")
        identifiers.add(runtime.name)
        if entry["status"] == "complete":
            if (record["termination"] != "complete" or call["status"] != "complete"
                    or entry["usage"] != record["input_tokens"] + record["output_tokens"]):
                raise ValueError("Review size predecessor changed completed usage")
            completed.append({"request_hash": call["request_hash"], "runtime_record": reference,
                              "purpose": call["request"]["purpose"]})
        else:
            if entry["status"] != "incomplete" or entry["usage"] is not None or record["termination"] != "error":
                raise ValueError("Review size predecessor released an incomplete charge")
            proof = network.failure_evidence(PRIOR, directory, plan, entry)
            if proof["eligible"]:
                network_spent += 1
            else:
                matching = [job for job in jobs if digest(job["prompt"]) == call["prompt_hash"]]
                if len(matching) != 1:
                    raise ValueError("Review size failure lacks one original window")
                failed.append((matching[0], recovery.failure(replica, call, matching[0])))
    activity = read_json(PRIOR / "reproduction/semantic-repair-execution.json")
    assembled = [row for row in completed if row["purpose"] == "assembled_candidate_verification"]
    if (len(failed) != 1 or failed[0][1]["semantic_check"] != "pass"
            or activity["status"] != "nonpass" or activity["probe"]
            or activity["stop"] != recovery.ERROR or set(activity["writers"]) != set(old["scope"]["rejected"])
            or set(activity["critics"]) != set(old["scope"]["rejected"])
            or len(completed) != len(assembled) + 2 * len(old["scope"]["rejected"])
            or len(identifiers) != usage["allocated_calls"] or usage["unknown_calls"] != network_spent + 1):
        raise ValueError("Review size recovery changed the repaired units or stopped cause")
    fresh = writer_repair.api_ids(replica, validate_local=True) - writer_repair.api_ids(Path(plan["snapshot"]))
    if fresh != set(old["all_fresh_runtime_ids"]) | identifiers:
        raise ValueError("Review size predecessor contains unaccounted runtime attempts")
    tree = tree_hashes(replica)
    job, checked = failed[0]
    children = recovery.partition(job, digest(job["prompt"]), 0)
    limits = bounds(len(jobs), len(assembled), network_spent, plan["recovery"]["maximum_total"])
    proof = {"version": VERSION, "predecessor": str(PRIOR), "plan_identity": plan["plan_identity"],
             "snapshot": plan["snapshot"], "replica": str(replica), "replica_hashes": tree,
             "retained_files": retained_files(tree), "semantic_scope": old["scope"],
             "unit_results": session["results"], "files": files, "all_fresh_runtime_ids": sorted(fresh),
             "completed": [*old["completed"], *completed], "failed_job": job, "size_failure": checked,
             "first_request_hash": digest(canonical_request(None, (), {"prompt": children[0]["prompt"],
                 "purpose": "assembled_candidate_verification", "response_schema": "critic-response"})), **limits}
    if before != (tree_hashes(PRIOR), ACCOUNT.read_bytes()):
        raise ValueError("Review size diagnosis changed evidence or accounting")
    result = {"status": "pass", "version": VERSION, "policy": recovery.POLICY, "predecessor": proof,
              "stage_hashes_identity": digest(before[0]), "settlement": usage, "process_hash": digest(process),
              "upstream_identity": upstream["identity"], "upstream_files": upstream["files"], "model_calls": 0}
    result["identity"] = digest(result)
    immutable(DIAGNOSTIC, result)
    return result


def report():
    value = read_json(DIAGNOSTIC)
    if (value["identity"] != digest({key: item for key, item in value.items() if key != "identity"})
            or value["policy"] != recovery.POLICY or value["status"] != "pass"
            or any(digest((ROOT / name).read_bytes()) != expected for name, expected in value["upstream_files"].items())):
        raise ValueError("Review size diagnosis or frozen predecessor changed")
    return value


def predecessor_evidence(output=PRIOR):
    from tools.automatic_program_account import ACCOUNT

    if Path(output).resolve() != PRIOR:
        raise ValueError("Review size recovery cannot replenish a different predecessor")
    value = report()
    with ExitStack() as locks:
        for name in ("execution.lock", "executor.lock", "reproduction/accounting-worker.lock", "reproduction/executor.lock"):
            handle = locks.enter_context((PRIOR / name).open("rb"))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = previous.validate_extension(read_json(PRIOR / "plan.json"))
        if (digest(tree_hashes(PRIOR)) != value["stage_hashes_identity"]
                or require_settled(PRIOR, plan, ACCOUNT) != value["settlement"]):
            raise ValueError("Review size predecessor changed after diagnosis")
    return value["predecessor"]


def extension():
    return {"version": VERSION, "policy": recovery.POLICY, "diagnostic_identity": report()["identity"],
            "files": {name: digest((ROOT / name).read_bytes()) for name in FILES}}


def validate_extension(plan):
    previous.validate_extension(plan)
    if plan.get("assembled_size_extension") != recovery.extension() or plan.get("review_size_continuation") != extension():
        raise ValueError("Review size recovery implementation changed")
    proof = plan.get("technical_restart", {})
    if proof.get("version") == VERSION and (proof != report()["predecessor"]
            or len(plan["calls"]) != proof["remaining_calls"]
            or plan["recovery"] != network.policy(proof["remaining_transport_extras"])):
        raise ValueError("Review size recovery changed retained work or replenished retries")
    return plan


@contextmanager
def guarded_reviews(snapshot, proof, *, probe=False):
    native = ModelAdapter.invoke
    seen, halted = [], False
    old = {row["request_hash"] for row in proof["completed"]}
    old.add(digest(canonical_request(None, (), {"prompt": proof["failed_job"]["prompt"],
        "purpose": "assembled_candidate_verification", "response_schema": "critic-response"})))

    class ProbeBoundary(KeyboardInterrupt):
        pass

    @wraps(native)
    def invoke(model, *arguments, **keywords):
        nonlocal halted
        if halted:
            raise previous.previous.critic.CriticTransportStop(RuntimeError("Review recovery already stopped"), None)
        halted = True
        request = canonical_request(model, arguments, keywords)
        identity = digest(request)
        verify_retained(snapshot, proof)
        if (Path(model.snapshot_dir).resolve() != Path(snapshot).resolve()
                or request["purpose"] != "assembled_candidate_verification"
                or identity in old or identity in seen or request not in semantic.assembled_requests(snapshot)):
            raise ValueError("Review recovery cannot repeat or change its exact remaining scope")
        seen.append(identity)
        if probe:
            if identity != proof["first_request_hash"]:
                raise ValueError("Review recovery probe left its exact first child")
            raise ProbeBoundary()
        try:
            result = native(model, *arguments, **keywords)
        except (ValueError, RuntimeError, OSError) as error:
            reference = getattr(error, "runtime_record", None) or getattr(model, "last_runtime_record", None)
            runtime = confined_path(snapshot, reference["path"]).parent if reference else None
            row = {"runtime_record": reference, "prompt_hash": digest(request["prompt"]), "status": "failed",
                   "raw_response": read_json(runtime / "response.json").get("text", "") if runtime else ""}
            context = json.loads(request["prompt"].split("REVIEW_DATA:\n", 1)[1])
            job = {key: context[key] for key in ("source", "candidate", "concepts")}
            job["prompt"] = request["prompt"]
            try:
                checked = recovery.failure(snapshot, row, job)
                if checked["semantic_errors"]:
                    raise ValueError("Substantive review rejection cannot be split")
            except (ValueError, KeyError, OSError):
                raise previous.previous.critic.CriticTransportStop(error, reference) from error
            halted = False
            raise
        halted = False
        return result

    ModelAdapter.invoke = invoke
    try:
        yield seen, ProbeBoundary
    finally:
        ModelAdapter.invoke = native


def release_retained(snapshot, proof):
    from humanvoice.cli_records import validate_cli_result
    from humanvoice.commands import release_v2_command

    verify_retained(snapshot, proof)
    arguments = SimpleNamespace(snapshot=Path(snapshot), output=None)
    code = release_v2_command.run(arguments)
    reference = getattr(arguments, "_cli_record", None)
    if reference:
        if validate_cli_result(snapshot, reference)["exit_code"] != code:
            raise ValueError("Retained release exit differs from its canonical CLI evidence")
    elif code == 0:
        raise ValueError("Successful retained release lacks canonical CLI evidence")
    return code


def resume(root, *, probe=False):
    root = Path(root).resolve()
    plan = validate_extension(read_json(root / "master-accounting-plan.json"))
    proof, snapshot = plan["technical_restart"], root / "replica"
    if snapshot.exists() or tree_hashes(Path(proof["replica"])) != proof["replica_hashes"]:
        raise ValueError("Review size recovery requires unchanged history and a fresh replica")
    shutil.copytree(proof["replica"], snapshot)
    recovery.install(snapshot)
    stop = None
    with guarded_reviews(snapshot, proof, probe=probe) as (requests, boundary):
        try:
            code = release_retained(snapshot, proof)
        except boundary:
            if not probe or len(requests) != 1:
                raise
            code = 0
        except previous.previous.critic.CriticTransportStop as error:
            code, stop = 1, str(error)
    verify_retained(snapshot, proof)
    write_json(root / "review-size-execution.json", {"status": "pass" if code == 0 else "nonpass", "probe": probe,
        "independent_pid": os.getpid(), "requests": requests, "stop": stop,
        "completed_responses_repeated": False, "retained_assembled_reviews": proof["retained_assembled_reviews"]})
    write_json(root / "execution.json", {"review_size_recovery": VERSION, "exit_code": code})
    return code


def validate_accounted_calls(root, plan, new_calls):
    validate_extension(plan)
    proof = predecessor_evidence(plan["technical_restart"]["predecessor"])
    verify_retained(Path(root) / "replica", proof)
    inherited = set(proof["all_fresh_runtime_ids"])
    if not inherited < set(new_calls):
        raise ValueError("Review size successor lacks inherited receipts or fresh independent work")
    result = writer_repair.NATIVES[0](root, plan, set(new_calls) - inherited)
    activity = read_json(Path(root) / "review-size-execution.json")
    requested = {row["journal"]["request_hash"] for row in result["calls"]}
    if (activity["status"] != "pass" or activity["probe"] or set(activity["requests"]) != requested
            or len(activity["requests"]) != len(requested)
            or requested & {row["request_hash"] for row in proof["completed"]}
            or any(row["journal"]["request"]["purpose"] != "assembled_candidate_verification" for row in result["calls"])):
        raise ValueError("Review size successor lost its exact review-only activity")
    return result


def verify_settlement(output):
    with archive.access():
        if "assembled_size_extension" not in read_json(Path(output) / "plan.json"):
            return SETTLEMENT_READER[0](output)
        with scope.accounting_scope(), pipeline(), scope.verification_only():
            return network.SETTLEMENT_READER[0](output)


@contextmanager
def pipeline(*, planning=(), snapshots=(), authorization=network.budget.authority.AUTHORITY):
    from tools import automatic_reproduction_worker, parallel_verification_replay

    enabled = {(str(Path(snapshot).resolve()), stage) for snapshot, stage in planning}
    scopes = {Path(snapshot).resolve() for snapshot in snapshots}
    with previous.pipeline(planning=planning, snapshots=snapshots, authorization=authorization), recovery.runtime():
        native_plan, native_worker_plan = MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for
        native_command, native_verifier = automatic_reproduction._command, automatic_reproduction.validate_accounted_calls
        native_settlement, native_invoke = parallel_verification_replay.verify_settlement, ModelAdapter.invoke

        def plan_for(snapshot, stage, *arguments, **options):
            parent = options.get("technical_predecessor")
            selected = (str(Path(snapshot).resolve()), stage) in enabled
            continued = parent is not None and Path(parent).resolve() == PRIOR
            proof = predecessor_evidence(parent) if continued else None
            if continued:
                if not selected or stage != "reproduction":
                    raise ValueError("Review size successor requires explicit reproduction scope")
                options.pop("technical_predecessor")
            result = native_plan(snapshot, stage, *arguments, **options)
            if proof:
                parent_plan = read_json(PRIOR / "plan.json")
                if (len(result["calls"]) != proof["remaining_calls"] or result["snapshot"] != proof["snapshot"]
                        or any(result["bindings"][key] != parent_plan["bindings"][key] for key in
                               ("manifest", "source", "policy", "rights", "implementation", "stage", "profile"))):
                    raise ValueError("Review size successor changed its qualified source or allowance")
                result.update(technical_restart=proof, recovery=network.policy(proof["remaining_transport_extras"]))
                result["bindings"]["restart_verifier"] = digest(Path(__file__).read_bytes())
                result["reproduction_timeout_seconds"] = min(86400, 900 * (proof["remaining_calls"]
                    + 2 * proof["remaining_transport_extras"]) + 300)
            if selected:
                result.update(assembled_size_extension=recovery.extension(), review_size_continuation=extension())
                result.pop("plan_identity")
                result["plan_identity"] = digest(result)
            return result

        def command(root, master_accounting=False):
            path = Path(root) / "master-accounting-plan.json"
            if master_accounting and path.exists() and "assembled_size_extension" in read_json(path):
                validate_extension(read_json(path))
                return [sys.executable, "-I", "-B", str(ROOT / "tools/reproduction_review_size_worker.py"), str(Path(root).resolve())]
            return native_command(root, master_accounting)

        def verifier(root, plan, new_calls):
            if plan.get("technical_restart", {}).get("version") == VERSION:
                return validate_accounted_calls(root, plan, new_calls)
            return native_verifier(root, plan, new_calls)

        @wraps(native_invoke)
        def invoke(model, *arguments, **keywords):
            if Path(model.snapshot_dir).resolve() in scopes:
                recovery.install(model.snapshot_dir)
            return native_invoke(model, *arguments, **keywords)

        MANUSCRIPT.plan_for = automatic_reproduction_worker.plan_for = plan_for
        automatic_reproduction._command, ModelAdapter.invoke = command, invoke
        try:
            with network.replaced_aliases(native_verifier, verifier), network.replaced_aliases(native_settlement, verify_settlement):
                yield
        finally:
            MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for = native_plan, native_worker_plan
            automatic_reproduction._command, ModelAdapter.invoke = native_command, native_invoke
