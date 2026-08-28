# WP6 Rights Review

**Date:** 2026-08-28  
**Contract:** HV-IC-2026-08-26 v1.1.0  
**Status:** All corpus items pending clearance; blocking G4 handoff for external release

## 1. Purpose

Review corpus rights status per `implementation_contract.json` section "corpus_rights". Required for G4 decision: can the prototype be externally released, or is it restricted to internal evaluation?

## 2. Contract Requirements

From `implementation_contract.json`:

**Required fields for every corpus item:**
- `source_path_or_url`
- `source_hash`
- `owner`
- `license_or_permission`
- `permitted_use`
- `redistribution_status`
- `retention_class`
- `consent_date`

**Allowed statuses:**
- `cleared-internal`: Approved for internal use
- `cleared-public`: Approved for public redistribution
- `restricted-not-for-export`: Internal use only, cannot be externally shared
- `pending-clearance`: Awaiting permission
- `excluded`: Not permitted for any use

**Rule:** "Pending or restricted material may support internal fixture work only when the owner permits it; it cannot enter a published benchmark, external reader packet, or commercial training set without written clearance."

## 3. Current Corpus Rights Manifest

Location: [docs/survey/evidence/corpus_rights_manifest.json](../survey/evidence/corpus_rights_manifest.json)

**Manifest status:** `incomplete`

### All items (5 total):

| Record ID | Source | Owner | Permission Status | Redistribution | Consent Date | Blocking Issue |
|-----------|--------|-------|------------------|----------------|--------------|----------------|
| CORP-BGS | DynareMCP/docs/AIpostdoc/finalBGS/ | Pending confirmation | Pending written permission | `pending-clearance` | null | No owner confirmation, no written permission |
| CORP-ZLB | BayesFilter/docs/surveys/zlb_discontinuous_hmc/ | Pending confirmation | Pending written permission | `pending-clearance` | null | No owner confirmation, no written permission |
| CORP-SMEWALLET | SMEwallet/docs/handoffs/ | Pending confirmation | Pending written permission | `pending-clearance` | null | No owner confirmation, no written permission |
| CORP-CARDNPV | cardnpv/docs/final/ | Pending confirmation | Pending written permission | `pending-clearance` | null | No owner confirmation, no written permission |
| CORP-MACROFINANCE | MacroFinance/docs/latex-papers/CIP_monograph/ | Pending confirmation | Pending written permission | `pending-clearance` | null | No owner confirmation, no written permission |

**Summary:** 0/5 items cleared, 5/5 items pending clearance, 0/5 items have consent dates.

**Current permitted use (all items):** `"internal fixture evaluation only"`

## 4. Historical Sources Status

Location: [fixtures/historical_sources.json](../../fixtures/historical_sources.json)

**Registry status:** `quarantined`

**Rule:** "A located artifact is not a permitted replay. Replay also requires an immutable source snapshot, answer key, provenance, and rights for the declared use."

### All historical sources (5 total):

| Source ID | Availability | Replay Status | Rights Record | Blocking Issue |
|-----------|--------------|---------------|---------------|----------------|
| HIST-BGS-REPAIR-MAP-V7 | `located-rights-pending` | `unavailable` | CORP-BGS | Rights pending, no answer key |
| HIST-ZLB-PASS-TWO | `unavailable` | `unavailable` | CORP-ZLB | Source snapshot not identified |
| HIST-ZLB-CURRENT-TEX | `located-rights-pending` | `unavailable` | CORP-ZLB | Rights pending, needs pass-two baseline |
| HIST-ZLB-CURRENT-PDF | `located-rights-pending` | `unavailable` | CORP-ZLB | Rights pending, not substitute for historical pair |
| HIST-SLOPTRIM-HUMANVOICE-CALIBRATION | `unavailable` | `unavailable` | null | No frozen calibration set with hashes |

**Summary:** 0/5 sources available for replay, 3/5 located but rights pending, 2/5 not located.

## 5. Impact on Prototype Status

### What can be done NOW (under "internal fixture evaluation only"):
✓ Test suite execution on synthetic fixtures  
✓ Property-based validation on synthetic fixtures  
✓ Mutation replay on synthetic fixtures  
✓ Internal development and iteration  
✓ Contract verification and gap analysis  
✓ Cost/burden analysis based on synthetic fixtures  

### What is BLOCKED (requires clearance):
✗ External release of prototype with real-document benchmarks  
✗ Publication of ZLB or BGS case studies  
✗ Redistribution of reader packets containing corpus-derived content  
✗ Public demonstration using BGS/ZLB/SMEwallet/CardNPV/MacroFinance materials  
✗ Commercial training on corpus materials  
✗ Independent reproduction of historical results (no answer keys)  

## 6. Clearing Process (Not Yet Started)

### Required actions per corpus item:
1. **Identify owner:** Confirm project ownership with named individual
2. **Request permission:** Formal written request for intended use
3. **Record consent:** Obtain dated written permission
4. **Freeze snapshot:** Create immutable source snapshot with hash
5. **Document license:** Record specific permitted uses and redistribution terms
6. **Update manifest:** Record consent date, final hash, cleared status

### Estimated burden:
- Owner identification: ~1 hour total (5 items, known projects)
- Permission request drafting: ~2 hours (template letter, legal review)
- Await response: 1-4 weeks (owner availability)
- Document processing: ~30 minutes per item
- **Total active time: ~5 hours**
- **Total calendar time: 1-4 weeks**

