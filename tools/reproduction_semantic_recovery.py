"""Repair settled reproduction rejections without repurchasing accepted work."""

import fcntl
import json
import os
import shutil
import sys
from contextlib import ExitStack, contextmanager
from functools import wraps
from pathlib import Path

from humanvoice import artifacts, automatic_reproduction, rewrite_engine
from humanvoice.artifacts import digest, implementation_hash, read_json, write_json
from humanvoice.model import ModelAdapter
from tools import review_request_recovery as previous
from tools import semantic_repair_protocol as semantic
from tools import settled_semantic_batch_repair as batch
from tools import writer_size_accounting as sizing
from tools.inventory_transport_continuation import canonical_request, immutable, tree_hashes
from tools.math_redline_continuation import require_settled

ROOT, BASE = previous.ROOT, previous.BASE
PRIOR = BASE / "held-out-reproduction-review-request-20261020-01"
EVIDENCE = BASE / "reproduction-semantic-recovery-20261020"
DIAGNOSTIC = EVIDENCE / "diagnostic.json"
VERSION = "reproduction-semantic-recovery-v1"
POLICY = {"repair_cycles": 1, "writer_revisions_per_rejected_unit": 1,
          "new_critics_per_changed_unit": 1, "accepted_units_changed": False,
          "completed_responses_repeated": False, "unknown_tokens_released": False,
          "maximum_split_children_per_root": 14, "network_retry_seconds": 900}
FILES = ("tools/reproduction_semantic_recovery.py", "tools/reproduction_semantic_worker.py",
         "tools/reproduction_semantic_runner.py", "tools/semantic_repair_protocol.py",
         "tools/settled_semantic_batch_repair.py")
MANUSCRIPT, network, scope = previous.MANUSCRIPT, previous.network, previous.scope
archive, authority = previous.previous.archive, previous.authority
size = previous.previous.previous
writer_repair = size.previous.repair
SETTLEMENT_READER = (previous.verify_settlement,)


def bounds(parent, review_scope, usage):
    reviewed, rejected = len(review_scope["units"]), len(review_scope["rejected"])
    completed = usage["allocated_calls"] - usage["unknown_calls"]
    remaining = len(parent["calls"]) - reviewed
    extras = parent["recovery"]["maximum_total"] - usage["unknown_calls"]
    if completed != reviewed or not 0 < rejected <= reviewed or remaining < 0 or extras < 0:
        raise ValueError("Semantic repair lost complete reviews or its finite allowance")
    logical = remaining + 2 * rejected
    return {"remaining_logical_calls": logical, "remaining_calls": logical + 14 * rejected,
            "remaining_transport_extras": extras, "assembled_calls": remaining}


def failed_process(plan):
    root = PRIOR / "reproduction"
    request, process = read_json(root / "request.json"), read_json(root / "process.json")
    command = [sys.executable, "-I", "-B", str(ROOT / "tools/review_request_worker.py"), str(root)]
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
        raise ValueError("Semantic recovery lost its stopped independent process")
    execution = read_json(root / "review-request-execution.json")
    if execution["status"] != "nonpass" or execution["stop"] is not None or execution["failure"] is not None:
        raise ValueError("Semantic recovery cannot conceal an unresolved invocation")
    return process


