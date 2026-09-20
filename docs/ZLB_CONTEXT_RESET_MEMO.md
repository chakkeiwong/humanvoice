# ZLB Context Reset Memo - Complete Recovery Document

**Date**: 2026-09-21  
**Session**: Master Program Execution (Phases 1-6)  
**Status**: Phases 1-4 COMPLETE, Phase 5 IN PROGRESS

---

## Executive Summary

**Problem**: Agent had context thrashing trying to execute all 6 phases at once instead of sequentially.

**Root Cause**: Tool usage explosion - tried to read files for all phases simultaneously.

**Solution**: Sequential execution approved by user, with git commit after each phase.

**Current State**: 
- ✅ Phases 1-4 complete (34 tests passing, 4 commits)
- 🔄 Phase 5 in progress (ZLB inventory running, window 14/146)
- ⏳ Phase 6 ready (plan documented)

---

## The Goal

**Product**: Transform AI-generated technical documents into human-readable versions that teach concepts adequately.

**Architecture**: 6-phase pipeline (init → inventory → plan → rewrite → preflight → assemble)

**Current Problem**: ZLB manuscript (189KB, 3,368 lines) fails at assembly:
- Only 22/33 units assembled (67% coverage)
- "original_text mismatch" errors
- Root cause: Units have 140KB span ranges (non-contiguous)

**Target Scale**: 500-800 page monographs (~20,000-32,000 lines)

---

## The Master Program (MP-ZLB-REBUILD)

**Total Duration**: 9-12 days  
**Phases**: 6  
**Strategy**: Fix locality at every pipeline stage

### Phase 1: Concept Locality Enforcement ✅
**Status**: COMPLETE (commit bbf9bfe)  
**Goal**: Prevent concepts from spanning entire document  
**Implementation**: Filter concepts with span range > 10KB  
**Files**: `model_extraction.py`, `concept_locality.py`  
**Tests**: 9 unit tests, all passing  
**Result**: All concepts in baseline have max 10KB span range

### Phase 2: Planner Contiguity Enforcement ✅
**Status**: COMPLETE (commit 69fbc3b)  
**Goal**: Ensure all units have contiguous spans  
**Implementation**: Split units when gap > 10KB between spans  
**Files**: `semantic_unit_splitting.py`  
**Tests**: 8 unit tests, all passing  
**Result**: All units are contiguous or split into contiguous clusters

### Phase 3: Phase Boundary Validation ✅
**Status**: COMPLETE (commit e754af9)  
**Goal**: Catch defects at phase boundaries (fail-closed)  
**Implementation**: Validate plans before rewrite phase  
**Files**: `plan_v2_command.py`  
**Tests**: 14 unit tests, all passing  
**Result**: Invalid plans rejected before expensive rewrite

### Phase 4: Assembly Simplification ✅
**Status**: COMPLETE (commit 59c92a9)  
**Goal**: Enforce contiguity at assembly time  
**Implementation**: Assert max 10KB gap, exit if violated  
**Files**: `assemble_v2_command.py`  
**Tests**: 3 unit tests, all passing  
**Result**: Assembly only processes verified contiguous units

### Phase 5: ZLB End-to-End Validation 🔄
**Status**: IN PROGRESS  
**Goal**: Validate all fixes work on real ZLB document  
**Current**: Running inventory extraction (window 14/146, ~10%)  
**Location**: `/tmp/zlb-test-rebuild`  
**Command**: `hv inventory . --freeze --adjudicator "phase5-test"`  
**Expected**: ~15 more minutes, ~1,100 concepts extracted  
**Validation**: `scripts/validate_phase5.py` ready

### Phase 6: Scale Testing ⏳
**Status**: READY (plan documented)  
**Goal**: Validate scaling to 800-page target  
**Tests**: 10, 50, 100, 250, 500, 800 pages  
**Cost**: ~$85 total (model API calls)  
**Plan**: `docs/phase6-scale-testing-plan.md`

