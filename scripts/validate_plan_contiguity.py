#!/usr/bin/env python3
"""
Validate that all units in a plan are contiguous.

Usage:
    python scripts/validate_plan_contiguity.py <snapshot_dir>

Checks:
1. All units have max 10KB gap between spans
2. No overlapping units
3. All span IDs exist in spans.jsonl
4. No passenger concepts (concepts without source spans in unit)

Exit codes:
    0 - All validation checks passed
    1 - Validation errors found
    2 - Missing required files
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple, Dict


def load_plan(snapshot_dir: Path) -> dict:
    """Load the most recent plan file."""
    plans_dir = snapshot_dir / ".humanvoice" / "plans"
    if not plans_dir.exists():
        print(f"❌ Plans directory not found: {plans_dir}")
        sys.exit(2)

    plan_files = list(plans_dir.glob("plan-*.json"))
    if not plan_files:
        print(f"❌ No plan files found in: {plans_dir}")
        sys.exit(2)

    # Use most recent plan
    plan_file = sorted(plan_files)[-1]
    print(f"Loading plan: {plan_file.name}")

    return json.loads(plan_file.read_text())


def load_spans(snapshot_dir: Path) -> Dict[str, dict]:
    """Load span offsets from spans.jsonl."""
    spans_path = snapshot_dir / ".humanvoice" / "inventory" / "spans.jsonl"
    if not spans_path.exists():
        print(f"❌ Spans file not found: {spans_path}")
        sys.exit(2)

    span_offsets = {}
    with open(spans_path) as f:
        for line in f:
            if line.strip():
                span = json.loads(line)
                span_offsets[span['record_id']] = {
                    'byte_start': span['byte_start'],
                    'byte_end': span['byte_end']
                }

    print(f"Loaded {len(span_offsets)} spans")
    return span_offsets


def load_baseline(snapshot_dir: Path) -> dict:
    """Load baseline for concept validation."""
    baseline_path = snapshot_dir / ".humanvoice" / "inventory" / "baseline.json"
    if not baseline_path.exists():
        print(f"❌ Baseline file not found: {baseline_path}")
        sys.exit(2)

    return json.loads(baseline_path.read_text())


def check_unit_contiguity(
    unit: dict,
    span_offsets: Dict[str, dict],
    max_gap_kb: int = 10
) -> Tuple[bool, str]:
    """
    Check if unit spans are contiguous (max gap <= threshold).

    Returns: (is_valid, error_message)
    """
    span_ids = unit['source_span_ids']

    if len(span_ids) < 2:
        # Single span is trivially contiguous
        return True, ""

    # Get positions
    positions = []
    for sid in span_ids:
        if sid not in span_offsets:
            return False, f"Missing span: {sid}"

        positions.append((
            span_offsets[sid]['byte_start'],
            span_offsets[sid]['byte_end']
        ))

    # Sort by start position
    positions.sort()

    # Check gaps
    max_gap_bytes = max_gap_kb * 1024

    for i in range(len(positions) - 1):
        gap = positions[i+1][0] - positions[i][1]
        if gap > max_gap_bytes:
            return False, f"Gap {gap} bytes > {max_gap_bytes} bytes"

    return True, ""


def get_unit_byte_range(
    unit: dict,
    span_offsets: Dict[str, dict]
) -> Tuple[int, int]:
    """Get (min_start, max_end) for unit's spans."""
    positions = []
    for sid in unit['source_span_ids']:
        if sid in span_offsets:
            positions.append((
                span_offsets[sid]['byte_start'],
                span_offsets[sid]['byte_end']
            ))

    if not positions:
        return (0, 0)

    positions.sort()
    return (positions[0][0], positions[-1][1])


def find_overlapping_units(
    units: List[dict],
    span_offsets: Dict[str, dict]
) -> List[Tuple[str, str]]:
    """Find pairs of units with overlapping byte ranges."""
    overlaps = []

    # Build unit ranges
    unit_ranges = []
    for unit in units:
        start, end = get_unit_byte_range(unit, span_offsets)
        if start < end:  # Valid range
            unit_ranges.append((unit['unit_id'], start, end))

    # Sort by start position
    unit_ranges.sort(key=lambda x: x[1])

    # Check for overlaps
    for i in range(len(unit_ranges) - 1):
        uid1, start1, end1 = unit_ranges[i]

        for j in range(i + 1, len(unit_ranges)):
            uid2, start2, end2 = unit_ranges[j]

            # If start2 >= end1, no more overlaps possible for unit i
            if start2 >= end1:
                break

            # Overlap detected
            overlaps.append((uid1, uid2))

    return overlaps


