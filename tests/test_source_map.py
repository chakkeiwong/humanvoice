"""Tests for the consolidated source-map contract (WP-V2-1).

Two things are being proven here. First, that both existing extractor
representations adapt into one byte-addressed contract without losing raw
forms, normalized forms, hashes, or parser attribution. Second, that a
protected object crossing a span boundary is reported rather than quietly
assigned, because that is the case where a rewrite would damage an object it
was supposed to protect.
"""

import hashlib
from pathlib import Path

import pytest

from humanvoice.partition import partition_text
from humanvoice.source_map import (
    CITATION,
    EQUATION,
    MappedObject,
    UnlocatableObject,
    content_hash,
    from_parser_objects,
    from_protected_manifest,
    link_objects_to_spans,
    locate_in_text,
    manifest_objects,
    normalize_form,
    object_identity,
    verify_objects_against_text,
)

HASH = "a" * 64


def mapped(
    raw="$x$",
    object_type=EQUATION,
    source_file="main.tex",
    byte_start=0,
    byte_end=None,
    line=1,
):
    end = byte_end if byte_end is not None else byte_start + len(raw)
    return MappedObject(
        object_id=object_identity(source_file, object_type, byte_start, end),
        object_type=object_type,
        raw_form=raw,
        normalized_form=normalize_form(raw),
        source_file=source_file,
        byte_start=byte_start,
        byte_end=end,
        line=line,
        content_hash=content_hash(raw),
        parser_source="test",
    )


class TestNormalization:
    def test_whitespace_only_differences_normalize_equal(self):
        assert normalize_form("x  =\n  1") == normalize_form("x = 1")

    def test_normalization_preserves_every_token(self):
        assert normalize_form("\\alpha  \\beta") == "\\alpha \\beta"

    def test_substantive_difference_survives_normalization(self):
        """Normalization must not make two different objects compare equal."""
        assert normalize_form("x = 1") != normalize_form("x = 2")
        assert content_hash("35 bp") != content_hash("53 bp")

    def test_sign_change_is_a_difference(self):
        assert content_hash("+0.35") != content_hash("-0.35")

    def test_brace_style_is_not_erased(self):
        """Aggressive normalization would hide a real structural change."""
        assert content_hash("x_{t+1}") != content_hash("x_t+1")


class TestIdentity:
    def test_identity_is_positional_not_ordinal(self):
        """v1 used eq_0/eq_1, so inserting an equation renumbered the rest."""
        first = object_identity("m.tex", EQUATION, 100, 110)
        same = object_identity("m.tex", EQUATION, 100, 110)
        moved = object_identity("m.tex", EQUATION, 200, 210)
        assert first == same
        assert first != moved

    def test_identity_separates_type_and_file(self):
        assert object_identity("a.tex", EQUATION, 0, 5) != object_identity(
            "b.tex", EQUATION, 0, 5
        )
        assert object_identity("a.tex", EQUATION, 0, 5) != object_identity(
            "a.tex", CITATION, 0, 5
        )


class TestLocation:
    def test_locates_unique_text(self):
        text = "before $x = 1$ after"
        assert locate_in_text(text, "$x = 1$") == (7, 14)

    def test_repeated_text_maps_to_distinct_occurrences(self):
        """The same short equation twice must not collapse onto one range."""
        text = "$x$ then $x$ again"
        used = set()
        first = locate_in_text(text, "$x$", used=used)
        second = locate_in_text(text, "$x$", used=used)
        assert first != second
        assert {first[0], second[0]} == {0, 9}

    def test_line_anchor_selects_the_right_occurrence(self):
        text = "$x$\n\n\n$x$\n"
        # Line 4 holds the second occurrence.
        start, _ = locate_in_text(text, "$x$", line=4)
        assert start == 6

    def test_missing_text_raises_rather_than_guessing(self):
        with pytest.raises(UnlocatableObject):
            locate_in_text("no math here", "$y$")

    def test_empty_needle_raises(self):
        with pytest.raises(UnlocatableObject):
            locate_in_text("text", "")


class _FakeLocation:
    def __init__(self, char_offset=None, line=None):
        self.char_offset = char_offset
        self.line = line


class _FakeParserObject:
    def __init__(self, raw, object_type=EQUATION, char_offset=None, line=None, normalized=None):
        self.raw_form = raw
        self.object_type = object_type
        self.normalized_form = normalized
        self.location = _FakeLocation(char_offset, line)
        self.metadata = {"source": "fake"}


