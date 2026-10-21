"""Punctuation ownership conserves judgments and rejects substantive gaps."""

import json
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from humanvoice.artifacts import load_spans, read_json
from humanvoice.concept_extraction import ConceptCandidate, create_extraction_windows
from humanvoice.model_extraction import CoverageVerdict, ReconstructionVerdict
from tools import inventory_punctuation as punctuation
from tools import zlb_ssd_workspace as workspace


@pytest.fixture
def case():
    texts = [("intro", "prose", "A multiplier "), ("left", "math", r"\(x\geq0\)"),
             ("colon", "prose", ":\n"), ("right", "math", r"\[xy=0\]")]
    window, offset = [], 0
    for identifier, kind, text in texts:
        window.append({"record_id": identifier, "source_file": "main.tex", "byte_start": offset,
            "byte_end": offset + len(text.encode()), "span_kind": kind, "reader_facing": True, "exact_text": text})
        offset = window[-1]["byte_end"]
    concept = ConceptCandidate("owner", "The multiplier is nonnegative.", "definition", ["intro", "left"],
                               supporting_spans=["right"], teaching_roles=["initial"])
    recon = ReconstructionVerdict("owner", "supported", "Nonnegative multiplier.", "Source agrees.", 1.0,
                                  ["intro", "left", "right"])
    coverage = [CoverageVerdict("intro", "covered", "Definition is retained.", ["owner"]),
                CoverageVerdict("colon", "covered", "No independent substantive assertion.", [])]
    return SimpleNamespace(spans=[window[0], window[2]], concepts=[concept], verdicts=coverage,
                           window=window, reconstruction=[recon])


def derive(case):
    return punctuation.derive(case.spans, case.concepts, case.verdicts, case.window, case.reconstruction)


@pytest.mark.parametrize("mark", [":", ";", ",", "."])
def test_unique_grounded_owner_preserves_raw_judgment_and_source(case, mark):
    case.window[2]["exact_text"] = mark + "\n"
    before = deepcopy(vars(case))
    result = derive(case)
    assert result[0] is case.verdicts[0]
    assert result[1].mapped_concept_ids == ["owner"]
    assert result[1].verdict == "covered"
    assert result[1].explanation == case.verdicts[1].explanation
    assert result[1].punctuation_ownership["raw_coverage"] == asdict(case.verdicts[1])
    assert vars(case) == before


@pytest.mark.parametrize("text", ["not", "not:\n", "=", "+", "-", "<", "!", "?", "...", "::", "", " ",
                                   r"\colon", "∴", "¬", "1:", ":\u200b"])
def test_substantive_or_ambiguous_text_cannot_acquire_punctuation_ownership(case, text):
    case.window[2]["exact_text"] = text
    with pytest.raises(ValueError):
        derive(case)


@pytest.mark.parametrize("defect", ["negative", "unresolved", "missing", "duplicate", "foreign_mapping", "explanation",
                                   "unsupported", "reconstruction_missing", "reconstruction_duplicate", "foreign_evidence",
                                   "ungrounded", "ambiguous", "gap", "file", "prose_boundary", "hidden", "context"])
def test_incomplete_or_unproven_judgments_stay_blocking(case, defect):
    if defect in {"negative", "unresolved"}:
        case.verdicts[1].verdict = "gap" if defect == "negative" else "unresolved"
    elif defect == "missing":
        case.verdicts.pop()
    elif defect == "duplicate":
        case.verdicts[0] = deepcopy(case.verdicts[1])
    elif defect == "foreign_mapping":
        case.verdicts[0].mapped_concept_ids = ["foreign"]
    elif defect == "explanation":
        case.verdicts[1].explanation = ""
    elif defect == "unsupported":
        case.reconstruction[0].verdict = "contradicted"
    elif defect == "reconstruction_missing":
        case.reconstruction.clear()
    elif defect == "reconstruction_duplicate":
        case.reconstruction.append(deepcopy(case.reconstruction[0]))
    elif defect == "foreign_evidence":
        case.reconstruction[0].evidence_span_ids.append("foreign")
    elif defect == "ungrounded":
        case.reconstruction[0].evidence_span_ids.remove("right")
    elif defect == "ambiguous":
        owner, recon = deepcopy(case.concepts[0]), deepcopy(case.reconstruction[0])
        owner.concept_id = recon.concept_id = "other"
        case.concepts.append(owner)
        case.reconstruction.append(recon)
    elif defect == "gap":
        case.window[1]["byte_end"] -= 1
    elif defect == "file":
        case.window[-1]["source_file"] = "other.tex"
    elif defect == "prose_boundary":
        case.window[-1]["span_kind"] = "prose"
    elif defect == "hidden":
        case.window[-1]["reader_facing"] = False
    else:
        case.spans = deepcopy(case.spans)
        case.spans[-1]["exact_text"] = "changed"
    with pytest.raises(ValueError):
        derive(case)


