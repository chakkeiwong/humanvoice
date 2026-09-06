"""
Protected-object extraction for humanvoice correspondence verification.

Implements parser bake-off strategy with provenance binding per Codex audit:
- Multiple parsers (pylatexenc + regex fallback)
- Per-object identity tracking by hash
- Provenance binding (source hash, parser versions, timestamps)
- Parser agreement measurement
- Optional manual gold standard
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple

try:
    from pylatexenc.latexwalker import (
        LatexWalker,
        LatexEnvironmentNode,
        LatexMacroNode,
        LatexMathNode,
    )
    PYLATEXENC_AVAILABLE = True
except ImportError:
    PYLATEXENC_AVAILABLE = False


@dataclass
class ProtectedObject:
    """Single protected object with provenance and version binding."""
    object_type: str  # equation, label, citation, displaymath, table
    content: str
    content_normalized: str  # For matching: whitespace normalized
    source_file: Path
    source_file_hash: str  # AMENDMENT: bind to exact source version
    line_number: int
    context_before: str
    context_after: str
    hash: str  # Hash of normalized content for identity tracking
    parser_source: str  # AMENDMENT: which parser found this


@dataclass
class ProtectedManifest:
    """Complete inventory of protected objects with provenance binding."""
    source_file: Path
    source_file_hash: str  # AMENDMENT: SHA256 of source file
    snapshot_id: str
    extraction_timestamp: str
    parser_version: str  # AMENDMENT: "pylatexenc:2.10+regex:builtin"
    model_version: Optional[str]  # AMENDMENT: model used for any assisted parsing
    parent_artifact_hash: Optional[str]  # AMENDMENT: for draft/assembly manifests

    equations: List[ProtectedObject] = field(default_factory=list)
    labels: List[ProtectedObject] = field(default_factory=list)
    citations: List[ProtectedObject] = field(default_factory=list)
    displaymath: List[ProtectedObject] = field(default_factory=list)
    tables: List[ProtectedObject] = field(default_factory=list)

    total_count: int = 0
    extraction_method: str = "parser_bakeoff"
    parser_agreement_score: Optional[float] = None  # AMENDMENT: consensus measure

    def to_json(self) -> dict:
        """Serialize for storage."""
        return {
            "source_file": str(self.source_file),
            "source_file_hash": self.source_file_hash,
            "snapshot_id": self.snapshot_id,
            "extraction_timestamp": self.extraction_timestamp,
            "parser_version": self.parser_version,
            "model_version": self.model_version,
            "parent_artifact_hash": self.parent_artifact_hash,
            "equations": [self._serialize_object(o) for o in self.equations],
            "labels": [self._serialize_object(o) for o in self.labels],
            "citations": [self._serialize_object(o) for o in self.citations],
            "displaymath": [self._serialize_object(o) for o in self.displaymath],
            "tables": [self._serialize_object(o) for o in self.tables],
            "total_count": self.total_count,
            "extraction_method": self.extraction_method,
            "parser_agreement_score": self.parser_agreement_score
        }

    def _serialize_object(self, obj: ProtectedObject) -> dict:
        return {
            "type": obj.object_type,
            "content": obj.content,
            "content_normalized": obj.content_normalized,
            "source_file": str(obj.source_file),
            "source_file_hash": obj.source_file_hash,
            "line": obj.line_number,
            "context_before": obj.context_before,
            "context_after": obj.context_after,
            "hash": obj.hash,
            "parser_source": obj.parser_source
        }

    @classmethod
    def from_json(cls, data: dict) -> 'ProtectedManifest':
        """Deserialize from storage."""
        def deserialize_object(obj_data: dict) -> ProtectedObject:
            return ProtectedObject(
                object_type=obj_data["type"],
                content=obj_data["content"],
                content_normalized=obj_data["content_normalized"],
                source_file=Path(obj_data["source_file"]),
                source_file_hash=obj_data["source_file_hash"],
                line_number=obj_data["line"],
                context_before=obj_data["context_before"],
                context_after=obj_data["context_after"],
                hash=obj_data["hash"],
                parser_source=obj_data["parser_source"]
            )

        return cls(
            source_file=Path(data["source_file"]),
            source_file_hash=data["source_file_hash"],
            snapshot_id=data["snapshot_id"],
            extraction_timestamp=data["extraction_timestamp"],
            parser_version=data["parser_version"],
            model_version=data.get("model_version"),
            parent_artifact_hash=data.get("parent_artifact_hash"),
            equations=[deserialize_object(o) for o in data.get("equations", [])],
            labels=[deserialize_object(o) for o in data.get("labels", [])],
            citations=[deserialize_object(o) for o in data.get("citations", [])],
            displaymath=[deserialize_object(o) for o in data.get("displaymath", [])],
            tables=[deserialize_object(o) for o in data.get("tables", [])],
            total_count=data["total_count"],
            extraction_method=data["extraction_method"],
            parser_agreement_score=data.get("parser_agreement_score")
        )


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 of file for provenance binding."""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def _normalize_content(content: str) -> str:
    """Normalize whitespace for robust matching."""
    normalized = re.sub(r'\s+', ' ', content).strip()
    return normalized


