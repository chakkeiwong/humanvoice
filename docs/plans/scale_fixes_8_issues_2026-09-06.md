# Scale Fixes: 8 Issues for Large Document Support

**Date**: 2026-09-06  
**Status**: Planning  
**Blocking**: v1.2 external release at scale (hundreds of pages)

## Problem Statement

Current toolchain cannot reliably produce documents at target scale (266-345 pages, 25k-145k words, 20-100+ units):

1. **ZLB benchmark (10.5k words, 5 sections)**: Section 2 truncated at ~4,160 output tokens, reported as "model abstained" due to missing truncation detection
2. **Bank marketing survey (145k words, 23 chapters)**: Largest chapter needs 6-7 units at observed ~2,400 word ceiling; one failure aborts entire pipeline with no resume
3. **Fail-open pattern continuation**: Assembly warns on latexdiff timeout but exits 0 with `blacklined_file: null`, repeating the v1.1 gate pattern

At 100 units and 95% per-unit reliability: 0.6% chance of clean run (1 success per 592 attempts). Tool is structurally unreachable at scale.

## Measured Baselines

- **Declared ceiling**: `max_output_tokens_per_unit: 2000` (inference_profile.json:53)
- **Observed ceiling**: Section 1 recorded 2,418 output tokens and succeeded; section 2 needed ~4,160 and truncated
- **Effective ceiling**: Likely 4096 (Claude API default), but `BudgetLedger` never imported into draft_command → budget block is documentation, not enforcement
- **Input overage**: Section 1 recorded 37,002 input tokens vs declared `max_input_tokens_per_unit: 12000` → 3x over
- **Test baseline**: 145 tests passing (pytest run 2026-09-06)

## 8 Issues (Ordered by Blocking Severity)

### Critical (Blocks ZLB Today, Blocks Everything at Scale)

#### 1. Detect Truncation
**File**: `src/humanvoice/model.py:370-380`  
**Current**: `stop_reason` read only on empty-content path (line 373), never on responses that arrive  
**Impact**: Truncation emerges as "Output failed schema validation: Expecting value: line 1 column 1 (char 0)" — indistinguishable from model refusal  
**Fix**: After line 374, add:
```python
if message.stop_reason == "max_tokens":
    raise RuntimeError(
        f"Model output truncated: hit {output_tokens} token ceiling. "
        f"Section needs decomposition or higher max_tokens. Message ID: {message.id}"
    )
```
**Test**: `test_truncation_detection.py` — mock message with `stop_reason="max_tokens"`, verify raises `RuntimeError` with diagnostic text, not schema validation error

---

#### 2. Partial-Tolerant Assembly
**File**: `src/humanvoice/commands/assemble_command.py:555-560`  
**Current**: Hard abstention (exit 2) if any section missing:
```python
if missing_sections:
    print("Abstention: Missing section drafts:", file=sys.stderr)
    for missing in missing_sections:
        print(f"  - {missing}", file=sys.stderr)
    return 2
```
**Impact**: 100-unit document with 1 failure → all-or-nothing, no incremental progress  
**Fix**: Replace abstention with gap records:
- Remove exit 2 block
- Add `gap_record` per missing section with `{"section_index": i, "title": title, "reason": "draft_not_found"}`
- Write gap manifest: `output_dir / "assembly_gaps.json"`
- Assembly exits 0 but emits warning: "Assembled with N gaps; release gate will block"
- Assembled document includes LaTeX comment at gap: `% MISSING: Section N — <title>`

**Contract change**: Assembly no longer guarantees completeness; release gate becomes the fail-closed point  
**Test**: `test_partial_assembly.py` — draft 3 of 5 sections, assemble, verify:
- Exit 0
- `assembly_gaps.json` exists with 2 entries
- Assembled .tex has `% MISSING:` comments
- Correspondence manifest records only the 3 present sections

---

