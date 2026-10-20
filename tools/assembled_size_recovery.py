"""Partition oversized reviews without changing candidates or accepting failed calls."""

import json
import math
import sys
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from pathlib import Path

from humanvoice import assembled_review, automatic_recovery
from humanvoice.artifacts import confined_path, digest, read_json
from humanvoice.codex_runtime import validate_codex_record
from humanvoice.preflight_verification import review_errors, validate_review_evidence
from humanvoice.response_schemas import parse_response
from tools import assembled_budget_runtime as budget
from tools import writer_size_accounting as accounting
from tools.inventory_transport_continuation import canonical_request, immutable

ROOT = Path(__file__).resolve().parents[1]
VERSION = "assembled-size-recovery-v1"
MARKER = ".humanvoice/assembled-size-recovery.json"
DIRECTORY = ".humanvoice/assembled-size-recovery"
ERROR = "Reported token usage exceeds its operational acceptance limit"
POLICY = {"input_limit": 80000, "output_limit": 32000, "maximum_split_depth": 3,
          "maximum_child_calls_per_root": 14, "candidate_changed": False,
          "source_context_changed": False, "semantic_rerolls": False,
          "completed_requests_repeated": False, "unknown_tokens_released": False,
          "aggregate_allowance_changed": False}
NATIVES = (assembled_review.assembled_windows, budget.require_review, accounting.attempt_layout)
ACTIVE = ContextVar("assembled_size_recovery_active", default=False)
CREATE = ContextVar("assembled_size_recovery_create", default=False)


def extension():
    return {"version": VERSION, "policy": POLICY,
            "files": {"tools/assembled_size_recovery.py": digest(Path(__file__).read_bytes())}}


def install(snapshot):
    immutable(Path(snapshot) / MARKER, extension())


def enabled(snapshot):
    path = Path(snapshot) / MARKER
    if not path.exists():
        return False
    if path.is_symlink() or read_json(path) != extension():
        raise ValueError("Assembled size recovery implementation or policy changed")
    return True


def classify(request, response, process, semantic_errors):
    actual_input, actual_output = response.get("input_tokens"), response.get("output_tokens")
    input_limit = request.get("assembled_input_budget", {}).get("authorized_input_limit",
                        request["profile"]["budget"]["max_input_tokens_per_unit"])
    output_limit, reservation = request["output_acceptance_limit"], request["reservation_tokens"]
    elapsed, deadline = process.get("elapsed_seconds"), process.get("deadline_seconds")
    if (request.get("purpose") != "assembled_candidate_verification"
            or request.get("response_schema") != "critic-response"
            or response.get("status") != "error" or response.get("failure_kind") != "invocation"
            or response.get("error") != ERROR or response.get("usage_status") != "reported"
            or not isinstance(response.get("text"), str) or not response["text"].strip()
            or not isinstance(response.get("thread_id"), str) or not response["thread_id"]
            or any(type(value) is not int or value <= 0 for value in
                   (actual_input, actual_output, input_limit, output_limit, reservation))
            or input_limit != POLICY["input_limit"] or output_limit != POLICY["output_limit"]
            or (actual_input <= input_limit and actual_output <= output_limit)
            or actual_input + actual_output > reservation
            or process.get("status") != "complete" or type(process.get("returncode")) is not int
            or process["returncode"] != 0 or process.get("process_started") is not True
            or type(elapsed) not in (int, float) or not math.isfinite(elapsed)
            or type(deadline) is not int or deadline != request.get("timeout_seconds")
            or not 0 <= elapsed < deadline):
        raise ValueError("Failure is not solely a completed assembled size breach")
    return {"version": VERSION, "reason": "assembled_review_size_breach",
            "input_tokens": actual_input, "input_limit": input_limit,
            "output_tokens": actual_output, "output_limit": output_limit,
            "semantic_check": "fail" if semantic_errors else "pass", "semantic_errors": semantic_errors,
            "transport_retry_eligible": False, "original_response_admitted": False,
            "completed_request_may_be_repeated": False, "unknown_tokens_released": False,
            "model_calls": 0}