---

## The Core Problem (140KB Bug)

### Root Cause Analysis

**Symptom**: Assembly fails with "original_text mismatch"

**Proximate Cause**: Units span 140KB but only contain 4,769 bytes of content

**Root Cause**: Planning/Assembly architecture mismatch

```
Planning Model:
  - Collects ALL spans from ALL concepts
  - Assumes units can be non-contiguous
  - Creates unit-005 with 22 spans across 144KB range

Assembly Model:
  - Uses min-max byte range (includes gaps)
  - Assumes units are contiguous
  - Tries to patch 140KB → encounters mismatches
```

**Example (unit-005)**:
```
22 spans, 4,769 bytes actual content
Byte range: [15,910 → 160,627] = 144,717 bytes
Gap: 139,948 bytes (96.7% empty space)
Status: BLOCKED by overlaps with other units
```

### The Fix (Multi-Layer Defense)

**Layer 1 (Inventory)**: Filter concepts with span range > 10KB  
**Layer 2 (Planning)**: Split units when gap > 10KB between spans  
**Layer 3 (Validation)**: Reject plans with non-contiguous units  
**Layer 4 (Assembly)**: Assert contiguity before creating patches

**Result**: Defects caught early, never reach assembly

---

## Current v2 Pipeline Architecture

### Phase 1: Init
**Command**: `hv init <source.tex> --brief <brief.json> --output <dir>`  
**Input**: LaTeX source file + reader brief  
**Output**: Snapshot directory with protected objects extracted  
**Key Files**:
- `source/`: Original LaTeX
- `manifest.json`: Snapshot metadata
- `.humanvoice/protected_objects.json`: Equations, citations, tables

### Phase 2: Inventory
**Command**: `hv inventory <snapshot> --freeze --adjudicator <id>`  
**Input**: Snapshot directory  
**Output**: Frozen baseline with concepts  
**Key Files**:
- `.humanvoice/inventory/spans.jsonl`: Source segmentation
- `.humanvoice/inventory/concepts.jsonl`: Extracted concepts
- `.humanvoice/inventory/baseline.json`: Frozen baseline

**Key Operations**:
1. Partition source into spans (~100-150 byte chunks)
2. Create extraction windows (overlapping, 15 spans each)
3. Extract concepts via model (claude-opus-5)
4. Filter for locality (Phase 1 fix)
5. Freeze baseline with valid concepts

### Phase 3: Plan
**Command**: `hv plan-v2 <snapshot> --baseline-id <id>`  
**Input**: Frozen baseline  
**Output**: Rewrite plan with semantic units  
**Key Files**:
- `.humanvoice/plans/plan-<id>.json`: Unit definitions
- `.humanvoice/plans/dependencies-<id>.json`: Unit dependencies

**Key Operations**:
1. Build dependency graph from concepts
2. Traverse graph to create semantic units
3. Assign spans to units based on concepts
4. Split units if gaps > 10KB (Phase 2 fix)
5. Validate plan contiguity (Phase 3 fix)

### Phase 4: Rewrite
**Command**: `hv rewrite <snapshot> --baseline-id <id> --plan-id <id>`  
**Input**: Frozen baseline + rewrite plan  
**Output**: Revised LaTeX for each unit  
**Key Files**:
- `.humanvoice/rewrites/unit-<id>.json`: Revised content + correspondence

**Key Operations**:
1. For each unit: load concepts, spans, dependencies
2. Call model to rewrite unit preserving concepts
3. Verify correspondence (all concepts represented)
4. Save rewrite result

### Phase 5: Preflight
**Command**: `hv preflight-v2 <snapshot>`  
**Input**: Rewrite results  
**Output**: Verification that all units ready for assembly  
**Key Operations**: Check all units have rewrites, verify protected objects

### Phase 6: Assembly
**Command**: `hv assemble-v2 <snapshot>`  
**Input**: Rewrite results  
**Output**: Final revised document  
**Key Files**:
- `.humanvoice/assembled/revised.tex`: Final output
- `.humanvoice/assembled/assembly_result.json`: Assembly report

