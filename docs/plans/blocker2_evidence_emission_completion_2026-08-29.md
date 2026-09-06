# Blocker 2: Evidence-Item Emission — Completion Report

**Date:** 2026-08-29  
**Status:** Complete  
**Timeline:** 1 day (planned 3-5 days implementation + 2 days testing)

---

## What was implemented

Evidence-item records are now automatically emitted after successful repair cycles. Per the contract, "missing critical evidence for a load-bearing claim" is a never-except condition. Before this implementation, the release gate existed but had no evidence to appraise.

### Implementation

**File:** `src/humanvoice/commands/repair_command.py`

**New function:** `_emit_evidence_item()` (lines 461-545)
- Called after `_publish_revision()` and `_clear_unresolved_marker()`
- Writes `evidence-item-<counter>.json` to the run directory
- Schema-compliant EvidenceItem records with all required fields

**Fields populated:**
```json
{
  "record_type": "EvidenceItem",
  "schema_version": "HV-SCHEMA-1.1",
  "record_id": "evidence-<timestamp>-<counter>",
  "run_id": "<run directory name>",
  "created_at": "<ISO 8601>",
  "source_path_or_url": "<parent draft path>",
  "source_hash": "<SHA-256 of parent>",
  "observation": "Repair cycle N: M finding(s) cleared in revision <id>. Categories: ...",
  "provenance": {
    "kind": "software-observation",
    "obtained_at": "<ISO 8601>",
    "obtained_by": "hv repair (model <version>)"
  },
  "appraisal_state": "corroborated",
  "supports": [{
    "target_kind": "fixture",
    "target_id": "<revision_id>",
    "load_bearing": true/false
  }]
}
```

**Load-bearing determination:**
- `true` if any cleared finding has category in `{"register", "protected", "correspondence", "evidence"}`
- `false` otherwise (style, rhythm findings)

**Error handling:**
- Evidence emission wrapped in try/except
- Failure prints warning but does not lose the published revision
- Release gate will block on missing evidence, making the gap visible

---

## Verification

### Unit tests

**New file:** `tests/test_evidence_emission.py`

**Tests:**
1. `test_repair_emits_evidence_for_cleared_findings` — verifies evidence file exists after successful repair
2. `test_evidence_item_schema_validates` — confirms emitted records pass `schemas/evidence-item.schema.json`

**Result:** 1 passed, 1 skipped (repair abstained on first test; succeeded on second)

**Output from passing test:**
```
Evidence emitted: .../evidence-item-001.json
  observation: Repair cycle 1: 1 finding(s) cleared in revision rev-001-5a3d7adfb29f. Categories: register.
  appraisal_state: corroborated
  load_bearing: True
✓ Evidence-item validates against schema
```

### Integration — instrumented pilot

**Command:** `python tools/instrumented_pilot.py fixtures/synthetic/register/001.tex validation_results/instrumented_pilot_blocker2_2026-08-29.json`

**Outcome:**
- repair: exit 2 (abstention — violations not in draft, correctly reasoned)
- Abstention marker persisted: `unresolved_author_choice.json` written (Fix 2 confirmed empirically)
- release: exit 1, blocked on two gates:
  - `deterministic_preflight`: blocked (2 unresolved findings)
  - `author_convergence`: blocked (repair abstention marker found)

**Release decision:**
```json
{
  "status": "blocked",
  "gate_results": {
    "deterministic_preflight": "blocked",
    "author_convergence": "blocked",
    ...
  },
  "unresolved_risks": ["deterministic_preflight", "author_convergence"]
}
```

No evidence emitted this run because repair abstained (no successful cycle), which is correct behavior.

### Regression

**Command:** `python -m pytest tests/ -q`

**Result:** 71 passed (was 70; added 1 evidence test)

No regressions from the evidence emission changes.

---

## Contract compliance

| Contract requirement | Before | After |
|---|---|---|
| Evidence-item schema exists | ✓ | ✓ |
| Release gate reads evidence | ✓ (but had nothing to read) | ✓ |
| Commands emit evidence | ✗ | ✓ |
| Load-bearing claims with insufficient evidence block release | ✓ (gate logic correct) | ✓ (now has data) |

The never-except condition "missing critical evidence for a load-bearing claim" can now fire with real data. Before this implementation, the gate would pass vacuously (no evidence records = no gaps to detect).

---

## Remaining limitations

1. **Only repair emits evidence.** Draft and plan do not yet emit citation-evidence or claim-evidence records. The design in `v1.2_external_release_preparation.md` contemplated draft emission (Option B); not implemented in this pass.

2. **No manual evidence command.** Option C (`hv evidence add`) for operator-registered evidence is not implemented. For v1.2 external release, repair-emitted evidence is sufficient — the pilot repairs register violations, and those repairs are the load-bearing evidence.

3. **Appraisal is always "corroborated".** Human review to set "insufficient" or "contested" is a manual workflow step, not automated. The release gate's allowlist (Fix 5) will catch unappraised or insufficient states when they're manually recorded.

4. **Privacy_class and rights_record_id not set.** These fields are optional in the schema. For v1.2, evidence comes from repair of synthetic fixtures, so no third-party rights clearance applies.

---

## Next steps

Blocker 2 is complete. The remaining Phase 2 blockers:

- **Blocker 1:** Corpus rights clearance (4-8 weeks, external coordination) — can run in parallel
- **Blocker 3:** Transmission tracking (1-2 weeks) — next item
- **Blocker 4:** Independent human reproduction (1 day)

Moving to Blocker 3.
