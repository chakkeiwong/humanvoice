"""Resume only uncompleted reviews after immutable response-free failures."""

import fcntl
import sys
from contextlib import ExitStack, contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path

from humanvoice import automatic_reproduction
from humanvoice.artifacts import confined_path, digest, implementation_hash, read_json
from humanvoice.codex_runtime import validate_codex_record
from humanvoice.model import ModelAdapter
from tools import overload_network_runtime as overload
from tools import reproduction_review_size_recovery as previous
from tools.inventory_transport_continuation import canonical_request, immutable, tree_hashes
from tools.math_redline_continuation import require_settled

ROOT, BASE = previous.ROOT, previous.BASE
PRIOR = BASE / "held-out-reproduction-review-size-20261020-01"
EVIDENCE = BASE / "review-overload-recovery-20261021"
DIAGNOSTIC = EVIDENCE / "diagnostic.json"
VERSION = "review-overload-continuation-v1"
FILES = ("tools/overload_network_runtime.py", "tools/reproduction_overload_recovery.py",
         "tools/reproduction_overload_worker.py", "tools/reproduction_overload_runner.py")
MANUSCRIPT, network, scope = previous.MANUSCRIPT, previous.network, previous.scope
archive, size, authority = previous.archive, previous.size, previous.authority
writer_repair, semantic, recovery = previous.writer_repair, previous.semantic, previous.recovery
SETTLEMENT_READER = (previous.verify_settlement,)


def failed_process(plan):
    root = PRIOR / "reproduction"
    request, process = read_json(root / "request.json"), read_json(root / "process.json")
    command = [sys.executable, "-I", "-B", str(ROOT / "tools/reproduction_review_size_worker.py"), str(root)]
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
        raise ValueError("Overload continuation lost its stopped independent process")
    return process


def bounds(remaining_roots, failures, maximum):
    extras = maximum - failures
    if (type(remaining_roots) is not int or remaining_roots < 1
            or type(failures) is not int or failures < 1 or not 1 <= extras <= 16):
        raise ValueError("Overload continuation exhausted its inherited retry allowance")
    return {"remaining_calls": remaining_roots * (1 + recovery.POLICY["maximum_child_calls_per_root"]),
            "remaining_transport_extras": extras, "remaining_roots": remaining_roots}