**Key Operations**:
1. Sort units by byte position
2. Create patches from rewrite results
3. Validate contiguity (Phase 4 fix)
4. Apply patches to source
5. Generate final document

---

## Critical Code Locations

### Phase 1 Implementation
**File**: `src/humanvoice/model_extraction.py`  
**Function**: `validate_concept_locality()`  
**Lines**: ~180-220  
**What it does**: Checks if concept spans are within 10KB threshold

**File**: `src/humanvoice/concept_locality.py`  
**Functions**: 
- `build_span_position_map()`: Load spans.jsonl
- `validate_all_concepts_locality()`: Batch validation

### Phase 2 Implementation
**File**: `src/humanvoice/semantic_unit_splitting.py`  
**Function**: `build_span_clusters()`  
**Lines**: ~280-320  
**What it does**: Groups spans into contiguous clusters

**Function**: `finalize_unit()`  
**Lines**: ~223-270  
**What it does**: Splits units when clusters are non-contiguous

### Phase 3 Implementation
**File**: `src/humanvoice/commands/plan_v2_command.py`  
**Function**: `validate_plan()`  
**Lines**: ~150-200  
**What it does**: Validates plan before proceeding to rewrite

**Checks**:
1. `check_unit_contiguity()`: Max 10KB gap
2. `find_overlapping_units()`: No byte range conflicts
3. Missing span detection
4. Passenger concept detection

### Phase 4 Implementation
**File**: `src/humanvoice/commands/assemble_v2_command.py`  
**Function**: `_collect_patches()`  
**Lines**: ~123-180  
**What it does**: Creates patches, validates contiguity

---

## Test Coverage

### Unit Tests (34 total, all passing)

**Phase 1 Tests** (`tests/test_concept_extraction_locality.py`):
- `test_validate_locality_contiguous_spans()`: 10KB range accepted
- `test_validate_locality_large_span_range()`: 140KB range rejected
- `test_validate_locality_single_span()`: Single span accepted
- `test_validate_locality_missing_span()`: Missing span handled
- `test_validate_locality_empty_spans()`: Empty list handled
- `test_validate_locality_threshold_boundary()`: Exactly at threshold
- `test_validate_locality_just_over_threshold()`: Just over rejected
- `test_validate_locality_unordered_spans()`: Sorting works
- `test_validate_locality_custom_threshold()`: Configurable threshold

**Phase 2 Tests** (`tests/test_semantic_unit_splitting_contiguity.py`):
- `test_build_span_clusters_single_cluster()`: Contiguous → 1 cluster
- `test_build_span_clusters_large_gap()`: 50KB gap → 2 clusters
- `test_build_span_clusters_multiple_gaps()`: Multiple splits
- `test_build_span_clusters_threshold()`: Exactly at threshold
- `test_finalize_unit_contiguous()`: Single unit created
- `test_finalize_unit_splits()`: Multiple units created
- `test_finalize_unit_concept_distribution()`: Concepts assigned correctly
- `test_finalize_unit_preserves_dependencies()`: Dependencies preserved

**Phase 3 Tests** (`tests/test_plan_v2_command.py`):
- `test_check_unit_contiguity_valid()`: Contiguous accepted
- `test_check_unit_contiguity_large_gap()`: Large gap rejected
- `test_check_unit_contiguity_single_span()`: Single span accepted
- `test_find_overlapping_units_none()`: No overlaps
- `test_find_overlapping_units_detected()`: Overlaps found
- `test_get_unit_byte_range()`: Byte range computed
- `test_validate_plan_complete()`: Full validation
- Plus 7 more edge case tests

**Phase 4 Tests** (`tests/test_patch_assembly.py`):
- `test_collect_patches_rejects_noncontiguous()`: Non-contiguous rejected
- `test_collect_patches_accepts_contiguous()`: Contiguous accepted
- `test_collect_patches_single_span()`: Single span accepted