### Risk factors:
- Owners may decline permission (lose that corpus item)
- Owners may grant restricted-internal only (blocks external release)
- Owners may require attribution or co-authorship (governance burden)
- Historical snapshots may be irretrievable (lose historical comparison)

## 7. Synthetic Fixtures Status

Location: [fixtures/synthetic/](../../fixtures/synthetic/)

**Status:** Project-owned, no external clearance needed

### Available fixture types:
- `citation/`: Citation identity and formatting tests
- `equation/`: Mathematical expression preservation tests
- `macro/`: LaTeX macro expansion tests
- `register/`: Writing style and register compliance tests
- `table/`: Tabular data preservation tests

**Rights:** All synthetic fixtures are humanvoice project artifacts; no external permissions required.

**Limitation:** Synthetic fixtures validate *properties* (does citation preservation work?) but not *performance* (does it work on real 40-page papers?).

## 8. G4 Handoff Implications

### For internal handoff (sponsor is project owner):
- Current rights status is acceptable
- Prototype works on synthetic fixtures
- Real-document performance is unvalidated
- **G4 decision can proceed with documented limitation**

### For external release (public benchmark, independent readers):
- Current rights status **blocks release**
- All 5 corpus items must be cleared or replaced with cleared alternatives
- Historical sources must be frozen with answer keys
- **G4 decision is "revise" (clear rights) or "stop" (abandon external release)**

### For academic publication (paper about humanvoice):
- Prototype description: ✓ permitted (no corpus redistribution)
- Synthetic fixture results: ✓ permitted (project-owned)
- ZLB/BGS case studies: ✗ blocked without clearance
- Historical comparison: ✗ blocked (no answer keys)
- **Can publish prototype description; cannot publish corpus-based validation**

## 9. Alternatives to Corpus Clearance

### Option A: Expand synthetic fixture coverage
- Create larger synthetic documents (15,000 words, 40 pages)
- Add synthetic evidence and authoring briefs
- Measure cost/burden on synthetic corpus
- **Pro:** No external permissions needed, full control
- **Con:** Doesn't prove real-document performance, less compelling for external audiences

### Option B: Use public-domain or CC-licensed academic papers
- Identify arXiv papers with permissive licenses
- Create ground-truth answer keys manually
- Replace BGS/ZLB with cleared corpus
- **Pro:** Clearable for external release
- **Con:** 20-40 hours to create answer keys per document, no historical repair comparison

### Option C: Obtain clearance for 1-2 key items (e.g., ZLB)
- Prioritize ZLB as the primary benchmark
- Focus clearing effort on single best case
- Accept that other items remain internal-only
- **Pro:** Lower burden than clearing all 5
- **Con:** Still requires 1-4 weeks, owner may decline

### Option D: Restrict to internal evaluation, defer external release
- Complete WP6 handoff with synthetic fixtures only
- Document rights as blocking issue for external release
- Defer external release to future work (post-G4)
- **Pro:** Unblocks G4 decision, completes v1.1 scope
- **Con:** No external validation, limits impact

## 10. Recommendations

### Immediate (for G4 handoff 2026-08-29):
1. **Document limitation:** G4 memo must state that rights are pending and external release is blocked
2. **Proceed with synthetic fixtures:** Cost/burden analysis based on synthetic corpus is acceptable for internal decision
3. **Defer clearance:** Obtaining written permission is 1-4 weeks; don't gate G4 on it

### Short-term (post-G4, if proceeding):
4. **Initiate clearance for ZLB:** Single high-value benchmark, document the clearing process
5. **Create one large synthetic document:** 15,000 words, validate cost model
6. **Freeze answer keys:** For any cleared items, create immutable ground truth

### Long-term (external release):
7. **Clear or replace all corpus items:** Required before public benchmark release
8. **Public fixture suite:** Curate CC-licensed papers as public benchmark corpus
9. **Historical reconstruction:** If BGS/ZLB owners grant permission, freeze historical snapshots with answer keys

## 11. Gap Summary for G4 Decision

| Requirement | Status | Impact on G4 | Mitigation |
|-------------|--------|--------------|------------|
| Corpus rights for internal use | ⚠ Permitted but unconfirmed | Low | Synthetic fixtures available |
| Corpus rights for external release | ✗ Blocked | **High** | Defer external release or clear rights |
| Historical answer keys | ✗ Missing | Medium | Cannot reproduce historical results; use forward-looking validation |
| Frozen source snapshots | ⚠ Current sources located, historical missing | Medium | Can measure current, cannot compare to historical |
| Consent dates | ✗ All null | Medium | Start clearance process post-G4 |

**G4 readiness:** Prototype is complete for internal evaluation; **not ready** for external release without rights clearance.

## 12. Decision Matrix

| Sponsor Goal | Rights Action | G4 Outcome | Timeline |
|--------------|---------------|------------|----------|
| Internal proof-of-concept only | None (proceed with synthetic) | Proceed | 2026-08-29 |
| Academic paper (no corpus data) | None (describe prototype only) | Proceed | 2026-08-29 |
| Academic paper (with ZLB case) | Clear ZLB only | Revise (1-4 weeks) | 2026-09-26 |
| Public benchmark release | Clear all 5 items or replace | Revise (4-8 weeks) | 2026-10-24 |
| External readers try it | Clear all items + create answer keys | Revise (8-12 weeks) | 2026-11-21 |

**Recommended decision for 2026-08-29 G4:** Proceed with internal handoff, document rights as blocking issue for external release, initiate ZLB clearance process as next step.
