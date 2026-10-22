"""Context repairs retain negative evidence and require fresh independent critics."""

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from humanvoice.artifacts import load_spans, read_json, write_json
from humanvoice.concept_extraction import create_extraction_windows
from humanvoice.model import ModelAdapter
from tools import inventory_context as context
from tools import inventory_context_continuation as continuation
from test_manuscript_transport_recovery import codex


def test_actual_failed_window_gets_complete_math_and_sentence_context():
    snapshot = Path(read_json(continuation.PRIOR / "plan.json")["snapshot"])
    rows = list(load_spans(snapshot).values())
    original = create_extraction_windows(rows)
    expanded = context.expand_windows(rows, original, 10)
    assert expanded[:10] == original[:10]
    assert len(expanded) == len(original) == 182
    assert {"span-170be5d8eff5e252", "span-1e61f81460033391", "span-ee9ba0cab550ad5a",
            "span-6b1ab08b9a6f2aa2", "span-46958969962c3bcf"} <= set(expanded[10].span_ids)
    assert not set(expanded[10].span_ids) <= set(original[10].span_ids)
    assert all(set(before.span_ids) <= set(after.span_ids) for before, after in zip(original, expanded))
    assert max(window.byte_end - window.byte_start for window in expanded[10:]) <= context.MAX_BYTES
    assert {identifier for window in expanded for identifier in window.span_ids} == {row["record_id"] for row in rows}
    assert all(left is right for left, right in zip(original[:10], expanded[:10]))


@pytest.mark.parametrize("defect", ["file", "gap", "duplicate", "oversize"])
def test_invalid_or_unbounded_context_is_rejected(defect):
    rows = [{"record_id": "before", "source_file": "main.tex", "span_kind": "prose", "exact_text": "A ",
             "byte_start": 0, "byte_end": 2},
            {"record_id": "after", "source_file": "main.tex", "span_kind": "prose", "exact_text": "claim.",
             "byte_start": 2, "byte_end": 8}]
    if defect == "file":
        rows[1]["source_file"] = "other.tex"
    elif defect == "gap":
        rows[1]["byte_start"] += 1
    elif defect == "duplicate":
        rows[1]["record_id"] = rows[0]["record_id"]
    else:
        rows[1]["byte_end"] = 20000
    with pytest.raises(ValueError):
        context.expand_windows(rows, create_extraction_windows(rows), 0)


def test_transport_failure_cannot_trigger_semantic_rerolls():
    calls = []

    def invoke(**keywords):
        calls.append(keywords)
        raise RuntimeError("response-free exhausted transport")

    proxy = context.PromptModel(SimpleNamespace(invoke=invoke), "scope")
    with pytest.raises(context.InvocationStopped):
        proxy.invoke(prompt="source")
    assert len(calls) == 1


