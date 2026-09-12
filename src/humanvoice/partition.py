"""Deterministic complete partitioning of a LaTeX source tree into spans.

Every byte of every source file lands in exactly one span. That completeness is
the point: v1 planned from section titles, so anything the planner did not
notice was silently absent from the plan and therefore from the output. A
partition that covers the whole file makes "we never looked at this text" a
detectable state rather than an invisible one.

Three properties matter and are all tested:

* **Complete.** The spans for one file tile its byte range with no gaps and no
  overlaps, from offset 0 to the file's length.
* **Deterministic.** The same bytes always produce the same spans with the same
  identifiers. Span identity is derived from the source hash and byte offsets,
  never from model output or wording, so a re-run or a second operator gets the
  same partition.
* **Conservative about meaning.** The partitioner classifies *form* — this is a
  comment, this is display math, this is a float. It does not decide what
  carries meaning. Anything that could carry a concept is left `unresolved` for
  the inventory phase to classify and a human to adjudicate. Guessing here
  would recreate the v1 failure in a new place.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

# Span kinds, matching schemas/source-span.schema.json.
PROSE = "prose"
HEADING = "heading"
COMMENT = "comment"
MATH = "math"
FLOAT = "float"
BIBLIOGRAPHY = "bibliography"
COMMAND = "command"
WHITESPACE = "whitespace"
OTHER = "other"

# Coverage dispositions, matching the same schema.
CONCEPT_BEARING = "concept_bearing"
PROTECTED_STRUCTURAL = "protected_structural"
NON_SUBSTANTIVE_SCAFFOLDING = "non_substantive_scaffolding"
UNRESOLVED = "unresolved"

# Sectioning commands introduce a heading span; the heading text itself is
# reader-facing and frequently states a concept, so it is never scaffolding.
SECTIONING = (
    "part",
    "chapter",
    "section",
    "subsection",
    "subsubsection",
    "paragraph",
    "subparagraph",
)

# Environments whose interior is an exact protected object. Their content is
# preserved verbatim, so the partitioner keeps each one whole rather than
# splitting prose out of it.
MATH_ENVIRONMENTS = (
    "equation",
    "equation*",
    "align",
    "align*",
    "alignat",
    "alignat*",
    "gather",
    "gather*",
    "multline",
    "multline*",
    "eqnarray",
    "eqnarray*",
    "displaymath",
    "math",
    "flalign",
    "flalign*",
    "split",
    "IEEEeqnarray",
)

FLOAT_ENVIRONMENTS = (
    "figure",
    "figure*",
    "table",
    "table*",
    "tabular",
    "tabularx",
    "longtable",
    "tikzpicture",
    "algorithm",
    "algorithmic",
    "lstlisting",
    "verbatim",
    "Verbatim",
    "minted",
    "listing",
)

BIBLIOGRAPHY_COMMANDS = (
    "bibliography",
    "bibliographystyle",
    "printbibliography",
    "addbibresource",
    "nocite",
)

# Preamble and layout commands that carry no reader-facing meaning on their
# own. Kept as COMMAND spans so they are accounted for without being offered
# to the concept inventory.
_PREAMBLE_COMMANDS = (
    "documentclass",
    "usepackage",
    "input",
    "include",
    "includeonly",
    "newcommand",
    "renewcommand",
    "providecommand",
    "DeclareMathOperator",
    "newenvironment",
    "renewenvironment",
    "newtheorem",
    "setlength",
    "addtolength",
    "setcounter",
    "addtocounter",
    "pagestyle",
    "thispagestyle",
    "geometry",
    "hypersetup",
    "definecolor",
    "graphicspath",
    "label",
    "maketitle",
    "tableofcontents",
    "listoffigures",
    "listoftables",
    "appendix",
    "clearpage",
    "newpage",
    "pagebreak",
    "noindent",
    "centering",
    "raggedright",
    "small",
    "footnotesize",
    "normalsize",
    "large",
    "Large",
    "huge",
    "Huge",
)


@dataclass(frozen=True)
class Span:
    """One contiguous, non-overlapping region of one source file.

    Byte offsets are the identity. Line numbers are derived for human
    readability and never used for matching, because a line number changes
    whenever anything above it changes.
    """

    span_id: str
    source_file: str
    byte_start: int
    byte_end: int
    line_start: int
    line_end: int
    span_kind: str
    reader_facing: bool
    coverage_disposition: str
    exact_text_hash: str
    structural_parent_id: str | None = None
    text: str = field(default="", repr=False, compare=False)

    @property
    def byte_length(self) -> int:
        return self.byte_end - self.byte_start


def span_identity(source_hash: str, source_file: str, byte_start: int, byte_end: int) -> str:
    """Derive a stable span ID from the source bytes it covers.

    Deliberately independent of any model, of the order spans were produced in,
    and of the surrounding text's content. Two runs over identical bytes agree;
    a run over changed bytes does not silently reuse an old identity.
    """
    digest = hashlib.sha256(
        b"\x00".join(
            (
                source_hash.encode("utf-8"),
                source_file.encode("utf-8"),
                str(byte_start).encode("ascii"),
                str(byte_end).encode("ascii"),
            )
        )
    ).hexdigest()
    return f"span-{digest[:16]}"


def text_hash(text: str) -> str:
    """Hash the exact span text, so a later phase can prove it is unchanged."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line_index(text: str) -> list[int]:
    """Byte offset of the start of each line, for offset-to-line lookup."""
    offsets = [0]
    for match in re.finditer(r"\n", text):
        offsets.append(match.end())
    return offsets


