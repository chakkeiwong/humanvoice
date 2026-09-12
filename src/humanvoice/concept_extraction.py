"""
Concept extraction with bounded windows and independent verification.

Implements Phase 3 of WP-V2-2: extract substantive concepts from source spans
in overlapping windows, run reconstruction and coverage critics, and reconcile
duplicates while preserving distinct teaching roles.

Key principles:
- Concepts are propositions/ideas, not just named terms
- Extract in bounded windows with adjacent context, never whole manuscript
- Run independent reconstruction critic (spans → concepts)
- Run independent coverage critic (concepts → spans)
- Reconcile duplicates only when teaching roles are identical
- Surface ambiguities for human adjudication
"""

from dataclasses import dataclass, field
from typing import Optional, Sequence
from pathlib import Path


@dataclass
class ConceptCandidate:
    """A concept extracted from source spans."""
    concept_id: str
    proposition: str
    concept_type: str  # definition, distinction, claim, mechanism, derivation, etc.
    source_span_ids: list[str]
    occurrence_count: int = 1
    teaching_roles: list[str] = field(default_factory=list)  # intro, detail, example, contrast
    supporting_spans: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    confidence: float = 1.0
    extraction_window: Optional[str] = None


@dataclass
class ExtractionWindow:
    """Bounded source window for concept extraction."""
    window_id: str
    span_ids: list[str]
    adjacent_before: list[str] = field(default_factory=list)
    adjacent_after: list[str] = field(default_factory=list)
    byte_start: int = 0
    byte_end: int = 0


def create_extraction_windows(
    spans: Sequence,
    window_size: int = 15,
    overlap: int = 3,
) -> list[ExtractionWindow]:
    """Partition spans into overlapping extraction windows.

    Args:
        spans: Source span records from partition phase
        window_size: Target number of spans per window
        overlap: Number of spans to overlap between windows

    Returns:
        List of ExtractionWindow objects covering all spans
    """
    windows = []
    i = 0
    window_index = 0

    while i < len(spans):
        end = min(i + window_size, len(spans))
        window_span_ids = [s["record_id"] for s in spans[i:end]]

        # Adjacent context: 2 spans before and after
        adj_before = [s["record_id"] for s in spans[max(0, i-2):i]]
        adj_after = [s["record_id"] for s in spans[end:min(end+2, len(spans))]]

        window = ExtractionWindow(
            window_id=f"window-{window_index:04d}",
            span_ids=window_span_ids,
            adjacent_before=adj_before,
            adjacent_after=adj_after,
            byte_start=spans[i]["byte_start"] if i < len(spans) else 0,
            byte_end=spans[end-1]["byte_end"] if end > 0 else 0,
        )
        windows.append(window)

        window_index += 1
        i += window_size - overlap

    return windows


@dataclass
class ReconstructionResult:
    """Result from reconstruction critic."""
    verified_concepts: list[str]
    missing_concepts: list[str]  # concepts claimed but not reconstructible
    extra_spans: list[str]  # spans not explained by any concept
    confidence: float


@dataclass
class CoverageResult:
    """Result from coverage critic."""
    covered_spans: set[str]
    uncovered_spans: set[str]
    concept_to_spans: dict[str, list[str]]
    confidence: float


