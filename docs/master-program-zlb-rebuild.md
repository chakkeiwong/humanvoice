# Master Program: ZLB Pipeline Architectural Rebuild

**Program ID:** MP-ZLB-REBUILD  
**Created:** 2026-09-19  
**Status:** Draft  
**Goal:** Fix ZLB assembly failures and scale pipeline to 500-800 page monographs

---

## Executive Summary

The ZLB manuscript (3,368 lines, 189KB) exposed fundamental architectural defects in the humanvoice v2 pipeline:

1. **Non-contiguous units:** Planner creates units with spans separated by 140KB gaps
2. **False overlaps:** Assembly treats gaps as occupied, creating artificial conflicts
3. **Deleted concepts:** 4/33 units lost 29 concepts during rewrite (15 in unit-014 alone)
4. **Missing span IDs:** 56 span references in plan not found in inventory
5. **Partial assembly:** Only 22/33 units assembled (67% completion)

These are not edge cases. They are systematic failures in the pipeline's core assumptions:
- **Planning model:** Assumes units can have non-contiguous spans
- **Assembly model:** Assumes units map to contiguous byte ranges

This program implements a 6-phase architectural rebuild to resolve the mismatch and scale to 800-page monographs.

---

## Context: User Feedback

User's critical insight (2026-09-19):

> "I think option A is better. However, I don't think that really addresses all the root causes. It seems that we have a problem in the understanding of 'concepts' in the work and how to explain it better. How can we have an even better more thorough rebuild so that we can handle monograph of 500 to 800 pages? We are encountering so many issues even for such a small document."

User's testing directive:

> "The program does not suggest good thorough tests to test the implementation. How can we test this better. On top of the tests you can design, I think you should clone the ZLB document and make it part of the integration test."

---

## Program Structure

### Phase 1: Concept Locality Enforcement (COMPLETE ✅)
**Goal:** Ensure concepts are LOCAL, not document-wide  
**Why:** Concepts spanning 140KB breaks assembly and rewrite coherence  
**Status:** Complete, 9 tests passing

### Phase 2: Planner Contiguity Enforcement (COMPLETE ✅)
**Goal:** Ensure all units have contiguous spans (gap < 10KB threshold)  
**Why:** Fixes root cause of false overlaps  
**Status:** Complete, 8 tests passing

### Phase 3: Phase Boundary Validation (COMPLETE ✅)
**Goal:** Add fail-closed checks between every pipeline phase  
**Why:** Catch defects early, not at assembly  
**Status:** Complete, 14 tests passing, ZLB validates successfully

### Phase 3.5: Passenger Concept Filtering (2.5 hours) **COMPLETE ✅**
**Goal:** Remove "passenger concepts" (concepts in units but without source spans)  
**Why:** Silent data corruption; rewrite cannot produce content for concepts without source text  
**Status:** Complete, 2-layer filtering + metrics + validation, 4 tests passing

### Phase 4: Assembly Simplification (1 day)
**Goal:** Remove gap-handling complexity, enforce 1:1 unit-to-patch mapping  
**Why:** Simpler assembly logic is more reliable

### Phase 5: ZLB End-to-End Validation (1 day)
**Goal:** Run complete pipeline on ZLB with new architecture  
**Why:** Validate fixes work on the real document that exposed defects

### Phase 6: Scale Testing (2-3 days)
**Goal:** Test on 10-page, 50-page, 100-page, 500-page fixtures  
**Why:** Validate scaling to 800-page target

**Total Duration:** 10-13 days (updated with Phase 3.5)  
**Deliverable:** Pipeline that completes ZLB with 100% assembly coverage

---

## Phase 1: Concept Locality Enforcement

### Problem

Current extraction allows concepts to reference spans anywhere in the document. Example from ZLB:

```
concept-042: "zero_lower_bound"
  source_span_ids: ["span-015", "span-1247", "span-2891"]
  Byte range: [15910, 160627] = 144KB span
```

This creates units that inherit those non-contiguous spans, breaking assembly.

### Solution

**File:** `src/humanvoice/model_extraction.py`

Add validation after concept extraction (line ~180):

```python
def validate_concept_locality(concept: ConceptEntry, span_offsets: dict, max_span_range_kb: int = 10) -> tuple[bool, str]:
    """
    Validate that all spans for a concept are within max_span_range_kb of each other.
    
    Returns: (is_valid, failure_reason)
    """
    if not concept.source_span_ids:
        return True, None
    
    # Get byte positions
    positions = []
    for span_id in concept.source_span_ids:
        if span_id not in span_offsets:
            return False, f"span_id_not_found: {span_id}"
        
        span = span_offsets[span_id]
        positions.append((span['byte_start'], span['byte_end']))
    
    # Sort by start position
    positions.sort()
    
    # Calculate total range
    first_start = positions[0][0]
    last_end = positions[-1][1]
    total_range = last_end - first_start
    max_range_bytes = max_span_range_kb * 1024
    
    if total_range > max_range_bytes:
        return False, f"span_range_exceeds_threshold: {total_range} bytes > {max_range_bytes} bytes"
    
    return True, None
```

Call in extraction workflow after each concept is extracted:

```python
# After line ~180 in extract_concepts_from_window
for concept in extracted_concepts:
    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)
    if not is_valid:
        # Option 1: Reject concept entirely
        logging.warning(f"Concept {concept.concept_id} rejected: {reason}")
        continue
        
        # Option 2: Split into multiple concepts (better for preservation)
        split_concepts = split_concept_by_span_clusters(concept, span_offsets, max_gap_kb=5)
        baseline.concept_entries.extend(split_concepts)
```

### Tests

**File:** `tests/test_concept_extraction_locality.py`

```python
def test_validate_concept_locality_rejects_large_span_range():
    """Concepts with spans >10KB apart should be rejected."""
    concept = ConceptEntry(
        concept_id="test-001",
        source_span_ids=["span-001", "span-002"],
        content="test"
    )
    
    span_offsets = {
        "span-001": {"byte_start": 1000, "byte_end": 1500},
        "span-002": {"byte_start": 15000, "byte_end": 15500}  # 13.5KB gap
    }
    
    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)
    
    assert not is_valid
    assert "span_range_exceeds_threshold" in reason

def test_validate_concept_locality_accepts_contiguous_spans():
    """Concepts with spans <10KB apart should be accepted."""
    concept = ConceptEntry(
        concept_id="test-001",
        source_span_ids=["span-001", "span-002"],
        content="test"
    )
    
    span_offsets = {
        "span-001": {"byte_start": 1000, "byte_end": 1500},
        "span-002": {"byte_start": 2000, "byte_end": 2500}  # 500 byte gap
    }
    
    is_valid, reason = validate_concept_locality(concept, span_offsets, max_span_range_kb=10)
    
    assert is_valid
    assert reason is None
```

### Deliverable

- [ ] `validate_concept_locality()` implemented
- [ ] Integration in extraction workflow
- [ ] 5 unit tests covering edge cases
- [ ] Documentation: "Concept Locality Requirements" section in architecture doc

### Refresh Procedure

**CRITICAL:** Phase 1 changes extraction logic, requiring a clean inventory rebuild.