def _line_of(line_starts: Sequence[int], offset: int) -> int:
    """1-based line number containing a byte offset (binary search)."""
    low, high = 0, len(line_starts) - 1
    while low < high:
        middle = (low + high + 1) // 2
        if line_starts[middle] <= offset:
            low = middle
        else:
            high = middle - 1
    return low + 1


@dataclass(frozen=True)
class _Region:
    start: int
    end: int
    kind: str
    reader_facing: bool


_ENVIRONMENT_START = re.compile(r"\\begin\{([^}]{1,64})\}")
_COMMAND = re.compile(r"\\([A-Za-z@]+)\*?")
_SECTIONING = re.compile(
    r"\\(" + "|".join(SECTIONING) + r")\*?\s*(?:\[[^\]]*\])?\s*\{"
)


def _matching_environment_end(text: str, name: str, from_offset: int) -> int:
    r"""Byte offset just past the \end{name} that closes this \begin{name}.

    Counts nested openings of the same name so that a tabular inside a tabular
    does not close the outer one early. Returns -1 when the environment is
    never closed, which the caller reports rather than guessing a boundary.
    """
    depth = 1
    pattern = re.compile(
        r"\\(begin|end)\{" + re.escape(name) + r"\}"
    )
    position = from_offset
    while True:
        match = pattern.search(text, position)
        if match is None:
            return -1
        depth += 1 if match.group(1) == "begin" else -1
        position = match.end()
        if depth == 0:
            return match.end()


def _brace_group_end(text: str, open_brace: int) -> int:
    """Byte offset just past the '}' matching the '{' at open_brace.

    Skips escaped braces. Returns -1 if unbalanced, which is a parse
    abstention rather than a silent truncation.
    """
    depth = 0
    position = open_brace
    length = len(text)
    while position < length:
        character = text[position]
        if character == "\\" and position + 1 < length:
            position += 2
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return position + 1
        position += 1
    return -1