@contextmanager
def stopped_locks():
    with ExitStack() as locks:
        for name in ("execution.lock", "executor.lock", "reproduction/accounting-worker.lock", "reproduction/executor.lock"):
            handle = locks.enter_context((PRIOR / name).open("rb"))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def diagnose():
    from tools import run_review_size_20261020 as controller
    from tools.automatic_program_account import ACCOUNT

    with stopped_locks():
        before = tree_hashes(PRIOR), ACCOUNT.read_bytes()
        upstream = controller.verify()
        plan = previous.validate_extension(read_json(PRIOR / "plan.json"))
        if (read_json(PRIOR / "execution.json")["status"] != "nonpass"
                or any(read_json(PRIOR / name)["status"] != "stopped" for name in
                       ("executor.json", "reproduction/executor.json"))):
            raise ValueError("Overload continuation requires a stopped predecessor")
        process, usage = failed_process(plan), require_settled(PRIOR, plan, ACCOUNT)
        replica, old = PRIOR / "reproduction/replica", plan["technical_restart"]
        session = previous.verify_retained(replica, old)
        evidence = read_json(PRIOR / "reproduction/master-accounting-calls.json")
        ledger = read_json(PRIOR / "allocation-ledger.json")
        if evidence["plan_identity"] != plan["plan_identity"] or evidence["ledger"] != ledger:
            raise ValueError("Overload predecessor lost native accounting evidence")
        layout = recovery.attempt_layout(PRIOR, plan, ledger["calls"])
        allowed = network.recovery.attempt_calls(plan)
        completed, failures, identifiers, requested = [], [], set(), set()
        for index, entry, row in zip(layout["indices"], ledger["calls"], evidence["calls"], strict=True):
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
                    or call["request"]["purpose"] != "assembled_candidate_verification"
                    or call["request_hash"] in {item["request_hash"] for item in old["completed"]}
                    or call["prompt_hash"] != request["prompt_hash"] or request["profile"] != plan["profile"]
                    or (runtime / "inputs/prompt.txt").read_text() != call["request"]["prompt"]
                    or runtime.name in identifiers or result["status"] != entry["status"]):
                raise ValueError("Overload predecessor allocation differs from actual invocation")
            identifiers.add(runtime.name)
            requested.add(call["request_hash"])
            if entry["status"] == "complete":
                if (record["termination"] != "complete" or call["status"] != "complete"
                        or entry["usage"] != record["input_tokens"] + record["output_tokens"]):
                    raise ValueError("Overload predecessor changed completed usage")
                completed.append({"request_hash": call["request_hash"], "runtime_record": reference,
                                  "purpose": call["request"]["purpose"]})
            else:
                native = overload.NATIVES[0](PRIOR, directory, plan, entry)
                checked = overload.classify(PRIOR, directory, native)
                if (entry["status"] != "incomplete" or entry["usage"] is not None
                        or record["termination"] != "error" or not checked["eligible"]):
                    raise ValueError("Overload predecessor contains a substantive or unproven failure")
                failures.append({"index": index, "request_hash": call["request_hash"],
                                 "classification": checked, "call_hash": digest(call)})
        activity = read_json(PRIOR / "reproduction/review-size-execution.json")
        if (not failures or failures[-1]["classification"]["reason"] != "stream_server_overloaded"
                or ledger["calls"][-1]["status"] != "incomplete" or activity["status"] != "nonpass" or activity["probe"]
                or set(activity["requests"]) != requested or len(activity["requests"]) != len(requested)
                or len(identifiers) != usage["allocated_calls"] or usage["unknown_calls"] != len(failures)):
            raise ValueError("Overload continuation lost its precise interrupted activity")
        fresh = writer_repair.api_ids(replica, validate_local=True) - writer_repair.api_ids(Path(plan["snapshot"]))
        if fresh != set(old["all_fresh_runtime_ids"]) | identifiers:
            raise ValueError("Overload predecessor contains unaccounted runtime attempts")
        _, baseline, candidate, roots, files = previous.jobs_for(replica)
        jobs, _ = recovery.windows(replica, session, baseline, candidate, 180000)
        all_completed = [*old["completed"], *completed]
        hashes = {item["request_hash"] for item in all_completed}
        request_for = lambda job: canonical_request(None, (), {"prompt": job["prompt"],
            "purpose": "assembled_candidate_verification", "response_schema": "critic-response"})
        remaining = [job for job in jobs if digest(request_for(job)) not in hashes]
        last = evidence["calls"][-1]["journal"]
        if (not remaining or request_for(remaining[0]) != last["request"]
                or any(job not in roots for job in remaining)
                or len({item["request_hash"] for item in completed}) != len(completed)
                or any(item["request_hash"] != last["request_hash"] for item in failures)):
            raise ValueError("Overload continuation changed its pending root windows")
        limits = bounds(len(remaining), len(failures), plan["recovery"]["maximum_total"])
        receipt = read_json(replica / last["runtime_record"]["path"])
        failed_at = datetime.fromisoformat(receipt["created_at"])
        if failed_at.tzinfo is None:
            raise ValueError("Overload failure timestamp lacks timezone")
        tree = tree_hashes(replica)
        proof = {"version": VERSION, "predecessor": str(PRIOR), "plan_identity": plan["plan_identity"],
                 "snapshot": plan["snapshot"], "replica": str(replica), "replica_hashes": tree,
                 "retained_files": previous.retained_files(tree), "semantic_scope": old["semantic_scope"],
                 "unit_results": session["results"], "files": files, "all_fresh_runtime_ids": sorted(fresh),
                 "completed": all_completed, "failed_job": old["failed_job"],
                 "first_request_hash": last["request_hash"], "failure_hash": digest(last),
                 "failed_at": failed_at.timestamp(), "failures": failures,
                 "retained_assembled_reviews": len(jobs) - len(remaining), "leaf_windows": len(jobs), **limits}
        if before != (tree_hashes(PRIOR), ACCOUNT.read_bytes()):
            raise ValueError("Overload diagnosis changed evidence or accounting")
        result = {"status": "pass", "version": VERSION, "policy": overload.extension(), "predecessor": proof,
                  "stage_hashes_identity": digest(before[0]), "settlement": usage, "process_hash": digest(process),
                  "upstream_identity": upstream["identity"], "upstream_files": upstream["files"], "model_calls": 0}
        result["identity"] = digest(result)
        immutable(DIAGNOSTIC, result)
        return result


