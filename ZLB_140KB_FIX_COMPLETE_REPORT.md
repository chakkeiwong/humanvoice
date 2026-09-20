# ZLB 140KB Bug Fix - Complete Implementation Report

**Date**: 2026-09-21  
**Author**: Claude Opus 5  
**Status**: Phases 1-4 Complete, Phase 5 In Progress

---

## Executive Summary

Fixed critical bug where ZLB document units had 140KB span ranges, causing assembly failures with "original_text mismatch" errors. Root cause was concepts spanning entire document instead of being locally contiguous.

**Solution**: Five-phase architectural fix enforcing locality at every pipeline stage.

**Result**: 34 unit tests passing, 4 phases fully validated, end-to-end ZLB test in progress.

---

## Architecture: Before vs After

### Before (Broken)
```
Inventory → concepts span entire document (140KB ranges)
    ↓
Planning → units inherit large gaps, non-contiguous spans
    ↓
Rewriting → model writes replacement for 140KB range
    ↓
Assembly → tries to patch 140KB, encounters mismatches → FAILS
```

### After (Fixed)
```
Inventory → concepts filtered for locality (max 10KB) ← Phase 1
    ↓
Planning → units split into contiguous clusters (max 10KB gaps) ← Phase 2
    ↓
Validation → verify contiguity at plan boundary ← Phase 3
    ↓
Assembly → enforce contiguity, 1:1 unit-to-patch ← Phase 4
    ↓
E2E Test → validate on real ZLB document ← Phase 5
```

---

## Phase-by-Phase Implementation

### Phase 1: Concept Locality Enforcement ✅

**Commit**: bbf9bfe  
**Files Changed**: 4 files, +487 lines  
**Tests**: 9 unit tests, all passing

**Changes**:
- Added `validate_concept_locality()` in `model_extraction.py`
  - Enforces max 10KB span range for all concepts
  - Checks all spans referenced by concept are within threshold
  - Returns (is_valid, reason) tuple
  
- Created `concept_locality.py` helper module
  - `build_span_position_map()`: Load span offsets from spans.jsonl
  - `validate_all_concepts_locality()`: Batch validation with filtering

- Modified `inventory_command.py` baseline freeze
  - Filters concepts that violate locality constraint
  - Reports filtered concepts by reason (no spans, invalid spans, non-local)
  - Exits with error if no valid concepts remain

**Test Coverage**:
- Contiguous spans accepted ✅
- Large span ranges rejected ✅
- Single span accepted (trivially local) ✅
- Missing spans rejected ✅
- Empty span list rejected ✅
- Threshold boundary cases (exactly at, just over) ✅
- Unordered spans handled correctly ✅
- Configurable threshold ✅

**Invariant Established**: All concepts in frozen baseline have max 10KB span range.

---

### Phase 2: Planner Contiguity Enforcement ✅

**Commit**: 69fbc3b  
**Files Changed**: 2 files, +534 lines (tests), -38 lines (refactor)  
**Tests**: 8 unit tests, all passing

**Changes**:
- `build_span_clusters()` in `semantic_unit_splitting.py`
  - Groups spans into contiguous clusters based on byte proximity
  - Configurable max_gap_kb threshold (default 10KB)
  - Returns list of clusters, each cluster is a list of span IDs
  
- `finalize_unit()` enhancement
  - Splits units when clusters are non-contiguous
  - Creates sub-units for each cluster
  - Distributes concepts to clusters based on span membership
  - Preserves dependencies and teaching sequence

**Algorithm**:
```python
1. Load span byte positions from spans.jsonl
2. Sort spans by byte position
3. Iterate through sorted spans:
   - If gap to previous span > threshold: start new cluster
   - Otherwise: add to current cluster
4. If multiple clusters: split unit into sub-units
5. Each sub-unit inherits only concepts with spans in that cluster
```

**Test Coverage**:
- Single contiguous cluster → one unit ✅
- Large gap → split into multiple units ✅
- Multiple large gaps → multiple units ✅
- Empty input handled ✅
- Spans sorted correctly even if input unordered ✅
- Concepts distributed to correct clusters ✅
- Concepts spanning multiple clusters appear in both ✅

**Invariant Established**: All units have contiguous spans (max 10KB gap between adjacent spans).

---

### Phase 3: Phase Boundary Validation ✅

