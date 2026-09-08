# Audit Failure Analysis: Content Loss Passed All Gates

**Date**: 2026-09-08  
**Severity**: Critical  
**Status**: Identified, fix needed

## The Failure

The ZLB document lost 24% of protected content (retention_vs_source: 0.76), yet **passed all release gates** and was declared complete.

**What was lost:**
- 11 citations
- 5 labels  
- 4 equations
- Mathematical content in sections 5-8
- Entire bibliography system

**How it passed:** The assembly retained 100% of what the **drafter** created (retention_vs_drafts: 1.0), but the drafter had already dropped 24% from the **source**. The gates checked assembly→draft fidelity but never checked draft→source fidelity.

## Root Cause: Single-Stage Audit

The release gate at [release_command.py:554](../src/humanvoice/commands/release_command.py#L554) only checks:

```python
ASSEMBLY_RETENTION_THRESHOLD = 0.99
if retention_vs_drafts < ASSEMBLY_RETENTION_THRESHOLD:
    # Block release
```

This checks: **Did assembly lose anything the drafter created?**

It NEVER checks: **Did the drafter lose anything from the source?**

## Why This Happened

The correspondence tracking has two stages:

1. **Source → Drafts** (`retention_vs_source`)
   - Computed during drafting
   - Recorded in assembly manifest
   - **Never gated**

2. **Drafts → Assembly** (`retention_vs_drafts`)  
   - Computed during assembly
   - Recorded in assembly manifest
   - **Gated at 99%**

The architecture assumes:
- Drafts are the "source of truth"
- Assembly is just concatenation
- If assembly preserves drafts, we're done

But this misses the actual failure mode:
- **Planning creates coarse blueprints** (18 subsections → 2)
- **Drafting compresses heavily** (loses 24% of content)
- **Assembly faithfully preserves the lossy drafts** (100% retention)
- **Release gate sees 100% and approves** ✓

## Consequences

This audit blindness meant:
- Content loss was invisible to the system
- No diagnostic flagged the 0.76 retention rate
- The 1.0 assembly score gave false confidence
- Release would have shipped catastrophically incomplete work

## What Should Have Been Checked

### Gate 1: Draft Correspondence (MISSING)

After **draft command** completes all sections:
```python
DRAFT_RETENTION_THRESHOLD = 0.95  # Require 95% preservation from source

for section in all_sections:
    if section.retention_vs_source < DRAFT_RETENTION_THRESHOLD:
        # Block or warn
        # Diagnose: which objects were lost?
        # Root cause: planning too coarse? drafting too aggressive?
```

### Gate 2: Aggregate Correspondence (MISSING)

After **assembly** completes:
```python
SOURCE_RETENTION_THRESHOLD = 0.95

if assembly.retention_vs_source < SOURCE_RETENTION_THRESHOLD:
    # Block release
    # Report: X% of source content lost during drafting/assembly
```

### Gate 3: Assembly Fidelity (EXISTS)

Already implemented at release:
```python
ASSEMBLY_RETENTION_THRESHOLD = 0.99

if assembly.retention_vs_drafts < ASSEMBLY_RETENTION_THRESHOLD:
    # Block release
```

## Detailed Failure Timeline

### What Actually Happened (ZLB)

1. **Planning** (Sep 7, 17:33)
   - Created 10 subsections for 5000-word document
   - Section 7: 2 subsections covering 18 source subsections ❌
   - No planning validation detected this

2. **Drafting** (Sep 7, 18:40-19:12)
   - 9/10 sections succeeded initially
   - Section 4 failed (hit token ceiling), retried successfully
   - **No gate checked retention_vs_source per section**
   - Missing objects: 11 citations, 5 labels, 4 equations

3. **Assembly** (Sep 8, 04:01)
   - Assembled 10 drafts into complete document
   - retention_vs_drafts: 1.0 ✓
   - retention_vs_source: 0.76 ⚠ **NOT CHECKED**
   - Reported metrics but triggered no gate

4. **Blackline** (Sep 8, 04:01)
   - Generated comparison (initial version had LaTeX bugs)
   - No quality check on content completeness

5. **Acceptance** 
   - Human review noticed content loss in sections 5-8
   - Mathematical content deleted rather than rewritten
   - Bibliography missing entirely
   - **System had declared success**

## Proposed Fixes

### Immediate: Add Source Retention Gate

```python
# In release_command.py after line 568

SOURCE_RETENTION_THRESHOLD = 0.95  # 95% minimum

if retention_vs_source < SOURCE_RETENTION_THRESHOLD:
    missing_count = assembly_data.get("missing_from_source_count", 0)
    total_source = assembly_data.get("total_source_objects", 0)
    return {
        "reason": "source_correspondence",
        "detail": (
            f"Source retention {retention_vs_source:.1%} below "
            f"{SOURCE_RETENTION_THRESHOLD:.0%} threshold. "
            f"{missing_count}/{total_source} objects lost during drafting."
        ),
        "retention_vs_source": retention_vs_source,
        "missing_count": missing_count,
        "total_source": total_source,
    }
```

### Medium: Per-Section Retention Tracking

Track retention per draft section, not just aggregate:

```python
# In draft_command.py, record per-section metrics
{
    "section_title": "...",
    "retention_vs_source": 0.85,  # This section lost 15%
    "missing_objects": [...]  # What was lost
}
```

Flag sections with low retention during drafting, not at release.

### Long-term: Planning Validation

Add `hv validate-plan` command (separate from `hv validate-blueprint`):

1. Check if blueprint subsections are too coarse for source structure
2. Predict token usage per subsection
3. Estimate content compression required
4. Warn if any subsection requires >2:1 compression

### Audit Checklist

Release should block if ANY of these fail:

- [ ] `retention_vs_source >= 0.95` (source→draft preservation)
- [ ] `retention_vs_drafts >= 0.99` (draft→assembly preservation)
- [ ] No section has `retention_vs_source < 0.90`
- [ ] Bibliography commands present if source had them
- [ ] All `\cite{}` commands have corresponding bibliography entries
- [ ] No unresolved `?` references in compiled PDF
- [ ] Blackline compiles to valid PDF
- [ ] Word count within ±20% of target

## Lessons

1. **Multi-stage processes need multi-stage audit**
   - Don't just check the last stage
   - Check every transformation in the pipeline

2. **Metrics without gates are invisible**
   - `retention_vs_source` was computed and logged
   - Never gated, so 0.76 passed silently

3. **Success at one stage hides failure at prior stages**
   - 100% assembly retention gave false confidence
   - Masked the 76% drafting retention

4. **Human review caught what automation missed**
   - User noticed "sections 5-8 are disastrous"
   - System had already declared success

## Status

**Fixed:** Planning (subsection extraction, structural preservation)  
**Remaining:** Add source retention gate to release command  
**Future Work:** Per-section tracking, planning validation command
