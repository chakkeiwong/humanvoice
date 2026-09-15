#!/usr/bin/env python3
"""
Unit tests for blackline_generator.py (v2 blackline generation).

Tests the core blackline generation functions extracted from v1 assemble_command.py
and adapted for v2 pipeline use.
"""

import tempfile
from pathlib import Path
import pytest

from humanvoice.blackline_generator import (
    check_latexdiff_available,
    extract_preamble,
    extract_postamble,
    extract_document_body,
    extract_chapters,
    wrap_as_document,
    chapter_label,
    generate_blacklined_diff,
)


def test_check_latexdiff_available():
    """Check if latexdiff is available (informational test)."""
    available = check_latexdiff_available()
    # Just check that it returns a bool, don't fail if latexdiff isn't installed
    assert isinstance(available, bool)


def test_extract_preamble_basic():
    """Extract preamble from simple LaTeX document."""
    doc = r"""\documentclass{article}
\usepackage{amsmath}
\begin{document}
Hello world
\end{document}"""

    preamble = extract_preamble(doc)
    assert r"\documentclass{article}" in preamble
    assert r"\usepackage{amsmath}" in preamble
    assert r"\begin{document}" not in preamble


def test_extract_preamble_no_begin_document():
    """Extract preamble when \\begin{document} missing (fallback)."""
    doc = r"""\documentclass{article}
\usepackage{amsmath}
% No \begin{document}"""

    preamble = extract_preamble(doc)
    # Should return first 20 lines as fallback
    assert r"\documentclass{article}" in preamble


def test_extract_postamble_with_bibliography():
    """Extract postamble including bibliography commands."""
    doc = r"""\documentclass{article}
\begin{document}
Content here
\bibliographystyle{plain}
\bibliography{refs}
\end{document}
% Comment after"""

    postamble = extract_postamble(doc)
    assert r"\bibliographystyle{plain}" in postamble
    assert r"\bibliography{refs}" in postamble


def test_extract_postamble_no_bibliography():
    """Extract postamble with no bibliography commands."""
    doc = r"""\documentclass{article}
\begin{document}
Content here
\end{document}"""

    postamble = extract_postamble(doc)
    # Should be empty or just whitespace
    assert postamble.strip() == ""


def test_extract_document_body():
    """Extract content between \\begin{document} and \\end{document}."""
    doc = r"""\documentclass{article}
\begin{document}
Content here
\end{document}"""

    body = extract_document_body(doc)
    assert "Content here" in body
    assert r"\documentclass" not in body
    assert r"\begin{document}" not in body


def test_extract_chapters_single_section():
    """Split document at \\section boundaries."""
    body = r"""\section{Introduction}
Intro text here.

\section{Methods}
Methods text here."""

    chapters = extract_chapters(body)
    assert len(chapters) == 2
    assert r"\section{Introduction}" in chapters[0]
    assert "Intro text here" in chapters[0]
    assert r"\section{Methods}" in chapters[1]
    assert "Methods text here" in chapters[1]


def test_extract_chapters_with_frontmatter():
    """Split document preserving text before first heading."""
    body = r"""Front matter before sections.

\section{Introduction}
Intro text here."""

    chapters = extract_chapters(body)
    assert len(chapters) == 2
    assert "Front matter" in chapters[0]
    assert r"\section{Introduction}" in chapters[1]


def test_extract_chapters_no_headings():
    """Handle document with no section/chapter commands."""
    body = "Just plain text, no headings."

    chapters = extract_chapters(body)
    assert len(chapters) == 1
    assert chapters[0] == body


def test_extract_chapters_roundtrip():
    """Verify that concatenating chapters reproduces original."""
    body = r"""Preamble text.

\section{Alpha}
Alpha content.

\section{Beta}
Beta content."""

    chapters = extract_chapters(body)
    reconstructed = "".join(chapters)
    assert reconstructed == body


def test_wrap_as_document():
    """Wrap body content as complete LaTeX document."""
    preamble = r"\documentclass{article}"
    body = "Content"
    postamble = ""

    doc = wrap_as_document(body, preamble, postamble)
    assert r"\documentclass{article}" in doc
    assert r"\begin{document}" in doc
    assert "Content" in doc
    assert r"\end{document}" in doc


def test_chapter_label_with_title():
    """Extract chapter label from chunk with title."""
    chunk = r"\section{Introduction}"
    label = chapter_label(chunk, 0)
    assert "Introduction" in label
    assert "part 0" in label


def test_chapter_label_without_title():
    """Generate label for chunk without heading."""
    chunk = "Plain text"
    label = chapter_label(chunk, 3)
    assert label == "part 3"


@pytest.mark.skipif(not check_latexdiff_available(), reason="latexdiff not installed")
def test_generate_blacklined_diff_simple():
    """Generate blackline diff for simple document change."""
    original = r"""\documentclass{article}
\begin{document}
Original text here.
\end{document}"""

    revised = r"""\documentclass{article}
\begin{document}
Revised text here.
\end{document}"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        original_path = tmpdir / "original.tex"
        revised_path = tmpdir / "revised.tex"
        output_path = tmpdir / "blackline.tex"

        original_path.write_text(original)
        revised_path.write_text(revised)

        success, errors = generate_blacklined_diff(
            original_path,
            revised_path,
            output_path
        )

        assert success, f"Blackline generation failed: {errors}"
        assert errors == []
        assert output_path.exists()

        blackline = output_path.read_text()
        # Should contain DIF markup
        assert r"\DIF" in blackline or "DIF" in blackline
        # Should be valid LaTeX document
        assert r"\documentclass" in blackline
        assert r"\begin{document}" in blackline
        assert r"\end{document}" in blackline


@pytest.mark.skipif(not check_latexdiff_available(), reason="latexdiff not installed")
def test_generate_blacklined_diff_multi_chapter():
    """Generate blackline for document with multiple sections."""
    original = r"""\documentclass{article}
\begin{document}
\section{Alpha}
Original alpha.

\section{Beta}
Original beta.
\end{document}"""

    revised = r"""\documentclass{article}
\begin{document}
\section{Alpha}
Revised alpha.

\section{Beta}
Revised beta.
\end{document}"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        original_path = tmpdir / "original.tex"
        revised_path = tmpdir / "revised.tex"
        output_path = tmpdir / "blackline.tex"

        original_path.write_text(original)
        revised_path.write_text(revised)

        success, errors = generate_blacklined_diff(
            original_path,
            revised_path,
            output_path
        )

        assert success, f"Blackline generation failed: {errors}"
        assert output_path.exists()

        blackline = output_path.read_text()
        # Should have exactly one \documentclass (not duplicated per chapter)
        assert blackline.count(r"\documentclass") == 1
        # Should contain both sections
        assert "Alpha" in blackline
        assert "Beta" in blackline


def test_generate_blacklined_diff_latexdiff_unavailable():
    """Handle case where latexdiff is not installed."""
    if check_latexdiff_available():
        pytest.skip("latexdiff is installed, cannot test unavailable case")

    # This test is mainly for documentation
    # In real usage, caller should check check_latexdiff_available() first
    pass
