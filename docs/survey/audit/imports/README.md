# Manual database imports

This directory contains reproducible public ACL, NBER, and ICLR slices. Add
licensed exports from the other domain databases named in
`../../audit_protocol.json`, preserving the original export bytes and a
sidecar named either `<export>.meta.json` or
`<stem>.meta.json`. Accepted formats are JSON (a list of records, or
`{ "records": [...] }`), CSV, and BibTeX (`.bib`/`.bibtex`).

The sidecar must identify the provenance of the bytes:

```json
{
  "database": "ACL Anthology",
  "source_url": "https://aclanthology.org/anthology.bib.gz",
  "retrieved_at": "2026-08-22T00:00:00Z",
  "sha256": "<sha256 of the export file>",
  "query_or_filter": "writing feedback OR human-AI collaboration",
  "raw_source_path": "docs/survey/audit/public_raw/original-export.bin",
  "raw_source_sha256": "<sha256 of the original downloaded bytes>"
}
```

Literature records should contain at least `title`, `authors`, `year`, `doi`
or `url`, and `abstract` when the export supplies it. Software records should
contain `record_type=software`, `name`, `repository` or `url`, and a version or
commit. The pipeline copies the provenance into the candidate trail, checks
the sidecar hash, and counts only provenance-complete records toward the
`domain-database-imports` gate. A missing or incomplete export remains visible
but cannot be mistaken for evidence of search coverage.

Screening and evidence review overlays are different from database exports.
`screening_review.csv` must retain the generated `screening_id` and record
independent `reviewer_1` and `reviewer_2` decisions (`include`, `exclude`, or
`uncertain`), final `adjudication` (`include` or `exclude`), and one frozen
`exclusion_code` for every exclusion. `evidence_review.csv` must retain the
evidence `id` and add the full-text `claim_anchor`, design classification,
appraisal tool and status, extracted limitations, reviewer, and
`independent_verification=verified` where warranted.

The repository also includes `tools/collect_repec.py`. It makes five bounded
queries through the official IDEAS/RePEc search form and preserves the raw HTML
responses under `docs/survey/audit/public_raw/repec/`. The resulting
`repec_ideas_writing.csv` is a specialist discovery slice, not a complete
RePEc export; its sidecar records that limitation. Do not treat its
title/abstract records as included studies until the independent screening and
full-text gates pass.
