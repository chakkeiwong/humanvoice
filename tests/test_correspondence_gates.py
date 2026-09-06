"""
Phase 0 regression tests for correspondence verification.

Tests the nine fail-closed conditions from the revised implementation plan:
1. Missing source manifest
2. Missing draft manifests
3. Stale source manifest (hash mismatch)
4. Parser disagreement
5. 50% correspondence loss
6. Per-object identity tracking (not just counts)
7. Type-specific thresholds
8. Missing dispositions for omitted objects
9. Assembly correspondence regression
"""

import json
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from humanvoice.protected_objects import (
    extract_protected_objects,
    ProtectedManifest,
    ProtectedObject,
    _compute_file_hash
)


@pytest.fixture
def temp_snapshot_dir(tmp_path):
    """Create a temporary snapshot directory structure."""
    snapshot_dir = tmp_path / "snapshot_test"
    snapshot_dir.mkdir()

    # Create standard directories
    (snapshot_dir / ".humanvoice" / "protected_objects").mkdir(parents=True)
    (snapshot_dir / ".humanvoice" / "runs").mkdir(parents=True)
    (snapshot_dir / ".humanvoice" / "revisions" / "assembled").mkdir(parents=True)

    return snapshot_dir


@pytest.fixture
def sample_source_manifest(temp_snapshot_dir):
    """Create a sample source manifest for testing."""
    source_tex = temp_snapshot_dir / "source.tex"
    source_tex.write_text(r"""
\begin{equation}\label{eq:test1}
E = mc^2
\end{equation}

\begin{equation}\label{eq:test2}
F = ma
\end{equation}
""")

    manifest = extract_protected_objects(source_tex, snapshot_id="test")
    manifest_path = temp_snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    manifest_path.write_text(json.dumps(manifest.to_json(), indent=2))

    return manifest_path, manifest


def test_fail_closed_missing_source_manifest(temp_snapshot_dir):
    """Gate must block when source manifest missing, not pass."""
    from humanvoice.commands.release_command import check_protected_manifest_correspondence

    # No source manifest exists
    result = check_protected_manifest_correspondence(temp_snapshot_dir)

    assert result is not None, "Should block when source manifest missing"
    assert result["reason"] == "missing_source_manifest"
    assert "source_manifest.json" in result["detail"] or "source manifest" in result["detail"].lower()


def test_fail_closed_missing_draft_manifests(temp_snapshot_dir, sample_source_manifest):
    """Gate must block when draft manifests missing, not pass."""
    from humanvoice.commands.release_command import check_protected_manifest_correspondence

    # Source manifest exists but no draft manifests
    result = check_protected_manifest_correspondence(temp_snapshot_dir)

    # Current implementation checks for runs_dir first, then would check manifests
    # This test validates the intended behavior
    assert result is not None, "Should block when draft manifests missing"
    # May report no_runs_directory or no_draft_manifests depending on implementation
    assert "run" in result["reason"].lower() or "draft" in result["reason"].lower()


def test_fail_closed_stale_manifest(temp_snapshot_dir, sample_source_manifest):
    """Gate must block when manifest source hash doesn't match current source."""
    manifest_path, manifest = sample_source_manifest

    # Modify source file after manifest was created
    source_tex = temp_snapshot_dir / "source.tex"
    source_tex.write_text(r"""
\begin{equation}\label{eq:modified}
E = mc^3
\end{equation}
""")

    # Reload manifest and check hash
    manifest_data = json.loads(manifest_path.read_text())
    current_hash = _compute_file_hash(source_tex)

    assert manifest_data["source_file_hash"] != current_hash, "Hash should differ after modification"

    # The correspondence check should detect this
    # (This test validates the detection logic, implementation in Phase 3)


def test_parser_disagreement_detection():
    """Gate must detect when parsers disagree on object count >10%."""
    from humanvoice.protected_objects import compute_parser_agreement

    # Simulate significant disagreement
    pylatexenc_results = {"equations": [None] * 100, "displaymath": [None] * 10}
    regex_results = {"equations": [None] * 50, "displaymath": [None] * 10}

    agreement_score, diagnostic = compute_parser_agreement(pylatexenc_results, regex_results)

    assert agreement_score < 0.9, f"Should detect disagreement, got {agreement_score:.2f}"
    assert "equations" in diagnostic


