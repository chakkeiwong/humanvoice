"""
Test suite for hv init command.

Tests immutable snapshot creation, brief validation, and error handling.
"""

import json
import pytest
import tempfile
from pathlib import Path
from humanvoice.commands import init_command


class Args:
    """Mock args object for testing."""
    def __init__(self, source, brief, output):
        self.source = Path(source)
        self.brief = Path(brief)
        self.output = Path(output)


def test_init_with_valid_brief_and_source(tmp_path):
    """Test successful snapshot creation."""
    # Create test source
    source = tmp_path / "source.tex"
    source.write_text(r"\documentclass{article}\begin{document}Test\end{document}")

    # Create valid brief
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "reader_role": "executive",
        "decision_type": "approve proposal",
        "time_available_minutes": 30,
        "prior_knowledge": "domain expert",
        "success_criteria": "understand risks"
    }))

    # Create snapshot
    output = tmp_path / "snapshot"
    args = Args(source, brief, output)

    result = init_command.run(args)
    assert result == 0
    assert (output / "manifest.json").exists()
    assert (output / "source").exists()
    assert (output / "scratch").exists()


def test_init_rejects_incomplete_brief(tmp_path):
    """Test that incomplete brief is rejected."""
    source = tmp_path / "source.tex"
    source.write_text("test")

    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "reader_role": "executive"
        # Missing required fields
    }))

    output = tmp_path / "snapshot"
    args = Args(source, brief, output)

    result = init_command.run(args)
    assert result == 3  # Invalid input


def test_init_rejects_missing_source(tmp_path):
    """Test that missing source file is rejected."""
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "reader_role": "executive",
        "decision_type": "approve",
        "time_available_minutes": 30,
        "prior_knowledge": "expert",
        "success_criteria": "clear"
    }))

    source = tmp_path / "nonexistent.tex"
    output = tmp_path / "snapshot"
    args = Args(source, brief, output)

    result = init_command.run(args)
    assert result == 3


def test_init_computes_correct_hash(tmp_path):
    """Test that source hash matches expected value."""
    # Use the known synthetic fixture
    import shutil
    fixture_source = Path("fixtures/synthetic/register/001.tex")
    if not fixture_source.exists():
        pytest.skip("Fixture not available")

    source = tmp_path / "001.tex"
    shutil.copy(fixture_source, source)

    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "reader_role": "sponsor",
        "decision_type": "approve",
        "time_available_minutes": 45,
        "prior_knowledge": "technical",
        "success_criteria": "sound"
    }))

    output = tmp_path / "snapshot"
    args = Args(source, brief, output)

    result = init_command.run(args)
    assert result == 0

    manifest = json.loads((output / "manifest.json").read_text())
    # Expected hash from fixture manifest
    assert manifest["source_hash"] == "b84cb60f45ee82f0a1be01c9bcc698855dfc28a073b1685b7df18fcab01314fa"


def test_init_rejects_existing_output(tmp_path):
    """Test that existing output directory is rejected."""
    source = tmp_path / "source.tex"
    source.write_text("test")

    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "reader_role": "executive",
        "decision_type": "approve",
        "time_available_minutes": 30,
        "prior_knowledge": "expert",
        "success_criteria": "clear"
    }))

    output = tmp_path / "snapshot"
    output.mkdir()  # Pre-create output

    args = Args(source, brief, output)
    result = init_command.run(args)
    assert result == 3