def _compute_object_hash(content: str) -> str:
    """Compute stable hash for object identity matching."""
    normalized = _normalize_content(content)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _get_context(lines: List[str], line_num: int, before: int = 0, after: int = 0) -> str:
    """Extract surrounding lines for context."""
    start = max(0, line_num - before - 1)
    end = min(len(lines), line_num + after)
    return '\n'.join(lines[start:end])


def _make_equation_object(
    obj_content: str,
    source_path: Path,
    source_hash: str,
    line_num: int,
    lines: List[str],
    parser_source: str,
) -> ProtectedObject:
    """Build an equation ProtectedObject with context and identity hash."""
    return ProtectedObject(
        object_type='equation',
        content=obj_content,
        content_normalized=_normalize_content(obj_content),
        source_file=source_path,
        source_file_hash=source_hash,
        line_number=line_num,
        context_before=_get_context(lines, line_num, before=2),
        context_after=_get_context(lines, line_num, after=2),
        hash=_compute_object_hash(obj_content),
        parser_source=parser_source,
    )


def _split_align_rows(env_content: str) -> List[Tuple[str, int]]:
    r"""
    Split a multi-row math environment into its individually labelled rows.

    align/gather/eqnarray bodies carry one \label per numbered row, so the
    environment is not the unit of correspondence -- the row is. A reader cites
    eq:021, not "the third align block". Returns (row_text, line_offset) pairs
    for rows carrying a label; an environment with no labelled rows returns
    fewer than two rows and is recorded whole by the caller.

    The scan is brace-depth aware so a row break inside a nested matrix or
    cases body does not split the enclosing row.
    """
    # Strip the environment wrappers before splitting so a row's identity is the
    # row itself rather than its position in the environment: including
    # \begin{align} in the first row's hash would change that row's identity if
    # the environment were later renamed, even though the equation did not
    # change. It also lets the independent regex path produce matching hashes.
    body = env_content
    line_shift = 0
    begin_match = re.match(r'\s*\\begin\{[^}]*\}', env_content)
    if begin_match:
        body = env_content[begin_match.end():]
        line_shift = env_content[:begin_match.end()].count('\n')
    end_match = re.search(r'\\end\{[^}]*\}\s*$', body)
    if end_match:
        body = body[:end_match.start()]

    rows: List[Tuple[str, int]] = []
    depth = 0
    start = 0
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth = max(0, depth - 1)
        elif ch == '\\' and depth == 0 and body[i:i + 2] == '\\\\':
            rows.append((body[start:i], start))
            i += 2
            start = i
            continue
        i += 1
    rows.append((body[start:], start))

    labelled = []
    for text, offset in rows:
        if '\\label{' in text:
            labelled.append((text.strip(), line_shift + body[:offset].count('\n')))
    return labelled


