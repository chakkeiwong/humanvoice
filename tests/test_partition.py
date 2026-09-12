"""Tests for deterministic complete source partitioning (WP-V2-1).

The partition is the foundation for every later semantic claim: if a byte is
not in a span, no inventory can find its concepts, and no coverage check can
report it missing. So completeness and determinism are tested directly, and
against real project sources rather than only toy strings.
"""

import hashlib

import pytest

from humanvoice.partition import (
    BIBLIOGRAPHY,
    COMMAND,
    COMMENT,
    FLOAT,
    HEADING,
    MATH,
    NON_SUBSTANTIVE_SCAFFOLDING,
    PROSE,
    PROTECTED_STRUCTURAL,
    UNRESOLVED,
    WHITESPACE,
    coverage_summary,
    partition_text,
    span_identity,
    span_records,
    verify_partition,
)

HASH = "a" * 64


def partition(text, name="main.tex"):
    spans, abstentions = partition_text(text, name, HASH)
    assert verify_partition(spans, len(text)) == [], "partition is not gapless"
    return spans, abstentions


def kinds(spans):
    return [span.span_kind for span in spans]


def reassemble(spans, text):
    return "".join(span.text for span in sorted(spans, key=lambda s: s.byte_start))


class TestCompleteness:
    """Every byte lands in exactly one span."""

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "plain prose",
            "% just a comment",
            "\n\n\n",
            "prose\n\n% comment\n\nmore prose",
            "\\section{Title}\nBody text.\n",
            "Text \\[ x = 1 \\] more text",
            "$a+b$ and $$c$$ and \\(d\\)",
            "\\begin{equation}\nE=mc^2\n\\end{equation}\n",
            "\\begin{figure}\n\\includegraphics{a}\n\\end{figure}",
            "\\documentclass{article}\n\\usepackage{amsmath}\n",
            "\\bibliography{refs}\n",
            "Escaped \\% percent and \\\\ backslash",
            "Nested \\begin{tabular}{cc}\\begin{tabular}{c}a\\end{tabular}\\end{tabular}",
            "unicode: \u03b1\u03b2\u03b3 \u2014 em dash",
            "trailing whitespace   \n\t\n",
        ],
    )
    def test_partition_tiles_the_file(self, text):
        spans, _ = partition(text)
        assert reassemble(spans, text) == text

    def test_no_empty_spans(self):
        spans, _ = partition("a\n\nb\n\n\n\nc")
        assert all(span.byte_length > 0 for span in spans)

    def test_reported_gap_is_detected(self):
        spans, _ = partition("first paragraph\n\nsecond paragraph")
        # Drop a span and confirm verify_partition notices, so the guard in
        # partition_tree cannot pass on a broken partition.
        problems = verify_partition(spans[1:], sum(s.byte_length for s in spans))
        assert any("gap" in problem or "covers" in problem for problem in problems)

    def test_overlap_is_detected(self):
        spans, _ = partition("alpha\n\nbeta")
        first = spans[0]
        clashing = type(first)(
            span_id="span-clash",
            source_file=first.source_file,
            byte_start=first.byte_start,
            byte_end=first.byte_end + 1,
            line_start=1,
            line_end=1,
            span_kind=PROSE,
            reader_facing=True,
            coverage_disposition=UNRESOLVED,
            exact_text_hash=HASH,
        )
        problems = verify_partition([first, clashing], first.byte_end + 1)
        assert any("overlap" in problem for problem in problems)


class TestDeterminism:
    def test_same_bytes_give_same_spans(self):
        text = "\\section{A}\nProse.\n\n\\begin{equation}x\\end{equation}\n"
        first, _ = partition(text)
        second, _ = partition(text)
        assert [s.span_id for s in first] == [s.span_id for s in second]
        assert [s.byte_start for s in first] == [s.byte_start for s in second]

    def test_identity_depends_on_source_hash(self):
        assert span_identity("a" * 64, "m.tex", 0, 10) != span_identity(
            "b" * 64, "m.tex", 0, 10
        )

    def test_identity_depends_on_file_and_offsets(self):
        assert span_identity(HASH, "a.tex", 0, 10) != span_identity(HASH, "b.tex", 0, 10)
        assert span_identity(HASH, "a.tex", 0, 10) != span_identity(HASH, "a.tex", 1, 10)

    def test_identity_is_not_derived_from_text(self):
        """Two identical texts at different offsets must not collide."""
        text = "same\n\nsame"
        spans, _ = partition(text)
        prose = [span for span in spans if span.span_kind == PROSE]
        assert len(prose) == 2
        assert prose[0].text == prose[1].text
        assert prose[0].span_id != prose[1].span_id

    def test_exact_text_hash_matches_the_bytes(self):
        spans, _ = partition("\\section{T}\nSome prose here.\n")
        for span in spans:
            assert span.exact_text_hash == hashlib.sha256(
                span.text.encode("utf-8")
            ).hexdigest()


