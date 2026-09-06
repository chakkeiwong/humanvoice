"""
Bounded blackline generation (scale fixes Issue 8).

The blackline is the deliverable -- a static comparison document showing net
differences between the snapshot source and the assembled draft. Before this
fix, assembly ran one `latexdiff` over the whole document with a 60s timeout,
and on failure printed a warning and exited 0 with `blacklined_file: null`.

On a 345-page document 60s is optimistic, and a silent null is the same
fail-open shape v1.1 already shipped: the run reports success while the thing
the reader was promised does not exist.

After this fix:
  - the diff runs per chapter with a per-chapter timeout, so cost scales with
    chapter count rather than document length
  - a diff that fails when the tool is present is an abstention, not a warning
  - a tool that is absent, or an operator who passed --skip-blackline, is
    recorded as an explicit status that the release gate reads
"""

import json
import subprocess
from argparse import Namespace
from unittest.mock import patch

import pytest

from humanvoice.commands.assemble_command import (
    _extract_chapters,
    _draft_filename_stem,
    run as assemble_run,
)
from humanvoice.commands.release_command import check_blackline_present


# ---------------------------------------------------------------------------
# Chapter splitting
# ---------------------------------------------------------------------------

class TestExtractChapters:
    def test_splits_at_section_boundaries(self):
        doc = (
            "\\section{One}\n\nFirst body.\n\n"
            "\\section{Two}\n\nSecond body.\n"
        )
        chapters = _extract_chapters(doc)

        assert len(chapters) == 2
        assert chapters[0].startswith("\\section{One}")
        assert "First body." in chapters[0]
        assert "Second body." not in chapters[0]

    def test_splits_at_chapter_boundaries(self):
        doc = "\\chapter{A}\n\nBody A.\n\n\\chapter{B}\n\nBody B.\n"
        chapters = _extract_chapters(doc)

        assert len(chapters) == 2
        assert chapters[1].startswith("\\chapter{B}")

    def test_preamble_before_first_heading_is_kept(self):
        """
        Text before the first heading is part of the document and must appear in
        the diff. Dropping it would silently exclude it from the comparison.
        """
        doc = "Front matter paragraph.\n\n\\section{One}\n\nBody.\n"
        chapters = _extract_chapters(doc)

        assert any("Front matter paragraph." in c for c in chapters)

    def test_document_with_no_headings_is_one_unit(self):
        doc = "Just prose, no headings at all.\n"
        chapters = _extract_chapters(doc)

        assert len(chapters) == 1
        assert "Just prose" in chapters[0]

    def test_round_trips_without_losing_content(self):
        """
        Concatenating the parts must reproduce the input. A splitter that drops
        or duplicates text would corrupt the blackline in ways that read as
        authored changes.
        """
        doc = (
            "Preamble line.\n\n\\section{One}\n\nBody one.\n\n"
            "\\subsection{One A}\n\nNested body.\n\n\\section{Two}\n\nBody two.\n"
        )
        assert "".join(_extract_chapters(doc)) == doc


# ---------------------------------------------------------------------------
# Fixtures for the assembly-level tests
# ---------------------------------------------------------------------------

@pytest.fixture
def complete_snapshot(tmp_path):
    """A fully drafted 2-section snapshot, ready to assemble."""
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()

    (snapshot / "manifest.json").write_text(json.dumps({
        "snapshot_id": "snapshot-blackline-test",
        "source_files": ["source/source.tex"],
        "protected_objects_count": 0,
    }))

    source_dir = snapshot / "source"
    source_dir.mkdir()
    (source_dir / "source.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\section{Alpha}\n\nOriginal alpha.\n\n"
        "\\section{Beta}\n\nOriginal beta.\n"
        "\\end{document}\n"
    )

    run_dir = snapshot / ".humanvoice" / "runs" / "run-test"
    run_dir.mkdir(parents=True)

    sections = [
        {"title": "Alpha", "purpose": "First"},
        {"title": "Beta", "purpose": "Second"},
    ]
    (run_dir / "blueprint.json").write_text(json.dumps({
        "blueprint_id": "blueprint-blackline-test",
        "blueprint": {"sections": sections, "total_words": 100},
    }))

    for title in ("Alpha", "Beta"):
        stem = _draft_filename_stem(title)
        (run_dir / f"draft_{stem}.tex").write_text(
            f"\\section{{{title}}}\n\nRevised {title.lower()} prose.\n"
        )

    brief_path = snapshot / "brief.json"
    brief_path.write_text(json.dumps({"document_type": "technical_survey"}))

    return snapshot, brief_path


