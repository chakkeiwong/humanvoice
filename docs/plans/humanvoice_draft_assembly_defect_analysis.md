# Humanvoice Draft/Assembly Defect Analysis
## Date: 2026-08-30
## Case: ZLB HMC Survey (109 equations → 4 equations)

## The Defect

The `hv draft` command produced 7 sections totaling 6,976 words from a 21,276-word source, but **dropped 105 of 109 equations** (96% loss). The `hv release` command's `protected_correspondence` gate reported "pass" despite this catastrophic loss.

## Root Causes

### 1. Evidence Truncation (3,000 chars = 1.8% of source)
**Location:** `src/humanvoice/commands/draft_command.py:122`
```python
{evidence_content[:3000]}
```

**Impact:**
- Source: 169,097 characters
- Window shown to model: 3,000 characters (1.8%)
- Equations in window: 0 of 109
- Model generates from training, not from source

**DynareMCP parallel:** Same pattern as "PDF text treated as equation evidence" (failure #4 in remedy ledger)

### 2. Fail-Open Gate Design
**Location:** `src/humanvoice/commands/release_command.py` - `check_protected_manifest_correspondence()`

**Behavior:**
```python
if not protected_manifests_exist:
    return None  # PASS (should BLOCK)
```

**Impact:** No protected manifests → gate passes → 105 missing equations unreported

**DynareMCP parallel:** "Blocked dossier treated as endpoint" (failure #17) - gates that should enforce substance don't

### 3. Draft Command Design Flaw
**The core mistake:** Draft treats the **entire source** as evidence for **one section**.

**What happens:**
1. User: "draft section 2 of 7"
2. System loads entire 169KB source as "evidence"
3. System truncates to 3KB
4. Model sees only preamble + abstract
5. Model writes plausible prose about "Reflection Methods" without seeing any reflection equations
6. System declares success

**What should happen:**
1. User: "draft section 2 of 7"
2. System locates section 2 boundaries in source
3. System loads section 2 content (with upstream dependencies)
4. Model sees actual section 2 equations and derivations
5. Model revises section 2
6. System verifies protected objects preserved

### 4. Blueprint Mismatch
**Blueprint assumes:** 7-section restructure for a 5,000-word decision document
**Draft command assumes:** Replace entire source with 7 new sections
**Reality:** Neither is happening - model invents 7 disconnected sections

**DynareMCP parallel:** "Foundation spine missing before thesis synthesis" (failure #29)

## Design Lessons From DynareMCP

### Lesson 1: Foundation-First
From remedy ledger #29:
> "The missing first move was what a junior postdoc would normally do before studying project variants: find the closest standard model with derivations and code, learn its notation and equations, reproduce or cite the baseline, then study deviations."

**Applied to humanvoice:**
- Before drafting section N, model must see canonical equations section N depends on
- Before assembly, verify that assembled version covers same protected objects as source
- Before release, block if protected correspondence drops >10%

### Lesson 2: Gates Must Enforce Substance
From remedy ledger #17:
> "Blocked dossier equals failed thesis gate (corrected in notes; previous final artifact remains inadequate)"

**Applied to humanvoice:**
- `protected_correspondence` should BLOCK when no manifests exist, not PASS
- Assembly should generate protected manifest and compare counts
- Release should enforce: |assembled_equations - source_equations| < threshold

### Lesson 3: Evidence Must Match Task
From remedy ledger #4:
> "PDF text treated as equation evidence -> Rendered source witnesses and source packets"

**Applied to humanvoice:**
- Draft section N needs section N evidence, not entire document
- Evidence window must contain the equations the section discusses
- If evidence > context budget, chunk by section, not truncate blindly

### Lesson 4: Honest Failure ≠ Valid Stop
From remedy ledger #28:
> "Agent could truthfully say the artifact failed and then stop working. This is better than false success, but still wrong when the user has asked for an improved artifact."

**Applied to humanvoice:**
- Draft that drops equations should trigger repair loop, not succeed
- Assembly that loses protected objects should abstain, not pass
- Release should present losses to user with repair options

## The Correct Product Design

### Architecture: Two Distinct Modes

#### Mode 1: Revision (Section-Level)
**Use case:** Revise section N of existing document
**Evidence:** Section N + dependencies (equations, labels it references)
**Output:** Revised section N
**Verification:** Protected objects in section N preserved or explicitly changed
**Assembly:** Replace section N in source, keep rest intact

#### Mode 2: Restructure (Document-Level)
**Use case:** Rewrite entire document for different reader/purpose
**Evidence:** Entire source + brief with restructure rationale
**Output:** New document structure via blueprint
**Verification:** All protected objects from source either included or explicitly marked "not relevant to new brief"
**Assembly:** Build new document, track correspondence to source

### Current Implementation: Neither Mode
**What it tries to do:** Mode 2 (restructure)
**What it actually does:** Mode 1 logic (section-by-section) with Mode 2 assumptions (replace everything)
**Result:** Hybrid that loses content

## Proposed Fix Strategy

### Fix 1: Remove Truncation
```python
# BEFORE (draft_command.py:122)
{evidence_content[:3000]}

# AFTER
{evidence_content}  # or implement smart chunking
```

**Trade-off:** May exceed context window for large documents
**Mitigation:** Chunk by section, or use structured evidence with equation extraction

### Fix 2: Fix Fail-Open Gates
```python
# BEFORE (release_command.py)
def check_protected_manifest_correspondence(snapshot_dir: Path) -> Optional[dict]:
    if not manifests:
        return None  # PASS
    ...

# AFTER
def check_protected_manifest_correspondence(snapshot_dir: Path) -> Optional[dict]:
    if not manifests:
        return {
            "reason": "no_protected_manifests",
            "detail": "Cannot verify correspondence without protected manifests"
        }  # BLOCK
    ...
```

### Fix 3: Add Protected Object Tracking to Draft
```python
# draft_command.py: after generating draft
source_objects = parse_protected_objects(evidence_content)
draft_objects = parse_protected_objects(draft_content)

# Compare counts
if len(draft_objects['equations']) < 0.9 * len(source_objects['equations']):
    return {
        "status": "abstention",
        "reason": "protected_object_loss",
        "source_equations": len(source_objects['equations']),
        "draft_equations": len(draft_objects['equations']),
        "detail": "Draft loses >10% of equations; likely evidence truncation"
    }
```

### Fix 4: Add Assembly Verification Gate
```python
# assemble_command.py: after assembly
source_manifest = parse_protected_objects(source_content)
assembled_manifest = parse_protected_objects(assembled_content)

losses = compare_manifests(source_manifest, assembled_manifest)
if losses['equations'] > 10:  # >10 equations lost
    abstain(f"Assembly lost {losses['equations']} equations; review sections")
```

### Fix 5: Make Mode Explicit
Add `--mode` flag to draft command:
```bash
# Mode 1: Revise section (default)
hv draft --mode=revise --section=2 ...
# Loads section 2 + dependencies only

# Mode 2: Restructure
hv draft --mode=restructure --section=2 ...
# Loads entire source as context for section 2 of new structure
```

## Testing Plan

### Test 1: Same Document, Fixed Code
1. Fix evidence truncation
2. Fix fail-open gates
3. Add protected object tracking
4. Re-run on ZLB HMC survey
5. **Success criterion:** Assembled document has ≥100 equations (vs. current 4)

### Test 2: Smaller Document
1. Create 5-page test document with 20 equations
2. Run draft → assemble → release
3. **Success criterion:** All 20 equations preserved or explicitly marked

### Test 3: Intentional Loss
1. Create brief that says "remove all proofs, keep only main results"
2. Run draft with equations in proofs
3. **Success criterion:** Gate blocks with "equations removed per brief; confirm?"

## DynareMCP Acceptance Tests Applied

From remedy ledger #29, applied to humanvoice:

```text
✗ A draft that processes section N but lacks section N equations must fail as 
  `draft_without_section_evidence`.
  
✗ An assembly without protected manifest must fail as `assembly_without_correspondence_check`.

✗ A release that finds no protected manifests must block as `no_protected_manifests`, 
  not pass.

✗ A draft that loses >10% equations must not count as successful drafting.

✗ An evidence window without the equations the brief discusses must fail as 
  `evidence_window_mismatch`.
  
✗ Protected correspondence with zero manifests must fail as 
  `correspondence_check_without_baseline`, not pass.
```

**Current status:** All 6 tests FAIL

## Conclusion

The defect is not in assembly logic. Assembly correctly concatenated what draft produced. The defect is in:

1. **Draft evidence design** - shows model 1.8% of source with 0 equations
2. **Gate design** - fails open when verification inputs missing
3. **Product architecture** - hybrid mode that doesn't match either use case

The fix requires:
- Remove truncation or implement section-aware chunking
- Change all fail-open gates to fail-closed
- Add protected object tracking at draft, assembly, and release stages
- Make revision vs restructure mode explicit

**Estimated effort:** 1-2 days to fix + 1 day to test on same document

**Next step:** Implement Fix 1-4, test on ZLB HMC survey, measure equation preservation.