def check_passenger_concepts(
    unit: dict,
    baseline: dict,
    span_offsets: Dict[str, dict]
) -> List[str]:
    """
    Check for passenger concepts (concepts in unit without source spans in unit).

    Returns: List of passenger concept IDs
    """
    unit_span_ids = set(unit['source_span_ids'])
    passengers = []

    for concept_entry in baseline['concept_entries']:
        concept_id = concept_entry['concept_id']

        # Is concept in this unit?
        if concept_id not in unit['concept_ids']:
            continue

        # Does concept have any spans in this unit?
        concept_span_ids = set(concept_entry['source_span_ids'])
        overlap = unit_span_ids & concept_span_ids

        if not overlap:
            passengers.append(concept_id)

    return passengers


def validate_plan(snapshot_dir: Path) -> int:
    """
    Run all validation checks on plan.

    Returns: 0 if all checks pass, 1 if errors found
    """
    print("=" * 70)
    print("Plan Contiguity Validation")
    print("=" * 70)
    print()

    # Load data
    plan = load_plan(snapshot_dir)
    span_offsets = load_spans(snapshot_dir)
    baseline = load_baseline(snapshot_dir)

    print(f"Plan: {plan['plan_id']}")
    print(f"Units: {plan['total_units']}")
    print()

    errors = []

    # Check 1: Unit contiguity
    print("Check 1: Unit Contiguity (max 10KB gap)")
    print("-" * 70)

    for unit in plan['units']:
        is_valid, reason = check_unit_contiguity(unit, span_offsets)
        if not is_valid:
            error = f"{unit['unit_id']}: {reason}"
            errors.append(error)
            print(f"  ❌ {error}")

    if not errors:
        print(f"  ✅ All {plan['total_units']} units are contiguous")
    print()

    # Check 2: Overlapping units
    print("Check 2: No Overlapping Units")
    print("-" * 70)

    overlaps = find_overlapping_units(plan['units'], span_offsets)
    if overlaps:
        for uid1, uid2 in overlaps:
            error = f"Overlapping units: {uid1} ↔ {uid2}"
            errors.append(error)
            print(f"  ❌ {error}")
    else:
        print(f"  ✅ No overlapping units detected")
    print()

    # Check 3: Missing spans
    print("Check 3: All Span IDs Exist")
    print("-" * 70)

    missing_spans = set()
    for unit in plan['units']:
        for span_id in unit['source_span_ids']:
            if span_id not in span_offsets:
                error = f"{unit['unit_id']}: missing span {span_id}"
                errors.append(error)
                missing_spans.add(span_id)

    if missing_spans:
        print(f"  ❌ {len(missing_spans)} missing span IDs")
    else:
        print(f"  ✅ All span IDs exist")
    print()

    # Check 4: Passenger concepts
    print("Check 4: No Passenger Concepts")
    print("-" * 70)

    passenger_count = 0
    for unit in plan['units']:
        passengers = check_passenger_concepts(unit, baseline, span_offsets)
        if passengers:
            passenger_count += len(passengers)
            for concept_id in passengers[:3]:  # Show first 3
                error = f"{unit['unit_id']}: passenger concept {concept_id}"
                errors.append(error)
                print(f"  ❌ {error}")
            if len(passengers) > 3:
                print(f"  ... and {len(passengers) - 3} more")

    if passenger_count == 0:
        print(f"  ✅ No passenger concepts detected")
    print()

    # Summary
    print("=" * 70)
    if errors:
        print(f"❌ VALIDATION FAILED: {len(errors)} error(s) found")
        print()
        print("First 10 errors:")
        for error in errors[:10]:
            print(f"  - {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
        return 1
    else:
        print("✅ VALIDATION PASSED: All checks successful")
        print()
        print("Summary:")
        print(f"  - {plan['total_units']} units")
        print(f"  - All units contiguous (max 10KB gap)")
        print(f"  - No overlapping units")
        print(f"  - All span IDs exist")
        print(f"  - No passenger concepts")
        return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python validate_plan_contiguity.py <snapshot_dir>")
        sys.exit(2)

    snapshot_dir = Path(sys.argv[1])
    if not snapshot_dir.exists():
        print(f"❌ Snapshot directory not found: {snapshot_dir}")
        sys.exit(2)

    sys.exit(validate_plan(snapshot_dir))
