"""
Semantic unit splitting for rewrite planning.

Partitions the concept baseline into rewrite units that respect:
- Concept dependencies (prerequisites before dependents)
- Size constraints (~2000 word estimate triggers split)
- Semantic coherence (related concepts stay together)
- Source span locality (minimize context jumps)

Key principles:
- Units are sized for successful model completion (~2000 words target)
- Dependencies never span unit boundaries without explicit resolution
- Each unit is independently rewritable
- Units map to contiguous or near-contiguous source regions
- Human can override automatic splits
"""

from dataclasses import dataclass, field
from typing import Optional
import json
from pathlib import Path


@dataclass
class RewriteUnit:
    """One independently rewritable semantic unit."""
    unit_id: str
    concept_ids: list[str]  # Concepts to teach in this unit
    source_span_ids: list[str]  # Source spans to rewrite
    prerequisites: list[str] = field(default_factory=list)  # Concepts from other units needed first
    estimated_words: int = 0
    unit_type: str = "semantic"  # "semantic" | "structural" | "scaffolding"
    teaching_sequence: int = 0  # Order in overall teaching plan
    split_rationale: Optional[str] = None


@dataclass
class RewritePlan:
    """Complete partitioning of baseline into rewrite units."""
    plan_id: str
    baseline_id: str
    snapshot_id: str
    units: list[RewriteUnit] = field(default_factory=list)
    total_units: int = 0
    total_concepts: int = 0
    max_unit_size: int = 1000  # Word estimate ceiling for split trigger


def estimate_unit_size(concept_ids: list[str], baseline, span_texts: dict) -> int:
    """Estimate output word count for a rewrite unit.

    Args:
        concept_ids: List of concept IDs in this unit
        baseline: ConceptBaseline with concept entries
        span_texts: Map of span_id -> text for source spans

    Returns:
        Estimated output word count
    """
    # Collect all source spans for these concepts
    span_ids = set()
    for entry in baseline.concept_entries:
        if entry.concept_id in concept_ids:
            span_ids.update(entry.source_span_ids)

    # Sum word counts from source spans
    total_words = 0
    for span_id in span_ids:
        text = span_texts.get(span_id, "")
        # Rough word count: split on whitespace
        words = len(text.split())
        total_words += words

    # Apply humanization expansion factor (typically 1.2-1.5x)
    # Conservative: assume 1.5x expansion
    estimated_output_words = int(total_words * 1.5)

    return estimated_output_words


def build_span_overlap_groups(baseline) -> dict[str, set[str]]:
    """Build groups of concepts that share spans and must stay together.

    Args:
        baseline: ConceptBaseline with concept entries

    Returns:
        Map of concept_id -> set of all concepts it must be grouped with
    """
    # Build map of span -> concepts that use it
    span_to_concepts = {}
    for entry in baseline.concept_entries:
        for span_id in entry.source_span_ids:
            if span_id not in span_to_concepts:
                span_to_concepts[span_id] = []
            span_to_concepts[span_id].append(entry.concept_id)

    # Build concept overlap graph
    concept_neighbors = {entry.concept_id: set() for entry in baseline.concept_entries}
    for span_id, concepts in span_to_concepts.items():
        if len(concepts) > 1:
            # These concepts share a span - link them
            for c1 in concepts:
                for c2 in concepts:
                    if c1 != c2:
                        concept_neighbors[c1].add(c2)

    # Find connected components using union-find
    concept_to_group = {}
    for concept_id in concept_neighbors:
        if concept_id not in concept_to_group:
            # BFS to find all connected concepts
            group = set()
            queue = [concept_id]
            while queue:
                current = queue.pop(0)
                if current in group:
                    continue
                group.add(current)
                for neighbor in concept_neighbors[current]:
                    if neighbor not in group:
                        queue.append(neighbor)

            # Assign this group to all members
            for member in group:
                concept_to_group[member] = group

    return concept_to_group