def diagnose():
    from tools import run_review_request_program_20261020 as controller
    from tools.automatic_program_account import ACCOUNT

    before = tree_hashes(PRIOR), ACCOUNT.read_bytes()
    upstream = controller.verify()
    plan = previous.validate_extension(read_json(PRIOR / "plan.json"))
    if (read_json(PRIOR / "execution.json")["status"] != "nonpass"
            or any(read_json(PRIOR / name)["status"] != "stopped" for name in
                   ("executor.json", "reproduction/executor.json"))):
        raise ValueError("Semantic recovery requires stopped, settled execution")
    process = failed_process(plan)
    usage = require_settled(PRIOR, plan, ACCOUNT)
    replica = PRIOR / "reproduction/replica"
    original = plan["technical_restart"]
    previous.verify_history(replica, original)
    fresh = writer_repair.api_ids(replica, validate_local=True) - writer_repair.api_ids(Path(plan["snapshot"]))
    calls = previous.validate_accounted_calls(PRIOR / "reproduction", plan, fresh)["calls"]
    review_scope = semantic.scope_for(replica)
    completed = [row["journal"] for row in calls if row["result"]["status"] == "complete"]
    if (len(review_scope["units"]) != 14 or set(review_scope["rejected"]) != {"unit-003", "unit-013"}
            or {row["request_hash"] for row in completed} != set(review_scope["completed_critic_requests"])
            or len(completed) != len(review_scope["completed_critic_requests"])
            or any(row["journal"]["request"]["purpose"] != "independent_rewrite_verification" for row in calls)
            or usage["unknown_calls"] != 4 or usage["retained_tokens"] - usage["reported_tokens"] != 2176000):
        raise ValueError("Semantic recovery changed completed reviews or retained network charges")
    limits = bounds(plan, review_scope, usage)
    proof = {"version": VERSION, "predecessor": str(PRIOR), "plan_identity": plan["plan_identity"],
             "snapshot": plan["snapshot"], "replica": str(replica), "replica_hashes": tree_hashes(replica),
             "scope": review_scope, "all_fresh_runtime_ids": sorted(fresh), "policy": POLICY,
             "completed": [*original["completed"], *[{"request_hash": row["request_hash"],
                 "runtime_record": row["runtime_record"]} for row in completed]], **limits}
    if before != (tree_hashes(PRIOR), ACCOUNT.read_bytes()):
        raise ValueError("Semantic diagnosis changed evidence or accounting")
    result = {"status": "pass", "version": VERSION, "policy": POLICY, "predecessor": proof,
              "stage_hashes_identity": digest(before[0]), "settlement": usage, "process_hash": digest(process),
              "upstream_identity": upstream["identity"], "upstream_files": upstream["files"], "model_calls": 0}
    result["identity"] = digest(result)
    immutable(DIAGNOSTIC, result)
    return result


def report():
    value = read_json(DIAGNOSTIC)
    if (value["identity"] != digest({key: item for key, item in value.items() if key != "identity"})
            or value["policy"] != POLICY or value["status"] != "pass"
            or any(digest((ROOT / name).read_bytes()) != expected for name, expected in value["upstream_files"].items())):
        raise ValueError("Semantic diagnosis or its frozen predecessor changed")
    return value


def predecessor_evidence(output=PRIOR):
    from tools.automatic_program_account import ACCOUNT

    if Path(output).resolve() != PRIOR:
        raise ValueError("A semantic repair cycle cannot be replenished")
    value = report()
    with ExitStack() as locks:
        for name in ("execution.lock", "executor.lock", "reproduction/accounting-worker.lock", "reproduction/executor.lock"):
            handle = locks.enter_context((PRIOR / name).open("rb"))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = previous.validate_extension(read_json(PRIOR / "plan.json"))
        if (digest(tree_hashes(PRIOR)) != value["stage_hashes_identity"]
                or require_settled(PRIOR, plan, ACCOUNT) != value["settlement"]):
            raise ValueError("Semantic predecessor changed after diagnosis")
    return value["predecessor"]


def extension():
    return {"version": VERSION, "policy": POLICY, "diagnostic_identity": report()["identity"],
            "files": {name: digest((ROOT / name).read_bytes()) for name in FILES}}


def validate_extension(plan):
    previous.validate_extension(plan)
    if plan.get("reproduction_semantic_extension") != extension():
        raise ValueError("Semantic recovery implementation changed")
    proof = plan.get("technical_restart", {})
    if proof.get("version") == VERSION and (proof != report()["predecessor"]
            or len(plan["calls"]) != proof["remaining_calls"]
            or plan["recovery"] != network.policy(proof["remaining_transport_extras"])):
        raise ValueError("Semantic recovery changed rejected work or replenished retries")
    return plan


