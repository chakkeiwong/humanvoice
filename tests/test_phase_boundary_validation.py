"""Tests for phase boundary validation (fail-closed checks)."""

import json
import pytest
from pathlib import Path
from humanvoice.concept_baseline import ConceptBaseline, ConceptBaselineEntry
from humanvoice.semantic_unit_splitting import RewritePlan, RewriteUnit
from humanvoice.commands.plan_v2_command import (
    validate_plan,
    check_unit_contiguity,
    find_overlapping_units,
    get_unit_byte_range,
)


# Test fixtures
@pytest.fixture
def span_offsets():
    """Sample span offsets for testing."""
    return {
        "span-001": {"byte_start": 1000, "byte_end": 1500},
        "span-002": {"byte_start": 2000, "byte_end": 2500},
        "span-003": {"byte_start": 3000, "byte_end": 3500},
        "span-004": {"byte_start": 15000, "byte_end": 15500},  # Large gap
    }


@pytest.fixture
def contiguous_unit():
    """Unit with contiguous spans."""
    return RewriteUnit(
        unit_id="unit-001",
        concept_ids=["concept-001", "concept-002"],
        source_span_ids=["span-001", "span-002"],
        prerequisites=[],
        estimated_words=200,
    )


@pytest.fixture
def non_contiguous_unit():
    """Unit with non-contiguous spans (>10KB gap)."""
    return RewriteUnit(
        unit_id="unit-002",
        concept_ids=["concept-003"],
        source_span_ids=["span-001", "span-004"],  # 13.5KB gap
        prerequisites=[],
        estimated_words=100,
    )


# Test check_unit_contiguity
def test_check_unit_contiguity_accepts_contiguous(contiguous_unit, span_offsets):
    """Contiguous unit should pass validation."""
    is_valid, reason = check_unit_contiguity(contiguous_unit, span_offsets, max_gap_kb=10)

    assert is_valid
    assert reason is None


def test_check_unit_contiguity_rejects_non_contiguous(non_contiguous_unit, span_offsets):
    """Non-contiguous unit with gap >10KB should fail validation."""
    is_valid, reason = check_unit_contiguity(non_contiguous_unit, span_offsets, max_gap_kb=10)

    assert not is_valid
    assert "non_contiguous" in reason
    assert "13.2KB" in reason or "13.5KB" in reason  # Allow for rounding differences


def test_check_unit_contiguity_missing_span():
    """Unit with missing span ID should fail validation."""
    unit = RewriteUnit(
        unit_id="unit-003",
        concept_ids=["concept-001"],
        source_span_ids=["span-999"],  # Doesn't exist
        prerequisites=[],
        estimated_words=100,
    )
    span_offsets = {"span-001": {"byte_start": 1000, "byte_end": 1500}}

    is_valid, reason = check_unit_contiguity(unit, span_offsets, max_gap_kb=10)

    assert not is_valid
    assert "span_id_not_found" in reason


def test_check_unit_contiguity_empty_spans():
    """Unit with no spans should pass validation (edge case)."""
    unit = RewriteUnit(
        unit_id="unit-004",
        concept_ids=["concept-001"],
        source_span_ids=[],
        prerequisites=[],
        estimated_words=0,
    )
    span_offsets = {}

    is_valid, reason = check_unit_contiguity(unit, span_offsets, max_gap_kb=10)

    assert is_valid
    assert reason is None


# Test get_unit_byte_range
def test_get_unit_byte_range(contiguous_unit, span_offsets):
    """Should return min-max byte range for unit's spans."""
    start, end = get_unit_byte_range(contiguous_unit, span_offsets)

    assert start == 1000  # span-001 start
    assert end == 2500    # span-002 end


def test_get_unit_byte_range_unsorted_spans(span_offsets):
    """Should handle unsorted span IDs."""
    unit = RewriteUnit(
        unit_id="unit-005",
        concept_ids=["concept-001"],
        source_span_ids=["span-003", "span-001", "span-002"],  # Unsorted
        prerequisites=[],
        estimated_words=300,
    )

    start, end = get_unit_byte_range(unit, span_offsets)

    assert start == 1000  # span-001 start (earliest)
    assert end == 3500    # span-003 end (latest)


def test_get_unit_byte_range_missing_spans():
    """Should return None, None when no spans exist."""
    unit = RewriteUnit(
        unit_id="unit-006",
        concept_ids=["concept-001"],
        source_span_ids=["span-999"],
        prerequisites=[],
        estimated_words=0,
    )
    span_offsets = {}

    start, end = get_unit_byte_range(unit, span_offsets)

    assert start is None
    assert end is None


# Test find_overlapping_units
def test_find_overlapping_units_no_overlaps(contiguous_unit, span_offsets):
    """Non-overlapping units should return empty list."""
    unit2 = RewriteUnit(
        unit_id="unit-002",
        concept_ids=["concept-003"],
        source_span_ids=["span-003"],
        prerequisites=[],
        estimated_words=100,
    )

    units = [contiguous_unit, unit2]
    overlaps = find_overlapping_units(units, span_offsets)

    assert len(overlaps) == 0