```bash
# Step 1: Delete old inventory artifacts
rm -rf sessions/zlb-v2-snapshot/.humanvoice/inventory/*

# Step 2: Rebuild inventory with new concept locality enforcement
hv inventory sessions/zlb-v2-snapshot --freeze --adjudicator test-harness

# Step 3: Verify new baseline created
BASELINE_ID=$(jq -r '.baseline_id' sessions/zlb-v2-snapshot/.humanvoice/inventory/baseline.json)
echo "New baseline: $BASELINE_ID"
echo "Previous baseline had 1,113 concepts (some with 140KB span ranges)"
echo "New baseline should have similar count but ALL concepts with span range < 10KB"
```

**Why refresh is required:**
- Old inventory has concepts with 140KB span ranges (e.g., concept-042)
- Testing new planner against old concepts would perpetuate the bug
- Must validate that extraction creates local concepts

### Exit Criteria

Run ZLB inventory with new validation:

```bash
hv inventory sessions/zlb-v2-snapshot --freeze --adjudicator test-harness
```

Expected: 
- Exit code 0
- No concepts with span range > 10KB
- Concept count within 1113 ± 100 (may decrease if concepts split, may increase if more granular)
- New baseline_id generated

---

## Phase 2: Planner Contiguity Enforcement

### Problem

Current planner (`semantic_unit_splitting.py`) collects ALL spans from ALL concepts in a unit, regardless of byte position. From lines 248-250:

```python
span_ids = set()
for entry in baseline.concept_entries:
    if entry.concept_id in concept_ids:
        span_ids.update(entry.source_span_ids)
```

This created unit-005 with 22 spans covering 4,769 bytes scattered across 144KB.

### Solution

**File:** `src/humanvoice/semantic_unit_splitting.py`

Modify `finalize_unit()` (starting line 223) to enforce contiguity:

```python
def finalize_unit(
    unit_id: str,
    concept_ids: set,
    baseline: FrozenBaseline,
    span_offsets: dict,
    max_gap_kb: int = 10
) -> List[RewriteUnit]:
    """
    Finalize unit with contiguity enforcement.
    
    If unit spans have gaps > max_gap_kb, split into multiple units.
    Returns list of units (1 if contiguous, N if split).
    """
    # Collect all spans from concepts
    span_ids = set()
    for entry in baseline.concept_entries:
        if entry.concept_id in concept_ids:
            span_ids.update(entry.source_span_ids)
    
    # Sort spans by byte position
    sorted_spans = sorted(
        [(sid, span_offsets[sid]['byte_start'], span_offsets[sid]['byte_end'])
         for sid in span_ids if sid in span_offsets],
        key=lambda x: x[1]
    )
    
    if not sorted_spans:
        return []
    
    # Build span clusters with gap threshold
    clusters = build_span_clusters(sorted_spans, max_gap_kb)
    
    if len(clusters) == 1:
        # Unit is contiguous, return as-is
        return [RewriteUnit(
            unit_id=unit_id,
            concept_ids=list(concept_ids),
            source_span_ids=[s[0] for s in sorted_spans],
            dependencies=[]  # Will be computed later
        )]
    else:
        # Unit is non-contiguous, split into multiple units
        units = []
        for i, cluster in enumerate(clusters):
            sub_unit_id = f"{unit_id}-cluster{i+1}"
            cluster_span_ids = [s[0] for s in cluster]
            
            # Assign concepts to cluster based on which spans they reference
            cluster_concept_ids = set()
            for entry in baseline.concept_entries:
                if entry.concept_id in concept_ids:
                    if any(sid in cluster_span_ids for sid in entry.source_span_ids):
                        cluster_concept_ids.add(entry.concept_id)
            
            units.append(RewriteUnit(
                unit_id=sub_unit_id,
                concept_ids=list(cluster_concept_ids),
                source_span_ids=cluster_span_ids,
                dependencies=[]
            ))
        
        return units

def build_span_clusters(sorted_spans: List[tuple], max_gap_kb: int) -> List[List[tuple]]:
    """
    Group spans into contiguous clusters.
    
    Args:
        sorted_spans: List of (span_id, byte_start, byte_end) sorted by byte_start
        max_gap_kb: Maximum gap in KB between spans in same cluster
    
    Returns:
        List of span clusters
    """
    if not sorted_spans:
        return []
    
    max_gap_bytes = max_gap_kb * 1024
    clusters = []
    current_cluster = [sorted_spans[0]]
    
    for span in sorted_spans[1:]:
        gap = span[1] - current_cluster[-1][2]  # gap = next_start - prev_end
        
        if gap <= max_gap_bytes:
            current_cluster.append(span)
        else:
            clusters.append(current_cluster)
            current_cluster = [span]
    
    clusters.append(current_cluster)
    return clusters
```

### Tests

**File:** `tests/test_semantic_unit_splitting_contiguity.py`

```python
def test_finalize_unit_contiguous_spans_single_unit():
    """Contiguous spans should produce single unit."""
    concept_ids = {"concept-001", "concept-002"}
    baseline = create_test_baseline_with_contiguous_concepts()
    span_offsets = load_test_span_offsets()
    
    units = finalize_unit("unit-001", concept_ids, baseline, span_offsets, max_gap_kb=10)
    
    assert len(units) == 1
    assert units[0].unit_id == "unit-001"

def test_finalize_unit_large_gap_splits_into_multiple():
    """Non-contiguous spans with gap >10KB should split."""
    concept_ids = {"concept-001", "concept-002"}
    baseline = create_test_baseline_with_noncontiguous_concepts(gap_kb=50)
    span_offsets = load_test_span_offsets()
    
    units = finalize_unit("unit-001", concept_ids, baseline, span_offsets, max_gap_kb=10)
    
    assert len(units) == 2
    assert units[0].unit_id == "unit-001-cluster1"
    assert units[1].unit_id == "unit-001-cluster2"
    
    # Verify no overlaps
    cluster1_spans = get_span_byte_range(units[0].source_span_ids, span_offsets)
    cluster2_spans = get_span_byte_range(units[1].source_span_ids, span_offsets)
    assert cluster1_spans[1] < cluster2_spans[0]  # end1 < start2

def test_build_span_clusters_threshold():
    """Cluster building should respect gap threshold."""
    spans = [
        ("s1", 1000, 1500),
        ("s2", 2000, 2500),   # 500 byte gap (OK)
        ("s3", 15000, 15500)  # 12.5KB gap (SPLIT)
    ]
    
    clusters = build_span_clusters(spans, max_gap_kb=10)
    
    assert len(clusters) == 2
    assert len(clusters[0]) == 2  # s1, s2
    assert len(clusters[1]) == 1  # s3
```

### Deliverable

- [ ] `build_span_clusters()` implemented
- [ ] `finalize_unit()` modified to enforce contiguity
- [ ] 8 unit tests covering edge cases
- [ ] Integration test: ZLB plan produces 0 non-contiguous units

### Refresh Procedure

**CRITICAL:** Phase 2 changes planning logic and depends on Phase 1 baseline.