@contextmanager
def guarded_repairs(snapshot, proof, *, probe=False):
    native = ModelAdapter.invoke
    review_scope = proof["scope"]
    seen, writers, critics = [], set(), set()
    children = {unit: 0 for unit in review_scope["rejected"]}
    old = {row["request_hash"] for row in proof["completed"]}
    halted = False

    class ProbeBoundary(KeyboardInterrupt):
        pass

    @wraps(native)
    def invoke(model, *arguments, **keywords):
        nonlocal halted
        if halted:
            raise previous.critic.CriticTransportStop(RuntimeError("Semantic workflow already stopped"), None)
        halted = True
        request = canonical_request(model, arguments, keywords)
        semantic.retained_bytes(snapshot, review_scope)
        identity = digest(request)
        if Path(model.snapshot_dir).resolve() != Path(snapshot).resolve() or identity in old or identity in seen:
            raise ValueError("Semantic recovery cannot repeat completed work or change its snapshot")
        if request["purpose"] == "source_grounded_rewrite":
            token = sizing.marker(request)
            if token:
                unit = token["root_unit"]
                if unit not in writers or children[unit] >= POLICY["maximum_split_children_per_root"]:
                    raise ValueError("Split child is outside its submitted rejected root")
                sizing.verify_child(snapshot, request)
                children[unit] += 1
            else:
                context = json.loads(request["prompt"].split("CONTEXT_JSON:\n", 1)[1])
                unit = context["unit_id"]
                if unit in writers or request != review_scope["rejected"].get(unit, {}).get("request"):
                    raise ValueError("Repair writer differs from its single feedback-directed request")
                writers.add(unit)
        elif request["purpose"] == "independent_rewrite_verification":
            context = json.loads(request["prompt"].split("REVIEW_DATA:\n", 1)[1])
            matches = [unit for unit in review_scope["rejected"] if all(
                context[key] == review_scope["units"][unit]["context"][key] for key in ("source", "concepts", "brief"))]
            if len(matches) != 1 or matches[0] not in writers or matches[0] in critics:
                raise ValueError("Repair review requires one changed rejected unit")
            unit = matches[0]
            result = artifacts.load_unit_result(Path(snapshot), artifacts.load_session(Path(snapshot)), unit)
            if (request != semantic.unit_requests(snapshot)[unit] or context["candidate"] != result["output_latex"]
                    or result["output_hash"] == review_scope["units"][unit]["output_hash"]):
                raise ValueError("An unchanged rejection cannot be reviewed again")
            critics.add(unit)
        elif (request["purpose"] != "assembled_candidate_verification" or critics != set(review_scope["rejected"])
                or request not in semantic.assembled_requests(snapshot)):
            raise ValueError("Semantic repair left its declared scope")
        seen.append(identity)
        if probe:
            raise ProbeBoundary()
        halted = False
        try:
            return native(model, *arguments, **keywords)
        except (ValueError, RuntimeError, OSError) as error:
            if request["purpose"] == "source_grounded_rewrite":
                raise
            halted = True
            reference = getattr(error, "runtime_record", None) or getattr(model, "last_runtime_record", None)
            raise previous.critic.CriticTransportStop(error, reference) from error

    ModelAdapter.invoke = invoke
    try:
        yield {"requests": seen, "writers": writers, "critics": critics}, ProbeBoundary
    finally:
        ModelAdapter.invoke = native


@contextmanager
def fail_fast_writers():
    native = rewrite_engine.rewrite_unit

    def rewrite(*arguments, **keywords):
        result = native(*arguments, **keywords)
        if not result.is_acceptable:
            raise previous.critic.CriticTransportStop(RuntimeError(
                "Directed writer failed: " + "; ".join(result.rejection_reasons)), None)
        return result

    rewrite_engine.rewrite_unit = rewrite
    try:
        yield
    finally:
        rewrite_engine.rewrite_unit = native


def failure_summary(output):
    provider = previous.failure_summary(output)
    if provider:
        return provider
    snapshot = Path(output) / "reproduction/replica"
    summary = snapshot / ".humanvoice/preflight/summary.json"
    if not summary.exists():
        return None
    rows = []
    for unit in read_json(summary).get("blocked_units", []):
        review = read_json(snapshot / ".humanvoice/preflight" / (unit + ".json"))
        verdict = (review.get("critic_record") or {}).get("verdict", {})
        rows.append({"unit_id": unit, "failure_stage": review.get("failure_stage"),
                     "unsupported_additions": [item[:1000] for item in verdict.get("unsupported_additions", [])[:3]]})
    return {"reason": "unit_review_rejections", "units": rows} if rows else None


def resume(root, *, probe=False):
    root = Path(root).resolve()
    plan = validate_extension(read_json(root / "master-accounting-plan.json"))
    proof, snapshot = plan["technical_restart"], root / "replica"
    if snapshot.exists() or tree_hashes(Path(proof["replica"])) != proof["replica_hashes"]:
        raise ValueError("Semantic recovery requires unchanged history and a fresh replica")
    shutil.copytree(proof["replica"], snapshot)
    stop = None
    with size.sized_writers(snapshot), fail_fast_writers(), guarded_repairs(snapshot, proof, probe=probe) as (activity, boundary):
        try:
            code = batch.run_consumer(root, snapshot, proof["scope"])
        except boundary:
            if not probe or len(activity["requests"]) != 1:
                raise
            code = 0
        except previous.critic.CriticTransportStop as error:
            code, stop = 1, str(error)
    semantic.retained_bytes(snapshot, proof["scope"], complete=code == 0 and not probe)
    detail = None if probe else failure_summary(root.parent)
    write_json(root / "semantic-repair-execution.json", {"status": "pass" if code == 0 else "nonpass", "probe": probe,
        "independent_pid": os.getpid(), "requests": activity["requests"], "writers": sorted(activity["writers"]),
        "critics": sorted(activity["critics"]), "stop": stop, "failure": detail, "completed_responses_repeated": False})
    write_json(root / "execution.json", {"semantic_repair_recovery": VERSION, "exit_code": code, "failure": detail})
    return code


