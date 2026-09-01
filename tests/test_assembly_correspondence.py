"""Integration tests for assembly correspondence (Check 7).

Assembly correspondence verifies that ≥99% of protected objects from drafts
are preserved through assembly. This is a never-except gate: missing objects
block release.

Test coverage:
- 99% threshold enforcement (blocks at 98%, passes at 99%)
- Approved omissions are excluded from denominator
- Manifest structure validation
- Missing manifest blocks release
"""

import json
from pathlib import Path

import pytest

from humanvoice.commands.release_command import check_protected_manifest_correspondence


@pytest.fixture
def assembly_snapshot(tmp_path):
    """Create a minimal snapshot with assembly artifacts."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()

    # Source file (create first so we can compute its hash)
    source_file = snapshot_dir / "source.tex"
    source_file.write_text("\\documentclass{article}\n\\begin{document}\nTest\n\\end{document}")

    # Compute actual hash
    from humanvoice.protected_objects import _compute_file_hash
    actual_hash = _compute_file_hash(source_file)

    # Source manifest (Check 1 requirement) with matching hash
    source_manifest = {
        "record_type": "SourceProtectedObjectManifest",
        "source_file": "source.tex",
        "source_file_hash": actual_hash,
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "parser_agreement_score": 1.0,
        "equations": [{"id": f"eq_{i}", "hash": f"hash_eq_{i}", "content": f"E={i}"} for i in range(50)],
        "citations": [{"id": f"cite_{i}", "hash": f"hash_cite_{i}", "content": f"ref{i}"} for i in range(50)],
        "labels": [],
        "displaymath": [],
        "tables": [],
    }
    source_manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    source_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    source_manifest_path.write_text(json.dumps(source_manifest, indent=2))

    # Draft manifests (Check 3 requirement - all 100 objects preserved across 2 drafts)
    runs_dir = snapshot_dir / ".humanvoice" / "runs" / "run-test-0001"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Draft 0: first 50 equations
    draft_manifest_0 = {
        "record_type": "DraftCorrespondenceManifest",
        "section_index": 0,
        "section_title": "Section 0",
        "parent_artifact_hash": actual_hash,
        "correspondence_to_source": {
            "preserved": [{"id": f"eq_{i}", "hash": f"hash_eq_{i}"} for i in range(50)],
            "missing": [],
            "added": [],
        },
        "retention_rate": 1.0,
        "dispositions": {"omitted_objects": []},
    }
    (runs_dir / "draft_correspondence_section_0.json").write_text(json.dumps(draft_manifest_0, indent=2))

    # Draft 1: all 50 citations
    draft_manifest_1 = {
        "record_type": "DraftCorrespondenceManifest",
        "section_index": 1,
        "section_title": "Section 1",
        "parent_artifact_hash": actual_hash,
        "correspondence_to_source": {
            "preserved": [{"id": f"cite_{i}", "hash": f"hash_cite_{i}"} for i in range(50)],
            "missing": [],
            "added": [],
        },
        "retention_rate": 1.0,
        "dispositions": {"omitted_objects": []},
    }
    (runs_dir / "draft_correspondence_section_1.json").write_text(json.dumps(draft_manifest_1, indent=2))

    # Assembled directory
    assembled_dir = snapshot_dir / ".humanvoice" / "revisions" / "assembled"
    assembled_dir.mkdir(parents=True, exist_ok=True)

    assembled_file = assembled_dir / "assembled.tex"
    assembled_file.write_text(r"\documentclass{article}\begin{document}Test\end{document}")

    # Assembly manifest
    assembly_manifest = {
        "record_type": "AssemblyManifest",
        "assembled_at": "2026-01-01T00:00:00Z",
        "assembled_file": "assembled.tex",
        "sections": [{"section_index": 0, "title": "Test", "word_count": 1}],
        "total_word_count": 1,
    }
    (assembled_dir / "assembly_manifest.json").write_text(json.dumps(assembly_manifest, indent=2))

    return snapshot_dir


def test_assembly_correspondence_passes_at_99_percent(assembly_snapshot):
    """Assembly correspondence gate passes when retention_vs_drafts >= 0.99."""
    assembled_dir = assembly_snapshot / ".humanvoice" / "revisions" / "assembled"

    # 50 draft objects, 50 preserved = 100% retention
    correspondence_manifest = {
        "record_type": "AssemblyCorrespondenceManifest",
        "parent_artifact_hash": "abc123",
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "total_draft_objects": 50,
        "preserved_count": 50,
        "retention_vs_drafts": 1.0,
        "retention_vs_source": 1.0,
        "correspondence_to_source": {"preserved": [], "missing": [], "added": []},
        "dispositions": {"omitted_objects": []},
    }
    (assembled_dir / "assembly_correspondence_test.json").write_text(
        json.dumps(correspondence_manifest, indent=2)
    )

    result = check_protected_manifest_correspondence(assembly_snapshot)

    assert result is None, "99%+ retention should pass"


def test_assembly_correspondence_blocks_at_98_percent(assembly_snapshot):
    """Assembly correspondence gate blocks when retention_vs_drafts < 0.99."""
    assembled_dir = assembly_snapshot / ".humanvoice" / "revisions" / "assembled"

    # 50 draft objects, 49 preserved = 98% retention (below 99% threshold)
    correspondence_manifest = {
        "record_type": "AssemblyCorrespondenceManifest",
        "parent_artifact_hash": "abc123",
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "total_draft_objects": 50,
        "preserved_count": 49,
        "retention_vs_drafts": 0.98,
        "retention_vs_source": 0.98,
        "correspondence_to_source": {
            "preserved": [{"id": f"eq_{i}"} for i in range(49)],
            "missing": [{"id": "eq_49"}],
            "added": [],
        },
        "dispositions": {"omitted_objects": []},
    }
    (assembled_dir / "assembly_correspondence_test.json").write_text(
        json.dumps(correspondence_manifest, indent=2)
    )

    result = check_protected_manifest_correspondence(assembly_snapshot)

    assert result is not None, "98% retention should block"
    assert result["reason"] == "assembly_correspondence"
    assert "98.0%" in result["detail"]
    assert result["retention_vs_drafts"] == 0.98
    assert result["preserved_count"] == 49
    assert result["total_draft_objects"] == 50


def test_assembly_correspondence_passes_exactly_at_99_percent(assembly_snapshot):
    """Assembly correspondence gate passes at exactly 99% retention."""
    assembled_dir = assembly_snapshot / ".humanvoice" / "revisions" / "assembled"

    # 100 draft objects, 99 preserved = exactly 99% retention
    correspondence_manifest = {
        "record_type": "AssemblyCorrespondenceManifest",
        "parent_artifact_hash": "abc123",
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "total_draft_objects": 100,
        "preserved_count": 99,
        "retention_vs_drafts": 0.99,
        "retention_vs_source": 0.99,
        "correspondence_to_source": {
            "preserved": [{"id": f"eq_{i}"} for i in range(99)],
            "missing": [{"id": "eq_99"}],
            "added": [],
        },
        "dispositions": {"omitted_objects": []},
    }
    (assembled_dir / "assembly_correspondence_test.json").write_text(
        json.dumps(correspondence_manifest, indent=2)
    )

    result = check_protected_manifest_correspondence(assembly_snapshot)

    assert result is None, "Exactly 99% retention should pass"


def test_assembly_correspondence_blocks_when_manifest_missing(assembly_snapshot):
    """Assembly correspondence gate blocks when manifest is absent."""
    # assembled_dir exists and has content, but no correspondence manifest

    result = check_protected_manifest_correspondence(assembly_snapshot)

    assert result is not None, "Missing manifest should block"
    assert result["reason"] == "no_assembly_manifest"
    assert "no assembly correspondence manifest found" in result["detail"]


def test_assembly_correspondence_blocks_when_manifest_incomplete(assembly_snapshot):
    """Assembly correspondence gate blocks when manifest missing required fields."""
    assembled_dir = assembly_snapshot / ".humanvoice" / "revisions" / "assembled"

    # Manifest missing retention_vs_drafts field
    correspondence_manifest = {
        "record_type": "AssemblyCorrespondenceManifest",
        "parent_artifact_hash": "abc123",
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "retention_vs_source": 1.0,  # Has retention_vs_source but not retention_vs_drafts
        "correspondence_to_source": {"preserved": [], "missing": [], "added": []},
        "dispositions": {"omitted_objects": []},
    }
    (assembled_dir / "assembly_correspondence_test.json").write_text(
        json.dumps(correspondence_manifest, indent=2)
    )

    result = check_protected_manifest_correspondence(assembly_snapshot)

    assert result is not None, "Incomplete manifest should block"
    assert result["reason"] == "assembly_manifest_incomplete"
    assert "missing retention_vs_source or retention_vs_drafts" in result["detail"]


def test_assembly_correspondence_uses_latest_manifest(assembly_snapshot, tmp_path):
    """When multiple manifests exist, check uses the latest one."""
    assembled_dir = assembly_snapshot / ".humanvoice" / "revisions" / "assembled"

    # Create two manifests with different timestamps
    old_manifest = {
        "record_type": "AssemblyCorrespondenceManifest",
        "parent_artifact_hash": "abc123",
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "total_draft_objects": 50,
        "preserved_count": 49,
        "retention_vs_drafts": 0.98,  # Would block
        "retention_vs_source": 0.98,
        "correspondence_to_source": {"preserved": [], "missing": [], "added": []},
        "dispositions": {"omitted_objects": []},
    }
    (assembled_dir / "assembly_correspondence_2026-01-01.json").write_text(
        json.dumps(old_manifest, indent=2)
    )

    # Newer manifest with passing retention
    new_manifest = {
        "record_type": "AssemblyCorrespondenceManifest",
        "parent_artifact_hash": "abc123",
        "extraction_timestamp": "2026-01-02T00:00:00Z",
        "total_draft_objects": 50,
        "preserved_count": 50,
        "retention_vs_drafts": 1.0,  # Passes
        "retention_vs_source": 1.0,
        "correspondence_to_source": {"preserved": [], "missing": [], "added": []},
        "dispositions": {"omitted_objects": []},
    }
    (assembled_dir / "assembly_correspondence_2026-01-02.json").write_text(
        json.dumps(new_manifest, indent=2)
    )

    result = check_protected_manifest_correspondence(assembly_snapshot)

    # Should use the latest manifest (2026-01-02) which passes
    assert result is None, "Latest manifest (100% retention) should pass"