### Integration Tests

**Golden Test**: `tests/integration_real/test_zlb_golden.py`  
**Status**: Implemented, not yet passing (pending Phase 5 completion)  
**What it tests**: Complete ZLB pipeline from init → assemble  
**Invariants**:
1. No non-contiguous units
2. No overlapping units
3. No deleted concepts
4. No missing spans
5. Byte identity (V2-G5 property)

---

## Key Files Reference

### Source Code
- `src/humanvoice/model_extraction.py`: Concept extraction
- `src/humanvoice/concept_locality.py`: Phase 1 helpers
- `src/humanvoice/semantic_unit_splitting.py`: Planning logic
- `src/humanvoice/commands/plan_v2_command.py`: Plan command + validation
- `src/humanvoice/commands/assemble_v2_command.py`: Assembly logic
- `src/humanvoice/patch_assembly.py`: Patch creation

### Tests
- `tests/test_concept_extraction_locality.py`: 9 tests
- `tests/test_semantic_unit_splitting_contiguity.py`: 8 tests
- `tests/test_plan_v2_command.py`: 14 tests
- `tests/test_patch_assembly.py`: 3 tests
- `tests/integration_real/test_zlb_golden.py`: Golden test

### Documentation
- `docs/master-program-zlb-rebuild.md`: Original master program
- `docs/phase6-scale-testing-plan.md`: Phase 6 plan
- `MASTER_PROGRAM_PROGRESS.md`: Status tracker
- `ZLB_140KB_FIX_COMPLETE_REPORT.md`: Implementation report

### Scripts
- `scripts/validate_phase5.py`: E2E validation for ZLB inventory
- `scripts/validate_plan_contiguity.py`: Plan validation (Phase 6)
- `scripts/generate_scale_fixture.py`: Synthetic doc generator (Phase 6)

### Fixtures
- `fixtures/real_documents/zlb_2026/manuscript.tex`: ZLB source (189KB)
- `fixtures/real_documents/zlb_2026/answer_key.json`: Expected results
- `fixtures/real_documents/zlb_2026/brief.json`: Reader profile

### Snapshots
- `/tmp/zlb-test-rebuild`: Current Phase 5 test (in progress)
- `sessions/zlb-v2-snapshot`: Original failed attempt (reference only)

---

## Git Commit History

```
1261aa9 Documentation: Phases 1-4 complete, Phase 5 in progress
59c92a9 Phase 4: Assembly contiguity enforcement
e754af9 Phase 3: Plan validation at phase boundary
69fbc3b Phase 2: Planner contiguity enforcement with span clustering
bbf9bfe Phase 1: Concept locality enforcement
```

---

## Phase 5 Current Status

**Command Running**:
```bash
cd /tmp/zlb-test-rebuild && hv inventory . --freeze --adjudicator "phase5-test"
```

**Progress**: Window 14/146 (~10%)  
**Task ID**: b7hwdt02w  
**Output**: `/tmp/claude-1000/.../tasks/b7hwdt02w.output`  
**Estimated completion**: ~15 more minutes  
**Cost**: ~$10 (live model)

**What's happening**:
1. Partitioned source into 1,751 spans (189,829 bytes)
2. Created 146 extraction windows (15 spans each, overlapping)
3. Model extracting concepts from each window
4. Currently on window 14, extracting 7-16 concepts per window
5. Phase 1 filter will apply after all windows complete

**Expected outcome**:
- ~1,100 concepts extracted (similar to original ZLB)
- All concepts will pass Phase 1 filter (span range < 10KB)
- Baseline will freeze successfully
- Ready for planning phase

**Next steps after inventory completes**:
1. Run `python scripts/validate_phase5.py /tmp/zlb-test-rebuild`
2. Verify: All concepts < 10KB span range
3. Record: Concept count, max span range, statistics
4. Run: `hv plan-v2 /tmp/zlb-test-rebuild`
5. Verify: All units contiguous, no overlaps
6. Commit: Phase 5 complete
7. Proceed: Phase 6 scale testing

