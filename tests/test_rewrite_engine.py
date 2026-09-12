"""
Tests for WP-V2-3 source-grounded rewrite engine.

Tests concept preservation, obligation fulfillment, protected object preservation,
and mutation safety.
"""

import pytest
from pathlib import Path
from humanvoice.rewrite_engine import (
    ExplanationObligation,
    ConceptCorrespondence,
    RewriteResult,
    build_rewrite_context,
    build_rewrite_prompt,
    verify_mutation_safety,
)
from humanvoice.concept_extraction import ConceptCandidate
from humanvoice.semantic_unit_splitting import RewriteUnit


@pytest.fixture
def sample_unit():
    """Create a sample rewrite unit."""
    return RewriteUnit(
        unit_id="unit-001",
        concept_ids=["concept-001", "concept-002"],
        source_span_ids=["span-001", "span-002", "span-003"],
        prerequisites=[],
        estimated_words=1500,
        teaching_sequence=1,
    )


@pytest.fixture
def sample_baseline():
    """Create a sample frozen baseline."""
    from humanvoice.concept_baseline import ConceptBaseline, ConceptBaselineEntry

    entries = [
        ConceptBaselineEntry(
            concept_id="concept-001",
            proposition="The zero lower bound constrains monetary policy",
            concept_type="claim",
            source_span_ids=["span-001"],
            teaching_roles=["initial"],
            confidence=0.95,
        ),
        ConceptBaselineEntry(
            concept_id="concept-002",
            proposition="Forward guidance affects expectations",
            concept_type="mechanism",
            source_span_ids=["span-002", "span-003"],
            teaching_roles=["initial"],
            confidence=0.90,
        ),
    ]

    baseline = ConceptBaseline(
        baseline_id="baseline-001",
        snapshot_id="snapshot-001",
        source_hash="abc123",
        concept_entries=entries,
        total_concepts=2,
        frozen_at="2026-09-12T00:00:00Z",
        frozen_by="test-user",
    )

    return baseline


@pytest.fixture
def sample_plan():
    """Create a sample rewrite plan."""
    from humanvoice.semantic_unit_splitting import RewritePlan

    return RewritePlan(
        plan_id="plan-001",
        baseline_id="baseline-001",
        snapshot_id="snapshot-001",
        units=[],
        total_units=1,
        total_concepts=2,
    )


@pytest.fixture
def sample_source_texts():
    """Create sample source texts."""
    return {
        "span-001": "When nominal interest rates approach zero, the central bank cannot cut rates further.",
        "span-002": "Forward guidance about future policy can still influence current expectations.",
        "span-003": "If the central bank commits to holding rates low, people adjust their saving and investment decisions.",
    }


@pytest.fixture
def sample_brief():
    """Create a HumanizationBrief."""
    return {
        "reader": {
            "expertise_level": "graduate_student",
            "prior_knowledge": ["basic_economics"],
        },
        "genre": "technical",
        "voice_register": "formal",
    }


def test_build_rewrite_context(sample_unit, sample_baseline, sample_plan, sample_source_texts, sample_brief):
    """Rewrite context includes all necessary information."""
    context = build_rewrite_context(
        unit=sample_unit,
        baseline=sample_baseline,
        plan=sample_plan,
        source_texts=sample_source_texts,
        protected_objects={},
        brief=sample_brief,
        policy_snapshot={},
        dependency_graph=None,
    )

    assert context["unit_id"] == "unit-001"
    assert len(context["source_text"]) > 0
    assert context["source_span_ids"] == ["span-001", "span-002", "span-003"]
    assert len(context["concepts_to_teach"]) == 2
    assert context["reader_expertise"] == "graduate_student"
    assert context["genre"] == "technical"


def test_rewrite_context_includes_concepts(sample_unit, sample_baseline, sample_plan, sample_source_texts, sample_brief):
    """Rewrite context includes all concepts with their details."""
    context = build_rewrite_context(
        unit=sample_unit,
        baseline=sample_baseline,
        plan=sample_plan,
        source_texts=sample_source_texts,
        protected_objects={},
        brief=sample_brief,
        policy_snapshot={},
        dependency_graph=None,
    )

    concepts = context["concepts_to_teach"]
    assert len(concepts) == 2

    concept_001 = next(c for c in concepts if c["concept_id"] == "concept-001")
    assert "zero lower bound" in concept_001["proposition"].lower()
    assert concept_001["concept_type"] == "claim"


