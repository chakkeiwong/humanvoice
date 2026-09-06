#!/usr/bin/env python3
"""Reproducible humanvoice literature and software audit.

The command deliberately separates discovery, screening, evidence extraction,
and product synthesis.  It can run offline from checked-in seeds, but an
offline run is never reported as exhaustive.  Network discovery is optional
and all responses, queries, errors, and hashes are written to the run folder.

Examples:
    python tools/survey_audit.py run --output /tmp/humanvoice-audit
    python tools/survey_audit.py run --online --output /tmp/humanvoice-audit
    python tools/survey_audit.py validate --run docs/survey/audit/latest
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - urllib fallback is intentional
    requests = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = ROOT / "docs" / "survey" / "audit_protocol.json"
DEFAULT_SEEDS = ROOT / "docs" / "survey" / "evidence" / "pilot_evidence.json"
DEFAULT_OUTPUT = ROOT / "docs" / "survey" / "audit" / "latest"
USER_AGENT = "humanvoice-survey-audit/1.0 (reproducible research pipeline)"
HTTP_TIMEOUT_SECONDS = 8

DOSSIER_ARTIFACTS = {
    "markdown": "implementation_dossier.md",
    "tex": "implementation_dossier.tex",
    "pdf": "implementation_dossier.pdf",
    "render": "dossier_render.json",
}
LEGACY_DOSSIER_ARTIFACTS = {
    "markdown": "final_product_proposal.md",
    "tex": "final_product_proposal.tex",
    "pdf": "final_product_proposal.pdf",
    "render": "proposal_render.json",
}
# These paths belong to the authored reader-facing manuscript.  The older
# Markdown proposal names remain protected as legacy aliases so a stale command
# cannot silently recreate a second public narrative.
CANONICAL_PROPOSAL_ARTIFACTS = frozenset(
    {
        "humanvoice_survey.tex",
        "humanvoice_survey.pdf",
        "humanvoice_document_status.json",
        "humanvoice_product_proposal.md",
        "humanvoice_product_proposal.tex",
        "humanvoice_product_proposal.pdf",
        "humanvoice_product_proposal_status.json",
    }
)
EVIDENCE_PUBLICATION_NAMES = frozenset(
    {
        "humanvoice_product_requirements.csv",
        "humanvoice_product_requirements.json",
        "humanvoice_evidence_status.json",
    }
)
if CANONICAL_PROPOSAL_ARTIFACTS & EVIDENCE_PUBLICATION_NAMES:
    raise RuntimeError("authored proposal and evidence publication paths overlap")


class AuditFailure(RuntimeError):
    pass


def dossier_artifacts(run_dir: Path) -> dict[str, str]:
    """Resolve current or legacy dossier names without rewriting a run."""
    current_required = ("markdown", "tex", "render")
    if all((run_dir / DOSSIER_ARTIFACTS[key]).is_file() for key in current_required):
        return dict(DOSSIER_ARTIFACTS)
    if all((run_dir / LEGACY_DOSSIER_ARTIFACTS[key]).is_file() for key in current_required):
        return dict(LEGACY_DOSSIER_ARTIFACTS)
    return dict(DOSSIER_ARTIFACTS)


def evidence_publication_pairs(artifacts: dict[str, str]) -> tuple[tuple[str, str], ...]:
    """Return the only backstage summaries an audit run may publish.

    The full dossier remains in the audit run directory.  Copying it beside
    the authored proposal would create a second document for readers to
    interpret, so publication is limited to machine-readable status and the
    compact audit trace.
    """
    pairs = (
        ("requirements_traceability.csv", "humanvoice_product_requirements.csv"),
        ("requirements_traceability.json", "humanvoice_product_requirements.json"),
    )
    destinations = {destination for _, destination in pairs}
    if destinations & CANONICAL_PROPOSAL_ARTIFACTS:
        raise AuditFailure("audit publication attempted to overwrite the reader-facing manuscript")
    return pairs


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True, sort_keys=True)
        handle.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def path_label(path: Path, base: Path = ROOT) -> str:
    """Return a stable relative label when a path is inside the repository."""
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str:
    """Rebuild OpenAlex's inverted-index abstract representation."""
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, offsets in inverted.items():
        for offset in offsets:
            positions.append((int(offset), word))
    return " ".join(word for _, word in sorted(positions))


def normalize(value: str) -> str:
    value = value or ""
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_doi(value: Any) -> str:
    """Normalize DOI display forms without accepting non-DOI identifiers."""
    doi = str(value or "").strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = doi.replace(r"\_", "_").strip().rstrip(".,;)")
    return doi if re.match(r"^10\.\d{4,9}/\S+$", doi, flags=re.I) else ""


def title_key(value: str) -> str:
    words = normalize(value).split()
    stop = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    return " ".join(word for word in words if word not in stop)


def slug(value: str) -> str:
    result = normalize(value).replace(" ", "-")
    return result[:80] or "item"


def validate_inputs(protocol: Any, seeds: Any) -> dict[str, Any]:
    """Validate the frozen protocol and evidence seed before doing any work."""
    errors: list[str] = []
    if not isinstance(protocol, dict):
        return {"status": "fail", "errors": ["protocol must be a JSON object"], "counts": {}}
    if not isinstance(seeds, list):
        return {"status": "fail", "errors": ["evidence seed must be a JSON array"], "counts": {}}

    def unique_nonempty(label: str, values: list[Any]) -> set[str]:
        clean = [str(value).strip() for value in values]
        for index, value in enumerate(clean, start=1):
            if not value:
                errors.append(f"{label}[{index}] is empty")
        duplicates = sorted({value for value in clean if value and clean.count(value) > 1})
        if duplicates:
            errors.append(f"{label} contains duplicates: {', '.join(duplicates)}")
        return {value for value in clean if value}

    questions = protocol.get("questions", [])
    if not isinstance(questions, list) or not questions:
        errors.append("questions must be a nonempty array")
        questions = []
    question_ids = unique_nonempty("question IDs", [row.get("id", "") for row in questions if isinstance(row, dict)])
    for row in questions:
        if not isinstance(row, dict) or not str(row.get("text", "")).strip():
            errors.append("every question requires nonempty id and text")

    literature = protocol.get("literature", {})
    sources = literature.get("sources", [])
    public_sources = literature.get("public_export_sources", [])
    source_ids = unique_nonempty(
        "literature source IDs",
        [row.get("id", "") for row in sources + public_sources if isinstance(row, dict)],
    )
    known_items = literature.get("known_items", [])
    known_item_ids = unique_nonempty("known-item IDs", [row.get("id", "") for row in known_items if isinstance(row, dict)])
    exclusion_rows = literature.get("eligibility", {}).get("exclude", [])
    exclusion_codes = unique_nonempty("exclusion codes", [row.get("code", "") for row in exclusion_rows if isinstance(row, dict)])

    evidence_ids = unique_nonempty("evidence IDs", [row.get("id", "") for row in seeds if isinstance(row, dict)])
    required_evidence = ["id", "source_type", "question_ids", "inspection", "finding", "implication", "confidence", "load_bearing", "source_provenance", "title", "authors", "year"]
    required_evidence.extend(protocol.get("evidence_extraction", {}).get("required_fields", []))
    required_evidence = list(dict.fromkeys(required_evidence))
    doi_pattern = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
    design_tools = set(literature.get("critical_appraisal", {}).get("design_tools", {}))
    for index, row in enumerate(seeds, start=1):
        if not isinstance(row, dict):
            errors.append(f"evidence row {index} must be an object")
            continue
        evidence_id = str(row.get("id", f"row-{index}"))
        missing = [
            field
            for field in required_evidence
            if field not in row or row.get(field) is None or row.get(field) == ""
        ]
        if missing:
            errors.append(f"{evidence_id} missing required fields: {', '.join(missing)}")
        row_questions = row.get("question_ids", [])
        if not isinstance(row_questions, list) or not row_questions:
            errors.append(f"{evidence_id} question_ids must be a nonempty array")
        else:
            unknown = sorted(set(map(str, row_questions)) - question_ids)
            if unknown:
                errors.append(f"{evidence_id} references unknown questions: {', '.join(unknown)}")
        if not isinstance(row.get("load_bearing"), bool):
            errors.append(f"{evidence_id} load_bearing must be boolean")
        if not str(row.get("url", "")).strip() and not str(row.get("local_path", "")).strip():
            errors.append(f"{evidence_id} requires url or local_path")
        doi = str(row.get("doi", "")).strip()
        if doi and not doi_pattern.fullmatch(doi):
            errors.append(f"{evidence_id} has invalid DOI syntax: {doi}")
        design = str(row.get("study_design", "")).strip()
        if design and design not in design_tools:
            errors.append(f"{evidence_id} uses unknown study_design: {design}")

    software = protocol.get("software", {})
    registry = software.get("registry_seeds", [])
    registry_names = unique_nonempty("software seed names", [row.get("name", "") for row in registry if isinstance(row, dict)])
    registry_repositories = unique_nonempty("software repositories", [row.get("repository", "") for row in registry if isinstance(row, dict)])
    adoption = [str(value).strip() for value in software.get("adoption_candidates", [])]
    unique_nonempty("software adoption candidates", adoption)
    registry_names_normalized = {normalize(value) for value in registry_names}
    manifest_names_normalized = {normalize(row.get("name", "")) for row in read_manifest()}
    resolvable_software = registry_names_normalized | manifest_names_normalized
    unresolved_adoption = sorted(value for value in adoption if normalize(value) not in resolvable_software)
    if unresolved_adoption:
        errors.append("adoption candidates without a protocol seed or vendor pin: " + ", ".join(unresolved_adoption))

    requirements = protocol.get("product_requirements", [])
    if not isinstance(requirements, list) or not requirements:
        errors.append("product_requirements must be a nonempty array")
        requirements = []
    requirement_ids = unique_nonempty("product requirement IDs", [row.get("id", "") for row in requirements if isinstance(row, dict)])
    for index, row in enumerate(requirements, start=1):
        if not isinstance(row, dict):
            errors.append(f"product requirement row {index} must be an object")
            continue
        requirement_id = str(row.get("id", f"row-{index}"))
        missing = [field for field in ("title", "statement", "acceptance_test", "evidence_ids", "phase") if not row.get(field)]
        if missing:
            errors.append(f"{requirement_id} missing requirement fields: {', '.join(missing)}")
        linked = row.get("evidence_ids", [])
        if not isinstance(linked, list) or not linked:
            errors.append(f"{requirement_id} evidence_ids must be a nonempty array")
        else:
            unknown = sorted(set(map(str, linked)) - evidence_ids)
            if unknown:
                errors.append(f"{requirement_id} references unknown evidence: {', '.join(unknown)}")

    counts = {
        "questions": len(question_ids),
        "literature_sources": len(source_ids),
        "known_items": len(known_item_ids),
        "exclusion_codes": len(exclusion_codes),
        "evidence_rows": len(evidence_ids),
        "software_seeds": len(registry_repositories),
        "adoption_candidates": len(adoption),
        "product_requirements": len(requirement_ids),
    }
    return {"status": "pass" if not errors else "fail", "errors": errors, "counts": counts}


def prepare_output_directory(output: Path, replace: bool = False) -> Path | None:
    """Create a clean run directory, preserving any explicitly replaced run."""
    backup: Path | None = None
    if output.exists() and not output.is_dir():
        raise AuditFailure(f"output path is not a directory: {output}")
    if output.is_dir() and any(output.iterdir()):
        if not replace:
            raise AuditFailure(
                f"output directory is not empty: {output}; choose a fresh --output or pass --replace-output"
            )
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = output.with_name(f"{output.name}.previous-{stamp}")
        suffix = 1
        while backup.exists():
            backup = output.with_name(f"{output.name}.previous-{stamp}-{suffix}")
            suffix += 1
        output.rename(backup)
    output.mkdir(parents=True, exist_ok=True)
    return backup


