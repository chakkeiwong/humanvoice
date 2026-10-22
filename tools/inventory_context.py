"""Bound inventory windows by sentences and repair rejected concepts automatically."""

import json
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from humanvoice.artifacts import digest, load_spans, read_json, validate_snapshot
from humanvoice.model_extraction import CoverageVerdict
from tools import inventory_punctuation as punctuation
from tools.inventory_transport_continuation import immutable

ROOT = Path(__file__).resolve().parents[1]
VERSION = "inventory-sentence-context-v1"
MARKER = ".humanvoice/inventory/context-policy.json"
FILES = ("tools/inventory_context.py",)
MAX_BYTES = 10240
MAX_ROUNDS = 2
MAX_REPAIRS = 8
SELECTED = ContextVar("inventory_context_snapshot", default=None)
ACTIVE = False


def policy(snapshot, starts):
    manifest = validate_snapshot(Path(snapshot))
    return {"version": VERSION, "source_hash": manifest["source_hash"], "manifest_sha256": digest(manifest),
            "first_windows": starts, "maximum_window_bytes": MAX_BYTES, "maximum_repairs_per_window": MAX_ROUNDS,
            "maximum_repairs": MAX_REPAIRS, "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
            "coverage_context": "all-source-spans-including-math", "negative_responses_retained": True}


def enable(snapshot, starts):
    immutable(Path(snapshot) / MARKER, policy(snapshot, starts))


def selected_policy(snapshot):
    snapshot = Path(snapshot)
    if not (snapshot / MARKER).exists():
        return None
    marker = read_json(snapshot / MARKER)
    starts = marker.get("first_windows", {})
    if (not starts or any(not isinstance(name, str) or type(index) is not int or index < 0
                         for name, index in starts.items()) or marker != policy(snapshot, starts)):
        raise ValueError("Inventory context policy or source changed")
    if not (snapshot / punctuation.MARKER).exists() or read_json(snapshot / punctuation.MARKER) != punctuation.policy(snapshot):
        raise ValueError("Inventory context lost its frozen punctuation policy")
    return marker


def expand_windows(rows, windows, first):
    if not rows:
        return windows
    if len({row["source_file"] for row in rows}) != 1:
        raise ValueError("Inventory sentence context cannot cross files")
    positions = {row["record_id"]: index for index, row in enumerate(rows)}
    if len(positions) != len(rows) or any(left["byte_end"] != right["byte_start"]
                                       for left, right in zip(rows, rows[1:])):
        raise ValueError("Inventory context requires a complete contiguous source partition")

    def boundary(index):
        return index in {0, len(rows)} or (rows[index - 1]["span_kind"] == "prose"
                and rows[index - 1]["exact_text"].rstrip().endswith((".", "!", "?")))

    result = []
    for index, window in enumerate(windows):
        if index < first:
            result.append(window)
            continue
        start, end = positions[window.span_ids[0]], positions[window.span_ids[-1]] + 1
        while not boundary(start):
            start -= 1
        while not boundary(end):
            end += 1
        if rows[end - 1]["byte_end"] - rows[start]["byte_start"] > MAX_BYTES:
            raise ValueError("Complete sentence context exceeds the inventory byte bound")
        result.append(replace(window, span_ids=[row["record_id"] for row in rows[start:end]],
                              byte_start=rows[start]["byte_start"], byte_end=rows[end - 1]["byte_end"]))
    return result


class InvocationStopped(BaseException):
    pass


class PromptModel:
    def __init__(self, model, suffix):
        self.model, self.suffix = model, suffix

    def invoke(self, **keywords):
        try:
            return self.model.invoke(**{**keywords, "prompt": keywords["prompt"] + self.suffix})
        except Exception as error:
            raise InvocationStopped("Inventory provider invocation stopped: " + str(error)) from error


@dataclass
class RepairedCoverage(CoverageVerdict):
    context_repair: dict = field(default_factory=dict)
    punctuation_ownership: dict = field(default_factory=dict)


