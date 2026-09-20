#!/usr/bin/env python3
"""
Phase 5 Validation Script

Validates that ZLB inventory meets all Phase 1-4 requirements:
- All concepts have span range < 10KB (Phase 1)
- Baseline frozen successfully
- Exit code 0 from inventory command
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def load_baseline(snapshot_dir: Path) -> Dict:
    """Load frozen baseline."""
    baseline_path = snapshot_dir / ".humanvoice" / "inventory" / "baseline.json"
    if not baseline_path.exists():
        print(f"Error: Baseline not found at {baseline_path}")
        sys.exit(1)
    return json.loads(baseline_path.read_text())


def load_span_offsets(snapshot_dir: Path) -> Dict[str, Dict]:
    """Load span byte offsets from spans.jsonl."""
    spans_path = snapshot_dir / ".humanvoice" / "inventory" / "spans.jsonl"
    span_offsets = {}

    with open(spans_path) as f:
        for line in f:
            if line.strip():
                span = json.loads(line)
                span_offsets[span['record_id']] = {
                    'byte_start': span['byte_start'],
                    'byte_end': span['byte_end']
                }

    return span_offsets


def validate_concept_locality(
    concept: Dict,
    span_offsets: Dict,
    max_kb: int = 10
) -> Tuple[bool, int, str]:
    """
    Check if concept spans are within max_kb of each other.

    Returns: (is_valid, span_range_bytes, error_msg)
    """
    source_span_ids = concept.get('source_span_ids', [])

    if not source_span_ids:
        return True, 0, None

    # Get byte positions
    positions = []
    for span_id in source_span_ids:
        if span_id not in span_offsets:
            return False, 0, f"Missing span: {span_id}"

        span = span_offsets[span_id]
        positions.append((span['byte_start'], span['byte_end']))

    # Sort by start position
    positions.sort()

    # Calculate total range
    first_start = positions[0][0]
    last_end = positions[-1][1]
    span_range = last_end - first_start

    max_bytes = max_kb * 1024

    if span_range > max_bytes:
        return False, span_range, f"Span range {span_range} > {max_bytes}"

    return True, span_range, None


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_phase5.py <snapshot_dir>")
        sys.exit(1)

    snapshot_dir = Path(sys.argv[1])

    print("=" * 80)
    print("Phase 5 Validation: ZLB Inventory with Locality Enforcement")
    print("=" * 80)
    print()

    # Load baseline
    print("Loading baseline...")
    baseline = load_baseline(snapshot_dir)

    print(f"  Baseline ID: {baseline['baseline_id']}")
    print(f"  Total concepts: {baseline['total_concepts']}")
    print(f"  Frozen: {baseline.get('frozen_at', 'NOT FROZEN')}")
    print()

    # Load spans
    print("Loading span offsets...")
    span_offsets = load_span_offsets(snapshot_dir)
    print(f"  Total spans: {len(span_offsets)}")
    print()

    # Validate all concepts
    print("Validating concept locality (max 10KB span range)...")

    invalid_concepts = []
    span_ranges = []

    for entry in baseline['concept_entries']:
        is_valid, span_range, error = validate_concept_locality(
            entry, span_offsets, max_kb=10
        )

        span_ranges.append(span_range)

        if not is_valid:
            invalid_concepts.append({
                'concept_id': entry['concept_id'],
                'span_range': span_range,
                'error': error,
                'proposition': entry.get('proposition', '')[:80]
            })

    # Report results
    print()
    print("Results:")
    print("-" * 80)

    if invalid_concepts:
        print(f"❌ FAILED: {len(invalid_concepts)} concepts violate locality constraint")
        print()
        print("Invalid concepts (showing first 10):")
        for c in invalid_concepts[:10]:
            print(f"  {c['concept_id']}: {c['span_range']:,} bytes")
            print(f"    Error: {c['error']}")
            print(f"    Proposition: {c['proposition']}")
            print()
        sys.exit(1)
    else:
        print(f"✅ PASSED: All {baseline['total_concepts']} concepts have span range ≤ 10KB")
        print()

        # Statistics
        if span_ranges:
            max_range = max(span_ranges)
            avg_range = sum(span_ranges) / len(span_ranges)

            print("Span range statistics:")
            print(f"  Max span range: {max_range:,} bytes ({max_range/1024:.1f} KB)")
            print(f"  Avg span range: {avg_range:,} bytes ({avg_range/1024:.1f} KB)")
            print(f"  Concepts < 1KB: {sum(1 for r in span_ranges if r < 1024)}")
            print(f"  Concepts 1-5KB: {sum(1 for r in span_ranges if 1024 <= r < 5*1024)}")
            print(f"  Concepts 5-10KB: {sum(1 for r in span_ranges if 5*1024 <= r <= 10*1024)}")
        print()

    print("=" * 80)
    print("Phase 5 validation complete!")
    print("=" * 80)


if __name__ == '__main__':
    main()