def failure(snapshot, call, job):
    reference = call.get("runtime_record")
    if not reference or call.get("status") == "complete":
        raise ValueError("Size recovery requires the exact failed native call")
    receipt = validate_codex_record(snapshot, reference)
    directory = confined_path(snapshot, reference["path"]).parent
    request, response, process = (read_json(directory / name) for name in
        ("inputs/api-request.json", "response.json", "process.json"))
    if (receipt["termination"] != "error" or request["prompt_hash"] != digest(job["prompt"])
            or (directory / "inputs/prompt.txt").read_text() != job["prompt"]
            or call.get("prompt_hash") != digest(job["prompt"])
            or (call.get("raw_response") or call.get("response_text")) != response["text"]):
        raise ValueError("Review size failure differs from its retained native evidence")
    verdict = parse_response(response["text"], "critic-response")
    validate_review_evidence(verdict, job["concepts"], job["candidate"])
    result = classify(request, response, process, review_errors(verdict, job["concepts"], job["candidate"]))
    result.update(runtime_record=reference, prompt_hash=request["prompt_hash"],
                  response_sha256=digest(response["text"]), call_sha256=digest(call))
    return result


def partition(job, root_hash, depth):
    concepts = job["concepts"]
    if not 0 <= depth < POLICY["maximum_split_depth"] or len(concepts) < 2:
        raise ValueError("Assembled size recovery reached an indivisible review or its depth limit")
    identifiers = [row["concept_id"] for row in concepts]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Assembled size partition has duplicate concepts")
    middle = len(concepts) // 2
    children = []
    context = json.loads(job["prompt"].split("REVIEW_DATA:\n", 1)[1])
    prefix = job["prompt"].split("Entry point: ", 1)[1].split("\n", 1)[0]
    for number, selected in enumerate((concepts[:middle], concepts[middle:])):
        scope = (job["scope"] + f"; size partition {number}, depth {depth + 1}, "
                 f"root {root_hash}, parent {digest(job['prompt'])}")
        prompt = assembled_review.assembled_prompt(job["source"], job["candidate"], selected,
                    context["brief"], prefix, scope)
        children.append(dict(job, concepts=selected, scope=scope, prompt=prompt))
    if ([row["concept_id"] for child in children for row in child["concepts"]] != identifiers
            or any(child[key] != job[key] for child in children for key in ("source", "candidate"))):
        raise ValueError("Assembled size partition lost content or changed relationship context")
    return children


def split_path(snapshot, job):
    return Path(snapshot) / DIRECTORY / "splits" / (digest(job["prompt"]) + ".json")


def failed_calls(snapshot, job):
    matches = []
    for path in Path(snapshot).glob(".humanvoice/preflight/assembled/*.json"):
        call = read_json(path)
        if call.get("prompt_hash") == digest(job["prompt"]) and call.get("runtime_record"):
            if call.get("status") != "complete" and (call.get("raw_response") or call.get("response_text")):
                matches.append((path, call))
    if len(matches) > 1:
        raise ValueError("A completed assembled response was purchased more than once")
    return matches


def leaves(snapshot, job, *, root_hash=None, depth=0):
    root_hash = root_hash or digest(job["prompt"])
    path = split_path(snapshot, job)
    matches = failed_calls(snapshot, job)
    if not path.exists() and not matches:
        return [job]
    if len(matches) != 1:
        raise ValueError("Review partition lost its exact failed parent call")
    call_path, call = matches[0]
    checked = failure(snapshot, call, job)
    if checked["semantic_errors"]:
        raise ValueError("A substantive assembled rejection cannot be split or rerolled")
    children = partition(job, root_hash, depth)
    proof = {"version": VERSION, "root_prompt_hash": root_hash, "depth": depth,
             "parent": job, "failure": checked, "children": children,
             "call_path": str(call_path.relative_to(snapshot))}
    if path.exists():
        if path.is_symlink() or read_json(path) != proof:
            raise ValueError("Assembled review partition or failed parent changed")
    elif CREATE.get():
        immutable(path, proof)
    else:
        raise ValueError("Assembled review partition is missing; verification cannot create recovery")
    result = [leaf for child in children for leaf in leaves(snapshot, child, root_hash=root_hash, depth=depth + 1)]
    if len(result) > 2 ** POLICY["maximum_split_depth"]:
        raise ValueError("Assembled review leaf allowance exceeded")
    return result


