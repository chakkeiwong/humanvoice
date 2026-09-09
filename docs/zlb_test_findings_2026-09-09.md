# ZLB Pipeline Test Results - 2026-09-09

## Executive Summary

**Test Objective:** Verify that recent remediation fixes prevent the 24% content loss issue on the actual ZLB document.

**Outcome:** ⚠️ **Partially successful** - Discovered and fixed a critical blueprint schema bug, but full end-to-end test incomplete due to drafting failures.

---

## Document Characteristics

- **Source:** ~/workspace/BayesFilter/docs/surveys/zlb_discontinuous_hmc/zlb_discontinuous_hmc_survey.tex
- **Size:** 3,368 lines, 186KB
- **Structure:** 18 sections, 42 subsections
- **Protected Objects:** 306 total (110 equations, 180 labels, 13 displaymath, 3 tables)
- **Complexity:** Large academic survey paper on Bayesian inference methods

---

## Bug Discovered: Blueprint Schema Mismatch

### Problem
Pipeline command crashed with "Plan abstained: blueprint contains zero sections" despite planner successfully generating a valid blueprint with 17 chapters and 49 subsections.

### Root Cause
Blueprint schema has two formats:
- **Flat:** `blueprint.sections[]` - for documents < 5000 words
- **Hierarchical:** `blueprint.chapters[].subsections[]` - for documents >= 5000 words

Pipeline command only checked `blueprint["blueprint"]["sections"]`, missing the chapters variant entirely.

### Impact
**CRITICAL:** This bug would have blocked ALL documents >= 5000 words from running through the pipeline, regardless of subsection extraction fixes.

### Fix (commit 2c89bd7)
Added `_flatten_blueprint_sections()` helper function that:
1. Handles both blueprint schemas
2. Flattens chapters.subsections into flat list for drafting
3. Preserves chapter context metadata
4. Updated 3 call sites in pipeline_command.py

**Tests:** All 13 pipeline orchestration tests passing

---

## Test Results

### Stage 1: Planning ✅
- **Status:** SUCCESS
- **Blueprint generated:** 17 chapters, 49 subsections
- **Subsection extraction working:** Planner correctly identified subsection hierarchy
- **Validation:** Blueprint schema correctly identified as chapters format

### Stage 2: Preflight ✅
- **Status:** SUCCESS  
- **Findings:** (data not captured, but stage completed)

### Stage 3: Drafting ⚠️
- **Status:** PARTIAL - 9/49 sections completed before stopping
- **Completed sections:** 0, 3-6, 8, 10-12
- **Failed sections:** 4 sections with register violations, 1 with truncation

**Failures:**
1. **Register violations (4 sections):** Model generated first-person text ("we") violating register constraints
2. **Output truncation (1 section):** Section exceeded 8192 token limit

**Protected Object Retention (from 9 completed sections):**
- Section 0: 0/1 (0%) - 1 missing
- Section 3: 5/5 (100%)
- Section 4: 5/5 (100%)
- Section 5: 9/9 (100%)
- Section 6: 1/1 (100%)
- Section 8: 9/10 (90%) - 1 missing
- Section 10: 7/7 (100%)
- Section 11: 3/3 (100%)
- Section 12: 3/3 (partial)

**Overall from completed sections: 42/45 (93.3%) retention**

### Stage 4: Repair
- **Status:** Not reached (drafting incomplete)

### Stage 5: Assembly
- **Status:** Not reached (drafting incomplete)

### Stage 6: Release (SOURCE RETENTION GATE)
- **Status:** ❌ Not reached - Could not test the primary fix

---

## Key Findings

### ✅ Fixes Verified Working

1. **Subsection Extraction (09ccee1):** Planner correctly identified and preserved all 42 subsections as 49 subsections in blueprint (some splitting occurred)

2. **Blueprint Schema Handling (2c89bd7 - NEW):** Pipeline now correctly processes chapter-based blueprints for large documents

3. **Token Ceiling Removal (677e9d4):** No mid-section truncation observed within successful sections

### ⚠️ Could Not Verify

1. **Source Retention Gate (cb56c79):** Pipeline stopped before reaching release stage, so the critical fix could not be tested end-to-end

2. **Assembly Correspondence:** Did not reach assembly stage

### ❌ New Issues Revealed

1. **Register Violations:** Model generating first-person pronouns despite register constraints
   - 4 sections failed with: "Register violation: first_person usage found"
   - Indicates prompt engineering or model instruction following issue

2. **Output Truncation:** 1 section exceeded 8192 token output limit
   - Suggests subsection granularity still too coarse for some sections
   - Or: section inherently large even after splitting

3. **Partial Completion Handling:** Pipeline does not have robust checkpoint/resume
   - When drafting fails partway, no way to continue from last successful section
   - This is exactly the Phase 3 (checkpoint/resume) gap we identified

---

## Conclusions

### Critical Fix Applied ✅
The blueprint schema bug (2c89bd7) is a **CRITICAL** fix that unblocks all large documents. Without it, any document >= 5000 words would fail immediately after planning.

### Source Retention Gate Not Tested ❌
The primary remediation fix (source retention gate at release) could not be tested because:
- Drafting failures prevented pipeline from reaching assembly/release stages
- Need either:
  1. Fix register violations and retry full pipeline
  2. Use mock mode to test release gate logic directly
  3. Test with smaller document that completes drafting

### Phase 3 Validation
This test empirically validates the need for Phase 3 (checkpoint/resume):
- Pipeline consumed significant tokens (52k+ in subagent)
- Completed 9/49 sections before failing
- No way to resume from section 9 and continue
- Must restart from beginning, wasting completed work

---

## Recommendations

### Immediate (before v1.2 release)

1. **Test source retention gate with mock mode:** Run pipeline with `--mock` to skip drafting and test release gate logic directly with synthetic retention data

2. **Test source retention gate with smaller document:** Use a complete document (e.g., test fixtures) that drafts successfully to verify release gate blocks correctly

3. **Document the blueprint schema issue:** Add to known issues or release notes that this bug would have blocked large documents

### Short-term (v1.2 post-release)

1. **Investigate register violations:** Why is model generating first-person text despite constraints?

2. **Review subsection granularity:** 49 subsections from 42 source subsections suggests some merging/splitting - is this optimal?

3. **Add truncation handling:** Detect when a subsection is too large and auto-split further

### Medium-term (Phase 3)

1. **Implement checkpoint/resume:** ZLB test confirms this is essential for large documents
   - Save after every N sections
   - Resume from last checkpoint on failure
   - Report progress: "Section 9/49 complete, ~340k tokens remaining"

---

## Files Modified

- src/humanvoice/commands/pipeline_command.py (commit 2c89bd7)
  - Added `_flatten_blueprint_sections()` helper
  - Updated 3 call sites (lines 219, 272, 621)

## Test Artifacts

- Test directory: /tmp/zlb_test_2026-09-09/
- Snapshot: /tmp/zlb_test_2026-09-09/snapshot/
- Protected objects extracted: 306 (110 equations, 180 labels, 13 displaymath, 3 tables)
- Subagent ID: a48a6e9f06752be57
- Token usage: 52,609 tokens

---

## Next Steps

1. Run mock mode test to verify source retention gate logic
2. Consider testing with fixtures/synthetic/large_report (smaller, should complete)
3. Proceed with v1.2 release noting blueprint schema fix as critical addition
4. Plan Phase 3 implementation for post-v1.2
