"""Prospective semantic acceptance and document/root limits."""

import subprocess
import sys
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from test_failure_first_semantics import retained_failure
from test_inventory_recovery_v3_policy import policy
from test_inventory_size_recovery import source_rows

from humanvoice.artifacts import digest
from humanvoice.concept_extraction import ConceptCandidate
from humanvoice.model_extraction import (
    CoverageVerdict,
    ExtractionResult,
    ReconstructionVerdict,
)
from tools.inventory_recovery_v3 import accounting
from tools.inventory_recovery_v3 import semantics as semantic


@pytest.mark.parametrize("interruption", [None, "validation", "execution"])
def test_document_history_restores_native_hooks_after_each_scope(monkeypatch, interruption):
    native = semantic.model_extraction.extract_concepts_from_window
    events = []

    @contextmanager
    def history():
        events.append(("history-enter", semantic.DOCUMENT.get() is not None))
        try:
            with semantic.context.runtime():
                yield
        finally:
            events.append(("history-exit", semantic.DOCUMENT.get() is not None))

    def inherited(origin, current_policy):
        assert origin == {"fixture": "retained-origin"}
        assert semantic.context.ACTIVE and semantic.DOCUMENT.get() is None
        events.append(("origin-validated", False))
        if interruption == "validation":
            raise OSError("interrupted validation")
        return []

    monkeypatch.setattr(accounting, "history_scope", history)
    monkeypatch.setattr(semantic, "inherited_rules", inherited)
    transition = {"rules": [], "policy": policy(), "inherited_rules": [],
                  "semantic_version": semantic.VERSION, "migration": {"fixture": "retained-origin"}}

    def enter():
        with accounting.document_scope(transition) as state:
            assert semantic.context.ACTIVE and semantic.DOCUMENT.get() is not None
            assert semantic.model_extraction.extract_concepts_from_window is not native
            with semantic.transition_runtime(transition) as nested:
                assert nested is state
            events.append(("execution", True))
            if interruption == "execution":
                raise OSError("interrupted execution")

    if interruption:
        with pytest.raises(OSError, match="interrupted " + interruption):
            enter()
    else:
        enter()
    assert events[:3] == [("history-enter", False), ("origin-validated", False), ("history-exit", False)]
    assert events[3:] == ([] if interruption == "validation" else
        [("history-enter", True), ("execution", True), ("history-exit", True)])
    assert not semantic.context.ACTIVE
    assert semantic.DOCUMENT.get() is None and semantic.ACTIVE.get() is None
    assert semantic.model_extraction.extract_concepts_from_window is native


def test_document_history_rejects_active_legacy_scope(monkeypatch):
    entered = []

    @contextmanager
    def history():
        entered.append(True)
        yield

    monkeypatch.setattr(accounting, "history_scope", history)
    transition = {"rules": [], "policy": policy(), "inherited_rules": [],
                  "semantic_version": semantic.VERSION, "migration": None}
    with semantic.context.runtime(), pytest.raises(RuntimeError, match="before historical runtime"), (
            accounting.document_scope(transition)):
        pytest.fail("Document policy installed beneath active legacy hooks")
    assert not entered and not semantic.context.ACTIVE


@pytest.mark.parametrize("interrupted", [False, True])
def test_qualification_replay_isolated_from_document_ownership(interrupted):
    from humanvoice import (
        automatic_calibration,
        automatic_qualification,
        critic_evaluation,
    )

    corpus = automatic_calibration.generate_corpus("document-qualification-isolation")
    cases = corpus["cases"]
    expected = [critic_evaluation.case_request(case) for case in cases]
    sensitivity = automatic_calibration.sensitivity_cases(corpus, distinct_requests=True)
    original = critic_evaluation.evaluate_case

    def replay():
        with semantic.runtime(policy=policy()) as observations, semantic.context.runtime():
            assert [automatic_qualification.case_request(case) for case in cases] == expected
            assert automatic_calibration.sensitivity_cases(corpus, distinct_requests=True) == sensitivity
            assert observations == {"observations": [], "applied": []}
            with pytest.raises(RuntimeError, match="original extraction root"):
                semantic.model_extraction.verify_coverage(cases[0]["data"]["spans"], [], object())
            if interrupted:
                raise OSError("qualification interruption")

    if interrupted:
        with pytest.raises(OSError, match="qualification interruption"):
            replay()
    else:
        replay()
    assert critic_evaluation.evaluate_case is original
    assert automatic_qualification.evaluate_case is original
    assert semantic.DOCUMENT.get() is None and semantic.ACTIVE.get() is None