class TestClassification:
    def test_comment_is_not_reader_facing(self):
        spans, _ = partition("% internal note\nProse.")
        comment = next(span for span in spans if span.span_kind == COMMENT)
        assert comment.reader_facing is False

    def test_escaped_percent_is_not_a_comment(self):
        spans, _ = partition("A 35\\% increase in output.")
        assert COMMENT not in kinds(spans)

    def test_comment_hides_an_environment(self):
        """A commented-out environment must not be read as real math."""
        spans, _ = partition("% \\begin{equation} x \\end{equation}\nProse.")
        assert MATH not in kinds(spans)
        assert COMMENT in kinds(spans)

    def test_display_math_is_protected_structural(self):
        spans, _ = partition("\\begin{equation}\nE=mc^2\n\\end{equation}")
        math = next(span for span in spans if span.span_kind == MATH)
        assert math.coverage_disposition == PROTECTED_STRUCTURAL
        assert "E=mc^2" in math.text

    def test_inline_math_is_captured_whole(self):
        spans, _ = partition("The value $x_{t+1} = f(x_t)$ evolves.")
        math = next(span for span in spans if span.span_kind == MATH)
        assert math.text == "$x_{t+1} = f(x_t)$"

    def test_float_is_kept_whole(self):
        text = "\\begin{table}\n\\begin{tabular}{cc}a&b\\end{tabular}\n\\end{table}"
        spans, _ = partition(text)
        floats = [span for span in spans if span.span_kind == FLOAT]
        assert len(floats) == 1
        assert floats[0].text == text

    def test_nested_same_name_environment_closes_correctly(self):
        inner = "\\begin{tabular}{c}x\\end{tabular}"
        text = f"\\begin{{tabular}}{{cc}}{inner}\\end{{tabular}}"
        spans, _ = partition(text)
        floats = [span for span in spans if span.span_kind == FLOAT]
        assert len(floats) == 1
        assert floats[0].text == text

    def test_heading_is_reader_facing(self):
        spans, _ = partition("\\section{Why continuity matters}\nProse.")
        heading = next(span for span in spans if span.span_kind == HEADING)
        assert heading.reader_facing is True
        assert "Why continuity matters" in heading.text

    def test_starred_and_optional_heading_forms(self):
        spans, _ = partition("\\section*[Short]{Long title}\nProse.")
        assert HEADING in kinds(spans)

    def test_bibliography_command_is_classified(self):
        spans, _ = partition("\\bibliography{humanvoice_survey}\n")
        assert BIBLIOGRAPHY in kinds(spans)

    def test_preamble_command_is_not_reader_facing(self):
        spans, _ = partition("\\usepackage[utf8]{inputenc}\n")
        command = next(span for span in spans if span.span_kind == COMMAND)
        assert command.reader_facing is False

    def test_inline_macro_stays_inside_prose(self):
        """\\emph and \\citep are part of a sentence, not separate spans."""
        spans, _ = partition("As \\citet{smith2020} shows, the \\emph{kink} matters.")
        prose = [span for span in spans if span.span_kind == PROSE]
        assert len(prose) == 1
        assert "\\citet{smith2020}" in prose[0].text
        assert "\\emph{kink}" in prose[0].text

    def test_whitespace_is_its_own_span(self):
        spans, _ = partition("first\n\nsecond")
        assert kinds(spans) == [PROSE, WHITESPACE, PROSE]

    def test_whitespace_disposition_is_final_and_structural(self):
        """Whitespace is preserved structure, not a reviewed removal decision.

        Marking it non_substantive_scaffolding would assert that a reviewer
        judged it reader-irrelevant and removable, which requires an
        accountable ScaffoldingDisposition record it does not have.
        """
        spans, _ = partition("a\n\nb")
        blank = next(span for span in spans if span.span_kind == WHITESPACE)
        assert blank.coverage_disposition == PROTECTED_STRUCTURAL

    def test_partitioner_never_claims_scaffolding(self):
        """Only an adjudicated disposition may mark a span as scaffolding."""
        spans, _ = partition(
            "\\section{T}\nProse.\n\n% comment\n"
            "\\begin{equation}x\\end{equation}\n\\usepackage{amsmath}\n"
        )
        assert all(
            span.coverage_disposition != NON_SUBSTANTIVE_SCAFFOLDING
            for span in spans
        )


