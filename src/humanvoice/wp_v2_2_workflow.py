"""
WP-V2-2 complete workflow integration.

Orchestrates the full concept inventory and teaching plan pipeline:
1. Model-based concept extraction with critics (Phase 4)
2. Ambiguity adjudication (Phase 5)
3. Frozen baseline creation (Phase 6)
4. Dependency planning (Phase 7)
5. Semantic unit splitting (Phase 8)

This module provides the high-level workflow functions that coordinate
all WP-V2-2 components into a complete baseline-creation pipeline.
"""

from pathlib import Path
from typing import Optional
import sys

from humanvoice.concept_extraction import create_extraction_windows
from humanvoice.model_extraction import (
    extract_concepts_from_window,
    verify_reconstruction,
    verify_coverage,
)
from humanvoice.ambiguity_adjudication import (
    identify_ambiguities,
    create_adjudication_session,
    save_adjudication_session,
    load_adjudication_session,
)
from humanvoice.concept_baseline import (
    create_baseline_from_adjudication,
    save_baseline,
    load_baseline,
    verify_baseline_integrity,
)
from humanvoice.dependency_planning import (
    create_dependency_graph,
    save_dependency_graph,
    detect_cycles,
)
from humanvoice.semantic_unit_splitting import (
    create_rewrite_plan,
    save_rewrite_plan,
    verify_unit_plan_completeness,
)


def run_extraction_phase(
    snapshot_dir: Path,
    brief: dict,
    model,
    registry,
    span_dicts: list[dict],
    span_texts: dict,
) -> tuple[list, list, list, list]:
    """Run Phase 4: Model-based extraction with critics.

    Args:
        snapshot_dir: Path to snapshot directory
        brief: HumanizationBrief dict
        model: ModelAdapter instance
        registry: SchemaRegistry instance
        span_dicts: List of span records
        span_texts: Map of span_id -> text

    Returns:
        Tuple of (concepts, abstentions, reconstruction_verdicts, coverage_verdicts)
    """
    print("Phase 4: Model-based concept extraction", file=sys.stderr)

    # Create extraction windows
    windows = create_extraction_windows(span_dicts, window_size=15, overlap=3)
    print(f"  Created {len(windows)} extraction windows", file=sys.stderr)

    all_concepts = []
    all_abstentions = []
    all_reconstruction_verdicts = []
    all_coverage_verdicts = []

    for i, window in enumerate(windows):
        print(f"  Extracting window {i+1}/{len(windows)} ({len(window.span_ids)} spans)...", file=sys.stderr)

        # Extract concepts
        result = extract_concepts_from_window(
            window=window,
            brief=brief,
            model=model,
            registry=registry,
            span_texts=span_texts,
        )

        all_concepts.extend(result.concepts)
        all_abstentions.extend(result.abstentions)

        if result.concepts:
            print(f"    Extracted {len(result.concepts)} concepts", file=sys.stderr)

            # Run reconstruction critic
            window_spans = [s for s in span_dicts if s['record_id'] in window.span_ids]
            reconstruction_verdicts = verify_reconstruction(result.concepts, window_spans, model)
            all_reconstruction_verdicts.extend(reconstruction_verdicts)

            # Run coverage critic
            coverage_verdicts = verify_coverage(window_spans, result.concepts, model)
            all_coverage_verdicts.extend(coverage_verdicts)

        if result.abstentions:
            print(f"    Abstentions: {len(result.abstentions)}", file=sys.stderr)

    print(f"\nExtraction complete:", file=sys.stderr)
    print(f"  Total concepts: {len(all_concepts)}", file=sys.stderr)
    print(f"  Abstentions: {len(all_abstentions)}", file=sys.stderr)
    print(f"  Reconstruction verdicts: {len(all_reconstruction_verdicts)}", file=sys.stderr)
    print(f"  Coverage verdicts: {len(all_coverage_verdicts)}", file=sys.stderr)

    return all_concepts, all_abstentions, all_reconstruction_verdicts, all_coverage_verdicts


def run_adjudication_phase(
    snapshot_id: str,
    snapshot_dir: Path,
    extraction_results: list,
    reconstruction_verdicts: list,
    coverage_verdicts: list,
    confidence_threshold: float = 0.7,
) -> Path:
    """Run Phase 5: Ambiguity adjudication.

    Args:
        snapshot_id: Snapshot identifier
        snapshot_dir: Path to snapshot directory
        extraction_results: List of ExtractionResult objects
        reconstruction_verdicts: List of ReconstructionVerdict objects
        coverage_verdicts: List of CoverageVerdict objects
        confidence_threshold: Minimum confidence to auto-accept

    Returns:
        Path to adjudication session JSON file
    """
    print("\nPhase 5: Ambiguity adjudication", file=sys.stderr)

    # Identify cases requiring human review
    ambiguity_cases = identify_ambiguities(
        extraction_results=extraction_results,
        reconstruction_verdicts=reconstruction_verdicts,
        coverage_verdicts=coverage_verdicts,
        confidence_threshold=confidence_threshold,
    )

    print(f"  Found {len(ambiguity_cases)} cases requiring adjudication", file=sys.stderr)

    # Create adjudication session
    session = create_adjudication_session(snapshot_id, ambiguity_cases)

    # Save for human review
    adjudication_dir = snapshot_dir / ".humanvoice" / "adjudication"
    adjudication_dir.mkdir(parents=True, exist_ok=True)
    session_path = adjudication_dir / f"{session.session_id}.json"

    save_adjudication_session(session, str(session_path))
    print(f"  Saved adjudication session to {session_path.relative_to(snapshot_dir)}", file=sys.stderr)

    return session_path


