"""
Tests for concept locality validation.

Concept locality ensures that all spans referenced by a concept are within
a reasonable distance (default 10KB) of each other. This prevents concepts
from spanning 140KB gaps which breaks assembly.
"""

import pytest
from humanvoice.model_extraction import validate_concept_locality
from humanvoice.concept_extraction import ConceptCandidate


def test_validate_concept_locality_accepts_contiguous_spans():
    """Concepts with spans close together (<10KB) should be accepted."""
    concept = ConceptCandidate(
        concept_id="concept-001",
        proposition="Test concept with nearby spans",
        concept_type="definition",
        source_span_ids=["span-001", "span-002", "span-003"],
        teaching_roles=["definition"],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )

    # Spans within 2KB range
    span_offsets = {
        "span-001": {"byte_start": 1000, "byte_end": 1500},
        "span-002": {"byte_start": 2000, "byte_end": 2500},
        "span-003": {"byte_start": 3000, "byte_end": 3500}
    }

    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)

    assert is_valid
    assert reason is None


def test_validate_concept_locality_rejects_large_span_range():
    """Concepts with spans >10KB apart should be rejected."""
    concept = ConceptCandidate(
        concept_id="concept-042",
        proposition="Zero lower bound",
        concept_type="definition",
        source_span_ids=["span-001", "span-002"],
        teaching_roles=["definition"],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )

    # Total range from first start to last end: 14500 bytes (14.2KB)
    span_offsets = {
        "span-001": {"byte_start": 1000, "byte_end": 1500},
        "span-002": {"byte_start": 15000, "byte_end": 15500}
    }

    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)

    assert not is_valid
    assert "span_range_exceeds_threshold" in reason
    assert "14500 bytes" in reason or "14.2KB" in reason


def test_validate_concept_locality_handles_single_span():
    """Concepts with single span should always be valid."""
    concept = ConceptCandidate(
        concept_id="concept-003",
        proposition="Single span concept",
        concept_type="definition",
        source_span_ids=["span-001"],
        teaching_roles=["definition"],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )

    span_offsets = {
        "span-001": {"byte_start": 1000, "byte_end": 5000}  # 4KB span
    }

    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)

    assert is_valid
    assert reason is None


def test_validate_concept_locality_rejects_missing_spans():
    """Concepts referencing non-existent spans should be rejected."""
    concept = ConceptCandidate(
        concept_id="concept-004",
        proposition="Concept with missing span",
        concept_type="definition",
        source_span_ids=["span-001", "span-999"],
        teaching_roles=["definition"],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )

    span_offsets = {
        "span-001": {"byte_start": 1000, "byte_end": 1500}
        # span-999 missing
    }

    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)

    assert not is_valid
    assert "span_id_not_found" in reason
    assert "span-999" in reason


def test_validate_concept_locality_rejects_no_spans():
    """Concepts with no source_span_ids should be rejected."""
    concept = ConceptCandidate(
        concept_id="concept-005",
        proposition="Concept with no spans",
        concept_type="definition",
        source_span_ids=[],
        teaching_roles=["definition"],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )

    span_offsets = {}

    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)

    assert not is_valid
    assert reason == "no_source_spans"


def test_validate_concept_locality_accepts_exactly_at_threshold():
    """Concepts at exactly 10KB range should be accepted."""
    concept = ConceptCandidate(
        concept_id="concept-006",
        proposition="Concept at threshold",
        concept_type="definition",
        source_span_ids=["span-001", "span-002"],
        teaching_roles=["definition"],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )

    # Exactly 10KB range: start=0, end=10240 (10240 bytes total range)
    span_offsets = {
        "span-001": {"byte_start": 0, "byte_end": 500},
        "span-002": {"byte_start": 9740, "byte_end": 10240}
    }

    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)

    assert is_valid
    assert reason is None


def test_validate_concept_locality_rejects_just_over_threshold():
    """Concepts just over 10KB threshold should be rejected."""
    concept = ConceptCandidate(
        concept_id="concept-007",
        proposition="Concept just over threshold",
        concept_type="definition",
        source_span_ids=["span-001", "span-002"],
        teaching_roles=["definition"],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )

    # 10KB + 1 byte: start=0, end=10241 (10241 bytes total range)
    span_offsets = {
        "span-001": {"byte_start": 0, "byte_end": 500},
        "span-002": {"byte_start": 9741, "byte_end": 10241}
    }

    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)

    assert not is_valid
    assert "span_range_exceeds_threshold" in reason


def test_validate_concept_locality_handles_unordered_spans():
    """Validation should work regardless of span_id order."""
    concept = ConceptCandidate(
        concept_id="concept-008",
        proposition="Concept with unordered spans",
        concept_type="definition",
        source_span_ids=["span-003", "span-001", "span-002"],  # Unordered
        teaching_roles=["definition"],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )

    span_offsets = {
        "span-001": {"byte_start": 1000, "byte_end": 1500},
        "span-002": {"byte_start": 2000, "byte_end": 2500},
        "span-003": {"byte_start": 3000, "byte_end": 3500}
    }

    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)

    assert is_valid
    assert reason is None


def test_validate_concept_locality_configurable_threshold():
    """Threshold should be configurable."""
    concept = ConceptCandidate(
        concept_id="concept-009",
        proposition="Concept with configurable threshold",
        concept_type="definition",
        source_span_ids=["span-001", "span-002"],
        teaching_roles=["definition"],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )

    # 15KB range
    span_offsets = {
        "span-001": {"byte_start": 1000, "byte_end": 1500},
        "span-002": {"byte_start": 16000, "byte_end": 16500}
    }

    # Rejected with 10KB threshold
    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)
    assert not is_valid

    # Accepted with 20KB threshold
    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=20)
    assert is_valid
    assert reason is None