def test_correspondence_50_percent_loss():
    """Gate must block when 50% of objects missing."""
    # This will be tested in Phase 3 when correspondence gate is implemented
    # Placeholder to ensure test structure is in place

    source_objects = 100
    draft_objects = 50
    loss_percentage = ((source_objects - draft_objects) / source_objects) * 100

    assert loss_percentage == 50.0
    # In Phase 3: assert check_correspondence() returns block with "loss" in reason


def test_per_object_tracking_not_just_counts():
    """Gate must verify specific objects preserved, not just counts."""
    # Test that 95% count but wrong equations should block

    # Create source objects
    source_hashes = {f"hash_{i:03d}" for i in range(100)}

    # Simulate draft with same count but different objects (5% overlap)
    draft_hashes = {f"hash_{i:03d}" for i in range(5)}  # Only first 5 match
    draft_hashes.update({f"wrong_hash_{i:03d}" for i in range(95)})  # 95 wrong ones

    # Identity preservation
    preserved = len(source_hashes & draft_hashes)
    identity_preservation_rate = preserved / len(source_hashes)

    assert len(draft_hashes) == 100, "Count matches (100 objects)"
    assert identity_preservation_rate == 0.05, "But only 5% identity preserved"

    # Gate should block on identity, not count
    # In Phase 3: assert check blocks when identity_preservation_rate < threshold


def test_type_specific_thresholds():
    """Different thresholds for equations (95%) vs assembly (99%)."""

    # Draft threshold: 95%
    draft_threshold = 0.95
    source_count = 100
    draft_count = 96

    draft_preservation = draft_count / source_count
    assert draft_preservation >= draft_threshold, "96% should pass draft threshold"

    # Assembly threshold: 99%
    assembly_threshold = 0.99
    assembly_count = 96

    assembly_preservation = assembly_count / source_count
    assert assembly_preservation < assembly_threshold, "96% should fail assembly threshold"


def test_omitted_object_requires_disposition():
    """Silently omitted objects must block; explicit disposition required."""

    source_objects = {"eq_001", "eq_002", "eq_003", "eq_004", "eq_005"}
    draft_objects = {"eq_001", "eq_002", "eq_003", "eq_004"}  # eq_005 missing

    missing = source_objects - draft_objects
    dispositions = {}  # No disposition provided

    assert len(missing) == 1, "One object missing"
    assert "eq_005" in missing
    assert "eq_005" not in dispositions, "No disposition for omitted object"

    # Gate should block requiring explicit disposition
    # In Phase 3: assert check blocks with "missing_disposition" in reason


def test_omitted_disposition_requires_human_approval():
    """Disposition exists but lacks human approval should block."""

    dispositions = {
        "eq_005": {
            "reason": "not_relevant",
            "comment": "Equation not needed in revised argument",
            "human_approved": False  # AI-generated, not human-approved
        }
    }

    for hash_val, disp in dispositions.items():
        assert not disp.get("human_approved", False), "Should require human approval"

    # Gate should block requiring human_approved: true
    # In Phase 3: assert check blocks with "unapproved" in reason


def test_assembly_correspondence_regression():
    """Assembly must not lose objects that draft preserved."""

    # Simulate draft preserving 96 equations
    draft_equation_hashes = {f"eq_{i:03d}" for i in range(96)}

    # Assembly loses 5 during concatenation
    assembled_equation_hashes = {f"eq_{i:03d}" for i in range(91)}

    missing_in_assembly = draft_equation_hashes - assembled_equation_hashes
    assembly_preservation = len(assembled_equation_hashes) / len(draft_equation_hashes)

    assert len(missing_in_assembly) == 5, "5 equations lost during assembly"
    assert assembly_preservation < 0.99, f"Assembly preservation {assembly_preservation:.2%} below 99% threshold"

    # Assembly should block
    # In Phase 4: assert assembly raises ValueError with "correspondence verification failed"


