# Word Budget Reform: From Hard Limits to Quality-First Guidance
**Date:** 2026-09-10  
**Status:** Ready for Execution  
**Priority:** HIGH (fixes content deletion issue discovered in ZLB test)

---

## Executive Summary

**Problem:** Hard word budget limits cause the model to arbitrarily delete important content to hit target word counts. ZLB test showed critical explanations (e.g., "discontinuous needs care") deleted because the model prioritized word count compliance over content preservation.

**Solution:** Convert word budgets from hard limits to guidance with high guardrails. Let the model focus on quality and completeness while preventing runaway token consumption.

**Impact:** 
- Preserves important content that requires thorough explanation
- Eliminates arbitrary content deletion
- Maintains cost control through reasonable guardrails
- Aligns with reader-focused quality gates (retention_vs_source ≥ 95%)

---

## Problem Analysis

### Current System (Hard Budget)

**Prompt tells model:**
```
Word budget: 450 (±20% acceptable)
Stay within word budget
```

**What happens:**
1. Model sees 450-word hard target
2. Source content requires 600 words for proper explanation
3. Model forced to delete content to hit 540-word ceiling (450 × 1.2)
4. Important content (definitions, foundational explanations) deleted
5. Result: Passes word budget check, fails content preservation

**Example from ZLB:**
- Section: "Why gradient-based MCMC matters" 
- Word budget: 450 words
- Source lines: 51-98 (≈600-700 words)
- Contains: Critical "discontinuous needs care" explanation
- Result: Explanation deleted to meet budget
- User feedback: "This genuinely explains an important point. It is badly written, but it has to be improved, not deleted."

### Root Cause: Goal Misalignment

**We want:** High-quality, complete explanations that preserve important content  
**We measure:** Word count compliance  
**Model optimizes for:** What we measure (word count), not what we want (quality)

**Result:** Perverse incentive to delete content rather than explain it well

---

## Proposed Solution

### Core Principle: Quality-First with Guardrails

**Word budgets become guidance, not hard limits.**

1. **Primary goal:** Completeness and clarity
2. **Secondary goal:** Reasonable length (guidance)
3. **Guardrail:** Maximum words to prevent token explosion
4. **Gate:** Content preservation (retention_vs_source ≥ 95%), not word count

---

## Implementation Plan

### **Change 1: Modify Draft Prompt**

**Current (draft_command.py lines 378-406):**
```python
prompt = f"""Generate a LaTeX draft for this section of a technical document.

**Section title:** {title}
**Purpose:** {purpose}
**Word budget:** {word_budget} (±20% acceptable)
**Reader:** {reader}
...
**Requirements:**
- Stay within word budget (±20%)
...
"""
```

**New:**
```python
# Calculate guidance and guardrail
target_guidance = word_budget  # Original planner target
absolute_maximum = min(word_budget * 4, 2000)  # Guardrail: 4x or 2000, whichever is lower

prompt = f"""Generate a LaTeX draft for this section of a technical document.

**Section title:** {title}
**Purpose:** {purpose}
**Target length:** {target_guidance} words (guidance, not a hard limit)
**Maximum allowed:** {absolute_maximum} words (guardrail only - do not target this)
**Reader:** {reader}
...

**Length Guidelines:**
Your primary goal is to write a complete, clear explanation that preserves all important 
content from the source material.

Target length: {target_guidance} words
- This is GUIDANCE for reasonable brevity
- If explaining well requires {int(target_guidance * 1.3)} words, use them
- If you can be complete in {int(target_guidance * 0.8)} words, that's fine too

Absolute maximum: {absolute_maximum} words
- This is a GUARDRAIL to prevent token explosion
- Only relevant if you're writing far beyond what's needed
- Do NOT try to write up to this limit
- Typical good sections are {target_guidance}-{int(target_guidance * 1.5)} words

**Quality matters more than hitting an exact word count.**

**Requirements:**
- Preserve all important content from source (definitions, key explanations, foundational concepts)
- Explain concepts clearly and completely
- Maintain technical precision
- Remove only: pure repetition without variation, unnecessary verbosity
- Keep: variations that aid understanding (per claudecodex policies)
...
"""
```

**Rationale for 4x/2000 guardrail:**
- 4x gives generous headroom (450 → 1800 words typical case)
- 2000 absolute cap prevents extreme cases
- Most well-written sections will be 1x-1.5x target anyway
- Guardrail rarely reached in practice

---

### **Change 2: Update Word Budget Validation**

**Current (draft_command.py lines 817-821):**
```python
# Check word count
word_count = metadata["word_count"]
budget = section.get("word_budget", 500)
if word_count > budget * 1.2:  # Allow 20% overage
    raise ValueError(
        f"Draft exceeds word budget: {word_count} words > {budget * 1.2} "
        f"(budget was {budget})"
    )
```

