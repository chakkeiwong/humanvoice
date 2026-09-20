"""
Tests for Phase 4: Assembly contiguity enforcement.

Verifies that assembly rejects units with non-contiguous spans.
"""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from humanvoice.commands.assemble_v2_command import _collect_patches


def test_collect_patches_rejects_non_contiguous_unit():
    """Assembly should reject units with gaps > 10KB between spans."""
    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create directory structure
        inventory_dir = tmpdir / ".humanvoice" / "inventory"
        inventory_dir.mkdir(parents=True)
        rewrites_dir = tmpdir / ".humanvoice" / "rewrites"
        rewrites_dir.mkdir(parents=True)
        source_dir = tmpdir / "source"
        source_dir.mkdir()

        # Create spans.jsonl with non-contiguous spans
        spans_path = inventory_dir / "spans.jsonl"
        with open(spans_path, 'w') as f:
            f.write(json.dumps({
                "record_id": "span-001",
                "byte_start": 1000,
                "byte_end": 1500,
                "source_file": "test.tex"
            }) + '\n')
            f.write(json.dumps({
                "record_id": "span-002",
                "byte_start": 15000,  # 13.5KB gap
                "byte_end": 15500,
                "source_file": "test.tex"
            }) + '\n')

        # Create source file
        source_path = source_dir / "test.tex"
        source_path.write_text("x" * 20000)

        # Create unit result with non-contiguous spans
        unit_path = rewrites_dir / "unit-001.json"
        unit_data = {
            "unit_id": "unit-001",
            "source_span_ids": ["span-001", "span-002"],
            "output_latex": "Rewritten text",
            "is_acceptable": True,
            "concept_correspondences": ["concept-001"]
        }
        with open(unit_path, 'w') as f:
            json.dump(unit_data, f)

        # Create session record
        session = {
            "units_completed": ["unit-001"]
        }

        # Should exit with code 4 due to non-contiguous spans
        with pytest.raises(SystemExit) as exc_info:
            _collect_patches(tmpdir, session, allow_incomplete=False)

        assert exc_info.value.code == 4


def test_collect_patches_accepts_contiguous_unit():
    """Assembly should accept units with gaps < 10KB."""
    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create directory structure
        inventory_dir = tmpdir / ".humanvoice" / "inventory"
        inventory_dir.mkdir(parents=True)
        rewrites_dir = tmpdir / ".humanvoice" / "rewrites"
        rewrites_dir.mkdir(parents=True)
        source_dir = tmpdir / "source"
        source_dir.mkdir()

        # Create spans.jsonl with contiguous spans
        spans_path = inventory_dir / "spans.jsonl"
        with open(spans_path, 'w') as f:
            f.write(json.dumps({
                "record_id": "span-001",
                "byte_start": 1000,
                "byte_end": 1500,
                "source_file": "test.tex"
            }) + '\n')
            f.write(json.dumps({
                "record_id": "span-002",
                "byte_start": 2000,  # 500 byte gap (OK)
                "byte_end": 2500,
                "source_file": "test.tex"
            }) + '\n')

        # Create source file
        source_path = source_dir / "test.tex"
        source_path.write_text("x" * 5000)

        # Create unit result with contiguous spans
        unit_path = rewrites_dir / "unit-001.json"
        unit_data = {
            "unit_id": "unit-001",
            "source_span_ids": ["span-001", "span-002"],
            "output_latex": "Rewritten text",
            "is_acceptable": True,
            "concept_correspondences": ["concept-001"]
        }
        with open(unit_path, 'w') as f:
            json.dump(unit_data, f)

        # Create session record
        session = {
            "units_completed": ["unit-001"]
        }

        # Should succeed
        patches, skipped = _collect_patches(tmpdir, session, allow_incomplete=False)

        assert len(patches) == 1
        assert patches[0].unit_id == "unit-001"
        assert patches[0].start_offset == 1000
        assert patches[0].end_offset == 2500


def test_collect_patches_single_span_unit():
    """Assembly should accept units with single span (trivially contiguous)."""
    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create directory structure
        inventory_dir = tmpdir / ".humanvoice" / "inventory"
        inventory_dir.mkdir(parents=True)
        rewrites_dir = tmpdir / ".humanvoice" / "rewrites"
        rewrites_dir.mkdir(parents=True)
        source_dir = tmpdir / "source"
        source_dir.mkdir()

        # Create spans.jsonl with single span
        spans_path = inventory_dir / "spans.jsonl"
        with open(spans_path, 'w') as f:
            f.write(json.dumps({
                "record_id": "span-001",
                "byte_start": 1000,
                "byte_end": 1500,
                "source_file": "test.tex"
            }) + '\n')

        # Create source file
        source_path = source_dir / "test.tex"
        source_path.write_text("x" * 5000)

        # Create unit result
        unit_path = rewrites_dir / "unit-001.json"
        unit_data = {
            "unit_id": "unit-001",
            "source_span_ids": ["span-001"],
            "output_latex": "Rewritten text",
            "is_acceptable": True,
            "concept_correspondences": ["concept-001"]
        }
        with open(unit_path, 'w') as f:
            json.dump(unit_data, f)

        # Create session record
        session = {
            "units_completed": ["unit-001"]
        }

        # Should succeed
        patches, skipped = _collect_patches(tmpdir, session, allow_incomplete=False)

        assert len(patches) == 1
        assert patches[0].unit_id == "unit-001"