def reconcile_duplicates(
    concepts: list[ConceptCandidate],
) -> tuple[list[ConceptCandidate], list[tuple[str, str, str]]]:
    """Reconcile duplicate concepts while preserving distinct teaching roles.

    Args:
        concepts: Extracted concept candidates from all windows

    Returns:
        Tuple of (reconciled_concepts, merge_decisions) where merge_decisions
        contains (concept_id_1, concept_id_2, reason) tuples for audit trail
    """
    # Group by normalized proposition
    from collections import defaultdict

    by_proposition = defaultdict(list)
    for concept in concepts:
        # Normalize: lowercase, remove extra whitespace
        normalized = " ".join(concept.proposition.lower().split())
        by_proposition[normalized].append(concept)

    reconciled = []
    merge_decisions = []

    for normalized_prop, group in by_proposition.items():
        if len(group) == 1:
            # No duplicates
            reconciled.append(group[0])
            continue

        # Check if teaching roles differ
        all_roles = set()
        for c in group:
            all_roles.update(c.teaching_roles)

        if len(all_roles) <= 1:
            # Same teaching role (or none) - safe to merge
            merged = ConceptCandidate(
                concept_id=group[0].concept_id,  # Keep first ID
                proposition=group[0].proposition,  # Keep original wording
                concept_type=group[0].concept_type,
                source_span_ids=list(set(
                    span_id
                    for c in group
                    for span_id in c.source_span_ids
                )),
                occurrence_count=len(group),
                teaching_roles=list(all_roles),
                supporting_spans=list(set(
                    span_id
                    for c in group
                    for span_id in c.supporting_spans
                )),
                prerequisites=list(set(
                    prereq
                    for c in group
                    for prereq in c.prerequisites
                )),
                confidence=min(c.confidence for c in group),
            )
            reconciled.append(merged)

            for c in group[1:]:
                merge_decisions.append((
                    c.concept_id,
                    group[0].concept_id,
                    "identical_proposition_and_role"
                ))
        else:
            # Different teaching roles - keep separate
            for concept in group:
                reconciled.append(concept)

    return reconciled, merge_decisions


@dataclass
class ScaffoldingCandidate:
    """A span classified as scaffolding with disposition."""
    span_id: str
    disposition: str  # retain_domain_content | move_backstage | remove_nonconcept | unresolved
    extracted_concepts: list[str] = field(default_factory=list)  # domain concepts embedded within
    reason: str = ""
    adjudication_required: bool = False


def classify_scaffolding(
    spans: Sequence,
    concepts: list[ConceptCandidate],
) -> list[ScaffoldingCandidate]:
    """Classify non-concept spans as scaffolding with disposition.

    Scaffolding is reader-irrelevant authoring or AI-governance material.
    Domain governance that is part of the subject stays as concept-bearing.

    Args:
        spans: All source spans
        concepts: Extracted concepts with their source span IDs

    Returns:
        List of ScaffoldingCandidate objects for spans needing disposition
    """
    # Build set of concept-bearing span IDs
    concept_span_ids = set()
    for concept in concepts:
        concept_span_ids.update(concept.source_span_ids)

    scaffolding = []

    for span in spans:
        span_id = span["record_id"]

        # Skip concept-bearing and protected spans
        if span_id in concept_span_ids:
            continue
        if span.get("coverage_disposition") == "protected_structural":
            continue

        # Placeholder logic - real implementation would use model classification
        # with embedded domain content extraction
        candidate = ScaffoldingCandidate(
            span_id=span_id,
            disposition="unresolved",
            reason="requires_classification",
            adjudication_required=True,
        )
        scaffolding.append(candidate)

    return scaffolding


@dataclass
class AdjudicationItem:
    """Item requiring human adjudication."""
    item_id: str
    item_type: str  # concept_boundary | scaffolding_disposition | dependency_ambiguity
    description: str
    options: list[str]
    recommended: Optional[str] = None
    context: dict = field(default_factory=dict)