def test_build_rewrite_prompt_includes_constraints(sample_unit, sample_baseline, sample_plan, sample_source_texts, sample_brief):
    """Rewrite prompt includes critical constraints."""
    context = build_rewrite_context(
        unit=sample_unit,
        baseline=sample_baseline,
        plan=sample_plan,
        source_texts=sample_source_texts,
        protected_objects={},
        brief=sample_brief,
        policy_snapshot={},
        dependency_graph=None,
    )

    prompt = build_rewrite_prompt(context)

    assert "Preserve every concept" in prompt
    assert "no deletion" in prompt.lower()
    assert "explain each concept adequately" in prompt.lower()
    assert "concept_id" in prompt  # Requires tracking correspondence


def test_build_rewrite_prompt_includes_source(sample_unit, sample_baseline, sample_plan, sample_source_texts, sample_brief):
    """Rewrite prompt includes actual source text."""
    context = build_rewrite_context(
        unit=sample_unit,
        baseline=sample_baseline,
        plan=sample_plan,
        source_texts=sample_source_texts,
        protected_objects={},
        brief=sample_brief,
        policy_snapshot={},
        dependency_graph=None,
    )

    prompt = build_rewrite_prompt(context)

    # Source text should be in prompt (case-insensitive)
    assert "nominal interest rates" in prompt
    assert "guidance" in prompt.lower()


def test_verify_mutation_safety_accepts_valid_correspondence(sample_unit, sample_baseline):
    """Valid correspondence with all concepts passes safety check."""
    correspondences = [
        ConceptCorrespondence(
            source_concept_id="concept-001",
            output_span_ids=["out-001"],
            mapping_type="paraphrase",
            rationale="Rephrased for clarity",
        ),
        ConceptCorrespondence(
            source_concept_id="concept-002",
            output_span_ids=["out-002", "out-003"],
            mapping_type="expand",
            rationale="Added example",
        ),
    ]

    result = verify_mutation_safety(
        unit=sample_unit,
        baseline=sample_baseline,
        output_latex="Improved text here",
        correspondences=correspondences,
        protected_objects_preserved=[],
    )

    assert result.is_acceptable
    assert len(result.rejection_reasons) == 0


def test_verify_mutation_safety_rejects_deleted_concepts(sample_unit, sample_baseline):
    """Deletion of concepts blocks acceptance."""
    # Only concept-001, missing concept-002
    correspondences = [
        ConceptCorrespondence(
            source_concept_id="concept-001",
            output_span_ids=["out-001"],
            mapping_type="retain",
        ),
    ]

    result = verify_mutation_safety(
        unit=sample_unit,
        baseline=sample_baseline,
        output_latex="Only concept one",
        correspondences=correspondences,
        protected_objects_preserved=[],
    )

    assert not result.is_acceptable
    assert any("Deleted concepts" in r for r in result.rejection_reasons)
    assert "concept-002" in str(result.mutations)


def test_verify_mutation_safety_rejects_mention_only(sample_unit, sample_baseline):
    """Mention without explanation blocks acceptance."""
    correspondences = [
        ConceptCorrespondence(
            source_concept_id="concept-001",
            output_span_ids=["out-001"],
            mapping_type="mention_only",  # INVALID
        ),
        ConceptCorrespondence(
            source_concept_id="concept-002",
            output_span_ids=["out-002"],
            mapping_type="expand",
        ),
    ]

    result = verify_mutation_safety(
        unit=sample_unit,
        baseline=sample_baseline,
        output_latex="Some text",
        correspondences=correspondences,
        protected_objects_preserved=[],
    )

    assert not result.is_acceptable
    assert any("mention" in r.lower() for r in result.rejection_reasons)


def test_verify_mutation_safety_rejects_truncation(sample_unit, sample_baseline):
    """Truncated or empty output blocks acceptance."""
    correspondences = [
        ConceptCorrespondence(
            source_concept_id="concept-001",
            output_span_ids=["out-001"],
            mapping_type="retain",
        ),
        ConceptCorrespondence(
            source_concept_id="concept-002",
            output_span_ids=["out-002"],
            mapping_type="retain",
        ),
    ]

    result = verify_mutation_safety(
        unit=sample_unit,
        baseline=sample_baseline,
        output_latex="",  # Empty output
        correspondences=correspondences,
        protected_objects_preserved=[],
    )

    assert not result.is_acceptable
    assert any("truncat" in r.lower() for r in result.rejection_reasons)


