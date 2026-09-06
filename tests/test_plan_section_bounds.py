"""
Tests for section line-bound extraction in plan_command.

Section bounds are what let draft_command route each source protected object
(equation, label, citation) to the blueprint section that should carry it. If
bounds are absent or leave gaps, objects fall through unrouted, no
correspondence manifest records them, and the release-time protected
correspondence gate counts them as missing. These tests pin the coverage
contract: the bounds emitted for a source file must tile the whole file with no
gaps and no overlaps.
"""

from humanvoice.commands.plan_command import _extract_section_structure


def _covered_lines(sections: list) -> set:
    """Union of every line number claimed by some section."""
    covered = set()
    for sec in sections:
        covered.update(range(sec["start_line"], sec["end_line"] + 1))
    return covered


def test_front_matter_before_first_section_is_covered():
    """
    Content above the first \\section{} must belong to the first section.

    An abstract typically holds citations and sometimes an equation. If the
    first section started at its own \\section{} line, those objects would be
    routed nowhere and would read as missing at release, dragging any document
    with front matter below the correspondence threshold.
    """
    source = "\n".join([
        r"\documentclass{article}",       # 1
        r"\begin{document}",              # 2
        r"\begin{abstract}",              # 3
        r"We extend \cite{smith2020}.",   # 4  <- citation in front matter
        r"\label{sec:abs}",               # 5  <- label in front matter
        r"\end{abstract}",                # 6
        r"",                              # 7
        r"\section{Introduction}",        # 8
        r"Body text.",                    # 9
    ])

    sections = _extract_section_structure(source, "source/001.tex")

    assert len(sections) == 1
    assert sections[0]["start_line"] == 1, (
        "first section must reach back to line 1 so front-matter protected "
        "objects are routed"
    )
    assert 4 in _covered_lines(sections)
    assert 5 in _covered_lines(sections)


def test_sections_tile_the_file_without_gaps_or_overlaps():
    """Every line belongs to exactly one section."""
    source = "\n".join([
        r"\documentclass{article}",   # 1
        r"\begin{document}",          # 2
        r"\section{One}",             # 3
        r"first body",                # 4
        r"\section{Two}",             # 5
        r"second body",               # 6
        r"\section{Three}",           # 7
        r"third body",                # 8
        r"\end{document}",            # 9
    ])
    total_lines = len(source.split("\n"))

    sections = _extract_section_structure(source, "source/001.tex")

    assert [s["title"] for s in sections] == ["One", "Two", "Three"]
    assert _covered_lines(sections) == set(range(1, total_lines + 1)), "gap in coverage"

    # No line claimed twice: summed span equals the file length.
    spans = sum(s["end_line"] - s["start_line"] + 1 for s in sections)
    assert spans == total_lines, "sections overlap"

    # Bounds are contiguous and ascending.
    for earlier, later in zip(sections, sections[1:]):
        assert later["start_line"] == earlier["end_line"] + 1


def test_file_without_sections_becomes_one_implicit_section():
    """A source file with no \\section{} still gets full-file bounds."""
    source = "\n".join([
        r"\documentclass{article}",         # 1
        r"\begin{document}",                # 2
        r"Just prose with \cite{jones}.",   # 3
        r"\end{document}",                  # 4
    ])

    sections = _extract_section_structure(source, "source/001.tex")

    assert len(sections) == 1
    assert sections[0]["start_line"] == 1
    assert sections[0]["end_line"] == len(source.split("\n"))
    assert 3 in _covered_lines(sections)


def test_every_section_carries_its_source_file():
    """
    Bounds are meaningless without the file they index into.

    draft_command matches a section's source_file against each object's path;
    dropping the field would let line 50 of one file capture line 50 of another.
    """
    source = "\n".join([r"\section{A}", r"body", r"\section{B}", r"body"])

    sections = _extract_section_structure(source, "source/chapter2.tex")

    assert all(s["source_file"] == "source/chapter2.tex" for s in sections)
