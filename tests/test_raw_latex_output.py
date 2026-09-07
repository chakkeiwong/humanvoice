"""
Raw LaTeX draft output (scale fixes Issue 6).

The model used to be asked for {"draft": {"latex": "\\section{...}"}}, which put
every backslash of a LaTeX document through JSON escaping, made one truncation
destroy a whole unit rather than its tail, and created a code-fence extraction
surface that cost an entire debugging session to misdiagnose.

The model is now asked for raw LaTeX, and the metadata that used to ride along in
the envelope is computed locally.

The first attempt at this shipped broken and every test still passed: it tried to
string-replace "Respond in JSON matching this schema:" out of the prompt, but the
prompt says "Return JSON matching this schema:". The replace matched nothing, the
model kept being asked for JSON, and schema validation had been switched off --
strictly worse than before the change.

Mock-based tests cannot catch that, because a mock returns whatever the test
author decided regardless of what the prompt said. So these tests assert on the
prompt text itself.
"""

import json

import pytest

from humanvoice.commands.draft_command import (
    ABSTAIN_MARKER,
    _build_draft_prompt,
    _extract_draft_metadata,
)


SECTION = {"title": "Exact methods", "purpose": "Survey", "word_budget": 800}
BRIEF = {"reader": "expert", "known_vocabulary": ["HMC"]}


class TestPromptAsksForRawLatex:
    """
    The contract lives in the prompt. If it still says "JSON", nothing downstream
    matters -- the model will send JSON and it will be written to a .tex file.
    """

    def _prompt(self):
        return _build_draft_prompt(SECTION, BRIEF, "evidence text", [])

    def test_prompt_does_not_ask_for_json(self):
        prompt = self._prompt()
        assert "Return JSON" not in prompt
        assert "Respond in JSON" not in prompt

    def test_prompt_does_not_show_a_draft_envelope(self):
        """The schema example itself taught the model to wrap output."""
        prompt = self._prompt()
        assert '"draft"' not in prompt
        assert '"latex"' not in prompt

    def test_prompt_asks_for_raw_latex_explicitly(self):
        prompt = self._prompt()
        assert "raw LaTeX only" in prompt
        assert "No JSON" in prompt

    def test_prompt_forbids_code_fences(self):
        """
        A fenced response reintroduces the extraction surface this removes.
        """
        prompt = self._prompt()
        assert "no code fences" in prompt.lower()

    def test_prompt_defines_the_abstention_marker(self):
        """
        Raw output has no field to carry an abstention, so the marker has to be
        specified in the prompt or the model will invent its own phrasing.
        """
        prompt = self._prompt()
        assert ABSTAIN_MARKER in prompt


class TestLocalMetadata:
    """
    Metadata is derived from the text, not requested in a second call.
    """

    def test_counts_words(self):
        latex = "\\section{Title}\n\nOne two three four five.\n"
        # \w+ counts command names too; the point is consistency with assembly,
        # which counts the same way.
        assert _extract_draft_metadata(latex)["word_count"] == len(
            __import__("re").findall(r"\w+", latex)
        )

    def test_extracts_cite_keys(self):
        latex = "Text \\cite{smith2020} more \\cite{jones2021}."
        assert _extract_draft_metadata(latex)["citations_needed"] == [
            "smith2020",
            "jones2021",
        ]

    def test_extracts_multi_key_and_variant_commands(self):
        latex = "\\citep{a,b} and \\citet[see][p.~2]{c}"
        assert _extract_draft_metadata(latex)["citations_needed"] == ["a", "b", "c"]

    def test_deduplicates_repeated_keys(self):
        latex = "\\cite{same} ... \\cite{same}"
        assert _extract_draft_metadata(latex)["citations_needed"] == ["same"]

    def test_no_citations_is_empty_not_missing(self):
        assert _extract_draft_metadata("\\section{T}\n\nProse.")["citations_needed"] == []

    def test_word_count_matches_assembly(self):
        """
        Draft and assembly must count words the same way, or a unit's recorded
        length and its assembled length will disagree for no real reason.
        """
        import re as _re

        latex = "\\subsection{A}\n\n\\cite{k} Some prose with 12{,}000 in it.\n"
        assembly_count = len(_re.findall(r"\w+", latex))
        assert _extract_draft_metadata(latex)["word_count"] == assembly_count


class TestAbstentionMarker:
    """
    The marker must be recognisable and must not collide with real LaTeX.
    """

    def test_marker_is_not_valid_latex_opening(self):
        assert not ABSTAIN_MARKER.startswith("\\")

    def test_marker_is_distinguishable_from_prose(self):
        """
        A section never opens with a bare capitalised word and a colon, so the
        marker cannot be produced accidentally by a well-formed draft.
        """
        assert ABSTAIN_MARKER.isupper() or ABSTAIN_MARKER.rstrip(":").isupper()
