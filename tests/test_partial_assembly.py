"""
Partial assembly (scale fixes Issue 2).

Assembly currently hard-abstains (exit 2) when any section draft is missing,
making the pipeline all-or-nothing. At 100 units and 95% per-unit reliability,
that produces a clean run once every 592 attempts.

After this fix, assembly becomes partial-tolerant: missing sections are recorded
as gaps, the assembled document includes LaTeX comments at the gap positions, and
the release gate becomes the fail-closed point rather than assembly itself.
"""

import json
import pytest
from pathlib import Path

from argparse import Namespace

from humanvoice.commands.assemble_command import run as assemble_run, _draft_filename_stem


def _args(snapshot, brief_path):
    """Assembly's arg surface: snapshot dir, brief, optional output override."""
    return Namespace(snapshot=str(snapshot), brief=str(brief_path), output=None)


@pytest.fixture
def partial_snapshot(tmp_path):
    """
    A snapshot with a 5-section blueprint where only sections 0, 2, 4 are drafted.
    """
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()

    # Minimal manifest
    manifest = {
        "snapshot_id": "snapshot-partial-test",
        "source_files": ["source/source.tex"],
        "protected_objects_count": 0,
    }
    (snapshot / "manifest.json").write_text(json.dumps(manifest))

    # Source file (minimal LaTeX)
    source_dir = snapshot / "source"
    source_dir.mkdir()
    (source_dir / "source.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nSource.\n\\end{document}"
    )

    # Blueprint with 5 sections - stored in the brief
    runs_dir = snapshot / ".humanvoice" / "runs"
    runs_dir.mkdir(parents=True)
    run_dir = runs_dir / "run-test"
    run_dir.mkdir()

    sections = [
        {"title": f"Section {i}", "purpose": f"Purpose {i}"} for i in range(5)
    ]
    # Assembly discovers the blueprint from the run directories, not from an arg.
    (run_dir / "blueprint.json").write_text(json.dumps({
        "blueprint_id": "blueprint-partial-test",
        "blueprint": {"sections": sections, "total_words": 5000},
    }))

    brief_path = snapshot / "brief.json"
    brief_path.write_text(json.dumps({
        "document_type": "technical_survey",
        "target_word_count": 5000,
        "target_sections": 5,
    }))

    # Draft only sections 0, 2, 4. Drafts are raw .tex, named by the same
    # sanitisation the draft stage applies to the section title.
    for i in [0, 2, 4]:
        stem = _draft_filename_stem(f"Section {i}")
        (run_dir / f"draft_{stem}.tex").write_text(
            f"\\section{{Section {i}}}\n\nDrafted content for section {i}."
        )

    return snapshot, brief_path


class TestPartialAssembly:
    def test_assembly_succeeds_with_gaps(self, partial_snapshot):
        """Assembly exits 0 when sections are missing, not exit 2."""
        snapshot, brief_path = partial_snapshot
        exit_code = assemble_run(_args(snapshot, brief_path))
        assert exit_code == 0, "partial assembly must exit 0, not abort"

    def test_gap_manifest_written(self, partial_snapshot):
        """Gaps are recorded in assembly_gaps.json."""
        snapshot, brief_path = partial_snapshot
        assemble_run(_args(snapshot, brief_path))

        output_dir = snapshot / ".humanvoice" / "revisions" / "assembled"
        gap_file = output_dir / "assembly_gaps.json"

        assert gap_file.exists(), "assembly_gaps.json must be written"

        gaps = json.loads(gap_file.read_text())
        assert len(gaps) == 2, "should record 2 gaps (sections 1, 3)"
        assert gaps[0]["section_index"] == 1
        assert gaps[0]["title"] == "Section 1"
        assert gaps[1]["section_index"] == 3

    def test_assembled_document_has_gap_comments(self, partial_snapshot):
        """Assembled .tex includes % MISSING: comments at gap positions."""
        snapshot, brief_path = partial_snapshot
        assemble_run(_args(snapshot, brief_path))

        output_dir = snapshot / ".humanvoice" / "revisions" / "assembled"
        assembled = (output_dir / "assembled_document.tex").read_text()

        assert "% MISSING: Section 1" in assembled
        assert "% MISSING: Section 3" in assembled
        assert "Section 0" in assembled, "section 0 should be present"
        assert "Section 2" in assembled
        assert "Section 4" in assembled

    def test_correspondence_records_only_present_sections(self, partial_snapshot):
        """Assembly manifest lists all sections, with included=False for gaps."""
        snapshot, brief_path = partial_snapshot
        assemble_run(_args(snapshot, brief_path))

        output_dir = snapshot / ".humanvoice" / "revisions" / "assembled"
        assembly_manifest = json.loads((output_dir / "assembly_manifest.json").read_text())

        assert len(assembly_manifest["sections"]) == 5, "all sections appear"
        included = [s["included"] for s in assembly_manifest["sections"]]
        assert included == [True, False, True, False, True], "gaps marked included=False"

        assert assembly_manifest["total_sections"] == 3, "counts exclude gaps"
        assert assembly_manifest["gap_count"] == 2

    def test_warning_emitted_on_gaps(self, partial_snapshot, capsys):
        """Assembly prints a warning when gaps are present."""
        snapshot, brief_path = partial_snapshot
        assemble_run(_args(snapshot, brief_path))

        captured = capsys.readouterr()
        assert "gap" in captured.err.lower()
        assert "2" in captured.err  # 2 gaps

    def test_complete_assembly_unaffected(self, tmp_path):
        """A complete assembly (no gaps) behaves exactly as before."""
        snapshot = tmp_path / "snapshot"
        snapshot.mkdir()

        manifest = {
            "snapshot_id": "snapshot-complete",
            "source_files": ["source/source.tex"],
            "protected_objects_count": 0,
        }
        (snapshot / "manifest.json").write_text(json.dumps(manifest))

        source_dir = snapshot / "source"
        source_dir.mkdir()
        (source_dir / "source.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nSource.\n\\end{document}"
        )

        runs_dir = snapshot / ".humanvoice" / "runs"
        runs_dir.mkdir(parents=True)
        run_dir = runs_dir / "run-test"
        run_dir.mkdir()

        sections = [{"title": f"Section {i}", "purpose": f"Purpose {i}"} for i in range(3)]
        (run_dir / "blueprint.json").write_text(json.dumps({
            "blueprint_id": "blueprint-complete",
            "blueprint": {"sections": sections, "total_words": 3000},
        }))

        brief_path = snapshot / "brief.json"
        brief_path.write_text(json.dumps({
            "document_type": "technical_survey",
            "target_word_count": 3000,
        }))

        for i in range(3):
            stem = _draft_filename_stem(f"Section {i}")
            (run_dir / f"draft_{stem}.tex").write_text(
                f"\\section{{Section {i}}}\n\nContent."
            )

        exit_code = assemble_run(_args(snapshot, brief_path))

        assert exit_code == 0

        output_dir = snapshot / ".humanvoice" / "revisions" / "assembled"
        gap_file = output_dir / "assembly_gaps.json"

        # Gap file should either be absent or contain empty list
        if gap_file.exists():
            gaps = json.loads(gap_file.read_text())
            assert len(gaps) == 0
