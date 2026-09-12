"""
Frozen concept baseline for semantic fidelity verification.

The baseline is a human-reviewed, hash-locked concept inventory that serves as
ground truth for all downstream correspondence verification. Once frozen, the
baseline becomes the authority: every rewrite must preserve exactly 1.0 concept
correspondence against it.

Key principles:
- Baseline is frozen after human adjudication completes
- Hash covers all substantive concepts and their teaching roles
- Baseline hash appears in all downstream records
- Changes to frozen baseline require explicit re-adjudication
- Retention is exactly 1.0 - no partial credit for "close enough"
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path


@dataclass
class ConceptBaselineEntry:
    """One concept in the frozen baseline."""
    concept_id: str
    proposition: str
    concept_type: str
    source_span_ids: list[str]
    teaching_roles: list[str]
    supporting_spans: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    confidence: float = 1.0
    adjudication_status: str = "accepted"  # accepted | rejected | revised
    human_rationale: Optional[str] = None


@dataclass
class ConceptBaseline:
    """Frozen concept inventory serving as ground truth."""
    baseline_id: str
    snapshot_id: str
    source_hash: str  # Hash of source files at freeze time
    concept_entries: list[ConceptBaselineEntry]
    total_concepts: int
    frozen_at: str
    frozen_by: str
    adjudication_session_id: Optional[str] = None
    baseline_hash: Optional[str] = None  # Computed from all entries


def compute_baseline_hash(baseline: ConceptBaseline) -> str:
    """Compute deterministic hash of frozen baseline.

    The hash covers:
    - All concept propositions
    - All concept types
    - All teaching roles
    - All source span IDs

    Changes to any of these require re-adjudication.

    Args:
        baseline: ConceptBaseline to hash

    Returns:
        Hex-encoded SHA256 hash of baseline content
    """
    # Sort entries by concept_id for determinism
    sorted_entries = sorted(baseline.concept_entries, key=lambda e: e.concept_id)

    # Build canonical representation
    canonical = []
    for entry in sorted_entries:
        canonical.append({
            "concept_id": entry.concept_id,
            "proposition": entry.proposition,
            "concept_type": entry.concept_type,
            "source_span_ids": sorted(entry.source_span_ids),
            "teaching_roles": sorted(entry.teaching_roles),
        })

    # Hash the canonical JSON
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
    return sha256(canonical_json.encode('utf-8')).hexdigest()


def create_baseline_from_adjudication(
    snapshot_id: str,
    source_hash: str,
    adjudication_session,
    accepted_concepts: list,
    frozen_by: str,
) -> ConceptBaseline:
    """Create frozen baseline from adjudicated concepts.

    Args:
        snapshot_id: Source snapshot identifier
        source_hash: Hash of source files at freeze time
        adjudication_session: AdjudicationSession with completed adjudications
        accepted_concepts: List of ConceptCandidate objects after adjudication
        frozen_by: Name/identifier of person freezing the baseline

    Returns:
        ConceptBaseline with computed hash
    """
    baseline_id = f"baseline-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    # Convert concepts to baseline entries
    entries = []
    for concept in accepted_concepts:
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
            human_rationale=None,
        ))

    baseline = ConceptBaseline(
        baseline_id=baseline_id,
        snapshot_id=snapshot_id,
        source_hash=source_hash,
        concept_entries=entries,
        total_concepts=len(entries),
        frozen_at=datetime.now(timezone.utc).isoformat(),
        frozen_by=frozen_by,
        adjudication_session_id=adjudication_session.session_id if adjudication_session else None,
    )

    # Compute and attach baseline hash
    baseline.baseline_hash = compute_baseline_hash(baseline)

    return baseline


def save_baseline(baseline: ConceptBaseline, output_path: Path) -> None:
    """Write frozen baseline to disk.

    Args:
        baseline: ConceptBaseline to save
        output_path: Path to write baseline JSON
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "baseline_id": baseline.baseline_id,
            "snapshot_id": baseline.snapshot_id,
            "source_hash": baseline.source_hash,
            "frozen_at": baseline.frozen_at,
            "frozen_by": baseline.frozen_by,
            "adjudication_session_id": baseline.adjudication_session_id,
            "baseline_hash": baseline.baseline_hash,
            "total_concepts": baseline.total_concepts,
            "concept_entries": [
                {
                    "concept_id": entry.concept_id,
                    "proposition": entry.proposition,
                    "concept_type": entry.concept_type,
                    "source_span_ids": entry.source_span_ids,
                    "teaching_roles": entry.teaching_roles,
                    "supporting_spans": entry.supporting_spans,
                    "prerequisites": entry.prerequisites,
                    "confidence": entry.confidence,
                    "adjudication_status": entry.adjudication_status,
                    "human_rationale": entry.human_rationale,
                }
                for entry in baseline.concept_entries
            ],
        }, f, indent=2)


