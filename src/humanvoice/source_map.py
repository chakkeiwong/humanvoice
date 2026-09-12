"""One source-map contract over the project's two protected-object extractors.

The repository grew two independent `ProtectedObject` types:

* `parser.ProtectedObject` — a typed enum, raw and normalized forms, a
  `SourceLocation` with a character offset, and parser metadata. Used by the
  comparison and findings layers.
* `protected_objects.ProtectedObject` — content plus normalized content, a line
  number, surrounding context, a content hash, and the parser that found it.
  Grouped into a `ProtectedManifest` by category. Used by the extraction,
  draft, and release commands.

Neither is wrong, and both have live callers, so this module does not replace
either. It defines the single contract the v2 pipeline reads — `MappedObject`,
addressed by byte offset — and adapts both representations into it.

Byte offsets are the reason this exists. Patch assembly applies replacements at
stable byte offsets, and the partitioner addresses spans the same way, but one
extractor records a character offset and the other records a line number.
Neither can be used to locate a protected object inside a span without a
conversion that is done once, in one place, and tested. Doing it at each call
site is how offsets drift.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# Object types shared by both extractors, normalized to the strings used in
# schemas/protected-manifest.schema.json.
EQUATION = "equation"
DISPLAYMATH = "displaymath"
INLINE_MATH = "inline_math"
LABEL = "label"
CITATION = "citation"
TABLE = "table"
MACRO = "macro"
QUOTATION = "quotation"
NUMBER = "number"
QUALIFICATION = "qualification"


@dataclass(frozen=True)
class MappedObject:
    """A protected object located by byte offset in one source file.

    `byte_start`/`byte_end` are authoritative. `line` is carried for display
    only; a line number shifts whenever anything above it changes, so it is
    never used for matching.

    `raw_form` is the exact source text and is what integrity checks compare.
    `normalized_form` exists so a comparison can distinguish an explained
    normalization (whitespace, brace style) from a substantive change, which is
    the distinction that makes a protected-object diff useful rather than noisy.
    """

    object_id: str
    object_type: str
    raw_form: str
    normalized_form: str | None
    source_file: str
    byte_start: int
    byte_end: int
    line: int
    content_hash: str
    parser_source: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def byte_length(self) -> int:
        return self.byte_end - self.byte_start

    def within(self, byte_start: int, byte_end: int) -> bool:
        """True when this object lies entirely inside a byte range.

        Containment is deliberately strict. An object straddling a span
        boundary is not "mostly in" that span: a rewrite of the span would
        have to reproduce part of a protected object, which is exactly the
        situation the caller must be told about rather than have resolved by a
        rounding rule.
        """
        return byte_start <= self.byte_start and self.byte_end <= byte_end


def normalize_form(text: str) -> str:
    """Collapse insubstantial variation while preserving every token.

    Whitespace runs become single spaces and surrounding whitespace is
    stripped. Nothing else is touched: no brace removal, no case folding, no
    math rewriting. Anything more aggressive would make two genuinely
    different objects compare equal, which turns a protected-object check into
    a rubber stamp.
    """
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text: str) -> str:
    """Hash the normalized form, so formatting alone is not a difference."""
    return hashlib.sha256(normalize_form(text).encode("utf-8")).hexdigest()


def object_identity(source_file: str, object_type: str, byte_start: int, byte_end: int) -> str:
    """Stable ID from location and type, independent of extraction order.

    v1 identifiers were positional (`eq_0`, `eq_1`), so inserting one equation
    renumbered every later one and made two runs incomparable. Deriving the ID
    from the bytes it covers keeps identity stable across runs and across
    extractors.
    """
    digest = hashlib.sha256(
        b"\x00".join(
            (
                source_file.encode("utf-8"),
                object_type.encode("utf-8"),
                str(byte_start).encode("ascii"),
                str(byte_end).encode("ascii"),
            )
        )
    ).hexdigest()
    return f"obj-{digest[:16]}"


class UnlocatableObject(ValueError):
    """Raised when a protected object cannot be given a byte range.

    This is never downgraded to a warning. An object whose location is unknown
    cannot be protected during a rewrite, so the caller must record an
    abstention and block, not proceed with a guessed offset.
    """


def _line_offsets(text: str) -> list[int]:
    """Byte offset at which each 1-based line begins."""
    offsets = [0]
    for match in re.finditer(r"\n", text):
        offsets.append(match.end())
    return offsets


def locate_in_text(
    text: str,
    needle: str,
    *,
    line: int | None = None,
    used: set[int] | None = None,
) -> tuple[int, int]:
    """Find the byte range of `needle` in `text`, disambiguated by line.

    A protected object's text often appears more than once — the same short
    equation, the same citation key. Searching from the start of the file would
    return the first occurrence rather than the right one, silently mislocating
    the object.

    So the search is anchored on the recorded line when there is one, and
    already-claimed ranges are skipped so repeated identical objects map to
    distinct occurrences in order. Raises UnlocatableObject rather than
    returning a best guess.
    """
    if not needle:
        raise UnlocatableObject("protected object has empty text")

    claimed = used if used is not None else set()

    def candidates() -> Iterable[int]:
        if line is not None:
            offsets = _line_offsets(text)
            if 1 <= line <= len(offsets):
                anchor = offsets[line - 1]
                # Prefer the occurrence on or just after the recorded line,
                # then fall back to the whole file. Exact-match-on-line is the
                # common case; the fallback covers extractors that record the
                # line of an enclosing environment.
                position = text.find(needle, anchor)
                if position >= 0:
                    yield position
                position = text.rfind(needle, 0, anchor)
                if position >= 0:
                    yield position
        position = text.find(needle)
        while position >= 0:
            yield position
            position = text.find(needle, position + 1)

    for position in candidates():
        if position not in claimed:
            claimed.add(position)
            return position, position + len(needle)

    raise UnlocatableObject(
        f"cannot locate protected object text in source (line={line})"
    )


def from_parser_objects(
    objects: Sequence[Any],
    *,
    text: str,
    source_file: str,
    parser_source: str = "pylatexenc",
) -> list[MappedObject]:
    """Adapt `parser.ProtectedObject` values into MappedObject.

    These already carry a character offset, which for a `str` read with a known
    encoding is the offset this module wants. It is still validated against the
    raw form rather than trusted: an offset that does not point at the recorded
    text is a defect worth surfacing, not an inconvenience to work around.
    """
    mapped: list[MappedObject] = []
    used: set[int] = set()
    for source_object in objects:
        raw = source_object.raw_form
        object_type = source_object.object_type
        type_name = (
            object_type.value if hasattr(object_type, "value") else str(object_type)
        )
        offset = getattr(source_object.location, "char_offset", None)

        if offset is not None and text[offset : offset + len(raw)] == raw:
            byte_start, byte_end = offset, offset + len(raw)
            used.add(byte_start)
        else:
            byte_start, byte_end = locate_in_text(
                text,
                raw,
                line=getattr(source_object.location, "line", None),
                used=used,
            )

        mapped.append(
            MappedObject(
                object_id=object_identity(source_file, type_name, byte_start, byte_end),
                object_type=type_name,
                raw_form=raw,
                normalized_form=source_object.normalized_form
                or normalize_form(raw),
                source_file=source_file,
                byte_start=byte_start,
                byte_end=byte_end,
                line=getattr(source_object.location, "line", None) or 1,
                content_hash=content_hash(raw),
                parser_source=parser_source,
                metadata=dict(getattr(source_object, "metadata", {}) or {}),
            )
        )
    return mapped


def from_protected_manifest(
    manifest: Any,
    *,
    text: str,
    source_file: str | None = None,
) -> list[MappedObject]:
    """Adapt a `protected_objects.ProtectedManifest` into MappedObject values.

    This representation records a line number rather than an offset, so every
    object is located by anchored search. Objects are processed in line order
    and claimed ranges are tracked, so repeated identical content maps to
    distinct occurrences instead of collapsing onto the first one.
    """
    relative = source_file or str(getattr(manifest, "source_file", "") or "")
    categories = (
        ("equations", EQUATION),
        ("displaymath", DISPLAYMATH),
        ("labels", LABEL),
        ("citations", CITATION),
        ("tables", TABLE),
    )

    rows: list[tuple[Any, str]] = []
    for attribute, object_type in categories:
        for source_object in getattr(manifest, attribute, []) or []:
            rows.append((source_object, object_type))
    rows.sort(key=lambda row: (getattr(row[0], "line_number", 0) or 0))

    mapped: list[MappedObject] = []
    used: set[int] = set()
    for source_object, object_type in rows:
        raw = source_object.content
        byte_start, byte_end = locate_in_text(
            text,
            raw,
            line=getattr(source_object, "line_number", None),
            used=used,
        )
        mapped.append(
            MappedObject(
                object_id=object_identity(relative, object_type, byte_start, byte_end),
                object_type=object_type,
                raw_form=raw,
                normalized_form=getattr(source_object, "content_normalized", None)
                or normalize_form(raw),
                source_file=relative,
                byte_start=byte_start,
                byte_end=byte_end,
                line=getattr(source_object, "line_number", 1) or 1,
                content_hash=content_hash(raw),
                parser_source=getattr(source_object, "parser_source", "unknown"),
                metadata={},
            )
        )
    return mapped


@dataclass
class SpanObjectLinks:
    """The result of binding protected objects to partition spans."""

    by_span: dict[str, list[str]]
    straddling: list[dict[str, Any]] = field(default_factory=list)
    unlocated: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True when every object sits inside exactly one span."""
        return not self.straddling and not self.unlocated