def _scan_regions(text: str, abstentions: list[dict[str, str]]) -> list[_Region]:
    r"""Find every structurally special region in one forward pass.

    Order matters and is not arbitrary. A `%` comment hides everything to the
    end of its line, including what would otherwise look like an environment,
    so comments must be recognized as the scan reaches them rather than found
    by a separate later pass. Verbatim-like environments hide `%` in turn. A
    single left-to-right scan is the only way to get both right.
    """
    regions: list[_Region] = []
    position = 0
    length = len(text)

    while position < length:
        character = text[position]

        # Escaped character: consume both bytes so \% and \\ cannot be
        # mistaken for a comment or a command.
        if character == "\\" and position + 1 < length:
            following = text[position + 1]
            if not following.isalpha() and following != "@":
                position += 2
                continue

            environment = _ENVIRONMENT_START.match(text, position)
            if environment is not None:
                name = environment.group(1)
                end = _matching_environment_end(text, name, environment.end())
                if end < 0:
                    abstentions.append({
                        "construct": f"\\begin{{{name}}}",
                        "reason": "environment is never closed",
                    })
                    position = environment.end()
                    continue
                if name in MATH_ENVIRONMENTS:
                    regions.append(_Region(position, end, MATH, True))
                elif name in FLOAT_ENVIRONMENTS:
                    regions.append(_Region(position, end, FLOAT, True))
                else:
                    # An unrecognized environment may well contain prose, so
                    # its delimiters are commands and its interior is scanned
                    # normally. Nothing is assumed about its meaning.
                    regions.append(
                        _Region(position, environment.end(), COMMAND, False)
                    )
                    position = environment.end()
                    continue
                position = end
                continue

            heading = _SECTIONING.match(text, position)
            if heading is not None:
                brace = text.index("{", heading.end() - 1)
                end = _brace_group_end(text, brace)
                if end < 0:
                    abstentions.append({
                        "construct": text[position:heading.end()],
                        "reason": "sectioning argument has unbalanced braces",
                    })
                    position = heading.end()
                    continue
                regions.append(_Region(position, end, HEADING, True))
                position = end
                continue

            command = _COMMAND.match(text, position)
            if command is not None:
                name = command.group(1)
                end = command.end()
                if name in BIBLIOGRAPHY_COMMANDS:
                    while end < length and text[end] in "{[":
                        closed = _brace_group_end(text, end) if text[end] == "{" else -1
                        if closed < 0:
                            break
                        end = closed
                    regions.append(_Region(position, end, BIBLIOGRAPHY, False))
                    position = end
                    continue
                if name in _PREAMBLE_COMMANDS:
                    while end < length and text[end] in "{[":
                        if text[end] == "{":
                            closed = _brace_group_end(text, end)
                        else:
                            bracket = text.find("]", end)
                            closed = bracket + 1 if bracket >= 0 else -1
                        if closed < 0:
                            break
                        end = closed
                    regions.append(_Region(position, end, COMMAND, False))
                    position = end
                    continue
                # Any other macro is left inline: it is usually part of a
                # sentence (\emph, \citep, \ref) and splitting it out would
                # fragment prose that a reader reads as one thought.
                position = end
                continue

            position += 1
            continue

        # Inline math: $...$ and \(...\) are protected exact objects.
        if character == "$":
            if text.startswith("$$", position):
                closing = text.find("$$", position + 2)
                end = closing + 2 if closing >= 0 else -1
            else:
                end = _inline_math_end(text, position)
            if end < 0:
                abstentions.append({
                    "construct": "$",
                    "reason": "inline math is never closed",
                })
                position += 1
                continue
            regions.append(_Region(position, end, MATH, True))
            position = end
            continue

        if character == "%":
            newline = text.find("\n", position)
            end = newline if newline >= 0 else length
            regions.append(_Region(position, end, COMMENT, False))
            position = end
            continue

        position += 1

    return regions


def _inline_math_end(text: str, dollar: int) -> int:
    """Offset just past the '$' closing an inline math run."""
    position = dollar + 1
    length = len(text)
    while position < length:
        if text[position] == "\\" and position + 1 < length:
            position += 2
            continue
        if text[position] == "$":
            return position + 1
        position += 1
    return -1


def _default_disposition(kind: str) -> str:
    """Map a span's form to its initial coverage disposition.

    Only forms whose disposition is a fact get a final answer here: math,
    floats, and whitespace are structural material that assembly preserves
    byte-identically. Note that whitespace is `protected_structural` rather
    than `non_substantive_scaffolding` — the scaffolding disposition is a
    reviewed judgement that specific text is reader-irrelevant and may be
    removed, and it requires an accountable ScaffoldingDisposition record. A
    blank line has no such judgement attached to it.

    Everything a reader actually reads — prose, headings, comments, commands —
    stays `unresolved`, because whether it carries a concept is a semantic
    question this module has no basis to answer. The inventory phase decides
    and a human adjudicates.
    """
    if kind in (MATH, FLOAT, WHITESPACE):
        return PROTECTED_STRUCTURAL
    return UNRESOLVED