def test_find_overlapping_units_detects_overlap(span_offsets):
    """Overlapping units should be detected."""
    unit1 = RewriteUnit(
        unit_id="unit-001",
        concept_ids=["concept-001"],
        source_span_ids=["span-001", "span-002"],  # 1000-2500
        prerequisites=[],
        estimated_words=200,
    )

    unit2 = RewriteUnit(
        unit_id="unit-002",
        concept_ids=["concept-002"],
        source_span_ids=["span-002", "span-003"],  # 2000-3500 (overlaps at span-002)
        prerequisites=[],
        estimated_words=200,
    )

    units = [unit1, unit2]
    overlaps = find_overlapping_units(units, span_offsets)

    assert len(overlaps) == 1
    assert overlaps[0] == ("unit-001", "unit-002")


def test_find_overlapping_units_multiple_overlaps(span_offsets):
    """Multiple overlapping pairs should all be detected."""
    unit1 = RewriteUnit(
        unit_id="unit-001",
        concept_ids=["concept-001"],
        source_span_ids=["span-001", "span-002", "span-003"],  # 1000-3500
        prerequisites=[],
        estimated_words=300,
    )

    unit2 = RewriteUnit(
        unit_id="unit-002",
        concept_ids=["concept-002"],
        source_span_ids=["span-002"],  # 2000-2500 (overlaps with unit1)
        prerequisites=[],
        estimated_words=100,
    )

    unit3 = RewriteUnit(
        unit_id="unit-003",
        concept_ids=["concept-003"],
        source_span_ids=["span-003"],  # 3000-3500 (overlaps with unit1)
        prerequisites=[],
        estimated_words=100,
    )

    units = [unit1, unit2, unit3]
    overlaps = find_overlapping_units(units, span_offsets)

    assert len(overlaps) == 2
    assert ("unit-001", "unit-002") in overlaps
    assert ("unit-001", "unit-003") in overlaps


# Test validate_plan (integration test with temp directory)
def test_validate_plan_all_valid(tmp_path, contiguous_unit, span_offsets):
    """Valid plan should return empty error list."""
    # Create minimal snapshot directory structure
    inventory_dir = tmp_path / ".humanvoice" / "inventory"
    inventory_dir.mkdir(parents=True, exist_ok=True)

    # Write spans.jsonl
    spans_path = inventory_dir / "spans.jsonl"
    with open(spans_path, 'w') as f:
        for span_id, offsets in span_offsets.items():
            record = {
                "record_id": span_id,
                "byte_start": offsets["byte_start"],
                "byte_end": offsets["byte_end"],
            }
            f.write(json.dumps(record) + "\n")

    # Create baseline with concepts
    baseline = ConceptBaseline(
        baseline_id="baseline-test-001",
        snapshot_id="snapshot-test-001",
        source_hash="abc123",
        concept_entries=[
            ConceptBaselineEntry(
                concept_id="concept-001",
                proposition="Test concept 1",
                concept_type="definition",
                source_span_ids=["span-001"],
                teaching_roles=[],
                supporting_spans=[],
                prerequisites=[],
                confidence=0.9,
                adjudication_status="accepted",
                human_rationale=None
            ),
            ConceptBaselineEntry(
                concept_id="concept-002",
                proposition="Test concept 2",
                concept_type="definition",
                source_span_ids=["span-002"],
                teaching_roles=[],
                supporting_spans=[],
                prerequisites=[],
                confidence=0.9,
                adjudication_status="accepted",
                human_rationale=None
            ),
        ],
        total_concepts=2,
        frozen_at="2026-09-21T00:00:00Z",
        frozen_by="test",
        adjudication_session_id=None,
        baseline_hash="test-hash"
    )

    # Create valid plan
    plan = RewritePlan(
        plan_id="plan-test-001",
        baseline_id="baseline-test-001",
        snapshot_id="snapshot-test-001",
        units=[contiguous_unit],
        total_units=1,
        total_concepts=2,
        max_unit_size=2000,
    )

    errors = validate_plan(plan, baseline, tmp_path)

    assert len(errors) == 0


