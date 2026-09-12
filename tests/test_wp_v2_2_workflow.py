"""
Tests for WP-V2-2 complete workflow.

Tests the integration of all WP-V2-2 phases:
- Phase 4: Model extraction with critics
- Phase 5: Ambiguity adjudication
- Phase 6: Frozen baseline
- Phase 7: Dependency planning
- Phase 8: Semantic unit splitting
"""

import pytest
from pathlib import Path
from humanvoice.concept_extraction import ConceptCandidate
from humanvoice.ambiguity_adjudication import (
    identify_ambiguities,
    create_adjudication_session,
    apply_adjudication,
    AmbiguityCase,
)
from humanvoice.concept_baseline import (
    create_baseline_from_adjudication,
    compute_baseline_hash,
    verify_baseline_integrity,
    ConceptBaselineEntry,
)
from humanvoice.dependency_planning import (
    create_dependency_graph,
    detect_cycles,
    topological_sort,
    verify_teaching_order,
    ConceptDependency,
)
from humanvoice.semantic_unit_splitting import (
    create_rewrite_plan,
    estimate_unit_size,
    verify_unit_plan_completeness,
)


@pytest.fixture
def sample_concepts():
    """Sample concepts for testing."""
    return [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="Zero lower bound constrains monetary policy",
            concept_type="claim",
            source_span_ids=["span-001", "span-002"],
            teaching_roles=["initial"],
            supporting_spans=[],
            prerequisites=[],
            confidence=0.95,
        ),
        ConceptCandidate(
            concept_id="concept-002",
            proposition="Taylor rule guides interest rate decisions",
            concept_type="mechanism",
            source_span_ids=["span-003", "span-004"],
            teaching_roles=["initial"],
            supporting_spans=[],
            prerequisites=["concept-001"],
            confidence=0.85,
        ),
        ConceptCandidate(
            concept_id="concept-003",
            proposition="Forward guidance affects expectations",
            concept_type="mechanism",
            source_span_ids=["span-005"],
            teaching_roles=["initial"],
            supporting_spans=[],
            prerequisites=["concept-001"],
            confidence=0.60,  # Low confidence - should trigger adjudication
        ),
    ]


@pytest.fixture
def sample_baseline(sample_concepts, tmp_path):
    """Create a sample frozen baseline."""
    from humanvoice.concept_baseline import ConceptBaseline

    entries = []
    for concept in sample_concepts[:2]:  # Only first 2 (high confidence)
        entries.append(ConceptBaselineEntry(
            concept_id=concept.concept_id,
            proposition=concept.proposition,
            concept_type=concept.concept_type,
            source_span_ids=concept.source_span_ids,
            teaching_roles=concept.teaching_roles,
            supporting_spans=concept.supporting_spans,
            prerequisites=concept.prerequisites,
            confidence=concept.confidence,
            adjudication_status="accepted",
        ))

    baseline = ConceptBaseline(
        baseline_id="baseline-test-001",
        snapshot_id="snapshot-test",
        source_hash="abc123",
        concept_entries=entries,
        total_concepts=len(entries),
        frozen_at="2026-09-12T00:00:00Z",
        frozen_by="test-user",
    )
    baseline.baseline_hash = compute_baseline_hash(baseline)

    return baseline


def test_identify_ambiguities_low_confidence(sample_concepts):
    """Ambiguities identified for low-confidence concepts."""
    from humanvoice.model_extraction import ExtractionResult

    # Create extraction result with low-confidence concept
    result = ExtractionResult(
        window_index=0,
        concepts=sample_concepts,
        abstentions=[],
    )

    cases = identify_ambiguities(
        extraction_results=[result],
        reconstruction_verdicts=[],
        coverage_verdicts=[],
        confidence_threshold=0.7,
    )

    # Should identify concept-003 as low confidence
    assert len(cases) == 1
    assert cases[0].case_type == "low_confidence"
    assert cases[0].concept_id == "concept-003"
    assert cases[0].confidence == 0.60


def test_adjudication_session_creation(sample_concepts):
    """Adjudication session created with all cases."""
    from humanvoice.model_extraction import ExtractionResult

    result = ExtractionResult(
        window_index=0,
        concepts=sample_concepts,
        abstentions=[],
    )

    cases = identify_ambiguities([result], [], [], confidence_threshold=0.7)
    session = create_adjudication_session("snapshot-test", cases)

    assert session.snapshot_id == "snapshot-test"
    assert session.total_cases == 1
    assert session.adjudicated_count == 0
    assert len(session.cases) == 1


def test_apply_adjudication():
    """Human adjudication applied to case."""
    case = AmbiguityCase(
        case_id="ambig-0001",
        case_type="low_confidence",
        window_id="window-001",
        span_ids=["span-005"],
        concept_id="concept-003",
        extractor_claim="Forward guidance affects expectations",
        confidence=0.60,
    )

    updated_case = apply_adjudication(
        case=case,
        disposition="accept",
        rationale="Concept is correct but spans are ambiguous",
        adjudicator="test-reviewer",
    )

    assert updated_case.human_disposition == "accept"
    assert updated_case.human_rationale == "Concept is correct but spans are ambiguous"
    assert updated_case.adjudicator == "test-reviewer"
    assert updated_case.adjudicated_at is not None


def test_baseline_hash_computation(sample_baseline):
    """Baseline hash computed deterministically."""
    hash1 = compute_baseline_hash(sample_baseline)
    hash2 = compute_baseline_hash(sample_baseline)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 hex digest


def test_baseline_integrity_verification(sample_baseline):
    """Baseline integrity verified via hash."""
    is_valid, message = verify_baseline_integrity(sample_baseline)

    assert is_valid
    assert "verified" in message.lower()