def validate_accounted_calls(root, plan, new_calls):
    validate_extension(plan)
    proof = predecessor_evidence(plan["technical_restart"]["predecessor"])
    semantic.retained_bytes(Path(root) / "replica", proof["scope"], complete=True)
    inherited = set(proof["all_fresh_runtime_ids"])
    if not inherited < set(new_calls):
        raise ValueError("Semantic successor lost retained receipts or new independent work")
    result = writer_repair.NATIVES[0](root, plan, set(new_calls) - inherited)
    activity = read_json(Path(root) / "semantic-repair-execution.json")
    requested = {row["journal"]["request_hash"] for row in result["calls"]}
    expected = set(proof["scope"]["rejected"])
    if (activity["status"] != "pass" or activity["probe"] or set(activity["writers"]) != expected
            or set(activity["critics"]) != expected or set(activity["requests"]) != requested
            or len(activity["requests"]) != len(requested)
            or set(activity["requests"]) & {row["request_hash"] for row in proof["completed"]}):
        raise ValueError("Semantic successor lost its bounded repair activity")
    return result


def verify_settlement(output):
    with archive.access():
        if "reproduction_semantic_extension" not in read_json(Path(output) / "plan.json"):
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
                    raise ValueError("Semantic successor requires an explicitly scoped reproduction")
                options.pop("technical_predecessor")
            result = native_plan(snapshot, stage, *arguments, **options)
            if proof:
                parent_plan = read_json(PRIOR / "plan.json")
                if (len(result["calls"]) != proof["remaining_calls"] or result["snapshot"] != proof["snapshot"]
                        or any(result["bindings"][key] != parent_plan["bindings"][key] for key in
                               ("manifest", "source", "policy", "rights", "implementation", "stage", "profile"))):
                    raise ValueError("Semantic successor changed its qualified source or allowance")
                result.update(technical_restart=proof, recovery=network.policy(proof["remaining_transport_extras"]))
                result["bindings"]["restart_verifier"] = digest(Path(__file__).read_bytes())
                result["reproduction_timeout_seconds"] = min(86400, 900 * (proof["remaining_calls"]
                    + 2 * proof["remaining_transport_extras"]) + 300)
            if selected:
                result["reproduction_semantic_extension"] = extension()
                result.pop("plan_identity")
                result["plan_identity"] = digest(result)
            return result

        def command(root, master_accounting=False):
            path = Path(root) / "master-accounting-plan.json"
            if master_accounting and path.exists() and "reproduction_semantic_extension" in read_json(path):
                validate_extension(read_json(path))
                return [sys.executable, "-I", "-B", str(ROOT / "tools/reproduction_semantic_worker.py"), str(Path(root).resolve())]
            return native_command(root, master_accounting)

        def verifier(root, plan, new_calls):
            if plan.get("technical_restart", {}).get("version") == VERSION:
                return validate_accounted_calls(root, plan, new_calls)
            return native_verifier(root, plan, new_calls)

        def observations(root, *arguments, **keywords):
            try:
                return native_observations(root, *arguments, **keywords)
            except ValueError as error:
                if str(error) != "Reproduction lacks current independent process execution evidence":
                    raise
                detail = failure_summary(Path(root).parent)
                if not detail:
                    raise
                raise ValueError("Reproduction blocked: " + json.dumps(detail, ensure_ascii=False)) from error

        MANUSCRIPT.plan_for = automatic_reproduction_worker.plan_for = plan_for
        automatic_reproduction._command, automatic_reproduction._observations = command, observations
        try:
            with network.replaced_aliases(native_verifier, verifier), network.replaced_aliases(native_settlement, verify_settlement):
                yield
        finally:
            MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for = native_plan, native_worker_plan
            automatic_reproduction._command, automatic_reproduction._observations = native_command, native_observations