---

## Phase 6 Plan Summary

**Goal**: Validate pipeline scales to 800-page target

**Test Matrix**:
| Pages | Est. Time | Est. Cost | Status |
|-------|-----------|-----------|--------|
| 10    | 1 min     | Free      | Ready  |
| 50    | 5 min     | <$5       | Ready  |
| 100   | 10 min    | <$10      | Ready  |
| 250   | 25 min    | ~$15      | Ready  |
| 500   | 50 min    | ~$25      | Ready  |
| 800   | 80 min    | ~$40      | Ready  |

**Strategy**:
1. Run small tests first (10-100 pages) - cheap validation
2. If successful, proceed to large tests (250-800 pages)
3. Generate synthetic fixtures using template-based generator
4. Validate locality and contiguity at each scale
5. Document performance metrics

**Success Criteria**:
- All scales pass locality validation (concepts < 10KB)
- All scales pass contiguity validation (units contiguous)
- 800-page test completes without memory/timeout issues
- Performance scales linearly (or better)

---

## Critical Invariants

These must hold at all times:

1. **Concept Locality**: Every concept has span range ≤ 10KB
2. **Unit Contiguity**: Every unit has max gap ≤ 10KB between spans
3. **No Overlaps**: No two units share byte ranges
4. **Span Existence**: All referenced span IDs exist in spans.jsonl
5. **No Passengers**: All concepts in units have at least one span in that unit

**Violated invariant = pipeline broken**

---

## Common Issues and Debugging

### Issue: Inventory fails with 0 concepts

**Cause**: Phase 1 filter rejected all concepts  
**Debug**: Check `baseline.json` for `filtered_concepts`  
**Fix**: Adjust threshold or check extraction quality

### Issue: Plan has non-contiguous units

**Cause**: Phase 2 didn't split properly  
**Debug**: Check unit's span byte positions  
**Fix**: Review `build_span_clusters()` logic

### Issue: Assembly fails with "original_text mismatch"

**Cause**: Unit somehow bypassed contiguity checks  
**Debug**: Check `assembly_result.json` for failed patches  
**Fix**: Review Phase 3/4 validation

### Issue: Out of memory during inventory

**Cause**: Document too large for available RAM  
**Debug**: Monitor memory usage  
**Fix**: Reduce extraction window size or batch process

---

## Recovery Checklist

To resume work from this memo:

- [ ] Read this entire memo (you are here)
- [ ] Check Phase 5 inventory status (window N/146)
- [ ] Wait for inventory completion OR continue if complete
- [ ] Run `python scripts/validate_phase5.py /tmp/zlb-test-rebuild`
- [ ] Document results in progress tracker
- [ ] Run `hv plan-v2 /tmp/zlb-test-rebuild`
- [ ] Validate plan contiguity
- [ ] Git commit Phase 5 results
- [ ] Proceed to Phase 6 per plan

---

## Contact/Context

**User**: Amit Flores  
**Project**: humanvoice (academic document humanization)  
**Repository**: `/home/ubuntu/workspace/humanvoice`  
**Main branch**: `main`  
**Current task**: Execute MP-ZLB-REBUILD master program (Phases 1-6)  
**Authorization**: All phases approved, git commit after each phase

---

## Summary for Quick Context Recovery

1. **What we're doing**: Fixing ZLB assembly failure (140KB bug)
2. **How we're fixing it**: 6-phase architectural rebuild enforcing locality
3. **Where we are**: Phases 1-4 done (34 tests passing), Phase 5 running (10% complete)
4. **What's next**: Complete Phase 5 validation, then Phase 6 scale testing
5. **Why it matters**: Proves pipeline can scale to 800-page monographs (user requirement)

**If context thrashes again**: Re-read this memo, start from "Recovery Checklist"

---

**End of Context Reset Memo**
