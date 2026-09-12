"""
Tests for hv inventory command.

Validates Phase 1 (deterministic partitioning) and Phase 2 (protected object linking).
"""

import json
import pytest
from pathlib import Path
from argparse import Namespace

from humanvoice.commands import inventory_command


@pytest.fixture
def minimal_snapshot(tmp_path):
    """Create minimal snapshot with manifest and source."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()

    # Manifest
    manifest = {
        "snapshot_id": "test-snapshot-001",
        "created_at": "2026-09-11T12:00:00Z",
        "source_hash": "a" * 64,
        "immutable": True
    }
    with open(snapshot_dir / "manifest.json", 'w') as f:
        json.dump(manifest, f)

    # Source directory with one file
    source_dir = snapshot_dir / "source"
    source_dir.mkdir()

    source_file = source_dir / "test.tex"
    source_file.write_text(
        "\\section{Introduction}\n"
        "This is a test document.\n"
        "\\begin{equation}\n"
        "E = mc^2\n"
        "\\end{equation}\n"
    )

    return snapshot_dir


def test_inventory_missing_snapshot(tmp_path):
    """Exit 3 when snapshot directory does not exist."""
    args = Namespace(snapshot=tmp_path / "nonexistent")
    result = inventory_command.run(args)
    assert result == 3


def test_inventory_missing_manifest(tmp_path):
    """Exit 3 when snapshot lacks manifest.json."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()

    args = Namespace(snapshot=snapshot_dir)
    result = inventory_command.run(args)
    assert result == 3


def test_inventory_missing_source(tmp_path):
    """Exit 3 when snapshot lacks source directory."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()

    manifest = {
        "snapshot_id": "test-001",
        "source_hash": "a" * 64,
        "immutable": True
    }
    with open(snapshot_dir / "manifest.json", 'w') as f:
        json.dump(manifest, f)

    args = Namespace(snapshot=snapshot_dir)
    result = inventory_command.run(args)
    assert result == 3


def test_inventory_phase_1_partitioning(minimal_snapshot, capsys):
    """Phase 1 partitions source and writes spans.jsonl."""
    args = Namespace(snapshot=minimal_snapshot)
    result = inventory_command.run(args)

    # Should succeed but concept extraction not implemented
    assert result == 0

    # Check spans.jsonl was written
    spans_path = minimal_snapshot / ".humanvoice" / "inventory" / "spans.jsonl"
    assert spans_path.exists()

    spans = []
    with open(spans_path) as f:
        for line in f:
            spans.append(json.loads(line))

    assert len(spans) > 0

    # Verify span structure
    for span in spans:
        assert "record_id" in span
        assert "snapshot_id" in span
        assert "source_file" in span
        assert "byte_start" in span
        assert "byte_end" in span
        assert "span_kind" in span
        assert "coverage_disposition" in span

    # Check stderr output
    captured = capsys.readouterr()
    assert "Partitioning source tree" in captured.err
    assert "spans covering" in captured.err
    assert "Phase 4: Model-based concept extraction" in captured.err


def test_inventory_stdout_json(minimal_snapshot, capsys):
    """Inventory writes JSON result to stdout."""
    args = Namespace(snapshot=minimal_snapshot)
    result = inventory_command.run(args)

    assert result == 0

    captured = capsys.readouterr()
    result_json = json.loads(captured.out)

    assert result_json["status"] == "partitioned"
    assert result_json["snapshot_id"] == "test-snapshot-001"
    assert result_json["total_files"] >= 1
    assert result_json["total_spans"] > 0
    assert result_json["total_bytes"] > 0
    assert result_json["concept_extraction"] in ("not_implemented", "no_concepts", "complete")


def test_inventory_determinism(minimal_snapshot):
    """Running inventory twice produces identical span IDs."""
    args = Namespace(snapshot=minimal_snapshot)

    # First run
    inventory_command.run(args)
    spans_path = minimal_snapshot / ".humanvoice" / "inventory" / "spans.jsonl"

    with open(spans_path) as f:
        first_spans = [json.loads(line) for line in f]

    # Delete and re-run
    spans_path.unlink()
    inventory_command.run(args)

    with open(spans_path) as f:
        second_spans = [json.loads(line) for line in f]

    assert len(first_spans) == len(second_spans)

    for s1, s2 in zip(first_spans, second_spans):
        assert s1["record_id"] == s2["record_id"]
        assert s1["byte_start"] == s2["byte_start"]
        assert s1["byte_end"] == s2["byte_end"]