def windows(snapshot, session, baseline, candidate, limit):
    jobs, files = NATIVES[0](snapshot, session, baseline, candidate, limit)
    if not enabled(snapshot):
        return jobs, files
    return [leaf for job in jobs for leaf in leaves(snapshot, job)], files


def require_review(snapshot, session, baseline, candidate, *, allow_calls=True):
    if not enabled(snapshot):
        return NATIVES[1](snapshot, session, baseline, candidate, allow_calls=allow_calls)
    token = CREATE.set(allow_calls)
    try:
        while True:
            try:
                result = NATIVES[1](snapshot, session, baseline, candidate, allow_calls=allow_calls)
                roots, _ = NATIVES[0](snapshot, session, baseline, candidate, 60000 * 3)
                result["size_recovery"] = {"version": VERSION, "root_windows": len(roots),
                    "leaf_windows": len(result["windows"]), "policy": POLICY,
                    "partitions": {str(path.relative_to(snapshot)): digest(path.read_bytes())
                                   for path in sorted((Path(snapshot) / DIRECTORY / "splits").glob("*.json"))}}
                return result
            except (RuntimeError, ValueError):
                if not allow_calls:
                    raise
                before = {str(path) for path in (Path(snapshot) / DIRECTORY / "splits").glob("*.json")}
                windows(snapshot, session, baseline, candidate, 60000 * 3)
                after = {str(path) for path in (Path(snapshot) / DIRECTORY / "splits").glob("*.json")}
                if after == before:
                    raise
    finally:
        CREATE.reset(token)


def child_token(snapshot, request):
    if request.get("purpose") != "assembled_candidate_verification":
        return None
    matches = []
    for path in (Path(snapshot) / DIRECTORY / "splits").glob("*.json"):
        proof = read_json(path)
        expected = partition(proof["parent"], proof["root_prompt_hash"], proof["depth"])
        call = read_json(confined_path(snapshot, proof["call_path"]))
        if (proof["version"] != VERSION or proof["children"] != expected
                or proof["failure"] != failure(snapshot, call, proof["parent"])
                or proof["failure"]["semantic_errors"]):
            raise ValueError("Assembled split child lost its exact native parent or partition")
        for child in expected:
            if canonical_request(None, (), {"prompt": child["prompt"], "purpose": "assembled_candidate_verification",
                    "response_schema": "critic-response"}) == request:
                matches.append({"root": proof["root_prompt_hash"], "parent_prompt_hash": digest(proof["parent"]["prompt"]),
                                "depth": proof["depth"] + 1})
    if len(matches) > 1:
        raise ValueError("Assembled split child has ambiguous parentage")
    return matches[0] if matches else None


def size_attempt(snapshot, row):
    if row["request"].get("purpose") == "source_grounded_rewrite":
        from types import SimpleNamespace
        return accounting.splitting.size_failure(snapshot,
            SimpleNamespace(is_acceptable=False, runtime_record=row.get("runtime_record")))
    if row["request"].get("purpose") != "assembled_candidate_verification":
        return None
    prompt = row["request"]["prompt"]
    context = json.loads(prompt.split("REVIEW_DATA:\n", 1)[1])
    job = {key: context[key] for key in ("source", "candidate", "concepts")}
    job["prompt"] = prompt
    try:
        result = failure(snapshot, row, job)
    except ValueError:
        return None
    return result if not result["semantic_errors"] else None


