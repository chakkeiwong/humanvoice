# Audit Failure Analysis: ZLB Content Loss Incident

**Date**: 2026-09-09  
**Incident**: ZLB document lost 24% of protected content but passed all release gates  
**Root Cause**: Missing source retention gate in release validation

---

## Executive Summary

The humanvoice release process failed to detect that 24% of protected objects were lost during the drafting phase of the ZLB document. The release gate checked **assembly fidelity** (retention_vs_drafts = 1.0 ✓) but not **drafting fidelity** (retention_vs_source = 0.76 ✗). This allowed catastrophic content loss to pass all quality gates.

**Fix**: Added source retention gate at [release_command.py:572-602](../src/humanvoice/commands/release_command.py) that blocks release when `retention_vs_source < 0.95`.

---

## The Failure

### What Happened

**ZLB Document Metrics**:
- Total source objects: 84
- Objects preserved in drafts: 64
- Objects lost during drafting: 20
- **retention_vs_source: 0.76** (76% preserved, 24% lost)
- retention_vs_drafts: 1.0 (100% - assembly preserved all drafted content)

**Result**: Document passed all gates and was cleared for release despite losing 1 in 4 protected objects.

### What We Missed

The original release gate (lines 554-562) only checked:

```python
ASSEMBLY_RETENTION_THRESHOLD = 0.99
if retention_vs_drafts < ASSEMBLY_RETENTION_THRESHOLD:
    return {"reason": "assembly_correspondence", ...}
```

This verified that **assembly preserved what the drafter produced**, but never checked whether **the drafter preserved what was in the source**.

### Why This Matters

Protected objects are the contract between author and reader:
- Equations that prove theorems
- Citations that establish provenance
- Labels that enable cross-references
- Display math that presents results

Losing 24% of these objects means theorems without proofs, claims without citations, and broken cross-references. The content is unusable for academic work.

---

## The Fix

### Source Retention Gate

Added at [release_command.py:572-602](../src/humanvoice/commands/release_command.py):

```python
SOURCE_RETENTION_THRESHOLD = 0.95
if retention_vs_source < SOURCE_RETENTION_THRESHOLD:
    # Load correspondence details
    missing_count = len(corr_to_source.get("missing", []))
    total_source = len(corr_to_source.get("preserved", [])) + missing_count
    
    return {
        "reason": "source_correspondence",
        "detail": (
            f"Source retention {retention_vs_source:.1%} below "
            f"{SOURCE_RETENTION_THRESHOLD:.0%} threshold. "
            f"{missing_count}/{total_source} objects lost during drafting. "
            "This indicates planning created subsections too coarse for the source structure, "
            "forcing the drafter to compress content heavily."
        ),
        "retention_vs_source": retention_vs_source,
        "retention_vs_drafts": retention_vs_drafts,
        "missing_count": missing_count,
        "total_source": total_source,
    }
```

### Gate Ordering

The release now checks two retention gates in sequence:

1. **Assembly gate** (line 554): `retention_vs_drafts >= 0.99`
   - Verifies assembly preserved drafted content
   - Threshold: 99% (stricter - we have full control)

2. **Source gate** (line 572): `retention_vs_source >= 0.95`
   - Verifies drafts preserved source content
   - Threshold: 95% (allows 5% loss due to word budget compression)

Both must pass for release to proceed.

### Why 95% for Source, 99% for Assembly?

- **Assembly (99%)**: Final stage where we have complete control. Near-perfect fidelity is achievable and required.
  
- **Source (95%)**: Drafting involves compression to meet word budgets. Some loss is acceptable, but 5% is the limit. Anything beyond indicates structural planning failure.

---

## Test Coverage

### New Tests

Created [tests/test_source_retention_gate.py](../tests/test_source_retention_gate.py) with 5 tests:

1. **test_zlb_scenario_would_be_blocked**: Verifies 76% retention fails the gate (regression test)
2. **test_good_retention_passes**: Verifies 97% retention passes
3. **test_boundary_cases**: Tests 94.9%, 95%, 95.1% retention
4. **test_assembly_threshold_stricter_than_source**: Verifies 0.99 > 0.95
5. **test_gate_implementation_exists**: Verifies gate code is present in release_command.py

### Test Results

```
228 passed in 9.18s
```

All existing tests continue to pass, plus 5 new tests verify the source retention gate.

---

## What This Prevents

### Before Fix

```
ZLB metrics: retention_vs_source=0.76, retention_vs_drafts=1.0
Gate check: retention_vs_drafts >= 0.99 ✓
Result: PASS (20/84 objects lost, undetected)
```

### After Fix

```
ZLB metrics: retention_vs_source=0.76, retention_vs_drafts=1.0
Gate 1: retention_vs_drafts >= 0.99 ✓
Gate 2: retention_vs_source >= 0.95 ✗
Result: BLOCKED
Detail: "Source retention 76% below 95% threshold. 20/84 objects lost during drafting."
```

---

## Why The Audit Failed

### The Blind Spot

The original audit process assumed:
- If assembly preserves drafts perfectly → content is preserved
- **Missing assumption**: Drafts themselves preserve source content

This created a blind spot where drafting losses went undetected because assembly fidelity was perfect.

### The Lesson

**Multi-stage pipelines need per-stage retention gates**, not just final-stage verification:

```
Source (84 objects)
    ↓ [GATE NEEDED: retention_vs_source >= 0.95]
Drafts (64 objects, 20 lost) ← UNDETECTED
    ↓ [GATE EXISTS: retention_vs_drafts >= 0.99]
Assembly (64 objects, 0 lost) ← DETECTED
```

### Process Improvement

Going forward, any multi-stage transformation must:
1. Emit retention metrics at each stage boundary
2. Gate each boundary independently
3. Never assume upstream fidelity from downstream metrics

---

## Related Issues

- **WP6 completion** (2026-08-28): Fixed prompt-hash + source-build gates, but missed retention gates
- **Release gate fail-open** (2026-08-29): Pilot released known violations, flagged systemic gate problems
- **G4 decision** (approved): Internal evaluation only; external release blocked until audit gaps closed

This fix closes one audit gap. Two remain per [v1.2 plan](../../.claude/projects/-home-ubuntu-workspace-humanvoice/memory/v1_2_plan.md):
1. ✅ Evidence item emission (Blocker 2, completed 2026-09-03)
2. **Source retention gate** (completed 2026-09-09, this fix)
3. Transmission tracking (pending)

---

## Verification

To verify the fix prevents future ZLB-like failures:

```bash
# Run regression tests
pytest tests/test_source_retention_gate.py -xvs

# Test with actual ZLB data (if available)
hv release /tmp/zlb_pipeline_final/snapshot

# Expected result:
# ❌ Release blocked: Source retention 76% below 95% threshold.
#    20/84 objects lost during drafting.
```

---

## Commit Message

```
Fix: Add source retention gate to catch drafting losses

Issue: ZLB document lost 24% of content (retention_vs_source=0.76)
but passed all gates because only assembly fidelity was checked.

Changes:
- Add SOURCE_RETENTION_THRESHOLD=0.95 gate at release_command.py:572
- Block release when retention_vs_source < 0.95
- Report missing object count and total source objects
- Add 5 regression tests in test_source_retention_gate.py

Result: ZLB scenario now blocked at release gate.
All 228 tests pass.

Ref: Audit failure analysis (docs/audit_failure_analysis.md)
```
