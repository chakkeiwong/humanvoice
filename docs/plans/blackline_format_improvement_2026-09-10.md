# Blackline Format Improvement Plan
**Date:** 2026-09-10  
**Status:** Ready for Execution  
**Priority:** HIGH (user feedback from ZLB review)

---

## Problem

**Current blackline issues:**
1. Only shows deletions (red strikethrough) - doesn't clearly show additions
2. Doesn't distinguish original vs changed text
3. Not intuitive - "not normally how blackline version is produced"

**User expectation:**
- Deletions clearly marked (red strikethrough) ✓ Already works
- Additions clearly marked (blue/green underline) ✗ Missing
- Easy to see what changed and what stayed
- Standard blackline format

---

## Root Cause

The current implementation uses `latexdiff` with default settings:
```python
subprocess.run([
    'latexdiff',
    '--exclude-textcmd=section,chapter,subsection',
    str(original_chunk),
    str(assembled_chunk)
])
```

**latexdiff default behavior:**
- Style: UNDERLINE
- Deletions: Red strikethrough (`\sout`)
- Additions: Blue wavy underline (`\uwave`)

**The problem:** The additions ARE marked, but may not be rendering properly or are hard to see in the current output.

---

## Solution

Use `latexdiff` with better markup style for clearer visual distinction.

### Option A: CTRADITIONAL Style (Recommended)
```bash
latexdiff --type=CTRADITIONAL \
  --exclude-textcmd=section,chapter,subsection \
  original.tex assembled.tex
```

**Output:**
- Deletions: Red strikethrough
- Additions: Blue text (not underlined, just colored)
- Cleaner, more readable

### Option B: CHANGEBAR Style
```bash
latexdiff --type=CHANGEBAR \
  --exclude-textcmd=section,chapter,subsection \
  original.tex assembled.tex
```

**Output:**
- Deletions: Red strikethrough
- Additions: Normal text with vertical bar in margin
- Very traditional blackline style

### Option C: COLOR Style
```bash
latexdiff --type=COLOR \
  --exclude-textcmd=section,chapter,subsection \
  original.tex assembled.tex
```

**Output:**
- Deletions: Red text
- Additions: Blue text
- No strikethrough/underline, just color

### Option D: Custom with explicit colors
```bash
latexdiff --type=UNDERLINE \
  --config="ADDTEXTCMD=blue,uwave" \
  --config="DELTEXTCMD=red,sout" \
  --exclude-textcmd=section,chapter,subsection \
  original.tex assembled.tex
```

**Output:**
- Full control over markup
- Can ensure additions are clearly visible

---

## Recommendation: Option A (CTRADITIONAL)

**Rationale:**
- Most readable for lengthy academic documents
- Deletions: red strikethrough (clearly removed)
- Additions: blue text (clearly added)
- No underlining/overlining that can clutter dense LaTeX
- Well-tested latexdiff style

---

## Implementation

### Change 1: Update latexdiff invocation

**File:** `src/humanvoice/commands/assemble_command.py`  
**Line:** 391-397

**Current:**
```python
result = subprocess.run(
    [
        'latexdiff',
        '--exclude-textcmd=section,chapter,subsection',
        str(original_chunk),
        str(assembled_chunk)
    ],
    capture_output=True,
    timeout=DIFF_TIMEOUT_PER_CHAPTER_SECONDS,
    text=True,
)
```

**New:**
```python
result = subprocess.run(
    [
        'latexdiff',
        '--type=CTRADITIONAL',
        '--exclude-textcmd=section,chapter,subsection',
        '--config="PICTUREENV=(?:picture|tikzpicture|pgfpicture|DIFnomarkup)[\w\d*@]*"',
        str(original_chunk),
        str(assembled_chunk)
    ],
    capture_output=True,
    timeout=DIFF_TIMEOUT_PER_CHAPTER_SECONDS,
    text=True,
)
```

**Additional options added:**
- `--type=CTRADITIONAL` - Better markup style
- `--config=PICTUREENV=...` - Protect tikz/pgf environments from markup

### Change 2: Document the markup in assembly manifest

**File:** `src/humanvoice/commands/assemble_command.py`  
**Line:** 963

**Current:**
```python
"diff_tool": diff_tool,
"diff_tool_version": diff_tool_version,
```

**New:**
```python
"diff_tool": diff_tool,
"diff_tool_version": diff_tool_version,
"diff_markup_style": "CTRADITIONAL",
"diff_markup_legend": {
    "deletions": "red strikethrough text",
    "additions": "blue text",
    "unchanged": "black text"
},
```

### Change 3: Add legend to compiled PDF

**Add comment at top of blacklined document:**
```latex
% Blackline Comparison: Original vs. Assembled
% 
% Legend:
%   - Red strikethrough text: DELETED from original
%   - Blue text: ADDED in assembled version
%   - Black text: UNCHANGED
```

This will appear as a comment in the .tex and can be rendered if desired.

---

## Testing Strategy