def partition_concepts_into_units(
    baseline,
    dependency_graph,
    span_texts: dict,
    max_unit_size: int = 1000,
    snapshot_dir: Optional[Path] = None,
) -> list[RewriteUnit]:
    """Partition concept baseline into rewrite units.

    Uses greedy algorithm respecting teaching order and size constraints.
    Enforces span uniqueness: concepts sharing spans stay in same unit.

    Args:
        baseline: ConceptBaseline with all concepts
        dependency_graph: DependencyGraph with teaching order
        span_texts: Map of span_id -> text for size estimation
        max_unit_size: Target maximum words per unit (triggers split)
        snapshot_dir: Snapshot directory (for loading span positions)

    Returns:
        List of RewriteUnit objects
    """
    # Build groups of concepts that share spans (must stay together)
    concept_to_group = build_span_overlap_groups(baseline)

    units = []
    unit_counter = 0

    # Process concepts in teaching order
    teaching_order = dependency_graph.teaching_order
    if not teaching_order:
        # No dependencies or unresolved cycles - use concept order from baseline
        teaching_order = [entry.concept_id for entry in baseline.concept_entries]

    current_unit_concepts = []
    current_unit_size = 0
    processed_concepts = set()

    for concept_id in teaching_order:
        if concept_id in processed_concepts:
            continue

        # Get the entire group this concept belongs to
        concept_group = list(concept_to_group.get(concept_id, {concept_id}))

        # Estimate size if we add this entire group to current unit
        test_concepts = current_unit_concepts + concept_group
        estimated_size = estimate_unit_size(test_concepts, baseline, span_texts)

        # Check if adding this group would exceed size limit
        if estimated_size > max_unit_size and current_unit_concepts:
            # Finalize current unit and start new one
            unit_counter += 1
            finalized_units = finalize_unit(
                unit_id=f"unit-{unit_counter:03d}",
                concept_ids=current_unit_concepts,
                baseline=baseline,
                dependency_graph=dependency_graph,
                span_texts=span_texts,
                teaching_sequence=unit_counter,
                snapshot_dir=snapshot_dir,
            )
            units.extend(finalized_units)  # Extend, not append (may be multiple units)

            # Start new unit with current group
            current_unit_concepts = concept_group
            current_unit_size = estimate_unit_size(concept_group, baseline, span_texts)
        else:
            # Add entire group to current unit
            current_unit_concepts.extend(concept_group)
            current_unit_size = estimated_size

        # Mark all concepts in group as processed
        processed_concepts.update(concept_group)

    # Finalize last unit
    if current_unit_concepts:
        unit_counter += 1
        finalized_units = finalize_unit(
            unit_id=f"unit-{unit_counter:03d}",
            concept_ids=current_unit_concepts,
            baseline=baseline,
            dependency_graph=dependency_graph,
            span_texts=span_texts,
            teaching_sequence=unit_counter,
            snapshot_dir=snapshot_dir,
        )
        units.extend(finalized_units)  # Extend, not append (may be multiple units)

    return units


def build_span_clusters(
    span_records: dict,
    span_ids: set[str],
    max_gap_kb: int = 10
) -> list[list[str]]:
    """Group spans into contiguous clusters based on byte positions.

    Args:
        span_records: Map of span_id -> span record with byte_start, byte_end
        span_ids: Set of span IDs to cluster
        max_gap_kb: Maximum gap in KB between spans in same cluster

    Returns:
        List of span clusters, where each cluster is a list of span IDs
    """
    if not span_ids:
        return []

    # Build list of (span_id, byte_start, byte_end) tuples
    span_positions = []
    for span_id in span_ids:
        if span_id in span_records:
            record = span_records[span_id]
            span_positions.append((
                span_id,
                record.get('byte_start', 0),
                record.get('byte_end', 0)
            ))

    if not span_positions:
        return []

    # Sort by byte_start
    span_positions.sort(key=lambda x: x[1])

    # Build clusters with gap threshold
    max_gap_bytes = max_gap_kb * 1024
    clusters = []
    current_cluster = [span_positions[0]]

    for span_tuple in span_positions[1:]:
        span_id, start, end = span_tuple
        prev_span_id, prev_start, prev_end = current_cluster[-1]

        gap = start - prev_end

        if gap <= max_gap_bytes:
            # Span is close enough, add to current cluster
            current_cluster.append(span_tuple)
        else:
            # Gap too large, start new cluster
            clusters.append(current_cluster)
            current_cluster = [span_tuple]

    # Don't forget the last cluster
    if current_cluster:
        clusters.append(current_cluster)

    # Convert clusters from [(span_id, start, end), ...] to [span_id, ...]
    return [[span_tuple[0] for span_tuple in cluster] for cluster in clusters]


