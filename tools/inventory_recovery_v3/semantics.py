"""Apply document-bounded splits while retaining native source and judgment checks."""

import fcntl
import json
import sys
from collections import Counter
from contextlib import ExitStack, contextmanager, nullcontext
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import FunctionType

from humanvoice import critic_evaluation, model_extraction
from humanvoice.artifacts import digest, load_spans, read_json
from humanvoice.source_macro_display import window_macro_display
from tools import inventory_context as context
from tools import sol_inventory_program as original
from tools import sol_inventory_reconnect_split as split
from tools.delayed_network_runtime import replaced_aliases
from tools.inventory_recovery_v2 import semantics as historical
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.policy import require_capacity

VERSION = "inventory-document-semantic-rule-v3"
ACTIVE = historical.ACTIVE
DOCUMENT = ContextVar("inventory_document_semantics", default=None)
request = historical.request


@contextmanager
def scoped_aliases(original, replacement):
    with replaced_aliases(original, replacement):
        try:
            yield
        finally:
            for name, module in list(sys.modules.items()):
                if module is None or not name.startswith(("humanvoice.", "tools.")):
                    continue
                for attribute, value in list(vars(module).items()):
                    if value is replacement:
                        setattr(module, attribute, original)


def normalized(observation):
    value = deepcopy(observation)
    if value["purpose"] == "concept_extraction":
        value["spans"] = {identifier: split.source_basis(row) for identifier, row in value["spans"].items()}
    return value


def source_file(spans):
    files = {row["source_file"] for row in spans}
    if len(files) != 1:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Semantic root requires one original source file")
    return next(iter(files))


