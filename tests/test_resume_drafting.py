"""
Resume drafting (scale fixes Issue 3).

A 345-page document is 60-100 draft units. Without resume, every failure costs
the whole run: the operator must hand-type one `hv draft --section N` per gap,
and `hv pipeline` returns on the first failing section so nothing downstream of
it is attempted.

After this fix:
  --section N   single unit (unchanged)
  --missing     draft only units that have no draft on disk
  --all         draft every unit, continuing past failures
and the pipeline drafts every section it can before deciding whether to assemble.
"""

import json
from argparse import Namespace

import pytest

from humanvoice.commands.draft_command import _find_undrafted_sections


@pytest.fixture
def snapshot_with_partial_drafts(tmp_path):
    """5-section blueprint with drafts present for 0, 2, 4."""
    snapshot = tmp_path / "snapshot"
    runs_dir = snapshot / ".humanvoice" / "runs" / "run-test"
    runs_dir.mkdir(parents=True)

    sections = [{"title": f"Section {i}", "purpose": f"P{i}"} for i in range(5)]

    for i in (0, 2, 4):
        # Filename stem matches the draft writer's sanitisation.
        (runs_dir / f"draft_section_{i}.tex").write_text(f"\\section{{Section {i}}}\n\nText.")

    return snapshot, sections


class TestFindUndraftedSections:
    def test_identifies_gaps(self, snapshot_with_partial_drafts):
        """Only sections without a draft on disk are returned."""
        snapshot, sections = snapshot_with_partial_drafts
        assert _find_undrafted_sections(snapshot, sections) == [1, 3]

    def test_empty_when_complete(self, tmp_path):
        """A fully drafted blueprint yields no work."""
        snapshot = tmp_path / "snapshot"
        runs_dir = snapshot / ".humanvoice" / "runs" / "run-test"
        runs_dir.mkdir(parents=True)

        sections = [{"title": f"Section {i}", "purpose": f"P{i}"} for i in range(3)]
        for i in range(3):
            (runs_dir / f"draft_section_{i}.tex").write_text("\\section{S}\n\nText.")

        assert _find_undrafted_sections(snapshot, sections) == []

    def test_all_when_nothing_drafted(self, tmp_path):
        """No runs directory means every section is outstanding."""
        snapshot = tmp_path / "snapshot"
        snapshot.mkdir()
        sections = [{"title": f"Section {i}", "purpose": f"P{i}"} for i in range(4)]

        assert _find_undrafted_sections(snapshot, sections) == [0, 1, 2, 3]

    def test_agrees_with_assembly(self, snapshot_with_partial_drafts):
        """
        Resume and assembly must agree on what counts as drafted, or `--missing`
        will report success while assembly still records a gap for the same unit.
        """
        from humanvoice.commands.assemble_command import _find_section_draft

        snapshot, sections = snapshot_with_partial_drafts
        runs_dir = snapshot / ".humanvoice" / "runs"

        undrafted = _find_undrafted_sections(snapshot, sections)
        for i, section in enumerate(sections):
            found = _find_section_draft(runs_dir, i, section["title"]) is not None
            assert found == (i not in undrafted), f"section {i} disagrees"


class TestModeSelection:
    """CLI wiring: exactly one of --section/--missing/--all, and it is required."""

    def _parse(self, argv):
        from humanvoice.cli import build_parser
        return build_parser().parse_args(argv)

    def test_section_mode(self):
        args = self._parse(["draft", "snap", "--blueprint", "b.json",
                            "--brief", "br.json", "--section", "2"])
        assert args.section == 2
        assert not args.missing and not args.all

    def test_missing_mode(self):
        args = self._parse(["draft", "snap", "--blueprint", "b.json",
                            "--brief", "br.json", "--missing"])
        assert args.missing is True
        assert args.section is None

    def test_all_mode(self):
        args = self._parse(["draft", "snap", "--blueprint", "b.json",
                            "--brief", "br.json", "--all"])
        assert args.all is True
        assert args.section is None

    def test_modes_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            self._parse(["draft", "snap", "--blueprint", "b.json",
                         "--brief", "br.json", "--section", "1", "--all"])

    def test_a_mode_is_required(self):
        with pytest.raises(SystemExit):
            self._parse(["draft", "snap", "--blueprint", "b.json",
                         "--brief", "br.json"])
