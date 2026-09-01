# Gate 4 Implementation Documentation

## Overview

Gate 4 (protected correspondence) is a never-except release gate that verifies protected object preservation through the drafting and assembly pipeline. It enforces:

- **Draft threshold**: ≥95% of source protected objects preserved in drafts
- **Assembly threshold**: ≥99% of draft protected objects preserved in assembled document
- **Fail-closed design**: Absence of evidence blocks release (zero manifests → block, not pass)

## Architecture

### Three-Phase Correspondence Chain

```
Source → Drafts → Assembly
  |        |         |
  v        v         v
Source   Draft    Assembly
Manifest Manifests Manifest
```

Each phase tracks protected objects by cryptographic hash, enabling identity-preserving verification across transformations.

### Manifest Types

1. **Source Manifest** (`.humanvoice/protected_objects/source_manifest.json`)
   - Ground truth: all protected objects extracted from source
   - Emitted by: `init_command.py`
   - Schema: `{equations, citations, labels, displaymath, tables}` with hashes

2. **Draft Correspondence Manifests** (`.humanvoice/runs/<run-id>/draft_correspondence_section_*.json`)
   - Per-section tracking: which source objects were preserved/missing
   - Emitted by: `draft_command.py`
   - Schema: `{correspondence_to_source: {preserved, missing, added}, dispositions}`

3. **Assembly Correspondence Manifest** (`.humanvoice/revisions/assembled/assembly_correspondence_*.json`)
   - Aggregate tracking: draft objects → assembly preservation
   - Emitted by: `assemble_command.py`
   - Schema: `{retention_vs_drafts, retention_vs_source, correspondence_to_source, dispositions}`

## Implementation Components

### Section Line Bounds (plan_command.py)

**Purpose**: Enable draft_command to route source protected objects to the correct section.

**Implementation**:
```python
def _extract_section_structure(source_file: Path) -> list[dict]:
    """Extract section boundaries from LaTeX source.
    
    Returns: [{"title": str, "start_line": int, "end_line": int, "source_file": str}]
    
    Contract:
    - Sections tile the file without gaps: end_line[i] + 1 = start_line[i+1]
    - First section extends to line 1 (covers front matter: abstract, preamble)
    - Last section extends to EOF
    """
```

**Key fix**: Front matter (abstract, preamble equations/citations before first `\section{}`) must be included in first section's bounds, or those objects are orphaned and count as missing.

Test coverage: `tests/test_plan_section_bounds.py`

### Section Evidence Routing (draft_command.py)

**Purpose**: Filter source protected objects by section bounds before LLM sees them.

**Implementation**:
```python
def _prepare_section_evidence(section: dict, source_objects: dict) -> dict:
    """Filter protected objects to those within section's line bounds.
    
    Matching logic:
    - File match: object's source file == section's source_file
    - Line range match: section.source_start_line <= object.line <= section.source_end_line
    
    Returns: {equations: [...], citations: [...], labels: [...], ...}
    """
```

**Correctness**: If bounds are wrong (gaps, overlaps, missing front matter), objects route incorrectly → manifests show missing objects → correspondence rate drops below 95% → release blocked.

Test coverage: `tests/test_pipeline_orchestration.py::test_blocked_release_reports_the_violation`

### Draft Correspondence Emission (draft_command.py)

**Purpose**: Record which source objects were preserved in each draft.

**Implementation**: After LLM draft generation, extract protected objects from draft output, match by hash against source objects, emit manifest with preserved/missing lists.

**Schema**:
```json
{
  "record_type": "DraftCorrespondenceManifest",
  "section_index": 0,
  "section_title": "Introduction",
  "parent_artifact_hash": "<source-file-hash>",
  "correspondence_to_source": {
    "preserved": [{"id": "eq:1", "hash": "abc...", "type": "equation"}],
    "missing": [{"id": "cite:jones", "hash": "def..."}],
    "added": []
  },
  "retention_rate": 0.97,
  "dispositions": {
    "omitted_objects": [
      {
        "hash": "def...",
        "reason": "not_relevant",
        "human_approved": true
      }
    ]
  }
}
```

Test coverage: `tests/test_draft_correspondence.py`

