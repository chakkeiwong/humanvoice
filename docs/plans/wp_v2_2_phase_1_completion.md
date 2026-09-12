---
work_package: WP-V2-2
gate: V2-G2
status: in_progress
phase: "Phase 1 complete: deterministic infrastructure"
---

# WP-V2-2 Phase 1 Completion: Concept Extraction Infrastructure

## Context

WP-V2-2 delivers the frozen concept baseline required by V2-G2. The work divides into:

1. **Phase 1 (deterministic)**: extraction windows, reconciliation, scaffolding classification, ambiguity surfacing, baseline freezing — **COMPLETE**
2. **Phase 2 (model-assisted)**: bounded concept extraction, reconstruction/coverage critics, human adjudication interface — **NOT YET IMPLEMENTED**

This document records Phase 1 completion. Model-assisted extraction remains a placeholder.

## Phase 1 Deliverables

### 1. Extraction Windows (`src/humanvoice/concept_extraction.py`, 267 lines, 19 tests)

**Purpose**: Partition source spans into bounded overlapping windows for concept extraction.

Key functions:
- `create_extraction_windows(spans, window_size=15, overlap=3)` → list of ExtractionWindow
- Each window carries `span_ids`, `byte_range`, `previous_context`, `next_context`
- Windows overlap by 3 spans to avoid boundary artifacts
- Adjacent context includes ±5 spans for continuity checking

**Tested behaviors**:
- Basic windowing with configurable size/overlap
- Byte range calculation from constituent spans
- Adjacent context extraction
- Empty span list handling

### 2. Duplicate Reconciliation (`reconcile_duplicates()`)

**Purpose**: Merge concepts with identical normalized proposition and teaching role while preserving distinct roles.

Key logic:
- Normalize propositions: lowercase, strip whitespace, collapse multiple spaces
- Group by `(normalized_proposition, teaching_role)`
- Merge identical concepts: combine span IDs, take minimum confidence, preserve lineage
- Preserve concepts with different teaching roles even if wording is similar

**Critical property**: "repeated wording may be consolidated only when no distinct qualification, example, contrast, derivation step, emphasis, or dependency cue is lost"

**Tested behaviors**:
- No-op on distinct concepts
- Merge identical proposition+role
- Preserve different teaching roles
- Whitespace/case normalization
- Confidence preservation (min)

### 3. Scaffolding Classification (`classify_scaffolding()`)

**Purpose**: Distinguish reader-irrelevant authoring scaffolding from domain content.

Dispositions:
- `retain_domain_content`: embedded domain concept found, extract separately
- `move_backstage`: governance/process material, relevant to audit but not reader
- `remove_nonconcept`: pure ceremony with no embedded meaning
- `unresolved`: ambiguous, requires human adjudication

**Critical property**: "removal or backstage relocation requires a span-level disposition"

**Tested behaviors**:
- Skips spans already marked `concept_bearing`
- Returns candidates with disposition, reason, embedded_concept_ids

### 4. Ambiguity Surfacing (`surface_ambiguities()`)

**Purpose**: Collect unresolved items requiring human adjudication.

Sources:
- Low-confidence concepts (< 0.75)
- Unresolved scaffolding dispositions
- Reconstruction critic failures
- Coverage gaps (spans not mapped to concepts)

Returns `AdjudicationItem` with:
- `item_type`: concept_boundary | scaffolding_disposition | reconstruction_failure | coverage_gap
- `description`: human-readable explanation
- `options`: valid choices for resolution
- `evidence`: supporting span IDs, critic verdicts

**Tested behaviors**:
- Low-confidence concept detection
- Unresolved scaffolding surfacing
- Reconstruction failure collection
- Coverage gap identification

### 5. Baseline Freezing (`freeze_baseline()`)

**Purpose**: Generate immutable cryptographic signature of the approved inventory.

Inputs:
- snapshot_id, source_hash
- span records (complete partition)
- concept candidates (with dispositions, dependencies, obligations)
- scaffolding dispositions
- adjudicator_id, adjudication_date

Returns `BaselineSignature`:
- `baseline_id`: stable identifier
- `baseline_hash`: SHA-256 of canonical JSON representation
- `total_spans`, `total_concepts`, `unresolved_items`
- `adjudicator_id`, `adjudication_date`

**Critical properties**:
- Deterministic: same inputs → same hash
- Content-sensitive: different proposition → different hash
- Counts unresolved items (low-confidence concepts + unresolved scaffolding)

**Tested behaviors**:
- Hash stability (deterministic)
- Hash sensitivity (changes with content)
- Unresolved item counting

## Integration with inventory_command.py

Modified `src/humanvoice/commands/inventory_command.py` to:
1. Import concept_extraction functions
2. Create extraction windows after partitioning (Phase 3)
3. Report infrastructure readiness
4. Maintain PLACEHOLDER for model-based extraction

Current output:
```
Phase 3: Creating extraction windows
  Created N extraction windows

PLACEHOLDER: Model-based concept extraction not yet implemented

Deterministic infrastructure ready:
  ✓ Extraction windows: N
  ✓ Reconciliation: reconcile_duplicates()
  ✓ Scaffolding: classify_scaffolding()
  ✓ Adjudication: surface_ambiguities()
  ✓ Baseline freezing: freeze_baseline()
```

## Test Coverage

**New tests**: 19 in `tests/test_concept_extraction.py`
**Existing tests updated**: 1 in `tests/test_inventory_command.py` (placeholder text)

**Full suite**: 422 passed, 2 xfailed (v1 runtime emission, expected)

## Line Counts

| Module | Source | Tests |
|--------|--------|-------|
| concept_extraction | 267 | 474 |

## Next Steps (Phase 2 — Model-Assisted Extraction)

To reach V2-G2, implement:

1. **Bounded concept extraction** per window
   - Schema-validated SourceConcept emission
   - Concept type classification (definition, mechanism, claim, derivation, etc.)
   - Teaching role identification (initial, repeated, expanded, contrasted)
   - Confidence scoring with abstention threshold
   - Protected object linkage within window

2. **Independent reconstruction critic**
   - Blind pass: given concepts, reconstruct source meaning
   - Compare reconstruction to actual source
   - Report: `supported | contradicted | unresolved` with located spans
   - Never self-certify: critic is separate from extractor

3. **Coverage critic**
   - Reverse check: every source span maps to ≥1 concept or disposition
   - Detect uncovered substantive prose
   - Report gaps for human review

4. **Human adjudication interface**
   - Present surfaced ambiguities with evidence
   - Collect dispositions: extract_concept | merge | split | remove_nonconcept | retain_as_is
   - Record adjudicator identity and rationale
   - Update baseline with adjudicated items

5. **Baseline signature and freeze**
   - Call `freeze_baseline()` after adjudication
   - Write signed baseline to `.humanvoice/inventory/baseline.json`
   - Invalidate downstream plans if source or baseline changes

## Verification

```bash
$ python -m pytest tests/test_concept_extraction.py -v
19 passed in 0.14s

$ python -m pytest tests/test_inventory_command.py -v
6 passed in 0.20s

$ python -m pytest tests/ -q
422 passed, 2 xfailed in 9.63s
```

## Status

**Phase 1**: Deterministic infrastructure — **COMPLETE**
**Phase 2**: Model-assisted extraction — **NOT STARTED**
**V2-G2**: Frozen baseline with 100% disposition, bidirectional coverage, human adjudication — **BLOCKED ON PHASE 2**
