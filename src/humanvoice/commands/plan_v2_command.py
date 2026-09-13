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

    # Load span texts for size estimation
    spans_path = inventory_dir / "spans.jsonl"
    if not spans_path.exists():
        print(f"Error: Span records not found: {spans_path}", file=sys.stderr)
        return 3

    span_texts = {}
    try:
        with open(spans_path, 'r') as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    span_id = record.get("record_id", "")
                    text = record.get("text", "")
                    if span_id:
                        span_texts[span_id] = text
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
    }
    print(json.dumps(result, indent=2))

    return 0


if __name__ == '__main__':
    sys.exit(run(None))