```bash
# Step 1: Delete old plan artifacts
rm -rf sessions/zlb-v2-snapshot/.humanvoice/plans/*

# Step 2: Get NEW baseline_id from Phase 1
BASELINE_ID=$(jq -r '.baseline_id' sessions/zlb-v2-snapshot/.humanvoice/inventory/baseline.json)
echo "Using baseline from Phase 1: $BASELINE_ID"

# Step 3: Rebuild plan with new contiguity enforcement
hv plan sessions/zlb-v2-snapshot --baseline-id $BASELINE_ID

# Step 4: Verify new plan created
PLAN_ID=$(jq -r '.plan_id' sessions/zlb-v2-snapshot/.humanvoice/plans/plan-*.json)
UNIT_COUNT=$(jq '.total_units' sessions/zlb-v2-snapshot/.humanvoice/plans/plan-*.json)
echo "New plan: $PLAN_ID"
echo "Units: $UNIT_COUNT (previous: 33)"
echo "Checking for contiguity and overlaps..."
```

**Why refresh is required:**
- Old plan has non-contiguous units (e.g., unit-005 with 140KB gap)
- Testing new assembly against old units would fail for wrong reasons
- Must validate that planner creates contiguous units from Phase 1 baseline

### Exit Criteria

Run ZLB plan with new contiguity enforcement:

```bash
hv plan sessions/zlb-v2-snapshot --baseline-id <id>
```

Expected:
- Exit code 0
- Unit count may increase (33 → 50-60 units due to splitting)
- Zero units with gaps > 10KB
- Zero overlapping units
- New plan_id generated

Verify with:

```python
python tests/integration_real/test_zlb_golden.py::test_zlb_golden_path
# Should pass Phase 3 (plan) invariant checks
```
```

---

## Phase 3: Phase Boundary Validation

### Problem

Current pipeline has no fail-closed checks between phases. Examples:
- Inventory with 0 concepts exits with code 0 (should be non-zero)
- Plan with overlapping units proceeds to rewrite (should block)
- Rewrite with deleted concepts exits 0 (should be non-zero)

This causes failures to cascade through multiple phases before detection.

### Solution

Add validation checkpoints in each command after its phase completes:

#### Inventory Command

**File:** `src/humanvoice/commands/inventory_command.py`

Replace unconditional `return 0` at line 366 with status-derived code:

```python
# After baseline is saved
if baseline.total_concepts == 0:
    print("Error: No concepts extracted (minimum 1 required)", file=sys.stderr)
    return 4  # Internal error
    
if not baseline_frozen:
    print("Warning: Baseline not frozen (use --freeze flag)", file=sys.stderr)
    return 3  # Invalid input
    
print(f"Baseline frozen: {baseline.baseline_id}")
print(f"Total concepts: {baseline.total_concepts}")
return 0
```

#### Plan Command

**File:** `src/humanvoice/commands/plan_v2_command.py`

Add validation after plan is created:

```python
# After save_rewrite_plan()
validation_errors = validate_plan(plan, snapshot_dir)

if validation_errors:
    print(f"Error: Plan validation failed with {len(validation_errors)} errors:", file=sys.stderr)
    for error in validation_errors[:5]:
        print(f"  - {error}", file=sys.stderr)
    return 4

print(f"Plan validated: {plan.plan_id}")
print(f"Total units: {plan.total_units}")
return 0
```

Add `validate_plan()` function:

```python
def validate_plan(plan: RewritePlan, snapshot_dir: Path) -> List[str]:
    """
    Validate plan meets all critical invariants.
    
    Returns list of validation errors (empty if valid).
    """
    errors = []
    
    # Load span offsets
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
    
    return errors
```

#### Rewrite Command

**File:** `src/humanvoice/commands/rewrite_command.py`

Already checks correspondence ratio, but exits after all units complete. Add early exit on first failure with `--strict` flag:

```python
# Add argument parser
parser.add_argument('--strict', action='store_true',
                   help='Exit immediately on first unit with deleted concepts')

# In rewrite loop (after line 195)
if args.strict and session.units_failed:
    print(f"Error: {len(session.units_failed)} unit(s) failed (--strict mode)", file=sys.stderr)
    for unit_id in session.units_failed[:5]:
        print(f"  - {unit_id}", file=sys.stderr)
    return 1
```

### Tests

**File:** `tests/test_phase_boundary_validation.py`

```python
def test_inventory_exits_nonzero_with_zero_concepts():
    """Inventory with 0 concepts should exit with code 4."""
    result = subprocess.run(['hv', 'inventory', '/path/to/empty', '--freeze'],
                          capture_output=True)
    assert result.returncode == 4

def test_plan_exits_nonzero_with_overlapping_units():
    """Plan with overlapping units should exit with code 4."""
    # Setup: create snapshot with intentionally overlapping concepts
    snapshot = create_snapshot_with_overlapping_concepts()
    result = subprocess.run(['hv', 'plan', str(snapshot)],
                          capture_output=True)
    assert result.returncode == 4
    assert b"Overlapping units" in result.stderr

def test_rewrite_exits_nonzero_with_deleted_concepts():
    """Rewrite with deleted concepts should exit with code 1."""
    # This test uses mock model that returns incomplete correspondences
    result = subprocess.run(['hv', 'rewrite', str(snapshot), '--mock'],
                          capture_output=True)
    assert result.returncode == 1
```

### Deliverable

- [ ] Inventory fail-closed on 0 concepts
- [ ] Plan fail-closed on validation errors
- [ ] Rewrite fail-closed on deleted concepts (existing)
- [ ] 6 integration tests for boundary validation
- [ ] Documentation: "Phase Boundary Contracts" in architecture doc

### Refresh Procedure

**CRITICAL:** Phase 3 adds validation logic but doesn't change data structures.

```bash
# Phase 3 has NO data refresh requirement
# Tests validation logic on existing or new data

# Test new validation on existing inventory
pytest tests/test_phase_boundary_validation.py::test_inventory_exits_nonzero_with_zero_concepts -v

# Test new validation on existing plan
pytest tests/test_phase_boundary_validation.py::test_plan_exits_nonzero_with_overlapping_units -v