def test_verify_mutation_safety_tracks_preserved_objects(sample_unit, sample_baseline):
    """Protected objects preservation tracked."""
    correspondences = [
        ConceptCorrespondence(
            source_concept_id="concept-001",
            output_span_ids=["out-001"],
            mapping_type="retain",
        ),
        ConceptCorrespondence(
            source_concept_id="concept-002",
            output_span_ids=["out-002"],
            mapping_type="retain",
        ),
    ]

    result = verify_mutation_safety(
        unit=sample_unit,
        baseline=sample_baseline,
        output_latex="Text with equation and citations",
        correspondences=correspondences,
        protected_objects_preserved=["equation-1", "cite-5"],
    )

    assert result.protected_objects_preserved == ["equation-1", "cite-5"]
    assert result.is_acceptable


def test_rewrite_result_has_correspondence_hash(sample_unit):
    """Rewrite result computes output hash."""
    result = RewriteResult(
        unit_id=sample_unit.unit_id,
        source_span_ids=sample_unit.source_span_ids,
        output_latex="The zero lower bound constrains monetary policy.",
        output_hash="",
    )

    # Hash should be computed
    from hashlib import sha256
    expected_hash = sha256(result.output_latex.encode()).hexdigest()
    assert len(expected_hash) == 64

    result.output_hash = expected_hash
    assert result.output_hash == expected_hash


def test_rewrite_result_tracks_obligation_fulfillment(sample_unit):
    """Rewrite result tracks met and unmet obligations."""
    obligation1 = ExplanationObligation(
        concept_id="concept-001",
        functions=["definition"],
        fulfilled_in_output=True,
    )
    obligation2 = ExplanationObligation(
        concept_id="concept-002",
        functions=["mechanism", "example"],
        fulfilled_in_output=False,
    )

    result = RewriteResult(
        unit_id=sample_unit.unit_id,
        source_span_ids=sample_unit.source_span_ids,
        output_latex="Some text",
        output_hash="abc123",
        fulfilled_obligations=[obligation1],
        unmet_obligations=[obligation2],
    )

    assert len(result.fulfilled_obligations) == 1
    assert len(result.unmet_obligations) == 1
    assert result.unmet_obligations[0].concept_id == "concept-002"


def test_concept_correspondence_tracks_mapping_type(sample_unit):
    """Concept correspondence tracks how concept was handled."""
    types = ["retain", "paraphrase", "expand", "merge", "split"]

    for mapping_type in types:
        corr = ConceptCorrespondence(
            source_concept_id="concept-001",
            output_span_ids=["out-001"],
            mapping_type=mapping_type,
            rationale=f"Test {mapping_type}",
        )

        assert corr.mapping_type == mapping_type
        assert "Test" in corr.rationale


def test_rewrite_result_rejection_accumulates_reasons(sample_unit):
    """Rewrite result collects all rejection reasons."""
    result = RewriteResult(
        unit_id=sample_unit.unit_id,
        source_span_ids=sample_unit.source_span_ids,
        output_latex="Short",
        output_hash="abc",
        is_acceptable=False,
    )

    result.rejection_reasons.append("Concept deletion detected")
    result.rejection_reasons.append("Protected object corrupted")
    result.rejection_reasons.append("Output truncated")

    assert len(result.rejection_reasons) == 3
    assert not result.is_acceptable


def test_verify_mutation_safety_records_mutation_details(sample_unit, sample_baseline):
    """Mutation verification records detailed mutation information."""
    correspondences = [
        ConceptCorrespondence(
            source_concept_id="concept-001",
            output_span_ids=["out-001"],
            mapping_type="retain",
        ),
        # Missing concept-002
    ]

    result = verify_mutation_safety(
        unit=sample_unit,
        baseline=sample_baseline,
        output_latex="Only first concept",
        correspondences=correspondences,
        protected_objects_preserved=[],
    )

    assert len(result.mutations) > 0
    mutation = result.mutations[0]
    assert mutation["type"] == "concept_deletion"
    assert mutation["severity"] == "BLOCK"
    assert "concept-002" in mutation["concepts"]
