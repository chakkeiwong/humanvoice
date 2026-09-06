# Humanvoice audit runner

The executable is `tools/survey_audit.py`. It creates an auditable run folder,
not a hidden agent summary.

```bash
python tools/survey_audit.py run --execute-tools --build-pdf --output docs/survey/audit/latest --replace-output
python tools/survey_audit.py validate --run docs/survey/audit/latest
python tools/survey_audit.py publish --run docs/survey/audit/latest
```

The runner refuses to use a non-empty output directory. Choose a fresh path,
or pass `--replace-output` when deliberately rebuilding an existing run; the
old directory is moved to a timestamped `.previous-*` sibling and is not
deleted.

For a reproducible public-domain supplement, collect the ACL Anthology export
before running the audit:

```bash
python tools/survey_audit.py collect-public
```

The command keeps the raw ACL, NBER, and ICLR responses and their hashes under
`public_raw/`, and writes filtered CSVs plus provenance sidecars under
`imports/`. It does not replace licensed EconLit, RePEc, SSRN, ACM, IEEE, Web
of Science, or Scopus exports.

The public ACL/NBER/ICLR slices satisfy only the general public-import gate.
The specialist-domain gate requires at least one provenance-complete EconLit,
RePEc/IDEAS, SSRN, ACM, IEEE, Web of Science, or Scopus export. The current
run satisfies that gate with the bounded RePEc/IDEAS slice described below;
the slice is not an exhaustive economics search.

For a bounded economics-domain supplement, run the official IDEAS/RePEc
collector (it preserves five declared query responses and their hashes):

```bash
python tools/collect_repec.py
```

Prepare blank, hash-bound human-review overlays from the completed run with:

```bash
python tools/prepare_review_packets.py --run docs/survey/audit/latest
```

The packet utility never fills reviewer decisions. It refuses to overwrite an
existing packet unless `--force` is supplied, and its manifest records the
source queue hashes.

Use `--online` in an environment with outbound access to query OpenAlex,
Crossref, and GitHub. Raw JSON responses, query status, timestamps, and hashes
are kept under `latest/raw/`. Without `--online`, the program still inventories
the local bibliography, checked-in evidence seeds, and vendored packages, but
the known-item recall gate fails deliberately.

The protocol is `docs/survey/audit_protocol.json`. It defines the questions,
search families, broad-recall and exact-challenge known-item tests, frozen
inclusion classes and exclusion codes, design-specific appraisal methods,
software categories, adoption candidates, and release gates. The checked-in
evidence file is a pilot seed, not a substitute for full-text extraction.

## Review workflow

1. Run the pipeline online and preserve the generated run folder.
2. Add exports from EconLit, RePEc/IDEAS, NBER, SSRN, ACM, ACL, IEEE, and any
   licensed index to `imports/`. CSV, JSON, and BibTeX exports must include a
   provenance sidecar; the required fields are documented in `imports/README.md`.
3. Copy `latest/screening_queue.csv` to `imports/screening_review.csv` and have
   two independent reviewers fill `reviewer_1`, `reviewer_2`, `adjudication`,
   `exclusion_code` where applicable, and `full_text_verified`. The queue
   includes every known-item challenge and
   a deterministic first-pass sample; the complete `screening.csv` remains the
   discovery ledger. The next run overlays those edits without changing the
   generated source sheet.
4. Copy `latest/evidence.csv` to `imports/evidence_review.csv` and add full-text
   inspection, a page/section `claim_anchor`, design classification,
   design-specific appraisal, extracted limitations, and
   `independent_verification=verified` for load-bearing empirical claims.
5. Run package adapters against the locked corpus. A smoke test is not an
   effectiveness result; adoption candidates need held-out labeled evaluation.
6. Replace `review_signoff.json` only after an independent librarian and an
   economics/HCI reviewer have signed off.

The evidence record remains incomplete until these conditions are satisfied.
It is supporting repository material for the single manuscript
`docs/survey/humanvoice_survey.tex`; a coherent generated dossier is not
evidence of search recall, study eligibility, package effectiveness, or
external review.

New runs emit `implementation_dossier.md`, `.tex`, and optionally `.pdf`.
Preserved runs created before the reader-facing proposal was separated may use
the legacy `final_product_proposal.*` names internally. In either case,
the dossier and audit report remain inside the audit run. `publish` copies only
machine-readable requirements and status summaries to `docs/survey/`; it cannot overwrite the
canonical manuscript `humanvoice_survey.tex` or its rendered PDF and status
file. The old `humanvoice_product_proposal.*` names are protected legacy
aliases and are retained only in the archive or preserved audit runs.

## Gate ownership and exit conditions

| Gate | Required input | Owner and objective exit condition |
|---|---|---|
| `manual-independent-screening` | `imports/screening_review.csv` | Two named reviewers independently complete the selected queue; an adjudicator records one include/exclude decision and a frozen exclusion code where needed. |
| `specialist-domain-coverage` | A sidecar-backed export from EconLit, RePEc/IDEAS, SSRN, ACM Digital Library, IEEE Xplore, Web of Science, or Scopus | The research steward verifies byte hash, query, retrieval time, and database identity; at least one provenance-complete specialist database is present. |
| `full-text-load-bearing-evidence` | `imports/evidence_review.csv` | A domain reviewer records full-text/page or section inspection and `independent_verification=verified` for every load-bearing empirical/review row. |
| `critical-appraisal` | The same evidence review overlay | The research-methods reviewer classifies each design, applies the protocol tool, records a claim anchor and limitations, and uses only `completed-low-concern` or `completed-some-concerns` for release claims. |
| `package-held-out-benchmark` | Locked corpus, adapters, and `package_benchmark_results.json` | The evaluation lead runs every adoption candidate on untouched labeled documents; only `effectiveness-pass` plus an independent review can change a package from hold to adopt. |
| `external-review` | `review_signoff.json` | An independent librarian and economics/HCI reviewer provide names, scope, date, and `status=approved`; the file is never self-approved by the implementer. |

The other gates are recomputed by the runner. A passing metadata or smoke check
does not override any of these six release conditions.

Each run also emits `screening_queue.csv`, `review_flow.json`,
`critical_appraisal_queue.csv`, `evidence_identity_audit.csv`,
`bibliography_identity_audit.csv`, and `bibliography_identity_summary.json`,
`package_selection.json`, `evaluation_plan.json`, and
`requirements_traceability.csv`, `requirements_traceability.json`, and
`artifact_manifest.json`. Together with the implementation dossier, they
expose pending human work, distinguish bibliographic identity from claim
verification, record adopt/hold decisions, specify the pilot, and verify every
generated byte after the PDF build.
