"""Tests for concept extraction module."""

import pytest
from humanvoice.concept_extraction import (
    ConceptCandidate,
    ExtractionWindow,
    create_extraction_windows,
    reconcile_duplicates,
    ReconstructionResult,
    CoverageResult,
    ScaffoldingCandidate,
    classify_scaffolding,
    AdjudicationItem,
    surface_ambiguities,
    BaselineSignature,
    freeze_baseline,
)


@pytest.fixture
def sample_spans():
    """Create sample span records for testing."""
    return [
        {
            "record_id": f"span-{i:04d}",
            "byte_start": i * 100,
            "byte_end": (i + 1) * 100,
            "span_kind": "prose",
        }
        for i in range(25)
    ]


def test_create_extraction_windows_basic(sample_spans):
    """Create non-overlapping windows from spans."""
    windows = create_extraction_windows(sample_spans, window_size=10, overlap=0)

    assert len(windows) == 3  # 25 spans / 10 per window = 3 windows
    assert windows[0].window_id == "window-0000"
    assert len(windows[0].span_ids) == 10
    assert len(windows[1].span_ids) == 10
    assert len(windows[2].span_ids) == 5  # remainder


def test_create_extraction_windows_overlap(sample_spans):
    """Windows overlap by specified amount."""
    windows = create_extraction_windows(sample_spans, window_size=10, overlap=3)

    # First window: spans 0-9
    # Second window: spans 7-16 (starts at 10-3=7)
    # Third window: spans 14-23 (starts at 17-3=14)
    # Fourth window: spans 21-24 (starts at 24-3=21)

    assert windows[0].span_ids[-3:] == windows[1].span_ids[:3]  # overlap check


def test_extraction_window_has_adjacent_context(sample_spans):
    """Windows include adjacent spans for context."""
    windows = create_extraction_windows(sample_spans, window_size=10, overlap=0)

    # First window should have no before, but after context
    assert len(windows[0].adjacent_before) == 0
    assert len(windows[0].adjacent_after) == 2
    assert windows[0].adjacent_after == ["span-0010", "span-0011"]

    # Middle window should have both
    assert len(windows[1].adjacent_before) == 2
    assert len(windows[1].adjacent_after) == 2

    # Last window should have before but no after
    assert len(windows[2].adjacent_before) == 2
    assert len(windows[2].adjacent_after) == 0


def test_extraction_window_byte_ranges(sample_spans):
    """Windows track byte ranges for source lookup."""
    windows = create_extraction_windows(sample_spans, window_size=10, overlap=0)

    assert windows[0].byte_start == 0
    assert windows[0].byte_end == 1000  # 10th span ends at 1000

    assert windows[1].byte_start == 1000
    assert windows[1].byte_end == 2000


def test_concept_candidate_structure():
    """ConceptCandidate has required fields."""
    concept = ConceptCandidate(
        concept_id="concept-abc123",
        proposition="The posterior distribution is proportional to prior times likelihood",
        concept_type="definition",
        source_span_ids=["span-0001", "span-0002"],
        teaching_roles=["introduction"],
        confidence=0.95,
    )

    assert concept.concept_id == "concept-abc123"
    assert concept.concept_type == "definition"
    assert len(concept.source_span_ids) == 2
    assert concept.occurrence_count == 1
    assert "introduction" in concept.teaching_roles


def test_concept_candidate_defaults():
    """ConceptCandidate has sensible defaults."""
    concept = ConceptCandidate(
        concept_id="concept-xyz",
        proposition="Test proposition",
        concept_type="claim",
        source_span_ids=["span-0001"],
    )

    assert concept.occurrence_count == 1
    assert concept.teaching_roles == []
    assert concept.supporting_spans == []
    assert concept.prerequisites == []
    assert concept.confidence == 1.0
    assert concept.extraction_window is None


def test_reconcile_duplicates_no_duplicates():
    """Reconcile preserves unique concepts."""
    concepts = [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="First concept",
            concept_type="definition",
            source_span_ids=["span-0001"],
        ),
        ConceptCandidate(
            concept_id="concept-002",
            proposition="Second concept",
            concept_type="claim",
            source_span_ids=["span-0002"],
        ),
    ]

    reconciled, merges = reconcile_duplicates(concepts)

    assert len(reconciled) == 2
    assert len(merges) == 0