#### 3. Resume Drafting
**File**: `src/humanvoice/commands/draft_command.py:475+`, `src/humanvoice/cli.py:63`  
**Current**: `--section` takes single required int, no multi-section or resume mode  
**Impact**: Manual orchestration per unit; failed unit requires full context reload  
**Fix**:
- Add `--missing` flag: drafts only sections without a valid draft in runs/
- Add `--all` flag: drafts all sections 0..N-1 sequentially, stops on first failure, exits with code indicating last successful index
- Add `--resume` flag: alias for `--missing`, clearer intent
- Keep `--section <int>` for single-unit mode
- Mutual exclusion: `--section` vs (`--missing` | `--all` | `--resume`)

**Implementation**:
```python
# In cli.py
draft_group = draft_parser.add_mutually_exclusive_group(required=True)
draft_group.add_argument('--section', type=int, help='Draft single section (0-based)')
draft_group.add_argument('--missing', action='store_true', help='Draft sections without valid drafts')
draft_group.add_argument('--all', action='store_true', help='Draft all sections sequentially')
draft_group.add_argument('--resume', action='store_true', help='Alias for --missing')

# In draft_command
def _find_existing_drafts(runs_dir, sections):
    """Return set of section indices with valid drafts."""
    pass

def cmd_draft_multi(args):
    """Multi-section drafting mode."""
    if args.resume or args.missing:
        indices = [i for i in range(len(sections)) if i not in existing]
    elif args.all:
        indices = range(len(sections))
    
    for i in indices:
        try:
            _draft_single_section(i, ...)
        except Exception as e:
            print(f"Failed at section {i}: {e}", file=sys.stderr)
            if args.all:
                return i  # Exit code = last successful index
            continue  # --missing keeps going
    return 0
```

**Test**: `test_resume_drafting.py`:
- Draft sections 0, 2, 4 manually
- Run `--missing`, verify only 1, 3 attempted
- Run `--all` with mock failure at section 2, verify exits after 1, returns code indicating progress

---

### High (Blocks Scale, ZLB Might Finish with Retries)

#### 4. Subsection Decomposition
**Files**: All blueprint/draft/assemble paths, schema changes  
**Current**: Blueprint section = one unit; largest chapters (16k words) need 6-7 units → all tracked as "section 11"  
**Impact**: Resume granularity too coarse, correspondence gates see one giant unit  
**Fix**: Two-level hierarchy — `chapter.subsections[]`, unit = subsection

**Schema changes**:
```python
PLAN_SCHEMA = {
    "blueprint": {
        "chapters": [  # was "sections"
            {
                "title": str,
                "purpose": str,
                "subsections": [  # NEW
                    {
                        "title": str,
                        "purpose": str,
                        "word_budget": int,  # 800-1200 target
                        "evidence_needed": [str],
                        "source_file": str,
                        "source_start_line": int,
                        "source_end_line": int
                    }
                ],
                "total_subsection_words": int  # chapter aggregate
            }
        ]
    }
}
```

**Plan prompt changes**:
- "Divide the document into N chapters based on..."
- "For each chapter, divide into subsections of 800-1200 words..."
- "A chapter's subsections must cover its full scope without overlap"

**Draft changes**:
- CLI: `--chapter <int> --subsection <int>`, or `--missing` across all (chapter, subsection) pairs
- Filename: `draft_ch{i}_sub{j}_{stem}.tex`
- Matching: by (chapter_idx, subsection_idx, title_stem)

**Assembly changes**:
- `_assemble_document(chapters: List[Chapter])` where `Chapter = {title, subsections: List[Subsection]}`
- Emit `\section{chapter.title}` then concatenate subsection LaTeX
- Gap records: `{chapter_index, subsection_index, title}`
- Correspondence: per-subsection, rolled up to chapter level for reporting

**Backward compat**: Detect legacy single-level blueprint (`"sections"` key), map to chapters with 1 subsection each  
**Test**: `test_subsection_decomposition.py`:
- Plan a 15k-word source into 3 chapters × 4 subsections
- Draft all 12 units
- Assemble, verify chapter structure reconstructed
- Draft 10/12, assemble, verify 2 gaps recorded at subsection granularity

---