### Test 1: Visual Inspection
```bash
# Generate blackline with new style
cd /tmp/zlb_test_new
python -m humanvoice.commands.pipeline_command snapshot --brief brief.json

# Compile PDF
cd snapshot/.humanvoice/revisions/assembled
pdflatex blacklined_comparison.tex

# Check:
# - Deletions show red strikethrough
# - Additions show blue text (not just strikethrough for deletions)
# - Both are clearly distinguishable
```

### Test 2: Compare Original Output
```bash
# Check line 71-98 in ZLB (the "discontinuous needs care" section)
# Original: Full explanation present
# Old blackline: Showed as deleted (red strikethrough)
# New blackline: Should show what was kept vs deleted vs added
```

### Test 3: Small Document Validation
```bash
# Test on smaller document first
# Verify markup renders correctly
# Ensure no LaTeX compilation errors
```

---

## Acceptance Criteria

1. **Deletions clearly marked:**
   - [ ] Red strikethrough text for deleted content
   - [ ] Easy to identify what was removed

2. **Additions clearly marked:**
   - [ ] Blue text for added content
   - [ ] Visually distinct from deletions and unchanged text
   - [ ] Not just "absence of deletion marker"

3. **Unchanged text clearly marked:**
   - [ ] Black/normal text for unchanged content
   - [ ] No markup confusion

4. **Document compiles:**
   - [ ] blacklined_comparison.tex compiles to PDF without errors
   - [ ] All sections render correctly
   - [ ] Math environments protected from markup

5. **User comprehension:**
   - [ ] Reviewer can identify: what was deleted, what was added, what stayed
   - [ ] Format matches standard blackline expectations

---

## Risks

### Risk 1: CTRADITIONAL requires additional LaTeX packages
**Likelihood:** Low  
**Impact:** Medium  
**Mitigation:**
- CTRADITIONAL uses standard LaTeX color package
- Most LaTeX distributions include it by default
- Document requirements in error message if missing

### Risk 2: Blue text hard to read in print
**Likelihood:** Low  
**Impact:** Low  
**Mitigation:**
- Digital viewing (primary use case) - blue is clear
- For print, COLOR style can be substituted (red/black only)
- User can choose style preference

### Risk 3: Existing blacklines need regeneration
**Likelihood:** High  
**Impact:** Low  
**Mitigation:**
- Old blacklines still valid with old markup
- Only new assemblies use new markup
- Not a breaking change

---

## Rollback Plan

If CTRADITIONAL causes issues:

1. **Fallback to default UNDERLINE:**
   ```python
   # Remove --type=CTRADITIONAL
   # Keep other options
   ```

2. **Try CHANGEBAR:**
   ```python
   '--type=CHANGEBAR',
   ```

3. **Disable custom markup entirely:**
   ```python
   # Use latexdiff defaults
   ```

---

## Implementation Steps

### Step 1: Update latexdiff invocation ✅ Ready
**File:** `src/humanvoice/commands/assemble_command.py`  
**Line:** 391  
**Add:** `--type=CTRADITIONAL` flag

### Step 2: Update assembly manifest ✅ Ready
**File:** `src/humanvoice/commands/assemble_command.py`  
**Line:** 963  
**Add:** markup style and legend fields

### Step 3: Test on small document ⏳ Pending
**Goal:** Verify markup renders correctly

### Step 4: Test on ZLB document ⏳ Pending
**Goal:** Verify "discontinuous needs care" section shows clearly

### Step 5: Commit changes ⏳ Pending

---

## Expected Outcomes

**Before (current):**
- Deletions: Red strikethrough ✓
- Additions: Blue wavy underline (may not be clear)
- User confusion: "Only shows deletions"

**After (CTRADITIONAL):**
- Deletions: Red strikethrough ✓
- Additions: Blue text (clearly distinct) ✓
- Unchanged: Black text ✓
- User understanding: "I can see what was deleted, added, and kept" ✓

---

## Alternative: Add Visual Legend to PDF

If markup is still unclear, add a legend page at the beginning:

```latex
\section*{Blackline Legend}

This document compares the original source with the assembled version.

\begin{itemize}
\item \textcolor{red}{\sout{Red strikethrough text}} indicates content deleted from the original
\item \textcolor{blue}{Blue text} indicates content added in the assembled version
\item Normal black text indicates unchanged content
\end{itemize}

\newpage
```

**Implementation:** Insert after `\begin{document}` in blacklined output

---

## Related Issues

- User feedback: "This blacklined version is not good. It does not say which one is original, which is changed, and only say what is deleted."
- Current markup may be present but not visually clear
- Need better visual distinction between deleted/added/unchanged

---

## Success Metrics

**User can answer these questions by looking at blacklined PDF:**
1. What content was deleted from original? (Red strikethrough)
2. What content was added in assembled? (Blue text)
3. What content stayed the same? (Black text)
4. Which version is original vs assembled? (Document structure + legend)

**All four must be clearly answerable.**

---

**Ready for execution:** YES

**Estimated effort:** 30 minutes (code change + testing)  
**Estimated impact:** Major improvement in blackline usability
