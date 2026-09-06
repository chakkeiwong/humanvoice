# Corpus Rights Clearance Process

**Status:** 0 of 5 items cleared (as of 2026-08-29)  
**Timeline:** 4-8 weeks for external coordination

---

## Overview

Per contract 1.1.0 and `corpus_rights_manifest.json`, no corpus item may be published, redistributed, sent to an external reader, or used for commercial training until its owner and permission are recorded. All five current corpus items have `redistribution_status: "pending-clearance"` and `consent_date: null`.

This directory tracks the clearance process: owner identification, permission requests, responses, and fallback alternatives.

---

## Items Requiring Clearance

| ID | Source | Owner | Status |
|---|---|---|---|
| CORP-BGS | `DynareMCP/docs/AIpostdoc/finalBGS/` | DynareMCP project: pending confirmation | Pending |
| CORP-ZLB | `BayesFilter/docs/surveys/zlb_discontinuous_hmc/` | BayesFilter project: pending confirmation | Pending |
| CORP-SMEWALLET | `SMEwallet/docs/handoffs/` | SMEwallet project: pending confirmation | Pending |
| CORP-CARDNPV | `cardnpv/docs/final/` | CardNPV project: pending confirmation | Pending |
| CORP-MACROFINANCE | `MacroFinance/docs/latex-papers/CIP_monograph/` | MacroFinance project: pending confirmation | Pending |

---

## Process

### Step 1: Owner Identification

For each item, determine:
- Who created the source material
- Whether it's an internal project (need organizational permission) or external (need copyright holder)
- Contact information (email, project page)

**Output:** `<record-id>_owner_identification.md` documenting:
- Source repository/path
- Creation date
- Author(s)
- Current rights holder
- Contact method

### Step 2: Permission Request

Draft and send a clearance request explaining:
- **Context:** Internal evaluation fixture for humanvoice authoring system
- **Current use:** Bounded testing during development (not redistributed)
- **Proposed use:** Include in external release as evaluation corpus
- **Scope:** Snapshot will be frozen with SHA-256 hash; no modifications
- **Attribution:** Original source credited in corpus manifest
- **No commercial training:** Corpus used only for evaluation, not model training

**Template:** `permission_request_template.md` (below)

**Output:** `<record-id>_request_sent_YYYY-MM-DD.md` with:
- Date sent
- Recipient
- Request text (or reference to template)
- Response deadline (suggested: 2-3 weeks)

### Step 3: Response Tracking

For each request, record:
- Date of response (or no response after deadline)
- Permission granted / denied / conditional
- Conditions (if any): attribution, non-commercial, time-limited, etc.
- Written confirmation (email, license file)

**Output:** `<record-id>_response_YYYY-MM-DD.md`

### Step 4: Consent Recording

For granted permissions:
- Copy written confirmation to `<record-id>_consent.txt` or `.pdf`
- Update `corpus_rights_manifest.json`:
  - `owner`: confirmed rights holder
  - `license_or_permission`: "Written permission granted YYYY-MM-DD" or license name
  - `permitted_use`: "internal and external evaluation" (or as specified)
  - `redistribution_status`: "cleared-for-external-release"
  - `consent_date`: ISO 8601 date of permission
  - `source_hash`: SHA-256 hash of frozen snapshot

**Output:** Updated manifest + consent artifact

### Step 5: Fallback Alternatives

For denied permissions or no response after 4 weeks:
- Identify public-domain alternative:
  - arXiv papers (permissive license)
  - Government reports (public domain in many jurisdictions)
  - Open-access publications (CC-BY or similar)
  - Synthetic fixtures (no clearance needed)
- Replace corpus item with alternative
- Update manifest to remove denied item, add cleared alternative

**Output:** `<record-id>_fallback.md` documenting replacement

---

## Permission Request Template

Save as `permission_request_template.md`:

```markdown
Subject: Permission Request: Use of [PROJECT] Material in Evaluation Corpus

Dear [OWNER NAME],

I am writing to request permission to include material from [PROJECT SOURCE]
in the evaluation corpus for humanvoice, an open-source technical authoring
system under development.

## Current Use (Internal Evaluation)

The material has been used internally as a test fixture during development.
It has not been redistributed, published externally, or used for commercial
purposes. Current use is limited to bounded testing by the development team.

## Proposed Use (External Release)

I would like to include a frozen snapshot of the material in the external
release of humanvoice as part of the evaluation corpus. The corpus demonstrates
the system's capability to process domain-specific technical documents.

## Scope and Attribution

- **Snapshot:** The material will be frozen at its current state with a
  SHA-256 hash. No modifications will be made.
- **Attribution:** The original source will be credited in the corpus manifest
  (`docs/survey/evidence/corpus_rights_manifest.json`).
- **Use:** Evaluation only. The corpus will not be used for commercial
  training of machine learning models.
- **License:** The overall humanvoice project is [LICENSE TBD], but the
  corpus material will retain your specified license or permission terms.

## Alternatives

If you prefer not to grant permission, I will replace the material with a
public-domain alternative (arXiv papers, government reports, or synthetic
fixtures). No action is required to decline — a lack of response within
3 weeks will be interpreted as a preference not to participate.

## Confirmation

If you are willing to grant permission, a brief email reply confirming:

  "I grant permission for [MATERIAL PATH] to be included in the humanvoice
   evaluation corpus under the terms described above."

...is sufficient. If you have specific conditions (e.g., attribution format,
non-commercial only, time limit), please state them and I will honor them.

Thank you for considering this request.

Best regards,
[YOUR NAME]
[CONTACT EMAIL]
```

---

## Status Updates

As responses arrive, update this file with:

### [YYYY-MM-DD] Update

- **Item:** CORP-XXX
- **Action:** Sent request / Received response / Updated manifest / Fallback selected
- **Outcome:** Granted / Denied / No response / Replaced

---

## Completion Criteria

Blocker 1 is complete when:

1. All 5 items have `redistribution_status` other than "pending-clearance", OR
2. Denied/no-response items are replaced with cleared alternatives, AND
3. `corpus_rights_manifest.json` has `status: "complete"`

**Acceptance:** The corpus can be redistributed in the external release without
legal or ethical risk. No item ships without documented owner consent or
public-domain status.

---

## Timeline

| Week | Activity |
|---|---|
| 1 | Identify owners, draft requests |
| 2 | Send requests |
| 3-4 | Await responses |
| 5-6 | Follow-up or begin fallback research |
| 7-8 | Finalize manifest with cleared items or alternatives |

**Critical path:** Week 4. After 4 weeks, any item without a response should
be replaced rather than waiting indefinitely.

---

## Risk Mitigation

If all 5 items are denied or no response:
- **Plan A:** Use public-domain corpus (arXiv economics papers, NBER reports)
- **Plan B:** Use only synthetic fixtures (register/001.tex and similar)
- **Documentation:** Note corpus limitation in release notes

A synthetic-only corpus is a known limitation, not a blocker. The system can
demonstrate its gates and pipeline without third-party corpus material. The
limitation is that external readers cannot evaluate it on real-world documents
from other domains.

---

## Next Steps

1. **Immediate (Week 1):** Complete owner identification for all 5 items
2. **Week 2:** Send permission requests
3. **Week 4 check-in:** Tally responses, initiate fallback research if needed
4. **Week 8 deadline:** Finalize manifest with cleared items