# Test new validation on existing rewrite
pytest tests/test_phase_boundary_validation.py::test_rewrite_exits_nonzero_with_deleted_concepts -v
```

**Why refresh is NOT required:**
- Phase 3 adds fail-closed checks (validation logic), not data generation
- Tests validation behavior itself, not data output
- Can test on any inventory/plan/rewrite (existing or new)

### Exit Criteria

All boundary validation tests pass:

```bash
pytest tests/test_phase_boundary_validation.py -v
```

Expected:
- All 6 tests pass
- Validation functions correctly reject invalid states
- Commands exit with non-zero codes on failures

---

## Phase 4: Assembly Simplification

### Problem

Current assembly uses min/max byte range including gaps. This worked for v1 section-based assembly but breaks with v2 semantic units.

### Solution

**File:** `src/humanvoice/patch_assembly.py`

Simplify `_collect_patches()` (lines 123-125) to use exact span bytes only:

```python
def _collect_patches_from_unit(
    unit: RewriteUnit,
    rewrite_result: RewriteResult,
    span_offsets: dict,
    source_bytes: bytes
) -> List[SourcePatch]:
    """
    Collect patches for one unit.
    
    With contiguity enforcement, each unit maps to one contiguous patch.
    No gap handling needed.
    """
    span_ids = unit.source_span_ids
    
    # Get byte positions
    byte_positions = []
    for span_id in span_ids:
        if span_id not in span_offsets:
            raise ValueError(f"Span {span_id} not found in offsets")
        byte_positions.append((span_offsets[span_id]['byte_start'],
                              span_offsets[span_id]['byte_end']))
    
    # Sort by position
    byte_positions.sort()
    
    # Verify contiguity (should be guaranteed by planner)
    for i in range(len(byte_positions) - 1):
        gap = byte_positions[i+1][0] - byte_positions[i][1]
        if gap > 10 * 1024:  # 10KB threshold
            raise ValueError(
                f"Unit {unit.unit_id} has non-contiguous spans (gap: {gap} bytes). "
                "This should have been caught by planner validation."
            )
    
    # Create single patch for entire unit
    start_offset = byte_positions[0][0]
    end_offset = byte_positions[-1][1]
    original_text = source_bytes[start_offset:end_offset].decode('utf-8', errors='replace')
    
    patch = SourcePatch(
        unit_id=unit.unit_id,
        source_span_ids=span_ids,
        start_offset=start_offset,
        end_offset=end_offset,
        original_text=original_text,
        replacement_text=rewrite_result.output_latex,
        concept_ids=unit.concept_ids,
        verified=True
    )
    
    return [patch]
```

### Tests

**File:** `tests/test_patch_assembly_simplified.py`

```python
def test_collect_patches_contiguous_unit():
    """Contiguous unit should produce single patch."""
    unit = create_contiguous_unit()
    result = create_rewrite_result(unit)
    span_offsets = load_span_offsets()
    source_bytes = load_source_bytes()
    
    patches = _collect_patches_from_unit(unit, result, span_offsets, source_bytes)
    
    assert len(patches) == 1
    assert patches[0].unit_id == unit.unit_id

def test_collect_patches_rejects_noncontiguous():
    """Non-contiguous unit should raise ValueError."""
    unit = create_noncontiguous_unit(gap_kb=50)
    result = create_rewrite_result(unit)
    span_offsets = load_span_offsets()
    source_bytes = load_source_bytes()
    
    with pytest.raises(ValueError, match="non-contiguous spans"):
        _collect_patches_from_unit(unit, result, span_offsets, source_bytes)
```

### Deliverable

- [ ] `_collect_patches_from_unit()` simplified
- [ ] Contiguity assertion added
- [ ] 4 unit tests
- [ ] Integration test: ZLB assembly completes with 100% coverage

### Refresh Procedure

**CRITICAL:** Phase 4 changes assembly logic and requires Phase 2 contiguous units.

```bash
# Phase 4 requires Phase 2 plan with contiguous units
# Must have rewrite results to test assembly

# Option A: Use existing rewrite results (if Phase 2 plan was rewritten)
# Check if rewrite results exist for current plan
PLAN_ID=$(jq -r '.plan_id' sessions/zlb-v2-snapshot/.humanvoice/plans/plan-*.json)
if [ ! -d "sessions/zlb-v2-snapshot/.humanvoice/rewrites" ]; then
    echo "No rewrite results found. Must run rewrite first."
fi

# Option B: Run mock rewrite (free, for testing assembly logic only)
hv rewrite sessions/zlb-v2-snapshot \
    --baseline-id $BASELINE_ID \
    --plan-id $PLAN_ID \
    --mock

# Option C: Run live rewrite (expensive ~$10, for real validation)
hv rewrite sessions/zlb-v2-snapshot \
    --baseline-id $BASELINE_ID \
    --plan-id $PLAN_ID \
    --timeout 3600

# If rewrite has failures, run repair
hv repair sessions/zlb-v2-snapshot \
    --baseline-id $BASELINE_ID \
    --plan-id $PLAN_ID

# Step 3: Run preflight (validates rewrite results)
hv preflight-v2 sessions/zlb-v2-snapshot

# Step 4: Test new assembly logic
hv assemble-v2 sessions/zlb-v2-snapshot
```

**Why refresh is required:**
- Assembly logic assumes contiguous units from Phase 2
- Testing against old non-contiguous plan would fail with wrong error
- Requires rewrite results (can be mock for logic testing)

### Exit Criteria

Run ZLB assembly with simplified logic:

```bash
hv assemble-v2 sessions/zlb-v2-snapshot
```

Expected:
- Exit code 0
- All patches applied (0 failed)
- Assembly complete: true
- No "non-contiguous spans" errors (should be caught by planner)

---

## Phase 3.5: Missing Concept Investigation **NEW**

### Problem

ZLB plan shows `plan_complete: false` with 37 concepts missing:

```
Warning: 37 concepts were not included in any unit:
  concept-097, concept-098, concept-1014 through concept-1028,
  concept-1032 through concept-1035, concept-1039, concept-1041,
  concept-1099 through concept-1105, concept-1115, concept-1116,
  concept-183, concept-188, concept-189, concept-200, concept-201, concept-213
```

**Impact:** 3.3% of concepts (37/1137) are dropped from the plan. This violates the core product requirement: "preserve every concept and teach it adequately."

**Blocking:** Phase 5 golden test requires 100% concept correspondence. Missing concepts in the plan mean they cannot be rewritten or assembled.

### Root Cause Investigation

**Hypothesis 1:** Dependency graph excludes orphan concepts (no incoming/outgoing edges)

The planner builds a dependency graph and traverses it to create units. Concepts with no dependencies may be unreachable.

**File to check:** `src/humanvoice/semantic_unit_splitting.py` (dependency graph construction)

**Hypothesis 2:** Concepts filtered out during unit finalization

The `finalize_unit()` function may drop concepts when splitting clusters.

**File to check:** `src/humanvoice/semantic_unit_splitting.py` (line 223+, `finalize_unit()`)

**Hypothesis 3:** Concepts rejected during locality validation

Phase 1 may have rejected concepts with span range > 10KB, and they were never added to the baseline.

**File to check:** Inventory baseline concept count vs extraction output

### Investigation Procedure

```bash
# 1. Check which concepts are missing
hv plan sessions/zlb-v2-snapshot 2>&1 | grep "concept-" | head -20

# 2. Examine missing concepts in baseline
jq -r '.concept_entries[] | select(.concept_id | IN("concept-097", "concept-098", "concept-1014")) | {concept_id, source_span_ids, content}' \
  sessions/zlb-v2-snapshot/.humanvoice/inventory/baseline.json | head -50

# 3. Check dependency graph for missing concepts
python -c "
import json
from pathlib import Path

# Load baseline
baseline = json.loads(Path('sessions/zlb-v2-snapshot/.humanvoice/inventory/baseline.json').read_text())

# Load plan
plan_file = list(Path('sessions/zlb-v2-snapshot/.humanvoice/plans').glob('plan-*.json'))[0]
plan = json.loads(plan_file.read_text())

# Find which concepts are in plan
concepts_in_plan = set()
for unit in plan['units']:
    concepts_in_plan.update(unit['concept_ids'])

# Find missing concepts
all_concepts = {e['concept_id'] for e in baseline['concept_entries']}
missing_concepts = all_concepts - concepts_in_plan