**Commit**: e754af9  
**Files Changed**: 2 files, +651 lines  
**Tests**: 14 unit tests, all passing

**Changes**:
- `validate_plan()` in `plan_v2_command.py`
  - Comprehensive plan validation before rewrite phase
  - Returns list of validation errors (empty if valid)
  - Checks:
    1. All units contiguous (max 10KB gap)
    2. No overlapping units (byte range conflicts)
    3. All span IDs exist in inventory
    4. No passenger concepts (concepts in units without source spans)

- `check_unit_contiguity()`
  - Verifies unit spans are within max_gap_kb threshold
  - Returns (is_valid, error_message) tuple

- `find_overlapping_units()`
  - Detects units with overlapping byte ranges
  - Returns list of (unit1_id, unit2_id) pairs

- `get_unit_byte_range()`
  - Computes (min_start, max_end) for unit's spans
  - Handles missing spans gracefully

**Fail-Closed Philosophy**: Defects caught at plan time (early) instead of assembly time (late).

**Test Coverage**:
- Valid contiguous units accepted ✅
- Non-contiguous units rejected ✅
- Overlapping units detected ✅
- Missing spans.jsonl handled ✅
- Empty span list handled ✅
- Unsorted spans handled ✅
- Multiple overlaps detected ✅
- Complete plan validation ✅

**Invariant Established**: Only valid plans (contiguous, non-overlapping units) proceed to rewrite.

---

### Phase 4: Assembly Simplification ✅

**Commit**: 59c92a9  
**Files Changed**: 2 files, +231 lines, -6 lines  
**Tests**: 3 unit tests, all passing

**Changes**:
- Enhanced `_collect_patches()` in `assemble_v2_command.py`
  - Added contiguity assertion before creating patches
  - Sorts unit spans by byte position
  - Validates max 10KB gap between adjacent spans
  - Exits with code 4 if non-contiguous unit detected

**Safety Net**: This check should never trigger (Phase 2 prevents non-contiguous units), but provides fail-safe if planner has bug.

**Test Coverage**:
- Non-contiguous units rejected with exit code 4 ✅
- Contiguous units accepted ✅
- Single-span units accepted ✅

**Invariant Established**: Assembly only processes verified contiguous units.

---

### Phase 5: ZLB End-to-End Validation 🔄

**Status**: In Progress  
**Snapshot**: `/tmp/zlb-test-rebuild`  
**Command**: `hv inventory . --freeze --adjudicator "phase5-test"`

**Plan**:
1. ✅ Initialize clean ZLB snapshot from fixtures
2. 🔄 Run inventory with Phase 1 locality enforcement (146 windows, ~15-20 min)
3. ⏳ Validate all concepts pass locality check (max 10KB span range)
4. ⏳ Run `hv plan-v2` to generate units with Phase 2 contiguity
5. ⏳ Validate all units are contiguous (Phase 3 validation)
6. ⏳ Document results and statistics

**Expected Outcome**:
- All concepts < 10KB span range
- No concepts filtered for excessive span range
- Units generated successfully with contiguous spans
- Plan validation passes

**Validation Script**: `scripts/validate_phase5.py` (ready)

**Progress**: Window 6/146 (as of last check)

---

## Test Summary

| Phase | Component | Tests | Status |
|-------|-----------|-------|--------|
| Phase 1 | Concept Locality | 9 | ✅ All passing |
| Phase 2 | Planner Contiguity | 8 | ✅ All passing |
| Phase 3 | Boundary Validation | 14 | ✅ All passing |
| Phase 4 | Assembly Safety | 3 | ✅ All passing |
| Phase 5 | ZLB E2E | TBD | 🔄 In progress |
| **Total** | | **34** | **34 passing** |

**Pre-existing Tests**: 18 patch assembly tests continue to pass (no regressions).

---

## Key Design Decisions

### 1. Why 10KB Threshold?

**Analysis**: ZLB document has 189,829 bytes across 1,751 spans. Average span ~108 bytes.

- 1KB threshold: Too tight, would split related concepts in same paragraph
- 10KB threshold: ~3-4 paragraphs, semantically coherent
- 50KB threshold: Too loose, wouldn't prevent original bug

**Decision**: 10KB balances semantic coherence with locality enforcement.

### 2. Why Enforce at Every Phase?

