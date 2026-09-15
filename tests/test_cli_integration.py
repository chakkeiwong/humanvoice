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


def create_live_model_brief(path: Path) -> None:
    """Create brief that authorizes live model inference (for tier 5 tests)."""
    brief = {
        "reader_role": "graduate_student",
        "decision_type": "research",
        "time_available_minutes": 60,
        "prior_knowledge": "graduate_level",
        "success_criteria": "understand_key_concepts",
        "genre": "technical",
        "remote_inference_authorized": True,  # Required for live model
    }
    path.write_text(json.dumps(brief, indent=2))


def run_pipeline_through_rewrite(tmp_path: Path, fixture: str = "register/001.tex") -> Path:
    """Run init -> inventory --freeze -> plan -> rewrite in mock mode.

    Returns the snapshot directory. Skips if the fixture is absent.
    """
    fixture_path = Path("fixtures/synthetic") / fixture
    if not fixture_path.exists():
        pytest.skip(f"Fixture not found: {fixture_path}")

    brief_path = tmp_path / "brief.json"
    create_minimal_brief(brief_path)
    snapshot = tmp_path / "snapshot"

    result = subprocess.run(
        ['hv', 'init', str(fixture_path), '--brief', str(brief_path), '--output', str(snapshot)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f"init failed: {result.stderr}"

    result = subprocess.run(
        ['hv', 'inventory', str(snapshot), '--mock', '--freeze', '--adjudicator', 'test-harness'],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f"inventory failed: {result.stderr}"

    result = subprocess.run(
        ['hv', 'plan', str(snapshot)], capture_output=True, text=True
    )
    assert result.returncode == 0, f"plan failed: {result.stderr}"
    plan_output = json.loads(result.stdout)

    result = subprocess.run(
        ['hv', 'rewrite', str(snapshot),
         '--baseline-id', plan_output['baseline_id'],
         '--plan-id', plan_output['plan_id'], '--mock'],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f"rewrite failed: {result.stderr}"

    return snapshot


def read_unit_result(snapshot: Path, unit_id: str = "unit-001") -> tuple[Path, dict]:
    """Read one rewrite unit result from disk."""
    path = snapshot / ".humanvoice" / "rewrites" / f"{unit_id}.json"
    assert path.exists(), f"rewrite output missing: {path}"
    return path, json.loads(path.read_text())


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

    # Step 5: hv preflight-v2
    result = subprocess.run(
        ['hv', 'preflight-v2', str(snapshot)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"preflight-v2 failed: {result.stderr}"

    preflight_output = json.loads(result.stdout)
    assert preflight_output['status'] == 'pass'

    # Step 6: hv assemble-v2
    result = subprocess.run(
        ['hv', 'assemble-v2', str(snapshot)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"assemble-v2 failed: {result.stderr}"

    # Verify assembled output exists
    assembled_file = snapshot / ".humanvoice" / "assembled" / "assembled.tex"
    assert assembled_file.exists(), "assembled output not created"

    # Verify assembly result was saved
    result_file = snapshot / ".humanvoice" / "assembled" / "assembly_result.json"
    assert result_file.exists(), "assembly result not created"

    assembly_result = json.loads(result_file.read_text())
    assert assembly_result['assembly_complete'] is True
    assert assembly_result['patches_failed'] == 0


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


def test_preflight_v2_accepts_clean_rewrite(tmp_path):
    """preflight-v2 passes when the rewrite preserved every concept."""
    snapshot = run_pipeline_through_rewrite(tmp_path)

    result = subprocess.run(
        ['hv', 'preflight-v2', str(snapshot)], capture_output=True, text=True
    )
    assert result.returncode == 0, f"preflight-v2 failed: {result.stderr}"

    summary = json.loads(result.stdout)
    assert summary['status'] == 'pass'
    assert summary['units_blocked'] == 0
    assert summary['units_acceptable'] == summary['units_verified'] >= 1

    # Per-unit result must be persisted for the assemble phase to read.
    preflight_file = snapshot / ".humanvoice" / "preflight" / "unit-001.json"
    assert preflight_file.exists(), "preflight result not written"


def test_preflight_v2_blocks_deleted_concept(tmp_path):
    """Negative control: a dropped concept correspondence must block."""
    snapshot = run_pipeline_through_rewrite(tmp_path)

    path, unit_result = read_unit_result(snapshot)
    unit_result['concept_correspondences'] = []
    path.write_text(json.dumps(unit_result, indent=2))

    result = subprocess.run(
        ['hv', 'preflight-v2', str(snapshot)], capture_output=True, text=True
    )
    assert result.returncode == 1, "deleted concept must fail closed"

    summary = json.loads(result.stdout)
    assert summary['status'] == 'blocked'
    assert 'unit-001' in summary['blocked_units']


def test_preflight_v2_blocks_unmet_obligation(tmp_path):
    """Negative control: an unmet explanation obligation must block."""
    snapshot = run_pipeline_through_rewrite(tmp_path)

    path, unit_result = read_unit_result(snapshot)
    unit_result['unmet_obligations'] = [{
        "concept_id": unit_result['concept_correspondences'][0]['source_concept_id'],
        "functions": ["definition", "motivation"],
        "fulfilled_in_output": False,
        "output_span_ids": [],
    }]
    path.write_text(json.dumps(unit_result, indent=2))

    result = subprocess.run(
        ['hv', 'preflight-v2', str(snapshot)], capture_output=True, text=True
    )
    assert result.returncode == 1, "unmet obligation must fail closed"
    assert 'obligation_unmet' in result.stderr


def test_preflight_v2_blocks_missing_output(tmp_path):
    """Negative control: a unit claimed complete with no output must block."""
    snapshot = run_pipeline_through_rewrite(tmp_path)

    path, _ = read_unit_result(snapshot)
    path.unlink()

    result = subprocess.run(
        ['hv', 'preflight-v2', str(snapshot)], capture_output=True, text=True
    )
    assert result.returncode == 1, "missing output must fail closed"

    summary = json.loads(result.stdout)
    assert 'unit-001' in summary['units_missing_output']


def test_preflight_v2_requires_rewrite_first(tmp_path):
    """preflight-v2 exits 3 when no rewrite session exists."""
    fixture_path = Path("fixtures/synthetic/register/001.tex")
    if not fixture_path.exists():
        pytest.skip("Register fixture not found")

    brief_path = tmp_path / "brief.json"
    create_minimal_brief(brief_path)
    snapshot = tmp_path / "snapshot"

    subprocess.run(
        ['hv', 'init', str(fixture_path), '--brief', str(brief_path), '--output', str(snapshot)],
        check=True, capture_output=True
    )

    result = subprocess.run(
        ['hv', 'preflight-v2', str(snapshot)], capture_output=True, text=True
    )
    assert result.returncode == 3, "missing prerequisites must exit 3"


def test_tier4_multi_file_architecture_assessment(tmp_path):
    """Tier 4: 20-file architecture assessment - verify multi-file topology."""

    fixture_dir = Path("fixtures/synthetic/architecture_assessment")
    if not fixture_dir.exists():
        pytest.skip("Architecture assessment fixture not found")

    # TODO: Multi-file init support - check if hv init accepts directory


def test_tier5_live_model_equation_fixture(tmp_path):
    """Tier 5: Live model execution on equation/001.tex (22 lines).

    This test exercises the full pipeline WITH live model inference:
    init -> inventory --freeze -> plan -> rewrite (NO --mock) -> preflight -> assemble

    This validates that ModelConfig.from_profile() works through the CLI and that
    timeout configuration allows model calls to complete.

    Uses equation/001.tex (22 lines of real technical content with LaTeX equations).
    """
    fixture_path = Path("fixtures/synthetic/equation/001.tex")
    if not fixture_path.exists():
        pytest.skip("Equation fixture not found")

    brief_path = tmp_path / "brief.json"
    create_live_model_brief(brief_path)  # Use live model brief
    snapshot = tmp_path / "snapshot"

    # Step 1: hv init
    result = subprocess.run(
        ['hv', 'init', str(fixture_path), '--brief', str(brief_path), '--output', str(snapshot)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"init failed: {result.stderr}"

    # Step 2: hv inventory --freeze (LIVE MODEL for real concept extraction)
    result = subprocess.run(
        ['hv', 'inventory', str(snapshot), '--freeze', '--adjudicator', 'live-test'],
        capture_output=True,
        text=True,
        timeout=600  # 10 minutes for live extraction
    )
    assert result.returncode == 0, f"inventory failed: {result.stderr}"

    # Step 3: hv plan (v2)
    result = subprocess.run(
        ['hv', 'plan', str(snapshot)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"plan failed: {result.stderr}"
    plan_output = json.loads(result.stdout)
    baseline_id = plan_output['baseline_id']
    plan_id = plan_output['plan_id']

    # Step 4: hv rewrite WITH LIVE MODEL (no --mock flag) and extended timeout
    result = subprocess.run(
        ['hv', 'rewrite', str(snapshot),
         '--baseline-id', baseline_id,
         '--plan-id', plan_id,
         '--timeout', '1800'],  # 30 minutes for live model
        capture_output=True,
        text=True,
        timeout=2000  # Subprocess timeout: 33+ minutes
    )
    assert result.returncode == 0, f"rewrite with live model failed: {result.stderr}"

    rewrite_output = json.loads(result.stdout)
    assert rewrite_output['status'] == 'complete', f"rewrite failed: {rewrite_output}"
    assert rewrite_output['correspondence_ratio'] == 1.0, "correspondence must be 100%"
    assert rewrite_output['units_completed'] > 0, "no units completed"

    # Step 5: hv preflight-v2
    result = subprocess.run(
        ['hv', 'preflight-v2', str(snapshot)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"preflight-v2 failed: {result.stderr}"

    preflight_output = json.loads(result.stdout)
    assert preflight_output['status'] == 'pass'

    # Step 6: hv assemble-v2
    result = subprocess.run(
        ['hv', 'assemble-v2', str(snapshot)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"assemble-v2 failed: {result.stderr}"

    assembled_file = snapshot / ".humanvoice" / "assembled" / "assembled.tex"
    assert assembled_file.exists(), "assembled output not created"

    assembly_result = json.loads((snapshot / ".humanvoice" / "assembled" / "assembly_result.json").read_text())
    assert assembly_result['assembly_complete'] is True
    assert assembly_result['patches_failed'] == 0