#### 5. Raise Effective Ceiling & Enforce Budget
**Files**: `src/humanvoice/model.py:95,132`, `src/humanvoice/commands/draft_command.py:546+`, `security/inference_profile.json:53`  
**Current**: Declared 2000, observed 2418, effective ~4096, no enforcement  
**Impact**: Ceiling unknown → unit sizing guesswork; overages undetected → document-level budget never checked  

**Fix A: Verify Profile Loading**
- Add logging at `ModelConfig.from_profile()` line 132: `print(f"Loaded max_tokens={config.max_tokens} from profile", file=sys.stderr)`
- Run draft, confirm loaded value vs declared value
- If mismatch, trace why `profile.get("budget", {}).get("max_output_tokens_per_unit", cls.max_tokens)` returns default

**Fix B: Raise Ceiling**
- Update `inference_profile.json:53`: `max_output_tokens_per_unit: 8192` (2x largest observed need)
- Update `model.py:95`: `max_tokens: int = 8192` (class default)
- Rationale: Subsections target 800-1200 words → ~2000-3000 tokens at LaTeX density; 8192 gives 2.7-4x headroom

**Fix C: Wire BudgetLedger into Draft**
```python
# draft_command.py, after loading config
from humanvoice.model import BudgetTracker
budget = BudgetTracker(
    max_input=profile.get("budget", {}).get("max_document_input_tokens", 250000),
    max_output=profile.get("budget", {}).get("max_document_output_tokens", 50000)
)

# After each model.invoke():
budget.check_and_record(response.input_tokens, response.output_tokens)

# Write usage to runtime manifest
manifest["budget_usage"] = budget.get_usage()
```

**Fix D: Document-Level Gate**
- Pipeline loads all draft runtime manifests, sums `output_tokens`
- If > 50k, exit 5 with diagnostic: "Document exceeded output budget: {used}/{limit}"
- Guidance: "Reduce target word count, increase subsection count, or raise max_document_output_tokens with justification"

**Test**: `test_budget_enforcement.py` (extend existing):
- Mock 3 sections returning 1500, 1500, 5500 tokens → third call raises `BudgetExceeded`
- Verify budget usage written to manifest
- Verify pipeline aggregates and blocks at document level

---

#### 6. Remove JSON Wrapping
**Files**: `src/humanvoice/model.py:377,395-406`, `src/humanvoice/commands/draft_command.py` (write path), all DRAFT_SCHEMA consumers  
**Current**: Model emits `{"draft": {"latex": "\\section{...}\n\n..."}}`; extraction at line 377 unwraps it  
**Impact**: 30k-word document forces every backslash through JSON escaping; one truncation destroys whole unit, not just tail; fence regex is a failure surface  

**Fix**: Raw LaTeX output with sidecar metadata

**New output format**:
```
draft_ch1_sub2_title.tex         # raw LaTeX, no JSON
draft_ch1_sub2_title.meta.json   # {"word_count": 987, "citations_needed": [...], "abstention": null}
```

**Prompt changes**:
- Remove `"Respond in JSON matching this schema:"`
- Add: `"Respond with raw LaTeX only, no code fences, no JSON wrapper. Start with \\subsection or \\section and end after your last paragraph."`
- Metadata goes in a SECOND model call with zero-shot extraction:
  ```
  You just wrote this LaTeX draft:
  <draft>
  {latex_text}
  </draft>
  
  Extract metadata as JSON:
  {
    "word_count": <count words in the draft>,
    "citations_needed": ["author_year", ...],
    "abstention": null
  }
  ```

**Schema changes**:
- DRAFT_SCHEMA deleted (no longer used)
- Metadata schema: `{"word_count": int, "citations_needed": [str], "abstention": str | null}`
- Validation: word count within section budget ±20%, abstention null or has diagnostic

**Benefits**:
- Truncation costs only the tail of the subsection, not the whole unit
- No escaping overhead → smaller output
- Fence extraction surface gone
- Human-readable draft files (no JSON clutter)

**Risks**:
- Two API calls per unit (draft + metadata extraction)
- If metadata call fails, word count unknown → accept draft, warn, skip budget check for that unit

