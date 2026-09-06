"""
Assembly gap release gate (scale fixes Issue 2, review correction R3).

Partial assembly is only safe if something downstream refuses to publish a gapped
document. Without this gate, Issue 2 would be a fail-open regression: assembly
would exit 0 on an incomplete document and release would pass it through, which
is the exact pattern this repo already shipped once in v1.1 (gates reporting
"pass" over known violations).

Assembly records the gaps. This gate is the fail-closed point.
"""

import json
import pytest
from pathlib import Path

from humanvoice.commands.release_command import check_assembly_gaps


@pytest.fixture
def assembled_dir(tmp_path):
    """Snapshot with an assembled revision directory."""
    snapshot = tmp_path / "snapshot"
    output_dir = snapshot / ".humanvoice" / "revisions" / "assembled"
    output_dir.mkdir(parents=True)
    return snapshot, output_dir


class TestAssemblyGapGate:
    def test_gaps_block_release(self, assembled_dir):
        """A document with recorded gaps must not release."""
        snapshot, output_dir = assembled_dir
        (output_dir / "assembly_gaps.json").write_text(json.dumps([
            {"section_index": 1, "title": "Section 1", "reason": "draft_not_found"},
            {"section_index": 3, "title": "Section 3", "reason": "draft_not_found"},
        ]))

        block = check_assembly_gaps(snapshot)

        assert block is not None, "gaps must block release"
        assert block["gate"] == "assembly_gaps"
        assert "2" in block["detail"], "must report how many gaps"

    def test_gap_titles_named_in_block(self, assembled_dir):
        """The operator must be told which sections to draft, not just a count."""
        snapshot, output_dir = assembled_dir
        (output_dir / "assembly_gaps.json").write_text(json.dumps([
            {"section_index": 3, "title": "Smoothing and surrogate approaches",
             "reason": "draft_not_found"},
        ]))

        block = check_assembly_gaps(snapshot)

        assert block is not None
        assert "Smoothing and surrogate approaches" in block["detail"]

    def test_empty_gap_list_passes(self, assembled_dir):
        """A complete assembly releases."""
        snapshot, output_dir = assembled_dir
        (output_dir / "assembly_gaps.json").write_text(json.dumps([]))

        assert check_assembly_gaps(snapshot) is None

    def test_missing_gap_file_blocks(self, assembled_dir):
        """
        Fail closed on absence. A missing gap record means assembly either never
        ran or ran under a version that did not record gaps; neither is evidence
        of completeness, and treating absence as "no gaps" is the fail-open shape
        this gate exists to prevent.
        """
        snapshot, _ = assembled_dir

        block = check_assembly_gaps(snapshot)

        assert block is not None, "absent evidence must not read as pass"
        assert "not found" in block["detail"].lower() or "missing" in block["detail"].lower()

    def test_unreadable_gap_file_blocks(self, assembled_dir):
        """Corrupt evidence is not passing evidence."""
        snapshot, output_dir = assembled_dir
        (output_dir / "assembly_gaps.json").write_text("{not valid json")

        block = check_assembly_gaps(snapshot)

        assert block is not None
        assert block["gate"] == "assembly_gaps"

    def test_gate_is_never_except(self, assembled_dir):
        """
        Gaps cannot be waived by an exception. A document missing sections is not
        a judgement call about acceptable risk -- it is incomplete.
        """
        snapshot, output_dir = assembled_dir
        (output_dir / "assembly_gaps.json").write_text(json.dumps([
            {"section_index": 0, "title": "Section 0", "reason": "draft_not_found"},
        ]))

        block = check_assembly_gaps(snapshot)

        assert block is not None
        assert block.get("never_except") is True
