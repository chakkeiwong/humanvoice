"""End-to-end ZLB snapshot integration tests.

These tests validate the complete v2 pipeline on the ZLB manuscript (3,368 lines).
Unlike test_cli_integration.py which uses synthetic fixtures, these run against the
real ZLB paper and verify that all pipeline stages complete without errors.
"""

import json
import subprocess
from pathlib import Path
import pytest


@pytest.fixture
def zlb_snapshot():
    """Return path to ZLB v2 snapshot directory."""
    snapshot = Path("sessions/zlb-v2-snapshot")
    if not snapshot.exists():
        pytest.skip("ZLB snapshot not initialized")
    return snapshot


def test_zlb_inventory_creates_baseline(zlb_snapshot):
    """Verify inventory command creates frozen baseline for ZLB."""
    baseline_path = zlb_snapshot / ".humanvoice" / "inventory" / "baseline.json"

    # Run inventory if baseline doesn't exist
    if not baseline_path.exists():
        result = subprocess.run(
            ['hv', 'inventory', str(zlb_snapshot), '--mock', '--freeze', '--adjudicator', 'test-harness'],
            capture_output=True,
            text=True,
            timeout=600
        )
        assert result.returncode == 0, f"inventory failed: {result.stderr}"

    # Verify baseline was created
    assert baseline_path.exists(), "Baseline not created"

    baseline = json.loads(baseline_path.read_text())
    assert 'concept_entries' in baseline
    assert len(baseline['concept_entries']) > 0, "Baseline has no concepts"
    print(f"✓ ZLB baseline created with {len(baseline['concept_entries'])} concepts")


def test_zlb_plan_creates_rewrite_units(zlb_snapshot):
    """Verify plan command creates rewrite units for ZLB."""
    # Ensure baseline exists first
    baseline_path = zlb_snapshot / ".humanvoice" / "inventory" / "baseline.json"

    if not baseline_path.exists():
        pytest.skip("Baseline not available")

    baseline = json.loads(baseline_path.read_text())
    baseline_id = baseline['baseline_id']

    # Run plan
    result = subprocess.run(
        ['hv', 'plan', str(zlb_snapshot)],
        capture_output=True,
        text=True,
        timeout=300
    )
    assert result.returncode == 0, f"plan failed: {result.stderr}"

    plan_output = json.loads(result.stdout)
    assert plan_output['status'] == 'plan_created'
    assert plan_output['total_units'] > 0, "No rewrite units created"

    # Verify plan file exists
    plan_file = zlb_snapshot / ".humanvoice" / "plans" / f"{plan_output['plan_id']}.json"
    assert plan_file.exists(), f"Plan file not found: {plan_file}"
    print(f"✓ ZLB plan created with {plan_output['total_units']} units")


def test_zlb_rewrite_with_mock(zlb_snapshot):
    """Verify rewrite completes in mock mode for ZLB."""
    # Ensure baseline and plan exist
    baseline_path = zlb_snapshot / ".humanvoice" / "inventory" / "baseline.json"

    if not baseline_path.exists():
        pytest.skip("Baseline not available")

    baseline = json.loads(baseline_path.read_text())
    baseline_id = baseline['baseline_id']

    plans_dir = zlb_snapshot / ".humanvoice" / "plans"
    plans = list(plans_dir.glob("plan-*.json"))

    if not plans:
        pytest.skip("Plan not available")

    plan_data = json.loads(plans[0].read_text())
    plan_id = plan_data['plan_id']

    # Run rewrite in mock mode with extended timeout
    result = subprocess.run(
        ['hv', 'rewrite', str(zlb_snapshot),
         '--baseline-id', baseline_id,
         '--plan-id', plan_id,
         '--mock',
         '--timeout', '600'],
        capture_output=True,
        text=True,
        timeout=700
    )
    assert result.returncode == 0, f"rewrite failed: {result.stderr}"

    rewrite_output = json.loads(result.stdout)
    assert rewrite_output['status'] == 'complete'
    assert rewrite_output['correspondence_ratio'] == 1.0
    print(f"✓ ZLB mock rewrite completed: {rewrite_output['units_completed']} units")


def test_zlb_full_pipeline_mock(zlb_snapshot):
    """Full pipeline test: inventory -> plan -> rewrite (mock) -> preflight.

    Note: Assembly is expected to fail with mock rewrite output because mock mode
    generates minimal placeholder text (132 bytes vs 190KB source). This validates
    that assembly correctly rejects data loss. Live model validation happens in
    test_cli_integration.py::test_tier5_live_model_equation_fixture.
    """
    # Step 1: Inventory
    result = subprocess.run(
        ['hv', 'inventory', str(zlb_snapshot), '--mock', '--freeze', '--adjudicator', 'test-harness'],
        capture_output=True,
        text=True,
        timeout=600
    )
    assert result.returncode == 0, f"inventory failed: {result.stderr}"

    baseline_path = zlb_snapshot / ".humanvoice" / "inventory" / "baseline.json"
    baseline = json.loads(baseline_path.read_text())
    baseline_id = baseline['baseline_id']

    # Step 2: Plan
    result = subprocess.run(
        ['hv', 'plan', str(zlb_snapshot)],
        capture_output=True,
        text=True,
        timeout=300
    )
    assert result.returncode == 0, f"plan failed: {result.stderr}"
    plan_output = json.loads(result.stdout)
    plan_id = plan_output['plan_id']

    # Step 3: Rewrite (mock)
    result = subprocess.run(
        ['hv', 'rewrite', str(zlb_snapshot),
         '--baseline-id', baseline_id,
         '--plan-id', plan_id,
         '--mock',
         '--timeout', '600'],
        capture_output=True,
        text=True,
        timeout=700
    )
    assert result.returncode == 0, f"rewrite failed: {result.stderr}"

    # Step 4: Preflight
    result = subprocess.run(
        ['hv', 'preflight-v2', str(zlb_snapshot)],
        capture_output=True,
        text=True,
        timeout=300
    )
    assert result.returncode == 0, f"preflight failed: {result.stderr}"

    # Step 5: Assembly will fail with mock output (expected)
    # Mock rewrite generates only 132 bytes placeholder text for 190KB source
    # Assembly correctly rejects this as data loss
    result = subprocess.run(
        ['hv', 'assemble-v2', str(zlb_snapshot)],
        capture_output=True,
        text=True,
        timeout=300
    )
    assert result.returncode == 3, "Assembly should fail with exit code 3 for mock output"
    assert "patches failed to apply" in result.stderr, "Should report patch failure"

    print(f"✓ ZLB mock pipeline validated through preflight (assembly fails as expected)")
