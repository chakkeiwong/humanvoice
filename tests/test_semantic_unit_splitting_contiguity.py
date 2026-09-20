"""Tests for Phase 2: Planner Contiguity Enforcement.

Validates that semantic_unit_splitting enforces span contiguity:
- Units with contiguous spans (gap < 10KB) remain single units
- Units with large gaps (> 10KB) are split into multiple units
- Concepts are correctly distributed across clusters
"""

import pytest
from pathlib import Path
import json
from dataclasses import dataclass, field
from humanvoice.semantic_unit_splitting import (
    build_span_clusters,
    finalize_unit,
    RewriteUnit,
)


# Mock dependency graph
@dataclass
class MockDependency:
    prerequisite_concept_id: str
    dependent_concept_id: str


@dataclass
class MockDependencyGraph:
    dependencies: list = field(default_factory=list)
    teaching_order: list = field(default_factory=list)


# Mock baseline
@dataclass
class MockConceptEntry:
    concept_id: str
    source_span_ids: list[str]
    content: str = ""


@dataclass
class MockBaseline:
    concept_entries: list = field(default_factory=list)


def test_build_span_clusters_single_cluster_contiguous():
    """Contiguous spans should produce single cluster."""
    span_records = {
        "span-001": {"byte_start": 1000, "byte_end": 1500},
        "span-002": {"byte_start": 1600, "byte_end": 2000},  # 100 byte gap
        "span-003": {"byte_start": 2100, "byte_end": 2500},  # 100 byte gap
    }
    span_ids = {"span-001", "span-002", "span-003"}

    clusters = build_span_clusters(span_records, span_ids, max_gap_kb=10)

    assert len(clusters) == 1
    assert len(clusters[0]) == 3


def test_build_span_clusters_split_on_large_gap():
    """Large gap should split into multiple clusters."""
    span_records = {
        "span-001": {"byte_start": 1000, "byte_end": 1500},
        "span-002": {"byte_start": 2000, "byte_end": 2500},   # 500 byte gap (OK)
        "span-003": {"byte_start": 15000, "byte_end": 15500}, # 12.5KB gap (SPLIT)
    }
    span_ids = {"span-001", "span-002", "span-003"}

    clusters = build_span_clusters(span_records, span_ids, max_gap_kb=10)

    assert len(clusters) == 2
    assert len(clusters[0]) == 2  # span-001, span-002
    assert len(clusters[1]) == 1  # span-003


def test_build_span_clusters_multiple_large_gaps():
    """Multiple large gaps should create multiple clusters."""
    span_records = {
        "span-001": {"byte_start": 1000, "byte_end": 1500},
        "span-002": {"byte_start": 20000, "byte_end": 20500},  # 18.5KB gap
        "span-003": {"byte_start": 40000, "byte_end": 40500},  # 19.5KB gap
    }
    span_ids = {"span-001", "span-002", "span-003"}

    clusters = build_span_clusters(span_records, span_ids, max_gap_kb=10)

    assert len(clusters) == 3
    assert len(clusters[0]) == 1
    assert len(clusters[1]) == 1
    assert len(clusters[2]) == 1


def test_build_span_clusters_empty_input():
    """Empty span set should return empty clusters."""
    clusters = build_span_clusters({}, set(), max_gap_kb=10)
    assert len(clusters) == 0


def test_build_span_clusters_sorting():
    """Spans should be sorted by byte position regardless of input order."""
    span_records = {
        "span-003": {"byte_start": 3000, "byte_end": 3500},
        "span-001": {"byte_start": 1000, "byte_end": 1500},
        "span-002": {"byte_start": 2000, "byte_end": 2500},
    }
    span_ids = {"span-003", "span-001", "span-002"}  # Deliberately unsorted

    clusters = build_span_clusters(span_records, span_ids, max_gap_kb=10)

    assert len(clusters) == 1
    # Verify spans are in position order
    assert clusters[0][0] == "span-001"
    assert clusters[0][1] == "span-002"
    assert clusters[0][2] == "span-003"


