#!/usr/bin/env python3
"""Refresh reproducible facts about the built Humanvoice manuscript."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path

from check_humanvoice_document import _word_count, expand_inputs, main_route
from check_visual_density import density_summary, parse_visuals


ROOT = Path(__file__).resolve().parents[1]
SURVEY = ROOT / "docs" / "survey"
SOURCE = SURVEY / "humanvoice_survey.tex"
PDF = SURVEY / "humanvoice_survey.pdf"
AUX = SURVEY / "humanvoice_survey.aux"
STATUS = SURVEY / "humanvoice_document_status.json"
EVIDENCE_STATUS = SURVEY / "humanvoice_evidence_status.json"
INPUT = re.compile(r"\\input\{([^}]+)\}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def route_inputs() -> list[Path]:
    """Return reader-facing input files in source order, excluding appendices."""
    result: list[Path] = []
    seen: set[Path] = set()

    def visit(path: Path, text: str) -> None:
        for name in INPUT.findall(text):
            child = (path.parent / name).with_suffix(".tex").resolve()
            if child in seen:
                continue
            seen.add(child)
            result.append(child)
            visit(child, child.read_text(encoding="utf-8"))

    visit(SOURCE, SOURCE.read_text(encoding="utf-8").split("\\appendix", 1)[0])
    return result


def route_hash(paths: list[Path]) -> str:
    lines = "".join(
        f"{sha256(path)}  {path.relative_to(ROOT)}\n" for path in paths
    )
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def document_date(source: str) -> str:
    match = re.search(r"\\date\{([^}]+)\}", source)
    if not match:
        return dt.date.today().isoformat()
    return dt.datetime.strptime(match.group(1), "%d %B %Y").date().isoformat()


def page_count() -> int:
    output = subprocess.run(
        ["pdfinfo", str(PDF)], check=True, capture_output=True, text=True
    ).stdout
    match = re.search(r"^Pages:\s+(\d+)$", output, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("pdfinfo did not report a page count")
    return int(match.group(1))


def extracted_word_count() -> int:
    output = subprocess.run(
        ["pdftotext", str(PDF), "-"], check=True, capture_output=True, text=True
    ).stdout
    return len(output.split())


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    status = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.is_file() else {}
    evidence = json.loads(EVIDENCE_STATUS.read_text(encoding="utf-8"))
    visuals = density_summary(parse_visuals(AUX.read_text(encoding="utf-8")))
    route = main_route(expand_inputs(source, SOURCE.parent))
    inputs = route_inputs()
    pages = page_count()

    status.update(
        {
            "canonical_source": str(SOURCE.relative_to(ROOT)),
            "rendered_artifact": str(PDF.relative_to(ROOT)),
            "document_role": "single_reader_facing_proposal_and_evidence_survey",
            "promotion_state": "author_repaired_draft",
            "human_acceptance": "pending_project_owner",
            "independent_reader_review": "pending",
            "evidence_status": "incomplete",
            "evidence_status_file": str(EVIDENCE_STATUS.relative_to(ROOT)),
            "audit_records": "docs/survey/audit/latest/",
            "updated_at": document_date(source),
            "source_sha256": sha256(SOURCE),
            "source_sha256_scope": (
                "top-level TeX entry point; route_source_sha256 is the SHA-256 "
                "of newline-terminated '<sha256>  <repository-relative path>' "
                "lines for recursively expanded pre-appendix inputs in source order"
            ),
            "route_source_sha256": route_hash(inputs),
            "rendered_sha256": sha256(PDF),
            "build_source_date_epoch": 1787529600,
            "page_count": pages,
            "extracted_word_count": extracted_word_count(),
            "main_route_word_count": _word_count(route),
            "figure_count": visuals["figures"],
            "table_count": visuals["tables"],
            "numbered_visual_count": visuals["total"],
            "pages_per_numbered_visual": round(float(visuals["pages_per_visual"]), 2),
            "largest_visual_page_gap": visuals["largest_page_gap"],
            "render_inspection": "agent-checked-all-figure-pages; independent reader pending",
            "note": (
                f"The canonical PDF is one {pages}-page proposal and evidence survey. "
                f"It contains {visuals['figures']} figures and {visuals['tables']} tables, "
                f"or one numbered visual per {visuals['pages_per_visual']:.2f} body pages "
                f"through the last visual. The current evidence audit passes "
                f"{evidence['passed_gates']} of {evidence['total_gates']} gates. "
                "Challenge-query recall, independent screening, full-text verification "
                "and appraisal, held-out package benchmarks, and external review remain "
                "blocked. Project-owner acceptance and an independent reader review are pending."
            ),
        }
    )
    STATUS.write_text(json.dumps(status, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(
        f"Updated {STATUS.relative_to(ROOT)}: pages={status['page_count']} "
        f"figures={status['figure_count']} tables={status['table_count']} "
        f"evidence_gates={evidence['passed_gates']}/{evidence['total_gates']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
