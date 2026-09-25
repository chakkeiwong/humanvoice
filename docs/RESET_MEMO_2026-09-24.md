# Reset Memo: ZLB Rebuild Execution Audit
**Date:** 2026-09-24  
**Session:** Full pipeline rebuild with Phase 1-3 verification  
**Status:** PHASES 1-3 VERIFIED WORKING | REWRITE PHASE COMPLETED WITH ISSUES

---

## Executive Summary

Conducted comprehensive execution audit of Master Program Phases 1-3 (Concept Locality, Planner Contiguity, Phase Boundary Validation). All three phases are **integrated, executing, and producing correct results**.

**Key Achievement:** Verified that the architectural fixes work as designed:
- ✅ Concepts have max 2.5 KB span range (threshold: 10 KB)
- ✅ Units have max 6.85 KB gaps (threshold: 10 KB)
- ✅ Plan passes all validation checks

**Rewrite Results:** 10/12 units completed (83% success), but correspondence check failed at 82.45% (requires 100%).

---

## What We Did

### 1. Master Program Audit (Code Integration)

**Initial Audit Finding:**
- Phase 1: Code exists but NOT called ❌
- Phase 2: Code exists but NOT called ❌
- Phase 3: Fully integrated ✅

**Corrected Audit Finding:**
- Phase 1: FULLY INTEGRATED ✅
- Phase 2: FULLY INTEGRATED ✅
- Phase 3: FULLY INTEGRATED ✅

My initial audit was wrong. I checked for direct function calls but missed that:
- Phase 1 uses `concept_locality` module (imported and called at inventory_command.py:419)
- Phase 2 uses call chain: `create_rewrite_plan() → partition_concepts_into_units() → finalize_unit() → build_span_clusters()`
- Phase 3 directly called at plan_v2_command.py:338

### 2. Execution Audit (Runtime Verification)

**Test Environment:**
- Location: `/tmp/zlb-test-rebuild-final`
- Source: `zlb_source.tex` (189,829 bytes, 3,368 lines)
- Method: Fresh rebuild from scratch

**Phase 1 Execution Results:**
```
Concepts extracted: 718
Max span range: 2.5 KB
Threshold: 10 KB
Violations: 0
Status: ✅ PASSED
```

**Verification:**
- Manually analyzed all 718 concepts
- Computed span ranges from byte offsets
- Confirmed max range = 2.5 KB (well below 10 KB threshold)
- Phase 1 enforcement is working correctly

**Phase 2 Execution Results:**
```
Units created: 12
Max gap between spans: 6.85 KB
Threshold: 10 KB
Violations: 0
Status: ✅ PASSED
```

**Verification:**
- Analyzed all 12 units for contiguity
- Computed gaps between consecutive spans
- Confirmed max gap = 6.85 KB (below 10 KB threshold)
- Phase 2 splitting is working correctly

**Phase 3 Execution Results:**
```
✓ All units contiguous (max gap: 10KB)
✓ No overlapping units
✓ All span IDs valid
✓ No passenger concepts
Plan validated: true
Status: ✅ PASSED
```

**Verification:**
- Checked for passenger concepts (concepts without spans in their unit)
- Checked for overlapping units
- Checked span ID validity
- All checks passed

### 3. Rewrite Phase Execution

**Command:**
```bash
hv rewrite . --baseline-id baseline-zlb-final-rebuild --plan-id plan-baseline-zlb-final-rebuild
```

**Results:**
```
Completed: 10/12 units (83% success)
Failed: 2 units
Concepts mapped: 592/718 (82.45%)
Exit code: 1 (correspondence check failed)
```

**Unit Files Created:**
- All 12 unit JSON files exist in `.humanvoice/rewrites/`
- But 2 units have empty/failed rewrites

**Issue:**
The rewrite phase requires 100% concept correspondence (Master Program V2-G3 requirement), but achieved only 82.45%. This is similar to the old ZLB rebuild failure rate.

---

## Key Findings

### Finding 1: Phase 1-3 Fixes Are Working

The architectural fixes successfully address the root causes of the double section header bug:

**Old Pipeline Problems:**
- Concepts could have 144 KB span ranges (unbounded)
- Units could have 140 KB gaps (non-contiguous)
- No validation before accepting plans

**New Pipeline Solutions:**
- Phase 1: Max span range reduced to 2.5 KB ✅
- Phase 2: Max unit gap reduced to 6.85 KB ✅
- Phase 3: Plan validation catches issues before rewrite ✅

### Finding 2: Rewrite Success Rate Unchanged

Despite the architectural improvements, rewrite success rate remains ~83%:

**Old ZLB Rebuild:**
- Units completed: 9/11 (82%)
- Unit-005 failed (140 KB gap)
- Unit-008 failed

**New ZLB Rebuild:**
- Units completed: 10/12 (83%)
- 2 units failed (TBD which ones)
- All units have <10 KB gaps

**Implication:**
The 17% failure rate is NOT caused by non-contiguous units or poor concept locality. It's caused by something else (likely model failures, content complexity, or rewrite engine issues).

### Finding 3: Correspondence Check Is Strict

The rewrite phase exits with error code 1 when correspondence < 100%:

```
Error: Correspondence < 1.0 (Master Program v2 V2-G3 requires 100%)
```

This is a **fail-closed** design: the pipeline refuses to proceed to assembly unless all concepts are mapped. This prevents partial rewrites from corrupting the output.

---

## Comparison: Old vs New

### Inventory Phase

| Metric | Old ZLB | New ZLB |
|--------|---------|---------|
| Concepts | 1,137 | 718 |
| Spans | 1,751 | 1,751 |
| Max concept span range | 144 KB | 2.5 KB |
| Locality enforcement | ❌ No | ✅ Yes |

### Planning Phase

| Metric | Old ZLB | New ZLB |
|--------|---------|---------|
| Units | 11 | 12 |
| Max unit gap | >140 KB | 6.85 KB |
| Contiguity enforcement | ❌ No | ✅ Yes |
| Plan validation | ❌ No | ✅ Yes |

### Rewrite Phase

| Metric | Old ZLB | New ZLB |
|--------|---------|---------|
| Units completed | 9/11 (82%) | 10/12 (83%) |
| Concepts mapped | ~87% | 82.45% |
| Failed units | 2 (unit-005, unit-008) | 2 (TBD) |
| Exit code | 0 (false success) | 1 (fail-closed) |

### Key Difference

**Old pipeline:** Failed silently and proceeded to assembly with partial rewrites, causing corruption (double section headers).

**New pipeline:** Fails loudly and refuses to proceed with partial rewrites, preventing corruption.

---

## What Worked

### ✅ Architectural Fixes (Phase 1-3)

1. **Concept Locality Enforcement**
   - Code integrated correctly
   - Executing during inventory
   - Producing correct results (max 2.5 KB)

2. **Planner Contiguity Enforcement**
   - Code integrated correctly
   - Executing during planning
   - Producing correct results (max 6.85 KB gaps)

3. **Phase Boundary Validation**
   - Code integrated correctly
   - Executing during planning
   - Producing correct results (0 validation errors)

### ✅ Fail-Closed Design

The new pipeline correctly refuses to proceed when correspondence < 100%, preventing the corruption that caused the double section header bug.

### ✅ Audit Methodology

The execution audit successfully verified that:
- Code is integrated into the pipeline
- Code is called during execution
- Code produces expected results
- Results match design specifications

---

## What Didn't Work

### ❌ Rewrite Success Rate

Despite architectural improvements:
- 2/12 units still fail (17% failure rate)
- Correspondence only 82.45% (not 100%)
- Root cause is NOT architectural (units are contiguous)