**New:**
```python
# Check word count against guardrail only
word_count = metadata["word_count"]
budget = section.get("word_budget", 500)
absolute_maximum = min(budget * 4, 2000)

# Guardrail check (rarely triggered)
if word_count > absolute_maximum:
    raise ValueError(
        f"Draft exceeds absolute maximum: {word_count} words > {absolute_maximum}. "
        f"Target was {budget} words (guidance). Maximum is {absolute_maximum} words (guardrail). "
        f"This section may need to be split into smaller subsections."
    )

# Information logging (not an error)
if word_count > budget * 1.5:
    print(
        f"Note: Section '{section.get('title')}' is {word_count} words "
        f"(target guidance was {budget}). This is acceptable if content completeness requires it.",
        file=sys.stderr
    )
elif word_count < budget * 0.5:
    print(
        f"Note: Section '{section.get('title')}' is {word_count} words "
        f"(target guidance was {budget}). Consider if more explanation would help readers.",
        file=sys.stderr
    )
```

**Changes:**
- Hard limit removed (budget × 1.2 → absolute_maximum)
- Informational logging added (helps identify planning issues)
- Failure only on guardrail breach (rare)

---

### **Change 3: Remove Word Budget Compliance Gate**

**Current:** No explicit gate exists, but word budget enforced via ValueError

**New:** No change needed - already no gate. The ValueError removal above is sufficient.

**Future consideration:** Add document-level reading time gate in Phase 3

---

### **Change 4: Update Tests**

**Test files to update:**
- `tests/test_budget_enforcement.py`

**Current test:**
```python
def test_word_budget_respected(self, tmp_path):
    """Draft must stay within word budget (±20%)."""
    # ... test expects ValueError when word_count > budget * 1.2
```

**New test:**
```python
def test_guardrail_enforced(self, tmp_path):
    """Draft must stay within absolute maximum guardrail."""
    # Mock response with word_count > absolute_maximum
    # Expect ValueError with "exceeds absolute maximum" message

def test_guidance_not_hard_limit(self, tmp_path):
    """Draft can exceed target guidance without error."""
    # Mock response with word_count = budget * 1.5
    # Expect: no error, just informational logging
    # Verify: draft written successfully
```

**Tests to keep:**
- Token ceiling enforcement (16384 output tokens)
- Document-level budget tracking
- Budget exceeded detection (BudgetTracker)

**Tests to remove/modify:**
- Hard word budget compliance tests (no longer enforced)

---

## Acceptance Criteria

### Must Pass

1. **Guardrail enforcement:**
   - [ ] Sections exceeding 4x budget or 2000 words raise ValueError
   - [ ] Error message clearly distinguishes guidance vs guardrail

2. **Guidance flexibility:**
   - [ ] Sections at 1.5x target guidance complete successfully
   - [ ] Informational logging shows when guidance exceeded
   - [ ] No errors for reasonable length variations

3. **Content preservation:**
   - [ ] ZLB test with new system preserves "discontinuous needs care" explanation
   - [ ] retention_vs_source improves from 77.8% toward 95%+

4. **Cost control:**
   - [ ] No sections exceed 2000 words
   - [ ] Typical sections stay 1x-1.5x guidance (monitored via logging)

5. **Test suite:**
   - [ ] All 228 existing tests pass
   - [ ] New guardrail tests pass
   - [ ] No regressions in budget tracking

### Nice to Have

- [ ] ZLB document reaches 95%+ retention with new system
- [ ] Monitoring shows most sections within 0.8x-1.5x guidance
- [ ] User feedback confirms important content no longer deleted

---

## Testing Strategy

### Phase 1: Unit Tests
```bash
# Update and run budget enforcement tests
python -m pytest tests/test_budget_enforcement.py -v

# All other tests should still pass
python -m pytest tests/ -q
```

### Phase 2: Integration Test - Small Document
```bash
# Test on small synthetic document first
python -m humanvoice.commands.pipeline_command \
  fixtures/synthetic/large_report/snapshot \
  --brief fixtures/briefs/large_synthetic_report.json
  
# Check:
# - No sections exceed guardrail
# - Sections vary reasonably around guidance
# - retention_vs_source high
```

### Phase 3: Validation - ZLB Document
```bash
# Re-run ZLB pipeline with new system
cd /tmp/zlb_test_2026-09-10
python -m humanvoice.commands.init_command source brief.json snapshot
python -m humanvoice.commands.pipeline_command snapshot --brief brief.json

# Check:
# - "discontinuous needs care" explanation preserved
# - retention_vs_source improved (target: 90%+)
# - No guardrail breaches
# - Section lengths reasonable
```

### Phase 4: Cost Analysis
```bash
# Compare token usage
# Old system (ZLB): ~80k tokens, 77.8% retention
# New system (ZLB): expect ~100-120k tokens, 90%+ retention
# Trade-off: 25-50% more tokens for 12%+ better retention
```

---

## Risk Analysis

### Risk 1: Token Cost Increase
**Likelihood:** High  
**Impact:** Medium  
**Mitigation:**
- 4x/2000 guardrail prevents runaway costs
- Document-level budget tracking still active
- Most sections won't use full headroom
- Trade-off acceptable: quality over strict budget

**Expected cost increase:** 25-50% for documents like ZLB

