"""
Tests for regression replay runner (WP-V2-6 deliverable).

Tests replay verification and reproducibility:
- Manifest loading
- Frozen input verification
- Replay execution
- Result comparison
- Divergence detection
"""

import pytest
import json
from pathlib import Path

from tools.run_regression_replay import (
    ReplayManifest,
    ReplayResult,
    load_replay_manifest,
    verify_frozen_inputs,
    save_replay_result,
)


@pytest.fixture
def sample_manifest_data():
    """Sample replay manifest data."""
    return {
        "manifest_id": "manifest-001",
        "original_run_id": "run-001",
        "original_operator": "operator-1",
        "snapshot_path": "/path/to/snapshot",
        "baseline_id": "baseline-001",
        "baseline_hash": "abc123",
        "plan_id": "plan-001",
        "brief_path": "/path/to/brief.json",
        "policy_snapshot_path": "/path/to/policy.json",
        "model_config": {
            "model": "claude-opus-5",
            "temperature": 0.3,
        },
        "expected_result_hash": "def456",
        "expected_unit_count": 5,
        "expected_concept_correspondence": 1.0,
    }


@pytest.fixture
def sample_manifest_file(tmp_path, sample_manifest_data):
    """Sample replay manifest file."""
    manifest_path = tmp_path / "manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(sample_manifest_data, f)
    return manifest_path


def test_load_replay_manifest(sample_manifest_file):
    """Replay manifest loaded from JSON."""
    manifest = load_replay_manifest(sample_manifest_file)

    assert manifest.manifest_id == "manifest-001"
    assert manifest.original_run_id == "run-001"
    assert manifest.original_operator == "operator-1"
    assert manifest.baseline_id == "baseline-001"
    assert manifest.baseline_hash == "abc123"
    assert manifest.expected_unit_count == 5


def test_replay_manifest_fields():
    """ReplayManifest contains all required fields."""
    manifest = ReplayManifest(
        manifest_id="m1",
        original_run_id="r1",
        original_operator="op1",
        snapshot_path="/path/to/snapshot",
        baseline_id="base-001",
        baseline_hash="hash123",
        plan_id="plan-001",
        brief_path="/brief.json",
        policy_snapshot_path="/policy.json",
        model_config={"model": "opus"},
    )

    assert manifest.manifest_id == "m1"
    assert manifest.baseline_hash == "hash123"
    assert manifest.model_config["model"] == "opus"


def test_verify_frozen_inputs_missing_snapshot():
    """Frozen input verification fails with missing snapshot."""
    manifest = ReplayManifest(
        manifest_id="m1",
        original_run_id="r1",
        original_operator="op1",
        snapshot_path="/nonexistent/snapshot",
        baseline_id="base-001",
        baseline_hash="hash123",
        plan_id="plan-001",
        brief_path="/brief.json",
        policy_snapshot_path="/policy.json",
        model_config={},
    )

    valid, issues = verify_frozen_inputs(manifest)

    assert not valid
    assert any("Snapshot not found" in issue for issue in issues)


def test_verify_frozen_inputs_with_valid_structure(tmp_path):
    """Frozen input verification passes with valid structure."""
    # Create mock snapshot structure
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()

    baseline_dir = snapshot / ".humanvoice" / "baseline"
    baseline_dir.mkdir(parents=True)

    plan_dir = snapshot / ".humanvoice" / "plans"
    plan_dir.mkdir(parents=True)

    # Create baseline file with hash
    baseline_file = baseline_dir / "baseline-001.json"
    with open(baseline_file, 'w') as f:
        json.dump({
            "baseline_id": "baseline-001",
            "baseline_hash": "test-hash-123",
        }, f)

    # Create plan file
    plan_file = plan_dir / "plan-001.json"
    with open(plan_file, 'w') as f:
        json.dump({"plan_id": "plan-001"}, f)

    # Create brief and policy files
    brief_file = tmp_path / "brief.json"
    with open(brief_file, 'w') as f:
        json.dump({"reader": "graduate"}, f)

    policy_file = tmp_path / "policy.json"
    with open(policy_file, 'w') as f:
        json.dump({"policies": []}, f)

    manifest = ReplayManifest(
        manifest_id="m1",
        original_run_id="r1",
        original_operator="op1",
        snapshot_path=str(snapshot),
        baseline_id="baseline-001",
        baseline_hash="test-hash-123",
        plan_id="plan-001",
        brief_path=str(brief_file),
        policy_snapshot_path=str(policy_file),
        model_config={},
    )

    valid, issues = verify_frozen_inputs(manifest)

    assert valid
    assert len(issues) == 0


