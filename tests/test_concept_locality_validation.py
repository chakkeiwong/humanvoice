"""Unit tests for concept locality validation (Phase 1)."""

import pytest
from humanvoice.model_extraction import validate_concept_locality
from humanvoice.concept_extraction import ConceptCandidate


def test_validate_concept_locality_accepts_contiguous():
    """Concepts with spans <10KB apart should pass."""
    concept = ConceptCandidate(
        concept_id='test-001',
        proposition='Test proposition',
        concept_type='definition',
        source_span_ids=['span-1', 'span-2'],
        teaching_roles=['initial'],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )
    span_index = {
        'span-1': {'byte_start': 1000, 'byte_end': 1500},
        'span-2': {'byte_start': 2000, 'byte_end': 2500}
    }

    is_valid, reason = validate_concept_locality(concept, span_index, max_span_range_kb=10)

    assert is_valid is True
    assert reason is None


def test_validate_concept_locality_rejects_large_gap():
    """Concepts with spans >10KB apart should fail."""
    concept = ConceptCandidate(
        concept_id='test-002',
        proposition='Test proposition',
        concept_type='definition',
        source_span_ids=['span-1', 'span-2'],
        teaching_roles=['initial'],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )
    span_index = {
        'span-1': {'byte_start': 1000, 'byte_end': 1500},
        'span-2': {'byte_start': 15000, 'byte_end': 15500}  # 14KB gap
    }

    is_valid, reason = validate_concept_locality(concept, span_index, max_span_range_kb=10)

    assert is_valid is False
    assert 'span_range' in reason
    assert '14500 bytes' in reason


def test_validate_concept_locality_handles_missing_span():
    """Concepts referencing non-existent spans should fail."""
    concept = ConceptCandidate(
        concept_id='test-003',
        proposition='Test proposition',
        concept_type='definition',
        source_span_ids=['span-1', 'span-999'],
        teaching_roles=['initial'],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )
    span_index = {
        'span-1': {'byte_start': 1000, 'byte_end': 1500}
    }

    is_valid, reason = validate_concept_locality(concept, span_index, max_span_range_kb=10)

    assert is_valid is False
    assert 'span_id_not_found' in reason
    assert 'span-999' in reason


def test_validate_concept_locality_handles_no_spans():
    """Concepts with no spans should fail."""
    concept = ConceptCandidate(
        concept_id='test-004',
        proposition='Test proposition',
        concept_type='definition',
        source_span_ids=[],
        teaching_roles=['initial'],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )
    span_index = {}

    is_valid, reason = validate_concept_locality(concept, span_index, max_span_range_kb=10)

    assert is_valid is False
    assert reason == 'no_source_spans'


def test_validate_concept_locality_custom_threshold():
    """Custom threshold should be respected."""
    concept = ConceptCandidate(
        concept_id='test-005',
        proposition='Test proposition',
        concept_type='definition',
        source_span_ids=['span-1', 'span-2'],
        teaching_roles=['initial'],
        supporting_spans=[],
        prerequisites=[],
        confidence=0.9
    )
    span_index = {
        'span-1': {'byte_start': 1000, 'byte_end': 1500},
        'span-2': {'byte_start': 6000, 'byte_end': 6500}  # 5KB gap
    }

    # Should pass with 10KB threshold
    is_valid, _ = validate_concept_locality(concept, span_index, max_span_range_kb=10)
    assert is_valid is True

    # Should fail with 4KB threshold
    is_valid, reason = validate_concept_locality(concept, span_index, max_span_range_kb=4)
    assert is_valid is False
    assert 'span_range' in reason