def finalize_unit(
    unit_id: str,
    concept_ids: list[str],
    baseline,
    dependency_graph,
    span_texts: dict,
    teaching_sequence: int,
    snapshot_dir: Optional[Path] = None,
    max_gap_kb: int = 10,
) -> list[RewriteUnit]:
    """Create RewriteUnit(s) from concept IDs, enforcing span contiguity.

    If the unit's spans have gaps > max_gap_kb, splits into multiple units.

    Args:
        unit_id: Unique unit identifier
        concept_ids: Concepts in this unit
        baseline: ConceptBaseline
        dependency_graph: DependencyGraph
        span_texts: Span text map for size estimation
        teaching_sequence: Position in overall teaching plan
        snapshot_dir: Snapshot directory (for loading span positions)
        max_gap_kb: Maximum gap in KB between spans (default 10KB)

    Returns:
        List of RewriteUnit objects (1 if contiguous, N if split)
    """
    # Collect source spans
    span_ids = set()
    for entry in baseline.concept_entries:
        if entry.concept_id in concept_ids:
            span_ids.update(entry.source_span_ids)

    if not span_ids:
        # No spans - return empty unit list
        return []

    # Load span positions for contiguity checking
    span_records = {}
    if snapshot_dir:
        spans_path = snapshot_dir / ".humanvoice" / "inventory" / "spans.jsonl"
        if spans_path.exists():
            try:
                with open(spans_path, 'r') as f:
                    for line in f:
                        if line.strip():
                            record = json.loads(line)
                            span_id = record.get("record_id", "")
                            if span_id in span_ids:
                                span_records[span_id] = record
            except Exception:
                pass

    # Build span clusters (contiguous groups with gaps < max_gap_kb)
    clusters = build_span_clusters(span_records, span_ids, max_gap_kb)

    if not clusters:
        # No valid clusters - return empty
        return []

    if len(clusters) == 1:
        # Unit is contiguous - return single unit
        cluster_span_ids = clusters[0]
        cluster_span_set = set(cluster_span_ids)

        # Filter concepts: only keep those that contributed spans to this cluster
        filtered_concept_ids = []
        for entry in baseline.concept_entries:
            if entry.concept_id in concept_ids:
                # Check if concept has at least one span in this cluster
                concept_span_ids = [sid for sid in entry.source_span_ids if sid in span_records]
                if any(sid in cluster_span_set for sid in concept_span_ids):
                    filtered_concept_ids.append(entry.concept_id)

        # If all concepts filtered out, return empty
        if not filtered_concept_ids:
            return []

        # Sort by document position
        sorted_span_ids = sorted(cluster_span_ids, key=lambda sid: (
            span_records.get(sid, {}).get("line_start", 999999),
            span_records.get(sid, {}).get("byte_start", 999999)
        )) if span_records else sorted(cluster_span_ids)

        # Find prerequisites (using filtered concept list)
        concept_set = set(filtered_concept_ids)
        prerequisites = set()
        for dep in dependency_graph.dependencies:
            if dep.dependent_concept_id in concept_set:
                if dep.prerequisite_concept_id not in concept_set:
                    prerequisites.add(dep.prerequisite_concept_id)

        # Estimate size (using filtered concept list)
        estimated_words = estimate_unit_size(filtered_concept_ids, baseline, span_texts)

        return [RewriteUnit(
            unit_id=unit_id,
            concept_ids=filtered_concept_ids,
            source_span_ids=sorted_span_ids,
            prerequisites=sorted(prerequisites),
            estimated_words=estimated_words,
            unit_type="semantic",
            teaching_sequence=teaching_sequence,
            split_rationale=None,
        )]

    else:
        # Unit is non-contiguous - split into multiple units
        units = []

        for i, cluster_span_ids in enumerate(clusters):
            sub_unit_id = f"{unit_id}-cluster{i+1}"

            # Assign concepts to this cluster based on which spans they reference
            cluster_concept_ids = []
            cluster_span_set = set(cluster_span_ids)

            for entry in baseline.concept_entries:
                if entry.concept_id in concept_ids:
                    # Include concept if ANY of its spans are in this cluster
                    if any(sid in cluster_span_set for sid in entry.source_span_ids):
                        cluster_concept_ids.append(entry.concept_id)

            if not cluster_concept_ids:
                continue

            # Sort spans by document position
            sorted_span_ids = sorted(cluster_span_ids, key=lambda sid: (
                span_records.get(sid, {}).get("line_start", 999999),
                span_records.get(sid, {}).get("byte_start", 999999)
            )) if span_records else sorted(cluster_span_ids)

            # Find prerequisites for this cluster
            cluster_concept_set = set(cluster_concept_ids)
            prerequisites = set()
            for dep in dependency_graph.dependencies:
                if dep.dependent_concept_id in cluster_concept_set:
                    if dep.prerequisite_concept_id not in cluster_concept_set:
                        prerequisites.add(dep.prerequisite_concept_id)

            # Estimate size
            estimated_words = estimate_unit_size(cluster_concept_ids, baseline, span_texts)

            # Calculate gap that triggered split
            if i > 0:
                prev_cluster = clusters[i-1]
                prev_last_span = prev_cluster[-1]
                curr_first_span = cluster_span_ids[0]

                prev_end = span_records.get(prev_last_span, ).get('byte_end', 0)
                curr_start = span_records.get(curr_first_span, {}).get('byte_start', 0)
                gap_bytes = curr_start - prev_end
                gap_kb = gap_bytes / 1024

                rationale = f"Split from {unit_id} due to {gap_kb:.1f}KB gap (threshold: {max_gap_kb}KB)"
            else:
                rationale = f"Split from {unit_id} (cluster {i+1}/{len(clusters)})"

            units.append(RewriteUnit(
                unit_id=sub_unit_id,
                concept_ids=cluster_concept_ids,
                source_span_ids=sorted_span_ids,
                prerequisites=sorted(prerequisites),
                estimated_words=estimated_words,
                unit_type="semantic",
                teaching_sequence=teaching_sequence,
                split_rationale=rationale,
            ))

        return units