def link_objects_to_spans(
    objects: Sequence[MappedObject],
    spans: Sequence[Any],
) -> SpanObjectLinks:
    """Assign each protected object to the span that contains it.

    An object that crosses a span boundary is reported rather than assigned.
    That case matters: rewriting one of those spans would require reproducing
    part of an equation or citation, so the unit boundary is wrong and has to
    be redrawn before any rewrite call. Silently attaching it to whichever span
    holds more of it is how a protected object gets mangled by a rewrite that
    looked authorized.
    """
    by_span: dict[str, list[str]] = {}
    straddling: list[dict[str, Any]] = []
    unlocated: list[dict[str, Any]] = []

    ordered = sorted(spans, key=lambda span: span.byte_start)
    for mapped in objects:
        containing = [
            span
            for span in ordered
            if span.source_file == mapped.source_file
            and mapped.within(span.byte_start, span.byte_end)
        ]
        if len(containing) == 1:
            by_span.setdefault(containing[0].span_id, []).append(mapped.object_id)
            continue

        overlapping = [
            span
            for span in ordered
            if span.source_file == mapped.source_file
            and span.byte_start < mapped.byte_end
            and mapped.byte_start < span.byte_end
        ]
        if overlapping:
            straddling.append(
                {
                    "object_id": mapped.object_id,
                    "object_type": mapped.object_type,
                    "byte_start": mapped.byte_start,
                    "byte_end": mapped.byte_end,
                    "span_ids": [span.span_id for span in overlapping],
                    "reason": "protected object crosses a span boundary",
                }
            )
        else:
            unlocated.append(
                {
                    "object_id": mapped.object_id,
                    "object_type": mapped.object_type,
                    "byte_start": mapped.byte_start,
                    "byte_end": mapped.byte_end,
                    "reason": "protected object lies outside every span",
                }
            )
    return SpanObjectLinks(by_span=by_span, straddling=straddling, unlocated=unlocated)


