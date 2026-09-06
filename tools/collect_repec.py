#!/usr/bin/env python3
"""Collect a bounded, provenance-hashed RePEc/IDEAS specialist slice.

RePEc discourages uncontrolled scraping and its API requires an access code.
This collector therefore uses the documented IDEAS search form, makes a small
fixed number of requests, preserves each HTML response, and calls the result a
specialist *slice* rather than a complete RePEc export.  The audit still
requires screening and full-text review after import.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMPORT_DIR = ROOT / "docs" / "survey" / "audit" / "imports"
DEFAULT_RAW_DIR = ROOT / "docs" / "survey" / "audit" / "public_raw" / "repec"
SEARCH_URL = "https://ideas.repec.org/cgi-bin/htsearch2"
USER_AGENT = "humanvoice-survey-audit/1.0 (bounded RePEc specialist slice)"
DEFAULT_QUERIES = (
    "generative AI writing",
    "AI writing feedback revision",
    "large language model workplace communication",
    "automated writing evaluation validity",
    "human AI collaborative writing",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ResultParser(HTMLParser):
    """Parse only result list items from the official IDEAS search page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self.item: dict[str, object] | None = None
        self.depth = 0
        self.in_title = False
        self.in_abstract = False
        self.in_handle = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag == "li" and "list-group-item" in (attrs_map.get("class") or ""):
            self.item = {"before": [], "title": [], "abstract": [], "handle": "", "url": ""}
            self.depth = 1
            self.in_title = self.in_abstract = self.in_handle = False
            return
        if self.item is None:
            return
        if tag == "li":
            self.depth += 1
        elif tag == "a" and attrs_map.get("href", "").startswith("https://ideas.repec.org/") and not self.item["url"]:
            self.item["url"] = attrs_map.get("href", "") or ""
            self.in_title = True
        elif tag == "hr":
            self.in_title = False
            self.in_abstract = True
        elif tag == "i" and self.in_abstract:
            self.in_handle = True

    def handle_endtag(self, tag: str) -> None:
        if self.item is None:
            return
        if tag == "a":
            self.in_title = False
        elif tag == "i":
            self.in_handle = False
        elif tag == "li":
            self.depth -= 1
            if self.depth <= 0:
                self.finish()

    def handle_data(self, data: str) -> None:
        if self.item is None:
            return
        text = re.sub(r"\s+", " ", data)
        if not text.strip():
            return
        if self.in_title:
            self.item["title"].append(text)
        elif self.in_handle:
            self.item["handle"] += text
        elif self.in_abstract:
            self.item["abstract"].append(text)
        else:
            self.item["before"].append(text)

    def finish(self) -> None:
        assert self.item is not None
        handle = re.search(r"RePEc:[^\s<]+", str(self.item["handle"]) + " " + " ".join(self.item["abstract"]))
        if not handle or not self.item["url"] or not self.item["title"]:
            self.item = None
            return
        before = html.unescape(" ".join(self.item["before"])).strip()
        match = re.match(r"(?P<authors>.+?)\s*\((?P<year>\d{4})\)\s*:\s*$", before)
        abstract = html.unescape(" ".join(self.item["abstract"]))
        abstract = re.sub(r"\s+Save to MyIDEAS.*$", "", abstract).strip()
        title = " ".join(html.unescape(" ".join(self.item["title"])).split())
        abstract = " ".join(abstract.split())
        self.results.append(
            {
                "title": title,
                "authors": match.group("authors").strip() if match else before,
                "year": match.group("year") if match else "",
                "doi": "",
                "url": str(self.item["url"]),
                "abstract": abstract,
                "database": "RePEc/IDEAS",
                "identifier": handle.group(0),
            }
        )
        self.item = None


def search(query: str, raw_path: Path, timeout: int = 30) -> dict[str, object]:
    form = {
        "form": "extended",
        "wm": "wrd",
        "dt": "range",
        "q": query,
        "ul": "",
        "wf": "4BFF",
        "s": "R",
    }
    request = Request(SEARCH_URL, data=urlencode(form).encode("utf-8"), headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed official endpoint
        raw = response.read()
        status = getattr(response, "status", 200)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    text = raw.decode("utf-8", errors="replace")
    parser = ResultParser()
    parser.feed(text)
    return {
        "query": query,
        "url": SEARCH_URL,
        "status": f"http-{status}",
        "raw_path": str(raw_path),
        "raw_sha256": sha256(raw_path),
        "records": parser.results,
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["title", "authors", "year", "doi", "url", "abstract", "database", "identifier"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def collect(queries: tuple[str, ...], import_dir: Path, raw_dir: Path, pause: float = 1.0) -> dict[str, object]:
    retrieved_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    responses: list[dict[str, object]] = []
    records: dict[str, dict[str, str]] = {}
    for index, query in enumerate(queries, start=1):
        response = search(query, raw_dir / f"search-{index:02d}.html")
        responses.append({key: value for key, value in response.items() if key != "records"})
        for record in response["records"]:  # type: ignore[union-attr]
            key = record["identifier"] or record["url"]  # type: ignore[index]
            records.setdefault(key, record)  # type: ignore[arg-type]
        if index < len(queries):
            time.sleep(pause)

    import_dir.mkdir(parents=True, exist_ok=True)
    export_path = import_dir / "repec_ideas_writing.csv"
    selected = sorted(records.values(), key=lambda row: (row.get("year", ""), row.get("title", "").lower()))
    write_csv(export_path, selected)
    raw_manifest = raw_dir / "raw_manifest.json"
    raw_manifest.write_text(json.dumps({"database": "RePEc/IDEAS", "retrieved_at": retrieved_at, "responses": responses}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    export_hash = sha256(export_path)
    metadata = {
        "database": "RePEc/IDEAS",
        "source_url": SEARCH_URL,
        "retrieved_at": retrieved_at,
        "sha256": export_hash,
        "query_or_filter": "Official IDEAS search form; bounded queries: " + " | ".join(queries) + "; first result page per query; deduplicated by RePEc handle.",
        "raw_source_path": str(raw_manifest.relative_to(ROOT)),
        "raw_source_sha256": sha256(raw_manifest),
        "record_count": len(selected),
        "scope_note": "Specialist discovery slice, not a complete RePEc export; title/abstract records require dual screening and full-text appraisal.",
    }
    (import_dir / "repec_ideas_writing.meta.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "imported", "records": len(selected), "export": str(export_path), "raw_manifest": str(raw_manifest), "export_sha256": export_hash}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", dest="queries", help="one bounded IDEAS query (repeatable)")
    parser.add_argument("--import-dir", type=Path, default=DEFAULT_IMPORT_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--pause", type=float, default=1.0)
    args = parser.parse_args(argv)
    queries = tuple(args.queries or DEFAULT_QUERIES)
    try:
        result = collect(queries, args.import_dir.resolve(), args.raw_dir.resolve(), max(0.0, args.pause))
    except Exception as exc:
        print(f"RePEc collection failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