def _args(snapshot, brief_path, skip_blackline=False):
    return Namespace(
        snapshot=str(snapshot),
        brief=str(brief_path),
        output=None,
        skip_blackline=skip_blackline,
    )


def _assembly_manifest(snapshot):
    path = (
        snapshot / ".humanvoice" / "revisions" / "assembled" / "assembly_manifest.json"
    )
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Assembly behaviour
# ---------------------------------------------------------------------------

class TestBoundedDiff:
    def test_successful_diff_records_blackline(self, complete_snapshot):
        """The happy path still produces a blackline and exits 0."""
        snapshot, brief_path = complete_snapshot

        exit_code = assemble_run(_args(snapshot, brief_path))

        assert exit_code == 0
        manifest = _assembly_manifest(snapshot)
        assert manifest["blacklined_file"] is not None
        assert manifest["blackline_status"] == "generated"

        blackline = (
            snapshot / ".humanvoice" / "revisions" / "assembled"
            / "blacklined_comparison.tex"
        )
        assert blackline.exists()
        assert blackline.stat().st_size > 0

    def test_timeout_on_one_chapter_abstains(self, complete_snapshot):
        """
        A diff failure with the tool present is an abstention, not a warning.

        This is the fail-open case Issue 8 exists to close: previously assembly
        exited 0 and the deliverable was simply absent.
        """
        snapshot, brief_path = complete_snapshot

        real_run = subprocess.run
        calls = {"n": 0}

        def flaky_run(cmd, *a, **kw):
            # Let the availability probe through; fail the second real diff.
            if cmd[:2] == ["latexdiff", "--version"]:
                return real_run(cmd, *a, **kw)
            calls["n"] += 1
            if calls["n"] == 2:
                raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 120))
            return real_run(cmd, *a, **kw)

        with patch("humanvoice.commands.assemble_command.subprocess.run", flaky_run):
            exit_code = assemble_run(_args(snapshot, brief_path))

        assert exit_code == 2, "diff failure must abstain"

    def test_per_chapter_timeout_is_used(self, complete_snapshot):
        """
        Timeout is per chapter, so total budget scales with chapter count rather
        than being one fixed 60s window for an arbitrarily long document.
        """
        snapshot, brief_path = complete_snapshot
        seen = []

        real_run = subprocess.run

        def recording_run(cmd, *a, **kw):
            if cmd and cmd[0] == "latexdiff" and "--version" not in cmd:
                seen.append(kw.get("timeout"))
            return real_run(cmd, *a, **kw)

        with patch("humanvoice.commands.assemble_command.subprocess.run", recording_run):
            assemble_run(_args(snapshot, brief_path))

        assert seen, "no diff invocation observed"
        assert all(t == 120 for t in seen), f"expected per-chapter 120s, saw {seen}"
        assert len(seen) >= 2, "diff should run per chapter, not once for the document"

    def test_output_is_one_well_formed_document(self, complete_snapshot):
        """
        The concatenated blackline must be a single compilable document.

        Two defects were found by hand here and neither was caught by the tests
        above, so both are pinned:

        1. Splitting the whole file (rather than its body) made chunk 0 contain
           `\\documentclass` and `\\begin{document}`, which then got wrapped in a
           preamble again -- the output carried two of each and would not compile.
        2. latexdiff injects `\\providecommand{\\DIFadd}` and friends into its
           output preamble. Reassembling bodies under the *source* preamble
           dropped those definitions, leaving markup that references undefined
           commands.
        """
        snapshot, brief_path = complete_snapshot
        assemble_run(_args(snapshot, brief_path))

        blackline = (
            snapshot / ".humanvoice" / "revisions" / "assembled"
            / "blacklined_comparison.tex"
        ).read_text()

        assert blackline.count("\\documentclass") == 1, "duplicated documentclass"
        assert blackline.count("\\begin{document}") == 1, "duplicated begin{document}"
        assert blackline.count("\\end{document}") == 1, "duplicated end{document}"

        # DIF markup must be defined, not merely used.
        assert "\\providecommand{\\DIFadd}" in blackline, "DIF definitions dropped"

        # Preamble must precede the body.
        assert blackline.index("\\documentclass") < blackline.index("\\begin{document}")

    def test_all_chapters_appear_in_the_diff(self, complete_snapshot):
        """
        Every chapter's revision must survive reassembly. Keeping only the first
        diff's body -- an easy mistake when the first output is treated specially
        for its preamble -- would silently drop every later chapter.
        """
        snapshot, brief_path = complete_snapshot
        assemble_run(_args(snapshot, brief_path))

        blackline = (
            snapshot / ".humanvoice" / "revisions" / "assembled"
            / "blacklined_comparison.tex"
        ).read_text()

        assert "Alpha" in blackline
        assert "Beta" in blackline, "later chapter lost during reassembly"
        # latexdiff splits words with markup, so assert on the tokens it emits
        # rather than on the original phrases.
        assert "\\DIFadd{Revised" in blackline or "Revised" in blackline
        assert "\\DIFdel{Original" in blackline or "Original" in blackline

    def test_skip_blackline_records_explicit_status(self, complete_snapshot):
        """
        --skip-blackline is allowed for draft review, but it is recorded as an
        operator decision rather than leaving an indistinguishable null.
        """
        snapshot, brief_path = complete_snapshot

        exit_code = assemble_run(_args(snapshot, brief_path, skip_blackline=True))

        assert exit_code == 0
        manifest = _assembly_manifest(snapshot)
        assert manifest["blacklined_file"] is None
        assert manifest["blackline_status"] == "skipped_by_operator"

    def test_absent_tool_records_status_and_still_assembles(self, complete_snapshot):
        """
        A missing latexdiff must not block local assembly -- but it must be
        recorded, so release can refuse rather than infer completeness.
        """
        snapshot, brief_path = complete_snapshot

        with patch(
            "humanvoice.commands.assemble_command._check_latexdiff_available",
            return_value=False,
        ):
            exit_code = assemble_run(_args(snapshot, brief_path))

        assert exit_code == 0
        manifest = _assembly_manifest(snapshot)
        assert manifest["blacklined_file"] is None
        assert manifest["blackline_status"] == "tool_unavailable"