def test_reconcile_duplicates_identical_proposition_and_role():
    """Identical propositions with same role merge."""
    concepts = [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="Bayesian inference updates beliefs",
            concept_type="definition",
            source_span_ids=["span-0001"],
            teaching_roles=["introduction"],
        ),
        ConceptCandidate(
            concept_id="concept-002",
            proposition="Bayesian inference updates beliefs",
            concept_type="definition",
            source_span_ids=["span-0010"],
            teaching_roles=["introduction"],
        ),
    ]

    reconciled, merges = reconcile_duplicates(concepts)

    assert len(reconciled) == 1
    assert len(merges) == 1
    assert merges[0] == ("concept-002", "concept-001", "identical_proposition_and_role")
    assert reconciled[0].occurrence_count == 2
    assert set(reconciled[0].source_span_ids) == {"span-0001", "span-0010"}


def test_reconcile_duplicates_different_teaching_roles():
    """Identical propositions with different teaching roles stay separate."""
    concepts = [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="The posterior is proportional to prior times likelihood",
            concept_type="definition",
            source_span_ids=["span-0001"],
            teaching_roles=["introduction"],
        ),
        ConceptCandidate(
            concept_id="concept-002",
            proposition="The posterior is proportional to prior times likelihood",
            concept_type="definition",
            source_span_ids=["span-0050"],
            teaching_roles=["example"],
        ),
        ConceptCandidate(
            concept_id="concept-003",
            proposition="The posterior is proportional to prior times likelihood",
            concept_type="definition",
            source_span_ids=["span-0100"],
            teaching_roles=["derivation"],
        ),
    ]

    reconciled, merges = reconcile_duplicates(concepts)

    # Different teaching roles means distinct pedagogical purposes
    assert len(reconciled) == 3
    assert len(merges) == 0


def test_reconcile_duplicates_normalization():
    """Propositions are normalized for comparison."""
    concepts = [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="Bayesian   inference    updates beliefs",
            concept_type="definition",
            source_span_ids=["span-0001"],
        ),
        ConceptCandidate(
            concept_id="concept-002",
            proposition="BAYESIAN INFERENCE UPDATES BELIEFS",
            concept_type="definition",
            source_span_ids=["span-0002"],
        ),
    ]

    reconciled, merges = reconcile_duplicates(concepts)

    assert len(reconciled) == 1
    assert len(merges) == 1


def test_reconcile_duplicates_preserves_min_confidence():
    """Merged concepts take minimum confidence."""
    concepts = [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="Test concept",
            concept_type="definition",
            source_span_ids=["span-0001"],
            confidence=0.95,
        ),
        ConceptCandidate(
            concept_id="concept-002",
            proposition="Test concept",
            concept_type="definition",
            source_span_ids=["span-0002"],
            confidence=0.85,
        ),
    ]

    reconciled, merges = reconcile_duplicates(concepts)

    assert len(reconciled) == 1
    assert reconciled[0].confidence == 0.85


def test_classify_scaffolding_skips_concept_bearing_spans():
    """Scaffolding classification excludes concept-bearing spans."""
    spans = [
        {"record_id": "span-0001", "coverage_disposition": "unresolved"},
        {"record_id": "span-0002", "coverage_disposition": "unresolved"},
        {"record_id": "span-0003", "coverage_disposition": "protected_structural"},
    ]

    concepts = [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="Test",
            concept_type="definition",
            source_span_ids=["span-0001"],
        ),
    ]

    scaffolding = classify_scaffolding(spans, concepts)

    # span-0001 is concept-bearing, span-0003 is protected, only span-0002 is scaffolding
    assert len(scaffolding) == 1
    assert scaffolding[0].span_id == "span-0002"
    assert scaffolding[0].disposition == "unresolved"


def test_surface_ambiguities_low_confidence_concepts():
    """Surface low-confidence concepts for adjudication."""
    concepts = [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="Clear concept",
            concept_type="definition",
            source_span_ids=["span-0001"],
            confidence=0.95,
        ),
        ConceptCandidate(
            concept_id="concept-002",
            proposition="Ambiguous concept",
            concept_type="claim",
            source_span_ids=["span-0002"],
            confidence=0.65,
        ),
        ConceptCandidate(
            concept_id="concept-003",
            proposition="Very unclear",
            concept_type="mechanism",
            source_span_ids=["span-0003"],
            confidence=0.45,
        ),
    ]

    items = surface_ambiguities(concepts, [])

    # Only low-confidence concepts surface
    assert len(items) == 2
    assert items[0].item_type == "concept_boundary"
    assert items[0].recommended == "accept"  # 0.65 >= 0.5
    assert items[1].recommended == "revise_boundary"  # 0.45 < 0.5


