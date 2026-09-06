# Blocker 1: Corpus Rights Clearance — Status Report

**Date:** 2026-08-29  
**Status:** Infrastructure complete, clearance pending external coordination  
**Items cleared:** 0 of 5 (all pending)

---

## What was delivered

Infrastructure for tracking and validating corpus rights clearance, ready for external coordination with rights holders.

### Deliverables

**1. Clearance process documentation:** `docs/survey/rights_clearance/README.md`
- 5-step process (owner ID → request → response → consent → fallback)
- Permission request template
- Status tracking format
- Timeline (8 weeks)
- Risk mitigation (public-domain alternatives)

**2. Validation tool:** `tools/check_corpus_rights.py`
- Reads `corpus_rights_manifest.json`
- Reports cleared vs blocking items
- Validates against `corpus-item.schema.json`
- Supports `--scope internal` (G4-approved) vs `--scope external` (requires clearance)
- Catches incomplete clearance records (status marked cleared but no consent_date/hash)
- Exit 0 if corpus may ship, exit 1 if blocked

**3. Clearance directory:** `docs/survey/rights_clearance/`
- Created for storing owner ID docs, request records, responses, consent artifacts

---

## Current Status

### Corpus Rights Manifest

**File:** `docs/survey/evidence/corpus_rights_manifest.json`  
**Manifest ID:** HV-CORPUS-RIGHTS-2026-08-26  
**Status:** incomplete

| Item | Owner | Status | Consent Date |
|---|---|---|---|
| CORP-BGS | DynareMCP project: pending confirmation | pending-clearance | null |
| CORP-ZLB | BayesFilter project: pending confirmation | pending-clearance | null |
| CORP-SMEWALLET | SMEwallet project: pending confirmation | pending-clearance | null |
| CORP-CARDNPV | CardNPV project: pending confirmation | pending-clearance | null |
| CORP-MACROFINANCE | MacroFinance project: pending confirmation | pending-clearance | null |

**Validation output:**
```
$ python tools/check_corpus_rights.py
Corpus rights: HV-CORPUS-RIGHTS-2026-08-26
Scope: external
Items: 0/5 cleared

Blocking:
  - CORP-BGS: pending-clearance
  - CORP-ZLB: pending-clearance
  - CORP-SMEWALLET: pending-clearance
  - CORP-CARDNPV: pending-clearance
  - CORP-MACROFINANCE: pending-clearance

Result: corpus may NOT ship in an external release. 5 item(s) blocking.
```

**Internal scope (G4-approved):**
```
$ python tools/check_corpus_rights.py --scope internal
Items: 5/5 cleared
Result: corpus may ship in an internal release.
```

Internal evaluation is already authorized per G4 decision (Option A: internal fixture evaluation). External release requires explicit permission from each corpus owner.

---

## What remains

### Immediate next steps (Week 1-2)

1. **Owner identification:** Determine rights holder contact information for each corpus item
   - DynareMCP, BayesFilter, SMEwallet, CardNPV, MacroFinance projects
   - Check if these are internal organizational projects or external third-party sources
   - Document findings in `docs/survey/rights_clearance/<record-id>_owner_identification.md`

2. **Draft permission requests:** Customize template for each owner
   - Explain humanvoice project context
   - Clarify internal vs external use
   - Request written permission for external release
   - Send via email with 3-week response window

### Week 3-4: Response window

Monitor for responses:
- Permission granted → proceed to consent recording
- Permission denied → identify fallback alternative
- No response after 3 weeks → send follow-up

### Week 5-8: Finalization

For each item:
- **Granted:** Update manifest (`redistribution_status: "cleared-public"`, `consent_date`, `source_hash`)
- **Denied/no response:** Replace with public-domain alternative (arXiv, NBER, synthetic)
- **Final validation:** `python tools/check_corpus_rights.py` exits 0

**Completion criteria:** Manifest `status: "complete"`, all items either cleared or replaced

---

## Risk mitigation

### If all items are denied or unresponsive

**Plan A:** Public-domain corpus
- arXiv economics/finance papers (permissive license)
- NBER working papers (public domain)
- Government reports (public domain in many jurisdictions)

**Plan B:** Synthetic-only corpus
- Use only `fixtures/synthetic/register/001.tex` and similar
- Document limitation: "System evaluated on synthetic fixtures only; real-world domain coverage pending corpus clearance"

**Impact:** Blocker 1 does not block Phase 3 packaging if fallback is used. It limits external evaluation scope, but does not prevent release.

---

## Timeline estimate

| Week | Activity | Deliverable |
|---|---|---|
| 1 | Owner identification | 5 × `_owner_identification.md` |
| 2 | Send requests | 5 × `_request_sent_YYYY-MM-DD.md` |
| 3-4 | Await responses | — |
| 5-6 | Follow-up or research fallbacks | Response records or fallback docs |
| 7-8 | Finalize manifest | `manifest.json` with `status: "complete"` |

**Critical decision point:** Week 4. Any item without a response should trigger fallback research rather than waiting indefinitely.

**Hard deadline:** Week 8. Phase 3 (external release packaging) cannot proceed until Blocker 1 is resolved or mitigated.

---

## Integration with release gates

The corpus rights manifest should eventually gate external release, similar to how preflight gates snapshot release. A never-except condition:

> "Corpus redistribution without documented owner consent"

This would require:
- New gate in `release_command.py`: `check_corpus_rights()`
- Calls `tools/check_corpus_rights.py --scope external --json`
- Blocks if `release_permitted: false`

**Not implemented yet** because corpus clearance is Phase 2 work (before first external release), while release gates apply to snapshot-level decisions. Corpus clearance is a repository-level gate, not a snapshot-level gate.

Future work: Add a top-level `hv publish` command that:
1. Checks corpus rights
2. Checks that at least one snapshot released successfully
3. Bundles snapshot + corpus + provenance
4. Emits external release artifact

---

## Acceptance criteria (partial)

From the plan:

> **Deliverable:** `docs/survey/rights_clearance/manifest.json` with clearance status per item

**✓ Delivered:** Infrastructure in place:
- Process documented
- Validation tool working
- Directory created

**⏳ Pending:** Actual clearance (requires external coordination, 4-8 weeks)

The infrastructure is complete. The blocking work is now contacting rights holders and awaiting responses, which cannot be automated.

---

## Files changed

**New:**
- `docs/survey/rights_clearance/README.md` (process documentation)
- `tools/check_corpus_rights.py` (validation tool)

**Existing:**
- `docs/survey/evidence/corpus_rights_manifest.json` (status: incomplete)
- `schemas/corpus-item.schema.json` (already existed, used for validation)

---

## Token budget

**Session total:** 93,706 / 200,000 (46.9%)  
**Remaining:** 106,294

Phase 2 infrastructure is now 100% complete. Blocker 1 clearance is ready for external coordination (weeks 1-8 timeline).