def surface_ambiguities(
    concepts: list[ConceptCandidate],
    scaffolding: list[ScaffoldingCandidate],
    reconstruction: Optional[ReconstructionResult] = None,
    coverage: Optional[CoverageResult] = None,
) -> list[AdjudicationItem]:
    """Surface ambiguities requiring human adjudication.

    Only surface items where automated classification is uncertain.
    Routine coverage checks that pass do not require line-item approval.

    Args:
        concepts: Extracted concepts
        scaffolding: Scaffolding candidates
        reconstruction: Optional reconstruction critic result
        coverage: Optional coverage critic result

    Returns:
        List of AdjudicationItem objects requiring human review
    """
    items = []

    # Low-confidence concepts
    for concept in concepts:
        if concept.confidence < 0.7:
            items.append(AdjudicationItem(
                item_id=concept.concept_id,
                item_type="concept_boundary",
                description=f"Low confidence extraction: {concept.proposition[:100]}",
                options=["accept", "reject", "revise_boundary"],
                recommended="accept" if concept.confidence >= 0.5 else "revise_boundary",
                context={"confidence": concept.confidence, "spans": concept.source_span_ids},
            ))

    # Unresolved scaffolding
    for s in scaffolding:
        if s.adjudication_required:
            items.append(AdjudicationItem(
                item_id=s.span_id,
                item_type="scaffolding_disposition",
                description=f"Span requires disposition: {s.reason}",
                options=["retain_domain_content", "move_backstage", "remove_nonconcept"],
                context={"span_id": s.span_id},
            ))

    # Missing concepts from reconstruction
    if reconstruction and reconstruction.missing_concepts:
        for concept_id in reconstruction.missing_concepts:
            items.append(AdjudicationItem(
                item_id=concept_id,
                item_type="concept_boundary",
                description="Concept claimed but not reconstructible from spans",
                options=["revise_spans", "reject_concept"],
                recommended="revise_spans",
            ))

    # Uncovered spans from coverage critic
    if coverage and coverage.uncovered_spans:
        for span_id in coverage.uncovered_spans:
            items.append(AdjudicationItem(
                item_id=span_id,
                item_type="concept_boundary",
                description="Span not explained by any concept",
                options=["extract_concept", "classify_scaffolding", "accept_gap"],
                context={"span_id": span_id},
            ))

    return items


@dataclass
class BaselineSignature:
    """Cryptographic signature of frozen baseline."""
    baseline_id: str
    baseline_hash: str
    snapshot_id: str
    source_hash: str
    total_spans: int
    total_concepts: int
    unresolved_items: int
    adjudicator_id: str
    adjudication_date: str
    signature_method: str = "SHA-256"


def freeze_baseline(
    snapshot_id: str,
    source_hash: str,
    spans: list,
    concepts: list[ConceptCandidate],
    scaffolding: list[ScaffoldingCandidate],
    adjudicator_id: str,
    adjudication_date: str,
) -> BaselineSignature:
    """Freeze the concept baseline with cryptographic signature.

    The baseline becomes immutable after adjudication. Any source or inventory
    changes invalidate downstream plans.

    Args:
        snapshot_id: Source snapshot identifier
        source_hash: Source content hash from manifest
        spans: All source spans
        concepts: Adjudicated concepts
        scaffolding: Adjudicated scaffolding dispositions
        adjudicator_id: Human reviewer identifier
        adjudication_date: ISO 8601 timestamp

    Returns:
        BaselineSignature with frozen hash
    """
    from hashlib import sha256
    import json

    # Count unresolved items
    unresolved = sum(
        1 for c in concepts if c.confidence < 0.7
    ) + sum(
        1 for s in scaffolding if s.disposition == "unresolved"
    )

    # Generate stable baseline ID
    baseline_id = f"baseline-{snapshot_id}"

    # Build canonical representation for hashing
    canonical = {
        "snapshot_id": snapshot_id,
        "source_hash": source_hash,
        "spans": [s["record_id"] for s in spans],
        "concepts": [
            {
                "id": c.concept_id,
                "proposition": c.proposition,
                "type": c.concept_type,
                "spans": sorted(c.source_span_ids),
            }
            for c in sorted(concepts, key=lambda x: x.concept_id)
        ],
        "scaffolding": [
            {
                "span": s.span_id,
                "disposition": s.disposition,
            }
            for s in sorted(scaffolding, key=lambda x: x.span_id)
        ],
        "adjudicator": adjudicator_id,
        "adjudication_date": adjudication_date,
    }

    # Compute hash
    canonical_bytes = json.dumps(canonical, sort_keys=True).encode("utf-8")
    baseline_hash = sha256(canonical_bytes).hexdigest()

    return BaselineSignature(
        baseline_id=baseline_id,
        baseline_hash=baseline_hash,
        snapshot_id=snapshot_id,
        source_hash=source_hash,
        total_spans=len(spans),
        total_concepts=len(concepts),
        unresolved_items=unresolved,
        adjudicator_id=adjudicator_id,
        adjudication_date=adjudication_date,
    )