def test_validate_plan_detects_non_contiguous(tmp_path, non_contiguous_unit, span_offsets):
    """Plan with non-contiguous unit should return errors."""
    # Create minimal snapshot directory structure
    inventory_dir = tmp_path / ".humanvoice" / "inventory"
    inventory_dir.mkdir(parents=True, exist_ok=True)

    # Write spans.jsonl
    spans_path = inventory_dir / "spans.jsonl"
    with open(spans_path, 'w') as f:
        for span_id, offsets in span_offsets.items():
            record = {
                "record_id": span_id,
                "byte_start": offsets["byte_start"],
                "byte_end": offsets["byte_end"],
            }
            f.write(json.dumps(record) + "\n")

    # Create baseline
    baseline = ConceptBaseline(
        baseline_id="baseline-test-002",
        snapshot_id="snapshot-test-002",
        source_hash="abc123",
        concept_entries=[
            ConceptBaselineEntry(
                concept_id="concept-003",
                proposition="Test concept 3",
                concept_type="definition",
                source_span_ids=["span-001", "span-004"],
                teaching_roles=[],
                supporting_spans=[],
                prerequisites=[],
                confidence=0.9,
                adjudication_status="accepted",
                human_rationale=None
            ),
        ],
        total_concepts=1,
        frozen_at="2026-09-21T00:00:00Z",
        frozen_by="test",
        adjudication_session_id=None,
        baseline_hash="test-hash"
    )

    # Create plan with non-contiguous unit
    plan = RewritePlan(
        plan_id="plan-test-002",
        baseline_id="baseline-test-002",
        snapshot_id="snapshot-test-002",
        units=[non_contiguous_unit],
        total_units=1,
        total_concepts=1,
        max_unit_size=2000,
    )

    errors = validate_plan(plan, baseline, tmp_path)

    assert len(errors) > 0
    assert any("non_contiguous" in error for error in errors)


def test_validate_plan_detects_overlaps(tmp_path, span_offsets):
    """Plan with overlapping units should return errors."""
    # Create minimal snapshot directory structure
    inventory_dir = tmp_path / ".humanvoice" / "inventory"
    inventory_dir.mkdir(parents=True, exist_ok=True)

    # Write spans.jsonl
    spans_path = inventory_dir / "spans.jsonl"
    with open(spans_path, 'w') as f:
        for span_id, offsets in span_offsets.items():
            record = {
                "record_id": span_id,
                "byte_start": offsets["byte_start"],
                "byte_end": offsets["byte_end"],
            }
            f.write(json.dumps(record) + "\n")

    # Create baseline
    baseline = ConceptBaseline(
        baseline_id="baseline-test-003",
        snapshot_id="snapshot-test-003",
        source_hash="abc123",
        concept_entries=[
            ConceptBaselineEntry(
                concept_id="concept-001",
                proposition="Test concept 1",
                concept_type="definition",
                source_span_ids=["span-001", "span-002"],
                teaching_roles=[],
                supporting_spans=[],
                prerequisites=[],
                confidence=0.9,
                adjudication_status="accepted",
                human_rationale=None
            ),
            ConceptBaselineEntry(
                concept_id="concept-002",
                proposition="Test concept 2",
                concept_type="definition",
                source_span_ids=["span-002", "span-003"],
                teaching_roles=[],
                supporting_spans=[],
                prerequisites=[],
                confidence=0.9,
                adjudication_status="accepted",
                human_rationale=None
            ),
        ],
        total_concepts=2,
        frozen_at="2026-09-21T00:00:00Z",
        frozen_by="test",
        adjudication_session_id=None,
        baseline_hash="test-hash"
    )

    # Create plan with overlapping units
    unit1 = RewriteUnit(
        unit_id="unit-001",
        concept_ids=["concept-001"],
        source_span_ids=["span-001", "span-002"],  # 1000-2500
        prerequisites=[],
        estimated_words=200,
    )

    unit2 = RewriteUnit(
        unit_id="unit-002",
        concept_ids=["concept-002"],
        source_span_ids=["span-002", "span-003"],  # 2000-3500
        prerequisites=[],
        estimated_words=200,
    )

    plan = RewritePlan(
        plan_id="plan-test-003",
        baseline_id="baseline-test-003",
        snapshot_id="snapshot-test-003",
        units=[unit1, unit2],
        total_units=2,
        total_concepts=2,
        max_unit_size=2000,
    )

    errors = validate_plan(plan, baseline, tmp_path)

    assert len(errors) > 0
    assert any("Overlapping units" in error for error in errors)


def test_validate_plan_missing_spans_file(tmp_path):
    """Plan validation should handle missing spans.jsonl gracefully."""
    # Don't create spans.jsonl

    # Create empty baseline
    baseline = ConceptBaseline(
        baseline_id="baseline-test-004",
        snapshot_id="snapshot-test-004",
        source_hash="abc123",
        concept_entries=[],
        total_concepts=0,
        frozen_at="2026-09-21T00:00:00Z",
        frozen_by="test",
        adjudication_session_id=None,
        baseline_hash="test-hash"
    )

    plan = RewritePlan(
        plan_id="plan-test-004",
        baseline_id="baseline-test-004",
        snapshot_id="snapshot-test-004",
        units=[],
        total_units=0,
        total_concepts=0,
        max_unit_size=2000,
    )

    errors = validate_plan(plan, baseline, tmp_path)

    assert len(errors) > 0
    assert any("Missing spans.jsonl" in error for error in errors)
