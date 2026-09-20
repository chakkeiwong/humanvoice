# Master Program: ZLB 140KB Bug Fix - Progress Report

**Date**: 2026-09-21
**Status**: Phase 5 in progress

## Problem Summary
ZLB document units had 140KB span ranges, breaking assembly with "original_text mismatch" errors. Root cause: concepts spanning entire document instead of being locally contiguous.

## Implementation Status

### ✅ Phase 1: Concept Locality Enforcement (COMPLETE)
**Commit**: bbf9bfe

**Implementation**:
- Added `validate_concept_locality()` in `model_extraction.py`
- Enforces max 10KB span range for all concepts
- Filters invalid concepts during baseline freeze
- Added `concept_locality.py` helper module

**Tests**: 9 unit tests, all passing
- Contiguous spans accepted
- Large gaps rejected
- Edge cases (empty spans, single span, threshold) covered

**Result**: Concepts are now LOCAL, not document-wide.

---

### ✅ Phase 2: Planner Contiguity Enforcement (COMPLETE)
**Commit**: 69fbc3b

**Implementation**:
- `build_span_clusters()` groups spans by proximity (max 10KB gap)
- `finalize_unit()` splits units when gaps exceed threshold
- Concepts distributed to clusters based on span membership

**Tests**: 8 unit tests, all passing
- Single contiguous cluster accepted
- Large gaps trigger splits
- Concepts correctly distributed across clusters

**Result**: All units are CONTIGUOUS or split into contiguous clusters.

---

### ✅ Phase 3: Phase Boundary Validation (COMPLETE)
**Commit**: e754af9

**Implementation**:
- `validate_plan()` checks contiguity, overlaps, missing spans, passenger concepts
- `check_unit_contiguity()` validates max 10KB gap within units
- `find_overlapping_units()` detects byte range conflicts
- `get_unit_byte_range()` computes unit extent

**Tests**: 14 unit tests, all passing
- Valid plans accepted
- Non-contiguous units detected
- Overlapping units detected
- Missing spans.jsonl handled

**Result**: Fail-closed validation at phase boundaries.

---

### ✅ Phase 4: Assembly Simplification (COMPLETE)
**Commit**: 59c92a9

**Implementation**:
- Added contiguity validation in `_collect_patches()`
- Verifies max 10KB gap between spans before creating patches
- Exits with code 4 if non-contiguous unit detected

**Tests**: 3 unit tests, all passing
- Non-contiguous units rejected
- Contiguous units accepted
- Single-span units accepted

**Result**: Assembly enforces 1:1 unit-to-patch with contiguity check.

---

### 🔄 Phase 5: ZLB End-to-End Validation (IN PROGRESS)
**Status**: Running inventory extraction on clean ZLB snapshot

**Plan**:
1. ✅ Initialize clean ZLB snapshot from fixtures
2. 🔄 Run `hv inventory --freeze` with locality enforcement
3. ⏳ Verify concepts pass locality validation
4. ⏳ Check concept span ranges (should be < 10KB)
5. ⏳ Run `hv plan-v2` to generate units
6. ⏳ Verify units are contiguous
7. ⏳ Document results

**Expected Outcome**: All concepts < 10KB span range, all units contiguous.

---

## Test Summary

| Phase | Tests | Status |
|-------|-------|--------|
| Phase 1 | 9 | ✅ All passing |
| Phase 2 | 8 | ✅ All passing |
| Phase 3 | 14 | ✅ All passing |
| Phase 4 | 3 | ✅ All passing |
| Phase 5 | TBD | 🔄 In progress |
| **Total** | **34** | **34 passing** |

---

## Architecture Changes

### Before Fix
```
Concepts → [document-wide, 140KB spans]
    ↓
Units → [inherit large gaps, non-contiguous]
    ↓
Assembly → [tries to patch 140KB ranges, FAILS]
```

### After Fix
```
Concepts → [local only, max 10KB] ← Phase 1 filter
    ↓
Units → [contiguous clusters, max 10KB gaps] ← Phase 2 split
    ↓
Validation → [verify contiguity at boundaries] ← Phase 3 check
    ↓
Assembly → [1:1 unit-to-patch, verified contiguous] ← Phase 4 enforce
```

---

## Key Invariants Established

1. **Concept Locality**: All concepts have max 10KB span range
2. **Unit Contiguity**: All units have max 10KB gap between spans
3. **Phase Boundaries**: Validation catches defects early (at plan time)
4. **Assembly Safety**: Non-contiguous units rejected with clear error

---

## Next Steps

1. **Complete Phase 5**: Wait for ZLB inventory to finish, validate results
2. **Document findings**: Record concept count, max span ranges, unit distribution
3. **Run full pipeline**: If inventory succeeds, run plan → rewrite → assemble
4. **Final commit**: Merge all phases with comprehensive test coverage