def create_rewrite_plan(
    baseline,
    dependency_graph,
    span_texts: dict,
    max_unit_size: int = 1000,
    snapshot_dir: Optional[Path] = None,
) -> RewritePlan:
    """Create complete rewrite plan from baseline and dependencies.

    Args:
        baseline: ConceptBaseline
        dependency_graph: DependencyGraph
        span_texts: Map of span_id -> text
        max_unit_size: Target max words per unit
        snapshot_dir: Snapshot directory (for loading span positions)

    Returns:
        RewritePlan with all units
    """
    plan_id = f"plan-{baseline.baseline_id}"

    units = partition_concepts_into_units(
        baseline=baseline,
        dependency_graph=dependency_graph,
        span_texts=span_texts,
        max_unit_size=max_unit_size,
        snapshot_dir=snapshot_dir,
    )

    return RewritePlan(
        plan_id=plan_id,
        baseline_id=baseline.baseline_id,
        snapshot_id=baseline.snapshot_id,
        units=units,
        total_units=len(units),
        total_concepts=len(baseline.concept_entries),
        max_unit_size=max_unit_size,
    )


def verify_unit_plan_completeness(plan: RewritePlan, baseline) -> tuple[bool, list[str]]:
    """Verify that rewrite plan covers all concepts exactly once.

    Args:
        plan: RewritePlan to verify
        baseline: ConceptBaseline to check against

    Returns:
        Tuple of (is_complete, list of issues)
    """
    issues = []

    # Collect all concept IDs from plan
    plan_concepts = set()
    for unit in plan.units:
        for concept_id in unit.concept_ids:
            if concept_id in plan_concepts:
                issues.append(f"Concept {concept_id} appears in multiple units")
            plan_concepts.add(concept_id)

    # Check against baseline
    baseline_concepts = {entry.concept_id for entry in baseline.concept_entries}

    missing = baseline_concepts - plan_concepts
    extra = plan_concepts - baseline_concepts

    if missing:
        issues.append(f"Missing concepts in plan: {sorted(missing)}")
    if extra:
        issues.append(f"Extra concepts not in baseline: {sorted(extra)}")

    return len(issues) == 0, issues


def save_rewrite_plan(plan: RewritePlan, output_path: Path) -> None:
    """Write rewrite plan to disk.

    Args:
        plan: RewritePlan to save
        output_path: Path to write JSON file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "plan_id": plan.plan_id,
            "baseline_id": plan.baseline_id,
            "snapshot_id": plan.snapshot_id,
            "total_units": plan.total_units,
            "total_concepts": plan.total_concepts,
            "max_unit_size": plan.max_unit_size,
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "concept_ids": unit.concept_ids,
                    "source_span_ids": unit.source_span_ids,
                    "prerequisites": unit.prerequisites,
                    "estimated_words": unit.estimated_words,
                    "unit_type": unit.unit_type,
                    "teaching_sequence": unit.teaching_sequence,
                    "split_rationale": unit.split_rationale,
                }
                for unit in plan.units
            ],
        }, f, indent=2)


def load_rewrite_plan(input_path: Path) -> RewritePlan:
    """Load rewrite plan from disk.

    Args:
        input_path: Path to rewrite plan JSON

    Returns:
        RewritePlan object
    """
    with open(input_path, 'r') as f:
        data = json.load(f)

    units = []
    for unit_data in data["units"]:
        units.append(RewriteUnit(
            unit_id=unit_data["unit_id"],
            concept_ids=unit_data["concept_ids"],
            source_span_ids=unit_data["source_span_ids"],
            prerequisites=unit_data.get("prerequisites", []),
            estimated_words=unit_data.get("estimated_words", 0),
            unit_type=unit_data.get("unit_type", "semantic"),
            teaching_sequence=unit_data.get("teaching_sequence", 0),
            split_rationale=unit_data.get("split_rationale"),
        ))

    return RewritePlan(
        plan_id=data["plan_id"],
        baseline_id=data["baseline_id"],
        snapshot_id=data["snapshot_id"],
        units=units,
        total_units=data["total_units"],
        total_concepts=data["total_concepts"],
        max_unit_size=data.get("max_unit_size", 2000),
    )