def load_baseline(input_path: Path) -> ConceptBaseline:
    """Load frozen baseline from disk.

    Args:
        input_path: Path to baseline JSON file

    Returns:
        ConceptBaseline object

    Raises:
        FileNotFoundError: If baseline file doesn't exist
        ValueError: If baseline hash verification fails
    """
    with open(input_path, 'r') as f:
        data = json.load(f)

    entries = []
    for entry_data in data["concept_entries"]:
        entries.append(ConceptBaselineEntry(
            concept_id=entry_data["concept_id"],
            proposition=entry_data["proposition"],
            concept_type=entry_data["concept_type"],
            source_span_ids=entry_data["source_span_ids"],
            teaching_roles=entry_data["teaching_roles"],
            supporting_spans=entry_data.get("supporting_spans", []),
            prerequisites=entry_data.get("prerequisites", []),
            confidence=entry_data.get("confidence", 1.0),
            adjudication_status=entry_data.get("adjudication_status", "accepted"),
            human_rationale=entry_data.get("human_rationale"),
        ))

    baseline = ConceptBaseline(
        baseline_id=data["baseline_id"],
        snapshot_id=data["snapshot_id"],
        source_hash=data["source_hash"],
        concept_entries=entries,
        total_concepts=data["total_concepts"],
        frozen_at=data["frozen_at"],
        frozen_by=data["frozen_by"],
        adjudication_session_id=data.get("adjudication_session_id"),
        baseline_hash=data.get("baseline_hash"),
    )

    # Verify baseline hash
    computed_hash = compute_baseline_hash(baseline)
    if baseline.baseline_hash != computed_hash:
        raise ValueError(
            f"Baseline hash mismatch: stored={baseline.baseline_hash}, "
            f"computed={computed_hash}. Baseline may have been tampered with."
        )

    return baseline


def verify_baseline_integrity(baseline: ConceptBaseline) -> tuple[bool, str]:
    """Verify baseline hash integrity.

    Args:
        baseline: ConceptBaseline to verify

    Returns:
        Tuple of (is_valid, message)
    """
    if not baseline.baseline_hash:
        return False, "Baseline has no hash (not properly frozen)"

    computed = compute_baseline_hash(baseline)
    if computed != baseline.baseline_hash:
        return False, f"Hash mismatch: stored={baseline.baseline_hash[:16]}..., computed={computed[:16]}..."

    return True, "Baseline integrity verified"


def get_baseline_concepts_by_span(baseline: ConceptBaseline) -> dict[str, list[ConceptBaselineEntry]]:
    """Build index of span_id -> concepts for correspondence checking.

    Args:
        baseline: ConceptBaseline to index

    Returns:
        Dict mapping span_id to list of concepts covering that span
    """
    span_index = {}
    for entry in baseline.concept_entries:
        for span_id in entry.source_span_ids:
            if span_id not in span_index:
                span_index[span_id] = []
            span_index[span_id].append(entry)

    return span_index
