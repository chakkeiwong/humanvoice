# ZLB Test Issues - Fix Plan
**Date:** 2026-09-09  
**Status:** Draft  
**Priority:** Medium (post-v1.2 release)

## Executive Summary

The ZLB end-to-end test revealed three issues that prevented full pipeline completion:
1. Register violations (4 sections failed)
2. Output truncation (1 section exceeded 8192 token limit)
3. No checkpoint/resume capability

This plan outlines fixes for each issue with implementation approach and acceptance criteria.

---

## Issue 1: Register Violations (4 Sections Failed)

### Problem
Model generated first-person pronouns ("we", "our") despite explicit instructions to use third-person technical register.

**Evidence:**
- 4 sections failed with: "Register violation: first_person usage found"
- Prompt explicitly states: "Write in third-person technical register (no "I", "we", "our" unless quoting evidence)"
- System prompt says: "Maintain third-person technical register unless evidence itself is first-person data"

### Root Cause Analysis

**Hypothesis 1: Source Material Contains First-Person Text**
The ZLB survey paper likely contains first-person constructions in the original:
- Academic papers often use "we" to describe methodology
- "We derive...", "We show...", "We survey..." are common in technical writing
- Model may be mimicking the source material's style despite instructions

**Hypothesis 2: Insufficient Constraint Strength**
The register constraint is stated but not emphasized strongly enough:
- Mentioned once in requirements list alongside other requirements
- May be overshadowed by "preserve protected objects" and "stay within budget"
- No examples showing good vs bad register usage

**Hypothesis 3: Context Window Dilution**
For large sections with extensive evidence:
- Evidence content may be 3-5k tokens
- Protected objects list can be 1-2k tokens
- Register instruction is only ~20 tokens
- Model attention may drift toward evidence style

### Proposed Fix

**Option A: Strengthen Register Constraint (Recommended)**

1. **Move register constraint to system prompt (higher priority)**
   ```python
   system_prompt = (
       "You are a technical writing assistant. "
       "CRITICAL CONSTRAINT: Always write in third-person technical register. "
       "Never use first-person pronouns (I, we, our, my, me, us) in your prose. "
       "Generate LaTeX for the specified section using the evidence provided. "
       "Respond with valid JSON matching the requested schema."
   )
   ```

2. **Add explicit negative examples in prompt**
   ```python
   prompt += """
   **Register Requirements (CRITICAL):**
   - Use third-person: "The paper demonstrates..." NOT "We demonstrate..."
   - Use passive voice: "It is shown..." NOT "We show..."
   - Use neutral constructions: "This section derives..." NOT "We derive..."
   - First-person is ONLY allowed when directly quoting evidence text
   
   Examples:
   ✗ BAD: "We survey the HMC methods..."
   ✓ GOOD: "This survey covers the HMC methods..."
   
   ✗ BAD: "We derive the kernel..."
   ✓ GOOD: "The kernel is derived as follows..."
   """
   ```

3. **Add register check to schema validation**
   - Currently: register check happens post-generation at line 822
   - Improvement: Include in system prompt so model self-corrects before outputting

**Option B: Allow First-Person in Academic Genre**

Academic surveys often use "we" legitimately. Consider:
- Add `genre` field to brief (already exists: "academic survey")
- Allow first-person for `genre == "academic survey"` or `"academic paper"`
- Modify check: `if brief.get("genre") not in ["academic survey", "academic paper"]:`

**Recommendation:** Try Option A first (strengthen constraint). If register violations persist, consider Option B (genre-based exceptions). For ZLB specifically, Option B may be more appropriate since academic writing conventions differ from technical memos.

---

## Issue 2: Output Truncation (1 Section Exceeded 8192 Tokens)

### Problem
One section exceeded the 8192 token output ceiling, causing truncation and draft failure.

**Evidence:**
- Section failed with: "Output truncated at 8192 tokens (ceiling was 8192)"
- ZLB has 49 subsections in blueprint (from 42 source subsections)
- Even with fine-grained planning, some subsections are inherently large

### Root Cause
The subsection granularity is better than before (09ccee1), but:
- Some source subsections are naturally large (500-700 words → 1500-2500 tokens)
- With LaTeX overhead (WORDS_TO_TOKENS = 3.5), a 700-word section → ~2450 tokens
- With JSON envelope, evidence context, and prompt: easily exceeds 8192 token output
- The 8192 ceiling is set by inference_profile.json and is hard-coded