def test_actual_retained_zlb_colon_maps_to_supported_multiplier_without_response_changes():
    paths = [workspace.STAGE / f"calls/{index:04d}/call.json" for index in (15, 16, 17)]
    before = [path.read_bytes() for path in paths]
    payloads = [json.loads(read_json(path)["response_text"]) for path in paths]
    spans = load_spans(workspace.WORK)
    window = create_extraction_windows(list(spans.values()), window_size=15, overlap=3)[7]
    rows = [spans[identifier] for identifier in window.span_ids]
    result = punctuation.derive([span for span in rows if span["span_kind"] == "prose" and span["exact_text"].strip()],
        [ConceptCandidate(**row) for row in payloads[0]], [CoverageVerdict(**row) for row in payloads[2]],
        rows, [ReconstructionVerdict(**row) for row in payloads[1]])
    derived = [row for row in result if isinstance(row, punctuation.OwnedPunctuation)]
    assert len(derived) == 1 and derived[0].span_id == "span-62039de336488637"
    assert derived[0].mapped_concept_ids == ["concept-006"]
    assert derived[0].punctuation_ownership["raw_coverage"]["mapped_concept_ids"] == []
    assert before == [path.read_bytes() for path in paths]


def test_runtime_is_scoped_to_marker_and_restores_native_aliases(case, monkeypatch, tmp_path):
    from humanvoice import baseline_evidence, model_extraction
    from humanvoice.commands import inventory_command

    monkeypatch.setattr(model_extraction, "verify_reconstruction", lambda *arguments: case.reconstruction)
    monkeypatch.setattr(model_extraction, "verify_coverage", lambda *arguments: case.verdicts)
    originals = [(module, module.verify_reconstruction, module.verify_coverage)
                 for module in (model_extraction, baseline_evidence, inventory_command)]
    model = SimpleNamespace(snapshot=tmp_path)
    with punctuation.runtime():
        inventory_command.verify_reconstruction(case.concepts, case.window, model)
        assert inventory_command.verify_coverage(case.spans, case.concepts, model) is case.verdicts
    for module, reconstruction, coverage in originals:
        assert module.verify_reconstruction is reconstruction
        assert module.verify_coverage is coverage


def test_nested_runtime_does_not_double_derive_or_restore_outer_scope():
    from humanvoice import baseline_evidence

    original = baseline_evidence.verify_coverage
    with punctuation.runtime() as outer:
        wrapper = baseline_evidence.verify_coverage
        with punctuation.runtime() as inner:
            assert inner is outer
            assert baseline_evidence.verify_coverage is wrapper
        assert baseline_evidence.verify_coverage is wrapper
    assert baseline_evidence.verify_coverage is original


@pytest.mark.parametrize("defect", [None, "policy", "source", "reconstruction"])
def test_execution_and_baseline_replay_derive_identical_evidence(case, monkeypatch, tmp_path, defect):
    from humanvoice import baseline_evidence, model_extraction
    from humanvoice.commands import inventory_command
    from humanvoice.artifacts import write_json

    monkeypatch.setattr(model_extraction, "verify_reconstruction", lambda *arguments: case.reconstruction)
    monkeypatch.setattr(model_extraction, "verify_coverage", lambda *arguments: case.verdicts)
    marker = {"source": "bound"}
    monkeypatch.setattr(punctuation, "policy", lambda snapshot: marker)
    source = {row["record_id"]: deepcopy(row) for row in case.window}
    monkeypatch.setattr(punctuation, "load_spans", lambda snapshot: source)
    write_json(tmp_path / punctuation.MARKER, marker if defect != "policy" else {"source": "tampered"})
    if defect == "source":
        source["colon"]["exact_text"] = "not"
    model = SimpleNamespace(snapshot=tmp_path)
    with punctuation.runtime():
        if defect != "reconstruction":
            inventory_command.verify_reconstruction(case.concepts, case.window, model)
        if defect:
            with pytest.raises(ValueError):
                inventory_command.verify_coverage(case.spans, case.concepts, model)
            return
        actual = inventory_command.verify_coverage(case.spans, case.concepts, model)
        baseline_evidence.verify_reconstruction(case.concepts, case.window, model)
        replayed = baseline_evidence.verify_coverage(case.spans, case.concepts, model)
        assert [asdict(row) for row in actual] == [asdict(row) for row in replayed]
