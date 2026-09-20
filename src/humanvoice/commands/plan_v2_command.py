"""
hv plan-v2 - Generate semantic rewrite plan from frozen baseline.

V2 planning flow:
1. Load frozen baseline from inventory
2. Create dependency graph from concept prerequisites
3. Split into rewrite units respecting dependencies and size constraints
4. Save rewrite plan for downstream rewrite phase

Exit codes:
  0 - plan generated successfully
  3 - invalid input (missing baseline, incomplete inventory)
  4 - internal error
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from humanvoice.concept_baseline import load_baseline, verify_baseline_integrity
from humanvoice.dependency_planning import create_dependency_graph, save_dependency_graph, detect_cycles
from humanvoice.semantic_unit_splitting import create_rewrite_plan, save_rewrite_plan, verify_unit_plan_completeness


def validate_plan(plan, baseline, snapshot_dir: Path) -> list[str]:
    """
    Validate plan meets all critical invariants.

    Returns list of validation errors (empty if valid).

    Checks:
    1. All units contiguous (max gap: 10KB)
    2. No overlapping units
    3. All span IDs exist in inventory
    4. No passenger concepts (concepts in units without source spans)
    """
    errors = []

    # Load span offsets
    spans_path = snapshot_dir / ".humanvoice" / "inventory" / "spans.jsonl"
    if not spans_path.exists():
        errors.append(f"Missing spans.jsonl at {spans_path}")
        return errors

    span_offsets = {}
    with open(spans_path) as f:
        for line in f:
            if line.strip():
                span = json.loads(line)
                span_offsets[span['record_id']] = {
                    'byte_start': span['byte_start'],
                    'byte_end': span['byte_end']
                }

    # Check 1: All units contiguous
    for unit in plan.units:
        is_contiguous, reason = check_unit_contiguity(unit, span_offsets, max_gap_kb=10)
        if not is_contiguous:
            errors.append(f"{unit.unit_id}: {reason}")

    # Check 2: No overlapping units
    overlaps = find_overlapping_units(plan.units, span_offsets)
    for u1, u2 in overlaps:
        errors.append(f"Overlapping units: {u1} ↔ {u2}")

    # Check 3: All span IDs exist
    for unit in plan.units:
        for span_id in unit.source_span_ids:
            if span_id not in span_offsets:
                errors.append(f"{unit.unit_id}: missing span {span_id}")

    # Check 4: No passenger concepts (concepts in units without spans in that unit)
    # Build concept map
    concept_map = {e.concept_id: e for e in baseline.concept_entries}

    for unit in plan.units:
        unit_span_set = set(unit.source_span_ids)

        for concept_id in unit.concept_ids:
            # Find concept in baseline
            concept_entry = concept_map.get(concept_id)
            if not concept_entry:
                errors.append(f"{unit.unit_id}: concept {concept_id} not in baseline")
                continue

            # Check if concept has at least one span in unit
            concept_spans_in_unit = [sid for sid in concept_entry.source_span_ids if sid in unit_span_set]
            if not concept_spans_in_unit:
                errors.append(f"{unit.unit_id}: passenger concept {concept_id} (no spans in unit)")

    return errors


def check_unit_contiguity(unit, span_offsets: dict, max_gap_kb: int = 10) -> tuple[bool, str]:
    """
    Check if unit has contiguous spans.

    Returns: (is_valid, failure_reason)
    """
    positions = []
    for span_id in unit.source_span_ids:
        if span_id not in span_offsets:
            return False, f"span_id_not_found: {span_id}"

        span = span_offsets[span_id]
        positions.append((span['byte_start'], span['byte_end']))

    if not positions:
        return True, None

    # Sort by start position
    positions.sort()

    # Check gaps
    max_gap_bytes = max_gap_kb * 1024
    for i in range(len(positions) - 1):
        gap = positions[i+1][0] - positions[i][1]
        if gap > max_gap_bytes:
            return False, f"non_contiguous: gap of {gap/1024:.1f}KB exceeds {max_gap_kb}KB threshold"

    return True, None


def find_overlapping_units(units, span_offsets: dict) -> list[tuple[str, str]]:
    """
    Find all overlapping unit pairs.

    Returns list of (unit_id_1, unit_id_2) tuples.
    """
    overlaps = []

    for i, unit1 in enumerate(units):
        range1 = get_unit_byte_range(unit1, span_offsets)
        if range1[0] is None:
            continue

        for unit2 in units[i+1:]:
            range2 = get_unit_byte_range(unit2, span_offsets)
            if range2[0] is None:
                continue

            # Check for overlap
            if range1[0] < range2[1] and range2[0] < range1[1]:
                overlaps.append((unit1.unit_id, unit2.unit_id))

    return overlaps


def get_unit_byte_range(unit, span_offsets: dict) -> tuple[int, int]:
    """Get the min-max byte range for a unit's spans."""
    positions = []
    for span_id in unit.source_span_ids:
        if span_id in span_offsets:
            span = span_offsets[span_id]
            positions.append((span['byte_start'], span['byte_end']))

    if not positions:
        return None, None

    positions.sort()
    return positions[0][0], positions[-1][1]