def csv_write(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def command(args: list[str], cwd: Path = ROOT, timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def repository_snapshot() -> dict[str, Any]:
    code, head, error = command(["git", "rev-parse", "HEAD"])
    code2, status, error2 = command(["git", "status", "--short"])
    tracked = []
    code3, files, _ = command(["git", "ls-files"])
    if code3 == 0:
        tracked = files.splitlines()
    return {
        "root": str(ROOT),
        "git_head": head if code == 0 else None,
        "git_error": error or None,
        "git_status": status if code2 == 0 else None,
        "tracked_file_count": len(tracked),
        "tracked_files_sha256": sha256_bytes("\n".join(tracked).encode()),
    }


def parse_bibtex_text(text: str, source_file: str) -> list[dict[str, str]]:
    """Parse BibTeX text without external dependencies."""
    starts = list(re.finditer(r"@([A-Za-z]+)\s*\{\s*([^,]+),", text))
    records: list[dict[str, str]] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        body = text[match.end() : end]
        fields: dict[str, str] = {}
        for field in re.finditer(r"(?im)^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body):
            field_start = field.end()
            rest = body[field_start:]
            if rest.startswith("{"):
                depth = 0
                field_end = 0
                for pos, char in enumerate(rest):
                    if char == "{":
                        depth += 1
                    elif char == "}":
                        depth -= 1
                        if depth == 0:
                            field_end = pos
                            break
                value = rest[1:field_end] if field_end else rest[1:]
            elif rest.startswith('"'):
                close = rest.find('"', 1)
                value = rest[1:close] if close >= 0 else rest[1:]
            else:
                value = re.split(r"[,\n]", rest, maxsplit=1)[0]
            fields[field.group(1).lower()] = re.sub(r"\s+", " ", value).strip()
        note = fields.get("note", "")
        doi = fields.get("doi", "")
        if not doi and re.match(r"^\s*doi\s*:", note, flags=re.I):
            doi = re.sub(r"^\s*doi\s*:\s*", "", note, flags=re.I).strip()
        identifier = fields.get("eprint", "")
        if not identifier and re.match(r"^\s*arxiv\s*:", note, flags=re.I):
            identifier = re.sub(r"^\s*arxiv\s*:\s*", "arXiv:", note, flags=re.I).strip()
        url = fields.get("url", "")
        if not url and identifier.lower().startswith("arxiv:"):
            url = "https://arxiv.org/abs/" + identifier.split(":", 1)[1]
        records.append(
            {
                "key": match.group(2).strip(),
                "entry_type": match.group(1).lower(),
                "title": fields.get("title", ""),
                "author": fields.get("author", ""),
                "year": fields.get("year", ""),
                "doi": doi,
                "identifier": identifier,
                "url": url,
                "source_file": source_file,
            }
        )
    return records


def parse_bibtex(path: Path) -> list[dict[str, str]]:
    """Small dependency-free BibTeX reader for audit metadata.

    It intentionally preserves raw fields instead of trying to normalize
    every BibTeX dialect. DOI and title are sufficient for deduplication; the
    original file remains the source of truth.
    """
    return parse_bibtex_text(path.read_text(encoding="utf-8"), path_label(path))


def collect_public_acl(protocol: dict[str, Any], import_dir: Path, raw_output: Path, query_filter: str | None = None) -> dict[str, Any]:
    """Collect a transparent, filtered ACL Anthology bibliography export.

    The complete compressed bibliography is retained in ``raw_output`` while
    the import directory receives a compact CSV plus a hash/provenance
    sidecar. The filter is intentionally broad and fixed in the metadata; it
    is a discovery export, not a hand-picked evidence list.
    """
    source = next((item for item in protocol.get("literature", {}).get("public_export_sources", []) if item.get("id") == "acl-anthology"), {})
    url = source.get("url", "https://aclanthology.org/anthology.bib.gz")
    filter_text = query_filter or "title contains writing, feedback, revision, human-AI, language model, essay, or creative"
    raw_output.mkdir(parents=True, exist_ok=True)
    raw_path = raw_output / "acl_anthology.bib.gz"
    status, raw, error = http_bytes(url, raw_path, "application/gzip")
    if raw is None:
        return {"status": status, "error": error or "download failed", "raw_path": str(raw_path)}
    try:
        import gzip

        text = gzip.decompress(raw).decode("utf-8", errors="replace")
    except Exception as exc:
        return {"status": "parse-error", "error": str(exc), "raw_path": str(raw_path), "raw_sha256": sha256_bytes(raw)}
    records = parse_bibtex_text(text, str(raw_path))
    terms = ("writing", "feedback", "revision", "human ai", "language model", "essay", "creative", "authoring")
    selected: list[dict[str, Any]] = []
    for record in records:
        title = normalize(record.get("title", ""))
        if not title or not any(term in title for term in terms):
            continue
        author = record.get("author", "").replace("\n", " ")
        selected.append(
            {
                "title": record.get("title", ""),
                "authors": re.sub(r"\s+", " ", author).strip(),
                "year": record.get("year", ""),
                "doi": record.get("doi", ""),
                "url": record.get("url", ""),
                "abstract": "",
                "database": "ACL Anthology",
            }
        )
    selected.sort(key=lambda row: (str(row.get("year", "")), title_key(row.get("title", ""))))
    # Retain the complete filtered public export. The filter is broad and
    # deterministic; dropping the newer records merely to make the file look
    # small would bias the coverage audit toward older literature.
    cap = len(selected)
    import_dir.mkdir(parents=True, exist_ok=True)
    export_path = import_dir / "acl_anthology_writing.csv"
    csv_write(export_path, selected, ["title", "authors", "year", "doi", "url", "abstract", "database"])
    export_hash = sha256_file(export_path) or ""
    metadata = {
        "database": "ACL Anthology",
        "source_url": url,
        "retrieved_at": now_utc(),
        "sha256": export_hash,
        "query_or_filter": filter_text + "; no record cap",
        "raw_source_sha256": sha256_bytes(raw),
        "raw_source_path": path_label(raw_path),
        "record_count_before_cap": len([record for record in records if any(term in normalize(record.get("title", "")) for term in terms)]),
        "record_count": len(selected),
    }
    write_json(import_dir / "acl_anthology_writing.meta.json", metadata)
    return {"status": status, "records": len(selected), "export": str(export_path), "raw_path": str(raw_path), "raw_sha256": sha256_bytes(raw), "export_sha256": export_hash}


def collect_public_nber(protocol: dict[str, Any], import_dir: Path, raw_output: Path, query: str = "generative AI workplace") -> dict[str, Any]:
    """Collect the first public NBER search page for an economics-domain query."""
    source = next((item for item in protocol.get("literature", {}).get("public_export_sources", []) if item.get("id") == "nber"), {})
    endpoint = source.get("api_url", "https://www.nber.org/api/v1/search")
    raw_output.mkdir(parents=True, exist_ok=True)
    raw_path = raw_output / "nber_search.json"
    status, payload, error = http_json(endpoint, {"q": query, "page": 1}, raw_path)
    if payload is None:
        return {"status": status, "error": error or "download failed", "raw_path": str(raw_path)}
    terms = ("generative ai", "writing", "email", "communication", "productivity", "workplace")
    selected: list[dict[str, Any]] = []
    for item in payload.get("results", []):
        title = str(item.get("title", "") or "")
        abstract = str(item.get("abstract", "") or "")
        haystack = normalize(title + " " + abstract)
        if not any(term in haystack for term in terms):
            continue
        authors = "; ".join(re.sub(r"<[^>]+>", "", str(author)) for author in (item.get("authors") or []))
        record_url = urllib.parse.urljoin("https://www.nber.org", str(item.get("url", "")))
        selected.append(
            {
                "title": title,
                "authors": authors,
                "year": (lambda match: match.group(0) if match else "")(re.search(r"\b(19|20)\d{2}\b", str(item.get("displaydate", "")))),
                "doi": "",
                "url": record_url,
                "abstract": abstract,
                "database": "NBER",
            }
        )
    import_dir.mkdir(parents=True, exist_ok=True)
    export_path = import_dir / "nber_generative_ai.csv"
    csv_write(export_path, selected, ["title", "authors", "year", "doi", "url", "abstract", "database"])
    export_hash = sha256_file(export_path) or ""
    raw_hash = sha256_file(raw_path) or ""
    metadata = {
        "database": "NBER",
        "source_url": endpoint,
        "retrieved_at": now_utc(),
        "sha256": export_hash,
        "query_or_filter": query + "; page=1; title/abstract terms=" + ", ".join(terms),
        "raw_source_sha256": raw_hash,
        "raw_source_path": path_label(raw_path),
        "record_count": len(selected),
    }
    write_json(import_dir / "nber_generative_ai.meta.json", metadata)
    return {"status": status, "records": len(selected), "export": str(export_path), "raw_path": str(raw_path), "raw_sha256": raw_hash, "export_sha256": export_hash}


def collect_public_iclr(protocol: dict[str, Any], import_dir: Path, raw_output: Path, query: str = "writing language models") -> dict[str, Any]:
    """Collect a broad search page from the public ICLR proceedings index."""
    source = next((item for item in protocol.get("literature", {}).get("public_export_sources", []) if item.get("id") == "iclr-proceedings"), {})
    endpoint = source.get("url", "https://proceedings.iclr.cc/papers/search")
    url = endpoint + "?" + urllib.parse.urlencode({"q": query})
    raw_output.mkdir(parents=True, exist_ok=True)
    raw_path = raw_output / "iclr_search.html"
    status, raw, error = http_bytes(url, raw_path, "text/html")
    if raw is None:
        return {"status": status, "error": error or "download failed", "raw_path": str(raw_path)}
    text = raw.decode("utf-8", errors="replace")
    pattern = re.compile(r'href="([^"]*Abstract-[^"]*\.html)"[^>]*>([^<]+)</a>\s*([^<]*)', re.I)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        record_url = urllib.parse.urljoin("https://proceedings.iclr.cc", html.unescape(match.group(1)))
        if record_url in seen:
            continue
        seen.add(record_url)
        selected.append(
            {
                "title": re.sub(r"\s+", " ", html.unescape(match.group(2))).strip(),
                "authors": re.sub(r"\s+", " ", html.unescape(match.group(3))).strip(),
                "year": "2024" if "/2024/" in record_url else "",
                "doi": "",
                "url": record_url,
                "abstract": "",
                "database": "ICLR Proceedings",
            }
        )
    import_dir.mkdir(parents=True, exist_ok=True)
    export_path = import_dir / "iclr_writing_language_models.csv"
    csv_write(export_path, selected, ["title", "authors", "year", "doi", "url", "abstract", "database"])
    export_hash = sha256_file(export_path) or ""
    raw_hash = sha256_file(raw_path) or ""
    metadata = {
        "database": "ICLR Proceedings",
        "source_url": url,
        "retrieved_at": now_utc(),
        "sha256": export_hash,
        "query_or_filter": query,
        "raw_source_sha256": raw_hash,
        "raw_source_path": path_label(raw_path),
        "record_count": len(selected),
    }
    write_json(import_dir / "iclr_writing_language_models.meta.json", metadata)
    return {"status": status, "records": len(selected), "export": str(export_path), "raw_path": str(raw_path), "raw_sha256": raw_hash, "export_sha256": export_hash}


def http_json(url: str, params: dict[str, Any], output_path: Path) -> tuple[str, dict[str, Any] | None, str | None]:
    """Fetch JSON and persist exact response bytes before parsing."""
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
    full_url = f"{url}?{query}" if query else url
    try:
        if requests is not None:
            response = requests.get(
                full_url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            raw = response.content
            status = f"http-{response.status_code}"
            if response.status_code >= 400:
                error = f"HTTP {response.status_code}: {response.text[:240]}"
                write_bytes(output_path, raw)
                return status, None, error
        else:
            request = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # nosec B310 - URL is protocol-controlled
                raw = response.read()
                status = f"http-{response.status}"
        write_bytes(output_path, raw)
        return status, json.loads(raw.decode("utf-8")), None
    except Exception as exc:  # network errors are recorded, never hidden
        return "network-error", None, f"{type(exc).__name__}: {exc}"


def http_bytes(url: str, output_path: Path, accept: str = "*/*") -> tuple[str, bytes | None, str | None]:
    """Fetch and preserve a public binary/text export exactly as received."""
    try:
        if requests is not None:
            response = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": accept}, timeout=HTTP_TIMEOUT_SECONDS)
            raw = response.content
            status = f"http-{response.status_code}"
            write_bytes(output_path, raw)
            if response.status_code >= 400:
                return status, None, f"HTTP {response.status_code}: {response.text[:240]}"
            return status, raw, None
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # nosec B310 - protocol-controlled URL
            raw = response.read()
            status = f"http-{response.status}"
        write_bytes(output_path, raw)
        return status, raw, None
    except Exception as exc:
        return "network-error", None, f"{type(exc).__name__}: {exc}"


def candidate_identity(record: dict[str, Any]) -> str:
    doi = normalize(str(record.get("doi", ""))).replace("https doi org ", "")
    if doi:
        return f"doi:{doi}"
    identifier = normalize(str(record.get("identifier", "")))
    if identifier:
        return f"identifier:{identifier}"
    title = title_key(str(record.get("title", "")))
    return f"title:{title}" if title else f"untitled:{record.get('candidate_id', '')}"


def merge_candidate(candidates: dict[str, dict[str, Any]], record: dict[str, Any]) -> None:
    identity = candidate_identity(record)
    if identity not in candidates:
        candidates[identity] = dict(record)
        candidates[identity]["candidate_identity"] = identity
        candidates[identity]["provenance"] = [
            {
                "source": record.get("source"),
                "query": record.get("query"),
                "search_mode": record.get("search_mode", "local"),
                "retrieved_at": record.get("retrieved_at"),
                "raw_response": record.get("raw_response"),
                "source_hash": record.get("source_hash", ""),
                "source_provenance": record.get("source_provenance", ""),
            }
        ]
        return
    current = candidates[identity]
    for field in ("title", "authors", "year", "doi", "identifier", "url", "abstract"):
        if not current.get(field) and record.get(field):
            current[field] = record[field]
    current.setdefault("provenance", []).append(
        {
            "source": record.get("source"),
            "query": record.get("query"),
            "search_mode": record.get("search_mode", "local"),
            "retrieved_at": record.get("retrieved_at"),
            "raw_response": record.get("raw_response"),
            "source_hash": record.get("source_hash", ""),
            "source_provenance": record.get("source_provenance", ""),
        }
    )
    if record.get("known_item_ids"):
        current.setdefault("known_item_ids", [])
        current["known_item_ids"] = sorted(set(current["known_item_ids"]) | set(record["known_item_ids"]))


def title_similarity(left: str, right: str) -> float:
    # BibTeX uses braces to preserve capitalization (for example, Coh-{M}etrix);
    # remove grouping braces before comparing title identity so formatting does
    # not create a spurious token boundary.
    left_identity = re.sub(r"[{}]", "", str(left or ""))
    right_identity = re.sub(r"[{}]", "", str(right or ""))
    a = set(title_key(left_identity).split())
    b = set(title_key(right_identity).split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def relevant_score(title: str, abstract: str, protocol: dict[str, Any]) -> tuple[int, int, int]:
    text = normalize(f"{title} {abstract}")
    ai = sum(1 for term in protocol["screening"]["ai_terms"] if normalize(term) in text)
    writing = sum(1 for term in protocol["screening"]["writing_terms"] if normalize(term) in text)
    return ai, writing, ai + writing


def query_openalex(
    protocol: dict[str, Any], run_dir: Path, events: list[dict[str, Any]], candidates: dict[str, dict[str, Any]], online: bool
) -> None:
    source = next(item for item in protocol["literature"]["sources"] if item["id"] == "openalex")
    query_specs = [(query, "broad") for query in source["queries"]]
    for item in protocol["literature"]["known_items"]:
        for challenge_query in item.get("challenge_queries", [item["query"]]):
            query_specs.append((challenge_query, "known-item-challenge"))
    for index, (query, search_mode) in enumerate(query_specs, start=1):
        started = now_utc()
        raw_path = run_dir / "raw" / f"openalex-{index:03d}.json"
        if not online:
            events.append({"source": "openalex", "query": query, "mode": search_mode, "status": "not-run-offline", "started_at": started, "result_count": 0, "raw_response": "", "raw_sha256": ""})
            continue
        status, payload, error = http_json(
            source["endpoint"],
            {"search": query, "per-page": source.get("per_page", 50)},
            raw_path,
        )
        results = (payload or {}).get("results", []) if payload else []
        raw_relative = path_label(raw_path, run_dir) if raw_path.is_file() else ""
        events.append({"source": "openalex", "query": query, "mode": search_mode, "status": status, "started_at": started, "result_count": len(results), "error": error or "", "raw_response": raw_relative, "raw_sha256": sha256_file(raw_path) or ""})
        for item in results:
            primary_location = item.get("primary_location") or {}
            source_info = primary_location.get("source") or {}
            merge_candidate(
                candidates,
                {
                    "source": "openalex",
                    "query": query,
                    "search_mode": search_mode,
                    "retrieved_at": started,
                    "raw_response": str(raw_path.relative_to(run_dir)),
                    "title": item.get("title", ""),
                    "authors": "; ".join((author.get("author") or {}).get("display_name", "") for author in item.get("authorships", [])),
                    "year": item.get("publication_year", ""),
                    "doi": item.get("doi", "") or "",
                    "url": item.get("doi", "") or item.get("id", ""),
                    "abstract": reconstruct_abstract(item.get("abstract_inverted_index")),
                    "venue": source_info.get("display_name", ""),
                },
            )


def query_crossref(
    protocol: dict[str, Any], run_dir: Path, events: list[dict[str, Any]], candidates: dict[str, dict[str, Any]], online: bool
) -> None:
    source = next(item for item in protocol["literature"]["sources"] if item["id"] == "crossref")
    query_specs = [(query, "broad") for query in source["queries"]]
    for item in protocol["literature"]["known_items"]:
        for challenge_query in item.get("challenge_queries", [item["query"]]):
            query_specs.append((challenge_query, "known-item-challenge"))
    for index, (query, search_mode) in enumerate(query_specs, start=1):
        started = now_utc()
        raw_path = run_dir / "raw" / f"crossref-{index:03d}.json"
        if not online:
            events.append({"source": "crossref", "query": query, "mode": search_mode, "status": "not-run-offline", "started_at": started, "result_count": 0, "raw_response": "", "raw_sha256": ""})
            continue
        status, payload, error = http_json(
            source["endpoint"],
            {"query.bibliographic": query, "rows": source.get("rows", 50)},
            raw_path,
        )
        results = (payload or {}).get("message", {}).get("items", []) if payload else []
        raw_relative = path_label(raw_path, run_dir) if raw_path.is_file() else ""
        events.append({"source": "crossref", "query": query, "mode": search_mode, "status": status, "started_at": started, "result_count": len(results), "error": error or "", "raw_response": raw_relative, "raw_sha256": sha256_file(raw_path) or ""})
        for item in results:
            authors = "; ".join(" ".join(filter(None, [author.get("given", ""), author.get("family", "")])) for author in item.get("author", []))
            merge_candidate(
                candidates,
                {
                    "source": "crossref",
                    "query": query,
                    "search_mode": search_mode,
                    "retrieved_at": started,
                    "raw_response": str(raw_path.relative_to(run_dir)),
                    "title": (item.get("title") or [""])[0],
                    "authors": authors,
                    "year": (item.get("published", {}).get("date-parts") or [[""]])[0][0],
                    "doi": item.get("DOI", ""),
                    "url": item.get("URL", ""),
                    "abstract": re.sub(r"<[^>]+>", " ", item.get("abstract", "")),
                    "venue": (item.get("container-title") or [""])[0],
                },
            )


def query_public_challenges(
    protocol: dict[str, Any],
    run_dir: Path,
    events: list[dict[str, Any]],
    candidates: dict[str, dict[str, Any]],
    online: bool,
) -> None:
    """Run declared exact-item searches against public domain endpoints.

    These calls are kept separate from broad API discovery. They test whether
    an item can be recovered through the domain's own public search interface,
    and every response is retained so the challenge result is reproducible.
    """
    sources = {item.get("id"): item for item in protocol.get("literature", {}).get("public_export_sources", [])}
    counters: dict[str, int] = {}
    for item in protocol.get("literature", {}).get("known_items", []):
        source_id = item.get("public_challenge_source")
        if not source_id or source_id not in sources:
            continue
        source = sources[source_id]
        query = (item.get("challenge_queries") or [item.get("query", "")])[0]
        started = now_utc()
        counters[source_id] = counters.get(source_id, 0) + 1
        suffix = f"{source_id}-{counters[source_id]:03d}"
        if source_id == "nber":
            raw_path = run_dir / "raw" / f"public-{suffix}.json"
            if not online:
                events.append({"source": source_id, "query": query, "mode": "known-item-challenge", "status": "not-run-offline", "started_at": started, "result_count": 0, "raw_response": "", "raw_sha256": ""})
                continue
            status, payload, error = http_json(source.get("api_url", "https://www.nber.org/api/v1/search"), {"q": query, "page": 1}, raw_path)
            results = (payload or {}).get("results", []) if payload else []
            raw_relative = path_label(raw_path, run_dir) if raw_path.is_file() else ""
            events.append({"source": source_id, "query": query, "mode": "known-item-challenge", "status": status, "started_at": started, "result_count": len(results), "error": error or "", "raw_response": raw_relative, "raw_sha256": sha256_file(raw_path) or ""})
            for result in results:
                title = str(result.get("title", "") or "")
                authors = "; ".join(re.sub(r"<[^>]+>", "", str(author)) for author in (result.get("authors") or []))
                url = urllib.parse.urljoin("https://www.nber.org", str(result.get("url", "")))
                merge_candidate(candidates, {"source": source_id, "query": query, "search_mode": "known-item-challenge", "retrieved_at": started, "raw_response": raw_relative, "title": title, "authors": authors, "year": (lambda match: match.group(0) if match else "")(re.search(r"\b(19|20)\d{2}\b", str(result.get("displaydate", "")))), "doi": "", "url": url, "abstract": str(result.get("abstract", "") or ""), "venue": "NBER"})
        elif source_id == "iclr-proceedings":
            raw_path = run_dir / "raw" / f"public-{suffix}.html"
            if not online:
                events.append({"source": source_id, "query": query, "mode": "known-item-challenge", "status": "not-run-offline", "started_at": started, "result_count": 0, "raw_response": "", "raw_sha256": ""})
                continue
            endpoint = source.get("url", "https://proceedings.iclr.cc/papers/search")
            url = endpoint + "?" + urllib.parse.urlencode({"q": query})
            status, raw, error = http_bytes(url, raw_path, "text/html")
            text = raw.decode("utf-8", errors="replace") if raw is not None else ""
            results = []
            for match in re.compile(r'href="([^"]*Abstract-[^"]*\.html)"[^>]*>([^<]+)</a>\s*([^<]*)', re.I).finditer(text):
                results.append({"title": re.sub(r"\s+", " ", html.unescape(match.group(2))).strip(), "authors": re.sub(r"\s+", " ", html.unescape(match.group(3))).strip(), "url": urllib.parse.urljoin("https://proceedings.iclr.cc", html.unescape(match.group(1)))})
            raw_relative = path_label(raw_path, run_dir) if raw_path.is_file() else ""
            events.append({"source": source_id, "query": query, "mode": "known-item-challenge", "status": status, "started_at": started, "result_count": len(results), "error": error or "", "raw_response": raw_relative, "raw_sha256": sha256_file(raw_path) or ""})
            for result in results:
                merge_candidate(candidates, {"source": source_id, "query": query, "search_mode": "known-item-challenge", "retrieved_at": started, "raw_response": raw_relative, "title": result["title"], "authors": result["authors"], "year": "2024", "doi": "", "url": result["url"], "abstract": "", "venue": "ICLR Proceedings"})


def query_github(protocol: dict[str, Any], run_dir: Path, events: list[dict[str, Any]], software: dict[str, dict[str, Any]], online: bool) -> None:
    endpoint = protocol["software"]["github_endpoint"]
    queries = protocol["software"]["github_queries"]
    for index, query in enumerate(queries, start=1):
        started = now_utc()
        raw_path = run_dir / "raw" / f"github-{index:03d}.json"
        if not online:
            events.append({"source": "github", "query": query, "status": "not-run-offline", "started_at": started, "result_count": 0, "raw_response": "", "raw_sha256": ""})
            continue
        status, payload, error = http_json(endpoint, {"q": query, "per_page": 30}, raw_path)
        results = (payload or {}).get("items", []) if payload else []
        raw_relative = path_label(raw_path, run_dir) if raw_path.is_file() else ""
        events.append({"source": "github", "query": query, "status": status, "started_at": started, "result_count": len(results), "error": error or "", "raw_response": raw_relative, "raw_sha256": sha256_file(raw_path) or ""})
        for item in results:
            repo = item.get("html_url", "")
            if repo:
                software.setdefault(
                    repo,
                    {
                        "name": item.get("name", ""),
                        "repository": repo,
                        "url": repo,
                        "ecosystem": "github-search",
                        "category": "discovered",
                        "source": "github-search",
                        "search_query": query,
                        "description": item.get("description", "") or "",
                        "stars": item.get("stargazers_count", 0),
                        "updated_at": item.get("updated_at", ""),
                    },
                )


def query_package_registries(protocol: dict[str, Any], run_dir: Path, events: list[dict[str, Any]], software: dict[str, dict[str, Any]], online: bool) -> None:
    """Resolve current metadata for protocol-seeded packages.

    Search results are intentionally not used as a substitute for registry or
    repository metadata. Only the finite seed set is queried here; broad GitHub
    candidates remain discovery-only until a reviewer promotes them.
    """
    for index, record in enumerate(list(software.values()), start=1):
        if record.get("source") not in {"protocol-seed", "vendor-manifest", "manual-import"}:
            continue
        name = str(record.get("name", ""))
        ecosystem = normalize(str(record.get("ecosystem", "")))
        repository = str(record.get("repository", ""))
        endpoint = ""
        params: dict[str, Any] = {}
        if ecosystem == "npm":
            endpoint = f"https://registry.npmjs.org/{urllib.parse.quote(name)}"
        elif ecosystem == "python":
            endpoint = f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json"
        elif repository.startswith("https://github.com/"):
            parts = repository.rstrip("/").split("/")
            if len(parts) >= 5:
                endpoint = f"https://api.github.com/repos/{parts[3]}/{parts[4].removesuffix('.git')}"
        if not endpoint:
            events.append({"source": "package-registry", "query": name, "status": "not-applicable", "started_at": now_utc(), "result_count": 0, "raw_response": "", "raw_sha256": ""})
            continue
        raw_path = run_dir / "raw" / f"registry-{index:03d}-{slug(name)}.json"
        if not online:
            events.append({"source": "package-registry", "query": name, "status": "not-run-offline", "started_at": now_utc(), "result_count": 0, "raw_response": "", "raw_sha256": ""})
            continue
        status, payload, error = http_json(endpoint, params, raw_path)
        events.append({"source": "package-registry", "query": name, "status": status, "started_at": now_utc(), "result_count": 1 if payload else 0, "error": error or "", "raw_response": path_label(raw_path, run_dir) if raw_path.is_file() else "", "raw_sha256": sha256_file(raw_path) or ""})
        if not payload:
            continue
        info = payload.get("info", {}) if ecosystem in {"npm", "python"} else payload
        record["registry_version"] = info.get("version", "") or payload.get("dist-tags", {}).get("latest", "")
        record["registry_release"] = (payload.get("time", {}) or {}).get(record["registry_version"], "") if ecosystem == "npm" else (payload.get("releases", {}).get(record["registry_version"], [{}]) or [{}])[0].get("upload_time", "") if ecosystem == "python" else info.get("pushed_at", "")
        record["registry_license"] = info.get("license", "") if ecosystem in {"npm", "python"} else (info.get("license") or {}).get("spdx_id", "") if isinstance(info.get("license"), dict) else ""
        record["registry_status"] = "archived" if info.get("archived") else "metadata-retrieved"
        if info.get("stargazers_count") is not None:
            record["stars"] = info.get("stargazers_count")
        if info.get("pushed_at"):
            record["updated_at"] = info.get("pushed_at")


def local_package_metadata(record: dict[str, Any]) -> dict[str, Any]:
    repository = str(record.get("repository", ""))
    repo_name = repository.rstrip("/").split("/")[-1].removesuffix(".git") if repository else ""
    aliases = {
        "textlint": "textlint",
        "vale": "vale",
        "proselint": "proselint",
        "sloptrim": "sloptrim",
        "humanizer": "humanizer",
        "academic-humanizer": "academic-humanizer",
        "avoid-ai-writing": "avoid-ai-writing",
        "fast-detect-gpt": "fast-detect-gpt",
        "humanizer-stack": "humanizer-stack",
        "stop-slop": "stop-slop",
        "taste-skill": "taste-skill",
        "writing-agent": "writing-agent",
        "slop-forensics": "slop-forensics",
        "vale-ai-tells": "vale-ai-tells",
    }
    local_name = aliases.get(repo_name, repo_name)
    category_by_name = {
        "sloptrim": "ai-tell-diagnostic",
        "vale-ai-tells": "prose-linter",
        "proselint": "prose-linter",
        "humanizer": "editing-guidance",
        "academic-humanizer": "editing-guidance",
        "humanizer-stack": "workflow-skills",
        "avoid-ai-writing": "editing-guidance",
        "stop-slop": "ai-tell-diagnostic",
        "taste-skill": "editing-guidance",
        "writing-agent": "writing-agent",
        "fast-detect-gpt": "ai-detector",
        "slop-forensics": "ai-tell-diagnostic",
    }
    if not record.get("category"):
        record["category"] = category_by_name.get(local_name, "discovered")
    # A GitHub search result named "proselint" is not the vendored proselint
    # package. Only protocol/manifests may claim local content.
    local_allowed = record.get("source") in {"vendor-manifest", "protocol-seed", "manual-import"}
    local_path = ROOT / "vendor" / local_name if local_allowed else ROOT / "vendor" / "__not_a_local_package__"
    if not local_path.is_dir():
        record.update({"local_path": "", "local_present": False, "local_commit": "", "license_file": "", "readme": False, "test_file_count": 0, "languages": "", "provenance_status": "remote-only"})
        return record
    has_nested_git = (local_path / ".git").exists()
    code, commit, error = (command(["git", "rev-parse", "HEAD"], cwd=local_path) if has_nested_git else (127, "", "No nested package repository; use the manifest pin."))
    license_file = ""
    for candidate in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        if (local_path / candidate).is_file():
            license_file = candidate
            break
    extensions: dict[str, int] = {}
    test_count = 0
    for path in local_path.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        suffix = path.suffix.lower()
        if suffix:
            extensions[suffix] = extensions.get(suffix, 0) + 1
        if "test" in path.name.lower() or "tests" in path.parts:
            test_count += 1
    common = sorted(extensions.items(), key=lambda pair: (-pair[1], pair[0]))[:5]
    record.update(
        {
            "local_path": str(local_path.relative_to(ROOT)),
            "local_present": True,
            "local_commit": commit if code == 0 else "",
            "local_git_error": error if code != 0 else "",
            "license_file": license_file,
            "readme": any((local_path / name).is_file() for name in ("README", "README.md", "README.rst")),
            "test_file_count": test_count,
            "languages": ", ".join(f"{suffix}:{count}" for suffix, count in common),
            "provenance_status": "vendored-commit" if code == 0 else ("vendored-manifest-pin" if record.get("manifest_commit") else "vendored-content-no-local-git"),
            "nested_git": has_nested_git,
        }
    )
    return record


def read_manifest() -> list[dict[str, str]]:
    path = ROOT / "vendor" / "MANIFEST.md"
    rows: list[dict[str, str]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(\S+)\s+([0-9a-f]{7,40})\s+(https?://\S+)$", line.strip())
        if match:
            rows.append({"name": match.group(1), "commit": match.group(2), "repository": match.group(3), "source": "vendor-manifest"})
    return rows


def read_manual_imports(
    protocol: dict[str, Any],
    events: list[dict[str, Any]],
    candidates: dict[str, dict[str, Any]],
    software: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Read library exports while preserving source provenance.

    A CSV/JSON/BibTeX file is useful for discovery, but it is not a defensible
    database import unless the file (or its sidecar ``.meta.json``) identifies
    the database, source URL, retrieval time, source hash, and query/filter.
    Incomplete records remain visible in the candidate registry and are marked
    as such; they never satisfy the domain-import gate.
    """
    import_dir = ROOT / protocol.get("manual_import_dir", "docs/survey/audit/imports")
    summary: dict[str, Any] = {
        "literature_files": 0,
        "literature_records": 0,
        "literature_provenance_records": 0,
        "software_files": 0,
        "software_records": 0,
        "software_provenance_records": 0,
        "invalid_files": 0,
        "raw_source_hash_mismatches": 0,
        "metadata_files": 0,
        "databases": [],
    }
    if not import_dir.is_dir():
        events.append(
            {
                "source": "manual-import",
                "query": "domain database exports",
                "status": "missing-import-directory",
                "started_at": now_utc(),
                "result_count": 0,
                "error": "Create the import directory and add a provenance-complete specialist export (EconLit, RePEc/IDEAS, SSRN, ACM, IEEE, Web of Science, or Scopus).",
                "raw_response": "",
                "raw_sha256": "",
            }
        )
        return summary

    accepted = {".json", ".csv", ".bib", ".bibtex"}
    # Review overlays and provenance sidecars are control records, not
    # literature exports. Keeping them in the same directory is convenient for
    # the workflow, but importing them would inflate discovery counts and could
    # turn blank reviewer rows into apparent source records.
    ignored_import_names = {
        "screening_review.csv",
        "evidence_review.csv",
        "review_packet_manifest.json",
    }
    for path in sorted(import_dir.iterdir()):
        if (
            not path.is_file()
            or path.name.startswith("README")
            or path.name in ignored_import_names
            or path.name.endswith(".meta.json")
            or path.suffix.lower() not in accepted
        ):
            continue
        source_hash = sha256_file(path) or ""
        sidecars = [path.with_suffix(path.suffix + ".meta.json"), path.with_suffix(".meta.json")]
        metadata: dict[str, Any] = {}
        for sidecar in sidecars:
            if sidecar.is_file():
                try:
                    loaded = load_json(sidecar)
                    metadata = loaded if isinstance(loaded, dict) else {}
                except Exception as exc:
                    summary["invalid_files"] += 1
                    events.append(
                        {
                            "source": "manual-import",
                            "query": sidecar.name,
                            "status": "metadata-parse-error",
                            "started_at": now_utc(),
                            "result_count": 0,
                            "error": str(exc),
                            "raw_response": path_label(sidecar),
                            "raw_sha256": sha256_file(sidecar) or "",
                        }
                    )
                break
        if metadata:
            summary["metadata_files"] += 1
        try:
            suffix = path.suffix.lower()
            if suffix == ".json":
                payload = load_json(path)
                records = payload if isinstance(payload, list) else payload.get("records", [])
            elif suffix in {".bib", ".bibtex"}:
                records = parse_bibtex(path)
            else:
                with path.open("r", encoding="utf-8", newline="") as handle:
                    records = list(csv.DictReader(handle))
            if not isinstance(records, list):
                raise ValueError("export must contain a list of records")
        except Exception as exc:
            summary["invalid_files"] += 1
            events.append(
                {
                    "source": "manual-import",
                    "query": path.name,
                    "status": "parse-error",
                    "started_at": now_utc(),
                    "result_count": 0,
                    "error": str(exc),
                    "raw_response": path_label(path),
                    "raw_sha256": source_hash,
                }
            )
            continue

        file_provenance = {
            "database": metadata.get("database", metadata.get("source_database", "")),
            "source_url": metadata.get("source_url", metadata.get("url", "")),
            "retrieved_at": metadata.get("retrieved_at", metadata.get("accessed_at", "")),
            "sha256": metadata.get("sha256", source_hash),
            "query_or_filter": metadata.get("query_or_filter", metadata.get("query", "")),
        }
        # A sidecar may intentionally describe the export bytes. If it supplies
        # a hash, require it to agree with the bytes actually read.
        file_hash_ok = not metadata.get("sha256") or str(metadata.get("sha256")).lower() == source_hash.lower()
        raw_source_hash_ok = True
        raw_source_path_value = metadata.get("raw_source_path", "")
        raw_source_hash_value = metadata.get("raw_source_sha256", "")
        if raw_source_path_value and raw_source_hash_value:
            raw_source_path = Path(str(raw_source_path_value))
            if not raw_source_path.is_absolute():
                raw_source_path = ROOT / raw_source_path
            actual_raw_hash = sha256_file(raw_source_path) or ""
            raw_source_hash_ok = actual_raw_hash.lower() == str(raw_source_hash_value).lower()
            if not raw_source_hash_ok:
                summary["raw_source_hash_mismatches"] += 1
        if file_provenance["database"] and file_provenance["database"] not in summary["databases"]:
            summary["databases"].append(file_provenance["database"])
        file_has_literature = False
        file_has_software = False
        for raw_record in records:
            record = dict(raw_record) if isinstance(raw_record, dict) else {"title": str(raw_record)}
            merged = dict(file_provenance)
            for key in ("database", "source_database", "source_url", "retrieved_at", "sha256", "query_or_filter", "query"):
                if record.get(key):
                    if key == "source_database":
                        merged["database"] = record[key]
                    elif key == "query":
                        merged["query_or_filter"] = record[key]
                    else:
                        merged[key] = record[key]
            required = ("database", "source_url", "retrieved_at", "sha256", "query_or_filter")
            provenance_complete = file_hash_ok and raw_source_hash_ok and all(str(merged.get(key, "")).strip() for key in required)
            record["database"] = merged.get("database", "")
            record["source_provenance"] = json.dumps(
                {**merged, "file": path_label(path), "file_sha256": source_hash, "complete": provenance_complete},
                ensure_ascii=True,
                sort_keys=True,
            )
            record["source_hash"] = source_hash
            record["search_mode"] = "public-database-broad" if provenance_complete else "manual-import"
            kind = str(record.get("record_type", record.get("type", "literature"))).lower()
            if kind in {"software", "package", "tool"}:
                file_has_software = True
                repository = record.get("repository", record.get("url", ""))
                if repository:
                    software.setdefault(repository, dict(record, source="manual-import"))
                    summary["software_records"] += 1
                    if provenance_complete:
                        summary["software_provenance_records"] += 1
            else:
                file_has_literature = True
                merge_candidate(
                    candidates,
                    dict(
                        record,
                        source="manual-import",
                        query=record.get("query_or_filter", path.name),
                        retrieved_at=record.get("retrieved_at", now_utc()),
                        abstract=record.get("abstract", ""),
                    ),
                )
                summary["literature_records"] += 1
                if provenance_complete:
                    summary["literature_provenance_records"] += 1
        if file_has_literature:
            summary["literature_files"] += 1
        if file_has_software:
            summary["software_files"] += 1
        status = "imported" if file_hash_ok and raw_source_hash_ok else "imported-provenance-incomplete"
        events.append(
            {
                "source": "manual-import",
                "query": path.name,
                "status": status,
                "started_at": now_utc(),
                "result_count": len(records),
                "error": "" if file_hash_ok and raw_source_hash_ok else ("sidecar sha256 does not match export bytes" if not file_hash_ok else "raw source hash/path does not match"),
                "raw_response": path_label(path),
                "raw_sha256": source_hash,
            }
        )
    if not summary["literature_files"]:
        events.append(
            {
                "source": "manual-import",
                "query": "domain database exports",
                "status": "no-literature-export",
                "started_at": now_utc(),
                "result_count": 0,
                "error": "No domain database export was supplied.",
                "raw_response": "",
                "raw_sha256": "",
            }
        )
    summary["databases"] = sorted(summary["databases"])
    return summary


def integrity_checks(
    run_dir: Path,
    events: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    screening: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check that generated records still point at the bytes they describe."""
    raw_checks: list[dict[str, Any]] = []
    missing_raw: list[str] = []
    mismatched_raw: list[str] = []
    for index, event in enumerate(events, start=1):
        raw_name = str(event.get("raw_response", ""))
        expected = str(event.get("raw_sha256", ""))
        if not raw_name:
            continue
        raw_path = Path(raw_name)
        candidates_for_path = [raw_path] if raw_path.is_absolute() else [run_dir / raw_path, ROOT / raw_path]
        actual_path = next((candidate for candidate in candidates_for_path if candidate.is_file()), None)
        item = {"event": index, "path": raw_name, "expected": expected, "actual": "", "status": "missing"}
        if actual_path is not None:
            item["actual"] = sha256_file(actual_path) or ""
            item["status"] = "pass" if expected and item["actual"] == expected else "hash-mismatch"
        raw_checks.append(item)
        if item["status"] == "missing":
            missing_raw.append(raw_name)
        elif item["status"] != "pass":
            mismatched_raw.append(raw_name)

    candidate_ids = [str(row.get("candidate_id", "")) for row in candidates]
    candidate_identity_values = [str(row.get("candidate_identity", "")) for row in candidates]
    screening_ids = [str(row.get("screening_id", "")) for row in screening]
    duplicate_candidate_ids = sorted({value for value in candidate_ids if value and candidate_ids.count(value) > 1})
    duplicate_identities = sorted({value for value in candidate_identity_values if value and candidate_identity_values.count(value) > 1})
    duplicate_screening_ids = sorted({value for value in screening_ids if value and screening_ids.count(value) > 1})
    missing_candidate_provenance = sum(1 for row in candidates if not row.get("provenance"))
    missing_evidence_provenance = [str(row.get("id", "")) for row in evidence if not str(row.get("source_provenance", "")).strip()]
    invalid_package_provenance = [str(row.get("name", "")) for row in inventory if row.get("provenance_status") not in {"vendored-commit", "vendored-manifest-pin", "remote-only"}]
    checks = {
        "raw_responses_hash": not missing_raw and not mismatched_raw,
        "candidate_ids_unique": not duplicate_candidate_ids,
        "candidate_identities_unique": not duplicate_identities,
        "screening_ids_unique": not duplicate_screening_ids,
        "candidate_provenance_present": missing_candidate_provenance == 0,
        "evidence_provenance_present": not missing_evidence_provenance,
        "software_provenance_valid": not invalid_package_provenance,
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "raw_checks": raw_checks,
        "missing_raw": missing_raw,
        "mismatched_raw": mismatched_raw,
        "duplicate_candidate_ids": duplicate_candidate_ids,
        "duplicate_candidate_identities": duplicate_identities,
        "duplicate_screening_ids": duplicate_screening_ids,
        "missing_candidate_provenance": missing_candidate_provenance,
        "missing_evidence_provenance": missing_evidence_provenance,
        "invalid_package_provenance": invalid_package_provenance,
    }


def write_artifact_manifest(run_dir: Path) -> dict[str, Any]:
    """Write a content manifest after all generated artifacts are complete."""
    files: list[dict[str, Any]] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "artifact_manifest.json":
            continue
        files.append({"path": path_label(path, run_dir), "bytes": path.stat().st_size, "sha256": sha256_file(path) or ""})
    manifest = {"generated_at": now_utc(), "run_dir": str(run_dir), "file_count": len(files), "files": files}
    write_json(run_dir / "artifact_manifest.json", manifest)
    return manifest


def verify_artifact_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "artifact_manifest.json"
    if not path.is_file():
        return {"status": "missing", "checked": 0, "mismatches": ["artifact_manifest.json"]}
    try:
        manifest = load_json(path)
    except Exception as exc:
        return {"status": "invalid", "checked": 0, "mismatches": [str(exc)]}
    mismatches: list[str] = []
    checked = 0
    recorded_paths: set[str] = set()
    run_root = run_dir.resolve()
    for item in manifest.get("files", []):
        relative = str(item.get("path", ""))
        target = (run_dir / relative).resolve()
        checked += 1
        if not relative or relative in recorded_paths or not target.is_relative_to(run_root):
            mismatches.append(relative or "<empty-path>")
            continue
        recorded_paths.add(relative)
        if not target.is_file() or sha256_file(target) != item.get("sha256") or target.stat().st_size != item.get("bytes"):
            mismatches.append(relative)
    actual_paths = {
        path_label(path, run_dir)
        for path in run_dir.rglob("*")
        if path.is_file() and path.name != "artifact_manifest.json"
    }
    mismatches.extend(f"unrecorded:{path}" for path in sorted(actual_paths - recorded_paths))
    mismatches.extend(f"missing:{path}" for path in sorted(recorded_paths - actual_paths))
    if manifest.get("file_count") != len(recorded_paths):
        mismatches.append("file_count")
    mismatches = sorted(set(mismatches))
    return {"status": "pass" if not mismatches else "fail", "checked": checked, "mismatches": mismatches}


def package_selection_record(protocol: dict[str, Any], inventory: list[dict[str, Any]], benchmarks: list[dict[str, Any]]) -> dict[str, Any]:
    """Create an explicit adopt/hold/survey decision record for software."""
    benchmark_map = {normalize(row.get("package", "")): row for row in benchmarks}
    wanted = [normalize(name) for name in protocol.get("software", {}).get("adoption_candidates", [])]
    records: list[dict[str, Any]] = []
    for name in wanted:
        matches = [row for row in inventory if normalize(row.get("name", "")) == name]
        matches.sort(key=lambda row: (row.get("source") not in {"protocol-seed", "vendor-manifest", "manual-import"}, not row.get("local_present")))
        package = matches[0] if matches else {"name": name}
        benchmark = benchmark_map.get(name, {})
        status = benchmark.get("status", "not-run")
        decision = "hold-pending-held-out-benchmark"
        if status == "effectiveness-pass":
            decision = "adopt-pending-independent-review"
        records.append(
            {
                "name": package.get("name", name),
                "repository": package.get("repository", ""),
                "category": package.get("category", ""),
                "provenance_status": package.get("provenance_status", ""),
                "license_file": package.get("license_file", ""),
                "local_commit": package.get("local_commit", "") or package.get("manifest_commit", ""),
                "benchmark_status": status,
                "decision": decision,
                "rationale": "Availability is documented; effectiveness remains unestablished until a locked human-labelled corpus benchmark passes.",
            }
        )
    return {
        "protocol_id": protocol.get("protocol_id", ""),
        "decision_rule": "No package is promoted by metadata or smoke tests; adoption requires held-out effectiveness and independent review.",
        "records": records,
    }


def evaluation_plan(protocol: dict[str, Any], corpus: list[dict[str, Any]], known: dict[str, Any]) -> dict[str, Any]:
    """Machine-readable pilot plan shared by proposal and implementation work."""
    proposal = protocol.get("proposal", {})
    return {
        "protocol_id": protocol.get("protocol_id", ""),
        "primary_outcome": proposal.get("primary_outcome", "human-feedback rounds to reader acceptance"),
        "secondary_outcomes": proposal.get("secondary_outcomes", []),
        "decision_rule": proposal.get("decision_rule", ""),
        "feasibility_scope": proposal.get("feasibility_scope", ""),
        "efficacy_design": proposal.get("efficacy_design", ""),
        "sample_size_rule": proposal.get("sample_size_rule", ""),
        "estimand": proposal.get("estimand", ""),
        "stratification": proposal.get("stratification", []),
        "planning_horizon_weeks": proposal.get("planning_horizon_weeks", 12),
        "planning_scope": proposal.get("planning_scope", ""),
        "corpus": [{"id": item.get("id"), "label": item.get("label")} for item in corpus],
        "required_strata": [
            "accepted human-authored economics prose",
            "rejected and repaired internal drafts",
            "AI-assisted drafts with interaction traces",
            "deliberately corrupted or adversarial examples",
        ],
        "holdout_rule": "Freeze tuning and held-out splits before reporting package or workflow effectiveness.",
        "judge_controls": ["randomize pair order", "length-control comparisons", "use a different judge family", "calibrate against human labels"],
        "known_item_recall": {"broad": known.get("recall", 0.0), "challenge": known.get("challenge_recall", 0.0)},
        "kill_criteria": proposal.get("kill_criteria", []),
    }


def build_software_inventory(protocol: dict[str, Any], run_dir: Path, events: list[dict[str, Any]], online: bool, manual_software: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    by_repo: dict[str, dict[str, Any]] = {}
    for record in protocol["software"]["registry_seeds"]:
        by_repo[record["repository"]] = dict(record, source="protocol-seed")
    for record in read_manifest():
        current = by_repo.setdefault(record["repository"], dict(record))
        current.update({"manifest_name": record["name"], "manifest_commit": record["commit"], "source": "vendor-manifest"})
    for repository, record in (manual_software or {}).items():
        by_repo.setdefault(repository, dict(record, repository=repository, source="manual-import"))
    query_package_registries(protocol, run_dir, events, by_repo, online)
    query_github(protocol, run_dir, events, by_repo, online)
    inventory = []
    for record in by_repo.values():
        inventory.append(local_package_metadata(dict(record)))
    inventory.sort(key=lambda row: (row.get("category", ""), row.get("name", "")))
    return inventory


def make_corpus(run_dir: Path) -> list[dict[str, Any]]:
    corpus = [
        {
            "id": "C-001",
            "label": "provisional-clean",
            "text": "The estimate is identified from variation in the policy threshold. We report the coefficient and its standard error, then discuss the assumptions required for interpretation.",
        },
        {
            "id": "C-002",
            "label": "provisional-surface-tell",
            "text": "This paper delves into a robust and holistic framework, underscoring the pivotal interplay between evidence and implementation while showcasing transformative insights.",
        },
        {
            "id": "C-003",
            "label": "provisional-internal-register",
            "text": "WP3 gates the document after the agent runs the control-plane checklist. The implementation record is then handed off for the next checkpoint and repair pass.",
        },
        {
            "id": "C-004",
            "label": "provisional-substance-gap",
            "text": "The method is important and useful. It provides a comprehensive approach and offers valuable insights for future work.",
        },
    ]
    for item in corpus:
        write_text(run_dir / "corpus" / f"{item['id']}.txt", item["text"] + "\n")
    write_json(run_dir / "corpus" / "manifest.json", [{key: item[key] for key in ("id", "label")} for item in corpus])
    return corpus


def run_package_benchmarks(inventory: list[dict[str, Any]], corpus: list[dict[str, Any]], run_dir: Path, execute: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for package in inventory:
        name = normalize(package.get("name", ""))
        local = ROOT / package["local_path"] if package.get("local_path") else None
        supported = name == "sloptrim" and local is not None and (local / "scripts" / "detect.py").is_file()
        if not execute:
            results.append({"package": package.get("name", ""), "status": "not-run", "reason": "use --execute-tools after reviewing the corpus and command policy", "cases": 0})
            continue
        if not supported:
            results.append({"package": package.get("name", ""), "status": "not-run", "reason": "no safe adapter is implemented for this package; benchmark adapter required", "cases": 0})
            continue
        case_rows = []
        script = local / "scripts" / "detect.py"
        for item in corpus:
            path = run_dir / "corpus" / f"{item['id']}.txt"
            code, stdout, stderr = command([sys.executable, str(script), str(path)], cwd=local, timeout=60)
            parsed: dict[str, Any] = {}
            if stdout:
                try:
                    parsed = json.loads(stdout)
                except json.JSONDecodeError:
                    parsed = {"raw_stdout": stdout[:1000]}
            metrics = parsed.get("_metrics", {}) if isinstance(parsed, dict) else {}
            case_rows.append({"corpus_id": item["id"], "label": item["label"], "return_code": code, "score": parsed.get("score", metrics.get("ai_tell_score", "")), "band": parsed.get("band", metrics.get("ai_tell_band", "")), "stderr": stderr[:500]})
        all_ok = all(case["return_code"] == 0 for case in case_rows)
        result = {"package": package.get("name", ""), "status": "smoke-pass" if all_ok else "smoke-fail", "reason": "detector executed on provisional corpus; no effectiveness claim", "cases": len(case_rows), "case_results": case_rows}
        results.append(result)
    write_json(run_dir / "package_benchmark_results.json", results)
    return results


def known_item_audit(protocol: dict[str, Any], candidates: dict[str, dict[str, Any]], events: list[dict[str, Any]], online: bool) -> dict[str, Any]:
    rows = []
    for item in protocol["literature"]["known_items"]:
        found = []
        item_doi = clean_doi(item.get("doi", ""))
        for candidate in candidates.values():
            similarity = title_similarity(item["title"], candidate.get("title", ""))
            candidate_doi = clean_doi(candidate.get("doi", ""))
            doi_match = bool(item_doi and candidate_doi and item_doi.lower() == candidate_doi.lower())
            if doi_match or similarity >= 0.72:
                found.append((candidate, similarity, bool(doi_match)))
        broad_found = False
        challenge_found = False
        if online:
            for candidate, _, _ in found:
                for entry in candidate.get("provenance", []):
                    if entry.get("source") in {"openalex", "crossref", "manual-import", "acl-anthology", "nber", "iclr-proceedings"}:
                        if entry.get("search_mode") in {"broad", "public-database-broad"}:
                            broad_found = True
                        elif entry.get("search_mode") == "known-item-challenge":
                            challenge_found = True
        rows.append(
            {
                "known_item_id": item["id"],
                "title": item["title"],
                "doi": item.get("doi", ""),
                "candidate_match_count": len(found),
                "search_retrieved": broad_found,
                "challenge_retrieved": challenge_found,
                "status": "pass" if broad_found else ("challenge-only" if challenge_found else ("seed-only" if found else "missing")),
                "matched_titles": " | ".join(candidate.get("title", "") for candidate, _, _ in found[:3]),
            }
        )
    search_count = sum(row["search_retrieved"] for row in rows)
    challenge_count = sum(row["challenge_retrieved"] for row in rows)
    total = len(rows)
    return {"rows": rows, "total": total, "search_retrieved": search_count, "challenge_retrieved": challenge_count, "recall": search_count / total if total else 0.0, "challenge_recall": challenge_count / total if total else 0.0, "offline": not online}


def make_screening(candidates: list[dict[str, Any]], protocol: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, candidate in enumerate(sorted(candidates, key=lambda row: title_key(row.get("title", ""))), start=1):
        ai, writing, total = relevant_score(candidate.get("title", ""), candidate.get("abstract", ""), protocol)
        known = bool(candidate.get("known_item_ids"))
        if total == 0:
            decision = "auto-exclude-low-relevance-but-retain"
            reason = "No configured AI or writing terms in title/abstract; a reviewer may overturn this exclusion."
        else:
            decision = "manual-screen-required"
            reason = "Candidate contains configured AI/writing terms; title/abstract screening and full-text eligibility remain outstanding."
        if known:
            decision = "known-item-manual-screen-required"
            reason = "Known-item challenge candidate; never auto-exclude."
        rows.append(
            {
                "screening_id": f"S-{index:04d}",
                "candidate_identity": candidate.get("candidate_identity", ""),
                "known_item": "yes" if known else "no",
                "title": candidate.get("title", ""),
                "source": candidate.get("source", ""),
                "year": candidate.get("year", ""),
                "doi": candidate.get("doi", ""),
                "identifier": candidate.get("identifier", ""),
                "ai_term_hits": ai,
                "writing_term_hits": writing,
                "screening_decision": decision,
                "screening_reason": reason,
                "reviewer_1": "",
                "reviewer_2": "",
                "adjudication": "",
                "exclusion_code": "",
                "full_text_url": "",
                "full_text_verified": "no",
                "screening_notes": "",
                "selected_for_manual_review": "no",
            }
        )
    return rows


def write_review_flow(run_dir: Path, candidates: list[dict[str, Any]], screening: list[dict[str, Any]]) -> dict[str, Any]:
    """Write a machine-readable review flow without inventing human decisions."""
    queue = [row for row in screening if row.get("selected_for_manual_review") == "yes"]
    adjudicated = [row for row in queue if row.get("adjudication") in {"include", "exclude"}]
    flow = {
        "discovery_records_after_deduplication": len(candidates),
        "records_auto_excluded_low_relevance_but_retained": sum(row.get("screening_decision") == "auto-exclude-low-relevance-but-retain" for row in screening),
        "records_requiring_manual_screening": sum(row.get("screening_decision") in {"manual-screen-required", "known-item-manual-screen-required"} for row in screening),
        "records_in_first_pass_dual_review_queue": len(queue),
        "records_dual_reviewed_and_adjudicated": len(adjudicated),
        "records_included_after_adjudication": sum(row.get("adjudication") == "include" for row in queue),
        "records_excluded_after_adjudication": sum(row.get("adjudication") == "exclude" for row in queue),
        "records_awaiting_dual_review": len(queue) - len(adjudicated),
        "status": "complete" if queue and len(queue) == len(adjudicated) else "screening-pending",
        "note": "The bounded queue is a first pass; the full discovery ledger is retained and the queue must expand if eligible strata are missed.",
    }
    write_json(run_dir / "review_flow.json", flow)
    return flow


def select_screening_queue(rows: list[dict[str, Any]], protocol: dict[str, Any]) -> list[dict[str, Any]]:
    """Mark a deterministic first-pass dual-review queue.

    The complete candidate sheet is retained. A bounded queue makes the first
    human pass executable while ensuring every known-item challenge record is
    reviewed and the remaining relevant pool is sampled reproducibly. The
    queue is not an efficacy result; later passes can expand it.
    """
    config = protocol.get("screening", {})
    sample_size = int(config.get("manual_review_sample_size", 200))
    seed = str(config.get("sample_seed", "humanvoice-screen"))
    relevant = [row for row in rows if row.get("screening_decision") in {"manual-screen-required", "known-item-manual-screen-required"}]
    known = [row for row in relevant if row.get("screening_decision") == "known-item-manual-screen-required" or row.get("known_item") == "yes"]
    selected_ids = {row.get("screening_id") for row in known}
    remaining = [row for row in relevant if row.get("screening_id") not in selected_ids]
    # Stable hash ordering is independent of API response order and therefore
    # auditable from the candidate identity alone.
    remaining.sort(key=lambda row: hashlib.sha256(f"{seed}:{row.get('candidate_identity', '')}".encode()).hexdigest())
    selected_ids.update(row.get("screening_id") for row in remaining[: max(0, sample_size - len(selected_ids))])
    for row in rows:
        row["selected_for_manual_review"] = "yes" if row.get("screening_id") in selected_ids else "no"
    return rows


def evidence_rows(seeds: list[dict[str, Any]], run_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for seed in seeds:
        row = dict(seed)
        local = ROOT / str(seed.get("local_path", "")) if seed.get("local_path") else None
        row["source_hash"] = sha256_file(local) if local and local.is_file() else ""
        row["audit_status"] = "provisional-seed"
        row["reviewer"] = ""
        row["independent_verification"] = "pending"
        source_type = str(row.get("source_type", ""))
        default_design = {
            "systematic-review": "systematic-review",
            "field-experiment": "primary-empirical-uncoded",
            "primary-study": "primary-empirical-uncoded",
        }.get(source_type, "not-applicable")
        row["study_design"] = row.get("study_design", default_design)
        row["appraisal_tool"] = row.get("appraisal_tool", "design must be classified before appraisal" if source_type in {"primary-study", "field-experiment", "systematic-review"} else "not-applicable")
        row["appraisal_status"] = row.get("appraisal_status", "pending" if source_type in {"primary-study", "field-experiment", "systematic-review"} else "not-applicable")
        row["claim_anchor"] = row.get("claim_anchor", "")
        row["limitations"] = row.get("limitations", "Not yet independently extracted." if source_type in {"primary-study", "field-experiment", "systematic-review"} else "")
        rows.append(row)
    return rows


def audit_evidence_identities(
    evidence: list[dict[str, Any]],
    run_dir: Path,
    events: list[dict[str, Any]],
    online: bool,
) -> dict[str, Any]:
    """Resolve DOI-bearing evidence rows without overstating verification.

    Crossref can establish bibliographic identity. It cannot establish that a
    methods section was read or that a synthesized finding is correct; those
    remain separate review fields and release gates.
    """
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(evidence, start=1):
        doi = clean_doi(row.get("doi", ""))
        result: dict[str, Any] = {
            "evidence_id": row.get("id", ""),
            "expected_doi": doi,
            "expected_title": row.get("title", ""),
            "expected_year": row.get("year", ""),
            "canonical_doi": "",
            "canonical_title": "",
            "canonical_year": "",
            "title_similarity": "",
            "status": "not-applicable-no-doi",
            "raw_response": "",
            "raw_sha256": "",
            "error": "",
        }
        if not doi:
            row["identity_status"] = result["status"]
            rows.append(result)
            continue
        started = now_utc()
        raw_path = run_dir / "raw" / f"evidence-doi-{index:03d}-{slug(row.get('id', 'evidence'))}.json"
        if not online:
            result["status"] = "not-run-offline"
            events.append(
                {
                    "source": "crossref-doi",
                    "query": doi,
                    "mode": "bibliographic-identity",
                    "status": "not-run-offline",
                    "started_at": started,
                    "result_count": 0,
                    "error": "",
                    "raw_response": "",
                    "raw_sha256": "",
                }
            )
        else:
            endpoint = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
            status, payload, error = http_json(endpoint, {}, raw_path)
            message = (payload or {}).get("message", {}) if payload else {}
            canonical_title = (message.get("title") or [""])[0]
            canonical_doi = str(message.get("DOI", "") or "")
            date_parts = message.get("published", {}).get("date-parts") or message.get("issued", {}).get("date-parts") or [[""]]
            canonical_year = date_parts[0][0] if date_parts and date_parts[0] else ""
            similarity = title_similarity(str(row.get("title", "")), canonical_title) if canonical_title else 0.0
            doi_match = normalize(doi) == normalize(canonical_doi)
            result.update(
                {
                    "canonical_doi": canonical_doi,
                    "canonical_title": canonical_title,
                    "canonical_year": canonical_year,
                    "title_similarity": round(similarity, 4),
                    "status": "verified" if status == "http-200" and doi_match and similarity >= 0.72 else ("identity-mismatch" if message else "unresolved"),
                    "raw_response": path_label(raw_path, run_dir) if raw_path.is_file() else "",
                    "raw_sha256": sha256_file(raw_path) or "",
                    "error": error or "",
                }
            )
            events.append(
                {
                    "source": "crossref-doi",
                    "query": doi,
                    "mode": "bibliographic-identity",
                    "status": status,
                    "started_at": started,
                    "result_count": 1 if message else 0,
                    "error": error or "",
                    "raw_response": result["raw_response"],
                    "raw_sha256": result["raw_sha256"],
                }
            )
            # Stay within Crossref's documented public-pool request rate.
            time.sleep(0.22)
        row["identity_status"] = result["status"]
        row["canonical_title"] = result["canonical_title"]
        row["canonical_year"] = result["canonical_year"]
        row["identity_raw_response"] = result["raw_response"]
        rows.append(result)
    summary = {
        "total_rows": len(rows),
        "doi_rows": sum(bool(item["expected_doi"]) for item in rows),
        "verified": sum(item["status"] == "verified" for item in rows),
        "mismatches": [item["evidence_id"] for item in rows if item["status"] == "identity-mismatch"],
        "unresolved": [item["evidence_id"] for item in rows if item["expected_doi"] and item["status"] not in {"verified", "identity-mismatch"}],
        "rows": rows,
    }
    csv_write(
        run_dir / "evidence_identity_audit.csv",
        rows,
        ["evidence_id", "expected_doi", "expected_title", "expected_year", "canonical_doi", "canonical_title", "canonical_year", "title_similarity", "status", "raw_response", "raw_sha256", "error"],
    )
    write_json(run_dir / "evidence_identity_summary.json", summary)
    return summary


def audit_bibliography_identities(
    bibliography: list[dict[str, Any]],
    run_dir: Path,
    events: list[dict[str, Any]],
    online: bool,
    evidence_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check every actual DOI in the checked-in bibliography.

    arXiv identifiers are deliberately excluded: they are recorded as
    identifiers by the BibTeX parser, not misreported as DOIs. Where an
    evidence row already resolved the same DOI, its preserved Crossref
    response is reused rather than issuing a second request.
    """
    cached = {
        clean_doi(row.get("expected_doi", "")): row
        for row in (evidence_identity or {}).get("rows", [])
        if clean_doi(row.get("expected_doi", ""))
    }
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(bibliography, start=1):
        doi = clean_doi(record.get("doi", ""))
        result: dict[str, Any] = {
            "bib_key": record.get("key", ""),
            "expected_doi": doi,
            "expected_title": record.get("title", ""),
            "expected_year": record.get("year", ""),
            "identifier": record.get("identifier", ""),
            "canonical_doi": "",
            "canonical_title": "",
            "canonical_year": "",
            "title_similarity": "",
            "status": "not-applicable-no-doi",
            "raw_response": "",
            "raw_sha256": "",
            "error": "",
            "reused_from_evidence": "no",
        }
        if not doi:
            result["status"] = "identifier-only" if record.get("identifier") else "not-applicable-no-doi"
            rows.append(result)
            continue
        cached_row = cached.get(doi)
        if cached_row and cached_row.get("status") == "verified":
            result.update(
                {
                    "canonical_doi": cached_row.get("canonical_doi", ""),
                    "canonical_title": cached_row.get("canonical_title", ""),
                    "canonical_year": cached_row.get("canonical_year", ""),
                    "title_similarity": cached_row.get("title_similarity", ""),
                    "status": "verified" if title_similarity(record.get("title", ""), cached_row.get("canonical_title", "")) >= 0.72 else "identity-mismatch",
                    "raw_response": cached_row.get("raw_response", ""),
                    "raw_sha256": cached_row.get("raw_sha256", ""),
                    "reused_from_evidence": "yes",
                }
            )
            rows.append(result)
            continue
        started = now_utc()
        raw_path = run_dir / "raw" / f"bib-doi-{index:03d}-{slug(record.get('key', 'bibliography'))}.json"
        if not online:
            result["status"] = "not-run-offline"
            events.append(
                {
                    "source": "crossref-bibliography",
                    "query": doi,
                    "mode": "bibliography-identity",
                    "status": "not-run-offline",
                    "started_at": started,
                    "result_count": 0,
                    "error": "",
                    "raw_response": "",
                    "raw_sha256": "",
                }
            )
        else:
            endpoint = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
            status, payload, error = http_json(endpoint, {}, raw_path)
            message = (payload or {}).get("message", {}) if payload else {}
            canonical_title = (message.get("title") or [""])[0]
            canonical_doi = str(message.get("DOI", "") or "")
            date_parts = message.get("published", {}).get("date-parts") or message.get("issued", {}).get("date-parts") or [[""]]
            canonical_year = date_parts[0][0] if date_parts and date_parts[0] else ""
            similarity = title_similarity(str(record.get("title", "")), canonical_title) if canonical_title else 0.0
            doi_match = normalize(doi) == normalize(canonical_doi)
            result.update(
                {
                    "canonical_doi": canonical_doi,
                    "canonical_title": canonical_title,
                    "canonical_year": canonical_year,
                    "title_similarity": round(similarity, 4),
                    "status": "verified" if status == "http-200" and doi_match and similarity >= 0.72 else ("identity-mismatch" if message else "unresolved"),
                    "raw_response": path_label(raw_path, run_dir) if raw_path.is_file() else "",
                    "raw_sha256": sha256_file(raw_path) or "",
                    "error": error or "",
                }
            )
            events.append(
                {
                    "source": "crossref-bibliography",
                    "query": doi,
                    "mode": "bibliography-identity",
                    "status": status,
                    "started_at": started,
                    "result_count": 1 if message else 0,
                    "error": error or "",
                    "raw_response": result["raw_response"],
                    "raw_sha256": result["raw_sha256"],
                }
            )
            time.sleep(0.22)
        rows.append(result)
    summary = {
        "total_rows": len(rows),
        "doi_rows": sum(bool(row["expected_doi"]) for row in rows),
        "verified": sum(row["status"] == "verified" for row in rows),
        "mismatches": [row["bib_key"] for row in rows if row["status"] == "identity-mismatch"],
        "unresolved": [row["bib_key"] for row in rows if row["expected_doi"] and row["status"] not in {"verified", "identity-mismatch"}],
        "identifier_only": sum(row["status"] == "identifier-only" for row in rows),
        "rows": rows,
    }
    csv_write(
        run_dir / "bibliography_identity_audit.csv",
        rows,
        ["bib_key", "expected_doi", "expected_title", "expected_year", "identifier", "canonical_doi", "canonical_title", "canonical_year", "title_similarity", "status", "raw_response", "raw_sha256", "error", "reused_from_evidence"],
    )
    write_json(run_dir / "bibliography_identity_summary.json", summary)
    return summary


def overlay_review_file(path: Path, rows: list[dict[str, Any]], key: str, fields: list[str]) -> int:
    """Apply human edits from a separate file without overwriting the source sheet."""
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        review_rows = list(csv.DictReader(handle))
    updates = {row.get(key, ""): row for row in review_rows if row.get(key, "")}
    count = 0
    for row in rows:
        review = updates.get(row.get(key, ""))
        if not review:
            continue
        changed = False
        for field in fields:
            if review.get(field, "") != "":
                if row.get(field, "") != review[field]:
                    row[field] = review[field]
                    changed = True
        # Merely copying a generated row into an overlay is not human review.
        # Count only rows for which at least one review field actually changed.
        if changed:
            count += 1
    return count


def gate_rows(
    protocol: dict[str, Any],
    online: bool,
    known: dict[str, Any],
    screening: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    benchmarks: list[dict[str, Any]],
    manual_imports: dict[str, Any],
    run_dir: Path,
    integrity: dict[str, Any] | None = None,
    bibliography_identity: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    gates = protocol["gates"]
    adoption = {normalize(name) for name in protocol["software"].get("adoption_candidates", [])}
    benchmark_map = {normalize(item.get("package", "")): item.get("status", "") for item in benchmarks}
    all_benchmarked = bool(adoption) and all(benchmark_map.get(name) == "effectiveness-pass" for name in adoption)
    manual_rows = [row for row in screening if row.get("selected_for_manual_review") == "yes"]
    decision_values = set(protocol.get("literature", {}).get("eligibility", {}).get("decision_values", ["include", "exclude", "uncertain"]))
    exclusion_codes = {item.get("code") for item in protocol.get("literature", {}).get("eligibility", {}).get("exclude", []) if item.get("code")}
    manual_done = bool(manual_rows) and all(
        row.get("reviewer_1") in decision_values
        and row.get("reviewer_2") in decision_values
        and row.get("adjudication") in {"include", "exclude"}
        and (row.get("adjudication") != "exclude" or row.get("exclusion_code") in exclusion_codes)
        for row in manual_rows
    )
    empirical_types = set(protocol.get("literature", {}).get("critical_appraisal", {}).get("required_for", ["primary-study", "field-experiment", "systematic-review"]))
    empirical_load_bearing = [row for row in evidence if row.get("load_bearing") and row.get("source_type") in empirical_types]
    def has_full_text_inspection(row: dict[str, Any]) -> bool:
        inspection = normalize(row.get("inspection", ""))
        return "full text" in inspection or "full local source" in inspection

    full_text_done = bool(empirical_load_bearing) and all(
        has_full_text_inspection(row) and row.get("independent_verification") == "verified"
        for row in empirical_load_bearing
    )
    acceptable_appraisals = {"completed-low-concern", "completed-some-concerns"}
    appraisal_done = bool(empirical_load_bearing) and all(row.get("appraisal_status") in acceptable_appraisals and row.get("claim_anchor") and row.get("limitations") for row in empirical_load_bearing)
    load_bearing_doi = [row for row in evidence if row.get("load_bearing") and clean_doi(row.get("doi", ""))]
    identity_done = bool(load_bearing_doi) and all(row.get("identity_status") == "verified" for row in load_bearing_doi)
    signoff_path = ROOT / protocol.get("external_signoff_file", "docs/survey/audit/review_signoff.json")
    signoff_ok = False
    if signoff_path.is_file():
        try:
            signoff = load_json(signoff_path)
            signoff_ok = signoff.get("status") == "approved" and bool(signoff.get("reviewers"))
        except Exception:
            signoff_ok = False
    specialist_databases = [str(value) for value in gates.get("specialist_domain_databases", [])]
    imported_databases = [str(value) for value in manual_imports.get("databases", [])]
    specialist_matches = [
        database
        for database in imported_databases
        if any(normalize(required) in normalize(database) for required in specialist_databases)
    ]
    specialist_import_done = bool(specialist_matches) if gates.get("require_specialist_domain_import", False) else True
    integrity = integrity or {"status": "fail", "checks": {}}
    bibliography_identity = bibliography_identity or {"doi_rows": 0, "verified": 0, "mismatches": [], "unresolved": []}
    bibliography_done = (
        not bibliography_identity.get("doi_rows")
        or (
            bibliography_identity.get("verified") == bibliography_identity.get("doi_rows")
            and not bibliography_identity.get("mismatches")
            and not bibliography_identity.get("unresolved")
        )
    )
    return [
        {"gate": "protocol-frozen", "status": "pass", "reason": "Versioned JSON protocol is checked in."},
        {"gate": "minimum-query-count", "status": "pass" if len(protocol["literature"]["sources"][0]["queries"]) >= gates["minimum_query_count"] else "fail", "reason": f"{len(protocol['literature']['sources'][0]['queries'])} OpenAlex query families are specified."},
        {"gate": "known-item-broad-recall", "status": "pass" if not known["offline"] and known["recall"] >= gates["known_item_broad_recall_target"] else "fail", "reason": f"Search retrieved {known['search_retrieved']}/{known['total']} known items; offline={known['offline']}."},
        {"gate": "known-item-challenge-recall", "status": "pass" if not known["offline"] and known.get("challenge_recall", 0.0) >= gates.get("known_item_challenge_target", 1.0) else "fail", "reason": f"Challenge queries retrieved {known.get('challenge_retrieved', 0)}/{known['total']} known items; offline={known['offline']}."},
        {"gate": "manual-independent-screening", "status": "pass" if manual_done else "fail", "reason": "Two independent include/exclude/uncertain decisions and include/exclude adjudication are required for every selected queue row; excluded records also require a frozen exclusion code."},
        {"gate": "domain-database-imports", "status": "pass" if manual_imports.get("literature_records", 0) > 0 and manual_imports.get("literature_provenance_records", 0) > 0 else "fail", "reason": f"At least one provenance-complete domain export is required; records={manual_imports.get('literature_records', 0)}, provenance-complete={manual_imports.get('literature_provenance_records', 0)}."},
        {"gate": "specialist-domain-coverage", "status": "pass" if specialist_import_done else "fail", "reason": f"At least one provenance-complete specialist/licensed export is required ({', '.join(specialist_databases)}); matched={', '.join(specialist_matches) or 'none'}. Public ACL/NBER/ICLR slices do not satisfy this gate."},
        {"gate": "full-text-load-bearing-evidence", "status": "pass" if full_text_done else "fail", "reason": f"Every load-bearing empirical/review record needs full-text inspection and independent verification; verified={sum(has_full_text_inspection(row) and row.get('independent_verification') == 'verified' for row in empirical_load_bearing)}/{len(empirical_load_bearing)}."},
        {"gate": "critical-appraisal", "status": "pass" if appraisal_done else "fail", "reason": f"Every load-bearing empirical/review record needs a low/some-concern design-specific appraisal, claim anchor, and limitations; acceptable={sum(bool(row.get('appraisal_status') in acceptable_appraisals and row.get('claim_anchor') and row.get('limitations')) for row in empirical_load_bearing)}/{len(empirical_load_bearing)}."},
        {"gate": "bibliographic-identity", "status": "pass" if identity_done else "fail", "reason": f"Every DOI-bearing load-bearing evidence row must resolve to a matching Crossref title; verified={sum(row.get('identity_status') == 'verified' for row in load_bearing_doi)}/{len(load_bearing_doi)}."},
        {"gate": "bibliography-doi-identity", "status": "pass" if bibliography_done else "fail", "reason": f"Every actual DOI in the checked-in bibliography must resolve to a matching Crossref title; verified={bibliography_identity.get('verified', 0)}/{bibliography_identity.get('doi_rows', 0)}, mismatches={len(bibliography_identity.get('mismatches', []))}, unresolved={len(bibliography_identity.get('unresolved', []))}. arXiv identifiers are tracked separately."},
        {"gate": "package-provenance", "status": "pass" if all(row.get("provenance_status") in {"vendored-commit", "vendored-manifest-pin", "remote-only"} for row in inventory) else "fail", "reason": "Each package must have a URL and a pinned local commit or an explicit remote-only status."},
        {"gate": "package-held-out-benchmark", "status": "pass" if all_benchmarked else "fail", "reason": "Every adoption candidate needs an adapter and effectiveness results on the locked corpus; smoke tests do not establish effectiveness."},
        {"gate": "external-review", "status": "pass" if signoff_ok else "fail", "reason": "The protocol requires an independent librarian/domain reviewer sign-off file with status=approved."},
        {"gate": "artifact-integrity", "status": "pass" if integrity.get("status") == "pass" else "fail", "reason": "Raw-response hashes, record identities, evidence provenance, and package provenance must remain internally consistent."},
    ]


def markdown_report(
    protocol: dict[str, Any], run_meta: dict[str, Any], events: list[dict[str, Any]], candidates: list[dict[str, Any]], screening: list[dict[str, Any]], evidence: list[dict[str, Any]], inventory: list[dict[str, Any]], known: dict[str, Any], benchmarks: list[dict[str, Any]], gates: list[dict[str, Any]], manual_imports: dict[str, Any] | None = None,
    bibliography_identity: dict[str, Any] | None = None,
) -> str:
    manual_imports = manual_imports or {}
    bibliography_identity = bibliography_identity or {}
    passed = sum(gate["status"] == "pass" for gate in gates)
    status = "RELEASE BLOCKED" if any(gate["status"] != "pass" for gate in gates) else "READY FOR EXTERNAL REVIEW"
    lines = [
        "# Humanvoice evidence audit",
        "",
        f"**Status: {status}.** This report was generated by `tools/survey_audit.py` at {run_meta['generated_at']}. It is an auditable pilot, not a claim that the literature is complete.",
        "",
        f"Protocol: `{run_meta['protocol_id']}`  \\  Mode: `{run_meta['mode']}`  \\  Gates passed: `{passed}/{len(gates)}`",
        "",
        "## What this run establishes",
        "",
        f"- `{len(events)}` search events were recorded; network discovery was {'enabled' if run_meta['mode'] == 'online' else 'not available in this run'}.",
        f"- `{len(candidates)}` deduplicated literature candidates are preserved, including the local bibliography and known-item challenge set.",
        f"- `{len(evidence)}` evidence records are present, each with an inspection level and provenance field; `{sum(row.get('identity_status') == 'verified' for row in evidence)}` DOI identities resolved against Crossref.",
        f"- Bibliography identity: `{bibliography_identity.get('verified', 0)}/{bibliography_identity.get('doi_rows', 0)}` actual DOI rows resolved; arXiv identifiers are tracked separately.",
        f"- `{sum(str(row.get('appraisal_status', '')).startswith('completed-') for row in evidence)}` evidence records have completed critical appraisal; pending rows remain explicit release blockers.",
        f"- `{len(inventory)}` software records are inventoried; benchmark results are reported separately from metadata.",
        f"- Domain-import records: `{manual_imports.get('literature_records', 0)}` total, `{manual_imports.get('literature_provenance_records', 0)}` provenance-complete.",
        f"- Known-item broad-search recall is `{known['search_retrieved']}/{known['total']}` (`{known['recall']:.1%}`); exact challenge-query recall is `{known.get('challenge_retrieved', 0)}/{known['total']}` (`{known.get('challenge_recall', 0.0):.1%}`). Seed-only matches never count as retrieval.",
        "",
        "## Release gates",
        "",
        "| Gate | Status | Reason |",
        "|---|---|---|",
    ]
    for gate in gates:
        lines.append(f"| {gate['gate']} | {gate['status']} | {gate['reason'].replace('|', '/') } |")
    gate_status = {str(gate.get("gate", "")): str(gate.get("status", "")) for gate in gates}
    if run_meta.get("mode") == "online":
        first_action = (
            "Keep the live query ledger and rerun it when the protocol or corpus changes; rate-limit and access errors remain part of the coverage record."
            if gate_status.get("known-item-broad-recall") == "pass" and gate_status.get("known-item-challenge-recall") == "pass"
            else "Add or repair broad query families, then rerun the online protocol; exact challenge retrieval must not be confused with broad-search recall."
        )
    else:
        first_action = "Run the same protocol with `--online` in an environment that permits OpenAlex, Crossref, and GitHub API access; preserve every raw response."
    specialist_action = (
        "Retain the provenance-complete specialist slice and, when access is available, extend it with a licensed EconLit, SSRN, ACM, IEEE, Web of Science, or Scopus export; the current slice is not exhaustive."
        if gate_status.get("specialist-domain-coverage") == "pass"
        else "Add at least one provenance-complete specialist export (EconLit, RePEc/IDEAS, SSRN, ACM Digital Library, IEEE Xplore, Web of Science, or Scopus); retain the ACL/NBER/ICLR public slices as supplementary imports and record complete queries in `search_log.csv`."
    )
    source_status: dict[str, dict[str, int]] = {}
    for event in events:
        source_name = str(event.get("source", "unknown"))
        status_name = str(event.get("status", ""))
        bucket = source_status.setdefault(source_name, {})
        bucket[status_name] = bucket.get(status_name, 0) + 1
    lines.extend([
        "",
        "## Search coverage and failure accounting",
        "",
        "A large candidate count is not evidence of exhaustive retrieval. The run records every source event and its exact status so an API quota, an authentication limit, or a missing licensed database cannot be mistaken for a negative result.",
        "",
    ])
    for source_name in sorted(source_status):
        statuses = source_status[source_name]
        total = sum(statuses.values())
        successful = statuses.get("http-200", 0) + statuses.get("imported", 0)
        status_text = "; ".join(f"{key}={value}" for key, value in sorted(statuses.items()))
        lines.append(f"- **{source_name}:** {successful}/{total} events completed retrieval or import; status ledger: {status_text}.")
    lines.extend([
        "",
        "OpenAlex rate-limit responses, when present, are preserved as raw JSON. Broad recall is computed across all declared discovery sources and must be read alongside this status ledger. The ACL, NBER, and ICLR public exports improve domain coverage but are explicitly reported as filtered public slices, not substitutes for licensed indexes.",
        "",
        "## Eligibility and appraisal protocol",
        "",
        protocol.get("literature", {}).get("eligibility", {}).get("scope", "Eligibility criteria are frozen in the protocol snapshot."),
        "",
        "Included evidence must satisfy one of the frozen inclusion classes; exclusions use the following codes:",
        "",
    ])
    for exclusion in protocol.get("literature", {}).get("eligibility", {}).get("exclude", []):
        lines.append(f"- **{exclusion.get('code', '')}:** {exclusion.get('reason', '')}")
    lines.extend([
        "",
        "Empirical studies and systematic reviews marked load-bearing enter `critical_appraisal_queue.csv`. Design-specific appraisal, a claim-level source anchor, limitations, and independent full-text verification are separate from DOI identity resolution.",
        "",
        "",
        "## Evidence discipline",
        "",
        "The pipeline keeps discovery records, screening records, evidence extraction, and synthesis separate. A title/abstract match is not an included study. A package README is not a benchmark. A seed record is not an independently verified result. Blank reviewer fields are intentional release blockers.",
        "",
        "## Load-bearing provisional evidence",
        "",
        "| ID | Question(s) | Type | Inspection | Source | Finding |",
        "|---|---|---|---|---|---|",
    ])
    for row in evidence:
        if row.get("load_bearing"):
            finding = re.sub(r"\s+", " ", row.get("finding", "")).replace("|", "/")
            source = row.get("url", row.get("local_path", "")).replace("|", "/")
            lines.append(f"| {row.get('id','')} | {', '.join(row.get('question_ids', []))} | {row.get('source_type','')} | {row.get('inspection','')} | {source} | {finding} |")
    lines.extend([
        "",
        "## Software inventory",
        "",
        "| Name | Category | Local | Commit | License file | Tests | Benchmark |",
        "|---|---|---|---|---|---:|---|",
    ])
    benchmark_map = {row.get("package"): row.get("status", "") for row in benchmarks}
    display_inventory = [row for row in inventory if row.get("local_present") or row.get("source") in {"protocol-seed", "manual-import"}]
    for row in display_inventory:
        lines.append(f"| {row.get('name','')} | {row.get('category','')} | {row.get('local_path','remote-only')} | {row.get('local_commit','') or row.get('manifest_commit','')} | {row.get('license_file','')} | {row.get('test_file_count',0)} | {benchmark_map.get(row.get('name',''),'not-run')} |")
    lines.extend([
        "",
        f"The full inventory contains `{len(inventory)}` records. The table above shows the `{len(display_inventory)}` local/protocol records; GitHub discovery candidates remain in `software_inventory.csv` and must be screened before adoption.",
        "",
        "## Required next actions",
        "",
        f"1. {first_action}",
        f"2. {specialist_action}",
        "3. Have two independent reviewers complete the deterministic `screening_queue.csv`, adjudicate disagreements, and attach full-text/page anchors to `evidence.csv`; expand the queue when the sample exposes new eligible strata.",
        "4. Expand the locked corpus with adjudicated human labels and implement a safe adapter for every package considered for adoption.",
        "5. Obtain external librarian and economics/HCI review before changing the release status to ready.",
        "",
        "## Generated files",
        "",
        "- `search_log.csv`: query, date, status, result count, error, and raw-response path.",
        "- `candidates.csv`: deduplicated records with all provenance links.",
        "- `screening.csv`: retained candidates and independent-review fields.",
        "- `screening_queue.csv`: deterministic first-pass dual-review queue, including all known-item challenges.",
        "- `review_flow.json`: discovery, screening, adjudication, inclusion, exclusion, and pending counts.",
        "- `evidence.csv`: claim-level extraction records and inspection depth.",
        "- `critical_appraisal_queue.csv`: design, appraisal, claim-anchor, and limitation fields for load-bearing empirical evidence.",
        "- `evidence_identity_audit.csv`: DOI/title/year identity checks with raw Crossref response hashes.",
        "- `bibliography_identity_audit.csv` and `bibliography_identity_summary.json`: identity checks for every actual DOI in the checked-in bibliography; arXiv identifiers are tracked separately.",
        "- `software_inventory.csv`: package metadata and pinning evidence.",
        "- `package_benchmark_results.json`: executable smoke/benchmark output.",
        "- `integrity.json`: raw-response hash and record-consistency checks.",
        "- `gate_results.json`: release decision gates.",
        "",
    ])
    return "\n".join(lines)


def tex_escape(value: str) -> str:
    value = str(value)
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(char, char) for char in value)


def tex_url(value: str) -> str:
    value = str(value)
    replacements = {"\\": r"\textbackslash{}", "%": r"\%", "#": r"\#", "_": r"\_", "&": r"\&", "{": r"\{", "}": r"\}"}
    return "".join(replacements.get(char, char) for char in value)


def ascii_clean(value: Any) -> str:
    """Normalize typographic Unicode before rendering generated artifacts."""
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
        "\u2026": "...",
    }
    text = str(value or "")
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("ascii", "replace").decode("ascii")


def md_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", ascii_clean(value)).replace("|", "/").strip()


def proposal_context(
    protocol: dict[str, Any],
    run_meta: dict[str, Any],
    events: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    screening: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    known: dict[str, Any],
    benchmarks: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    manual_imports: dict[str, Any],
    bibliography_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bibliography_identity = bibliography_identity or {}
    passed = sum(gate.get("status") == "pass" for gate in gates)
    status = "RELEASE BLOCKED" if passed < len(gates) else "READY FOR EXTERNAL REVIEW"
    load_bearing = [row for row in evidence if row.get("load_bearing")]
    empirical_load_bearing = [
        row
        for row in load_bearing
        if row.get("source_type") in {"primary-study", "field-experiment", "systematic-review"}
    ]
    verified = [row for row in load_bearing if row.get("independent_verification") == "verified"]
    manual_rows = [row for row in screening if row.get("selected_for_manual_review") == "yes"]
    reviewed_rows = [row for row in manual_rows if row.get("reviewer_1") and row.get("reviewer_2") and row.get("adjudication")]
    adoption_names = [normalize(name) for name in protocol.get("software", {}).get("adoption_candidates", [])]
    # Discovery can return many repositories with the same display name. The
    # proposal shows one canonical protocol record per adoption candidate; the
    # complete landscape remains in software_inventory.csv.
    adoption: list[dict[str, Any]] = []
    for wanted in adoption_names:
        matches = [row for row in inventory if normalize(row.get("name", "")) == wanted]
        matches.sort(key=lambda row: (row.get("source") not in {"protocol-seed", "vendor-manifest", "manual-import"}, not row.get("local_present"), row.get("name", "")))
        if matches:
            adoption.append(matches[0])
    source_status: dict[str, dict[str, int]] = {}
    for event in events:
        source = str(event.get("source", "unknown"))
        status_name = str(event.get("status", ""))
        bucket = source_status.setdefault(source, {})
        bucket[status_name] = bucket.get(status_name, 0) + 1
    return {
        "passed": passed,
        "status": status,
        "events": len(events),
        "candidates": len(candidates),
        "screening_manual": len(manual_rows),
        "screening_reviewed": len(reviewed_rows),
        "evidence": len(evidence),
        "load_bearing": len(load_bearing),
        "empirical_load_bearing": len(empirical_load_bearing),
        "verified": len(verified),
        "identity_verified": sum(row.get("identity_status") == "verified" for row in evidence),
        "bibliography_identity": bibliography_identity,
        "appraisal_completed": sum(str(row.get("appraisal_status", "")).startswith("completed-") for row in evidence),
        "systematic_reviews": sum(row.get("source_type") == "systematic-review" for row in evidence),
        "field_experiments": sum(row.get("source_type") == "field-experiment" for row in evidence),
        "primary_studies": sum(row.get("source_type") == "primary-study" for row in evidence),
        "inventory": len(inventory),
        "adoption": adoption,
        "benchmarks": benchmarks,
        "manual_imports": manual_imports,
        "known": known,
        "gates": gates,
        "protocol": protocol,
        "run_meta": run_meta,
        "source_status": source_status,
    }


def proposal_document(
    protocol: dict[str, Any],
    run_meta: dict[str, Any],
    events: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    screening: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    known: dict[str, Any],
    benchmarks: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    manual_imports: dict[str, Any],
    bibliography_identity: dict[str, Any] | None = None,
) -> str:
    """Render the backstage implementation dossier from the audit records."""
    ctx = proposal_context(protocol, run_meta, events, candidates, screening, evidence, inventory, known, benchmarks, gates, manual_imports, bibliography_identity)
    proposal = protocol.get("proposal", {})
    lines = [
        "# Humanvoice implementation and evidence dossier",
        "",
        f"**Status: {ctx['status']}**  ",
        f"Generated by `tools/survey_audit.py` at `{run_meta['generated_at']}` under protocol `{run_meta['protocol_id']}`.",
        "",
        "This is a backstage implementation record, not the reader-facing product proposal. It records what was searched and verified, the requirements supported by those records, the proposed evaluation, and the evidence still required before stronger claims can be made.",
        "",
        "## Executive decision",
        "",
        "Build humanvoice as a reader-acceptance workflow with a deterministic measurement layer and a separately validated feedback layer. The system should help an author or editor find register leakage, structural repetition, defensive prose, unsupported claims, citation errors, and meaning drift. It must not rewrite automatically, issue authorship verdicts, or substitute a model score for a human acceptance decision.",
        "",
        "The immediate funding decision is a bounded implementation and pilot, not unrestricted deployment. Release of the product as evidence of improved writing is conditional on the gates in this document and on a preregistered comparison with the current workflow.",
        "",
        "## Evidence at a glance",
        "",
        f"- **Search events:** `{ctx['events']}`. Network queries and local/import events are recorded.",
        f"- **Literature candidates:** `{ctx['candidates']}`. This is a discovery pool, not an included-study count.",
        f"- **Evidence rows:** `{ctx['evidence']}`; `{ctx['load_bearing']}` marked load-bearing, including `{ctx['empirical_load_bearing']}` empirical/review rows subject to the full-text gate; `{ctx['verified']}` load-bearing rows independently verified.",
        f"- **Empirical evidence profile:** `{ctx['systematic_reviews']}` systematic reviews, `{ctx['field_experiments']}` field experiments, and `{ctx['primary_studies']}` other primary studies; source type is not a quality rating.",
        f"- **Bibliographic identity:** `{ctx['identity_verified']}` DOI-bearing rows resolved to matching Crossref records; this does not verify findings.",
        f"- **Checked-in bibliography identity:** `{ctx['bibliography_identity'].get('verified', 0)}/{ctx['bibliography_identity'].get('doi_rows', 0)}` actual DOI rows resolved; arXiv identifiers are not counted as DOIs.",
        f"- **Critical appraisal:** `{ctx['appraisal_completed']}` rows completed; pending appraisal prevents release-ready evidence claims.",
        f"- **Software records:** `{ctx['inventory']}`. Metadata inventory; effectiveness is a separate question.",
        f"- **Domain imports:** `{manual_imports.get('literature_records', 0)}` total; `{manual_imports.get('literature_provenance_records', 0)}` carry complete export provenance.",
        f"- **Broad known-item recall:** `{known['search_retrieved']}/{known['total']}` (`{known['recall']:.1%}`). Seed-only and exact challenge matches do not count.",
        f"- **Challenge-query recall:** `{known.get('challenge_retrieved', 0)}/{known['total']}` (`{known.get('challenge_recall', 0.0):.1%}`). This confirms identity lookup, not search saturation.",
        f"- **Release gates:** `{ctx['passed']}/{len(gates)}`. Status remains blocked until the remainder are independently satisfied.",
        "",
        "## Decision requested",
        "",
        "Authorize the following reversible phase:",
        "",
        "1. Freeze the protocol, schemas, and protected-source policy in version control.",
        "2. Implement the format-aware diagnostics and review packet described below.",
        "3. Assemble an adjudicated economics writing corpus from the internal records and external reference material.",
        "4. Run one live-document feasibility test, then a preregistered, power-justified paired or stepped rollout against the current workflow.",
        "5. Stop or revise the project if the kill criteria are met; do not expand the system because a surface score improves.",
        "",
        "## Why this product",
        "",
        "The internal failure record shows a repeated sequence: internal workflow language leaks into exposition; mechanical surface cues obscure missing explanation; defensive qualifications replace mechanisms; and readers reject documents that automated checks accepted. The accepted SMEwallet units also show that adding length and connective reasoning can improve comprehension, so compression is not a valid quality proxy.",
        "",
        "The external evidence changes the implementation in six ways:",
        "",
        "- Controlled writing experiments find productivity and quality gains from assistance, but those outcomes are task-specific and do not establish reader acceptance.",
        "- Feedback studies find that models can produce specific comments while missing the most important problem or misjudging whether criticism is warranted.",
        "- Co-writing studies find risks of convergence, disclosure effects, and loss of agency or ownership.",
        "- Citation and review studies show that fluent output can contain unverifiable references and that model judges remain weak on long, critical evaluation.",
        "- Two systematic reviews find more consistent surface and process benefits than higher-order writing gains, and warn that validity and fairness remain unsettled for consequential evaluation.",
        "- In-the-wild interaction traces and workplace deployments show that behavior and effects vary by intent, task, and writer skill; an average effect is not an expert-writing result.",
        "",
        "The product therefore optimizes the human decision process, not a detector score or a generic notion of human-likeness.",
        "",
        "## Literature synthesis by decision question",
        "",
        "The evidence is heterogeneous, so the proposal uses it as a set of bounded design constraints rather than as a pooled effect estimate.",
        "",
        "- **Does assistance improve work?** Controlled experiments report task-specific gains in speed or evaluated output quality, including professional writing tasks and workplace email. A deployment to 5,172 support agents also found heterogeneous effects, with larger gains for less-experienced workers and small quality losses among the most skilled. Those estimates do not identify the value of this repository's reader-acceptance workflow, so they motivate a skill-stratified pilot rather than an ROI claim.",
        "- **Can a model give useful revision feedback?** Recent writing-feedback studies show that models can produce specific comments, but they can miss the most important defect, vary by writer proficiency, and disagree with human judgments. Systematic reviews of 25 and 96 empirical studies find more consistent surface/process gains than higher-order writing gains. The product must rank issues, expose uncertainty, and measure the next revision against a domain rubric.",
        "- **What can be lost?** Co-writing and disclosure studies point to agency, ownership, reader-perception, and collective-diversity effects. These are not cosmetic risks: a workflow that makes documents more uniform while reducing reader trust is a failed intervention.",
        "- **Can a machine judge replace a reader?** Citation-reliability and long-form review studies make that substitution unsafe. Model judges may screen, but acceptance remains a named human decision and every load-bearing claim needs an evidence anchor.",
        "- **What process should be measured?** In-the-wild writing traces show recurring intent revision, exploration, questioning, style adjustment, and content injection. The workflow must retain suggestion, acceptance, edit, rejection, and rollback events; output-only comparisons cannot explain how quality or burden changed.",
        "- **How should the survey be trusted?** PRISMA-S, OpenAlex, and Crossref provide reporting and infrastructure patterns for replayable searches; they do not make public API coverage equivalent to licensed economics or bibliographic databases. The separate domain-import and specialist-coverage gates are therefore substantive, not paperwork.",
        "",
        "## Review method and current certainty",
        "",
        "The protocol freezes inclusion classes, seven exclusion codes, dual-review decisions, design-specific critical-appraisal tools, and a known-item recall challenge. Discovery records remain distinct from included evidence. The first-pass queue is deterministic and bounded; it is a work allocation device, not a claim that screening is complete.",
        "",
        "DOI resolution verifies title identity only. Empirical findings become release-ready only after full-text inspection, a source anchor for the extracted claim, design-specific appraisal, limitations, and independent verification. This separation prevents a valid citation from being mistaken for a valid inference.",
        "",
        "## Product boundary",
        "",
        "### In scope",
        "",
        "- A protected-source representation for LaTeX, Markdown, citations, equations, tables, code, and quoted material.",
        "- Deterministic diagnostics for register leakage, cadence, defensive language, unsupported specificity, citation identity, compilation, and version drift.",
        "- A review packet containing quoted spans, context, evidence links, and an editorial question. Diagnostics flag; a human or explicitly invoked editor decides.",
        "- A reader-facing acceptance workflow with low-context review, blinded pairwise comparison, and a recorded human verdict.",
        "- Corpus-level monitoring of convergence and machine-typical language, without per-document authorship classification.",
        "",
        "### Out of scope",
        "",
        "- Automatic authorship or misconduct judgments.",
        "- Detector evasion, watermark removal, or optimization against a vendor's classifier.",
        "- Autonomous generation of claims, citations, data, or references.",
        "- Uploading confidential manuscripts to an unapproved remote provider.",
        "- A claim that any tool reduces human-feedback rounds before the pilot measures it.",
        "",
        "## Operating model",
        "",
        "The workflow has four actors. The author owns claims, evidence, and final wording. The diagnostic layer measures observable properties and emits spans. The editor or writing agent proposes bounded changes while preserving protected content. The reader is the acceptance authority. A research steward maintains the corpus, protocol, package pins, and disclosure record.",
        "",
        "Every intervention produces two artifacts: a reader-facing draft and an internal provenance record. The reader-facing draft should not contain row IDs, gate names, or process vocabulary. The provenance record stores the source hash, tool versions, prompts or rule sets, changed spans, reviewer decisions, and disclosure status.",
        "",
        "## System architecture",
        "",
        "```text",
        "source files -> format parser -> protected document model",
        "                              |",
        "                              +--> deterministic diagnostics",
        "                              |       (flags and measurements)",
        "                              +--> evidence/citation resolver",
        "                              |",
        "                              +--> meaning-preserving diff",
        "                              |",
        "                              +--> review packet -> human decision",
        "                                                      |",
        "                         corpus + verdicts <-----------+",
        "                              |",
        "                         held-out evaluation and drift monitoring",
        "```",
        "",
        "The measurement layer is intentionally modular. A package can be removed without changing the acceptance protocol. A model can be swapped without changing the protected-source or evidence schemas. No diagnostic is allowed to promote a document by itself.",
        "",
        "## Functional requirements",
        "",
        "Each requirement has an acceptance test and an evidence trail. The IDs are stable so implementation issues and pilot results can refer back to them.",
        "",
        *[
            f"- **{md_cell(requirement.get('id', ''))} {md_cell(requirement.get('title', ''))}.** "
            f"{md_cell(requirement.get('statement', ''))} **Acceptance:** {md_cell(requirement.get('acceptance_test', ''))} "
            f"**Evidence:** {md_cell(', '.join(requirement.get('evidence_ids', [])))}. **Phase:** {md_cell(requirement.get('phase', ''))}."
            for requirement in protocol.get("product_requirements", [])
        ],
        "",
        "## Implementation contracts",
        "",
        "The core is a versioned document and evidence model, not a chain of prompts. Every command reads immutable source hashes, emits schema-versioned JSON, and records the tool, configuration, and model version that produced each result. Style findings return data rather than silently changing a file; only invariant, build, privacy, or unresolved load-bearing citation failures may return a blocking status.",
        "",
        "The minimum records are:",
        "",
        "- **DocumentRecord:** document and version IDs, source hash, format, source map, protected spans, policy/configuration version, and disclosure class.",
        "- **DiagnosticFinding:** stable finding ID, rule and category, source span, excerpt hash, surrounding context, measurement, editorial question, and disposition. Severity is operational priority, not a quality score.",
        "- **ChangeRecord:** before/after hashes and spans, editor or tool identity, stated reason, protected-content impact, and author disposition.",
        "- **CitationRecord:** citation key, supplied and canonical DOI/URL metadata, identity status, sentence-level claim anchors, full-text verification, and reviewer.",
        "- **ReviewDecision:** pseudonymous reader, blinded condition where feasible, document hash, rubric responses, acceptance or revision decision, confidence, requested changes, and elapsed time.",
        "- **InteractionEvent:** session and document version, actor, intent class, suggestion hash, accept/edit/reject/rollback event, editing distance, timestamp, and retention class. Store the minimum manuscript content needed for audit.",
        "",
        "The seven command contracts are:",
        "",
        "- **`hv leak`:** source plus project policy to located internal-register and disclosure findings. It must replay the preserved rejected/accepted cases and report locations without editing.",
        "- **`hv rhythm`:** source and rendered prose to sentence, paragraph, opener, transition, and convergence measurements. Thresholds are genre-configured and never certify quality.",
        "- **`hv defensive`:** source to contextualized candidate spans and editorial questions. Precision, recall, and reviewer burden are measured on labelled tuning and untouched holdout sets before activation.",
        "- **`hv diff`:** two DocumentRecords to protected-token censuses, changed spans, and an explain-every-removal ledger. Any unexplained equation, number, label, citation, or claim change blocks promotion.",
        "- **`hv cite`:** bibliography plus claim contexts to canonical identity results and a human verification queue. Seeded valid, nonexistent, wrong-DOI, duplicate, and title-mismatch fixtures must be classified correctly.",
        "- **`hv gate`:** source to reproducible build status, unresolved-reference report, layout warnings, PDF hash, and selected rendered-page images. A PDF that compiles but fails visual inspection does not pass.",
        "- **`hv drift`:** a sufficiently sized document population to aggregate vocabulary, structure, and convergence trends. It refuses single-document attribution and suppresses small cells.",
        "",
        "Parser adapters implement the same source-map contract. Pandoc and pylatexenc are the first benchmark pair; plasTeX is the macro-expanding fallback, LaTeXML the heavier conversion fallback, and tree-sitter-latex the incremental-editor candidate. No adapter becomes authoritative until malformed, unknown-macro, nested-environment, comment, math, citation, and round-trip fixtures pass.",
        "",
        "## Evaluation design",
        "",
        f"The primary outcome is **{proposal.get('primary_outcome', 'human-feedback rounds to reader acceptance')}**. Secondary outcomes are {', '.join(proposal.get('secondary_outcomes', []))}. The pilot must compare the complete workflow with a documented baseline, use the same document task distribution, blind the reader to condition where feasible, and report paired differences with uncertainty rather than a single average.",
        "",
        f"One live document is a feasibility test only: {proposal.get('feasibility_scope', 'integration and burden testing')}. The efficacy phase uses {proposal.get('efficacy_design', 'a preregistered comparative rollout')}. Its sample size is determined by this rule: {proposal.get('sample_size_rule', 'justify precision before outcomes are inspected')}. Prespecified strata are {', '.join(proposal.get('stratification', []))}.",
        "",
        "The corpus should contain at least four strata: accepted human-authored economics prose, rejected and repaired internal drafts, AI-assisted drafts with interaction traces, and deliberately corrupted or adversarial examples. Each item needs a provenance record, protected-source map, defect labels, and reader verdicts. Tuning and held-out evaluation splits must be frozen before benchmark results are reported.",
        "",
        "The reader study should record: reconstruction of purpose and contribution, perceived substance, factual/citation trust, willingness to act, revision requests, confidence, and time. A second reader sample estimates inter-reader agreement. Model judges can reduce screening cost only after their position, verbosity, self-preference, and domain biases are measured on the human-labelled subset.",
        "",
        "The causal question is narrow: does the workflow reduce the number of human-feedback rounds required to reach acceptance without increasing meaning violations or reader time? It is not whether a document receives a higher detector score.",
        "",
        "## Software strategy",
        "",
        "The survey separates three claims that are often conflated: availability, operational suitability, and effectiveness. Registry and repository metadata support only the first. A pinned, reproducible adapter supports the second. A held-out, human-labelled benchmark supports the third.",
        "",
        "The adoption candidates are listed below. A package remains survey-only until the stated benchmark is complete.",
        "",
    ]
    benchmark_map = {normalize(row.get("package", "")): row.get("status", "not-run") for row in benchmarks}
    for package in ctx["adoption"]:
        name = package.get("name", "")
        status = benchmark_map.get(normalize(name), "not-run")
        lines.append(f"- **{md_cell(name)}** ({md_cell(package.get('category', ''))}): benchmark status `{md_cell(status)}`. Before adoption, test protected-region behavior, false positives, runtime, license, and held-out effectiveness.")
    lines.extend([
        "- **humanvoice diagnostics** (local product code): build status. Acceptance requires replay fixtures, reader agreement, and the pilot endpoint.",
        "",
        "The initial stack should prefer local, format-aware, composable components. Pandoc and pylatexenc compete in the first protected-source parser benchmark; plasTeX, LaTeXML, and tree-sitter-latex are explicit fallbacks for macro expansion, structured conversion, and incremental editor spans. latexdiff is a visual-review supplement, never the invariant checker. Vale-style rules, textlint, LanguageTool, TeXtidote, and the maintained LTeX+ LS remain replaceable diagnostic adapters; archived ltex-ls and the deep review's rejected proselint dependency are not adoption candidates. GROBID is optional PDF ingestion, textstat is descriptive only, Inspect AI is an optional model-evaluation harness, and llama.cpp is a privacy-capable runtime whose model quality must be evaluated separately. Remote model calls are optional and must be explicit. AI detectors remain survey-only unless a future population-level validation supports a narrowly defined monitoring use.",
        "",
        "The machine-readable `package_selection.json` records one canonical decision per adoption candidate. The current policy is hold-pending-held-out-benchmark; a smoke pass is not an adoption decision.",
        "",
        "## Implementation plan",
        "",
        "- **P0, weeks 1-4, evidence completion:** specialist and licensed domain exports, dual screening and adjudication, full-text claim anchors, design-specific critical appraisal, and package selection record. Exit when the evidence gates and provenance checks pass.",
        "- **P1, weeks 1-3, policy and protected source:** schemas, disclosure policy, parser adapter benchmark, protected-region model, and baseline map. Exit when round-trip and malformed-source fixtures pass.",
        "- **P2, weeks 2-6, deterministic diagnostics:** implement `leak`, `rhythm`, `defensive`, `cite`, `diff`, `gate`, and `drift` contracts. Exit when historical replay, invariant, and citation fixtures pass.",
        "- **P3, weeks 3-7, corpus and harness:** labelled repair pairs, reader rubric, and blinded pairwise harness. Exit when inter-rater and holdout splits are recorded.",
        "- **P4, weeks 6-9, workflow integration:** review packet, editor interface, provenance record, and CI entry point. Exit when one document runs end to end.",
        "- **P5, weeks 9-12, feasibility:** run one live document end to end and report integration failures, privacy events, telemetry completeness, and burden; do not estimate efficacy from it. Then preregister the powered paired or stepped rollout. The efficacy schedule follows the power/precision analysis and live-document arrival rate rather than an arbitrary 12-week promise.",
        "",
        f"Resource planning assumption: {proposal.get('resource_assumption', 'one product engineer, one research/evaluation lead, and part-time domain reviewer')}. This is a budgeting placeholder, not a measured cost estimate.",
        f"Planning boundary: {proposal.get('planning_scope', 'the build horizon does not imply a completed efficacy study')}",
        "",
        "## Economic decision model",
        "",
        "The investment case should be computed from observed workflow data. Let `r0` and `r1` be baseline and treatment feedback rounds, `t0` and `t1` reader hours per round, `c_r` the loaded cost of reader time, and `C` the one-time build and maintenance cost. The pilot supports deployment only if the expected discounted value of `(r0*t0 - r1*t1)*c_r` plus any measured quality or time benefit exceeds `C`, subject to the meaning-preservation, privacy, and disclosure constraints. No current literature result supplies these project-specific values.",
        "",
        "This formulation prevents productivity studies from being misused as an ROI claim for humanvoice. External experiments establish that assistance can change task time or quality under particular conditions; they do not establish the value of this workflow for this repository's documents.",
        "",
        "## Governance and risks",
        "",
        "- **House-style convergence:** rising cross-document similarity or loss of distinctive arguments. Control with population-level drift reports and no single-style optimization. Pause if diversity falls without reader benefit.",
        "- **Meaning drift:** changed numbers, citations, equations, or scope after editing. Control with protected diffs and human source checks. Stop on any unexplained load-bearing change.",
        "- **False-positive fatigue:** readers ignore or disable diagnostics. Measure review burden and precision by category; stop if flags cost more time than they save.",
        "- **Fluent factual error:** unsupported or mismatched references. Use DOI/URL resolution, evidence anchors, and human verification; stop on unresolved load-bearing citations.",
        "- **Judge bias:** order swaps or length padding change verdicts. Randomize pair order, control length, and calibrate on human labels; pause if the judge misses its threshold.",
        "- **Privacy or disclosure failure:** confidential text leaves the approved boundary. Use local-first routing and provider logs; stop on any unapproved transmission.",
        "- **Process capture:** the proposal becomes a ledger instead of a product. Keep reader and audit artifacts separate and use short result notes; pause if a reader cannot explain the purpose.",
        "",
        "## Release decision",
        "",
        "The current run is not a release. The exact gate results are reproduced below and remain authoritative:",
        "",
        "The gate list is intentionally short and auditable:",
        "",
    ])
    for gate in gates:
        lines.append(f"- **{md_cell(gate.get('gate', ''))}:** `{md_cell(gate.get('status', ''))}`. {md_cell(gate.get('reason', ''))}")
    lines.extend([
        "",
        "A release-ready proposal requires all of the following: broad search recall at the frozen target; genuine domain exports with source metadata; two independent screeners and adjudication; full-text anchors, acceptable critical appraisal, and independent verification for every load-bearing empirical claim; held-out package effectiveness results; and an independent librarian plus economics/HCI sign-off. Passing the automated parts cannot substitute for those human inputs.",
        "",
        "## Reproducibility and handoff",
        "",
        "Run the following from the repository root:",
        "",
        "```bash",
        "python3 tools/survey_audit.py run --online --execute-tools --build-pdf --replace-output",
        "python3 tools/survey_audit.py validate --run docs/survey/audit/latest",
        "python3 tools/survey_audit.py publish --run docs/survey/audit/latest",
        "```",
        "",
        "The run folder contains the frozen protocol, raw responses and hashes, candidate registry, complete screening ledger, deterministic screening queue, review flow, evidence and DOI-identity matrices, critical-appraisal queue, software inventory, package selection record, evaluation plan, benchmark results, corpus manifest, PDF build record, artifact manifest, requirements traceability matrix, and gate results. `publish` leaves the dossier and audit report in this run folder and copies only machine-readable requirements and status summaries; it never writes a second reader-facing document or the authored product proposal.",
        "",
        "## Evidence register",
        "",
        "The full machine-readable evidence matrix remains in `evidence.csv`; the compact register below keeps the dossier navigable while retaining the source link.",
        "",
    ])
    for row in evidence:
        finding = md_cell(row.get("finding", ""))
        if len(finding) > 320:
            finding = finding[:317] + "..."
        source = md_cell(row.get("url") or row.get("local_path") or "unresolved")
        lines.append(f"- **{md_cell(row.get('id', ''))}** ({md_cell(row.get('source_type', ''))}; {md_cell(row.get('inspection', ''))}; questions {md_cell(', '.join(row.get('question_ids', [])))}): {finding} [source]({source}).")
    lines.extend([
        "",
        "## Limitations",
        "",
        "The current evidence rows are a curated, provisional synthesis and not a completed systematic review. Abstract-level records cannot support methods-level claims. Public API coverage is not equivalent to EconLit, RePEc, SSRN, ACM, IEEE, Web of Science, or Scopus coverage. The internal case record is valuable for product requirements but is not an external efficacy study. These limits are why the proposal remains gated.",
        "",
    ])
    proposal_coverage: list[str] = [
        "## Search coverage and failure accounting",
        "",
        "A large candidate count is not evidence of exhaustive retrieval. The run records every source event and its exact status so an API quota, an authentication limit, or a missing licensed database cannot be mistaken for a negative result.",
        "",
    ]
    for source_name in sorted(ctx.get("source_status", {})):
        statuses = ctx["source_status"][source_name]
        total = sum(statuses.values())
        successful = statuses.get("http-200", 0) + statuses.get("imported", 0)
        status_text = "; ".join(f"{key}={value}" for key, value in sorted(statuses.items()))
        proposal_coverage.append(f"- **{md_cell(source_name)}:** {successful}/{total} events completed retrieval or import; status ledger: {status_text}.")
    proposal_coverage.extend([
        "",
        "OpenAlex rate-limit responses, when present, are preserved as raw JSON. Broad recall is computed across all declared discovery sources and must be read alongside this status ledger. The ACL, NBER, and ICLR public exports improve domain coverage but are explicitly reported as filtered public slices, not substitutes for licensed indexes.",
        "",
    ])
    boundary_index = lines.index("## Product boundary")
    lines[boundary_index:boundary_index] = proposal_coverage
    return "\n".join(lines)


def proposal_tex(
    evidence: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    run_meta: dict[str, Any],
    protocol: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    screening: list[dict[str, Any]] | None = None,
    known: dict[str, Any] | None = None,
    benchmarks: list[dict[str, Any]] | None = None,
    manual_imports: dict[str, Any] | None = None,
    bibliography_identity: dict[str, Any] | None = None,
) -> str:
    """Fallback TeX renderer used when Pandoc is unavailable."""
    protocol = protocol or {"proposal": {}, "software": {"adoption_candidates": []}}
    document = proposal_document(protocol, run_meta, events or [], candidates or [], screening or [], evidence, inventory, known or {"total": 0, "search_retrieved": 0, "recall": 0.0, "challenge_retrieved": 0, "challenge_recall": 0.0}, benchmarks or [], gates, manual_imports or {}, bibliography_identity)
    lines = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=0.9in]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{lmodern}",
        r"\usepackage{longtable,booktabs,hyperref,xcolor,enumitem}",
        r"\setlength{\emergencystretch}{3em}",
        r"\sloppy",
        r"\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}",
        r"\title{Humanvoice: Implementation and Evidence Dossier}",
        r"\author{Generated from the humanvoice evidence audit}",
        f"\\date{{{tex_escape(run_meta['generated_at'])}}}",
        r"\begin{document}",
        r"\maketitle",
        r"\section*{Generated dossier}",
        tex_escape(document).replace("\\n", "\\\\\\n"),
        r"\end{document}",
    ]
    return "\n".join(lines) + "\n"


def render_proposal_tex(
    markdown_path: Path,
    tex_path: Path,
    evidence: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    run_meta: dict[str, Any],
    protocol: dict[str, Any],
    events: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    screening: list[dict[str, Any]],
    known: dict[str, Any],
    benchmarks: list[dict[str, Any]],
    manual_imports: dict[str, Any],
    bibliography_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render the audit dossier to TeX, with a dependency fallback."""
    pandoc = shutil.which("pandoc")
    if pandoc:
        code, stdout, stderr = command(
            [pandoc, "--from=gfm", "--to=latex", "--wrap=none", markdown_path.name],
            cwd=markdown_path.parent,
            timeout=120,
        )
        if code == 0 and stdout.strip():
            preamble = "\n".join(
                [
                    r"\documentclass[11pt]{article}",
                    r"\usepackage[margin=0.85in]{geometry}",
                    r"\usepackage[T1]{fontenc}",
                    r"\usepackage[utf8]{inputenc}",
                    r"\usepackage{lmodern}",
                    r"\usepackage{microtype}",
                    r"\usepackage{longtable,booktabs,array,tabularx,enumitem,float,fancyvrb,xcolor}",
                    r"\usepackage[hyphens]{url}",
                    r"\usepackage[colorlinks=true,linkcolor=blue!45!black,urlcolor=blue!45!black]{hyperref}",
                    r"\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}",
                    r"\definecolor{shadecolor}{RGB}{248,248,248}",
                    r"\newenvironment{Shaded}{\begin{quote}\small}{\end{quote}}",
                    r"\DefineVerbatimEnvironment{Highlighting}{Verbatim}{commandchars=\\\{\}}",
                    r"\newcommand{\KeywordTok}[1]{#1}",
                    r"\newcommand{\DataTypeTok}[1]{#1}",
                    r"\newcommand{\DecValTok}[1]{#1}",
                    r"\newcommand{\NormalTok}[1]{#1}",
                    r"\newcommand{\OperatorTok}[1]{#1}",
                    r"\newcommand{\StringTok}[1]{#1}",
                    r"\newcommand{\CommentTok}[1]{\textit{#1}}",
                    r"\newcommand{\BuiltInTok}[1]{#1}",
                    r"\newcommand{\ExtensionTok}[1]{#1}",
                    r"\newcommand{\AttributeTok}[1]{#1}",
                    r"\newcommand{\ControlFlowTok}[1]{#1}",
                    r"\newcommand{\FunctionTok}[1]{#1}",
                    r"\newcommand{\ImportTok}[1]{#1}",
                    r"\newcommand{\InformationTok}[1]{#1}",
                    r"\newcommand{\WarningTok}[1]{#1}",
                    r"\newcommand{\AlertTok}[1]{#1}",
                    r"\newcommand{\ErrorTok}[1]{#1}",
                    r"\newcommand{\ConstantTok}[1]{#1}",
                    r"\newcommand{\SpecialCharTok}[1]{#1}",
                    r"\newcommand{\VerbatimStringTok}[1]{#1}",
                    r"\newcommand{\VerbatimTok}[1]{#1}",
                    r"\newcommand{\VariableTok}[1]{#1}",
                    r"\newcommand{\OtherTok}[1]{#1}",
                    r"\setlength{\LTleft}{0pt}",
                    r"\setlength{\LTright}{0pt}",
                    r"\setlength{\emergencystretch}{3em}",
                    r"\sloppy",
                    r"\title{Humanvoice: Implementation and Evidence Dossier}",
                    r"\author{Generated from the humanvoice evidence audit}",
                    f"\\date{{{tex_escape(run_meta['generated_at'])}}}",
                    r"\begin{document}",
                ]
            )
            write_text(tex_path, preamble + "\n" + stdout + "\n\\end{document}\n")
            return {"renderer": "pandoc", "status": "pass", "stderr": stderr[-2000:]}
    write_text(
        tex_path,
        proposal_tex(
            evidence,
            inventory,
            gates,
            run_meta,
            protocol,
            events,
            candidates,
            screening,
            known,
            benchmarks,
            manual_imports,
            bibliography_identity,
        ),
    )
    return {"renderer": "fallback", "status": "pass", "reason": "pandoc unavailable or conversion failed"}


def build_pdf(run_dir: Path, basename: str = "implementation_dossier") -> dict[str, Any]:
    """Compile the generated dossier twice and preserve the build log."""
    executable = shutil.which("pdflatex")
    if not executable:
        result = {"status": "unavailable", "reason": "pdflatex is not installed"}
        write_json(run_dir / "pdf_build.json", result)
        return result
    logs: list[str] = []
    return_codes: list[int] = []
    for _ in range(2):
        code, stdout, stderr = command(
            [executable, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", f"{basename}.tex"],
            cwd=run_dir,
            timeout=120,
        )
        return_codes.append(code)
        logs.append((stdout + "\n" + stderr)[-12000:])
    pdf_path = run_dir / f"{basename}.pdf"
    try:
        pdf_label = str(pdf_path.relative_to(ROOT))
    except ValueError:
        pdf_label = str(pdf_path)
    result = {
        "status": "pass" if return_codes and all(code == 0 for code in return_codes) else "fail",
        "return_codes": return_codes,
        "pdf": pdf_label if pdf_path.is_file() else "",
        "sha256": sha256_file(pdf_path) or "",
        "logs": logs,
    }
    write_json(run_dir / "pdf_build.json", result)
    return result


def run_audit(args: argparse.Namespace) -> int:
    protocol_path = Path(args.protocol).resolve()
    seeds_path = Path(args.seeds).resolve()
    output = Path(args.output).resolve()
    protocol = load_json(protocol_path)
    seeds = load_json(seeds_path)
    input_validation = validate_inputs(protocol, seeds)
    if input_validation["status"] != "pass":
        raise AuditFailure("invalid protocol or evidence seed:\n- " + "\n- ".join(input_validation["errors"]))
    backup = prepare_output_directory(output, args.replace_output)
    (output / "raw").mkdir(exist_ok=True)
    run_meta = {
        "generated_at": now_utc(),
        "protocol_id": protocol["protocol_id"],
        "mode": "online" if args.online else "offline",
        "network_note": "Network calls are disabled unless --online is supplied.",
        "protocol_path": str(protocol_path.relative_to(ROOT) if protocol_path.is_relative_to(ROOT) else protocol_path),
        "seeds_path": str(seeds_path.relative_to(ROOT) if seeds_path.is_relative_to(ROOT) else seeds_path),
        "replaced_output_backup": str(backup) if backup else "",
        "repository": repository_snapshot(),
    }
    write_json(output / "run_metadata.json", run_meta)
    write_json(output / "input_validation.json", input_validation)
    write_json(output / "protocol_snapshot.json", protocol)
    write_json(output / "seed_evidence_snapshot.json", seeds)

    events: list[dict[str, Any]] = []
    candidates: dict[str, dict[str, Any]] = {}
    bib_path = ROOT / "docs" / "survey" / "humanvoice_survey.bib"
    bibliography = parse_bibtex(bib_path)
    for bib in bibliography:
        merge_candidate(candidates, dict(bib, source="local-bibliography", query="checked-in bibliography", retrieved_at=run_meta["generated_at"], abstract="", authors=bib.get("author", ""), url=bib.get("url", "")))
    for item in protocol["literature"]["known_items"]:
        merge_candidate(candidates, dict(item, source="known-item-seed", query=item.get("query", ""), retrieved_at=run_meta["generated_at"], authors="", abstract="", known_item_ids=[item["id"]]))
    for seed in seeds:
        if seed.get("source_type") in {"primary-study", "systematic-review", "reporting-guideline"}:
            merge_candidate(candidates, dict(seed, source="seed-evidence", query="checked-in pilot evidence", retrieved_at=run_meta["generated_at"], authors=seed.get("authors", ""), abstract=seed.get("finding", ""), known_item_ids=[]))

    query_openalex(protocol, output, events, candidates, args.online)
    query_crossref(protocol, output, events, candidates, args.online)
    query_public_challenges(protocol, output, events, candidates, args.online)
    manual_software: dict[str, dict[str, Any]] = {}
    manual_imports = read_manual_imports(protocol, events, candidates, manual_software)
    inventory = build_software_inventory(protocol, output, events, args.online, manual_software)
    candidate_rows = sorted(candidates.values(), key=lambda row: title_key(row.get("title", "")))
    for index, row in enumerate(candidate_rows, start=1):
        row["candidate_id"] = f"CAND-{index:04d}"
        row["provenance_json"] = json.dumps(row.get("provenance", []), ensure_ascii=True, sort_keys=True)
    screening = select_screening_queue(make_screening(candidate_rows, protocol), protocol)
    evidence = evidence_rows(seeds, output)
    screening_reviewed = overlay_review_file(
        ROOT / protocol.get("manual_import_dir", "docs/survey/audit/imports") / "screening_review.csv",
        screening,
        "screening_id",
        ["reviewer_1", "reviewer_2", "adjudication", "exclusion_code", "full_text_url", "full_text_verified", "screening_decision", "screening_notes"],
    )
    evidence_reviewed = overlay_review_file(
        ROOT / protocol.get("manual_import_dir", "docs/survey/audit/imports") / "evidence_review.csv",
        evidence,
        "id",
        ["inspection", "independent_verification", "reviewer", "confidence", "study_design", "appraisal_tool", "appraisal_status", "claim_anchor", "limitations"],
    )
    write_review_flow(output, candidate_rows, screening)
    evidence_identity = audit_evidence_identities(evidence, output, events, args.online)
    bibliography_identity = audit_bibliography_identities(bibliography, output, events, args.online, evidence_identity)
    known = known_item_audit(protocol, candidates, events, args.online)
    corpus = make_corpus(output)
    benchmarks = run_package_benchmarks(inventory, corpus, output, args.execute_tools)
    write_json(output / "package_selection.json", package_selection_record(protocol, inventory, benchmarks))
    write_json(output / "evaluation_plan.json", evaluation_plan(protocol, corpus, known))
    requirement_rows = []
    for requirement in protocol.get("product_requirements", []):
        row = dict(requirement)
        row["evidence_ids"] = ";".join(requirement.get("evidence_ids", []))
        requirement_rows.append(row)
    csv_write(
        output / "requirements_traceability.csv",
        requirement_rows,
        ["id", "title", "statement", "acceptance_test", "evidence_ids", "phase"],
    )
    write_json(
        output / "requirements_traceability.json",
        {
            "protocol_id": protocol.get("protocol_id", ""),
            "requirement_count": len(protocol.get("product_requirements", [])),
            "requirements": protocol.get("product_requirements", []),
        },
    )
    integrity = integrity_checks(output, events, candidate_rows, screening, evidence, inventory)
    gates = gate_rows(protocol, args.online, known, screening, evidence, inventory, benchmarks, manual_imports, output, integrity, bibliography_identity)

    event_fields = ["source", "query", "mode", "status", "started_at", "result_count", "error", "raw_response", "raw_sha256"]
    candidate_fields = ["candidate_id", "candidate_identity", "title", "authors", "year", "doi", "identifier", "url", "venue", "source", "query", "raw_response", "provenance_json"]
    screening_fields = ["screening_id", "candidate_identity", "known_item", "title", "source", "year", "doi", "identifier", "ai_term_hits", "writing_term_hits", "screening_decision", "screening_reason", "reviewer_1", "reviewer_2", "adjudication", "exclusion_code", "full_text_url", "full_text_verified", "screening_notes", "selected_for_manual_review"]
    csv_write(output / "screening_queue.csv", [row for row in screening if row.get("selected_for_manual_review") == "yes"], screening_fields)
    evidence_fields = ["id", "question_ids", "source_type", "study_design", "title", "authors", "year", "doi", "url", "local_path", "inspection", "claim_anchor", "finding", "implication", "limitations", "confidence", "load_bearing", "appraisal_tool", "appraisal_status", "source_hash", "source_provenance", "audit_status", "reviewer", "independent_verification", "identity_status", "canonical_title", "canonical_year", "identity_raw_response"]
    appraisal_types = set(protocol.get("literature", {}).get("critical_appraisal", {}).get("required_for", []))
    csv_write(output / "critical_appraisal_queue.csv", [row for row in evidence if row.get("load_bearing") and row.get("source_type") in appraisal_types], evidence_fields)
    software_fields = ["name", "category", "ecosystem", "url", "repository", "source", "manifest_commit", "local_path", "local_present", "local_commit", "provenance_status", "license_file", "registry_version", "registry_release", "registry_license", "registry_status", "readme", "test_file_count", "languages", "description", "stars", "updated_at"]
    csv_write(output / "search_log.csv", events, event_fields)
    csv_write(output / "candidates.csv", candidate_rows, candidate_fields)
    csv_write(output / "screening.csv", screening, screening_fields)
    csv_write(output / "evidence.csv", evidence, evidence_fields)
    csv_write(output / "software_inventory.csv", inventory, software_fields)
    csv_write(output / "known_item_audit.csv", known["rows"], ["known_item_id", "title", "doi", "candidate_match_count", "search_retrieved", "challenge_retrieved", "status", "matched_titles"])
    write_json(output / "gate_results.json", gates)
    write_json(output / "known_item_summary.json", known)
    write_json(output / "manual_import_summary.json", manual_imports)
    write_json(output / "evidence_identity_summary.json", evidence_identity)
    write_json(output / "bibliography_identity_summary.json", bibliography_identity)
    write_json(output / "integrity.json", integrity)
    write_json(output / "review_overlay_summary.json", {"screening_rows_updated": screening_reviewed, "evidence_rows_updated": evidence_reviewed})
    write_json(output / "search_events.json", events)
    report = markdown_report(protocol, run_meta, events, candidate_rows, screening, evidence, inventory, known, benchmarks, gates, manual_imports, bibliography_identity)
    write_text(output / "audit_report.md", report)
    dossier = proposal_document(protocol, run_meta, events, candidate_rows, screening, evidence, inventory, known, benchmarks, gates, manual_imports, bibliography_identity)
    write_text(output / DOSSIER_ARTIFACTS["markdown"], dossier)
    render_record = render_proposal_tex(
        output / DOSSIER_ARTIFACTS["markdown"],
        output / DOSSIER_ARTIFACTS["tex"],
        evidence,
        inventory,
        gates,
        run_meta,
        protocol,
        events,
        candidate_rows,
        screening,
        known,
        benchmarks,
        manual_imports,
        bibliography_identity,
    )
    write_json(output / DOSSIER_ARTIFACTS["render"], render_record)
    if args.build_pdf:
        build_pdf(output)
    write_artifact_manifest(output)
    print(report.split("## Release gates", 1)[0].rstrip())
    try:
        artifact_label = str(output.relative_to(ROOT))
    except ValueError:
        artifact_label = str(output)
    print(f"\nArtifacts: {artifact_label}")
    print(f"Release gates: {sum(gate['status'] == 'pass' for gate in gates)}/{len(gates)} passed")
    return 0 if all(gate["status"] == "pass" for gate in gates) else 2


def validate_run(args: argparse.Namespace) -> int:
    run_dir = Path(args.run).resolve()
    artifacts = dossier_artifacts(run_dir)
    required = ["run_metadata.json", "input_validation.json", "protocol_snapshot.json", "search_log.csv", "candidates.csv", "screening.csv", "screening_queue.csv", "review_flow.json", "evidence.csv", "critical_appraisal_queue.csv", "evidence_identity_audit.csv", "evidence_identity_summary.json", "bibliography_identity_audit.csv", "bibliography_identity_summary.json", "software_inventory.csv", "gate_results.json", "audit_report.md", artifacts["markdown"], artifacts["tex"], artifacts["render"], "integrity.json", "package_selection.json", "evaluation_plan.json", "requirements_traceability.csv", "requirements_traceability.json", "artifact_manifest.json"]
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        print("Missing required artifacts: " + ", ".join(missing), file=sys.stderr)
        return 1
    gates = load_json(run_dir / "gate_results.json")
    text = (run_dir / "audit_report.md").read_text(encoding="utf-8")
    checks = {
        "all_required_files": not missing,
        "gate_report_present": bool(gates),
        "release_status_is_explicit": "RELEASE BLOCKED" in text or "READY FOR EXTERNAL REVIEW" in text,
        "screening_has_reviewer_columns": "reviewer_1" in (run_dir / "screening.csv").read_text(encoding="utf-8").splitlines()[0],
        "raw_directory_present": (run_dir / "raw").is_dir(),
        "dossier_markdown_present": (run_dir / artifacts["markdown"]).is_file(),
        "dossier_render_recorded": load_json(run_dir / artifacts["render"]).get("status") == "pass",
        "integrity_recorded": load_json(run_dir / "integrity.json").get("status") in {"pass", "fail"},
        "input_validation_passed": load_json(run_dir / "input_validation.json").get("status") == "pass",
        "requirements_are_traceable": load_json(run_dir / "requirements_traceability.json").get("requirement_count", 0) > 0,
        "bibliography_identity_recorded": bool(load_json(run_dir / "bibliography_identity_summary.json").get("rows")),
        "bibliography_identity_gate_present": any(item.get("gate") == "bibliography-doi-identity" for item in gates),
    }
    integrity = load_json(run_dir / "integrity.json")
    checks["integrity_checks_recomputed"] = bool(integrity.get("checks"))
    checks["integrity_raw_hashes"] = integrity.get("checks", {}).get("raw_responses_hash", False)
    checks["artifact_manifest_recorded"] = (run_dir / "artifact_manifest.json").is_file()
    checks["artifact_manifest_valid"] = verify_artifact_manifest(run_dir).get("status") == "pass"
    if (run_dir / "pdf_build.json").is_file():
        pdf_build = load_json(run_dir / "pdf_build.json")
        checks["pdf_build_recorded"] = pdf_build.get("status") in {"pass", "unavailable", "fail"}
        if pdf_build.get("status") == "pass":
            checks["pdf_exists"] = bool(pdf_build.get("pdf")) and (run_dir / artifacts["pdf"]).is_file()
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return 0 if all(checks.values()) else 1


def publish_run(args: argparse.Namespace) -> int:
    """Publish evidence artifacts without writing the authored proposal."""
    run_dir = Path(args.run).resolve()
    artifacts = dossier_artifacts(run_dir)
    required = [
        "run_metadata.json", "input_validation.json", "protocol_snapshot.json", "search_log.csv",
        "candidates.csv", "screening.csv", "screening_queue.csv", "review_flow.json", "evidence.csv",
        "critical_appraisal_queue.csv", "evidence_identity_audit.csv", "evidence_identity_summary.json",
        "bibliography_identity_audit.csv", "bibliography_identity_summary.json", "software_inventory.csv",
        "gate_results.json", "audit_report.md", artifacts["markdown"], artifacts["tex"],
        artifacts["render"], "integrity.json", "package_selection.json", "evaluation_plan.json",
        "requirements_traceability.csv", "requirements_traceability.json", "artifact_manifest.json",
    ]
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        print("Cannot publish; missing: " + ", ".join(missing), file=sys.stderr)
        return 1
    integrity = load_json(run_dir / "integrity.json")
    manifest_check = verify_artifact_manifest(run_dir)
    if integrity.get("status") != "pass" or manifest_check.get("status") != "pass":
        print(
            "Cannot publish; evidence or artifact integrity failed: "
            f"evidence={integrity.get('status', 'missing')}, artifacts={manifest_check.get('status', 'missing')}",
            file=sys.stderr,
        )
        return 1
    destination = ROOT / "docs" / "survey"
    copied = []
    for source_name, destination_name in evidence_publication_pairs(artifacts):
        target = destination / destination_name
        shutil.copyfile(run_dir / source_name, target)
        copied.append(str(target.relative_to(ROOT)))
    gates = load_json(run_dir / "gate_results.json")
    status = "release-blocked" if any(gate.get("status") != "pass" for gate in gates) else "ready-for-external-review"
    failed_gates = [gate.get("gate", "") for gate in gates if gate.get("status") != "pass"]
    dossier_path = run_dir / artifacts["markdown"]
    try:
        dossier_location = str(dossier_path.relative_to(ROOT))
    except ValueError:
        dossier_location = str(dossier_path)
    write_json(
        destination / "humanvoice_evidence_status.json",
        {
            "status": status,
            "source_run": str(run_dir),
            "passed_gates": len(gates) - len(failed_gates),
            "total_gates": len(gates),
            "failed_gates": failed_gates,
            "artifact_manifest_sha256": sha256_file(run_dir / "artifact_manifest.json"),
            "dossier_location": dossier_location,
            "copied": copied,
            "published_at": now_utc(),
        },
    )
    print(f"Published {len(copied)} evidence artifacts; status={status}")
    for path in copied:
        print(path)
    return 0


def collect_public_command(args: argparse.Namespace) -> int:
    protocol = load_json(Path(args.protocol).resolve())
    acl_result = collect_public_acl(
        protocol,
        Path(args.import_dir).resolve(),
        Path(args.raw_output).resolve(),
        args.query_filter,
    )
    nber_result = collect_public_nber(
        protocol,
        Path(args.import_dir).resolve(),
        Path(args.raw_output).resolve(),
        args.nber_query,
    )
    iclr_result = collect_public_iclr(
        protocol,
        Path(args.import_dir).resolve(),
        Path(args.raw_output).resolve(),
        args.iclr_query,
    )
    result = {"acl": acl_result, "nber": nber_result, "iclr": iclr_result}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(item.get("status") == "http-200" and item.get("records", 0) > 0 for item in (acl_result, nber_result, iclr_result)) else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="execute the audit and generate artifacts")
    run.add_argument("--online", action="store_true", help="query OpenAlex, Crossref, and GitHub; preserve raw responses")
    run.add_argument("--execute-tools", action="store_true", help="run adapters implemented for local packages")
    run.add_argument("--build-pdf", action="store_true", help="compile implementation_dossier.tex twice with pdflatex")
    run.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    run.add_argument("--seeds", default=str(DEFAULT_SEEDS))
    run.add_argument("--output", default=str(DEFAULT_OUTPUT))
    run.add_argument("--replace-output", action="store_true", help="move a nonempty output directory to a timestamped backup before running")
    run.set_defaults(func=run_audit)
    validate = sub.add_parser("validate", help="validate an existing run folder")
    validate.add_argument("--run", default=str(DEFAULT_OUTPUT))
    validate.set_defaults(func=validate_run)
    publish = sub.add_parser("publish", help="publish compact audit summaries without creating a second reader-facing document")
    publish.add_argument("--run", default=str(DEFAULT_OUTPUT))
    publish.set_defaults(func=publish_run)
    collect = sub.add_parser("collect-public", help="collect a provenance-hashed public ACL bibliography export")
    collect.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    collect.add_argument("--import-dir", default=str(ROOT / "docs" / "survey" / "audit" / "imports"))
    collect.add_argument("--raw-output", default=str(ROOT / "docs" / "survey" / "audit" / "public_raw"))
    collect.add_argument("--query-filter", default="")
    collect.add_argument("--nber-query", default="generative AI workplace")
    collect.add_argument("--iclr-query", default="writing language models")
    collect.set_defaults(func=collect_public_command)
    return root


if __name__ == "__main__":
    try:
        parsed_args = parser().parse_args()
        raise SystemExit(parsed_args.func(parsed_args))
    except AuditFailure as exc:
        print(f"audit failure: {exc}", file=sys.stderr)
        raise SystemExit(1)