class TestSemanticRestraint:
    """The partitioner classifies form, never meaning."""

    def test_prose_starts_unresolved(self):
        spans, _ = partition("The censored rule differs from a true discontinuity.")
        prose = next(span for span in spans if span.span_kind == PROSE)
        assert prose.coverage_disposition == UNRESOLVED

    def test_comment_starts_unresolved_not_removable(self):
        """A comment may hold real domain content, so it is not pre-judged."""
        spans, _ = partition("% NOTE: the wedge is 35bp, per Table 3\nProse.")
        comment = next(span for span in spans if span.span_kind == COMMENT)
        assert comment.coverage_disposition == UNRESOLVED

    def test_heading_starts_unresolved(self):
        spans, _ = partition("\\section{The kink}\nProse.")
        heading = next(span for span in spans if span.span_kind == HEADING)
        assert heading.coverage_disposition == UNRESOLVED


class TestAbstentions:
    def test_unclosed_environment_abstains_without_losing_bytes(self):
        text = "\\begin{equation}\nx = 1\n"
        spans, abstentions = partition(text)
        assert reassemble(spans, text) == text
        assert any("never closed" in a["reason"] for a in abstentions)

    def test_unclosed_inline_math_abstains(self):
        text = "The value $x is unterminated"
        spans, abstentions = partition(text)
        assert reassemble(spans, text) == text
        assert any("never closed" in a["reason"] for a in abstentions)


class TestRecordEmission:
    def test_records_validate_against_the_shared_registry(self):
        from humanvoice.schemas import get_registry

        spans, _ = partition(
            "\\section{T}\nProse with $x$ math.\n\n% comment\n"
            "\\begin{equation}y=1\\end{equation}\n"
        )
        records = span_records(
            spans,
            run_id="run-001",
            snapshot_id="snapshot-001",
            source_hash=HASH,
            created_at="2026-09-11T00:00:00Z",
        )
        registry = get_registry()
        for record in records:
            assert registry.validate(record, raise_on_error=False) == []

    def test_links_are_emitted_empty(self):
        spans, _ = partition("Prose.")
        record = span_records(
            spans,
            run_id="r",
            snapshot_id="s",
            source_hash=HASH,
            created_at="2026-09-11T00:00:00Z",
        )[0]
        assert record["concept_ids"] == []
        assert record["protected_object_ids"] == []
        assert record["scaffolding_disposition_ids"] == []


class TestCoverageSummary:
    def test_unresolved_reader_bytes_are_reported(self):
        spans, _ = partition("Real prose here.\n\n% a comment\n")
        summary = coverage_summary(spans)
        assert summary["unresolved_reader_facing_bytes"] > 0
        assert summary["total_bytes"] == sum(s.byte_length for s in spans)

    def test_math_only_document_has_no_unresolved_reader_bytes(self):
        spans, _ = partition("\\begin{equation}x\\end{equation}")
        summary = coverage_summary(spans)
        assert summary["unresolved_reader_facing_bytes"] == 0


class TestRealSources:
    """Run against real project LaTeX, not only crafted strings."""

    @pytest.mark.parametrize(
        "relative",
        [
            "docs/survey/proposal/03_product.tex",
            "docs/survey/proposal/06_design.tex",
            "docs/survey/humanvoice_survey.tex",
        ],
    )
    def test_real_chapter_partitions_completely(self, relative):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        text = (root / relative).read_text(encoding="utf-8")
        spans, _ = partition(text, relative)
        assert reassemble(spans, text) == text
        summary = coverage_summary(spans)
        assert summary["span_count"] > 10
        assert summary["reader_facing_bytes"] > 0

    def test_real_chapter_is_stable_across_runs(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        relative = "docs/survey/proposal/06_design.tex"
        text = (root / relative).read_text(encoding="utf-8")
        first, _ = partition(text, relative)
        second, _ = partition(text, relative)
        assert [s.span_id for s in first] == [s.span_id for s in second]