def report():
    value = read_json(DIAGNOSTIC)
    if (value["identity"] != digest({key: item for key, item in value.items() if key != "identity"})
            or value["policy"] != overload.extension() or value["status"] != "pass"
            or any(digest((ROOT / name).read_bytes()) != expected for name, expected in value["upstream_files"].items())):
        raise ValueError("Overload diagnosis or frozen predecessor changed")
    return value


def predecessor_evidence(output=PRIOR):
    from tools.automatic_program_account import ACCOUNT

    if Path(output).resolve() != PRIOR:
        raise ValueError("Overload continuation cannot replenish a different predecessor")
    value = report()
    with stopped_locks():
        plan = previous.validate_extension(read_json(PRIOR / "plan.json"))
        if (digest(tree_hashes(PRIOR)) != value["stage_hashes_identity"]
                or require_settled(PRIOR, plan, ACCOUNT) != value["settlement"]):
            raise ValueError("Overload predecessor changed after diagnosis")
    return value["predecessor"]


def extension():
    return {"version": VERSION, "diagnostic_identity": report()["identity"],
            "files": {name: digest((ROOT / name).read_bytes()) for name in FILES}}


def validate_extension(plan):
    previous.validate_extension(plan)
    if plan.get("overload_network_extension") != overload.extension() or plan.get("overload_continuation") != extension():
        raise ValueError("Overload continuation implementation changed")
    proof = plan.get("technical_restart", {})
    if proof.get("version") == VERSION and (proof != report()["predecessor"]
            or len(plan["calls"]) != proof["remaining_calls"]
            or plan["recovery"] != network.policy(proof["remaining_transport_extras"])):
        raise ValueError("Overload continuation changed retained work or replenished retries")
    return plan


@contextmanager
def interrupted_request(proof):
    native, started = ModelAdapter.invoke, False

    @wraps(native)
    def invoke(model, *arguments, **keywords):
        nonlocal started
        request = canonical_request(model, arguments, keywords)
        if not started and digest(request) != proof["first_request_hash"]:
            raise ValueError("Overload continuation must resume its exact interrupted request")
        started = True
        return native(model, *arguments, **keywords)

    ModelAdapter.invoke = invoke
    try:
        yield
    finally:
        ModelAdapter.invoke = native


def resume(root, *, probe=False):
    root = Path(root).resolve()
    plan = validate_extension(read_json(root / "master-accounting-plan.json"))
    proof = predecessor_evidence(plan["technical_restart"]["predecessor"])
    if not probe:
        network.wait_until(root / "initial-retry-wait.json", proof["failure_hash"], proof["failed_at"])
    with interrupted_request(proof):
        return previous.resume(root, probe=probe)