def extract_with_pylatexenc(content: str, source_path: Path, source_hash: str) -> Dict[str, List[ProtectedObject]]:
    """Extract using pylatexenc parser."""
    if not PYLATEXENC_AVAILABLE:
        return {"equations": [], "displaymath": [], "tables": []}

    objects = {"equations": [], "displaymath": [], "tables": []}
    lines = content.split('\n')

    try:
        walker = LatexWalker(content)
        nodelist, pos, len_ = walker.get_latex_nodes()

        def walk_nodes(nodes, in_table=False):
            """Recursively walk all nodes including nested environments."""
            for node in nodes:
                if isinstance(node, LatexEnvironmentNode):
                    env_name = node.environmentname

                    if env_name in ['equation', 'align', 'gather', 'multline', 'eqnarray']:
                        line_num = content[:node.pos].count('\n') + 1
                        obj_content = content[node.pos:node.pos+node.len]

                        # A labelled row is the unit of correspondence, not the
                        # enclosing environment: align bodies carry one \label
                        # per numbered row and readers cite the row.
                        rows = _split_align_rows(obj_content)
                        if len(rows) > 1:
                            for row_text, row_offset in rows:
                                objects["equations"].append(_make_equation_object(
                                    row_text, source_path, source_hash,
                                    line_num + row_offset, lines, "pylatexenc"
                                ))
                        else:
                            objects["equations"].append(_make_equation_object(
                                obj_content, source_path, source_hash,
                                line_num, lines, "pylatexenc"
                            ))

                    elif env_name == 'displaymath':
                        line_num = content[:node.pos].count('\n') + 1
                        obj_content = content[node.pos:node.pos+node.len]

                        obj = ProtectedObject(
                            object_type='displaymath',
                            content=obj_content,
                            content_normalized=_normalize_content(obj_content),
                            source_file=source_path,
                            source_file_hash=source_hash,
                            line_number=line_num,
                            context_before=_get_context(lines, line_num, before=1),
                            context_after=_get_context(lines, line_num, after=1),
                            hash=_compute_object_hash(obj_content),
                            parser_source="pylatexenc"
                        )
                        objects["displaymath"].append(obj)

                    elif env_name == 'table':
                        # Record table environment, not nested tabular
                        if not in_table:
                            line_num = content[:node.pos].count('\n') + 1
                            obj_content = content[node.pos:node.pos+node.len]

                            obj = ProtectedObject(
                                object_type='table',
                                content=obj_content,
                                content_normalized=_normalize_content(obj_content),
                                source_file=source_path,
                                source_file_hash=source_hash,
                                line_number=line_num,
                                context_before=_get_context(lines, line_num, before=1),
                                context_after=_get_context(lines, line_num, after=1),
                                hash=_compute_object_hash(obj_content),
                                parser_source="pylatexenc"
                            )
                            objects["tables"].append(obj)

                        # Recurse with in_table=True to skip nested tabular
                        if hasattr(node, 'nodelist') and node.nodelist:
                            walk_nodes(node.nodelist, in_table=True)
                        continue

                    elif env_name == 'tabular' and in_table:
                        # Skip tabular when nested inside table
                        if hasattr(node, 'nodelist') and node.nodelist:
                            walk_nodes(node.nodelist, in_table=True)
                        continue

                    # Recursively walk nested nodes
                    if hasattr(node, 'nodelist') and node.nodelist:
                        walk_nodes(node.nodelist, in_table)

                # LatexMathNode for inline/display math
                elif isinstance(node, LatexMathNode) if PYLATEXENC_AVAILABLE else False:
                    if node.displaytype == 'display':
                        line_num = content[:node.pos].count('\n') + 1
                        obj_content = content[node.pos:node.pos+node.len]

                        obj = ProtectedObject(
                            object_type='displaymath',
                            content=obj_content,
                            content_normalized=_normalize_content(obj_content),
                            source_file=source_path,
                            source_file_hash=source_hash,
                            line_number=line_num,
                            context_before=_get_context(lines, line_num, before=1),
                            context_after=_get_context(lines, line_num, after=1),
                            hash=_compute_object_hash(obj_content),
                            parser_source="pylatexenc"
                        )
                        objects["displaymath"].append(obj)

                # Walk into other node types
                elif hasattr(node, 'nodelist') and node.nodelist:
                    walk_nodes(node.nodelist, in_table)

        walk_nodes(nodelist)

    except Exception as e:
        print(f"Warning: pylatexenc extraction encountered error: {e}")

    return objects