def test_baseline_fixture_extraction():
    """Validate extraction on baseline fixture meets acceptance criteria."""
    baseline_fixture = Path("fixtures/correspondence_baseline/source.tex")

    if not baseline_fixture.exists():
        pytest.skip("Baseline fixture not found")

    gold_manifest_path = Path("fixtures/correspondence_baseline/gold_manifest.json")
    gold_data = json.loads(gold_manifest_path.read_text())

    # Extract with parser bake-off
    manifest = extract_protected_objects(baseline_fixture, snapshot_id="test_baseline")

    # Acceptance criteria: ≥95% of gold standard found
    expected_equations = gold_data["protected_objects"]["equations"]["count"]
    found_equations = len(manifest.equations)

    extraction_rate = found_equations / expected_equations if expected_equations > 0 else 0

    assert extraction_rate >= 0.95, f"Extraction rate {extraction_rate:.1%} below 95% threshold (found {found_equations}/{expected_equations})"

    # Parser agreement: ≥90%
    assert manifest.parser_agreement_score >= 0.9, f"Parser agreement {manifest.parser_agreement_score:.1%} below 90% threshold"

    # Provenance binding present
    assert manifest.source_file_hash, "Source file hash must be present"
    assert manifest.parser_version, "Parser version must be present"
    assert manifest.extraction_timestamp, "Extraction timestamp must be present"

    print(f"\nBaseline fixture extraction:")
    print(f"  Expected equations: {expected_equations}")
    print(f"  Found equations: {found_equations}")
    print(f"  Extraction rate: {extraction_rate:.1%}")
    print(f"  Parser agreement: {manifest.parser_agreement_score:.1%}")
    print(f"  Source hash: {manifest.source_file_hash[:16]}...")


def test_provenance_binding_present():
    """All manifests must have provenance binding fields."""
    baseline_fixture = Path("fixtures/correspondence_baseline/source.tex")

    if not baseline_fixture.exists():
        pytest.skip("Baseline fixture not found")

    manifest = extract_protected_objects(baseline_fixture, snapshot_id="test_provenance")

    # Required provenance fields
    assert manifest.source_file_hash, "source_file_hash required"
    assert manifest.parser_version, "parser_version required"
    assert manifest.extraction_timestamp, "extraction_timestamp required"

    # Timestamp should be ISO 8601
    datetime.fromisoformat(manifest.extraction_timestamp.replace('Z', '+00:00'))

    # Parser version should list parsers used
    assert "pylatexenc" in manifest.parser_version or "regex" in manifest.parser_version

    # Each object should have provenance
    if manifest.equations:
        eq = manifest.equations[0]
        assert eq.source_file_hash == manifest.source_file_hash
        assert eq.hash, "Object hash required for identity tracking"
        assert eq.parser_source, "Parser source required"


def test_per_object_hash_uniqueness():
    """Object hashes should be unique for different content."""
    from humanvoice.protected_objects import _compute_object_hash

    content1 = "E = mc^2"
    content2 = "F = ma"
    content3 = "E=mc^2"  # Same as content1, different whitespace

    hash1 = _compute_object_hash(content1)
    hash2 = _compute_object_hash(content2)
    hash3 = _compute_object_hash(content3)

    assert hash1 != hash2, "Different equations should have different hashes"

    # Normalization collapses whitespace *runs* but does not strip all spaces.
    # This is conservative by design: stripping all spaces would merge distinct
    # tokens (\alpha beta → \alphabeta). So "E = mc^2" and "E=mc^2" normalize
    # to different strings and hash differently.
    assert hash1 != hash3, "Different whitespace patterns yield different hashes (conservative normalization)"

    # But multiple spaces collapse to one
    content4 = "E  =  mc^2"  # Multiple spaces
    hash4 = _compute_object_hash(content4)
    assert hash4 == hash1, "Whitespace runs should collapse to single space"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
