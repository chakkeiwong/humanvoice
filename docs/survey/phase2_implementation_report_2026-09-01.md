# Phase 2 Implementation Report: Draft Correspondence Tracking

**Date:** 2026-09-01  
**Phase:** 2 of 6 (Evidence routing in draft_command.py)  
**Status:** Complete  

## Objective

Replace the 3,000-character evidence truncation in `draft_command.py:122-123` with targeted evidence routing that:
1. Loads the source protected manifest before drafting
2. Routes protected objects to sections based on line numbers
3. Updates the draft prompt to emphasize protected objects with hashes
4. Emits per-section draft correspondence manifests tracking preservation/omission
5. Reports retention rate to stderr

## Changes Made

### 1. Modified `src/humanvoice/commands/draft_command.py`

**Imports added:**
- `ProtectedManifest` from `humanvoice.protected_objects`
- `Optional, Tuple` from `typing`

**New functions:**

- `_load_source_manifest(snapshot_dir: Path) -> Optional[ProtectedManifest]`
  - Reads `.humanvoice/protected_objects/source_manifest.json`
  - Returns `None` if absent (extraction never ran)
  - Raises on parse failure (corrupt manifest is distinct from absent)
  - Filters the placeholder sentinel `"[No evidence files available]"` to avoid treating it as real evidence

- `_prepare_section_evidence(section, source_content, source_manifest, evidence_files, snapshot_dir) -> Tuple[str, List[Dict]]`
  - Loads supplementary evidence via existing `_load_evidence_content`
  - Selects protected objects whose line numbers fall within `section["source_start_line"]` to `section["source_end_line"]`
  - Converts `ProtectedObject` dataclass instances to dicts for downstream compatibility
  - Builds evidence text with two sections:
    - `=== Supplementary Evidence ===` (papers, external docs)
    - `=== Protected Objects in This Section ===` (per-object excerpts with hash, type, content, context)
  - Returns `(evidence_text, protected_objects_list)`

- `_emit_draft_manifest(output_dir, section_title, source_manifest, protected_objects_in_section, draft_latex) -> Path`
  - Re-extracts protected objects from the draft LaTeX via `extract_protected_objects_from_text`
  - Compares source and draft hashes to categorize objects as `preserved`, `missing`, or `added`
  - Calculates retention rate: `len(preserved) / len(source_objects)`
  - Emits `DraftCorrespondenceManifest` with:
    - `record_type`, `schema_version`, `section_title`, `parent_artifact_hash`
    - `correspondence_to_source`: three lists with type/hash/content
    - `retention_rate`: float in [0, 1]
    - `dispositions.omitted_objects`: array of missing objects, each with `reason=None`, `human_approved=False`, requiring manual disposition before release
  - Writes to `<run_dir>/draft_correspondence_<safe_title>.json`

**Modified functions:**

- `_build_draft_prompt(section, brief, evidence_content, protected_objects)`
  - Added `protected_objects` parameter (list of dicts)
  - Removed 3,000-char truncation and `brief["protected_objects"]` count
  - Added new prompt section listing protected objects with hashes:
    ```
    **Protected objects that must be preserved exactly:**
    N objects in this section:
      - equation [hash: abc123def456]: \begin{equation}...
      - label [hash: ...]: sec:intro
    ```
  - Evidence is no longer truncated — full text from `_prepare_section_evidence` is included

- `run(args)`
  - Calls `_load_source_manifest(snapshot_dir)` early; warns if `None`
  - Calls `_prepare_section_evidence` instead of `_load_evidence_content`
  - Logs routed object count to stderr: `"Routed N protected objects to 'Section Title' (lines X-Y)"`
  - Passes `protected_objects` list to `_build_draft_prompt`
  - After draft generation, calls `_emit_draft_manifest` if manifest and objects exist
  - Reads back the manifest to report retention: `"Protected object retention: M/N (X.Y%), K missing"`

### 2. Test Coverage

Created `tests/test_draft_correspondence.py` with three integration tests:

- `test_draft_routes_protected_objects_by_line_number`
  - Runs `hv init` on baseline fixture to extract 131 objects
  - Routes all objects by line range (18–340)
  - Uses source document itself as draft (honest upper bound for retention)
  - Verifies 100% retention, correct manifest structure, empty dispositions

- `test_draft_manifest_tracks_missing_objects`
  - Routes all objects, builds draft with only first half
  - Verifies retention < 100%, `missing` list populated, dispositions array matches missing count
  - Confirms each disposition has `reason=None`, `human_approved=False`

- `test_draft_no_manifest_degrades_gracefully`
  - No source manifest present
  - `_load_source_manifest` returns `None`
  - `_prepare_section_evidence` returns empty object list, `"[No evidence available]"` text
  - No crash, no manifest emission

All three tests pass.

## Design Decisions

### Dataclass vs Dict Inconsistency

- `ProtectedManifest.from_json()` returns dataclass instances with attribute access (`obj.hash`)
- Routing converts to dicts (`{"hash": obj.hash}`) for downstream code that expects dict access
- `extract_protected_objects_from_text` returns dataclasses
- Manifest emission handles both: source objects are dicts, draft objects are dataclasses

**Rationale:** Mixing both patterns is expedient for Phase 2. A future refactor could normalize to one representation, but that's beyond scope.

### Sentinel String Handling

`_load_evidence_content` returns `"[No evidence files available]"` when `evidence_files` is empty. This truthy string was incorrectly treated as real evidence. Fixed by filtering it out in `_prepare_section_evidence`:

```python
if supplementary_evidence == "[No evidence files available]":
    supplementary_evidence = ""
```

### Perfect-Draft Test Fixture

Initial test built a "perfect draft" by concatenating `obj["content"]` for all objects. This failed with 84% retention because:
- Labels store bare names (`sec:intro`, not `\label{sec:intro}`)
- Align rows store row bodies without environment wrappers
- Re-extraction from naive concatenation loses both

**Fix:** Use the source document itself as the draft. Retention is 100% by construction, which is the honest upper bound and validates the mechanism correctly.

### Error Handling for Corrupt Manifests

Original `_load_source_manifest` caught all exceptions and returned `None`, treating corrupt manifests the same as absent ones. This masks the real failure: a corrupt manifest means correspondence tracking is broken.

**Fix:** Let parse failures raise. Absence is expected and degrades gracefully; corruption is a data integrity failure that must surface.

## Verification

```bash
python -m pytest tests/test_draft_correspondence.py -v
# 3 passed in 0.32s

python -c "from humanvoice.commands import draft_command; print('IMPORT OK')"
# IMPORT OK

grep -c "3000" src/humanvoice/commands/draft_command.py
# 0 (truncation removed)
```

## Integration with Phases 0 & 1

- **Phase 0:** Baseline fixture (131 objects, 100% parser agreement) used in all Phase 2 tests
- **Phase 1:** `hv init` extraction tested via integration; manifests load correctly
- **Phase 3 (next):** `check_protected_manifest_correspondence()` will consume these draft manifests to enforce retention thresholds and disposition approval

## Remaining Work

1. **Phase 3:** Rewrite release gate with 7 fail-closed checks (missing/stale source manifest, missing draft manifests, per-object identity gaps, unapproved dispositions)
2. **Phase 4:** Assembly correspondence at 99% threshold
3. **Phase 5:** Hash-targeted restoration in `repair_command.py`
4. **Phase 6:** Documentation with explicit claim/non-claim separation

## Exit Criteria Met

✅ 3,000-char truncation removed  
✅ Source manifest loaded before drafting  
✅ Protected objects routed by line number  
✅ Prompt surfaces object hashes  
✅ Draft manifest emitted per section with correspondence tracking  
✅ Retention rate reported to stderr  
✅ Integration tests pass (3/3)  
✅ Dispositions structure present for all missing objects  

**Status:** Phase 2 complete. Ready for Phase 3 (release gate rewrite).