def extract_with_regex(content: str, source_path: Path, source_hash: str) -> Dict[str, List[ProtectedObject]]:
    """Fallback regex extraction for labels, citations, and simple patterns."""
    objects = {"equations": [], "labels": [], "citations": [], "displaymath": []}
    lines = content.split('\n')

    # Extract labels
    for match in re.finditer(r'\\label\{([^}]+)\}', content):
        line_num = content[:match.start()].count('\n') + 1
        obj_content = match.group(1)

        obj = ProtectedObject(
            object_type='label',
            content=obj_content,
            content_normalized=_normalize_content(obj_content),
            source_file=source_path,
            source_file_hash=source_hash,
            line_number=line_num,
            context_before=_get_context(lines, line_num, before=1),
            context_after=_get_context(lines, line_num, after=1),
            hash=_compute_object_hash(obj_content),
            parser_source="regex"
        )
        objects["labels"].append(obj)

    # Extract citations
    for match in re.finditer(r'\\cite[tp]?\{([^}]+)\}', content):
        line_num = content[:match.start()].count('\n') + 1
        obj_content = match.group(1)

        obj = ProtectedObject(
            object_type='citation',
            content=obj_content,
            content_normalized=_normalize_content(obj_content),
            source_file=source_path,
            source_file_hash=source_hash,
            line_number=line_num,
            context_before=_get_context(lines, line_num, before=1),
            context_after=_get_context(lines, line_num, after=1),
            hash=_compute_object_hash(obj_content),
            parser_source="regex"
        )
        objects["citations"].append(obj)

    # Extract displaymath (\[ \])
    for match in re.finditer(r'\\\[(.*?)\\\]', content, re.DOTALL):
        line_num = content[:match.start()].count('\n') + 1
        obj_content = match.group(0)

        obj = ProtectedObject(
            object_type='displaymath',
            content=obj_content,
            content_normalized=_normalize_content(obj_content),
            source_file=source_path,
            source_file_hash=source_hash,
            line_number=line_num,
            context_before=_get_context(lines, line_num, before=1),
            context_after=_get_context(lines, line_num, after=1),
            hash=_compute_object_hash(obj_content),
            parser_source="regex"
        )
        objects["displaymath"].append(obj)

    # Extract simple equation environments as fallback
    for match in re.finditer(r'\\begin\{equation\}(.*?)\\end\{equation\}', content, re.DOTALL):
        line_num = content[:match.start()].count('\n') + 1
        obj_content = match.group(0)

        obj = ProtectedObject(
            object_type='equation',
            content=obj_content,
            content_normalized=_normalize_content(obj_content),
            source_file=source_path,
            source_file_hash=source_hash,
            line_number=line_num,
            context_before=_get_context(lines, line_num, before=2),
            context_after=_get_context(lines, line_num, after=2),
            hash=_compute_object_hash(obj_content),
            parser_source="regex"
        )
        objects["equations"].append(obj)

    # Extract align/gather/eqnarray rows. This is deliberately a separate
    # implementation from the pylatexenc path -- a naive top-level split rather
    # than a brace-depth-aware scan -- so the agreement score can actually
    # detect a bug in either one. Sharing the splitter would make both parsers
    # fail identically and certify a common blind spot.
    for match in re.finditer(
        r'\\begin\{(align|gather|eqnarray)\*?\}(.*?)\\end\{\1\*?\}',
        content,
        re.DOTALL,
    ):
        env_body = match.group(2)
        base_line = content[:match.start()].count('\n') + 1
        base_line += content[match.start():match.start(2)].count('\n')

        consumed = 0
        for row in re.split(r'\\\\', env_body):
            row_line = base_line + env_body[:consumed].count('\n')
            consumed += len(row) + 2
            if '\\label{' not in row:
                continue
            objects["equations"].append(_make_equation_object(
                row.strip(), source_path, source_hash, row_line, lines, "regex"
            ))

    return objects


