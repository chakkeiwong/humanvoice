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
    max_unit_size: int = 2000  # Word estimate ceiling for split trigger


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


def partition_concepts_into_units(
    baseline,
    dependency_graph,
    span_texts: dict,
    max_unit_size: int = 2000,
) -> list[RewriteUnit]:
    """Partition concept baseline into rewrite units.

    Uses greedy algorithm respecting teaching order and size constraints.

    Args:
        baseline: ConceptBaseline with all concepts
        dependency_graph: DependencyGraph with teaching order
        span_texts: Map of span_id -> text for size estimation
        max_unit_size: Target maximum words per unit (triggers split)

    Returns:
        List of RewriteUnit objects
    """
    units = []
    unit_counter = 0

    # Process concepts in teaching order
    teaching_order = dependency_graph.teaching_order
    if not teaching_order:
        # No dependencies or unresolved cycles - use concept order from baseline
        teaching_order = [entry.concept_id for entry in baseline.concept_entries]

    current_unit_concepts = []
    current_unit_size = 0

    for concept_id in teaching_order:
        # Estimate size if we add this concept to current unit
        test_concepts = current_unit_concepts + [concept_id]
        estimated_size = estimate_unit_size(test_concepts, baseline, span_texts)

        # Check if adding this concept would exceed size limit
        if estimated_size > max_unit_size and current_unit_concepts:
            # Finalize current unit and start new one
            unit_counter += 1
            unit = finalize_unit(
                unit_id=f"unit-{unit_counter:03d}",
                concept_ids=current_unit_concepts,
                baseline=baseline,
                dependency_graph=dependency_graph,
                span_texts=span_texts,
                teaching_sequence=unit_counter,
            )
            units.append(unit)

            # Start new unit with current concept
            current_unit_concepts = [concept_id]
            current_unit_size = estimate_unit_size([concept_id], baseline, span_texts)
        else:
            # Add concept to current unit
            current_unit_concepts.append(concept_id)
            current_unit_size = estimated_size

    # Finalize last unit
    if current_unit_concepts:
        unit_counter += 1
        unit = finalize_unit(
            unit_id=f"unit-{unit_counter:03d}",
            concept_ids=current_unit_concepts,
            baseline=baseline,
            dependency_graph=dependency_graph,
            span_texts=span_texts,
            teaching_sequence=unit_counter,
        )
        units.append(unit)

    return units


def finalize_unit(
    unit_id: str,
    concept_ids: list[str],
    baseline,
    dependency_graph,
    span_texts: dict,
    teaching_sequence: int,
) -> RewriteUnit:
    """Create RewriteUnit from concept IDs.

    Args:
        unit_id: Unique unit identifier
        concept_ids: Concepts in this unit
        baseline: ConceptBaseline
        dependency_graph: DependencyGraph
        span_texts: Span text map for size estimation
        teaching_sequence: Position in overall teaching plan

    Returns:
        Finalized RewriteUnit
    """
    # Collect source spans
    span_ids = set()
    for entry in baseline.concept_entries:
        if entry.concept_id in concept_ids:
            span_ids.update(entry.source_span_ids)

    # Find prerequisites from other units (concepts not in this unit)
    concept_set = set(concept_ids)
    prerequisites = set()
    for dep in dependency_graph.dependencies:
        if dep.dependent_concept_id in concept_set:
            if dep.prerequisite_concept_id not in concept_set:
                prerequisites.add(dep.prerequisite_concept_id)

    # Estimate size
    estimated_words = estimate_unit_size(concept_ids, baseline, span_texts)

    return RewriteUnit(
        unit_id=unit_id,
        concept_ids=concept_ids,
        source_span_ids=sorted(span_ids),
        prerequisites=sorted(prerequisites),
        estimated_words=estimated_words,
        unit_type="semantic",
        teaching_sequence=teaching_sequence,
    )


def create_rewrite_plan(
    baseline,
    dependency_graph,
    span_texts: dict,
    max_unit_size: int = 2000,
) -> RewritePlan:
    """Create complete rewrite plan from baseline and dependencies.

    Args:
        baseline: ConceptBaseline
        dependency_graph: DependencyGraph
        span_texts: Map of span_id -> text
        max_unit_size: Target max words per unit

    Returns:
        RewritePlan with all units
    """
    plan_id = f"plan-{baseline.baseline_id}"

    units = partition_concepts_into_units(
        baseline=baseline,
        dependency_graph=dependency_graph,
        span_texts=span_texts,
        max_unit_size=max_unit_size,
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