def positive(spans, concepts, reconstruction, coverage):
    local = {concept.concept_id for concept in concepts}
    return (bool(local) and len(local) == len(concepts) and len(reconstruction) == len(local)
            and {row.concept_id for row in reconstruction} == local
            and all(row.verdict == "supported" and row.reconstruction and row.comparison and row.evidence_span_ids
                    and set(row.evidence_span_ids) <= {span["record_id"] for span in spans} for row in reconstruction)
            and len(coverage) == sum(span["span_kind"] == "prose" and bool(span["exact_text"].strip()) for span in spans)
            and {row.span_id for row in coverage} == {span["record_id"] for span in spans
                                                      if span["span_kind"] == "prose" and span["exact_text"].strip()}
            and all(row.verdict == "covered" and row.explanation and set(row.mapped_concept_ids) <= local
                    for row in coverage))


@contextmanager
def runtime():
    global ACTIVE
    from humanvoice import baseline_evidence, concept_extraction, model_extraction
    from humanvoice.commands import inventory_command
    from tools.inventory_stage_runtime import network

    if ACTIVE:
        yield
        return
    native_extract = model_extraction.extract_concepts_from_window
    native_reconstruct = model_extraction.verify_reconstruction
    native_cover = model_extraction.verify_coverage
    native_windows = concept_extraction.create_extraction_windows
    native_run, native_verify = inventory_command.run, baseline_evidence.verify_inventory_semantics
    states = {}

    @contextmanager
    def selection(snapshot):
        marker = selected_policy(snapshot)
        token = SELECTED.set((Path(snapshot), marker, {"repairs": 0}) if marker else None)
        try:
            yield
        finally:
            SELECTED.reset(token)

    def run(arguments):
        with selection(arguments.snapshot):
            return native_run(arguments)

    def verify(snapshot, baseline, evidence):
        with selection(snapshot):
            return native_verify(snapshot, baseline, evidence)

    def windows(rows, window_size=15, overlap=3):
        result = native_windows(rows, window_size, overlap)
        selected = SELECTED.get()
        if not selected or not rows or rows[0]["source_file"] not in selected[1]["first_windows"]:
            return result
        return expand_windows(rows, result, selected[1]["first_windows"][rows[0]["source_file"]])

    with punctuation.runtime(), ExitStack() as bindings:
        legacy_reconstruct, legacy_cover = model_extraction.verify_reconstruction, model_extraction.verify_coverage

        def extract(window, brief, model, registry, adjacent_context=None, span_texts=None, span_index=None, macro_display=None):
            selected = SELECTED.get()
            source_file = next(iter(span_index.values()))["source_file"] if span_index else None
            start = selected[1]["first_windows"].get(source_file) if selected else None
            enabled = start is not None and int(window.window_id.rsplit("-", 1)[1]) >= start
            if enabled:
                source = load_spans(selected[0])
                rows = [source[identifier] for identifier in window.span_ids]
                if any(punctuation.span_basis(row) != punctuation.span_basis(span_index[row["record_id"]]) for row in rows):
                    raise ValueError("Inventory context differs from immutable source")
                state = {"window": window, "brief": brief, "registry": registry, "adjacent": adjacent_context,
                         "texts": span_texts, "index": span_index, "macro": macro_display, "rows": rows,
                         "round": 0, "diagnostics": [], "budget": selected[2]}
                states[id(model)] = state
                actual = PromptModel(model, request_scope(state))
            else:
                states.pop(id(model), None)
                actual = model
            result = native_extract(window, brief, actual, registry, adjacent_context, span_texts, span_index, macro_display)
            if enabled:
                if result.abstentions or not result.concepts:
                    raise ValueError("Inventory extraction abstained or returned malformed concepts")
                state.update(concepts=result.concepts, reconstruction=native_reconstruct(result.concepts, rows,
                    PromptModel(model, request_scope(state)), macro_display))
                substantive = [row for row in rows if row["span_kind"] == "prose" and row["exact_text"].strip()]
                state["coverage"] = evaluate(substantive, result.concepts, model, macro_display)
            return result

        def request_scope(state):
            return "\n\nInventory context request: " + json.dumps({"policy": VERSION,
                "window": state["window"].window_id, "source_file": state["rows"][0]["source_file"],
                "repair_round": state["round"]}, sort_keys=True)

        def reconstruct(concepts, spans, model, macro_display=None):
            state = states.get(id(model))
            if state is None:
                return legacy_reconstruct(concepts, spans, model, macro_display)
            if state["concepts"] is not concepts or spans != state["rows"]:
                raise ValueError("Inventory reconstruction differs from the verified extraction context")
            return state["reconstruction"]

        def cover(spans, concepts, model, macro_display=None):
            state = states.get(id(model))
            if state is None:
                return legacy_cover(spans, concepts, model, macro_display)
            if state["concepts"] is not concepts or spans != [row for row in state["rows"]
                    if row["span_kind"] == "prose" and row["exact_text"].strip()]:
                raise ValueError("Inventory coverage differs from the independently verified extraction")
            return state["coverage"]

        def evaluate(spans, concepts, model, macro_display=None):
            state = states[id(model)]
            if state["concepts"] is not concepts:
                raise ValueError("Inventory coverage lost its independently reconstructed concepts")
            context = "\n\nComplete ordered source context, including math (context only; return verdicts for the target prose spans above):\n"
            context += json.dumps([punctuation.span_basis(row) for row in state["rows"]], ensure_ascii=False, sort_keys=True)
            while True:
                verdicts = native_cover(spans, concepts, PromptModel(model, context + request_scope(state)), macro_display)
                failure = None
                if positive(state["rows"], concepts, state["reconstruction"], verdicts):
                    try:
                        verdicts = punctuation.derive(spans, concepts, verdicts, state["rows"], state["reconstruction"])
                    except ValueError as error:
                        failure = str(error)
                    else:
                        if not state["diagnostics"]:
                            return verdicts
                        proof = {"version": VERSION, "failed_attempts": state["diagnostics"],
                                 "repair_round": state["round"],
                                 "source_sha256": digest([punctuation.span_basis(row) for row in state["rows"]])}
                        return [RepairedCoverage(**asdict(row), context_repair=proof) for row in verdicts]
                if state["round"] >= MAX_ROUNDS or state["budget"]["repairs"] >= MAX_REPAIRS:
                    raise ValueError("Inventory context repair exhausted its bounded attempts; negative judgments retained")
                diagnostic = {"concepts": [asdict(row) for row in concepts],
                              "reconstruction": [asdict(row) for row in state["reconstruction"]],
                              "coverage": [asdict(row) for row in verdicts], "validation_error": failure}
                state["diagnostics"].append(diagnostic)
                state["round"] += 1
                state["budget"]["repairs"] += 1
                instruction = ("\n\nRepair the previous inventory using the same complete source. Address every critic finding. "
                    "Preserve all source qualifications and relationships; remove unsupported claims. "
                    "Return a new complete concept array. These previous findings are diagnostics, not source facts:\n")
                repair_model = PromptModel(model, request_scope(state) + instruction + json.dumps(diagnostic, sort_keys=True))
                repaired = native_extract(state["window"], state["brief"], repair_model, state["registry"], state["adjacent"],
                    state["texts"], state["index"], state["macro"])
                if repaired.abstentions or not repaired.concepts:
                    raise ValueError("Inventory context repair abstained or returned malformed concepts")
                concepts[:] = repaired.concepts
                state["reconstruction"][:] = native_reconstruct(concepts, state["rows"],
                    PromptModel(model, request_scope(state)), state["macro"])

        for original, replacement in ((native_run, run), (native_verify, verify), (native_windows, windows),
                (native_extract, extract), (legacy_reconstruct, reconstruct), (legacy_cover, cover)):
            bindings.enter_context(network.replaced_aliases(original, replacement))
        ACTIVE = True
        try:
            yield
        finally:
            ACTIVE = False