def run(args) -> int:
    """
    Generate semantic rewrite plan from frozen baseline.

    Requires:
      - Frozen baseline from hv inventory --freeze
      - Span texts for size estimation

    Produces:
      - Dependency graph (concepts with prerequisites)
      - Rewrite plan (semantic units with teaching sequence)
    """
    snapshot_dir = args.snapshot.resolve()

    # Check snapshot exists
    if not snapshot_dir.exists():
        print(f"Error: Snapshot does not exist: {snapshot_dir}", file=sys.stderr)
        return 3

    # Load manifest
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: Snapshot manifest not found: {manifest_path}", file=sys.stderr)
        return 3

    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"Error: Cannot read manifest: {e}", file=sys.stderr)
        return 4

    snapshot_id = manifest["snapshot_id"]
    inventory_dir = snapshot_dir / ".humanvoice" / "inventory"

    # Check baseline exists
    baseline_path = inventory_dir / "baseline.json"
    if not baseline_path.exists():
        print(f"Error: Baseline not found. Run 'hv inventory --freeze' first.", file=sys.stderr)
        print(f"  Expected: {baseline_path}", file=sys.stderr)
        return 3

    # Load baseline
    print(f"Loading frozen baseline from {baseline_path.relative_to(snapshot_dir)}", file=sys.stderr)
    try:
        baseline = load_baseline(baseline_path)
    except Exception as e:
        print(f"Error: Cannot load baseline: {e}", file=sys.stderr)
        return 4

    # Verify baseline integrity
    is_valid, issues = verify_baseline_integrity(baseline)
    if not is_valid:
        print(f"Error: Baseline integrity check failed:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 3

    print(f"  Baseline: {baseline.total_concepts} concepts", file=sys.stderr)

    # Load span texts for size estimation (using byte offsets from source files)
    spans_path = inventory_dir / "spans.jsonl"
    if not spans_path.exists():
        print(f"Error: Span records not found: {spans_path}", file=sys.stderr)
        return 3

    span_texts = {}
    source_files = {}
    source_dir = snapshot_dir / "source"

    try:
        with open(spans_path, 'r') as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    span_id = record.get("record_id", "")
                    source_file = record.get("source_file")

                    # Load source file if not already loaded
                    if source_file and source_file not in source_files:
                        source_path = source_dir / source_file
                        if source_path.exists():
                            source_files[source_file] = source_path.read_bytes()

                    # Extract text using byte offsets
                    if source_file and source_file in source_files:
                        byte_start = record.get("byte_start", 0)
                        byte_end = record.get("byte_end", 0)
                        exact_text = source_files[source_file][byte_start:byte_end].decode('utf-8', errors='replace')
                        span_texts[span_id] = exact_text
    except Exception as e:
        print(f"Error: Cannot load span texts: {e}", file=sys.stderr)
        return 4

    print(f"  Loaded {len(span_texts)} span texts", file=sys.stderr)

    # Phase 1: Create dependency graph
    print("", file=sys.stderr)
    print("Phase 1: Dependency graph creation", file=sys.stderr)

    try:
        dependency_graph = create_dependency_graph(baseline)
    except Exception as e:
        print(f"Error: Dependency graph creation failed: {e}", file=sys.stderr)
        return 4

    print(f"  Created dependency graph with {len(dependency_graph.dependencies)} dependencies", file=sys.stderr)

    # Check for cycles
    concept_ids = {entry.concept_id for entry in baseline.concept_entries}
    cycles = detect_cycles(dependency_graph.dependencies, concept_ids)
    has_cycles = len(cycles) > 0
    if has_cycles:
        print(f"  Warning: Detected {len(cycles)} dependency cycles:", file=sys.stderr)
        for cycle in cycles[:3]:  # Show first 3
            print(f"    - {' -> '.join(cycle)}", file=sys.stderr)
        if len(cycles) > 3:
            print(f"    ... and {len(cycles) - 3} more cycles", file=sys.stderr)

    # Save dependency graph
    plans_dir = snapshot_dir / ".humanvoice" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    graph_path = plans_dir / f"dependencies-{baseline.baseline_id}.json"
    save_dependency_graph(dependency_graph, graph_path)
    print(f"  Saved dependency graph to {graph_path.relative_to(snapshot_dir)}", file=sys.stderr)

    # Phase 2: Semantic unit splitting
    print("", file=sys.stderr)
    print("Phase 2: Semantic unit splitting", file=sys.stderr)

    max_unit_size = getattr(args, 'max_unit_size', 2000)

    try:
        plan = create_rewrite_plan(
            baseline=baseline,
            dependency_graph=dependency_graph,
            span_texts=span_texts,
            max_unit_size=max_unit_size,
            snapshot_dir=snapshot_dir,
        )
    except Exception as e:
        print(f"Error: Rewrite plan creation failed: {e}", file=sys.stderr)
        return 4

    print(f"  Created rewrite plan with {plan.total_units} units", file=sys.stderr)

    # Verify completeness
    is_complete, plan_issues = verify_unit_plan_completeness(plan, baseline)
    if not is_complete:
        print(f"  Warning: Plan completeness issues:", file=sys.stderr)
        for issue in plan_issues:
            print(f"    - {issue}", file=sys.stderr)

    # Show unit summary
    print(f"", file=sys.stderr)
    print(f"Unit summary:", file=sys.stderr)
    for unit in plan.units[:5]:  # Show first 5
        print(f"  Unit {unit.unit_id}: {len(unit.concept_ids)} concepts, "
              f"~{unit.estimated_words} words, {len(unit.prerequisites)} prereqs", file=sys.stderr)
    if len(plan.units) > 5:
        print(f"  ... and {len(plan.units) - 5} more units", file=sys.stderr)

    # Save rewrite plan
    plan_path = plans_dir / f"{plan.plan_id}.json"
    save_rewrite_plan(plan, plan_path)
    print(f"", file=sys.stderr)
    print(f"Saved rewrite plan to {plan_path.relative_to(snapshot_dir)}", file=sys.stderr)

    # Phase 3: Validate plan (fail-closed boundary check)
    print(f"", file=sys.stderr)
    print(f"Phase 3: Plan validation", file=sys.stderr)

    validation_errors = validate_plan(plan, baseline, snapshot_dir)

    if validation_errors:
        print(f"", file=sys.stderr)
        print(f"Error: Plan validation failed with {len(validation_errors)} errors:", file=sys.stderr)
        for error in validation_errors[:10]:  # Show first 10
            print(f"  - {error}", file=sys.stderr)
        if len(validation_errors) > 10:
            print(f"  ... and {len(validation_errors) - 10} more errors", file=sys.stderr)
        return 4  # Internal error - plan violates invariants

    print(f"  ✓ All units contiguous (max gap: 10KB)", file=sys.stderr)
    print(f"  ✓ No overlapping units", file=sys.stderr)
    print(f"  ✓ All span IDs valid", file=sys.stderr)
    print(f"  ✓ No passenger concepts", file=sys.stderr)

    # Output result
    result = {
        "status": "plan_created",
        "snapshot_id": snapshot_id,
        "baseline_id": baseline.baseline_id,
        "plan_id": plan.plan_id,
        "total_units": plan.total_units,
        "total_concepts": plan.total_concepts,
        "max_unit_size": plan.max_unit_size,
        "dependency_cycles": len(cycles) if has_cycles else 0,
        "plan_complete": is_complete,
        "plan_validated": True,
    }
    print(json.dumps(result, indent=2))

    return 0


if __name__ == '__main__':
    sys.exit(run(None))