def _split_prose(text: str, start: int, end: int) -> Iterator[tuple[int, int, str]]:
    """Split an unclaimed run into paragraph-sized prose and whitespace spans.

    A blank line is the paragraph boundary LaTeX itself uses, which makes it
    the boundary a reader perceives. Whitespace between paragraphs becomes its
    own span so that prose spans hold only prose: a rewrite that replaces a
    paragraph must not have to reproduce the exact blank lines around it.
    """
    segment = text[start:end]
    if not segment:
        return
    if not segment.strip():
        yield start, end, WHITESPACE
        return

    position = 0
    for match in re.finditer(r"\n[ \t]*\n[ \s]*", segment):
        if match.start() > position:
            yield start + position, start + match.start(), PROSE
        yield start + match.start(), start + match.end(), WHITESPACE
        position = match.end()
    if position < len(segment):
        yield start + position, end, PROSE


def partition_text(
    text: str,
    source_file: str,
    source_hash: str,
) -> tuple[list[Span], list[dict[str, str]]]:
    """Partition one file's text into a gapless, non-overlapping span list.

    Returns the spans in byte order plus any abstentions. An abstention means
    the partitioner could not determine a boundary (an unclosed environment,
    unbalanced braces); it never means a byte was dropped. Unparsed regions
    still receive a span, marked `unresolved`, so downstream coverage checks
    see them.
    """
    abstentions: list[dict[str, str]] = []
    regions = _scan_regions(text, abstentions)

    # Drop any region contained in an earlier one. The scan already skips past
    # what it consumes, so this only removes pathological overlaps, but a
    # partition that silently overlapped would corrupt every later offset.
    regions.sort(key=lambda region: (region.start, -region.end))
    claimed: list[_Region] = []
    for region in regions:
        if claimed and region.start < claimed[-1].end:
            continue
        claimed.append(region)

    pieces: list[tuple[int, int, str, bool]] = []
    cursor = 0
    for region in claimed:
        if region.start > cursor:
            for start, end, kind in _split_prose(text, cursor, region.start):
                pieces.append((start, end, kind, kind == PROSE))
        pieces.append((region.start, region.end, region.kind, region.reader_facing))
        cursor = region.end
    if cursor < len(text):
        for start, end, kind in _split_prose(text, cursor, len(text)):
            pieces.append((start, end, kind, kind == PROSE))

    line_starts = _line_index(text)
    spans: list[Span] = []
    for start, end, kind, reader_facing in pieces:
        if start == end:
            continue
        body = text[start:end]
        spans.append(
            Span(
                span_id=span_identity(source_hash, source_file, start, end),
                source_file=source_file,
                byte_start=start,
                byte_end=end,
                line_start=_line_of(line_starts, start),
                line_end=_line_of(line_starts, max(start, end - 1)),
                span_kind=kind,
                reader_facing=reader_facing and kind != WHITESPACE,
                coverage_disposition=_default_disposition(kind),
                exact_text_hash=text_hash(body),
                text=body,
            )
        )
    return spans, abstentions


def verify_partition(spans: Sequence[Span], total_bytes: int) -> list[str]:
    """Return the reasons a span list is not a valid partition.

    This is the invariant the whole phase rests on, so it is checked rather
    than assumed. An empty list means the spans tile [0, total_bytes) exactly.
    """
    errors: list[str] = []
    ordered = sorted(spans, key=lambda span: span.byte_start)
    cursor = 0
    for span in ordered:
        if span.byte_start < cursor:
            errors.append(
                f"span {span.span_id} overlaps the previous span at byte {span.byte_start}"
            )
        elif span.byte_start > cursor:
            errors.append(
                f"partition gap in {span.source_file}: bytes {cursor}-{span.byte_start}"
            )
        if span.byte_end <= span.byte_start:
            errors.append(f"span {span.span_id} is empty or inverted")
        cursor = max(cursor, span.byte_end)
    if cursor != total_bytes:
        errors.append(f"partition covers {cursor} of {total_bytes} bytes")
    identifiers = [span.span_id for span in ordered]
    if len(set(identifiers)) != len(identifiers):
        errors.append("partition contains duplicate span identifiers")
    return errors