@pytest.fixture
def native_case(codex, tmp_path, monkeypatch):
    from humanvoice.commands import init_command
    from humanvoice.corpus_rights import install_rights
    from rights_fixture import fixture_rights

    source = tmp_path / "context.tex"
    source.write_text("\\documentclass{article}\n\\begin{document}\nThe measure is Lebesgue in \\(x\\) times counting in "
                      "\\(r\\) when the map is bijective.\n\\end{document}\n")
    snapshot, brief = tmp_path / "context", tmp_path / "brief.json"
    write_json(brief, read_json(codex.snapshot / "manifest.json")["brief"])
    assert init_command.run(SimpleNamespace(source=source, brief=brief, output=snapshot)) == 0
    rights = fixture_rights(snapshot)
    record = read_json(rights)
    record["extensions"].update(provider="VisionCoder", destinations=["https://cn.origincoder.com/v1/responses"])
    write_json(rights, record)
    install_rights(snapshot, rights)
    context.punctuation.enable(snapshot)
    context.enable(snapshot, {"context.tex": 0})
    state = SimpleNamespace(snapshot=snapshot, failures=1, defect="coverage", requests=[], change_membership=False)
    native = ModelAdapter.invoke

    def respond(model, **keywords):
        state.requests.append(deepcopy(keywords))
        spans = list(load_spans(snapshot).values())
        prose = [row for row in spans if row["span_kind"] == "prose" and row["exact_text"].strip()]
        math = [row for row in spans if row["span_kind"] == "math"]
        round_number = sum(request["purpose"] == "concept_extraction" for request in state.requests) - 1
        concept = {"concept_id": "measure", "proposition": "For a bijective map, the measure is Lebesgue in x times counting in r.",
            "concept_type": "definition", "source_span_ids": [row["record_id"] for row in prose],
            "supporting_spans": [row["record_id"] for row in math], "teaching_roles": ["initial"],
            "prerequisites": [], "confidence": 1.0}
        concepts = [concept]
        if state.change_membership and round_number > 0:
            concept["concept_id"] = "measure-fixed"
            concepts.append({**concept, "concept_id": "counting", "proposition": "The counting component is in r."})
        if keywords["purpose"] == "concept_extraction":
            payload = concepts
        elif keywords["purpose"] == "reconstruction_verification":
            payload = [{"concept_id": item["concept_id"], "verdict": "contradicted" if state.defect == "reconstruction"
                and round_number < state.failures else "supported", "reconstruction": item["proposition"],
                "comparison": "Synthetic source check.", "confidence": 1.0,
                "evidence_span_ids": item["source_span_ids"] + item["supporting_spans"]} for item in concepts]
        else:
            assert all(row["exact_text"] in keywords["prompt"].replace("\\\\", "\\") for row in math)
            payload = [{"span_id": row["record_id"], "verdict": "gap" if state.defect == "coverage"
                and round_number < state.failures else "covered", "explanation": "Synthetic independent coverage.",
                "mapped_concept_ids": [concept["concept_id"]]} for row in prose]
        write_json(codex.settings, {"response": payload})
        return native(model, **keywords)

    monkeypatch.setattr(ModelAdapter, "invoke", respond)
    return state


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("defect,failures,changed", [("coverage", 1, False), ("coverage", 2, True), ("reconstruction", 1, False)])
def test_native_context_repair_replays_negative_and_positive_judgments(native_case, defect, failures, changed):
    from humanvoice import baseline_evidence
    from humanvoice.baseline_review import require_baseline_review
    from humanvoice.commands import inventory_command, plan_v2_command
    from humanvoice.concept_baseline import load_baseline

    native_case.defect, native_case.failures, native_case.change_membership = defect, failures, changed
    snapshot = native_case.snapshot
    with context.runtime():
        assert inventory_command.run(SimpleNamespace(snapshot=snapshot, mock=False, freeze=True)) == 0
        baseline = load_baseline(snapshot / ".humanvoice/inventory/baseline.json")
        assert require_baseline_review(snapshot, baseline)["status"] == "pass"
        assert plan_v2_command.run(SimpleNamespace(snapshot=snapshot, max_unit_size=2000)) == 0
        evidence = read_json(snapshot / ".humanvoice/inventory/inventory_result.json")
        assert len(evidence["model_calls"]) == 3 * (1 + failures)
        assert len(native_case.requests) == 3 * (1 + failures)
        repaired = [row for row in evidence["coverage"] if "context_repair" in row]
        assert repaired and all(len(row["context_repair"]["failed_attempts"]) == failures for row in repaired)
        for round_number in range(1, 1 + failures):
            assert "previous findings" in native_case.requests[3 * round_number]["prompt"]
            assert "previous findings" not in native_case.requests[3 * round_number + 1]["prompt"]
        changed = deepcopy(evidence)
        changed["coverage"][0]["context_repair"]["failed_attempts"].clear()
        with pytest.raises(ValueError, match="summaries differ"):
            baseline_evidence.verify_inventory_semantics(snapshot, baseline, changed)
        missing = deepcopy(evidence)
        missing["model_calls"].pop(0)
        with pytest.raises((ValueError, context.InvocationStopped)):
            baseline_evidence.verify_inventory_semantics(snapshot, baseline, missing)
    assert len(native_case.requests) == 3 * (1 + failures)


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_stage_repair_budget_is_enforced(native_case, monkeypatch):
    from humanvoice.commands import inventory_command

    monkeypatch.setattr(context, "MAX_REPAIRS", 1)
    native_case.failures = 100
    marker = context.policy(native_case.snapshot, {"context.tex": 0})
    write_json(native_case.snapshot / context.MARKER, marker)
    with context.runtime():
        assert inventory_command.run(SimpleNamespace(snapshot=native_case.snapshot, mock=False, freeze=True)) == 3
    assert len(native_case.requests) == 6
    assert not (native_case.snapshot / ".humanvoice/inventory/baseline.json").exists()


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_repair_exhaustion_stays_blocking(native_case):
    from humanvoice.commands import inventory_command

    native_case.failures = 100
    with context.runtime():
        assert inventory_command.run(SimpleNamespace(snapshot=native_case.snapshot, mock=False, freeze=True)) == 3
    assert len(native_case.requests) == 9
    assert not (native_case.snapshot / ".humanvoice/inventory/baseline.json").exists()
    assert len(list((native_case.snapshot / ".humanvoice/inventory/calls").glob("*/*.json"))) == 9


def test_unmarked_snapshot_keeps_legacy_requests(tmp_path, monkeypatch):
    from humanvoice.commands import inventory_command

    observed = []

    def run(arguments):
        assert context.SELECTED.get() is None
        observed.append(True)
        return 7

    monkeypatch.setattr(inventory_command, "run", run)
    with context.runtime():
        assert inventory_command.run(SimpleNamespace(snapshot=tmp_path)) == 7
    assert observed == [True] and inventory_command.run is run


def test_policy_refuses_source_or_code_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(context, "policy", lambda snapshot, starts: {"first_windows": starts, "version": "expected"})
    write_json(tmp_path / context.MARKER, {"first_windows": {"main.tex": 0}, "version": "changed"})
    with pytest.raises(ValueError):
        context.selected_policy(tmp_path)