def validate_accounted_calls(root, plan, new_calls):
    validate_extension(plan)
    proof = predecessor_evidence(plan["technical_restart"]["predecessor"])
    previous.verify_retained(Path(root) / "replica", proof)
    inherited = set(proof["all_fresh_runtime_ids"])
    if not inherited < set(new_calls):
        raise ValueError("Overload successor lacks inherited receipts or fresh independent work")
    result = writer_repair.NATIVES[0](root, plan, set(new_calls) - inherited)
    activity = read_json(Path(root) / "review-size-execution.json")
    requested = {row["journal"]["request_hash"] for row in result["calls"]}
    if (activity["status"] != "pass" or activity["probe"] or set(activity["requests"]) != requested
            or len(activity["requests"]) != len(requested) or activity["requests"][0] != proof["first_request_hash"]
            or requested & {row["request_hash"] for row in proof["completed"]}
            or any(row["journal"]["request"]["purpose"] != "assembled_candidate_verification" for row in result["calls"])):
        raise ValueError("Overload successor lost its exact review-only activity")
    return result


def verify_settlement(output):
    with archive.access():
        if "overload_network_extension" not in read_json(Path(output) / "plan.json"):
            return SETTLEMENT_READER[0](output)
        with scope.accounting_scope(), pipeline(), scope.verification_only():
            return network.SETTLEMENT_READER[0](output)


@contextmanager
def pipeline(*, planning=(), snapshots=(), authorization=network.budget.authority.AUTHORITY):
    from tools import automatic_reproduction_worker, parallel_verification_replay

    enabled = {(str(Path(snapshot).resolve()), stage) for snapshot, stage in planning}
    with previous.pipeline(planning=planning, snapshots=snapshots, authorization=authorization), overload.runtime():
        native_plan, native_worker_plan = MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for
        native_command, native_verifier = automatic_reproduction._command, automatic_reproduction.validate_accounted_calls
        native_settlement = parallel_verification_replay.verify_settlement

        def plan_for(snapshot, stage, *arguments, **options):
            parent = options.get("technical_predecessor")
            selected = (str(Path(snapshot).resolve()), stage) in enabled
            continued = parent is not None and Path(parent).resolve() == PRIOR
            proof = predecessor_evidence(parent) if continued else None
            if continued:
                if not selected or stage != "reproduction":
                    raise ValueError("Overload successor requires explicit reproduction scope")
                options.pop("technical_predecessor")
            result = native_plan(snapshot, stage, *arguments, **options)
            if proof:
                parent_plan = read_json(PRIOR / "plan.json")
                if (len(result["calls"]) != proof["remaining_calls"] or result["snapshot"] != proof["snapshot"]
                        or any(result["bindings"][key] != parent_plan["bindings"][key] for key in
                               ("manifest", "source", "policy", "rights", "implementation", "stage", "profile"))):
                    raise ValueError("Overload successor changed its qualified source or allowance")
                result.update(technical_restart=proof, recovery=network.policy(proof["remaining_transport_extras"]))
                result["bindings"]["restart_verifier"] = digest(Path(__file__).read_bytes())
                result["reproduction_timeout_seconds"] = min(86400, 900 * (proof["remaining_calls"]
                    + 2 * proof["remaining_transport_extras"]) + 300)
            if selected:
                result.update(overload_network_extension=overload.extension(), overload_continuation=extension())
                result.pop("plan_identity")
                result["plan_identity"] = digest(result)
            return result

        def command(root, master_accounting=False):
            path = Path(root) / "master-accounting-plan.json"
            if master_accounting and path.exists() and "overload_network_extension" in read_json(path):
                validate_extension(read_json(path))
                return [sys.executable, "-I", "-B", str(ROOT / "tools/reproduction_overload_worker.py"), str(Path(root).resolve())]
            return native_command(root, master_accounting)

        def verifier(root, plan, new_calls):
            if plan.get("technical_restart", {}).get("version") == VERSION:
                return validate_accounted_calls(root, plan, new_calls)
            return native_verifier(root, plan, new_calls)

        MANUSCRIPT.plan_for = automatic_reproduction_worker.plan_for = plan_for
        automatic_reproduction._command = command
        try:
            with network.replaced_aliases(native_verifier, verifier), network.replaced_aliases(native_settlement, verify_settlement):
                yield
        finally:
            MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for = native_plan, native_worker_plan
            automatic_reproduction._command = native_command