**Defense in Depth**: Each phase catches defects at different levels:
- Phase 1: Prevents bad concepts from entering baseline
- Phase 2: Splits units that would be non-contiguous
- Phase 3: Catches planner bugs before expensive rewrite
- Phase 4: Final safety net before assembly

Single-phase enforcement would be fragile—a bug in one phase cascades to assembly.

### 3. Why Not Merge Adjacent Spans?

**Alternative Considered**: Merge spans with small gaps into single spans.

**Rejected Because**:
- Changes source segmentation (violates immutability principle)
- Complicates span linking (protected objects, citations)
- Doesn't solve root cause (concepts still document-wide)

**Chosen Approach**: Keep span segmentation unchanged, enforce locality in concepts.

---

## Metrics and Statistics

### Code Changes
- Total files modified: 8
- Total lines added: 1,903
- Total lines removed: 48
- Net change: +1,855 lines
- Test coverage: 34 new unit tests

### Commits
- Phase 1: bbf9bfe
- Phase 2: 69fbc3b
- Phase 3: e754af9
- Phase 4: 59c92a9
- Total: 4 commits

### Test Execution Time
- Phase 1 tests: 0.39s
- Phase 2 tests: 0.15s
- Phase 3 tests: 0.17s
- Phase 4 tests: 0.14s
- Total: 0.85s (all 34 tests)

### ZLB Document
- File size: 189,841 bytes
- Total spans: 1,751
- Average span: ~108 bytes
- Extraction windows: 146
- Protected objects: 306

---

## Validation Checklist

### Pre-Phase 5 (Complete)
- [x] Phase 1 tests pass (9/9)
- [x] Phase 2 tests pass (8/8)
- [x] Phase 3 tests pass (14/14)
- [x] Phase 4 tests pass (3/3)
- [x] No regressions in existing tests (18 patch assembly tests pass)
- [x] Clean git history with descriptive commits
- [x] Validation script prepared

### Phase 5 (In Progress)
- [x] ZLB snapshot initialized
- [ ] Inventory completes successfully (exit code 0)
- [ ] All concepts pass locality validation (≤10KB span range)
- [ ] Baseline frozen successfully
- [ ] Concept statistics documented
- [ ] Plan generation succeeds
- [ ] All units verified contiguous
- [ ] Unit statistics documented

### Post-Phase 5 (Future)
- [ ] Run complete pipeline (inventory → plan → rewrite → assemble)
- [ ] Assembly succeeds without "original_text mismatch" errors
- [ ] Revised document generates successfully
- [ ] Integration test added to test suite
- [ ] Documentation updated with fix details
- [ ] Master program marked complete

---

## Risk Assessment

### Risks Mitigated
1. ✅ Concepts spanning entire document → Phase 1 enforcement
2. ✅ Units with large gaps → Phase 2 splitting
3. ✅ Defects discovered late (at assembly) → Phase 3 validation
4. ✅ Assembly crashes on invalid units → Phase 4 safety net

### Residual Risks
1. **Model may extract fewer concepts**: Locality constraint may cause model to abstain more frequently
   - Mitigation: Extraction windows designed for local context
   - Impact: Acceptable—quality over quantity

2. **More units may be created**: Splitting on gaps creates more units
   - Mitigation: Units still semantically coherent within 10KB threshold
   - Impact: Acceptable—more units = better granularity

3. **Phase 5 may reveal edge cases**: Real document may expose issues not caught by unit tests
   - Mitigation: Comprehensive unit tests cover wide range of scenarios
   - Impact: Will address if discovered

---

## Next Steps

1. **Complete Phase 5**: Wait for inventory to finish (~15 more minutes)
2. **Validate Results**: Run `scripts/validate_phase5.py`
3. **Document Findings**: Record concept/unit statistics
4. **Run Planning**: Execute `hv plan-v2` with Phase 2 enforcement
5. **Final Commit**: Merge all validation results
6. **Update Documentation**: Add fix to main README and CHANGELOG

---

## Conclusion

This fix addresses the root cause of the ZLB 140KB bug through systematic enforcement of locality constraints at every pipeline stage. The multi-phase approach provides defense in depth, catching defects early with comprehensive test coverage.

**Status**: 4/5 phases complete, 34/34 unit tests passing, ZLB end-to-end test in progress.