def compute_parser_agreement(pylatexenc_results: dict, regex_results: dict) -> Tuple[float, str]:
    """
    AMENDMENT: Measure parser consensus.
    Returns (agreement_score, diagnostic_message).
    """
    diagnostics = []
    overall_agreement = []

    # Compare equation counts
    pylatex_eq_count = len(pylatexenc_results.get("equations", []))
    regex_eq_count = len(regex_results.get("equations", []))

    if pylatex_eq_count > 0 or regex_eq_count > 0:
        mean_count = (pylatex_eq_count + regex_eq_count) / 2
        diff = abs(pylatex_eq_count - regex_eq_count)
        agreement = 1.0 - min(diff / mean_count if mean_count > 0 else 0, 1.0)
        overall_agreement.append(agreement)
        diagnostics.append(f"equations: pylatexenc={pylatex_eq_count}, regex={regex_eq_count}, agreement={agreement:.2f}")

    # Compare displaymath counts
    pylatex_dm_count = len(pylatexenc_results.get("displaymath", []))
    regex_dm_count = len(regex_results.get("displaymath", []))

    if pylatex_dm_count > 0 or regex_dm_count > 0:
        mean_count = (pylatex_dm_count + regex_dm_count) / 2
        diff = abs(pylatex_dm_count - regex_dm_count)
        agreement = 1.0 - min(diff / mean_count if mean_count > 0 else 0, 1.0)
        overall_agreement.append(agreement)
        diagnostics.append(f"displaymath: pylatexenc={pylatex_dm_count}, regex={regex_dm_count}, agreement={agreement:.2f}")

    overall_score = sum(overall_agreement) / len(overall_agreement) if overall_agreement else 1.0
    diagnostic_msg = "; ".join(diagnostics)

    return overall_score, diagnostic_msg


def merge_parser_results(
    pylatexenc_results: dict,
    regex_results: dict,
    gold_standard_path: Optional[Path] = None
) -> Dict[str, List[ProtectedObject]]:
    """
    AMENDMENT: Merge parser results, preferring gold standard if available.

    Strategy:
    1. If gold standard exists, validate against it and use merged results
    2. Otherwise, use union of parser results with deduplication
    3. Prefer pylatexenc for equations/displaymath (more robust parsing)
    4. Use regex for labels/citations (pylatexenc doesn't extract these)
    """
    if gold_standard_path and gold_standard_path.exists():
        # TODO: Load and validate against gold standard
        pass

    # Merge strategy: union with deduplication by hash
    merged = {
        "equations": {},
        "labels": {},
        "citations": {},
        "displaymath": {},
        "tables": {}
    }

    # Prefer pylatexenc for equations, displaymath, tables
    for obj in pylatexenc_results.get("equations", []):
        merged["equations"][obj.hash] = obj

    # Add regex equations if not already found by pylatexenc
    for obj in regex_results.get("equations", []):
        if obj.hash not in merged["equations"]:
            merged["equations"][obj.hash] = obj
        else:
            # Mark as found by multiple parsers
            existing = merged["equations"][obj.hash]
            if "regex" not in existing.parser_source:
                existing.parser_source += "+regex"

    # Displaymath
    for obj in pylatexenc_results.get("displaymath", []):
        merged["displaymath"][obj.hash] = obj

    for obj in regex_results.get("displaymath", []):
        if obj.hash not in merged["displaymath"]:
            merged["displaymath"][obj.hash] = obj
        else:
            existing = merged["displaymath"][obj.hash]
            if "regex" not in existing.parser_source:
                existing.parser_source += "+regex"

    # Tables (pylatexenc only)
    for obj in pylatexenc_results.get("tables", []):
        merged["tables"][obj.hash] = obj

    # Labels and citations (regex only - pylatexenc doesn't extract these)
    for obj in regex_results.get("labels", []):
        merged["labels"][obj.hash] = obj

    for obj in regex_results.get("citations", []):
        merged["citations"][obj.hash] = obj

    return {k: list(v.values()) for k, v in merged.items()}


