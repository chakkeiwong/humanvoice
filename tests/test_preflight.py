"""
Test suite for hv preflight command.

Tests deterministic register checking, abstention behavior, and fixture F-REGISTER-001.
"""

import json
import pytest
import subprocess
from pathlib import Path


def test_preflight_detects_wp_labels(tmp_path):
    """Test that WP3 is detected as a register violation."""
    source = tmp_path / "source.tex"
    source.write_text(r"\documentclass{article}\begin{document}The WP3 phase.\end{document}")

    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "reader_role": "executive",
        "decision_type": "approve",
        "time_available_minutes": 30,
        "prior_knowledge": "expert",
        "success_criteria": "clear"
    }))

    snapshot = tmp_path / "snapshot"

    # Init
    subprocess.run(['hv', 'init', str(source), '--brief', str(brief), '--output', str(snapshot)],
                   check=True, capture_output=True)

    # Preflight
    result = subprocess.run(['hv', 'preflight', str(snapshot), '--brief', str(brief), '--deterministic'],
                           capture_output=True, text=True)

    assert result.returncode == 1  # Gate failure
    output = json.loads(result.stdout)

    assert output["status"] == "gate_failure"
    assert len(output["findings"]) == 1
    assert output["findings"][0]["category"] == "register"
    assert "WP3" in output["findings"][0]["source_terms"]


def test_preflight_detects_private_paths(tmp_path):
    """Test that /srv/humanvoice/private is detected."""
    source = tmp_path / "source.tex"
    source.write_text(r"\documentclass{article}\begin{document}Path: /srv/humanvoice/private\end{document}")

    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "reader_role": "executive",
        "decision_type": "approve",
        "time_available_minutes": 30,
        "prior_knowledge": "expert",
        "success_criteria": "clear"
    }))

    snapshot = tmp_path / "snapshot"
    subprocess.run(['hv', 'init', str(source), '--brief', str(brief), '--output', str(snapshot)],
                   check=True, capture_output=True)

    result = subprocess.run(['hv', 'preflight', str(snapshot), '--brief', str(brief), '--deterministic'],
                           capture_output=True, text=True)

    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert any("/srv/humanvoice/private" in f["source_terms"] for f in output["findings"])


def test_preflight_passes_clean_document(tmp_path):
    """Test that clean document passes."""
    source = tmp_path / "source.tex"
    source.write_text(r"\documentclass{article}\begin{document}Clean text.\end{document}")

    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "reader_role": "executive",
        "decision_type": "approve",
        "time_available_minutes": 30,
        "prior_knowledge": "expert",
        "success_criteria": "clear"
    }))

    snapshot = tmp_path / "snapshot"
    subprocess.run(['hv', 'init', str(source), '--brief', str(brief), '--output', str(snapshot)],
                   check=True, capture_output=True)

    result = subprocess.run(['hv', 'preflight', str(snapshot), '--brief', str(brief), '--deterministic'],
                           capture_output=True, text=True)

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "pass"
    assert output["findings"] == []


def test_preflight_matches_fixture_answer_key(tmp_path):
    """Test that F-REGISTER-001 produces expected findings."""
    import shutil
    fixture_source = Path("fixtures/synthetic/register/001.tex")
    answer_key_path = Path("fixtures/answer-keys/register-001.json")

    if not fixture_source.exists() or not answer_key_path.exists():
        pytest.skip("Fixture not available")

    source = tmp_path / "001.tex"
    shutil.copy(fixture_source, source)

    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "reader_role": "sponsor",
        "decision_type": "approve review",
        "time_available_minutes": 45,
        "prior_knowledge": "technical",
        "success_criteria": "sound proposal"
    }))

    snapshot = tmp_path / "snapshot"
    subprocess.run(['hv', 'init', str(source), '--brief', str(brief), '--output', str(snapshot)],
                   check=True, capture_output=True)

    result = subprocess.run(['hv', 'preflight', str(snapshot), '--brief', str(brief), '--deterministic'],
                           capture_output=True, text=True)

    assert result.returncode == 1  # Expected failure
    output = json.loads(result.stdout)

    # Load answer key
    answer_key = json.loads(answer_key_path.read_text())
    expected_terms = answer_key["expected_findings"][0]["source_terms"]

    # Check that both expected terms are found
    found_terms = []
    for finding in output["findings"]:
        found_terms.extend(finding["source_terms"])

    assert "WP3" in found_terms
    assert "/srv/humanvoice/private" in found_terms


def test_preflight_rejects_nonexistent_snapshot(tmp_path):
    """Test that missing snapshot is rejected."""
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "reader_role": "executive",
        "decision_type": "approve",
        "time_available_minutes": 30,
        "prior_knowledge": "expert",
        "success_criteria": "clear"
    }))

    snapshot = tmp_path / "nonexistent"
    result = subprocess.run(['hv', 'preflight', str(snapshot), '--brief', str(brief), '--deterministic'],
                           capture_output=True, text=True)

    assert result.returncode == 3