# ---------------------------------------------------------------------------
# Release gate
# ---------------------------------------------------------------------------

class TestBlacklineGate:
    def _write_manifest(self, tmp_path, payload, create_blackline=False):
        assembled = tmp_path / "snapshot" / ".humanvoice" / "revisions" / "assembled"
        assembled.mkdir(parents=True)
        (assembled / "assembly_manifest.json").write_text(json.dumps(payload))
        if create_blackline:
            (assembled / "blacklined_comparison.tex").write_text("\\section{Diff}\n")
        return tmp_path / "snapshot"

    def test_generated_blackline_passes(self, tmp_path):
        snapshot = self._write_manifest(tmp_path, {
            "blacklined_file": ".humanvoice/revisions/assembled/blacklined_comparison.tex",
            "blackline_status": "generated",
        }, create_blackline=True)
        assert check_blackline_present(snapshot) is None

    def test_named_but_absent_blackline_blocks(self, tmp_path):
        """
        The manifest is a record, not proof. A named file that is not on disk --
        moved, or never written despite the record -- must not pass.
        """
        snapshot = self._write_manifest(tmp_path, {
            "blacklined_file": ".humanvoice/revisions/assembled/blacklined_comparison.tex",
            "blackline_status": "generated",
        })  # deliberately not created

        block = check_blackline_present(snapshot)
        assert block is not None
        assert "does not exist" in block["detail"]

    def test_missing_blackline_blocks(self, tmp_path):
        snapshot = self._write_manifest(tmp_path, {
            "blacklined_file": None,
            "blackline_status": "tool_unavailable",
        })
        block = check_blackline_present(snapshot)

        assert block is not None
        assert block["gate"] == "blackline_present"
        assert "latexdiff" in block["detail"].lower()

    def test_operator_skip_blocks_release(self, tmp_path):
        """
        Skipping is fine for review and not fine for release. The status is
        recorded so the refusal can name the reason precisely.
        """
        snapshot = self._write_manifest(tmp_path, {
            "blacklined_file": None,
            "blackline_status": "skipped_by_operator",
        })
        block = check_blackline_present(snapshot)

        assert block is not None
        assert "skip" in block["detail"].lower()

    def test_absent_manifest_blocks(self, tmp_path):
        """Fail closed: no assembly record is not evidence of a blackline."""
        snapshot = tmp_path / "snapshot"
        snapshot.mkdir()

        block = check_blackline_present(snapshot)
        assert block is not None