def extract_protected_objects(
    source_path: Path,
    snapshot_id: str = None,
    gold_standard_path: Optional[Path] = None
) -> ProtectedManifest:
    """
    AMENDMENT: Parser bake-off extraction with manual gold standard.

    1. Run multiple parsers (pylatexenc, regex)
    2. Compare results and compute agreement score
    3. If gold standard exists, validate against it; otherwise merge results
    4. Warn if parser disagreement >10%
    """
    content = source_path.read_text()
    source_hash = _compute_file_hash(source_path)

    # Run parser bake-off
    pylatexenc_results = extract_with_pylatexenc(content, source_path, source_hash)
    regex_results = extract_with_regex(content, source_path, source_hash)

    # Compute parser agreement
    agreement_score, agreement_diagnostic = compute_parser_agreement(pylatexenc_results, regex_results)

    if agreement_score < 0.9:
        print(f"Warning: Parser disagreement detected (agreement={agreement_score:.2f})")
        print(f"  Diagnostic: {agreement_diagnostic}")

    # Merge results
    merged = merge_parser_results(pylatexenc_results, regex_results, gold_standard_path)

    # Build parser version string
    pylatexenc_version = "2.11" if PYLATEXENC_AVAILABLE else "unavailable"
    parser_version = f"pylatexenc:{pylatexenc_version}+regex:builtin"

    if snapshot_id is None:
        snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    total_count = sum(len(objs) for objs in merged.values())

    return ProtectedManifest(
        source_file=source_path,
        source_file_hash=source_hash,
        snapshot_id=snapshot_id,
        extraction_timestamp=datetime.now(timezone.utc).isoformat(),
        parser_version=parser_version,
        model_version=None,
        parent_artifact_hash=None,
        equations=merged["equations"],
        labels=merged["labels"],
        citations=merged["citations"],
        displaymath=merged["displaymath"],
        tables=merged["tables"],
        total_count=total_count,
        extraction_method="parser_bakeoff_with_provenance",
        parser_agreement_score=agreement_score
    )


def extract_protected_objects_from_text(
    content: str,
    source_file: Path,
    parent_artifact_hash: Optional[str] = None
) -> ProtectedManifest:
    """
    Extract protected objects from text content (for draft/assembly verification).

    Similar to extract_protected_objects but works on in-memory content rather
    than reading from disk. Used for verifying drafted/assembled documents.
    """
    # Write content to temporary file for hash computation
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        source_hash = _compute_file_hash(temp_path)

        # Run parser bake-off
        pylatexenc_results = extract_with_pylatexenc(content, source_file, source_hash)
        regex_results = extract_with_regex(content, source_file, source_hash)

        # Compute parser agreement
        agreement_score, _ = compute_parser_agreement(pylatexenc_results, regex_results)

        # Merge results
        merged = merge_parser_results(pylatexenc_results, regex_results, None)

        pylatexenc_version = "2.11" if PYLATEXENC_AVAILABLE else "unavailable"
        parser_version = f"pylatexenc:{pylatexenc_version}+regex:builtin"

        total_count = sum(len(objs) for objs in merged.values())

        return ProtectedManifest(
            source_file=source_file,
            source_file_hash=source_hash,
            snapshot_id="draft",
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            parser_version=parser_version,
            model_version=None,
            parent_artifact_hash=parent_artifact_hash,
            equations=merged["equations"],
            labels=merged["labels"],
            citations=merged["citations"],
            displaymath=merged["displaymath"],
            tables=merged["tables"],
            total_count=total_count,
            extraction_method="parser_bakeoff_from_text",
            parser_agreement_score=agreement_score
        )
    finally:
        temp_path.unlink()