def test_surface_ambiguities_unresolved_scaffolding():
    """Surface unresolved scaffolding for disposition."""
    scaffolding = [
        ScaffoldingCandidate(
            span_id="span-0010",
            disposition="unresolved",
            adjudication_required=True,
            reason="unclear_purpose",
        ),
        ScaffoldingCandidate(
            span_id="span-0011",
            disposition="remove_nonconcept",
            adjudication_required=False,
            reason="clearly_nonconcept",
        ),
    ]

    items = surface_ambiguities([], scaffolding)

    # Only adjudication_required=True surfaces
    assert len(items) == 1
    assert items[0].item_type == "scaffolding_disposition"
    assert items[0].item_id == "span-0010"


def test_surface_ambiguities_reconstruction_failures():
    """Surface concepts that failed reconstruction."""
    reconstruction = ReconstructionResult(
        verified_concepts=["concept-001"],
        missing_concepts=["concept-002", "concept-003"],
        extra_spans=[],
        confidence=0.8,
    )

    items = surface_ambiguities([], [], reconstruction=reconstruction)

    assert len(items) == 2
    assert all(item.item_type == "concept_boundary" for item in items)
    assert all(item.recommended == "revise_spans" for item in items)


def test_surface_ambiguities_coverage_gaps():
    """Surface spans not covered by any concept."""
    coverage = CoverageResult(
        covered_spans={"span-0001", "span-0002"},
        uncovered_spans={"span-0003", "span-0004"},
        concept_to_spans={},
        confidence=0.9,
    )

    items = surface_ambiguities([], [], coverage=coverage)

    assert len(items) == 2
    assert all(item.item_type == "concept_boundary" for item in items)
    assert "extract_concept" in items[0].options


def test_freeze_baseline_generates_stable_hash():
    """Baseline hash is deterministic from content."""
    spans = [{"record_id": "span-0001"}]
    concepts = [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="Test",
            concept_type="definition",
            source_span_ids=["span-0001"],
        ),
    ]
    scaffolding = []

    sig1 = freeze_baseline(
        snapshot_id="snap-123",
        source_hash="abc123",
        spans=spans,
        concepts=concepts,
        scaffolding=scaffolding,
        adjudicator_id="reviewer-1",
        adjudication_date="2026-09-11T12:00:00Z",
    )

    sig2 = freeze_baseline(
        snapshot_id="snap-123",
        source_hash="abc123",
        spans=spans,
        concepts=concepts,
        scaffolding=scaffolding,
        adjudicator_id="reviewer-1",
        adjudication_date="2026-09-11T12:00:00Z",
    )

    assert sig1.baseline_hash == sig2.baseline_hash
    assert len(sig1.baseline_hash) == 64  # SHA-256


def test_freeze_baseline_changes_with_content():
    """Different content produces different hash."""
    spans = [{"record_id": "span-0001"}]
    concepts1 = [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="First",
            concept_type="definition",
            source_span_ids=["span-0001"],
        ),
    ]
    concepts2 = [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="Second",
            concept_type="definition",
            source_span_ids=["span-0001"],
        ),
    ]

    sig1 = freeze_baseline(
        snapshot_id="snap-123",
        source_hash="abc123",
        spans=spans,
        concepts=concepts1,
        scaffolding=[],
        adjudicator_id="reviewer-1",
        adjudication_date="2026-09-11T12:00:00Z",
    )

    sig2 = freeze_baseline(
        snapshot_id="snap-123",
        source_hash="abc123",
        spans=spans,
        concepts=concepts2,
        scaffolding=[],
        adjudicator_id="reviewer-1",
        adjudication_date="2026-09-11T12:00:00Z",
    )

    assert sig1.baseline_hash != sig2.baseline_hash


def test_freeze_baseline_counts_unresolved():
    """Baseline counts unresolved items."""
    spans = [{"record_id": f"span-{i:04d}"} for i in range(5)]
    concepts = [
        ConceptCandidate(
            concept_id="concept-001",
            proposition="Clear",
            concept_type="definition",
            source_span_ids=["span-0001"],
            confidence=0.95,
        ),
        ConceptCandidate(
            concept_id="concept-002",
            proposition="Unclear",
            concept_type="claim",
            source_span_ids=["span-0002"],
            confidence=0.65,
        ),
    ]
    scaffolding = [
        ScaffoldingCandidate(
            span_id="span-0003",
            disposition="unresolved",
        ),
        ScaffoldingCandidate(
            span_id="span-0004",
            disposition="remove_nonconcept",
        ),
    ]

    sig = freeze_baseline(
        snapshot_id="snap-123",
        source_hash="abc123",
        spans=spans,
        concepts=concepts,
        scaffolding=scaffolding,
        adjudicator_id="reviewer-1",
        adjudication_date="2026-09-11T12:00:00Z",
    )

    assert sig.total_spans == 5
    assert sig.total_concepts == 2
    assert sig.unresolved_items == 2  # 1 low-confidence concept + 1 unresolved scaffolding



