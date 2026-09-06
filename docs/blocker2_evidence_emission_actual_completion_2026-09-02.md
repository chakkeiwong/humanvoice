# Blocker 2: Evidence Item Emission — Actual Completion

**Date:** 2026-09-02  
**Status:** Complete (for real this time)  
**Commit:** 1efab5c

---

## What happened

The blocker2_evidence_emission_completion_2026-08-29.md report (written 2026-08-30) claimed Blocker 2 was complete and described `_emit_evidence_item()` at lines 461-545 in repair_command.py.

**Investigation revealed:**
- repair_command.py was only 421 lines total
- The function `_emit_evidence_item()` did not exist anywhere in the codebase
- Git history showed repair_command.py was never committed before 2026-09-02 (commit f57b086)
- Bytecode was compiled from the stub implementation, not from an original
- The blocker2 report was a **plan document mislabeled as a completion report**

**Root cause:** The 2026-08-30 report documented intended implementation, not delivered code. The work was never actually done.

---

## What was implemented (2026-09-02)

### 1. Complete repair_command.run()

**Before:** Stub with `if args.mock or True:` that never executed real repair logic.

**After:** Full implementation that:
- Generates verbatim replacements for findings
- Preserves numeric values (e.g., "WP3" → "phase 3" for register violations)
- Applies changes using `_apply_changes()`
- Validates revisions against brief and findings
- Publishes revision manifests atomically
- Clears unresolved markers
- Emits evidence items

### 2. Implement _emit_evidence_item()

**Location:** [repair_command.py:361-446](src/humanvoice/commands/repair_command.py#L361-L446)

**Schema-compliant records with:**
- `record_type: "EvidenceItem"`
- `schema_version: "HV-SCHEMA-1.1"`
- `appraisal_state: "corroborated"` (software observations)
- `load_bearing: true` for register/protected/correspondence/evidence categories
- `load_bearing: false` for style/rhythm findings
- All required fields (record_id, run_id, created_at, source_path_or_url, source_hash, observation, provenance, supports)

**Load-bearing determination:**
```python
load_bearing_categories = {"register", "protected", "correspondence", "evidence"}
categories = {finding_category for each cleared finding}
is_load_bearing = bool(categories & load_bearing_categories)
```

**Observation format:**
```
Repair cycle 1: 2 finding(s) cleared in revision rev-001-abc123. Categories: register, style.
```

---

## Verification

### Unit tests

**File:** tests/test_evidence_emission.py

**Before:** 2 tests skipped (pytest.skip when repair didn't converge)

**After:** 2 tests PASSED
1. `test_repair_emits_evidence_for_cleared_findings` — verifies evidence file exists, schema compliance, load_bearing=True for register category
2. `test_evidence_item_schema_validates` — confirms emitted records pass JSON Schema validation

### Full test suite

**Before:** 143 passed, 2 skipped

**After:** 145 passed (all tests passing)

### Integration test

```python
# repair → evidence emission → release gate reads it
repair_rc = repair_command.run(args)  # exit 0
evidence_files = list(run.glob('**/evidence-item-*.json'))  # 1 file found
ev = json.loads(evidence_files[0].read_text())
assert ev["appraisal_state"] == "corroborated"
assert ev["supports"][0]["load_bearing"] is True
# ✓ Evidence gate in release_command.py can now read real data
```

---

## Contract compliance

| Contract requirement | Before (2026-08-30 claim) | After (2026-09-02 actual) |
|---|---|---|
| Evidence-item schema exists | ✓ | ✓ |
| Release gate reads evidence | ✓ (but had nothing to read) | ✓ (has real data) |
| Commands emit evidence | ✗ (not implemented) | ✓ (working) |
| Load-bearing claims with insufficient evidence block release | ✓ (gate logic correct) | ✓ (now has data to appraise) |

**Before this implementation:** The evidence_sufficiency gate would pass vacuously because no evidence records existed.

**After this implementation:** The never-except condition "missing critical evidence for a load-bearing claim" can fire with real data.

---

## Remaining limitations (same as before)

1. **Only repair emits evidence.** Draft and plan do not yet emit citation-evidence or claim-evidence records. For v1.2 external release, repair-emitted evidence is sufficient.

2. **No manual evidence command.** Option C (`hv evidence add`) for operator-registered evidence is not implemented.

3. **Appraisal is always "corroborated".** Human review to set "insufficient" or "contested" is a manual workflow step. The release gate's allowlist will catch these when manually recorded.

4. **privacy_class and rights_record_id not set.** These fields are optional. For v1.2, evidence comes from repair of synthetic fixtures, so no third-party rights clearance applies.

5. **Stub model behavior.** The repair implementation uses rule-based replacements (e.g., "WP3" → "phase 3") rather than calling a generative model. This is sufficient for test coverage and gate verification. Real model integration is a separate work item.

---

## Impact on v1.2 roadmap

**Blocker 2 is now truly complete.**

Remaining Phase 2 blockers:
- **Blocker 1:** Corpus rights clearance — DONE (all 5 items cleared 2026-08-29)
- **Blocker 2:** Evidence-item emission — DONE (this implementation)
- **Blocker 3:** Transmission tracking — next item (1-2 weeks)
- **Blocker 4:** Independent human reproduction — (1 day, after Blocker 3)

The evidence system is functional end-to-end:
1. ✓ Preflight detects violations
2. ✓ Repair clears findings and emits evidence
3. ✓ Release gate reads evidence and blocks on insufficient appraisal
4. ✓ All gates fail-closed (no more silent passes)

---

## What changed from the 2026-08-30 report

The 2026-08-30 report described:
- `_emit_evidence_item()` (lines 461-545) — **never existed**
- "Evidence emitted: .../evidence-item-001.json" — **never happened**
- "1 passed, 1 skipped" test result — **was actually 0 passed, 2 skipped**

This completion report documents:
- `_emit_evidence_item()` (lines 361-446) — **actually implemented**
- Evidence emission verified in integration test — **actually working**
- "2 passed" test result — **actually achieved**

The 2026-08-30 report was aspirational. This report is empirical.

---

## Next steps

Move to Blocker 3 (transmission tracking): instrument model.py to record external LLM calls, emit transmission records, and add release gate to enforce transmission-to-corpus correspondence.
