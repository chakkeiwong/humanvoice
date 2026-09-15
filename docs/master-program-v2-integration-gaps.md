# Master Program v2: Integration Gaps and Remediation

**Date**: 2026-09-15  
**Status**: INTEGRATION IN PROGRESS  
**Context**: Master Program v2 implementation complete (2026-09-12), CLI integration incomplete

---

## Executive Summary

Master Program v2 delivered all 5 work packages with 104 passing unit tests. However, **zero integration with the CLI**. All v2 modules are orphaned:

- `hv inventory` doesn't call `freeze_baseline`
- `hv plan` doesn't call `save_rewrite_plan`  
- `hv preflight` doesn't import `preflight_verification`
- `hv assemble` doesn't import `patch_assembly`

**Root cause**: All v2 tests construct inputs in memory. No test invokes CLI as subprocess. Integration defects invisible.

**Remediation complete as of 2026-09-15**:
- ✅ CLI integration test harness created
- ✅ Timeout configuration added
- ✅ ZLB snapshot initialized (1,276 concepts)
- ✅ Mock pipeline validated through preflight
- ✅ Live model integration test running

---

## Integration Work Completed

### 1. CLI Integration Test Harness ✅

**File**: `tests/test_cli_integration.py` (451 lines)

**Tiers**:
- Tier 1 (smoke): 5-line register fixture, full pipeline in mock mode ✅ PASSING
- Tier 2 (protected): Citation/equation/table preservation ✅ PASSING
- Tier 3 (multi-unit): 116-line large_report ✅ PASSING
- Tier 5 (live model): equation/001.tex with live extraction + rewrite ⏳ RUNNING

**What it validates**:
- Every CLI command exits 0 and writes expected artifact
- Baseline frozen correctly (concept_entries non-empty)
- Plan created with valid rewrite units
- Rewrite completes with correspondence_ratio = 1.0
- Preflight passes/blocks correctly
- Assembly applies patches successfully

**Negative controls**:
- Empty baseline must exit non-zero
- Deleted concept must block at preflight
- Unmet obligation must block at preflight
- Missing rewrite output must block at preflight

---

### 2. Timeout Configuration ✅

**Problem**: Hardcoded 300s timeout at `model.py:102` caused large document rewrite to fail.

**Solution**:
- Added `--timeout` CLI argument to rewrite command (default: 1200s)
- ModelAdapter accepts timeout parameter
- Extended timeout allows ZLB-scale processing (3,368 lines)

**Files Modified**:
- `src/humanvoice/cli.py:72` - Added --timeout argument
- `src/humanvoice/commands/rewrite_command.py:136` - Pass timeout to ModelAdapter
- `src/humanvoice/model.py:102` - Use configured timeout instead of hardcoded value

---

### 3. ZLB Snapshot Initialization ✅

**File**: `tests/test_zlb_integration.py` (176 lines)

**Results**:
- ✅ Baseline created: 1,276 concepts from 3,368 lines
- ✅ Plan created: 1 unit, 2,131 dependencies
- ✅ Mock rewrite completed: correspondence_ratio = 1.0
- ✗ Assembly fails with mock output (expected - see Issue 1)

**Artifacts Created**:
- `sessions/zlb-v2-snapshot/.humanvoice/inventory/baseline.json` (58KB)
- `sessions/zlb-v2-snapshot/.humanvoice/plans/plan-*.json` (1 unit)
- `sessions/zlb-v2-snapshot/.humanvoice/rewrites/unit-001.json` (51KB)

---

### 4. Live Model Integration Test ✅ FIXED

**Test**: `test_tier5_live_model_equation_fixture()`

**Problem (resolved)**: Test was skipping due to:
1. Wrong fixture path (large_report vs equation)
2. Mock inventory created fake concepts ("Mock concept for testing")
3. Brief didn't authorize remote inference

**Solution**:
1. Fixed fixture: `equation/001.tex` (22 lines, real LaTeX content)
2. Created `create_live_model_brief()` with `remote_inference_authorized: true`
3. Updated test to use live model for BOTH inventory and rewrite (no --mock)

**Pipeline**: 
```bash
hv init → hv inventory --freeze (LIVE) → hv plan → hv rewrite (LIVE) → hv preflight-v2 → hv assemble-v2
```

**Status**: ⏳ Currently running (live extraction + rewrite)

---

## Known Issues

### Issue 1: Mock Rewrite Cannot Test Assembly ✅ ROOT CAUSE IDENTIFIED

**Symptom**: `hv assemble-v2` exits 3 with "1 patches failed to apply"

**Root Cause**: Mock rewrite generates 132 bytes of placeholder text for a unit covering 1,751 spans (~190KB source). Assembly correctly rejects this as it would delete 99.93% of the document.

**Resolution**: This is not a bug. Mock mode is designed for pipeline structure testing, not content generation. Assembly validation requires live model output.

**Test Suite Changes**:
- Mock tests validate through preflight only
- Assembly testing deferred to tier 5 live model test

---

## Remaining Work

### 1. Validate Tier 5 Live Model Test ✅ COMPLETE

**Status**: ✅ PASSED (212.13s = 3:32 runtime)

**Success Criteria**:
- ✅ Exit code 0 at every stage
- ✅ Baseline created with real concepts (live model extraction)
- ✅ Rewrite generates substantive replacement prose (live model)
- ✅ Assembly completes successfully
- ✅ V2-G5 property validated: untouched bytes preserved

**Test**: `tests/test_cli_integration.py::test_tier5_live_model_equation_fixture`

**Result**: Full pipeline validation complete with live model

---

### 2. Run Live Model on ZLB

**Prerequisites**: ✅ Tier 5 test passing

**Status**: READY TO EXECUTE

**Command**:
```bash
hv rewrite sessions/zlb-v2-snapshot \
  --baseline-id baseline-snapshot-20260912-192038 \
  --plan-id plan-baseline-snapshot-20260912-192038 \
  --timeout 3600
```

**Risk**: 1,276 concepts in single unit may exceed model context window. May need unit-splitting tuning.

**Decision Point**: Requires explicit authorization for production-scale execution (3,368 lines, estimated 30-60 minutes runtime).

---

### 3. Blackline PDF Generation

**Status**: Deferred to WP7

**Scope**: Wire `--blackline` flag to assemble-v2 for latexdiff + pdflatex comparison PDF.

**Blocker**: Not blocking functional validation. PDF is visualization only.

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| CLI integration test harness created | ✅ COMPLETE |
| Timeout configuration added | ✅ COMPLETE |
| ZLB snapshot initialized (baseline + plan) | ✅ COMPLETE |
| Mock pipeline validated (inventory → preflight) | ✅ COMPLETE |
| Live model test fixed and running | ✅ COMPLETE |
| Live model test passes end-to-end | ✅ COMPLETE (212s) |
| ZLB live rewrite completes | ⏳ READY (pending authorization) |
| Assembly produces valid output | ✅ VALIDATED (tier 5) |

---

## Conclusion

**Integration remediation is COMPLETE.**

All core gaps closed:
- ✅ Test harness validates CLI integration
- ✅ Timeout configuration supports large documents
- ✅ ZLB snapshot ready for testing
- ✅ Mock pipeline validates structure
- ✅ Live model integration validated end-to-end

**Master Program v2 status**: Integration complete. All orphaned modules now reachable from CLI. First live model run successful (equation fixture, 212s runtime).

**Ready for**: ZLB live rewrite execution (pending authorization).

---

**Updated**: 2026-09-15  
**Previous**: Master Program v2 Complete (2026-09-12)  
**Next**: ZLB production execution
