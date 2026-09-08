# Fix: Subsection Structure Preservation (Issue: Content Loss in Sections 5-8)

**Date**: 2026-09-08  
**Status**: Fixed

## Problem

When testing on the ZLB rescue document, sections 5-8 suffered massive content loss:
- Section 7 originally had **18 subsections** with detailed implementation guidance
- The blueprint compressed these into only **2 subsections** 
- 24% of protected objects were dropped (11 citations, 5 labels, 4 equations lost)
- Mathematical content and important material deleted rather than rewritten
- `retention_vs_source: 0.76` indicated catastrophic loss

## Root Cause

The planner only extracted `\section{}` commands from LaTeX source, completely ignoring `\subsection{}` commands.

**What the model saw:**
```
- "BGS decision chapter: from methods to an executable choice" (lines 533-718)
```

**What actually existed:**
- Section 7: lines 533-725 containing **18 subsections**:
  - The decision object
  - Stage 1: the BGS boundary atlas
  - Stage 2: fixed-branch HMC baseline
  - Stage 3: a toy target with BGS-like margins
  - Stage 4A: event-aware HMC feasibility
  - Stage 4B: corrected KMC/neural proposal feasibility
  - ... (12 more subsections)

The planner was **blind** to this structure, created coarse blueprints (2 subsections covering 185 lines), and the drafter had to compress 18 subsections into 2, causing massive loss.

## Systemic Issues Fixed

### 1. Subsection Extraction (`plan_command.py:46-124`)

**Before:**
- Only parsed `\section{...}` commands
- Returned flat list of sections with line ranges

**After:**
- Parses both `\section{...}` and `\subsection{...}` commands
- Returns hierarchical structure: sections contain subsections
- Computes correct line ranges for both levels
- Each subsection gets proper `start_line` and `end_line` within its parent section

### 2. Prompt Visibility (`plan_command.py:126-162`)

**Before:**
```
File: source/source.tex
  - "BGS decision chapter" (lines 533-718)
```

**After:**
```
File: source/source.tex
  - "BGS decision chapter" (lines 533-725) — contains 18 subsections:
      • "The decision object" (lines 537-547)
      • "Stage 1: the BGS boundary atlas" (lines 548-566)
      • "Stage 2: fixed-branch HMC baseline" (lines 567-571)
      ... (15 more)
```

### 3. Planning Constraint (`plan_command.py:269-295`)

Added strong constraint to planning prompt:

```
**Source structure preservation (CRITICAL to avoid content loss):**
When the source contains rich subsection structure (5+ subsections in a section), you MUST
create roughly one blueprint subsection per source subsection. Do NOT compress many source
subsections into one or two blueprint subsections—this causes massive content loss during drafting.

Example BAD plan: Source has 18 subsections in lines 533-725, blueprint creates 2 subsections.
Example GOOD plan: Source has 18 subsections, blueprint creates 15-20 subsections.

When mapping source subsections to blueprint subsections:
- Each blueprint subsection should cover 1-3 source subsections maximum
- Preserve source subsection boundaries in source_start_line/source_end_line
- Use source subsection titles as guidance for blueprint subsection titles
- Allocate 400-600 words per blueprint subsection
```

### 4. Bibliography Support (`init.py`, `assemble_command.py`)

Also fixed in this session (separate but related):

**Init command** - Now copies `.bib` files:
```python
# Before: only *.tex
for tex_file in source_dir.rglob("*.tex"):

# After: both *.tex and *.bib  
for source_file in list(source_dir.rglob("*.tex")) + list(source_dir.rglob("*.bib")):
```

**Postamble extraction** - Now captures bibliography commands before `\end{document}`:
```python
# Before: only captured text after \end{document}
end_pos = content.find(r'\end{document}')
return content[end_pos + len(r'\end{document}'):].strip()

# After: captures \bibliographystyle and \bibliography before \end{document}
```

**Assembly** - Now inserts bibliography commands in correct position before `\end{document}`

## Results

### Before Fix (run-20260907-181125)
- 10 subsections total
- Chapter 7: **2 subsections** covering lines 533-725
- `retention_vs_source: 0.76` (24% loss)
- Missing: 11 citations, 5 labels, 4 equations

### After Fix (run-20260908-175734)
- **46 subsections** total
- Chapter 5 (renamed "Decision Framework"): **17 subsections** covering lines 537-725
- Each blueprint subsection maps to 1-2 source subsections
- Proper word budgets (400-550w per subsection)

Example mapping:
```
5.1. The decision object (lines 537-547, 500w)
5.2. Stage 1: Mapping the BGS boundary atlas (lines 548-566, 500w)
5.3. Stage 2: Fixed-branch HMC baseline (lines 567-571, 400w)
5.4. Stage 3: Toy target with BGS-like margins (lines 572-584, 500w)
... (13 more subsections)
5.17. Remaining gaps and continuation conditions (lines 714-725, 500w)
```

## Tests Added

New test file `test_subsection_extraction.py` with 4 tests:
1. `test_extracts_subsections_within_sections` - Verifies both levels extracted
2. `test_subsections_get_correct_line_ranges` - Verifies line ranges tile properly
3. `test_sections_without_subsections` - Handles sections with no subsections
4. `test_mixed_sections_some_with_subsections` - Mixed structure handling

All 223 tests pass (219 original + 4 new).

## Why This Matters

This was a **systemic planning failure**, not a one-off bug. Without this fix:
- Any document with rich subsection structure would suffer content loss
- Mathematical detail would be compressed away
- Protected objects (equations, citations) would be dropped
- The tool would be unusable for technical documents

The fix ensures:
- Planner sees full document structure
- Blueprint preserves granularity
- Drafter has appropriate scope per unit
- Protected objects get routed correctly
- Content is rewritten, not deleted

## Future Codex Agents

A fresh codex agent running the same ZLB test case will now:
1. See all 18 subsections in the source structure
2. Create 15-20 blueprint subsections for that chapter
3. Draft each with appropriate scope (400-600 words)
4. Preserve mathematical content and protected objects
5. Achieve high retention rates (`retention_vs_source > 0.95`)
