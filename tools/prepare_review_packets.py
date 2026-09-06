#!/usr/bin/env python3
"""Prepare deterministic human-review overlays from a completed audit run.

The audit runner keeps generated discovery and extraction sheets immutable and
reads human decisions from ``docs/survey/audit/imports``.  This utility creates
the blank overlay templates without copying provisional values into reviewer
fields.  It is deliberately a preparation step: it cannot mark a row included,
verified, or appraised.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "docs" / "survey" / "audit" / "latest"
DEFAULT_OUTPUT = ROOT / "docs" / "survey" / "audit" / "imports"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def generated_context(row: dict[str, str], prefix: str, fields: list[str]) -> dict[str, str]:
    """Copy machine output under an explicit prefix, never into review cells."""
    return {f"{prefix}{field}": row.get(field, "") for field in fields}


def prepare_screening(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    fields = [
        "screening_id",
        "candidate_identity",
        "known_item",
        "title",
        "source",
        "year",
        "doi",
        "identifier",
        "full_text_url",
        "generated_screening_decision",
        "generated_screening_reason",
        "reviewer_1",
        "reviewer_2",
        "adjudication",
        "exclusion_code",
        "full_text_verified",
        "screening_notes",
    ]
    output: list[dict[str, str]] = []
    for row in rows:
        item = {
            **{key: row.get(key, "") for key in fields if not key.startswith("generated_")},
            **generated_context(row, "generated_", ["screening_decision", "screening_reason"]),
        }
        for field in ("reviewer_1", "reviewer_2", "adjudication", "exclusion_code", "full_text_verified", "screening_notes"):
            item[field] = ""
        output.append(item)
    return output, fields


def prepare_evidence(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    fields = [
        "id",
        "question_ids",
        "source_type",
        "title",
        "authors",
        "year",
        "doi",
        "url",
        "local_path",
        "finding",
        "implication",
        "load_bearing",
        "generated_study_design",
        "generated_appraisal_tool",
        "inspection",
        "claim_anchor",
        "limitations",
        "confidence",
        "appraisal_tool",
        "appraisal_status",
        "reviewer",
        "independent_verification",
        "review_notes",
    ]
    generated_fields = ["study_design", "appraisal_tool"]
    output: list[dict[str, str]] = []
    for row in rows:
        item = {key: row.get(key, "") for key in fields if not key.startswith("generated_")}
        item.update(generated_context(row, "generated_", generated_fields))
        for field in (
            "inspection",
            "claim_anchor",
            "limitations",
            "confidence",
            "appraisal_tool",
            "appraisal_status",
            "reviewer",
            "independent_verification",
            "review_notes",
        ):
            item[field] = ""
        output.append(item)
    return output, fields


def packet_readme(run: Path, screening_count: int, evidence_count: int) -> str:
    run_label = str(run.relative_to(ROOT)) if run.is_relative_to(ROOT) else str(run)
    return f"""# Humanvoice review packet

This packet was generated from `{run_label}` on
`{dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()}`.

It is a blank review overlay, not a result. The generated source sheets remain
in the run directory. Two people must work independently, without copying one
another's decisions. Use only the protocol's values:

- screening: `include`, `exclude`, or `uncertain`; adjudication is `include` or
  `exclude`; every exclusion receives one frozen code `E1`--`E7`;
- evidence: cite a page, table, figure, section, or paragraph in
  `claim_anchor`; classify the design; record the protocol appraisal tool and
  status; state limitations; use `independent_verification=verified` only after
  a reviewer has inspected the full text.

The packet contains {screening_count} screening rows and {evidence_count}
load-bearing evidence rows. Empty reviewer cells are intentional. Do not fill
them from the generated columns, and do not edit the generated audit sheets.

After independent review, place the completed files at:

- `docs/survey/audit/imports/screening_review.csv`
- `docs/survey/audit/imports/evidence_review.csv`

Then rerun the audit and retain the resulting overlay summary. A named
independent librarian and an economics/HCI reviewer must still sign
`docs/survey/audit/review_signoff.json` before release.
"""


def prepare(run: Path, output: Path, force: bool = False) -> dict[str, Any]:
    required = [run / "screening_queue.csv", run / "critical_appraisal_queue.csv", run / "run_metadata.json"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError("missing audit artifacts: " + ", ".join(missing))
    output.mkdir(parents=True, exist_ok=True)
    targets = [output / "screening_review.csv", output / "evidence_review.csv", output / "review_packet_README.md"]
    if not force:
        existing = [str(path) for path in targets if path.exists()]
        if existing:
            raise ValueError("refusing to overwrite existing review files; use --force: " + ", ".join(existing))

    screening, screening_fields = prepare_screening(read_csv(required[0]))
    evidence, evidence_fields = prepare_evidence(read_csv(required[1]))
    screening_path = output / "screening_review.csv"
    evidence_path = output / "evidence_review.csv"
    readme_path = output / "review_packet_README.md"
    write_csv(screening_path, screening, screening_fields)
    write_csv(evidence_path, evidence, evidence_fields)
    readme_path.write_text(packet_readme(run, len(screening), len(evidence)), encoding="utf-8")
    manifest = {
        "status": "prepared-blank-overlay",
        "source_run": str(run.relative_to(ROOT) if run.is_relative_to(ROOT) else run),
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "screening_rows": len(screening),
        "evidence_rows": len(evidence),
        "reviewer_decisions": "none",
        "source_artifacts": {
            "screening_queue.csv": sha256(run / "screening_queue.csv"),
            "critical_appraisal_queue.csv": sha256(run / "critical_appraisal_queue.csv"),
            "artifact_manifest.json": sha256(run / "artifact_manifest.json") if (run / "artifact_manifest.json").is_file() else "",
        },
        "files": {
            "screening_review.csv": {"sha256": sha256(screening_path), "rows": len(screening)},
            "evidence_review.csv": {"sha256": sha256(evidence_path), "rows": len(evidence)},
            "review_packet_README.md": {"sha256": sha256(readme_path)},
        },
    }
    # The manifest intentionally does not contain its own hash: a self-hash
    # would change every time it was written and could never be verified.
    manifest_path = output / "review_packet_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="replace existing blank templates; never use after human edits")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.run.resolve(), args.output.resolve(), args.force)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"review packet preparation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
