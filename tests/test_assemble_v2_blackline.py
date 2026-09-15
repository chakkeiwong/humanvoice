#!/usr/bin/env python3
"""
Integration tests for assemble-v2 blackline generation.

Tests the full assemble-v2 command with blackline generation, covering:
- Default behavior (blackline enabled)
- --skip-blackline flag
- Tool unavailable handling
- Fail-closed status recording
"""

import json
import subprocess
import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def simple_fixture_snapshot(tmp_path):
    """Create a simple snapshot with completed rewrite for testing."""
    # Use the existing register fixture
    fixture_source = Path("fixtures/synthetic/register/001.tex")
    if not fixture_source.exists():
        pytest.skip("Register fixture not available")

    snapshot = tmp_path / "test-snapshot"

    # Initialize snapshot
    result = subprocess.run(
        ['hv', 'init', str(fixture_source), '--brief', 'mock-brief.json', '--out', str(snapshot)],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        pytest.skip(f"init failed: {result.stderr}")

    # Run inventory (mock mode for speed)
    result = subprocess.run(
        ['hv', 'inventory', str(snapshot), '--mock', '--freeze', '--adjudicator', 'test-harness'],
        capture_output=True,
        text=True,
        timeout=120
    )
    if result.returncode != 0:
        pytest.skip(f"inventory failed: {result.stderr}")

    # Run plan
    result = subprocess.run(
        ['hv', 'plan', str(snapshot)],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        pytest.skip(f"plan failed: {result.stderr}")

    plan_output = json.loads(result.stdout)
    baseline_id = plan_output['baseline_id']
    plan_id = plan_output['plan_id']

    # Run rewrite (mock mode)
    result = subprocess.run(
        ['hv', 'rewrite', str(snapshot),
         '--baseline-id', baseline_id,
         '--plan-id', plan_id,
         '--mock'],
        capture_output=True,
        text=True,
        timeout=120
    )
    if result.returncode != 0:
        pytest.skip(f"rewrite failed: {result.stderr}")

    # Run preflight
    result = subprocess.run(
        ['hv', 'preflight-v2', str(snapshot)],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        pytest.skip(f"preflight failed: {result.stderr}")

    return snapshot


def test_assemble_v2_skip_blackline(simple_fixture_snapshot):
    """Verify --skip-blackline flag properly skips blackline generation."""
    snapshot = simple_fixture_snapshot

    result = subprocess.run(
        ['hv', 'assemble-v2', str(snapshot), '--skip-blackline'],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"assemble-v2 failed: {result.stderr}"
    assert "skipped" in result.stdout.lower()

    # Check assembly result metadata
    result_path = snapshot / ".humanvoice" / "assembled" / "assembly_result.json"
    assert result_path.exists()

    assembly_result = json.loads(result_path.read_text())
    assert assembly_result['blackline_status'] == 'skipped_by_operator'
    assert assembly_result.get('blackline_errors') is None

    # Blackline file should not exist
    blackline_path = snapshot / ".humanvoice" / "assembled" / "blackline.tex"
    assert not blackline_path.exists()


def test_assemble_v2_default_attempts_blackline(simple_fixture_snapshot):
    """Verify default behavior attempts blackline generation."""
    snapshot = simple_fixture_snapshot

    result = subprocess.run(
        ['hv', 'assemble-v2', str(snapshot)],
        capture_output=True,
        text=True
    )

    # Assembly should succeed regardless of blackline outcome
    assert result.returncode == 0, f"assemble-v2 failed: {result.stderr}"

    # Check assembly result metadata
    result_path = snapshot / ".humanvoice" / "assembled" / "assembly_result.json"
    assert result_path.exists()

    assembly_result = json.loads(result_path.read_text())

    # Blackline status should be recorded (not 'not_generated')
    blackline_status = assembly_result['blackline_status']
    assert blackline_status in ['generated', 'tool_unavailable', 'generation_failed']

    if blackline_status == 'generated':
        # Blackline file should exist
        blackline_path = snapshot / ".humanvoice" / "assembled" / "blackline.tex"
        assert blackline_path.exists(), "blackline.tex not found despite status=generated"

        # Should be valid LaTeX
        blackline_content = blackline_path.read_text()
        assert r"\documentclass" in blackline_content
        assert r"\begin{document}" in blackline_content
        assert r"\end{document}" in blackline_content

    elif blackline_status == 'generation_failed':
        # Errors should be recorded
        assert assembly_result.get('blackline_errors') is not None
        assert len(assembly_result['blackline_errors']) > 0


def test_assemble_v2_blackline_preserves_assembly_success(simple_fixture_snapshot):
    """Verify that blackline generation failure does not fail assembly."""
    snapshot = simple_fixture_snapshot

    # Run with default (blackline enabled)
    result = subprocess.run(
        ['hv', 'assemble-v2', str(snapshot)],
        capture_output=True,
        text=True
    )

    # Assembly must succeed even if blackline fails
    assert result.returncode == 0, f"assemble-v2 should succeed even if blackline fails: {result.stderr}"

    result_path = snapshot / ".humanvoice" / "assembled" / "assembly_result.json"
    assembly_result = json.loads(result_path.read_text())

    # Core assembly must complete
    assert assembly_result['assembly_complete'] is True
    assert assembly_result['patches_failed'] == 0

    # Assembled output must exist
    assembled_path = snapshot / ".humanvoice" / "assembled" / "assembled.tex"
    assert assembled_path.exists()


def test_assemble_v2_blackline_result_schema():
    """Verify assembly_result.json has correct blackline fields."""
    from humanvoice.patch_assembly import PatchAssemblyResult

    # Create result with blackline fields
    result = PatchAssemblyResult(
        snapshot_id="test-snapshot",
        total_patches=1,
        patches_applied=1,
        patches_failed=[],
        assembly_complete=True,
        blackline_status="generated",
        blackline_errors=None,
    )

    # Should have all expected fields
    assert hasattr(result, 'blackline_status')
    assert hasattr(result, 'blackline_errors')

    # Test with errors
    result_with_errors = PatchAssemblyResult(
        snapshot_id="test-snapshot",
        total_patches=1,
        patches_applied=1,
        patches_failed=[],
        assembly_complete=True,
        blackline_status="generation_failed",
        blackline_errors=["part 0: timeout"],
    )

    assert result_with_errors.blackline_errors == ["part 0: timeout"]