def test_verify_frozen_inputs_baseline_hash_mismatch(tmp_path):
    """Frozen input verification fails with baseline hash mismatch."""
    snapshot = tmp_path / "snapshot"
    baseline_dir = snapshot / ".humanvoice" / "baseline"
    baseline_dir.mkdir(parents=True)

    baseline_file = baseline_dir / "baseline-001.json"
    with open(baseline_file, 'w') as f:
        json.dump({
            "baseline_id": "baseline-001",
            "baseline_hash": "wrong-hash",
        }, f)

    plan_dir = snapshot / ".humanvoice" / "plans"
    plan_dir.mkdir(parents=True)
    plan_file = plan_dir / "plan-001.json"
    with open(plan_file, 'w') as f:
        json.dump({"plan_id": "plan-001"}, f)

    brief_file = tmp_path / "brief.json"
    with open(brief_file, 'w') as f:
        json.dump({}, f)

    policy_file = tmp_path / "policy.json"
    with open(policy_file, 'w') as f:
        json.dump({}, f)

    manifest = ReplayManifest(
        manifest_id="m1",
        original_run_id="r1",
        original_operator="op1",
        snapshot_path=str(snapshot),
        baseline_id="baseline-001",
        baseline_hash="expected-hash",
        plan_id="plan-001",
        brief_path=str(brief_file),
        policy_snapshot_path=str(policy_file),
        model_config={},
    )

    valid, issues = verify_frozen_inputs(manifest)

    assert not valid
    assert any("hash mismatch" in issue for issue in issues)


def test_replay_result_initialization():
    """ReplayResult initializes with correct fields."""
    result = ReplayResult(
        replay_id="replay-001",
        manifest_id="manifest-001",
        replay_operator="operator-2",
        original_result_hash="hash1",
        replay_result_hash="hash2",
    )

    assert result.replay_id == "replay-001"
    assert result.manifest_id == "manifest-001"
    assert result.replay_operator == "operator-2"
    assert not result.results_match


def test_replay_result_match_detection():
    """ReplayResult detects matching results."""
    result = ReplayResult(
        replay_id="replay-001",
        manifest_id="manifest-001",
        replay_operator="operator-2",
        original_result_hash="abc123",
        replay_result_hash="abc123",
    )

    result.results_match = (
        result.original_result_hash == result.replay_result_hash
    )

    assert result.results_match


def test_save_replay_result(tmp_path):
    """Replay result saved to JSON."""
    result = ReplayResult(
        replay_id="replay-001",
        manifest_id="manifest-001",
        replay_operator="operator-2",
        original_result_hash="hash1",
        replay_result_hash="hash1",
        results_match=True,
        unit_count_match=True,
        concept_correspondence_match=True,
        divergent_units=[],
    )

    output_file = tmp_path / "result.json"
    save_replay_result(result, output_file)

    assert output_file.exists()

    with open(output_file) as f:
        data = json.load(f)

    assert data["replay_id"] == "replay-001"
    assert data["results_match"]
    assert len(data["divergent_units"]) == 0


def test_replay_result_with_divergences():
    """ReplayResult tracks divergent units."""
    result = ReplayResult(
        replay_id="replay-001",
        manifest_id="manifest-001",
        replay_operator="operator-2",
        original_result_hash="hash1",
        replay_result_hash="hash2",
        results_match=False,
        divergent_units=["unit-003", "unit-007"],
        divergence_summary="2 units diverged",
    )

    assert not result.results_match
    assert len(result.divergent_units) == 2
    assert "unit-003" in result.divergent_units


def test_model_config_in_manifest():
    """Model config stored in manifest."""
    manifest = ReplayManifest(
        manifest_id="m1",
        original_run_id="r1",
        original_operator="op1",
        snapshot_path="/path",
        baseline_id="base-001",
        baseline_hash="hash",
        plan_id="plan-001",
        brief_path="/brief.json",
        policy_snapshot_path="/policy.json",
        model_config={
            "model": "claude-opus-5",
            "temperature": 0.3,
            "max_tokens": 8000,
        },
    )

    assert manifest.model_config["model"] == "claude-opus-5"
    assert manifest.model_config["temperature"] == 0.3
    assert manifest.model_config["max_tokens"] == 8000