def attempt_layout(root, plan, entries, **keywords):
    if "assembled_size_extension" not in plan:
        return NATIVES[2](root, plan, entries, **keywords)
    if plan["assembled_size_extension"] != extension():
        raise ValueError("Assembled size accounting extension changed")
    accounting.runtime.validate_extension(plan["writer_size_extension"])
    accounting.network.validate_extension(plan)
    root = Path(root)
    snapshot = Path(keywords.get("runtime_snapshot") or plan.get("execution_snapshot", plan["snapshot"]))
    raw = keywords.get("raw")

    def journal(index):
        relative = f"calls/{index:04d}/call.json"
        return json.loads(raw(relative)) if raw else read_json(root / relative)

    allowed = automatic_recovery.attempt_calls(plan)
    by_key = {call["key"]: index for index, call in enumerate(allowed)}
    indices, selected, failures, requests = [], {}, [], set()
    base_count, network_count, children = 0, 0, {}
    if len(entries) > automatic_recovery.call_limit(plan) or len({row["key"] for row in entries}) != len(entries):
        raise ValueError("Review size recovery exceeded frozen allocation membership")
    for position, entry in enumerate(entries):
        index = by_key.get(entry["key"])
        if index is None or entry["input_hash"] != allowed[index]["input_hash"]:
            raise ValueError("Unplanned review size allocation")
        logical = index % len(plan["calls"])
        row = read_json(root / f"size-intents/{index:04d}.json") if entry["status"] == "allocated_unknown" else journal(index)
        request = row["request"]
        if index >= len(plan["calls"]):
            if not indices or indices[-1] != index - len(plan["calls"]) or entries[position - 1]["status"] != "incomplete":
                raise ValueError("Review network retry lost its immediate failed attempt")
            proof = accounting.network.failure_evidence(root, root / f"calls/{indices[-1]:04d}",
                        plan, entries[position - 1], **keywords)
            if not proof["eligible"] or request != journal(indices[-1])["request"]:
                raise ValueError("Completed review cannot enter network retry")
            failures.append({"logical_index": logical, "attempt_index": indices[-1], **proof})
            network_count += 1
        else:
            if logical != base_count or digest(request) in requests:
                raise ValueError("Review size allocation skipped or repeated a request")
            token = child_token(snapshot, request)
            writer = accounting.verify_child(snapshot, request)
            if token or writer:
                key = ("review", token["root"]) if token else ("writer", writer["root_unit"])
                children[key] = children.get(key, 0) + 1
                if children[key] > POLICY["maximum_child_calls_per_root"]:
                    raise ValueError("Size child allowance exhausted")
            if indices and entries[position - 1]["status"] != "complete":
                previous = size_attempt(snapshot, journal(indices[-1]))
                parent_hash = (token or writer or {}).get("parent_prompt_hash")
                if previous is None or parent_hash != previous["prompt_hash"]:
                    raise ValueError("A new request cannot follow an unresolved non-size failure")
            base_count += 1
            requests.add(digest(request))
        selected[logical] = index
        indices.append(index)
    for entry, index in zip(entries, indices):
        if entry["status"] != "incomplete" or index in {row["attempt_index"] for row in failures}:
            continue
        row = journal(index)
        checked = size_attempt(snapshot, row)
        if checked:
            receipt = read_json(snapshot / row["runtime_record"]["path"])
            failures.append({"logical_index": index % len(plan["calls"]), "attempt_index": index,
                "eligible": False, "reason": "bounded_size_decomposition",
                "provider_receipt": "codex:" + receipt["extensions"]["thread_id"],
                "runtime_record_hash": row["runtime_record"]["hash"]})
            selected.pop(index % len(plan["calls"]), None)
    if network_count > plan["recovery"]["maximum_total"]:
        raise ValueError("Review network allowance exhausted")
    return {"selected": selected, "indices": indices, "failures": failures,
            "recoveries": network_count, "base_count": base_count, "child_calls": sum(children.values())}


@contextmanager
def replaced_aliases(original, replacement):
    def replace(before, after):
        for name, module in list(sys.modules.items()):
            if module is None or name == __name__ or not name.startswith(("humanvoice.", "tools.")):
                continue
            for attribute, value in list(vars(module).items()):
                if value is before:
                    setattr(module, attribute, after)

    replace(original, replacement)
    try:
        yield
    finally:
        replace(replacement, original)


@contextmanager
def runtime():
    if ACTIVE.get():
        yield
        return
    token = ACTIVE.set(True)
    try:
        with ExitStack() as stack:
            for original, replacement in ((NATIVES[0], windows), (NATIVES[1], require_review),
                                           (NATIVES[2], attempt_layout)):
                stack.enter_context(replaced_aliases(original, replacement))
            yield
    finally:
        ACTIVE.reset(token)