### Assembly Correspondence Emission (assemble_command.py)

**Purpose**: Verify draft objects preserved through assembly (99% threshold).

**Implementation**: Extract protected objects from assembled document, match against union of all draft objects, emit manifest with retention metrics.

**Schema** (backward-compatible):
```json
{
  "record_type": "AssemblyCorrespondenceManifest",
  "retention_vs_drafts": 0.99,      // New field (Check 7)
  "retention_vs_source": 0.95,      // New field
  "retention_rate": 0.99,            // Old field (kept for compatibility)
  "total_draft_objects": 100,
  "preserved_count": 99,
  "correspondence_to_source": {
    "preserved": [...],
    "missing": [...],
    "added": [...]
  },
  "dispositions": {"omitted_objects": [...]}
}
```

**Backward compatibility**: Emits both new fields (`retention_vs_drafts`, `retention_vs_source`) and old field (`retention_rate`) so existing consumers continue working during migration.

Test coverage: `tests/test_assembly_correspondence.py`

### Release Gate Checks (release_command.py)

**Purpose**: Block release when correspondence evidence is missing or thresholds violated.

**Check 4** (Draft correspondence, 95% threshold):
```python
def check_protected_manifest_correspondence(snapshot_dir: Path) -> Optional[dict]:
    """
    7 fail-closed checks:
    1. Source manifest exists
    2. Source hash matches current source (no drift)
    3. Draft manifests exist (at least one per run)
    4. Identity preservation ≥95% (draft threshold)
    5. All missing objects have approved dispositions
    6. Parser agreement ≥90%
    7. Assembly correspondence ≥99% (if assembled)
    
    Returns None if all pass, block dict otherwise.
    """
```

**Check 7** (Assembly correspondence, 99% threshold):
- Reads latest assembly correspondence manifest
- Validates `retention_vs_drafts >= 0.99`
- Returns block if threshold violated, including diagnostic details

Test coverage: `tests/test_gate_enforcement.py`, `tests/test_assembly_correspondence.py`

### Repair Command (repair_command.py)

**Purpose**: Hash-targeted restoration when assembly correspondence < 99%.

**Workflow**:
1. Read assembly correspondence manifest → identify missing objects by hash
2. Look up each missing hash in source manifest → get content + line number
3. Extract source context (±3 lines) for verification
4. Propose restoration strategy (copy_from_source, manual_review)
5. Output JSON report for human review

**Output schema**:
```json
{
  "status": "repairs_needed",
  "missing_count": 2,
  "retention_vs_drafts": 0.97,
  "proposals": [
    {
      "object_hash": "abc123...",
      "strategy": "copy_from_source",
      "source_file": "source.tex",
      "source_line": 42,
      "content": "\\cite{jones2021}",
      "type": "citation",
      "context": "40: Previous text\n41: More context\n42: \\cite{jones2021}\n43: Following text"
    }
  ]
}
```

Test coverage: `tests/test_repair_integration.py`

## Design Principles

### 1. Fail-Closed by Default

**Rationale**: The ZLB rescue (humanvoice founding incident) demonstrated that fail-open gates pass when evidence is absent, shipping violations to readers. Gate 4 must block when correspondence cannot be verified.

**Implementation**:
- Missing source manifest → block ("cannot verify correspondence without ground truth")
- Missing draft manifests → block ("no evidence of preservation")
- Missing assembly manifest (when assembled/ exists) → block ("assembly correspondence required")

### 2. Identity-Preserving Verification

**Rationale**: Counting objects is insufficient. If `\cite{jones2021}` becomes `\cite{smith2022}`, the count is unchanged but the content is wrong.

**Implementation**: Hash-based matching. Each protected object carries a cryptographic hash of its content. Correspondence is verified by hash identity, not string similarity or count.

### 3. Front Matter Coverage

**Problem**: LaTeX documents have content before the first `\section{}`:
```latex
\documentclass{article}
\begin{document}
\begin{abstract}
Text with \cite{important2020}.  % ← Outside any section!
\end{abstract}
\section{Introduction}
...
```

If sections start at their `\section{}` line, the abstract citation is never routed to any draft → shows as missing → correspondence < 95% → release blocked.

**Solution**: Extend first section's `start_line` back to 1 after computing all section boundaries.