print(f'Total concepts: {len(all_concepts)}')
print(f'Concepts in plan: {len(concepts_in_plan)}')
print(f'Missing concepts: {len(missing_concepts)}')
print(f'Missing: {sorted(missing_concepts)[:20]}')
"

# 4. Analyze missing concept characteristics
python -c "
import json
from pathlib import Path

baseline = json.loads(Path('sessions/zlb-v2-snapshot/.humanvoice/inventory/baseline.json').read_text())
plan_file = list(Path('sessions/zlb-v2-snapshot/.humanvoice/plans').glob('plan-*.json'))[0]
plan = json.loads(plan_file.read_text())

concepts_in_plan = set()
for unit in plan['units']:
    concepts_in_plan.update(unit['concept_ids'])

missing_concepts = []
for entry in baseline['concept_entries']:
    if entry['concept_id'] not in concepts_in_plan:
        missing_concepts.append(entry)

# Analyze characteristics
print(f'Missing concept analysis:')
print(f'  Total missing: {len(missing_concepts)}')

# Check if they have dependencies
missing_with_deps = [c for c in missing_concepts if c.get('dependencies', [])]
print(f'  Missing with dependencies: {len(missing_with_deps)}')

# Check span counts
span_counts = [len(c.get('source_span_ids', [])) for c in missing_concepts]
print(f'  Avg spans per missing concept: {sum(span_counts)/len(span_counts):.1f}')
print(f'  Min/Max spans: {min(span_counts)}/{max(span_counts)}')