def scope(observation):
    value = observation.get("scope")
    if (not isinstance(value, dict) or set(value) != {"source_file", "window", "purpose"}
            or any(not isinstance(item, str) or not item for item in value.values())
            or value["purpose"] != observation["purpose"]
            or ".split-" in value["window"]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Semantic observation lost its original root scope")
    rows = (list(observation["spans"].values()) if observation["purpose"] == "concept_extraction"
            else observation["context"]["spans"])
    if value["source_file"] != source_file(rows):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Semantic scope changed its original source file")
    if observation["purpose"] == "concept_extraction" and (
            value["window"] != observation["window"]["window_id"].split(".split-", 1)[0]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Semantic scope changed its original extraction window")
    return value


def rule(observation, failure):
    native = historical.rule(observation, failure)
    observed = normalized(observation)
    scope(observed)
    value = {"version": VERSION, "observation": observed,
             "request": native["request"], "recipe": native["recipe"]}
    return {**value, "identity": digest(value)}


def matches(observation, item):
    rebuilt = (rule(observation, item["recipe"]["failure"]) if item.get("version") == VERSION
               else historical.rule(observation, item["recipe"]["failure"]))
    return rebuilt == item


def critic_prompt(purpose, payload):
    from humanvoice.concept_extraction import ConceptCandidate

    concepts = [ConceptCandidate(**row) for row in payload["concepts"]]
    if purpose == "coverage_verification":
        return model_extraction._coverage_prompt(payload["spans"], concepts, payload["macro_display"])
    return model_extraction._reconstruction_prompt(concepts, "\n".join(
        f"[{row['record_id']}]: {row['exact_text']}" for row in payload["spans"]), payload["macro_display"])


def critic_child(parent, selected):
    recipe, child = parent["recipe"], selected["recipe"]
    if (recipe["kind"] != child["kind"] or recipe["depth"] + 1 != child["depth"]
            or child["owned"] not in [row["owned"] for row in recipe["children"]]):
        return False
    payload = recipe["context"]
    expected = deepcopy(payload)
    field, identifier = (("spans", "record_id") if recipe["kind"] == "coverage_verification"
                         else ("concepts", "concept_id"))
    expected[field] = [row for row in payload[field] if row[identifier] in child["owned"]]
    prompt = critic_prompt(recipe["kind"], payload)
    if child["context"] != expected or not parent["request"]["prompt"].startswith(prompt):
        return False
    suffix = "\n\nComplete original critic context (context only; return only requested target judgments):\n"
    request = {**parent["request"], "prompt": critic_prompt(child["kind"], expected)
        + suffix + json.dumps(payload, sort_keys=True, ensure_ascii=False)
        + parent["request"]["prompt"][len(prompt):]}
    return selected["request"] == request


def validate_graph(rules, spans, size_rules):
    requests, receipts, windows, parents = set(), set(), {}, set()
    semantic_paths, critic_rules, critic_paths = {}, {}, {}
    combined = [{"request": item["request"], "receipt": item["failure"]["runtime_record"]["hash"],
                 "window": item["window"], "children": item["children"]} for item in size_rules]
    for item in rules:
        recipe = item["recipe"]
        value = {"request": item["request"], "receipt": recipe["failure"]["receipt_hash"], "semantic": item}
        if recipe["kind"] == "extraction":
            split.validate_extraction(recipe, spans)
            value.update(window=recipe["window"], children=recipe["children"])
        combined.append(value)
    for item in combined:
        request_hash = digest(item["request"])
        if request_hash in requests or item["receipt"] in receipts:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Combined split graph repeats a request or failed receipt")
        requests.add(request_hash)
        receipts.add(item["receipt"])
        if "window" not in item:
            selected = item["semantic"]
            chain = []
            if selected["recipe"]["depth"]:
                candidates = [identity for identity, parent in critic_rules.items() if critic_child(parent, selected)]
                if len(candidates) != 1:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic graph lacks a unique exact native parent")
                parent_hash = candidates[0]
                chain = [*critic_paths[parent_hash], parent_hash]
            if selected.get("version") == VERSION:
                observation = selected["observation"]
                if observation["parents"] != chain:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic graph changed its complete parent chain")
            critic_rules[request_hash] = selected
            critic_paths[request_hash] = chain
            continue
        window = item["window"]
        file = source_file([spans[identifier] for identifier in window["span_ids"]])
        key = file, window["window_id"]
        if key in parents:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Combined split graph has conflicting parent edges")
        if ".split-" in window["window_id"] and windows.get(key) != window:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Combined split graph skipped or changed its parent")
        if key in windows and windows[key] != window:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Combined split graph changed original root membership")
        selected = item.get("semantic")
        expected_parents = semantic_paths.get(key, [])
        if selected is not None and selected.get("version") == VERSION and selected["observation"]["parents"] != expected_parents:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Extraction graph changed its semantic parent chain")
        parents.add(key)
        windows[key] = window
        for child in item["children"]:
            key = file, child["window_id"]
            if key in windows and windows[key] != child:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Combined split graph changed child ownership")
            windows[key] = child
            semantic_paths[key] = [*expected_parents, request_hash] if selected is not None else expected_parents
    return True


def plan_policy(plan):
    marker = plan.get("inventory_document_recovery", {})
    if marker.get("semantic_version") != VERSION:
        if any(row.get("version") == VERSION for row in marker.get("split_rules", [])):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Document rules lack their versioned semantic binding")
        return {}
    return {"policy": marker["policy"], "inherited": marker["inherited_rules"],
            "origin": marker.get("transition", {}).get("migration")}


@contextmanager
def transition_runtime(transition, *, validation_scope=nullcontext):
    options = ({"policy": transition["policy"], "inherited": transition["inherited_rules"],
                "origin": transition.get("migration")}
               if transition.get("semantic_version") == VERSION else {})
    with runtime(transition["rules"], validation_scope=validation_scope, **options) as state:
        yield state


def settled_failure(output):
    from tools.inventory_recovery_v3 import accounting, execution, runtime
    from tools.inventory_recovery_v3.migration import verify_journal

    output = Path(output)
    if runtime.FIELD not in read_json(Path(output) / "plan.json"):
        return historical.settled_failure(output)
    with (output / "executor.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = runtime.validate_plan(read_json(output / "plan.json"))
        usage = accounting.verify_settlement(output)["report"]
        settlements = [event["usage"] for event in read_json(original.account.ACCOUNT)["events"]
                       if event["kind"] == "settle" and event["usage"]["plan_identity"] == plan["plan_identity"]]
        if settlements != [usage] or read_json(output / "executor.json").get("status") != "stopped":
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Decomposition requires unique settlement and a stopped executor")
        entries = read_json(output / "allocation-ledger.json")["calls"]
        with runtime.runtime(plan, output):
            state = execution.layout(output, plan, entries)
        if state["mode"] not in {"decomposition_required", "size_decomposition_required"} or state["pending"] is not None:
            raise RecoveryStop("BLOCKED_DECOMPOSITION", "Decomposition requires settled native size or repeated timeout evidence")
        index = state["selected"][state["logical"]]
        journal, _result, _record, _entry = verify_journal(output, index)
        value = {"kind": "output_limit", "output": str(output), "plan_identity": plan["plan_identity"],
            "receipt_hash": journal["runtime_record"]["hash"], "settlement_hash": digest(usage),
            "settled": True, "group_quiescent": True, "request": journal["request"],
            "request_hash": digest(journal["request"]),
            "recovery_sessions_used": plan[runtime.FIELD]["recovery_sessions_used"] + len(entries) - state["logical"]}
        folder = Path(plan["snapshot"]) / Path(journal["runtime_record"]["path"]).parent
        if read_json(folder / "process.json").get("group_quiescent") is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Decomposition cannot overlap a provider process")
        if state["mode"] == "decomposition_required":
            position = state["indices"].index(index)
            if position < 1:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Repeated timeout lacks a passing canary")
            canary_index = state["indices"][position - 1]
            descriptor = read_json(output / f"reconnect-attempts/{canary_index:04d}.json")
            canary, result, _record, _entry = verify_journal(output, canary_index)
            if descriptor["kind"] != "canary" or result["status"] != "complete":
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Repeated timeout lost its native canary")
            value.update(kind="repeated_response_free_envelope_after_canary",
                canary_receipt_hash=canary["runtime_record"]["hash"], prior_failure_hash=descriptor["incident_hash"],
                cause_proven=False)
        return value


def inherited_rules(origin, policy):
    from tools.inventory_recovery_v2 import runtime as legacy
    from tools.inventory_recovery_v3.migration import (
        inspect_parent,
        require_account_extension,
    )
    from tools.inventory_recovery_v3.stage import reconstruct

    if origin is None:
        return []
    if (origin.get("identity") != digest({key: value for key, value in origin.items() if key != "identity"})
            or origin.get("legacy_successor_charge") != policy["inherited_recovery"]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Semantic origin lost its original migration binding")
    account_path = original.account.ACCOUNT
    from tools.inventory_recovery_v2 import qualification

    checked = inspect_parent(origin["parent"], account_path, verify_settlement=legacy.verify_settlement,
                             reconstruct=reconstruct, verify_qualification=qualification.verify)
    require_account_extension(origin["account_boundary"], account_path)
    checked["account_boundary"] = origin["account_boundary"]
    checked["evidence"][str(Path(account_path))] = origin["evidence"][str(Path(account_path))]
    checked["identity"] = digest({key: value for key, value in checked.items() if key != "identity"})
    if checked != origin:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Semantic origin changed independently retained migration")
    plan = legacy.validate_plan(read_json(Path(origin["parent"]) / "plan.json"))
    return plan[legacy.FIELD].get("split_rules", [])


def validate_rules(rules, verify_failure=settled_failure, *, policy=None, inherited=(), origin=None):
    if policy is None:
        return historical.validate_rules(rules, verify_failure)
    require_capacity(policy)
    if (not isinstance(rules, list) or rules[:len(inherited)] != list(inherited)
            or any(item.get("version") == VERSION for item in inherited)
            or list(inherited) != inherited_rules(origin, policy)):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Document semantics changed its inherited rule prefix")
    historical.validate_rules(list(inherited), verify_failure)
    requests, failures, roots, expansion = set(), set(), Counter(), 0
    for position, item in enumerate(rules):
        failure = item["recipe"]["failure"]
        if (item.get("identity") != digest({key: value for key, value in item.items() if key != "identity"})
                or failure != verify_failure(failure["output"])
                or failure.get("request") != item["request"]
                or failure.get("request_hash") != digest(item["request"])
                or digest(item["request"]) in requests or failure["receipt_hash"] in failures):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Semantic rule lacks unique independently settled failure evidence")
        requests.add(digest(item["request"]))
        failures.add(failure["receipt_hash"])
        if position < len(inherited):
            continue
        if item.get("version") != VERSION or rule(item["observation"], failure) != item:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Document semantic rule changed its exact native recipe")
        observation = item["observation"]
        parents = observation.get("parents")
        if (not isinstance(parents, list) or len(parents) != len(set(parents))
                or any(not isinstance(parent, str) or parent not in requests - {digest(item["request"])} for parent in parents)
                or observation["purpose"] != "concept_extraction" and len(parents) != observation["depth"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Document semantic rule lost its ordered parent request chain")
        previous_depth = observation["depth"] - len(parents) - 1
        for parent in parents:
            ancestor = next(row for row in rules[:position] if digest(row["request"]) == parent)
            if (ancestor["recipe"]["depth"] != previous_depth + 1
                    or ancestor["request"]["purpose"] != observation["purpose"]
                    or ancestor.get("version") == VERSION and scope(ancestor["observation"]) != scope(observation)):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Document semantic rule changed its parent scope or depth")
            previous_depth = ancestor["recipe"]["depth"]
        children = len(item["recipe"]["children"])
        expansion += children - 1
        root = digest(scope(item["observation"]))
        roots[root] += children
        if roots[root] > policy["maximum_lineage_children"]:
            raise RecoveryStop("BLOCKED_DECOMPOSITION", "Original root child allowance exhausted")
    if expansion > policy["split_allowance"]:
        raise RecoveryStop("BLOCKED_BUDGET", "Document split expansion exceeds reserved capacity")
    return rules


@contextmanager
def runtime(rules=(), *, policy=None, inherited=(), origin=None, verify_failure=settled_failure,
            validation_scope=nullcontext):
    if policy is None:
        with historical.runtime(rules, verify_failure=verify_failure) as observed:
            yield observed
        return
    binding = {"policy": policy, "inherited": list(inherited), "rules": list(rules), "origin": origin}
    retained = DOCUMENT.get()
    if retained is not None:
        if retained != binding:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Nested semantic runtime changed document bounds")
        yield ACTIVE.get()["observations"]
        return
    if ACTIVE.get() is not None or context.ACTIVE:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Install document semantics before historical runtime")
    with validation_scope():
        frozen = deepcopy(validate_rules(list(rules), verify_failure, policy=policy, inherited=inherited, origin=origin))
    if ACTIVE.get() is not None or context.ACTIVE:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Semantic validation left an active historical runtime")
    by_request = {digest(item["request"]): item for item in frozen}
    observed, applied, decomposed, windows = [], [], set(), {}
    applied_roots, root_children, inherited_roots = {}, Counter(), set()
    native_extract = model_extraction.extract_concepts_from_window
    native_reconstruct = model_extraction.verify_reconstruction
    native_cover = model_extraction.verify_coverage
    native_evaluate = critic_evaluation.evaluate_case
    qualification_active = True

    def qualification_case(*arguments, **keywords):
        if not qualification_active:
            current = critic_evaluation.evaluate_case
            return (native_evaluate if current is qualification_case else current)(*arguments, **keywords)
        namespace = {**native_evaluate.__globals__, "verify_reconstruction": native_reconstruct,
                     "verify_coverage": native_cover}
        evaluate = FunctionType(native_evaluate.__code__, namespace, argdefs=native_evaluate.__defaults__)
        evaluate.__kwdefaults__ = native_evaluate.__kwdefaults__
        return evaluate(*arguments, **keywords)

    def model_identity(model):
        while isinstance(model, context.PromptModel):
            model = model.model
        return id(model)

    def model_key(model):
        return model_identity(model), windows.get(model_identity(model))

    def require_judgments(results, covering, identifiers, spans, concepts):
        keys = [row.span_id if covering else row.concept_id for row in results]
        concept_ids = {row.concept_id for row in concepts}
        span_ids = {row["record_id"] for row in spans}
        if (len(keys) != len(set(keys)) or set(keys) != identifiers
                or any(row.verdict != ("covered" if covering else "supported") for row in results)
                or covering and any(not row.explanation or not row.mapped_concept_ids
                                    or not set(row.mapped_concept_ids) <= concept_ids for row in results)
                or not covering and any(not row.reconstruction or not row.comparison or not row.evidence_span_ids
                                        or not set(row.evidence_span_ids) <= span_ids for row in results)):
            raise split.native.SplitStopped("Split critic failed native judgments; no sibling or semantic reroll")

    def selected(observation):
        root = digest(scope(observation))
        observed.append(deepcopy(observation))
        item = by_request.get(digest(observation["request"]))
        if item is not None:
            if not matches(observation, item):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Decomposition changed native source, context or lineage")
            identity = item["identity"]
            if identity in applied_roots and applied_roots[identity] != root:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Semantic rule crossed original source roots")
            if identity not in applied_roots:
                root_children[root] += len(item["recipe"]["children"])
                applied_roots[identity] = root
            if root_children[root] > policy["maximum_lineage_children"]:
                raise RecoveryStop("BLOCKED_DECOMPOSITION", "Inherited and prospective root children exceed allowance")
            applied.append(identity)
        return item

    def extract(window, brief, model, registry, adjacent_context=None, span_texts=None, span_index=None,
                macro_display=None, *, depth=0, parents=()):
        rows = [span_index[identifier] for identifier in window.span_ids]
        original_window = window.window_id.split(".split-", 1)[0]
        source = source_file(rows)
        windows[model_identity(model)] = (source, original_window)
        depth = max(depth, window.window_id.count(".split-"))
        actual = split.native.scoped_request(window, brief, model, adjacent_context, span_texts, macro_display)
        observation = {"purpose": "concept_extraction", "request": actual, "window": asdict(window),
            "spans": span_index, "depth": depth, "parents": list(parents),
            "scope": {"source_file": source, "window": original_window, "purpose": "concept_extraction"}}
        root = digest(observation["scope"])
        if root not in inherited_roots:
            selected_context = context.SELECTED.get()
            historical_size = split.native.selected_policy(selected_context[0]) if selected_context else None
            spans = load_spans(selected_context[0]) if selected_context else span_index
            root_children[root] = sum(len(row["children"]) for row in historical_size["rules"]
                if row["root_window"] == original_window and source_file(
                    [spans[identifier] for identifier in row["window"]["span_ids"]]) == source) if historical_size else 0
            inherited_roots.add(root)
        item = selected(observation)
        if item is None:
            return native_extract(window, brief, model, registry, adjacent_context, span_texts, span_index, macro_display)
        recipe = item["recipe"]
        decomposed.add(model_key(model))
        children = split.validate_extraction(recipe, span_index)
        selected_context = context.SELECTED.get()
        spans = load_spans(selected_context[0]) if selected_context else span_index
        results = []
        for child in children:
            child_rows = [spans[identifier] for identifier in child.span_ids]
            results.append(extract(child, brief, model, registry, adjacent_context,
                {row["record_id"]: row["exact_text"] for row in child_rows},
                {row["record_id"]: row for row in child_rows}, window_macro_display(child_rows, spans),
                depth=depth + 1, parents=(*parents, digest(actual))))
            result = results[-1]
            if (result.abstentions or not result.concepts or result.window_index != child.span_ids[0]
                    or len({concept.concept_id for concept in result.concepts}) != len(result.concepts)
                    or any(not concept.concept_id for concept in result.concepts)
                    or any(not concept.source_span_ids or not set(concept.source_span_ids) <= set(child.span_ids)
                           or not set(concept.supporting_spans) <= set(window.span_ids) for concept in result.concepts)):
                raise split.native.SplitStopped("Split child failed native extraction; do not dispatch siblings")
        return split.merge_extraction(recipe, span_index, results)

    def critic(purpose, spans, concepts, model, macro_display, depth, parents=()):
        covering = purpose == "coverage_verification"
        prompt = (model_extraction._coverage_prompt(spans, concepts, macro_display) if covering else
                  model_extraction._reconstruction_prompt(concepts, "\n".join(
                      f"[{row['record_id']}]: {row['exact_text']}" for row in spans), macro_display))
        actual = request(prompt, purpose, "coverage-response" if covering else "reconstruction-response", model)
        owned = [row["record_id"] for row in spans] if covering else [row.concept_id for row in concepts]
        payload = {"spans": [split.source_basis(row) for row in spans],
                   "concepts": [asdict(row) for row in concepts], "macro_display": macro_display}
        original = windows.get(model_identity(model))
        if original is None or original[0] != source_file(spans):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic lacks its original extraction root")
        observation = {"purpose": purpose, "request": actual, "owned": owned, "context": payload,
            "depth": depth, "parents": list(parents),
            "scope": {"source_file": original[0], "window": original[1], "purpose": purpose}}
        item = selected(observation)
        if item is None:
            results = native_cover(spans, concepts, model, macro_display) if covering else native_reconstruct(
                concepts, spans, model, macro_display)
            if model_key(model) in decomposed:
                require_judgments(results, covering, set(owned), spans, concepts)
            return results
        recipe = item["recipe"]
        suffix = "\n\nComplete original critic context (context only; return only requested target judgments):\n"
        decomposed.add(model_key(model))
        scoped = context.PromptModel(model, suffix + json.dumps(payload, sort_keys=True, ensure_ascii=False))
        children = []
        for child in recipe["children"]:
            identifiers = set(child["owned"])
            subset_spans = [row for row in spans if row["record_id"] in identifiers] if covering else spans
            subset_concepts = concepts if covering else [row for row in concepts if row.concept_id in identifiers]
            results = critic(purpose, subset_spans, subset_concepts, scoped, macro_display,
                             depth + 1, (*parents, digest(actual)))
            require_judgments(results, covering, identifiers, spans, concepts)
            children.append(results)
        merged = split.merge_critics(recipe, [[asdict(row) for row in child] for child in children])
        value_type = model_extraction.CoverageVerdict if covering else model_extraction.ReconstructionVerdict
        return [value_type(**row) for row in merged]

    def reconstruct(concepts, spans, model, macro_display=None):
        return critic("reconstruction_verification", spans, concepts, model, macro_display, 0)

    def cover(spans, concepts, model, macro_display=None):
        return critic("coverage_verification", spans, concepts, model, macro_display, 0)

    with ExitStack() as bindings:
        state = {"observations": observed, "applied": applied}
        token = ACTIVE.set({"rules": frozen, "observations": state})
        bindings.callback(ACTIVE.reset, token)
        token = DOCUMENT.set(deepcopy(binding))
        bindings.callback(DOCUMENT.reset, token)
        for original, replacement in ((native_extract, extract), (native_reconstruct, reconstruct), (native_cover, cover)):
            bindings.enter_context(scoped_aliases(original, replacement))
        bindings.enter_context(scoped_aliases(native_evaluate, qualification_case))
        try:
            yield state
        finally:
            qualification_active = False