class TestParserAdapter:
    def test_trusted_offset_is_validated_and_used(self):
        text = "prose $x = 1$ prose"
        objects = from_parser_objects(
            [_FakeParserObject("$x = 1$", char_offset=6)],
            text=text,
            source_file="m.tex",
        )
        assert objects[0].byte_start == 6
        assert objects[0].byte_end == 13
        assert text[6:13] == "$x = 1$"

    def test_wrong_offset_falls_back_to_search(self):
        """A bad offset is corrected, not trusted."""
        text = "prose $x = 1$ prose"
        objects = from_parser_objects(
            [_FakeParserObject("$x = 1$", char_offset=999)],
            text=text,
            source_file="m.tex",
        )
        assert text[objects[0].byte_start : objects[0].byte_end] == "$x = 1$"

    def test_metadata_and_normalized_form_are_preserved(self):
        text = "$x  =  1$"
        objects = from_parser_objects(
            [_FakeParserObject("$x  =  1$", char_offset=0, normalized="$x = 1$")],
            text=text,
            source_file="m.tex",
        )
        assert objects[0].normalized_form == "$x = 1$"
        assert objects[0].metadata == {"source": "fake"}

    def test_enum_object_type_is_flattened_to_its_value(self):
        class _Kind:
            value = "equation"

        text = "$x$"
        objects = from_parser_objects(
            [_FakeParserObject("$x$", object_type=_Kind(), char_offset=0)],
            text=text,
            source_file="m.tex",
        )
        assert objects[0].object_type == "equation"


class _FakeManifestObject:
    def __init__(self, content, line_number, normalized=None, parser="regex"):
        self.content = content
        self.content_normalized = normalized or normalize_form(content)
        self.line_number = line_number
        self.parser_source = parser


class _FakeManifest:
    def __init__(self, equations=(), citations=(), labels=(), tables=(), displaymath=()):
        self.equations = list(equations)
        self.citations = list(citations)
        self.labels = list(labels)
        self.tables = list(tables)
        self.displaymath = list(displaymath)
        self.source_file = "m.tex"


class TestManifestAdapter:
    def test_line_numbers_convert_to_byte_offsets(self):
        text = "line one\n$x = 1$\nline three\n"
        objects = from_protected_manifest(
            _FakeManifest(equations=[_FakeManifestObject("$x = 1$", 2)]),
            text=text,
        )
        assert len(objects) == 1
        assert text[objects[0].byte_start : objects[0].byte_end] == "$x = 1$"
        assert objects[0].line == 2

    def test_repeated_content_on_different_lines_stays_distinct(self):
        text = "$x$\n$x$\n"
        objects = from_protected_manifest(
            _FakeManifest(
                equations=[
                    _FakeManifestObject("$x$", 1),
                    _FakeManifestObject("$x$", 2),
                ]
            ),
            text=text,
        )
        starts = sorted(o.byte_start for o in objects)
        assert starts == [0, 4]
        assert objects[0].object_id != objects[1].object_id

    def test_parser_attribution_is_retained(self):
        text = "\\cite{smith}"
        objects = from_protected_manifest(
            _FakeManifest(
                citations=[_FakeManifestObject("\\cite{smith}", 1, parser="pylatexenc")]
            ),
            text=text,
        )
        assert objects[0].parser_source == "pylatexenc"

    def test_all_categories_are_adapted(self):
        text = "$e$ \\cite{c} \\label{l} T D"
        objects = from_protected_manifest(
            _FakeManifest(
                equations=[_FakeManifestObject("$e$", 1)],
                citations=[_FakeManifestObject("\\cite{c}", 1)],
                labels=[_FakeManifestObject("\\label{l}", 1)],
                tables=[_FakeManifestObject("T", 1)],
                displaymath=[_FakeManifestObject("D", 1)],
            ),
            text=text,
        )
        assert len(objects) == 5