# Sample missing concepts
print(f'\nSample missing concepts:')
for c in missing_concepts[:5]:
    print(f\"  {c['concept_id']}: {len(c.get('source_span_ids', []))} spans, {len(c.get('dependencies', []))} deps\")
    print(f\"    Content preview: {c.get('content', '')[:80]}\")
"
```

### Solution Options

**Option A: Include orphan concepts in plan**

Modify planner to include concepts with no dependencies as single-concept units.

**File:** `src/humanvoice/semantic_unit_splitting.py`

Add after dependency graph traversal:

```python
# After building units from dependency graph
planned_concepts = set()
for unit in units:
    planned_concepts.update(unit.concept_ids)

# Find orphan concepts
all_concepts = {e.concept_id for e in baseline.concept_entries}
orphan_concepts = all_concepts - planned_concepts

# Create units for orphan concepts
for concept_id in sorted(orphan_concepts):
    unit_id = f"unit-orphan-{concept_id}"
    units.append(RewriteUnit(
        unit_id=unit_id,
        concept_ids=[concept_id],
        source_span_ids=get_span_ids_for_concept(concept_id, baseline),
        dependencies=[]
    ))
```

**Option B: Strengthen dependency detection**

Improve dependency extraction so fewer concepts are orphans.

**File:** `src/humanvoice/model_extraction.py`

Adjust prompt to identify more dependencies, or use heuristics (e.g., concepts in adjacent spans likely depend on each other).

**Option C: Accept missing concepts as non-essential**

Document that concepts without dependencies (typically citations, footnotes, isolated definitions) can be excluded.

**Risk:** Violates product requirement "preserve every concept."

### Tests

**File:** `tests/test_missing_concepts.py`

```python
def test_plan_includes_all_concepts():
    """All concepts from baseline must appear in plan."""
    baseline = load_test_baseline()
    plan = create_plan(baseline)
    
    all_concepts = {e.concept_id for e in baseline.concept_entries}
    planned_concepts = {cid for unit in plan.units for cid in unit.concept_ids}
    
    missing = all_concepts - planned_concepts
    assert len(missing) == 0, f"Missing concepts: {missing}"

def test_orphan_concepts_become_units():
    """Concepts with no dependencies should become single-concept units."""
    baseline = create_baseline_with_orphan_concepts()
    plan = create_plan(baseline)
    
    # Check that orphan concepts are in plan
    orphan_concept_ids = ["concept-orphan-1", "concept-orphan-2"]
    planned_concepts = {cid for unit in plan.units for cid in unit.concept_ids}
    
    for concept_id in orphan_concept_ids:
        assert concept_id in planned_concepts
```

### Deliverable

- [ ] Investigation script run, root cause identified
- [ ] Solution implemented (Option A preferred)
- [ ] 2 tests added
- [ ] ZLB plan shows `plan_complete: true`
- [ ] All 1,137 concepts included in plan

### Exit Criteria

```bash
hv plan sessions/zlb-v2-snapshot
```

Expected output:
```
Plan created: plan-<id>
Total units: ~25-30 (includes orphan units)
Total concepts: 1137
Plan complete: true ✅
```

---

## Phase 4: Assembly Simplification

### Goal

Run complete pipeline on ZLB manuscript with all architectural fixes in place.

### Refresh Procedure

**CRITICAL:** Phase 5 validates the ENTIRE pipeline end-to-end with all fixes integrated. MUST start completely clean.

```bash
# Step 1: Clean start with NEW directory (not sessions/zlb-v2-snapshot)
rm -rf /tmp/zlb-rebuild

# Step 2: Copy source only (no old artifacts)
mkdir -p /tmp/zlb-rebuild-source
cp fixtures/real_documents/zlb_2026/manuscript.tex /tmp/zlb-rebuild-source/

# Step 3: Init fresh snapshot
hv init /tmp/zlb-rebuild-source/manuscript.tex \
    --brief fixtures/real_documents/zlb_2026/brief.json \
    --output /tmp/zlb-rebuild

# Step 4: Run Phase 2 - Inventory (with Phase 1 fixes: concept locality)
hv inventory /tmp/zlb-rebuild --freeze --adjudicator test-harness

# Capture baseline ID
BASELINE_ID=$(jq -r '.baseline_id' /tmp/zlb-rebuild/.humanvoice/inventory/baseline.json)
echo "Baseline (with locality enforcement): $BASELINE_ID"

# Step 5: Run Phase 3 - Plan (with Phase 2 fixes: contiguity enforcement)
hv plan /tmp/zlb-rebuild --baseline-id $BASELINE_ID

# Capture plan ID
PLAN_ID=$(jq -r '.plan_id' /tmp/zlb-rebuild/.humanvoice/plans/plan-*.json)
echo "Plan (with contiguity enforcement): $PLAN_ID"

# Step 6: Verify plan validation (Phase 3 fixes: boundary validation)
python -c "
from pathlib import Path
import json
import sys
sys.path.insert(0, 'src')
from humanvoice.commands.plan_v2_command import validate_plan

plan_file = list(Path('/tmp/zlb-rebuild/.humanvoice/plans').glob('plan-*.json'))[0]
plan = json.loads(plan_file.read_text())

errors = validate_plan(plan, Path('/tmp/zlb-rebuild'))
if errors:
    print(f'FAIL: {len(errors)} validation errors:')
    for e in errors[:10]:
        print(f'  - {e}')
    sys.exit(1)
else:
    print('PASS: Plan validation successful')
    print(f'  Units: {plan[\"total_units\"]}')
    print(f'  All units contiguous, no overlaps')
"

# Step 7: Run Phase 4 - Rewrite (with live model, ~$10 cost)
echo "Starting rewrite with live model (expected cost: ~\$10)..."
hv rewrite /tmp/zlb-rebuild \
    --baseline-id $BASELINE_ID \
    --plan-id $PLAN_ID \
    --timeout 3600

# Step 8: OPTIONAL - If rewrite has failures, run repair
if [ -f "/tmp/zlb-rebuild/.humanvoice/rewrites/session-*.json" ]; then
    FAILED_COUNT=$(jq '.units_failed | length' /tmp/zlb-rebuild/.humanvoice/rewrites/session-*.json)
    if [ "$FAILED_COUNT" -gt 0 ]; then
        echo "Rewrite had $FAILED_COUNT failures. Running repair..."
        hv repair /tmp/zlb-rebuild \
            --baseline-id $BASELINE_ID \
            --plan-id $PLAN_ID
    fi
fi

# Step 9: Run Phase 5 - Preflight
hv preflight-v2 /tmp/zlb-rebuild

# Step 10: Run Phase 6 - Assembly (with Phase 4 fixes: simplified assembly)
hv assemble-v2 /tmp/zlb-rebuild

# Step 11: Verify assembly result
python -c "
import json
result = json.loads(open('/tmp/zlb-rebuild/.humanvoice/assembled/assembly_result.json').read())
print(f'Assembly complete: {result[\"assembly_complete\"]}')
print(f'Patches applied: {result[\"patches_applied\"]}/{result[\"total_patches\"]}')
print(f'Patches failed: {result[\"patches_failed\"]}')

if not result['assembly_complete']:
    print('FAIL: Assembly incomplete')
    exit(1)
if result['patches_failed'] > 0:
    print('FAIL: Patches failed')
    exit(1)

print('PASS: ZLB assembly successful')
"

# Step 12: Run golden test
pytest tests/integration_real/test_zlb_golden.py::test_zlb_golden_path -v -s
```

**Why COMPLETE refresh is critical:**

Phase 5 validates that Phases 1-4 work TOGETHER:
- NEW concepts from Phase 1 (locality enforced)
- NEW plan from Phase 2 (contiguity enforced, built from Phase 1 baseline)
- NEW validation from Phase 3 (boundaries checked)
- NEW assembly from Phase 4 (simplified logic, processing Phase 2 contiguous units)

Using old data from `sessions/zlb-v2-snapshot` would test the OLD broken architecture, not the fixes. The session directory contains pre-fix artifacts that would invalidate the end-to-end test.

**Use /tmp/zlb-rebuild (clean directory), NOT sessions/zlb-v2-snapshot (has old artifacts).**

### Procedure

### Success Criteria

All phases complete with exit code 0:
- ✓ Inventory: ~1,100 concepts extracted (all with span range < 10KB)
- ✓ Plan: 50-60 units created (all contiguous, no overlaps)
- ✓ Rewrite: 100% correspondence, 0 deleted concepts (or <5% if model non-compliance)
- ✓ Preflight: All units verified
- ✓ Assembly: 100% patches applied, byte identity verified

Golden test passes all 6 phases.

### Deliverable

- [ ] ZLB pipeline completes end-to-end in /tmp/zlb-rebuild
- [ ] Assembly result JSON shows `assembly_complete: true`
- [ ] Golden test passes without errors
- [ ] Documentation: "ZLB Rebuild Success Report"

- [ ] ZLB pipeline completes end-to-end
- [ ] Assembly result JSON shows `assembly_complete: true`
- [ ] Golden test passes without errors
- [ ] Documentation: "ZLB Rebuild Success Report"

---

## Phase 6: Scale Testing

### Goal

Validate pipeline scales to 800-page target.

### Test Fixtures

Create scale fixtures (if not exist):

```bash
# Generate scale test fixtures
python tools/generate_scale_fixtures.py \
    --output fixtures/scale \
    --sizes 10,50,100,250,500,800 \
    --template fixtures/synthetic/large_report/source.tex
```

Each fixture:
- Realistic LaTeX structure (sections, equations, citations)
- Predictable concept count (proportional to pages)
- Protected objects (equations, citations, tables)

### Test Procedure

Run pipeline on each scale increment:

```bash
for pages in 10 50 100 250 500 800; do
    echo "Testing ${pages}-page fixture..."
    
    hv init fixtures/scale/pages_${pages}/source.tex \
        --brief fixtures/scale/pages_${pages}/brief.json \
        --output /tmp/scale_test_${pages}
    
    hv inventory /tmp/scale_test_${pages} --freeze --adjudicator test-harness
    
    BASELINE_ID=$(jq -r '.baseline_id' /tmp/scale_test_${pages}/.humanvoice/inventory/baseline.json)
    
    hv plan /tmp/scale_test_${pages} --baseline-id $BASELINE_ID
    
    # Validate plan
    python -c "
from pathlib import Path
import json
from humanvoice.commands.plan_v2_command import validate_plan

plan = json.loads(list(Path('/tmp/scale_test_${pages}/.humanvoice/plans').glob('plan-*.json'))[0].read_text())
errors = validate_plan(plan, Path('/tmp/scale_test_${pages}'))
assert len(errors) == 0, f'Plan validation failed: {errors[:5]}'
print(f'PASS: ${pages} pages, {plan[\"total_units\"]} units')
"
    
    # Stop here for scale tests (don't run expensive rewrite on all)
done
```

### Performance Benchmarks

Record metrics for each scale:

| Pages | Lines | Concepts | Units | Plan Time | Memory (GB) |
|-------|-------|----------|-------|-----------|-------------|
| 10 | 400 | ~50 | ~5 | <10s | <0.5 |
| 50 | 2,000 | ~250 | ~25 | <30s | <1 |
| 100 | 4,000 | ~500 | ~50 | <60s | <2 |
| 250 | 10,000 | ~1,250 | ~125 | <180s | <5 |
| 500 | 20,000 | ~2,500 | ~250 | <360s | <10 |
| 800 | 32,000 | ~4,000 | ~400 | <600s | <16 |

### Success Criteria

For all scale fixtures:
- ✓ Inventory completes without memory errors
- ✓ Plan validation passes (0 errors)
- ✓ All units contiguous
- ✓ No overlapping units
- ✓ Memory usage < 16GB for 800 pages

### Refresh Procedure

**CRITICAL:** Phase 6 tests scalability on larger documents. Each scale test must start clean.

```bash
# Step 1: Generate scale fixtures if they don't exist
if [ ! -d "fixtures/generated/pages_800" ]; then
    echo "Generating scale fixtures..."
    python tools/generate_scale_fixtures.py \
        --output fixtures/generated \
        --sizes 10,50,100,250,500,800 \
        --template fixtures/synthetic/large_report/source.tex
fi

# Step 2: Test each scale with clean rebuild
for pages in 10 50 100 250 500 800; do
    echo "Testing ${pages}-page fixture..."
    
    # Clean start for this scale
    rm -rf /tmp/scale_test_${pages}
    
    # Init
    hv init fixtures/generated/pages_${pages}/source.tex \
        --brief fixtures/generated/pages_${pages}/brief.json \
        --output /tmp/scale_test_${pages}
    
    # Inventory (with Phase 1 locality enforcement)
    hv inventory /tmp/scale_test_${pages} --freeze --adjudicator test-harness
    
    BASELINE_ID=$(jq -r '.baseline_id' /tmp/scale_test_${pages}/.humanvoice/inventory/baseline.json)
    CONCEPT_COUNT=$(jq '.total_concepts' /tmp/scale_test_${pages}/.humanvoice/inventory/baseline.json)
    echo "  Concepts: $CONCEPT_COUNT"
    
    # Plan (with Phase 2 contiguity enforcement)
    hv plan /tmp/scale_test_${pages} --baseline-id $BASELINE_ID
    
    UNIT_COUNT=$(jq '.total_units' /tmp/scale_test_${pages}/.humanvoice/plans/plan-*.json)
    echo "  Units: $UNIT_COUNT"
    
    # Validate plan (no rewrite needed for scale test)
    python -c "
from pathlib import Path
import json
import sys
sys.path.insert(0, 'src')
from humanvoice.commands.plan_v2_command import validate_plan

plan = json.loads(list(Path('/tmp/scale_test_${pages}/.humanvoice/plans').glob('plan-*.json'))[0].read_text())
errors = validate_plan(plan, Path('/tmp/scale_test_${pages}'))
if errors:
    print(f'FAIL: {len(errors)} validation errors')
    sys.exit(1)
else:
    print(f'PASS: ${pages} pages validated')
"
    
    # Record performance metrics
    echo "$pages,$CONCEPT_COUNT,$UNIT_COUNT" >> /tmp/scale_test_results.csv
done

# Display results
echo "Scale test results:"
cat /tmp/scale_test_results.csv
```

**Why refresh is required:**
- Each scale test must start from clean state for accurate memory/performance measurement
- Reusing artifacts would invalidate performance benchmarks
- Only runs inventory + plan (not expensive rewrite) for cost control

**Note:** Phase 6 does NOT run rewrite on all scales (too expensive, ~$200 for all). Only tests inventory + plan phases which prove scalability of the core architecture.

### Deliverable

- [ ] Scale fixtures generated (if needed)
- [ ] Performance benchmarks recorded in `/tmp/scale_test_results.csv`
- [ ] 800-page fixture passes inventory + plan phases
- [ ] Documentation: "Scale Test Results"

---

## Program Execution Plan

### Execution Mode

This program will be executed **sequentially, one phase at a time**, with **refresh procedures** at each phase boundary.

**Why sequential:**
- Each phase depends on previous phase success
- Early phases (concept locality, contiguity) fundamentally change data structures
- Attempting parallel work risks building on unstable foundations
- **Refresh steps ensure fixes are tested on NEW data, not old artifacts**

### Execution Schedule with Refresh Steps

```
Day 1-2: Phase 1 (Concept Locality)
  - Implement validation functions
  - Add to extraction workflow
  - Write tests
  - REFRESH: Delete old inventory, rebuild with new code
  - Run on ZLB inventory
  - CHECKPOINT: Verify no concepts with span range > 10KB

Day 3-4: Phase 2 (Planner Contiguity)
  - Implement span clustering
  - Modify finalize_unit()
  - Write tests
  - REFRESH: Delete old plans, rebuild from Phase 1 baseline
  - Run on ZLB plan
  - CHECKPOINT: Verify 0 overlapping units, all contiguous

Day 5: Phase 3 (Boundary Validation)
  - Add validation to inventory/plan/rewrite commands
  - Write tests
  - NO REFRESH NEEDED (validation logic only, no data changes)
  - Run validation tests
  - CHECKPOINT: All boundary tests pass

Day 6: Phase 4 (Assembly Simplification)
  - Simplify patch collection
  - Add contiguity assertion
  - Write tests
  - REFRESH: Need Phase 2 plan + rewrite results (use mock rewrite for testing)
  - CHECKPOINT: Unit tests pass

Day 7: Phase 5 (ZLB End-to-End)
  - REFRESH: COMPLETE CLEAN REBUILD in /tmp/zlb-rebuild
  - Run full pipeline: init → inventory → plan → rewrite → repair → preflight → assemble
  - Execute golden test
  - CHECKPOINT: Golden test passes all 6 phases

Day 8-9: Phase 6 (Scale Testing)
  - Generate scale fixtures (if needed)
  - REFRESH: Clean rebuild for EACH scale test (10, 50, 100, 250, 500, 800 pages)
  - Run scale tests (inventory + plan only, no rewrite)
  - Record performance metrics
  - CHECKPOINT: 800-page fixture passes inventory + plan

Day 10: Documentation & Commit
  - Update architecture docs
  - Write completion report
  - Commit all changes
```
  - Write tests
  - Run validation tests
  - CHECKPOINT: All boundary tests pass

Day 6: Phase 4 (Assembly Simplification)
  - Simplify patch collection
  - Add contiguity assertion
  - Write tests
  - CHECKPOINT: Unit tests pass

Day 7: Phase 5 (ZLB End-to-End)
  - Clean ZLB rebuild from scratch
  - Run full pipeline
  - Execute golden test
  - CHECKPOINT: Golden test passes all 6 phases

Day 8-9: Phase 6 (Scale Testing)
  - Generate scale fixtures (if needed)
  - Run scale tests
  - Record performance metrics
  - CHECKPOINT: 800-page fixture passes inventory + plan

Day 10: Documentation & Commit
  - Update architecture docs
  - Write completion report
  - Commit all changes
```

### Verification Gates with Refresh Requirements

Each phase has a **mandatory verification gate** with **explicit refresh requirements** before proceeding:

1. **Phase 1 gate:** No concepts with span range > 10KB in ZLB inventory
   - **Refresh:** Delete `sessions/zlb-v2-snapshot/.humanvoice/inventory/*`, rebuild with new code
   - **Verify:** Query baseline.json for max concept span range

2. **Phase 2 gate:** Zero overlapping units in ZLB plan
   - **Refresh:** Delete `sessions/zlb-v2-snapshot/.humanvoice/plans/*`, rebuild from Phase 1 baseline
   - **Verify:** Run `validate_plan()`, check for 0 overlaps

3. **Phase 3 gate:** All boundary validation tests pass
   - **Refresh:** None (validation logic only, not data generation)
   - **Verify:** `pytest tests/test_phase_boundary_validation.py -v`

4. **Phase 4 gate:** Assembly unit tests pass
   - **Refresh:** Need Phase 2 contiguous plan + rewrite results (mock or live)
   - **Verify:** `pytest tests/test_patch_assembly_simplified.py -v`

5. **Phase 5 gate:** Golden test passes all 6 phases
   - **Refresh:** COMPLETE rebuild in `/tmp/zlb-rebuild` (not sessions/zlb-v2-snapshot)
   - **Verify:** `pytest tests/integration_real/test_zlb_golden.py::test_zlb_golden_path -v`

6. **Phase 6 gate:** 800-page fixture completes inventory + plan
   - **Refresh:** Clean rebuild for each scale test in `/tmp/scale_test_<pages>/`
   - **Verify:** Check `/tmp/scale_test_results.csv` for 800-page row

**If any gate fails:** Stop, diagnose, fix, re-refresh, re-verify. Do not proceed to next phase.

**Critical rule:** Never test new code against old artifacts. Always refresh data after code changes.

### Risk Management

**Risk 1: Concept locality enforcement rejects too many concepts**
- **Mitigation:** Implement concept splitting instead of rejection
- **Fallback:** Adjust threshold from 10KB to 20KB

**Risk 2: Planner contiguity creates too many units (>200)**
- **Impact:** Rewrite phase takes longer (more model calls)
- **Mitigation:** Acceptable tradeoff for correctness
- **Fallback:** Optimize unit merging (combine small adjacent units)

**Risk 3: ZLB rewrite still has deleted concepts after fixes**
- **Root cause:** Model prompt non-compliance (not fixable)
- **Mitigation:** Already implemented retry mechanism in plan
- **Fallback:** Review rewrite prompt, add more explicit preservation instruction

**Risk 4: Scale fixtures don't exist or are malformed**
- **Mitigation:** Generate from template if missing
- **Fallback:** Use existing large_report (116 lines) as largest test

**Risk 5: Testing new code against old artifacts gives false results**
- **Impact:** Fixes appear to fail when old data still has defects
- **Mitigation:** Explicit refresh procedures at each phase boundary
- **Critical:** Always delete old artifacts before testing new code

**Risk 6: Phase 5 uses wrong directory (sessions/zlb-v2-snapshot instead of /tmp/zlb-rebuild)**
- **Impact:** End-to-end test validates old architecture, not fixes
- **Mitigation:** Use `/tmp/zlb-rebuild` (clean), never `sessions/zlb-v2-snapshot` (has old artifacts)
- **Verification:** Check path in all Phase 5 commands

---

## Success Metrics

### Primary Goal

**ZLB pipeline completes with 100% assembly coverage**

```json
{
  "assembly_complete": true,
  "patches_applied": 50,
  "patches_failed": 0,
  "units_assembled": 50,
  "units_excluded": 0,
  "coverage_percent": 100.0
}
```

### Secondary Goals

1. **Concept locality:** 100% of concepts have span range < 10KB
2. **Unit contiguity:** 100% of units have max gap < 10KB
3. **No overlaps:** 0 overlapping unit pairs in any plan
4. **Correspondence:** ≥95% correspondence ratio in rewrites (model limitation)
5. **Scale validation:** Pipeline completes on 800-page fixture

**Note on correspondence:** 100% correspondence is ideal but model prompt non-compliance may cause some concept deletion. Target ≥95% as acceptable threshold.

### Quality Gates

All tests pass:
- ✓ 577 existing unit tests (no regressions)
- ✓ 22 new unit tests (concept locality, contiguity, boundaries)
- ✓ 1 golden test (ZLB end-to-end)
- ✓ 6 scale tests (10, 50, 100, 250, 500, 800 pages)

Total test count: **606 tests**

---

## Deliverables

### Code Changes

1. `src/humanvoice/model_extraction.py` - Concept locality validation
2. `src/humanvoice/semantic_unit_splitting.py` - Contiguity enforcement
3. `src/humanvoice/commands/inventory_command.py` - Fail-closed validation
4. `src/humanvoice/commands/plan_v2_command.py` - Plan validation
5. `src/humanvoice/patch_assembly.py` - Simplified assembly

### Tests

6. `tests/test_concept_extraction_locality.py` - 5 tests
7. `tests/test_semantic_unit_splitting_contiguity.py` - 8 tests
8. `tests/test_phase_boundary_validation.py` - 6 tests
9. `tests/test_patch_assembly_simplified.py` - 4 tests
10. `tests/integration_real/test_zlb_golden.py` - Already complete

### Documentation

11. `docs/architectural-rebuild-phase1.md` - Phase 1 implementation notes
12. `docs/architectural-rebuild-phase2.md` - Phase 2 implementation notes
13. `docs/zlb-rebuild-success-report.md` - Final validation results
14. `docs/scale-test-results.md` - Performance benchmarks

### Artifacts

15. `/tmp/zlb-rebuild/` - Clean ZLB rebuild with new architecture (Phase 5)
16. `/tmp/scale_test_<pages>/` - Scale test snapshots (Phase 6)
17. `/tmp/scale_test_results.csv` - Performance benchmarks
18. `fixtures/generated/pages_<size>/` - Scale test fixtures (if generated)

**Important:** Artifacts use `/tmp/` directories for clean rebuilds, not `sessions/zlb-v2-snapshot` (has old artifacts).

---

## Refresh Procedures Summary

**Critical principle:** Never test new code against old artifacts.

| Phase | Refresh Required? | What to Delete | What to Rebuild |
|-------|-------------------|----------------|-----------------|
| Phase 1 | YES | `sessions/zlb-v2-snapshot/.humanvoice/inventory/*` | Run `hv inventory` with new extraction code |
| Phase 2 | YES | `sessions/zlb-v2-snapshot/.humanvoice/plans/*` | Run `hv plan` with Phase 1 baseline |
| Phase 3 | NO | Nothing | Tests validation logic on any data |
| Phase 4 | YES | Need Phase 2 plan + rewrite results | Run mock rewrite for assembly testing |
| Phase 5 | YES (CRITICAL) | Everything - use `/tmp/zlb-rebuild` | Full pipeline from init through assemble |
| Phase 6 | YES | Each scale test directory | Clean rebuild for each page count |

**Anti-patterns to avoid:**
- ❌ Running Phase 2 plan on old Phase 1 inventory (has 140KB concept spans)
- ❌ Running Phase 4 assembly on old non-contiguous plans
- ❌ Running Phase 5 golden test in `sessions/zlb-v2-snapshot` (has old artifacts)
- ❌ Reusing Phase 6 scale test directories across runs (invalidates performance benchmarks)

**Correct patterns:**
- ✓ Delete artifacts after code changes
- ✓ Rebuild from scratch for integration tests (Phase 5)
- ✓ Use clean `/tmp/` directories for validation
- ✓ Verify path in commands matches expected directory

---

## Conclusion

This program addresses the user's concern: "How can we have an even better more thorough rebuild so that we can handle monograph of 500 to 800 pages?"

**The answer:**

1. **Fix the concept model:** Enforce locality (spans within 10KB)
2. **Fix the planning model:** Enforce contiguity (units with max 10KB gaps)
3. **Fix the boundaries:** Fail-closed validation at every phase
4. **Fix assembly:** Simplify to 1:1 unit-to-patch mapping
5. **Add refresh procedures:** Ensure fixes are tested on new data, not old artifacts
6. **Validate at scale:** Test on real ZLB + synthetic 10-800 page fixtures

This is not a patch. This is an architectural rebuild that:
- Aligns the planning model with the assembly model
- Fixes the root causes exposed by ZLB
- Adds explicit refresh procedures to prevent false test results
- Validates scaling to 800 pages

**Duration:** 9-12 days  
**Risk:** Medium (concept locality may need tuning, refresh procedures add discipline overhead)  
**Confidence:** High (golden test will prove it works, refresh procedures ensure valid testing)

**Key addition from refresh requirements:**
- Explicit refresh steps at each phase boundary
- Anti-patterns documented to prevent testing mistakes
- Directory conventions (`/tmp/` for clean rebuilds)
- Verification that new code is tested on new data

Ready to execute Phase 1?