### Risk 2: Some Sections Hit Guardrail
**Likelihood:** Low  
**Impact:** Low  
**Mitigation:**
- Guardrail at 4x/2000 is very generous
- If hit, indicates planning issue (section too large)
- Error message suggests splitting
- Planner can be improved in Phase 2

**Fallback:** Manually split large sections in brief

### Risk 3: Model Ignores Guidance, Writes Too Long
**Likelihood:** Low  
**Impact:** Low  
**Mitigation:**
- Prompt emphasizes guidance is for "reasonable brevity"
- Shows example lengths (0.8x-1.3x)
- Most models respect stylistic guidance
- Guardrail catches extreme cases

**Monitoring:** Log length distributions after deployment

### Risk 4: Regression in Existing Behavior
**Likelihood:** Low  
**Impact:** Medium  
**Mitigation:**
- All existing tests must pass
- Small document test before ZLB
- Changes are surgical (prompt + validation)
- Core drafting logic unchanged

---

## Rollback Plan

If the change causes problems:

1. **Immediate rollback:**
   ```bash
   git revert <commit-hash>
   ```

2. **Temporary workaround:**
   - Restore hard budget checks in draft_command.py line 817
   - Keep improved prompt language (helps even with hard limits)

3. **Partial rollback:**
   - Keep 2x guardrail instead of 4x (more conservative)
   - Keep informational logging
   - Tighten guardrail if needed

---

## Implementation Order

### Step 1: Update Draft Command Prompt ✅ Ready
**File:** `src/humanvoice/commands/draft_command.py`  
**Lines:** 378-420 (prompt building)  
**Changes:** Add target guidance language, guardrail explanation

### Step 2: Update Word Budget Validation ✅ Ready
**File:** `src/humanvoice/commands/draft_command.py`  
**Lines:** 817-821 (validation logic)  
**Changes:** Replace hard limit with guardrail check, add logging

### Step 3: Update Tests ✅ Ready
**File:** `tests/test_budget_enforcement.py`  
**Changes:** Remove hard limit tests, add guardrail tests, add guidance flexibility tests

### Step 4: Run Test Suite ⏳ Pending
**Command:** `python -m pytest tests/ -v`  
**Expected:** All 228 tests pass with new tests added

### Step 5: Small Document Test ⏳ Pending
**Document:** `fixtures/synthetic/large_report`  
**Goal:** Validate behavior on known document

### Step 6: ZLB Validation Test ⏳ Pending
**Document:** ZLB survey (3368 lines)  
**Goal:** Verify content preservation improvement

### Step 7: Commit & Document ⏳ Pending
**Commits:**
1. Code changes + tests
2. Test results documentation
3. Update remediation plan

---

## Success Metrics

**Before (Hard Budgets):**
- ZLB retention_vs_source: 77.8%
- Sections failing: 4 register violations + 1 truncation
- Important content deleted: "discontinuous needs care" explanation
- User feedback: "Important point deleted, should be improved not removed"

**After (Guidance + Guardrails):**
- ZLB retention_vs_source: Target 90%+ (improve by 12+ percentage points)
- Important content preserved: Foundational explanations kept
- Section failures: Only genuine issues, not budget compliance
- User feedback: Content preservation acceptable

**Cost trade-off:**
- Token increase: 25-50% (acceptable for 12%+ better retention)
- Quality improvement: Major (preserves important content)

---

## Future Enhancements (Post-v1.2)

### Phase 2: Document-Level Reading Time Budget
- Add `total_reading_time` gate based on brief.time_available_minutes
- Per-section flexibility, document-level constraint
- Timeline: 2-3 weeks post-v1.2

### Phase 3: Two-Pass Drafting
- Pass 1: Expansion draft (generous, thorough)
- Pass 2: Quality-preserving trimming
- Preserves "repetition with variation" (claudecodex policies)
- Timeline: 4-6 weeks post-v1.2

### Phase 4: Non-Uniform Compression
- Content-first drafting (no budgets)
- Measure actual needs
- Apply compression where safe, keep foundational content detailed
- Timeline: 2-3 months post-v1.2

---

## Related Documents

- [Budget Management Remediation Plan](budget_management_remediation_2026-09-09.md) - Phase 3 planning
- [ZLB Test Findings](../zlb_test_findings_2026-09-09.md) - Content deletion evidence
- [ZLB Issues Fix Plan](zlb_issues_fix_plan_2026-09-09.md) - Register/truncation fixes
- `~/workspace/claudecodex/policies` - Repetition with variation principles

---

## Approval

**Ready for execution:** YES  

**Rationale:**
- Fixes demonstrated content deletion problem
- Maintains cost control via guardrails
- Aligns with quality-first principles
- Low risk, high reward
- Surgical changes, comprehensive testing plan

**Estimated effort:** 2-3 hours (code changes + testing)  
**Estimated impact:** Major improvement in content preservation

---

**Prepared by:** Claude Opus 5  
**Reviewed by:** Amit Flores  
**Status:** Awaiting execution approval