**Test**: `test_raw_latex_output.py`:
- Mock model returns raw LaTeX with no fences
- Verify `.tex` and `.meta.json` written separately
- Verify word count extracted correctly
- Mock truncated output (no closing brace), verify tail lost but rest preserved
- Assembly reads `.tex` directly, ignores `.meta.json`

---

### Medium (Performance/Cost, Not Blocking)

#### 7. Correspondence Storage Optimization
**Files**: `src/humanvoice/commands/assemble_command.py:402-406,421-424,445-454`, `src/humanvoice/commands/draft_command.py` (correspondence emit)  
**Current**: Manifests embed full `content` for every preserved/missing/added object:
```python
"preserved": [
    {"type": "equation", "hash": "a1b2c3", "content": "\\nabla \\log p(\\theta|y)"},
    ...
]
```
**Impact**: At 84 objects, 5 copies (source manifest + 5 draft manifests + assembly manifest + release manifest) → fine. At 5,000 objects in a 345-page doc → every correspondence read loads megabytes, gates become O(document²)  

**Fix**: Hash + offset index, content dereferenced on demand

**New manifest format**:
```json
{
  "preserved": ["a1b2c3d4", "e5f6g7h8", ...],
  "missing": ["i9j0k1l2"],
  "added": ["m3n4o5p6"]
}
```

**Offset index** (written once at init, read by all gates):
```json
// .humanvoice/protected_objects/source_index.json
{
  "objects": [
    {"hash": "a1b2c3d4", "type": "equation", "offset": 1523, "length": 28},
    {"hash": "e5f6g7h8", "type": "citation", "offset": 7834, "length": 15}
  ],
  "source_file": "source/source.tex",
  "source_hash": "f24a46138a183b7a..."
}
```

**Dereference helper**:
```python
def _load_object_content(index_path, hashes):
    """Load content for specific hashes from source via offset."""
    index = json.load(open(index_path))
    source_path = snapshot_dir / index["source_file"]
    source = source_path.read_text()
    
    lookup = {o["hash"]: o for o in index["objects"]}
    results = []
    for h in hashes:
        obj = lookup[h]
        content = source[obj["offset"]:obj["offset"]+obj["length"]]
        results.append({"hash": h, "type": obj["type"], "content": content})
    return results
```

**Migration**: Old manifests still readable (check for `content` key, fall back to hash-only)  
**Test**: `test_correspondence_index.py`:
- Init snapshot, verify `source_index.json` written
- Draft section, verify correspondence manifest uses hash-only
- Load missing objects via dereference helper, verify content matches
- Measure manifest size: hash-only vs full-content at 1000 objects

---

#### 8. Bounded Latexdiff
**Files**: `src/humanvoice/commands/assemble_command.py:249-286,594-620`  
**Current**: Single `latexdiff source.tex assembled.tex` with 60s timeout; failure prints warning, assembly exits 0 with `blacklined_file: null`  
**Impact**: 345-page diff takes >60s → silent failure, deliverable missing, repeats v1.1 fail-open pattern  

**Fix**: Per-chapter diff with scaled timeout, fail-closed

**Implementation**:
```python
def _generate_blacklined_per_chapter(
    original_chapters: List[Path],  # extracted from source
    assembled_chapters: List[Path],  # extracted from assembled
    output_dir: Path,
    timeout_per_chapter: int = 120
) -> Tuple[Optional[Path], List[str]]:
    """
    Generate per-chapter diffs, concatenate into single blacklined doc.
    
    Returns:
        (final_blacklined_path, errors)
    
    Errors list is empty on success, contains chapter names on failure.
    """
    chapter_diffs = []
    errors = []
    
    for i, (orig, asm) in enumerate(zip(original_chapters, assembled_chapters)):
        try:
            result = subprocess.run(
                ['latexdiff', str(orig), str(asm)],
                capture_output=True,
                timeout=timeout_per_chapter,
                text=True
            )
            if result.returncode == 0:
                chapter_diffs.append(result.stdout)
            else:
                errors.append(f"Chapter {i}: latexdiff exit {result.returncode}")
        except subprocess.TimeoutExpired:
            errors.append(f"Chapter {i}: timeout after {timeout_per_chapter}s")
    
    if errors:
        return None, errors
    
    # Concatenate chapter diffs
    final_path = output_dir / "blacklined_comparison.tex"
    final_path.write_text("\n\n".join(chapter_diffs))
    return final_path, []
```

