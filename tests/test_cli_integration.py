"""
CLI integration tests for v2 pipeline end-to-end execution.

Tests that the full pipeline (init -> inventory -> plan -> rewrite -> preflight -> assemble)
completes successfully and produces the expected artifacts at each phase boundary.

All tests run in --mock mode for speed and cost.
"""

import json
import pytest
import subprocess
from pathlib import Path


def create_minimal_brief(path: Path) -> None:
    """Create minimal brief for testing."""
    brief = {
        "reader_role": "graduate_student",
        "decision_type": "research",
        "time_available_minutes": 60,
        "prior_knowledge": "graduate_level",
        "success_criteria": "understand_key_concepts",
        "genre": "technical",
        "remote_inference_authorized": False,
    }
    path.write_text(json.dumps(brief, indent=2))


def test_tier0_negative_empty_baseline_fails(tmp_path):
    """Negative control: empty baseline must exit non-zero."""
    baseline = tmp_path / "empty_baseline.json"
    baseline.write_text(json.dumps({
        "baseline_id": "baseline-empty",
        "snapshot_id": "snap-001",
        "source_hash": "fake",
        "concept_entries": [],  # Empty
        "total_concepts": 0,
    }))

    # Attempting to plan with empty baseline should fail
    # (This will fail until hv plan is wired to v2 planner)
    # Placeholder for now - will implement after wiring


def test_tier1_smoke_register_fixture(tmp_path):
    """Tier 1: 5-line register fixture through full pipeline in mock mode."""

    # Use existing register fixture
    fixture_path = Path("fixtures/synthetic/register/001.tex")
    if not fixture_path.exists():
        pytest.skip("Register fixture not found")

    brief_path = tmp_path / "brief.json"
    create_minimal_brief(brief_path)

    snapshot = tmp_path / "snapshot"

    # Step 1: hv init
    result = subprocess.run(
        ['hv', 'init', str(fixture_path), '--brief', str(brief_path), '--output', str(snapshot)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"init failed: {result.stderr}"
    assert snapshot.exists()
    assert (snapshot / "manifest.json").exists()

    # Step 2: hv inventory --mock --freeze
    result = subprocess.run(
        ['hv', 'inventory', str(snapshot), '--mock', '--freeze', '--adjudicator', 'test-harness'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"inventory failed: {result.stderr}"

    # Check that spans and baseline were written
    spans_file = snapshot / ".humanvoice" / "inventory" / "spans.jsonl"
    assert spans_file.exists(), "spans.jsonl not created"

    baseline_file = snapshot / ".humanvoice" / "inventory" / "baseline.json"
    assert baseline_file.exists(), "baseline not frozen"

    # Step 3: hv plan
    result = subprocess.run(
        ['hv', 'plan', str(snapshot)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"plan failed: {result.stderr}"

    # Verify plan was created
    import json
    output = json.loads(result.stdout)
    plan_id = output['plan_id']
    plan_file = snapshot / ".humanvoice" / "plans" / f"{plan_id}.json"
    assert plan_file.exists(), "plan not created"

    # Step 4: hv rewrite --mock
    baseline_id = output['baseline_id']
    result = subprocess.run(
        ['hv', 'rewrite', str(snapshot), '--baseline-id', baseline_id, '--plan-id', plan_id, '--mock'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"rewrite failed: {result.stderr}"

    # Verify rewrite session was saved
    rewrite_output = json.loads(result.stdout)
    assert rewrite_output['status'] == 'complete'
    assert rewrite_output['correspondence_ratio'] == 1.0

    # TODO: After item 5 (wire preflight/assemble), extend to full pipeline:
    # Step 5: hv preflight
    # Step 6: hv assemble


def test_tier2_protected_citation_fixture(tmp_path):
    """Tier 2: Citation fixture - verify protected objects preserved."""

    fixture_path = Path("fixtures/synthetic/citation/001.tex")
    if not fixture_path.exists():
        pytest.skip("Citation fixture not found")

    answer_key_path = Path("fixtures/answer-keys/citation-001.json")
    if not answer_key_path.exists():
        pytest.skip("Citation answer key not found")

    brief_path = tmp_path / "brief.json"
    create_minimal_brief(brief_path)

    snapshot = tmp_path / "snapshot"

    # Init and inventory
    subprocess.run(
        ['hv', 'init', str(fixture_path), '--brief', str(brief_path), '--output', str(snapshot)],
        check=True,
        capture_output=True
    )

    result = subprocess.run(
        ['hv', 'inventory', str(snapshot), '--mock'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0

    # TODO: After full pipeline wired, load answer key and verify protected objects
    # are byte-identical in assembled output


def test_tier3_multi_unit_large_report(tmp_path):
    """Tier 3: 116-line report - verify multiple rewrite units created."""

    fixture_path = Path("fixtures/synthetic/large_report/source.tex")
    if not fixture_path.exists():
        pytest.skip("Large report fixture not found")

    brief_path = tmp_path / "brief.json"
    create_minimal_brief(brief_path)

    snapshot = tmp_path / "snapshot"

    subprocess.run(
        ['hv', 'init', str(fixture_path), '--brief', str(brief_path), '--output', str(snapshot)],
        check=True,
        capture_output=True
    )

    result = subprocess.run(
        ['hv', 'inventory', str(snapshot), '--mock'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0

    # TODO: After plan wiring, verify:
    # plan = load_rewrite_plan(plan_path)
    # assert len(plan.units) > 1, "Should create multiple units for 116-line source"


def test_tier4_multi_file_architecture_assessment(tmp_path):
    """Tier 4: 20-file architecture assessment - verify multi-file topology."""

    fixture_dir = Path("fixtures/synthetic/architecture_assessment")
    if not fixture_dir.exists():
        pytest.skip("Architecture assessment fixture not found")

    # TODO: Multi-file init support - check if hv init accepts directory
    # or needs modification to handle multi-file sources
    pytest.skip("Multi-file init not yet confirmed")