Test coverage: `tests/test_plan_section_bounds.py::test_front_matter_before_first_section_is_covered`

### 4. Backward-Compatible Schema Evolution

**Context**: Check 7 was enhanced to validate actual retention rates (not just manifest existence). Old test fixtures used `retention_rate` field; new code expects `retention_vs_drafts` and `retention_vs_source`.

**Solution**: 
- `assemble_command.py` emits all three fields
- `release_command.py` reads the new fields
- Old consumers (if any) can still read `retention_rate`
- Test fixtures updated to include all three fields

**Migration path**: When all consumers move to new fields, remove `retention_rate` in a future schema version.

## Testing Strategy

### Unit Tests
- `tests/test_plan_section_bounds.py`: Section tiling, front matter coverage
- `tests/test_draft_correspondence.py`: Manifest emission, hash matching
- `tests/test_assembly_correspondence.py`: 99% threshold, manifest structure

### Integration Tests
- `tests/test_pipeline_orchestration.py`: End-to-end (source → draft → assembly → release)
- `tests/test_gate_enforcement.py`: All 7 fail-closed checks
- `tests/test_repair_integration.py`: Hash-targeted restoration

### Key Test Cases

1. **Front matter coverage** (`test_front_matter_before_first_section_is_covered`)
   - Document with abstract + citation before first section
   - Verify first section starts at line 1
   - Verify citation routes to first section's draft

2. **Section tiling** (`test_sections_tile_the_file_without_gaps_or_overlaps`)
   - Multi-section document
   - Verify `sections[i].end_line + 1 == sections[i+1].start_line`
   - Verify no line is unreachable

3. **99% threshold enforcement** (`test_assembly_correspondence_blocks_at_98_percent`)
   - Assembly manifest with `retention_vs_drafts = 0.98`
   - Verify release blocked
   - Verify diagnostic includes preserved/total counts

4. **Missing manifest blocks release** (`test_assembly_correspondence_blocks_when_manifest_missing`)
   - Assembled directory exists but no correspondence manifest
   - Verify release blocked (fail-closed)

5. **Repair identifies missing objects** (`test_repair_identifies_missing_objects`)
   - Assembly manifest with 2 missing objects
   - Verify repair command finds them by hash
   - Verify source line numbers included

## Remaining Work

### Production Data Gap
**Issue**: 69 existing drafts (from before Gate 4 implementation) have zero correspondence manifests. Release gate correctly blocks them, but authors need a path forward.

**Options**:
1. **Re-draft all 69 documents** (cleanest, but high cost)
2. **Backfill manifests** by re-parsing drafts and matching against source (requires draft text still available)
3. **Grandfather exception** (violates fail-closed principle, not recommended)

**Recommendation**: Option 1 (re-draft). Gate 4 is a v1.2 requirement; existing snapshots can be marked "pre-v1.2" and released under the old (fail-open) rules, but new work goes through the full gate.

### Evidence Item Emission
**Scope**: v1.2 external release requirement (not blocking internal eval).

**Purpose**: Reader packet must include the correspondence manifests so readers can verify preservation claims.

**Implementation**: Extend `assemble_reader_packet()` to copy source manifest, draft manifests, and assembly manifest into the packet.

### Transmission Tracking
**Scope**: v1.2 external release requirement.

**Purpose**: Record which API calls transmitted which protected objects (for auditing model behavior).

**Implementation**: Log protected object hashes in API request/response metadata.

## Claim vs. Non-Claim Separation

**Claims** (verified by tests):
- Section line bounds cover front matter without gaps
- Draft evidence routing matches objects by (file, line range)
- Assembly correspondence validates 99% retention threshold
- Missing manifests block release (fail-closed)
- Repair command locates missing objects by hash

**Non-claims** (not tested, cannot verify):
- LLM will preserve ≥95% of objects (depends on prompt, model, content)
- Human reviewers will approve all legitimate omissions
- Source parser extracts 100% of protected objects (parser agreement threshold is 90%)

**Principle**: The implementation enforces the *process* (manifests emitted, thresholds checked, evidence routed). Whether the process achieves the *outcome* (high preservation in practice) is measured but not guaranteed.