**Assembly changes**:
- If `_generate_blacklined_per_chapter` returns errors, exit 2 (abstention) instead of 0
- Rationale: blackline is a deliverable, not optional diagnostic
- Error message: "Abstention: Blackline generation failed for N chapters: {errors}"

**Chapter extraction**:
```python
def _extract_chapters(latex_doc: str) -> List[str]:
    """Split document at \\chapter or \\section boundaries."""
    # Regex: split on \chapter{...} or \section{...} keeping the delimiter
    pattern = r'(\\(?:chapter|section)\{[^}]+\})'
    parts = re.split(pattern, latex_doc)
    
    chapters = []
    for i in range(1, len(parts), 2):
        if i+1 < len(parts):
            chapters.append(parts[i] + parts[i+1])
    return chapters
```

**Timeout scaling**:
- 120s per chapter (2x current total)
- Scales linearly with chapter count, not document length
- 23-chapter doc → max 46 minutes (acceptable for hundreds of pages)

**Fail-closed verification**:
- Release gate checks `blacklined_file` not null
- If null and assembly exited 0 → release blocks with "blackline missing"

**Test**: `test_bounded_latexdiff.py`:
- Mock latexdiff timeout on chapter 3 of 5
- Verify assembly exits 2 with diagnostic listing chapter 3
- Mock all chapters succeed, verify concatenated output correct
- Verify release gate blocks when `blacklined_file: null`

---

## Implementation Order

**Phase 1: Critical (1-2 days)**
1. Truncation detection
2. Partial assembly
3. Resume drafting
- Goal: ZLB document finishable, all 5 sections to blackline

**Phase 2: High (3-5 days)**
4. Subsection decomposition (schema + plan + draft + assemble)
5. Budget ceiling + enforcement
6. Raw LaTeX output
- Goal: Bank marketing 345-page document draftable

**Phase 3: Medium (2-3 days)**
7. Correspondence optimization
8. Bounded latexdiff
- Goal: Performance at scale, fail-closed deliverable

**Total: 6-10 days** (1 developer, assuming test-first, no context thrashing)

## Testing Strategy

- **Test-first**: Write test, watch it fail, implement, watch it pass
- **Regression**: Run full suite after each fix (baseline: 145 passing)
- **Integration**: After Phase 1, run ZLB pipeline end-to-end
- **Scale**: After Phase 2, run bank marketing (23 chapters) in mock mode, measure:
  - Units attempted vs succeeded
  - Budget consumption
  - Resume effectiveness
  - Assembly gap handling

## Risk Mitigation

1. **Subsection decomposition backward compat**: Detect legacy blueprint, auto-promote to single-subsection chapters
2. **Raw LaTeX dual risk**: Two API calls per unit costs 2x. Mitigation: metadata extraction uses cheap model (Haiku) or local heuristic (word count via `len(re.findall(r'\w+', text))`)
3. **Partial assembly contract change**: Release gate becomes fail-closed point. Verify all existing gates check assembly_gaps.json
4. **Latexdiff fail-closed**: Long diffs may legitimately timeout. Provide `--skip-blackline` flag for draft review, require blackline only for external release

## Success Criteria

- [ ] ZLB 5-section document assembles with blackline, all gates pass
- [ ] Bank marketing 23-chapter mock run completes with resume, gaps handled
- [ ] Truncation surfaces diagnostic error, not schema failure
- [ ] Budget enforcement blocks at document level when exceeded
- [ ] All 145+ tests passing
- [ ] Correspondence manifest size at 1000 objects < 50KB (hash-only vs ~500KB full-content)
- [ ] Latexdiff timeout on 345-page doc exits 2, not 0