**Hypothesis:**
The 17% failure rate is caused by:
1. Model failures (timeout, token limit, refusal)
2. Content complexity (unit too difficult to rewrite)
3. Rewrite engine bugs (prompt issues, parsing failures)
4. Concept extraction quality (bad concepts can't be rewritten)

### ❌ 100% Correspondence Requirement

The Master Program V2-G3 requirement for 100% correspondence is too strict:
- Achieving 100% may be impossible for complex documents
- Even 83% success prevents assembly due to fail-closed design
- May need to relax requirement or fix underlying rewrite issues

---

## Outstanding Questions

### Q1: Which 2 units failed in the new rebuild?

**Status:** Unknown - need to analyze rewrite logs

The output shows 10/12 completed, but all 12 unit files exist. Need to check:
- Which units have empty `replacement_latex`
- What error messages were logged
- Whether failures are the same units as old rebuild

### Q2: Why did those units fail?

**Status:** Unknown - need to investigate failure modes

Possible causes:
- Model timeout (unit too large)
- Model refusal (content issues)
- Parsing failure (malformed LaTeX)
- Concept quality issues (unmappable concepts)

### Q3: Can we achieve 100% correspondence?

**Status:** Unknown - may require relaxing requirement

Options:
1. Fix rewrite engine to achieve 100% success
2. Relax correspondence requirement to 90-95%
3. Allow partial assembly with warnings
4. Improve concept extraction to reduce unmappable concepts

### Q4: Does contiguity improvement help unit success?

**Status:** Unclear - success rate unchanged at ~83%

The architectural fixes did NOT improve unit success rate:
- Old: 82% success (9/11)
- New: 83% success (10/12)

This suggests contiguity was NOT the main cause of unit failures.

---

## Recommendations

### Immediate Actions

1. **Analyze Failed Units**
   - Identify which 2 units failed
   - Extract error messages from rewrite logs
   - Compare to old rebuild failures
   - Determine if same units or different units

2. **Investigate Failure Root Cause**
   - Check for model timeouts
   - Check for parsing errors
   - Check for concept quality issues
   - Check for content complexity patterns

3. **Update Master Program Status**
   - Document Phase 1-3 as VERIFIED
   - Document rewrite success rate as 83%
   - Document correspondence issue as BLOCKER
   - Update Phase 4 status (assembly blocked)

### Strategic Decisions Needed

1. **Correspondence Requirement**
   - Should we relax 100% requirement?
   - What is acceptable threshold (90%? 95%?)?
   - Should we allow partial assembly with warnings?

2. **Rewrite Engine Improvements**
   - Should we improve rewrite prompts?
   - Should we add retry logic for failed units?
   - Should we add unit splitting for oversized units?

3. **Phase 5-6 Priorities**
   - Should we fix rewrite issues before Phase 5-6?
   - Or proceed with Phase 5-6 on 83% success rate?
   - How do we define "success" for golden test?

---

## Files Modified

### Documentation Created
- `docs/MASTER_PROGRAM_EXECUTION_AUDIT.md` - Full execution audit report
- `docs/RESET_MEMO_2026-09-24.md` - This memo

### Documentation Updated
- `docs/MP-ZLB-REBUILD-STATUS.md` - Updated with execution audit results

### Test Environment
- `/tmp/zlb-test-rebuild-final/` - Fresh rebuild with Phase 1-3 fixes
  - Inventory: 718 concepts, 1,751 spans
  - Plan: 12 units, all contiguous
  - Rewrites: 10/12 completed, 82.45% correspondence

---

## Verification Evidence

### Phase 1 Verification
```python
# Manual verification script output
Concepts checked: 718
Max span range: 2.5 KB
Threshold: 10 KB
Violations: 0
✅ PHASE 1 PASSED
```

### Phase 2 Verification
```python
# Manual verification script output
Total units: 12
Max gap between spans: 6.85 KB
Threshold: 10 KB
Violations: 0
✅ PHASE 2 PASSED
```

### Phase 3 Verification
```
# Planner output
✓ All units contiguous (max gap: 10KB)
✓ No overlapping units
✓ All span IDs valid
✓ No passenger concepts
✅ PHASE 3 PASSED
```

### Rewrite Output
```
# Rewrite command output
WP-V2-3: Rewrite phase complete
  Completed: 10/12
  Failed: 2
  Concepts mapped: 592/718

Correspondence ratio: 82.45%
Error: Correspondence < 1.0 (Master Program v2 V2-G3 requires 100%)
Exit code: 1
```

---

## Next Session Priorities

1. **Identify failed units** - Analyze which 2 units failed and why
2. **Decide on correspondence threshold** - 100% or relaxed?
3. **Fix or bypass rewrite blocker** - Can't test assembly until rewrite succeeds
4. **Update Master Program** - Reflect execution audit findings
5. **Plan Phase 4 testing** - How to test assembly with partial rewrites?

---

## Session Statistics

**Duration:** ~3 hours  
**Cost:** ~$15 (inventory + planning + rewrites)  
**Token Usage:** ~65K tokens (context management)  
**Phases Tested:** 1, 2, 3, rewrite  
**Phases Verified:** 1, 2, 3  
**Phases Blocked:** 4 (assembly), 5 (golden test), 6 (scale testing)

---

## Conclusion

**The architectural fixes work.** Phase 1-3 are integrated, executing, and producing correct results. Concepts are local, units are contiguous, and plans are validated.

**But the rewrite success rate hasn't improved.** Despite fixing the architectural issues, 17% of units still fail. This suggests the root cause of unit failures is NOT architectural.

**The pipeline is now fail-closed.** The new design correctly prevents corruption by refusing to assemble partial rewrites. This is better than silently corrupting output, but blocks progress until rewrite issues are resolved.

**Decision needed:** Should we fix the rewrite engine to achieve 100% correspondence, or relax the requirement to allow assembly with 80-90% correspondence?

---

**Prepared by:** Claude (Opus 5)  
**Session ID:** 2026-09-24-execution-audit  
**Audit Report:** `docs/MASTER_PROGRAM_EXECUTION_AUDIT.md`  
**Test Rebuild:** `/tmp/zlb-test-rebuild-final/`