def test_baseline_integrity_fails_on_tampering(sample_baseline):
    """Baseline integrity check fails if content changed."""
    # Tamper with baseline
    sample_baseline.concept_entries[0].proposition = "TAMPERED"

    is_valid, message = verify_baseline_integrity(sample_baseline)

    assert not is_valid
    assert "mismatch" in message.lower()


def test_dependency_graph_creation(sample_baseline):
    """Dependency graph created from baseline."""
    graph = create_dependency_graph(sample_baseline)

    assert graph.baseline_id == sample_baseline.baseline_id
    assert len(graph.dependencies) == 1  # concept-002 depends on concept-001
    assert graph.dependencies[0].dependent_concept_id == "concept-002"
    assert graph.dependencies[0].prerequisite_concept_id == "concept-001"


def test_dependency_cycle_detection():
    """Circular dependencies detected."""
    # Create circular dependencies: A -> B -> C -> A
    deps = [
        ConceptDependency("concept-A", "concept-B", "definition"),
        ConceptDependency("concept-B", "concept-C", "definition"),
        ConceptDependency("concept-C", "concept-A", "definition"),
    ]

    concept_ids = {"concept-A", "concept-B", "concept-C"}
    cycles = detect_cycles(deps, concept_ids)

    assert len(cycles) > 0
    # Should detect the cycle A -> B -> C -> A


def test_topological_sort_valid_order(sample_baseline):
    """Topological sort produces valid teaching order."""
    graph = create_dependency_graph(sample_baseline)
    concept_ids = {entry.concept_id for entry in sample_baseline.concept_entries}

    teaching_order = topological_sort(graph.dependencies, concept_ids)

    assert teaching_order is not None
    assert len(teaching_order) == 2
    # concept-001 should come before concept-002
    assert teaching_order.index("concept-001") < teaching_order.index("concept-002")


def test_teaching_order_verification(sample_baseline):
    """Teaching order verified against dependencies."""
    graph = create_dependency_graph(sample_baseline)

    # Valid order
    valid_order = ["concept-001", "concept-002"]
    is_valid, violations = verify_teaching_order(valid_order, graph.dependencies)
    assert is_valid
    assert len(violations) == 0

    # Invalid order (reversed)
    invalid_order = ["concept-002", "concept-001"]
    is_valid, violations = verify_teaching_order(invalid_order, graph.dependencies)
    assert not is_valid
    assert len(violations) == 1


def test_unit_size_estimation(sample_baseline):
    """Unit size estimated from source spans."""
    span_texts = {
        "span-001": "The zero lower bound constraint",
        "span-002": "limits monetary policy effectiveness",
        "span-003": "Taylor rule guides",
        "span-004": "interest rate decisions",
    }

    # Estimate for first concept
    size = estimate_unit_size(["concept-001"], sample_baseline, span_texts)

    # Should have some non-zero estimate
    assert size > 0
    # Should apply expansion factor (rough check)
    source_words = len("The zero lower bound constraint limits monetary policy effectiveness".split())
    assert size >= source_words  # At least as big as source


def test_rewrite_plan_creation(sample_baseline, tmp_path):
    """Rewrite plan created with units."""
    from humanvoice.dependency_planning import load_dependency_graph, save_dependency_graph

    # Create and save dependency graph
    graph = create_dependency_graph(sample_baseline)
    deps_path = tmp_path / "deps.json"
    save_dependency_graph(graph, deps_path)

    span_texts = {
        "span-001": "The zero lower bound",
        "span-002": "limits policy",
        "span-003": "Taylor rule",
        "span-004": "guides rates",
    }

    plan = create_rewrite_plan(
        baseline=sample_baseline,
        dependency_graph=graph,
        span_texts=span_texts,
        max_unit_size=2000,
    )

    assert plan.baseline_id == sample_baseline.baseline_id
    assert plan.total_units >= 1
    assert plan.total_concepts == 2


def test_rewrite_plan_completeness(sample_baseline):
    """Rewrite plan covers all concepts exactly once."""
    graph = create_dependency_graph(sample_baseline)
    span_texts = {
        "span-001": "text1",
        "span-002": "text2",
        "span-003": "text3",
        "span-004": "text4",
    }

    plan = create_rewrite_plan(sample_baseline, graph, span_texts, max_unit_size=2000)

    is_complete, issues = verify_unit_plan_completeness(plan, sample_baseline)

    assert is_complete
    assert len(issues) == 0


def test_unit_splitting_respects_size_limit(sample_baseline):
    """Concepts split into multiple units when possible."""
    graph = create_dependency_graph(sample_baseline)

    # Create moderate span texts - concept-001 smaller, concept-002 larger
    span_texts = {
        "span-001": " ".join(["word"] * 200),  # 200 words -> ~300 estimated
        "span-002": " ".join(["word"] * 200),  # 200 words -> ~300 estimated
        "span-003": " ".join(["word"] * 800),  # 800 words -> ~1200 estimated
        "span-004": " ".join(["word"] * 800),  # 800 words -> ~1200 estimated
    }

    plan = create_rewrite_plan(
        baseline=sample_baseline,
        dependency_graph=graph,
        span_texts=span_texts,
        max_unit_size=1000,  # Should force split between concepts
    )

    # Should create 2 units: concept-001 alone, concept-002 alone
    # (because combined they'd exceed 1000 words)
    assert plan.total_units == 2

    # Verify concepts are distributed
    all_concepts = []
    for unit in plan.units:
        all_concepts.extend(unit.concept_ids)
    assert len(all_concepts) == 2
    assert "concept-001" in all_concepts
    assert "concept-002" in all_concepts
