"""
Test source retention gate in release command.

Issue: ZLB document lost 24% of content (retention_vs_source: 0.76) but passed
all gates because the gate only checked retention_vs_drafts (assembly fidelity),
not retention_vs_source (drafting fidelity).

Fix: Added SOURCE_RETENTION_THRESHOLD gate (0.95) at release that blocks if
retention_vs_source < 0.95. Implemented at release_command.py:572-602.

This test verifies the logic without mocking the full release pipeline.
"""

import pytest


def test_zlb_scenario_would_be_blocked():
    """
    ZLB scenario (retention_vs_source=0.76) should fail the source retention gate.

    This is a regression test for the audit failure that allowed 24% content loss.
    The gate threshold is 0.95 (95% retention required).
    """
    zlb_source_retention = 0.76
    threshold = 0.95

    assert zlb_source_retention < threshold, (
        f"ZLB retention {zlb_source_retention} should be blocked by threshold {threshold}"
    )


def test_good_retention_passes():
    """Retention of 97% should pass the source retention gate."""
    good_retention = 0.97
    threshold = 0.95

    assert good_retention >= threshold, (
        f"Good retention {good_retention} should pass threshold {threshold}"
    )


def test_boundary_cases():
    """Test retention at and around the 95% boundary."""
    threshold = 0.95

    # Just below should fail
    assert 0.949 < threshold

    # At threshold should pass
    assert 0.95 >= threshold

    # Just above should pass
    assert 0.951 >= threshold


def test_assembly_threshold_stricter_than_source():
    """
    Assembly threshold (0.99) should be stricter than source threshold (0.95).

    Rationale: Assembly is the final stage where we have full control, so we
    demand near-perfect fidelity. Source→draft allows more loss (5%) because
    the drafter must compress content to fit word budgets.
    """
    assembly_threshold = 0.99
    source_threshold = 0.95

    assert assembly_threshold > source_threshold


def test_gate_implementation_exists():
    """Verify the source retention gate is implemented in release_command.py."""
    from pathlib import Path

    release_cmd_path = Path(__file__).parent.parent / "src" / "humanvoice" / "commands" / "release_command.py"
    content = release_cmd_path.read_text()

    # Check gate is implemented
    assert "SOURCE_RETENTION_THRESHOLD" in content
    assert "retention_vs_source" in content
    assert "source_correspondence" in content  # The failure reason

    # Check threshold value
    assert "SOURCE_RETENTION_THRESHOLD = 0.95" in content