class TestVerification:
    def test_matching_objects_verify(self):
        text = "prose $x$ prose"
        assert verify_objects_against_text([mapped(raw="$x$", byte_start=6)], text) == []

    def test_shifted_range_is_reported(self):
        text = "prose $x$ prose"
        errors = verify_objects_against_text([mapped(raw="$x$", byte_start=0)], text)
        assert any("does not match its byte range" in error for error in errors)

    def test_stale_content_hash_is_reported(self):
        text = "$x$"
        stale = MappedObject(
            object_id="obj-1",
            object_type=EQUATION,
            raw_form="$x$",
            normalized_form="$x$",
            source_file="m.tex",
            byte_start=0,
            byte_end=3,
            line=1,
            content_hash="0" * 64,
            parser_source="test",
        )
        errors = verify_objects_against_text([stale], text)
        assert any("stale content hash" in error for error in errors)


class TestSpanLinking:
    def _spans(self, text):
        spans, _ = partition_text(text, "main.tex", HASH)
        return spans

    def test_object_inside_one_span_links_cleanly(self):
        text = "Some prose with $x = 1$ inline.\n"
        spans = self._spans(text)
        objects = from_parser_objects(
            [_FakeParserObject("$x = 1$", char_offset=text.index("$x = 1$"))],
            text=text,
            source_file="main.tex",
        )
        links = link_objects_to_spans(objects, spans)
        assert links.is_clean
        assert sum(len(ids) for ids in links.by_span.values()) == 1

    def test_display_math_links_to_its_own_span(self):
        text = "Prose.\n\n\\begin{equation}\nx = 1\n\\end{equation}\n"
        spans = self._spans(text)
        math_span = next(span for span in spans if span.span_kind == "math")
        objects = [
            mapped(
                raw=math_span.text,
                byte_start=math_span.byte_start,
                byte_end=math_span.byte_end,
            )
        ]
        links = link_objects_to_spans(objects, spans)
        assert links.is_clean
        assert math_span.span_id in links.by_span

    def test_straddling_object_is_reported_not_assigned(self):
        """A unit boundary that splits a protected object must be surfaced."""
        text = "first paragraph\n\nsecond paragraph"
        spans = self._spans(text)
        # A range deliberately spanning the paragraph break.
        straddler = mapped(
            raw=text[10:20],
            byte_start=10,
            byte_end=20,
        )
        links = link_objects_to_spans([straddler], spans)
        assert not links.is_clean
        assert links.straddling
        assert "crosses a span boundary" in links.straddling[0]["reason"]
        assert links.by_span == {}

    def test_object_in_another_file_is_not_linked(self):
        text = "Some prose.\n"
        spans = self._spans(text)
        other = mapped(raw="$x$", source_file="other.tex", byte_start=0)
        links = link_objects_to_spans([other], spans)
        assert not links.is_clean
        assert links.unlocated


class TestManifestRendering:
    def test_rendered_objects_carry_byte_offsets(self):
        rows = manifest_objects([mapped(raw="$x = 1$", byte_start=42, line=3)])
        assert rows[0]["location"]["char_offset"] == 42
        assert rows[0]["location"]["length"] == len("$x = 1$")
        assert rows[0]["location"]["line"] == 3

    def test_rendered_manifest_validates_in_a_record(self):
        from humanvoice.schemas import get_registry

        record = {
            "record_type": "ProtectedManifest",
            "schema_version": "HV-SCHEMA-2.0",
            "record_id": "protected-1",
            "run_id": "run-001",
            "created_at": "2026-09-11T00:00:00Z",
            "source_hash": HASH,
            "objects": manifest_objects([mapped(raw="$x = 1$", byte_start=0)]),
            "parser_name": "pylatexenc",
            "parser_version": "2.10",
        }
        assert get_registry().validate(record, raise_on_error=False) == []


class TestRealSource:
    def test_real_chapter_objects_locate_and_verify(self):
        """Adapt real extractor output over a real chapter end to end."""
        from humanvoice.protected_objects import extract_protected_objects_from_text

        root = Path(__file__).resolve().parents[1]
        relative = "docs/survey/proposal/06_design.tex"
        text = (root / relative).read_text(encoding="utf-8")

        manifest = extract_protected_objects_from_text(text, Path(relative), HASH)
        objects = from_protected_manifest(manifest, text=text, source_file=relative)
        assert objects, "real chapter yielded no protected objects"
        assert verify_objects_against_text(objects, text) == []

        spans, _ = partition_text(text, relative, HASH)
        links = link_objects_to_spans(objects, spans)
        # Every located object must land in exactly one span, or be reported.
        assert (
            sum(len(ids) for ids in links.by_span.values())
            + len(links.straddling)
            + len(links.unlocated)
            == len(objects)
        )