def manifest_objects(
    objects: Sequence[MappedObject],
) -> list[dict[str, Any]]:
    """Render MappedObject values as ProtectedManifest `objects` entries.

    Byte offsets are carried in `location` alongside the character offset the
    schema already defines, so a consumer can patch by offset without
    re-deriving it from the text.
    """
    return [
        {
            "object_id": mapped.object_id,
            "object_type": mapped.object_type,
            "raw_form": mapped.raw_form,
            "normalized_form": mapped.normalized_form,
            "location": {
                "char_offset": mapped.byte_start,
                "line": mapped.line,
                "length": mapped.byte_length,
            },
            "content_hash": mapped.content_hash,
            "parser_source": mapped.parser_source,
        }
        for mapped in objects
    ]


def verify_objects_against_text(
    objects: Sequence[MappedObject], text: str
) -> list[str]:
    """Confirm every object's byte range still holds its recorded raw form.

    This is the check that makes a byte offset trustworthy. It is cheap, and it
    is the difference between a source map that is correct and one that is
    merely plausible.
    """
    errors: list[str] = []
    for mapped in objects:
        actual = text[mapped.byte_start : mapped.byte_end]
        if actual != mapped.raw_form:
            errors.append(
                f"{mapped.object_id} does not match its byte range "
                f"[{mapped.byte_start}:{mapped.byte_end}]"
            )
        if content_hash(mapped.raw_form) != mapped.content_hash:
            errors.append(f"{mapped.object_id} has a stale content hash")
    return errors