@pytest.mark.parametrize("interrupted", [False, True])
def test_cold_qualification_import_restores_aliases_and_historical_observations(interrupted):
    from tools.validate_inventory_history import environment

    script = r'''
import sys
from types import SimpleNamespace
from humanvoice import automatic_calibration, critic_evaluation
from tools.inventory_recovery_v3 import semantics
from tools.inventory_recovery_v3.policy import proposal

assert "humanvoice.automatic_execution" not in sys.modules
policy = proposal(remaining_requests=1, inherited_recovery=0, incident_allowance=1,
    split_allowance=1, qualification_calls=0, available_calls=4, available_tokens=2176000)
case = next(row for row in automatic_calibration.generate_corpus("cold-alias")["cases"]
            if row["critic"] == "reconstruction")
native = critic_evaluation.evaluate_case
model = SimpleNamespace(invoke=lambda **keywords: SimpleNamespace(
    text="", abstention="offline preview", truncated=False))

def evaluate(function):
    try:
        function(case, model)
    except ValueError as error:
        assert str(error) == "Incomplete reconstruction verdicts"
    else:
        raise AssertionError("Expected native abstention")

try:
    with semantics.runtime(policy=policy) as observations:
        from humanvoice import automatic_execution
        saved = automatic_execution.evaluate_case
        assert saved is not native
        evaluate(saved)
        assert not observations["observations"]
        if sys.argv[1] == "True":
            raise OSError("cut")
except OSError as error:
    assert str(error) == "cut"
assert automatic_execution.evaluate_case is native
assert critic_evaluation.evaluate_case is native
assert semantics.ACTIVE.get() is None and semantics.DOCUMENT.get() is None
for function in (automatic_execution.evaluate_case, saved):
    with semantics.historical.runtime() as observations:
        evaluate(function)
        assert len(observations["observations"]) == 1
with semantics.runtime(policy=policy) as observations:
    evaluate(saved)
    evaluate(automatic_execution.evaluate_case)
    assert not observations["observations"]
assert automatic_execution.evaluate_case is native
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(interrupted)],
        cwd=Path(__file__).resolve().parents[1], env=environment(), capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-4000:]


def observed_window(number=0, file="main.tex", texts=None):
    window, spans = source_rows(texts or ["First. ", "Second."])
    window = replace(window, window_id=f"window-{number:04d}")
    for row in spans.values():
        row["source_file"] = file
    model = semantic.context.PromptModel(object(), f"Scope {file}/{number}")
    request = semantic.split.native.scoped_request(window, {}, model, None,
        {key: row["exact_text"] for key, row in spans.items()}, None)
    observed = {"purpose": "concept_extraction", "request": request, "window": asdict(window),
        "spans": spans, "depth": 0, "parents": [],
        "scope": {"source_file": file, "window": window.window_id, "purpose": "concept_extraction"}}
    return window, spans, model, observed


def install_native(monkeypatch):
    calls = []

    def extract(window, brief, model, registry, adjacent_context=None, span_texts=None, span_index=None, macro_display=None):
        calls.append(window.window_id)
        return ExtractionResult(window.span_ids[0], [ConceptCandidate("local", "Claim.", "claim", window.span_ids)])

    def cover(spans, concepts, model, macro_display=None):
        return [CoverageVerdict(row["record_id"], "covered", "Covered.", [concept.concept_id for concept in concepts])
                for row in spans]

    def reconstruct(concepts, spans, model, macro_display=None):
        return [ReconstructionVerdict(row.concept_id, "supported", row.proposition, "Supported.", 1.0,
                                     [span["record_id"] for span in spans]) for row in concepts]

    monkeypatch.setattr(semantic.model_extraction, "extract_concepts_from_window", extract)
    monkeypatch.setattr(semantic.model_extraction, "verify_coverage", cover)
    monkeypatch.setattr(semantic.model_extraction, "verify_reconstruction", reconstruct)
    return calls


def invoke(window, spans, model):
    return semantic.model_extraction.extract_concepts_from_window(window, {}, model, None,
        span_texts={key: row["exact_text"] for key, row in spans.items()}, span_index=spans)


def test_document_over_sixteen_independent_splits_and_namespaced_windows(monkeypatch):
    cases = [observed_window(number // 2, f"file-{number % 2}.tex") for number in range(34)]
    failures = {f"fixture-settled-{index}": retained_failure(observed, index)
                for index, (_window, _spans, _model, observed) in enumerate(cases)}
    rules = [semantic.rule(observed, failures[f"fixture-settled-{index}"])
             for index, (_window, _spans, _model, observed) in enumerate(cases)]
    calls = install_native(monkeypatch)
    with semantic.runtime(rules, policy=policy(split_allowance=34), verify_failure=failures.__getitem__) as state:
        for window, spans, model, _observed in cases:
            result = invoke(window, spans, model)
            assert len(result.concepts) == 2
            assert len({row.concept_id for row in result.concepts}) == 2
            assert len(semantic.model_extraction.verify_coverage(list(spans.values()), result.concepts, model)) == 2
    assert len(calls) == 68 and len(state["applied"]) == 34
    with pytest.raises(RuntimeError, match="Document split expansion"):
        semantic.validate_rules(rules, policy=policy(split_allowance=33), verify_failure=failures.__getitem__)


@pytest.mark.parametrize("purpose", ["reconstruction_verification", "coverage_verification"])
@pytest.mark.parametrize("kind", ["missing", "negative"])
def test_extraction_split_enforces_original_window_judgments(monkeypatch, purpose, kind):
    window, spans, model, observed = observed_window()
    failure = retained_failure(observed, 0)
    calls = install_native(monkeypatch)

    def failed(*arguments):
        if kind == "missing":
            return []
        if purpose == "coverage_verification":
            return [CoverageVerdict(row["record_id"], "unresolved", "Bad.", ["claim"]) for row in arguments[0]]
        return [ReconstructionVerdict(row.concept_id, "unsupported", "Bad.", "Bad.", 1.0, list(spans))
                for row in arguments[0]]

    monkeypatch.setattr(semantic.model_extraction,
        "verify_coverage" if purpose == "coverage_verification" else "verify_reconstruction", failed)
    with semantic.runtime([semantic.rule(observed, failure)], policy=policy(), verify_failure=lambda output: failure):
        result = invoke(window, spans, model)
        with pytest.raises(semantic.split.native.SplitStopped, match="native judgments"):
            if purpose == "coverage_verification":
                semantic.model_extraction.verify_coverage(list(spans.values()), result.concepts, model)
            else:
                semantic.model_extraction.verify_reconstruction(result.concepts, list(spans.values()), model)
    assert len(calls) == 2


@pytest.mark.parametrize("change", ["recipe", "request", "duplicate", "old_new_duplicate"])
def test_rehashed_rules_cannot_change_recipe_or_reuse_failure(change):
    _window, _spans, _model, observed = observed_window()
    failure = retained_failure(observed, 0)
    rule = semantic.rule(observed, failure)
    rules, inherited = [rule], []
    if change == "recipe":
        rule["recipe"]["children"].reverse()
        rule["recipe"]["identity"] = digest({key: value for key, value in rule["recipe"].items() if key != "identity"})
    elif change == "request":
        rule["request"]["prompt"] += "changed"
    elif change == "duplicate":
        rules.append(deepcopy(rule))
    else:
        inherited = [semantic.historical.rule(observed, failure)]
        rules = [*inherited, rule]
    rule["identity"] = digest({key: value for key, value in rule.items() if key != "identity"})
    with pytest.raises((ValueError, RuntimeError)):
        semantic.validate_rules(rules, policy=policy(), inherited=inherited, verify_failure=lambda root: failure)


def test_nested_runtime_restores_native_state_after_exception():
    with pytest.raises(OSError, match="interruption"), semantic.runtime(policy=policy()) as state:
        with semantic.runtime(policy=policy()) as nested:
            assert nested is state
        with pytest.raises(RuntimeError, match="Nested semantic"), semantic.runtime(policy=policy(split_allowance=33)):
            pass
        raise OSError("interruption")
    assert semantic.ACTIVE.get() is None and semantic.DOCUMENT.get() is None
    with semantic.historical.runtime() as state:
        assert state == {"observations": [], "applied": []}


@pytest.mark.parametrize("downgraded", [False, True])
def test_prospective_split_cannot_be_reclassified_as_inherited(downgraded):
    _window, _spans, _model, observed = observed_window()
    failure = retained_failure(observed, 0)
    selected = semantic.historical.rule(observed, failure) if downgraded else semantic.rule(observed, failure)
    with pytest.raises(RuntimeError, match="inherited rule prefix"):
        semantic.validate_rules([selected], policy=policy(split_allowance=0), inherited=[selected],
            verify_failure=lambda root: failure)


def test_combined_graph_requires_semantic_parents_but_accepts_size_ancestry():
    window, spans, model, observed = observed_window(texts=["First. ", "Second. ", "Third. ", "Fourth."])
    failure = retained_failure(observed, 0)
    parent = semantic.rule(observed, failure)
    child_window = semantic.split.native.partition(window, spans)[0]
    child_spans = {identifier: spans[identifier] for identifier in child_window.span_ids}
    child = {**deepcopy(observed), "window": asdict(child_window), "spans": child_spans, "depth": 1,
        "parents": [digest(observed["request"])], "request": semantic.split.native.scoped_request(
            child_window, {}, model, None, {key: row["exact_text"] for key, row in child_spans.items()}, None)}
    failed = retained_failure(child, 1)
    selected = semantic.rule(child, failed)
    assert semantic.validate_graph([parent, selected], spans, [])
    corrupted = deepcopy(child)
    corrupted["parents"] = []
    missing_parent = semantic.rule(corrupted, failed)
    with pytest.raises(RuntimeError, match="semantic parent chain"):
        semantic.validate_graph([parent, missing_parent], spans, [])
    inherited = {"window": parent["recipe"]["window"], "children": parent["recipe"]["children"],
        "request": parent["request"], "failure": {"runtime_record": {"hash": "original-size-failure"}}}
    assert semantic.validate_graph([missing_parent], spans, [inherited])
    with pytest.raises(RuntimeError, match="repeats a request"):
        semantic.validate_graph([parent], spans, [inherited])


@pytest.mark.parametrize("defect", ["targets", "context", "ancestor"])
def test_critic_graph_rejects_rehashed_nonchild_context_or_chain(monkeypatch, defect):
    window, spans, model, _observed = observed_window(texts=["One. ", "Two. ", "Three. ", "Four."])
    install_native(monkeypatch)
    with semantic.runtime(policy=policy()) as state:
        result = invoke(window, spans, model)
        semantic.model_extraction.verify_coverage(list(spans.values()), result.concepts, model)
    observed = state["observations"][-1]
    failure = retained_failure(observed, 0)
    parent = semantic.rule(observed, failure)
    with semantic.runtime([parent], policy=policy(), verify_failure=lambda root: failure) as state:
        result = invoke(window, spans, model)
        semantic.model_extraction.verify_coverage(list(spans.values()), result.concepts, model)
    child = next(row for row in state["observations"] if row["purpose"] == "coverage_verification" and row["depth"] == 1)
    if defect == "targets":
        child["owned"] = [child["owned"][0], observed["owned"][-1]]
    elif defect == "context":
        child["context"]["macro_display"] = "changed context"
    else:
        child["parents"] = ["wrong-parent"]
    selected = semantic.rule(child, retained_failure(child, 1))
    with pytest.raises(RuntimeError, match="Critic graph"):
        semantic.validate_graph([parent, selected], spans, [])


@pytest.mark.parametrize("purpose", ["coverage_verification", "reconstruction_verification"])
def test_critic_graph_derives_mixed_history_chain_from_native_requests(monkeypatch, purpose):
    window, spans, model, _observed = observed_window(texts=[f"Sentence {index}. " for index in range(8)])
    install_native(monkeypatch)
    concepts = [ConceptCandidate(f"concept-{index}", "Claim.", "claim", [identifier])
                for index, identifier in enumerate(spans)]
    failures, rules = {}, []

    def invoke_critic(selected_model):
        if purpose == "coverage_verification":
            return semantic.model_extraction.verify_coverage(list(spans.values()), concepts, selected_model)
        return semantic.model_extraction.verify_reconstruction(concepts, list(spans.values()), selected_model)

    for depth in range(2):
        with semantic.historical.runtime(rules, verify_failure=failures.__getitem__) as state:
            assert len(invoke_critic(model)) == 8
        observed = next(row for row in state["observations"] if row["depth"] == depth)
        failure = retained_failure(observed, depth)
        failures[failure["output"]] = failure
        rules.append(semantic.historical.rule(observed, failure))
    with semantic.historical.runtime(rules, verify_failure=failures.__getitem__) as state:
        assert len(invoke_critic(model)) == 8
    child = next(row for row in state["observations"] if row["depth"] == 2)
    child.update(scope={"source_file": "main.tex", "window": window.window_id, "purpose": purpose},
                 parents=[digest(row["request"]) for row in rules])
    with semantic.historical.runtime() as state:
        invoke_critic(semantic.context.PromptModel(object(), "Independent original window"))
    unrelated = state["observations"][0]
    other = semantic.historical.rule(unrelated, retained_failure(unrelated, 3))
    failure = retained_failure(child, 2)
    selected = semantic.rule(child, failure)
    assert semantic.validate_graph([*rules, other, selected], spans, [])
    child["parents"][0] = digest(other["request"])
    corrupted = semantic.rule(child, failure)
    with pytest.raises(RuntimeError, match="complete parent chain"):
        semantic.validate_graph([*rules, other, corrupted], spans, [])
    with pytest.raises(RuntimeError, match="unique exact native parent"):
        semantic.validate_graph([other, rules[1], selected], spans, [])