def test_finalize_unit_contiguous_single_unit(tmp_path):
    """Contiguous unit should produce single RewriteUnit."""
    # Create mock baseline
    baseline = MockBaseline(concept_entries=[
        MockConceptEntry("concept-001", ["span-001", "span-002"]),
        MockConceptEntry("concept-002", ["span-003"]),
    ])

    # Create spans file
    snapshot_dir = tmp_path / "test_session"
    spans_path = snapshot_dir / ".humanvoice" / "inventory"
    spans_path.mkdir(parents=True)

    with open(spans_path / "spans.jsonl", 'w') as f:
        f.write(json.dumps({"record_id": "span-001", "byte_start": 1000, "byte_end": 1500}) + "\n")
        f.write(json.dumps({"record_id": "span-002", "byte_start": 1600, "byte_end": 2000}) + "\n")
        f.write(json.dumps({"record_id": "span-003", "byte_start": 2100, "byte_end": 2500}) + "\n")

    # Create mock dependency graph
    dep_graph = MockDependencyGraph()

    # Finalize unit
    units = finalize_unit(
        unit_id="unit-001",
        concept_ids=["concept-001", "concept-002"],
        baseline=baseline,
        dependency_graph=dep_graph,
        span_texts={"span-001": "text1", "span-002": "text2", "span-003": "text3"},
        teaching_sequence=1,
        snapshot_dir=snapshot_dir,
        max_gap_kb=10,
    )

    assert len(units) == 1
    assert units[0].unit_id == "unit-001"
    assert set(units[0].concept_ids) == {"concept-001", "concept-002"}
    assert units[0].split_rationale is None


def test_finalize_unit_noncontiguous_splits(tmp_path):
    """Non-contiguous unit should split into multiple units."""
    # Create mock baseline with concepts that reference distant spans
    baseline = MockBaseline(concept_entries=[
        MockConceptEntry("concept-001", ["span-001"]),
        MockConceptEntry("concept-002", ["span-002"]),  # 18.5KB away
    ])

    # Create spans file with large gap
    snapshot_dir = tmp_path / "test_session"
    spans_path = snapshot_dir / ".humanvoice" / "inventory"
    spans_path.mkdir(parents=True)

    with open(spans_path / "spans.jsonl", 'w') as f:
        f.write(json.dumps({"record_id": "span-001", "byte_start": 1000, "byte_end": 1500}) + "\n")
        f.write(json.dumps({"record_id": "span-002", "byte_start": 20000, "byte_end": 20500}) + "\n")

    # Create mock dependency graph
    dep_graph = MockDependencyGraph()

    # Finalize unit
    units = finalize_unit(
        unit_id="unit-001",
        concept_ids=["concept-001", "concept-002"],
        baseline=baseline,
        dependency_graph=dep_graph,
        span_texts={"span-001": "text1", "span-002": "text2"},
        teaching_sequence=1,
        snapshot_dir=snapshot_dir,
        max_gap_kb=10,
    )

    assert len(units) == 2
    assert units[0].unit_id == "unit-001-cluster1"
    assert units[1].unit_id == "unit-001-cluster2"
    assert "concept-001" in units[0].concept_ids
    assert "concept-002" in units[1].concept_ids
    assert units[1].split_rationale is not None
    assert "18.1KB" in units[1].split_rationale  # Gap = 20000 - 1500 = 18500 bytes = 18.1KB


def test_finalize_unit_concept_distribution(tmp_path):
    """Concepts should be distributed to clusters based on span membership."""
    # Concept with spans in both clusters
    baseline = MockBaseline(concept_entries=[
        MockConceptEntry("concept-001", ["span-001"]),
        MockConceptEntry("concept-002", ["span-001", "span-003"]),  # Spans both clusters
        MockConceptEntry("concept-003", ["span-003"]),
    ])

    snapshot_dir = tmp_path / "test_session"
    spans_path = snapshot_dir / ".humanvoice" / "inventory"
    spans_path.mkdir(parents=True)

    with open(spans_path / "spans.jsonl", 'w') as f:
        f.write(json.dumps({"record_id": "span-001", "byte_start": 1000, "byte_end": 1500}) + "\n")
        f.write(json.dumps({"record_id": "span-003", "byte_start": 20000, "byte_end": 20500}) + "\n")

    dep_graph = MockDependencyGraph()

    units = finalize_unit(
        unit_id="unit-001",
        concept_ids=["concept-001", "concept-002", "concept-003"],
        baseline=baseline,
        dependency_graph=dep_graph,
        span_texts={"span-001": "text1", "span-003": "text3"},
        teaching_sequence=1,
        snapshot_dir=snapshot_dir,
        max_gap_kb=10,
    )

    assert len(units) == 2
    # concept-002 should appear in both clusters (it references spans in both)
    cluster1_concepts = set(units[0].concept_ids)
    cluster2_concepts = set(units[1].concept_ids)

    assert "concept-001" in cluster1_concepts
    assert "concept-002" in cluster1_concepts  # References span-001
    assert "concept-002" in cluster2_concepts  # References span-003
    assert "concept-003" in cluster2_concepts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