## Open Questions

1. **Effective ceiling verification**: Why did section 1 use 2418 tokens vs declared 2000? Profile loading bug or API override?
2. **Metadata extraction cost**: Two-call raw LaTeX vs one-call JSON — measure actual cost difference at 100 units
3. **Chapter vs section terminology**: Blueprint uses "section" currently; decomposition needs "chapter" + "subsection" — rename existing or add parallel?

## Plan Review (2026-09-06, post-drafting)

Reviewed against actual code. Five corrections to the plan above; the plan as first
drafted would have failed on three of them.

### R1. Missing Step 0: revert debug scaffolding
`git diff src/humanvoice/model.py` shows uncommitted changes from the misdiagnosed
session. They are **not** a fix:
- Adds four `DEBUG:` prints to stderr inside the validation path
- Calls `_extract_json_from_markdown` a **second** time at line 252, when
  `_invoke_api` already called it at line 377
- Widens the abstention string to carry both original and cleaned text

The regex at lines 395-402 already uses `\s*` on both sides of the fence, so the
"fix" the previous session was chasing was already present. The real defect was
truncation (Issue 1). **Revert this diff before any other work** — it is noise that
will confuse every subsequent test run.

### R2. Issue 6 was over-engineered — no second API call needed
The plan proposed a second model call to extract `word_count` and
`citations_needed`. Unnecessary: `assemble_command.py:544` already computes word
count locally with `len(re.findall(r'\w+', content))`. Citations are extractable by
the same regex machinery `protected_objects` already uses.

**Revised**: compute metadata locally, zero extra API calls. This removes the 2x
cost risk and the "metadata call fails" branch entirely. Risk section item 2 is void.

### R3. Issue 2 depends on a release gate that does not exist
The plan asserted "release gate becomes the fail-closed point" for assembly gaps.
Verified: `release_command.py` has **no** gap gate. Searching `assembly_gaps|gap`
returns only unrelated evidence/parsing gap checks (lines 337-413).

**Revised**: Issue 2 must *add* `check_assembly_gaps()` to `release_command` as a
never-except gate. Without it, partial assembly is a fail-open regression — exactly
the v1.1 pattern this repo already shipped once. Issue 2 is not complete until the
gate exists.

### R4. Issue 8 depends on a blackline gate that does not exist
Same shape. `release_command.py:746` records `"diff_available": <bool>` and
lines 727-732 copy the file only `if assembly_manifest.get("blacklined_file")`.
Nothing blocks on absence.

**Revised**: Issue 8 must *add* `check_blackline_present()` as a never-except gate,
with the `--skip-blackline` escape hatch recorded as an explicit exception rather
than a silent null.

### R5. Issue 3 must also patch the pipeline
`pipeline_command.py:594-606` returns on the first failing section. The plan named
`draft_command` and `cli` as edit targets but omitted this. Resume in `hv draft`
without resume in `hv pipeline` leaves the orchestrated path still all-or-nothing.

### Verified correct
- `stop_reason` is a real field on `anthropic.types.Message` (`model_fields`
  confirms; anthropic 0.42.0)
- `sys` already imported in `model.py:21` — no import needed for Issue 1
- Line references in Issues 1, 2, 5, 7, 8 all resolve to the code described
- Test baseline 145 passing, `test_budget_enforcement.py` already covers
  `BudgetTracker` in isolation; Issue 5 extends it to the wiring, not the class

### Revised order
**Step 0** — revert debug diff, commit clean baseline  
**Phase 1** — Issues 1, 2 (+ gap gate), 3 (+ pipeline)  
**Phase 2** — Issues 5, 6 (local metadata), 4  
**Phase 3** — Issues 7, 8 (+ blackline gate)

Issue 5 moves ahead of 4: knowing the true ceiling determines subsection word
budgets, so decomposing first would size units against a guess.

## Approval

Reviewed by: Claude (self-review against code, 2026-09-06)  
Approved: proceeding per user instruction "execute"  
Start date: 2026-09-06
