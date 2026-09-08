"""
Test that source subsection structure is extracted and preserved in planning.

Issue: The planner was only extracting \\section{} commands, not \\subsection{}.
When source had rich subsection structure (e.g., 18 subsections in one section),
the planner would create coarse blueprints (e.g., 2 blueprint subsections covering
18 source subsections), causing massive content loss during drafting.

Fix: Extract both \\section{} and \\subsection{}, show them to the model, and
add a strong constraint that blueprint subsections should roughly match source
subsections when rich structure exists.
"""

import pytest
from humanvoice.commands.plan_command import _extract_section_structure


def test_extracts_subsections_within_sections():
    """Planner should extract both sections and subsections."""
    source = r"""
\section{Introduction}
Some text.

\subsection{Background}
More text.

\subsection{Motivation}
Even more text.

\section{Methods}
Methods text.

\subsection{Approach A}
A text.

\subsection{Approach B}
B text.
"""

    result = _extract_section_structure(source, "test.tex")

    assert len(result) == 2

    # First section has 2 subsections
    assert result[0]['title'] == 'Introduction'
    assert len(result[0]['subsections']) == 2
    assert result[0]['subsections'][0]['title'] == 'Background'
    assert result[0]['subsections'][1]['title'] == 'Motivation'

    # Second section has 2 subsections
    assert result[1]['title'] == 'Methods'
    assert len(result[1]['subsections']) == 2
    assert result[1]['subsections'][0]['title'] == 'Approach A'
    assert result[1]['subsections'][1]['title'] == 'Approach B'


def test_subsections_get_correct_line_ranges():
    """Subsection line ranges should not overlap and should tile their parent section."""
    source = r"""
\section{Methods}
Methods intro.

\subsection{Part A}
Part A content.

\subsection{Part B}
Part B content.

\subsection{Part C}
Part C content.
"""

    result = _extract_section_structure(source, "test.tex")

    section = result[0]
    subs = section['subsections']

    assert len(subs) == 3

    # Each subsection should start where declared
    assert 'Part A' in source.split('\n')[subs[0]['start_line'] - 1]
    assert 'Part B' in source.split('\n')[subs[1]['start_line'] - 1]
    assert 'Part C' in source.split('\n')[subs[2]['start_line'] - 1]

    # Subsections should not overlap
    assert subs[0]['end_line'] < subs[1]['start_line']
    assert subs[1]['end_line'] < subs[2]['start_line']

    # Last subsection should end where section ends
    assert subs[2]['end_line'] == section['end_line']


def test_sections_without_subsections():
    """Sections with no subsections should have empty subsections list."""
    source = r"""
\section{Introduction}
Just section content, no subsections.

\section{Methods}
More section content.
"""

    result = _extract_section_structure(source, "test.tex")

    assert len(result) == 2
    assert result[0]['subsections'] == []
    assert result[1]['subsections'] == []


def test_mixed_sections_some_with_subsections():
    """Some sections may have subsections while others don't."""
    source = r"""
\section{Introduction}
Plain section.

\section{Background}
Section with structure.

\subsection{Part 1}
Content.

\subsection{Part 2}
More content.

\section{Conclusion}
Another plain section.
"""

    result = _extract_section_structure(source, "test.tex")

    assert len(result) == 3
    assert len(result[0]['subsections']) == 0  # Introduction
    assert len(result[1]['subsections']) == 2  # Background
    assert len(result[2]['subsections']) == 0  # Conclusion