def run_baseline_freeze_phase(
    snapshot_id: str,
    source_hash: str,
    snapshot_dir: Path,
    adjudication_session_path: Optional[Path],
    accepted_concepts: list,
    frozen_by: str,
) -> Path:
    """Run Phase 6: Frozen baseline creation.

    Args:
        snapshot_id: Snapshot identifier
        source_hash: Hash of source files
        snapshot_dir: Path to snapshot directory
        adjudication_session_path: Path to completed adjudication session (or None)
        accepted_concepts: List of ConceptCandidate objects after adjudication
        frozen_by: Name/identifier of person freezing baseline

    Returns:
        Path to frozen baseline JSON file
    """
    print("\nPhase 6: Frozen baseline creation", file=sys.stderr)

    # Load adjudication session if exists
    adjudication_session = None
    if adjudication_session_path and adjudication_session_path.exists():
        adjudication_session = load_adjudication_session(str(adjudication_session_path))

    # Create frozen baseline
    baseline = create_baseline_from_adjudication(
        snapshot_id=snapshot_id,
        source_hash=source_hash,
        adjudication_session=adjudication_session,
        accepted_concepts=accepted_concepts,
        frozen_by=frozen_by,
    )

    # Verify integrity
    is_valid, message = verify_baseline_integrity(baseline)
    if not is_valid:
        raise ValueError(f"Baseline integrity check failed: {message}")

    print(f"  Created baseline {baseline.baseline_id}", file=sys.stderr)
    print(f"  Total concepts: {baseline.total_concepts}", file=sys.stderr)
    print(f"  Baseline hash: {baseline.baseline_hash[:16]}...", file=sys.stderr)

    # Save baseline
    baseline_dir = snapshot_dir / ".humanvoice" / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = baseline_dir / f"{baseline.baseline_id}.json"

    save_baseline(baseline, baseline_path)
    print(f"  Saved frozen baseline to {baseline_path.relative_to(snapshot_dir)}", file=sys.stderr)

    return baseline_path


def run_dependency_planning_phase(
    snapshot_dir: Path,
    baseline_path: Path,
) -> Path:
    """Run Phase 7: Dependency planning.

    Args:
        snapshot_dir: Path to snapshot directory
        baseline_path: Path to frozen baseline JSON

    Returns:
        Path to dependency graph JSON file
    """
    print("\nPhase 7: Dependency planning", file=sys.stderr)

    # Load baseline
    baseline = load_baseline(baseline_path)

    # Create dependency graph
    dependency_graph = create_dependency_graph(baseline)

    print(f"  Found {len(dependency_graph.dependencies)} dependencies", file=sys.stderr)

    # Check for cycles
    concept_ids = {entry.concept_id for entry in baseline.concept_entries}
    cycles = detect_cycles(dependency_graph.dependencies, concept_ids)

    if cycles:
        print(f"  WARNING: Detected {len(cycles)} circular dependencies", file=sys.stderr)
        for cycle in cycles[:3]:  # Show first 3
            print(f"    Cycle: {' -> '.join(cycle)}", file=sys.stderr)
        print("  These require human resolution before teaching order can be finalized", file=sys.stderr)
    else:
        print(f"  Teaching order computed: {len(dependency_graph.teaching_order)} concepts", file=sys.stderr)

    # Save dependency graph
    deps_dir = snapshot_dir / ".humanvoice" / "dependencies"
    deps_dir.mkdir(parents=True, exist_ok=True)
    deps_path = deps_dir / f"dependencies-{baseline.baseline_id}.json"

    save_dependency_graph(dependency_graph, deps_path)
    print(f"  Saved dependency graph to {deps_path.relative_to(snapshot_dir)}", file=sys.stderr)

    return deps_path


def run_unit_splitting_phase(
    snapshot_dir: Path,
    baseline_path: Path,
    dependency_graph_path: Path,
    span_texts: dict,
    max_unit_size: int = 2000,
) -> Path:
    """Run Phase 8: Semantic unit splitting.

    Args:
        snapshot_dir: Path to snapshot directory
        baseline_path: Path to frozen baseline JSON
        dependency_graph_path: Path to dependency graph JSON
        span_texts: Map of span_id -> text for size estimation
        max_unit_size: Target max words per unit

    Returns:
        Path to rewrite plan JSON file
    """
    print("\nPhase 8: Semantic unit splitting", file=sys.stderr)

    # Load baseline and dependency graph
    baseline = load_baseline(baseline_path)
    from humanvoice.dependency_planning import load_dependency_graph
    dependency_graph = load_dependency_graph(dependency_graph_path)

    # Create rewrite plan
    plan = create_rewrite_plan(
        baseline=baseline,
        dependency_graph=dependency_graph,
        span_texts=span_texts,
        max_unit_size=max_unit_size,
    )

    print(f"  Created rewrite plan with {plan.total_units} units", file=sys.stderr)

    # Verify completeness
    is_complete, issues = verify_unit_plan_completeness(plan, baseline)
    if not is_complete:
        print(f"  WARNING: Plan completeness issues:", file=sys.stderr)
        for issue in issues:
            print(f"    - {issue}", file=sys.stderr)

    # Print unit summary
    for unit in plan.units[:5]:  # Show first 5
        print(f"  Unit {unit.unit_id}: {len(unit.concept_ids)} concepts, "
              f"~{unit.estimated_words} words, {len(unit.prerequisites)} prereqs", file=sys.stderr)
    if len(plan.units) > 5:
        print(f"  ... and {len(plan.units) - 5} more units", file=sys.stderr)

    # Save rewrite plan
    plan_dir = snapshot_dir / ".humanvoice" / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / f"{plan.plan_id}.json"

    save_rewrite_plan(plan, plan_path)
    print(f"  Saved rewrite plan to {plan_path.relative_to(snapshot_dir)}", file=sys.stderr)

    return plan_path