### Proposed Fix

**Option A: Increase Output Ceiling (Short-term)**

1. **Raise profile limit to 16384 tokens**
   ```json
   // inference_profile.json
   {
     "max_output_tokens_per_unit": 16384,  // Was 8192
   }
   ```

2. **Update draft_command.py line 83**
   ```python
   return 16384  # Matches inference_profile.json max_output_tokens_per_unit
   ```

**Pros:** Simple, immediate fix  
**Cons:** Doubles max token cost per section, doesn't solve root cause

**Option B: Auto-Split Large Subsections (Medium-term)**

1. **Add subsection size estimation to planner**
   ```python
   def _estimate_subsection_tokens(subsection: Dict, source_text: str) -> int:
       """Estimate output tokens for a subsection based on source length."""
       word_budget = subsection.get("word_budget", 500)
       # Estimate: word_budget * 1.2 variance * 3.5 WORDS_TO_TOKENS
       return int(word_budget * 1.2 * 3.5)
   ```

2. **Auto-split subsections exceeding threshold**
   ```python
   MAX_SUBSECTION_TOKENS = 6000  # Leave headroom below 8192
   
   if _estimate_subsection_tokens(subsection, source) > MAX_SUBSECTION_TOKENS:
       # Split into 2-3 smaller subsections
       split_subsections = _split_large_subsection(subsection)
       blueprint["subsections"].extend(split_subsections)
   ```

**Pros:** Prevents issue at planning stage, surgical fix  
**Cons:** More complex, requires planner changes

**Option C: Cascade Truncation Handling (Long-term)**

1. **Detect truncation early**
   ```python
   if latex_response.truncated:
       # Check if we're within 95% of budget target
       if word_count >= word_budget * 0.95:
           # Accept as "close enough", flag for repair
           warnings.append("truncated_but_near_target")
       else:
           # True failure: insufficient output
           raise ValueError(f"Output truncated with only {word_count} words")
   ```

2. **Add continuation strategy**
   - If truncated but content is coherent, accept the draft
   - Repair stage can request expansion if needed
   - Better than hard-failing and losing partial work

**Recommendation:** 
- **Short-term (v1.2):** Option A - Increase ceiling to 16384 tokens
- **Medium-term (post-v1.2):** Option B - Auto-split in planner
- **Long-term (Phase 3):** Option C - Graceful truncation handling

---

## Issue 3: No Checkpoint/Resume (Phase 3)

### Problem
Pipeline completed 9/49 sections then failed. No way to resume from section 9.
- Wasted 52k tokens on completed sections
- Must restart from beginning
- Same failures will occur again on retry

### Impact
This is the **most critical** usability issue. Without checkpoint/resume:
- Large documents (40+ sections) are impractical
- Any mid-pipeline failure wastes all prior work
- Budget exhaustion mid-document has no recovery path
- Users cannot split work across sessions

### Proposed Fix (Already Defined in Phase 3)

**Implementation Approach:**

1. **Add checkpoint save after every N sections**
   ```python
   # pipeline_command.py, in draft loop
   CHECKPOINT_INTERVAL = 10  # Configurable
   
   if (len(state.section_drafts) % CHECKPOINT_INTERVAL) == 0:
       _save_checkpoint(state, output_dir)
       print(f"Checkpoint saved: {len(state.section_drafts)}/{len(sections)} sections complete",
             file=sys.stderr)
   ```

2. **Checkpoint manifest structure**
   ```json
   {
     "checkpoint_version": "1.0",
     "run_id": "run-20260909-123456",
     "snapshot_dir": "/path/to/snapshot",
     "blueprint_path": "/path/to/blueprint.json",
     "completed_sections": [0, 1, 2, 3, 4, 5, 6, 7, 8],
     "failed_sections": [9, 11],
     "section_drafts": [
       {"index": 0, "path": "...", "repaired": false},
       ...
     ],
     "tokens_consumed": 52609,
     "timestamp": "2026-09-09T12:34:56Z"
   }
   ```

3. **Add --resume flag**
   ```python
   # pipeline_command.py
   parser.add_argument('--resume', type=str, help='Resume from checkpoint run_id')
   
   if args.resume:
       checkpoint = _load_checkpoint(snapshot_dir, args.resume)
       state = PipelineState.from_checkpoint(checkpoint)
       sections_to_draft = [i for i in range(len(sections)) 
                           if i not in checkpoint["completed_sections"]]
   ```

