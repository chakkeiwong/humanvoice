"""
Tests for model-assisted concept extraction and verification.

Phase 2 of WP-V2-2: model calls with independent critics.
"""

import pytest
from humanvoice.model_extraction import (
    ExtractionResult,
    ReconstructionVerdict,
    CoverageVerdict,
    extract_concepts_from_window,
    verify_reconstruction,
    verify_coverage,
    _extraction_prompt,
    _reconstruction_prompt,
    _coverage_prompt,
)
from humanvoice.concept_extraction import ExtractionWindow, ConceptCandidate


@pytest.fixture
def simple_window():
    """Minimal extraction window for testing."""
    return ExtractionWindow(
        window_id="window-0001",
        span_ids=["span-0001", "span-0002", "span-0003"],
        adjacent_before=["span-0000"],
        adjacent_after=["span-0004"],
        byte_start=0,
        byte_end=150,
    )


@pytest.fixture
def minimal_brief():
    """Minimal HumanizationBrief for extraction."""
    return {
        "reader": {
            "expertise_level": "graduate_student",
            "prior_knowledge": ["basic_statistics"],
        },
        "genre": "technical",
    }


@pytest.fixture
def sample_concepts():
    """Sample extracted concepts for critic testing."""
    return [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="The posterior distribution combines prior and likelihood",
            concept_type="definition",
            source_span_ids=["span-0001"],
            teaching_roles=["initial"],
            confidence=0.92,
        ),
        ConceptCandidate(
            concept_id="concept-002",
            proposition="Conjugate priors simplify computation",
            concept_type="claim",
            source_span_ids=["span-0002"],
            teaching_roles=["initial"],
            confidence=0.88,
        ),
    ]


@pytest.fixture
def sample_spans():
    """Sample source spans for coverage testing."""
    return [
        {
            "record_id": "span-0001",
            "span_kind": "prose",
            "exact_text": "The posterior distribution combines prior and likelihood.",
            "coverage_disposition": "unresolved",
        },
        {
            "record_id": "span-0002",
            "span_kind": "prose",
            "exact_text": "Conjugate priors simplify computation.",
            "coverage_disposition": "unresolved",
        },
        {
            "record_id": "span-0003",
            "span_kind": "math",
            "exact_text": "\\pi(\\theta | y) \\propto \\pi(\\theta) L(y | \\theta)",
            "coverage_disposition": "protected_structural",
        },
    ]


def test_extraction_prompt_includes_source_spans(simple_window, minimal_brief):
    """Extraction prompt contains span IDs."""
    prompt = _extraction_prompt(simple_window, minimal_brief, {}, {})

    assert "span-0001" in prompt
    assert "span-0002" in prompt
    assert "span-0003" in prompt


def test_extraction_prompt_includes_reader_profile(simple_window, minimal_brief):
    """Extraction prompt conveys reader knowledge."""
    prompt = _extraction_prompt(simple_window, minimal_brief, {}, {})

    assert "graduate_student" in prompt
    assert "basic_statistics" in prompt


def test_extraction_prompt_defines_concept(simple_window, minimal_brief):
    """Extraction prompt explains what counts as a concept."""
    prompt = _extraction_prompt(simple_window, minimal_brief, {}, {})

    assert "definition" in prompt.lower()
    assert "mechanism" in prompt.lower()
    assert "claim" in prompt.lower()


def test_extraction_prompt_includes_abstention_conditions(simple_window, minimal_brief):
    """Extraction prompt tells model when to abstain."""
    prompt = _extraction_prompt(simple_window, minimal_brief, {}, {})

    assert "abstain" in prompt.lower() or "empty list" in prompt.lower()


def test_reconstruction_prompt_blinds_critic_first(sample_concepts):
    """Reconstruction critic sees concepts before source."""
    prompt = _reconstruction_prompt(sample_concepts, "Source text here")

    # The concept JSON data appears before the actual source text
    # (instruction headers don't matter, data order is what matters)
    concept_json_start = prompt.find('[')  # Start of concept JSON array
    source_text_start = prompt.find("Source text here")

    assert concept_json_start < source_text_start


def test_reconstruction_prompt_includes_verdict_options(sample_concepts):
    """Reconstruction prompt defines verdict values."""
    prompt = _reconstruction_prompt(sample_concepts, "Source text here")

    assert "supported" in prompt
    assert "contradicted" in prompt
    assert "unresolved" in prompt


def test_coverage_prompt_includes_spans_and_concepts(sample_spans, sample_concepts):
    """Coverage prompt shows both spans and concepts."""
    prompt = _coverage_prompt(sample_spans, sample_concepts)

    assert "span-0001" in prompt
    assert "concept-001" in prompt


def test_coverage_prompt_skips_structural_spans(sample_spans, sample_concepts):
    """Coverage prompt tells critic to skip whitespace/commands."""
    prompt = _coverage_prompt(sample_spans, sample_concepts)

    assert "whitespace" in prompt.lower()
    assert "structural" in prompt.lower()


def test_extract_concepts_returns_abstention_placeholder(simple_window, minimal_brief):
    """Extraction returns abstention until model call implemented."""
    result = extract_concepts_from_window(
        window=simple_window,
        brief=minimal_brief,
        model=None,  # Not used yet
        registry=None,  # Not used yet
    )

    assert isinstance(result, ExtractionResult)
    assert len(result.concepts) == 0
    assert "model_call_not_implemented" in result.abstentions
    assert result.prompt_hash is not None


def test_verify_reconstruction_returns_empty_placeholder(sample_concepts, sample_spans):
    """Reconstruction critic returns empty until implemented."""
    verdicts = verify_reconstruction(
        concepts=sample_concepts,
        source_spans=sample_spans,
        model=None,
    )

    assert isinstance(verdicts, list)
    assert len(verdicts) == 0  # Placeholder


def test_verify_coverage_returns_empty_placeholder(sample_spans, sample_concepts):
    """Coverage critic returns empty until implemented."""
    verdicts = verify_coverage(
        spans=sample_spans,
        concepts=sample_concepts,
        model=None,
    )

    assert isinstance(verdicts, list)
    assert len(verdicts) == 0  # Placeholder


def test_extraction_result_structure():
    """ExtractionResult has required fields."""
    result = ExtractionResult(
        window_index=0,
        concepts=[],
        abstentions=["test"],
        prompt_hash="abc123",
    )

    assert result.window_index == 0
    assert result.concepts == []
    assert result.abstentions == ["test"]
    assert result.prompt_hash == "abc123"


def test_reconstruction_verdict_structure():
    """ReconstructionVerdict has required fields."""
    verdict = ReconstructionVerdict(
        concept_id="concept-001",
        verdict="supported",
        reconstruction="Inferred meaning",
        comparison="Matches source",
        confidence=0.95,
        evidence_span_ids=["span-0001"],
    )

    assert verdict.concept_id == "concept-001"
    assert verdict.verdict == "supported"
    assert verdict.confidence == 0.95


def test_coverage_verdict_structure():
    """CoverageVerdict has required fields."""
    verdict = CoverageVerdict(
        span_id="span-0001",
        verdict="covered",
        explanation="Proposition matches",
        mapped_concept_ids=["concept-001"],
    )

    assert verdict.span_id == "span-0001"
    assert verdict.verdict == "covered"
    assert len(verdict.mapped_concept_ids) == 1