def partition_tree(
    source_root: Path,
    relative_paths: Iterable[str],
    source_hash: str,
) -> tuple[dict[str, list[Span]], list[dict[str, str]]]:
    """Partition every file in a snapshot, keyed by relative path.

    Files are processed in sorted order so the result is reproducible
    regardless of filesystem enumeration order.
    """
    by_file: dict[str, list[Span]] = {}
    abstentions: list[dict[str, str]] = []
    for relative in sorted(relative_paths):
        path = source_root / relative
        text = path.read_text(encoding="utf-8")
        spans, file_abstentions = partition_text(text, relative, source_hash)
        problems = verify_partition(spans, len(text))
        if problems:
            # A partition that does not tile its file is a defect in this
            # module, not a property of the document. Surface it loudly.
            raise AssertionError(
                f"incomplete partition for {relative}: " + "; ".join(problems)
            )
        by_file[relative] = spans
        for abstention in file_abstentions:
            abstentions.append({**abstention, "source_file": relative})
    return by_file, abstentions


def span_records(
    spans: Sequence[Span],
    *,
    run_id: str,
    snapshot_id: str,
    source_hash: str,
    created_at: str,
    schema_version: str = "HV-SCHEMA-2.0",
) -> list[dict[str, object]]:
    """Render spans as SourceSpan records for the shared schema registry.

    Concept, protected-object, and scaffolding links are emitted empty. This
    module establishes coverage; the inventory and protected-object phases fill
    those in. Emitting a guess here would let an unreviewed link look reviewed.
    """
    records: list[dict[str, object]] = []
    for span in spans:
        records.append(
            {
                "record_type": "SourceSpan",
                "schema_version": schema_version,
                "record_id": span.span_id,
                "run_id": run_id,
                "created_at": created_at,
                "snapshot_id": snapshot_id,
                "source_hash": source_hash,
                "source_file": span.source_file,
                "byte_start": span.byte_start,
                "byte_end": span.byte_end,
                "line_start": span.line_start,
                "line_end": span.line_end,
                "exact_text_hash": span.exact_text_hash,
                "span_kind": span.span_kind,
                "reader_facing": span.reader_facing,
                "structural_parent_id": span.structural_parent_id,
                "coverage_disposition": span.coverage_disposition,
                "concept_ids": [],
                "protected_object_ids": [],
                "scaffolding_disposition_ids": [],
            }
        )
    return records


def coverage_summary(spans: Sequence[Span]) -> dict[str, object]:
    """Counts an operator needs to see before approving an inventory.

    `unresolved_reader_facing_bytes` is the number that matters: it is how much
    of what a reader reads has not yet been classified. Rewriting may not start
    while it is nonzero.
    """
    by_kind: dict[str, int] = {}
    by_disposition: dict[str, int] = {}
    unresolved_reader_bytes = 0
    reader_bytes = 0
    for span in spans:
        by_kind[span.span_kind] = by_kind.get(span.span_kind, 0) + span.byte_length
        by_disposition[span.coverage_disposition] = (
            by_disposition.get(span.coverage_disposition, 0) + span.byte_length
        )
        if span.reader_facing:
            reader_bytes += span.byte_length
            if span.coverage_disposition == UNRESOLVED:
                unresolved_reader_bytes += span.byte_length
    return {
        "span_count": len(spans),
        "total_bytes": sum(span.byte_length for span in spans),
        "reader_facing_bytes": reader_bytes,
        "unresolved_reader_facing_bytes": unresolved_reader_bytes,
        "bytes_by_kind": dict(sorted(by_kind.items())),
        "bytes_by_disposition": dict(sorted(by_disposition.items())),
    }