4. **Progress reporting**
   ```python
   print(f"Progress: {completed}/{total} sections ({pct:.0%}), "
         f"~{remaining_tokens:,} tokens remaining",
         file=sys.stderr)
   ```

**Acceptance Criteria:**
- [ ] Checkpoint saved every 10 sections (or after each section if < 20 sections total)
- [ ] `hv pipeline --resume <run_id>` skips completed sections
- [ ] Resume preserves all state (blueprints, preflights, correspondence)
- [ ] Progress indicator shows completion percentage and estimated remaining tokens
- [ ] Failed sections recorded and skipped on resume
- [ ] Works with both --section and full pipeline modes

**Timeline:** 2-3 weeks (part of Phase 3 work)

---

## Implementation Priority

### Immediate (Before v1.2 Release)
- **Issue 2 - Option A:** Increase output ceiling to 16384 tokens
  - Risk: Low
  - Effort: 5 minutes (one-line change)
  - Impact: Unblocks large subsections

### Post-v1.2 (Next 2-4 weeks)
1. **Issue 1 - Option A:** Strengthen register constraints
   - Risk: Medium (might not fully solve)
   - Effort: 1 day (prompt engineering + testing)
   - Impact: Reduces drafting failures by 4-8 sections per document

2. **Issue 1 - Option B (if A fails):** Genre-based first-person allowance
   - Risk: Low
   - Effort: 2 hours (add genre check)
   - Impact: Allows legitimate academic voice

3. **Issue 2 - Option B:** Auto-split large subsections in planner
   - Risk: Medium (requires planning logic changes)
   - Effort: 3-5 days
   - Impact: Prevents truncation at root cause

### Phase 3 (3-4 weeks)
- **Issue 3:** Checkpoint/resume system (full implementation)
  - Risk: Low (well-understood problem)
  - Effort: 2-3 weeks
  - Impact: Makes large documents practical

---

## Testing Strategy

### For Register Violations
1. Extract sections 1, 2, 7, 9 from ZLB (the ones that failed)
2. Re-run with strengthened prompt
3. Measure: violations per section before/after
4. Success: < 1 violation per 10 sections

### For Output Truncation
1. Test with ceiling = 16384
2. Re-run ZLB full pipeline
3. Measure: truncation failures before/after
4. Success: 0 truncation failures

### For Checkpoint/Resume
1. Run ZLB pipeline, kill after 10 sections
2. Resume with `--resume <run_id>`
3. Verify: skips sections 0-9, starts at section 10
4. Success: completes remaining 39 sections without re-drafting first 10

---

## Risk Assessment

### Issue 1 (Register)
- **Risk if not fixed:** 8-15% of sections fail in academic documents
- **Workaround:** Manual editing of failed sections
- **Severity:** Medium (annoying but not blocking)

### Issue 2 (Truncation)
- **Risk if not fixed:** 2-5% of subsections fail in large documents
- **Workaround:** Manual splitting of large subsections
- **Severity:** Medium-High (blocks specific sections)

### Issue 3 (Checkpoint)
- **Risk if not fixed:** Large documents (40+ sections) impractical due to budget waste on retries
- **Workaround:** Break documents into smaller chunks manually
- **Severity:** **HIGH** (blocks large document use cases entirely)

---

## Recommendation

**For v1.2 Release:**
- ✅ Ship with Issue 2 Option A (increase ceiling to 16384) - 5 minute fix
- ✅ Document remaining issues in release notes
- ✅ Proceed with external release - issues are non-blocking

**Post-v1.2:**
- Week 1-2: Implement Issue 1 fixes (register constraints)
- Week 2-3: Implement Issue 2 Option B (auto-split)
- Week 3-6: Implement Issue 3 (checkpoint/resume - Phase 3)

---

## Files to Modify

### Immediate (v1.2)
- `inference_profile.json` - Increase max_output_tokens_per_unit: 16384
- `src/humanvoice/commands/draft_command.py` line 83 - Update ceiling return value

### Post-v1.2
- `src/humanvoice/commands/draft_command.py` - Strengthen register prompts
- `src/humanvoice/commands/plan_command.py` - Add subsection size estimation and auto-split
- `src/humanvoice/commands/pipeline_command.py` - Add checkpoint save/resume logic
- `tests/test_checkpoint_resume.py` - New test file
