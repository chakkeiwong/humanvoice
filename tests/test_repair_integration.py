"""Integration tests for restore command (Phase 5: hash-targeted restoration).

The restore command analyzes assembly correspondence manifests to identify
missing protected objects and proposes restoration strategies.

Test coverage:
- Missing object identification by hash
- Repair proposal generation with source context
- Edge cases: no missing objects, source unavailable, line out of bounds
"""

import json
from pathlib import Path

import pytest


@pytest.fixture
def repair_snapshot(tmp_path):
    """Create a snapshot with assembly correspondence showing missing objects."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()

    # Source file
    source_file = snapshot_dir / "source.tex"
    source_content = r"""\documentclass{article}
\begin{document}
Introduction text here.
\begin{equation}
\label{eq:energy}
E = mc^2
\end{equation}
More text with \cite{einstein1905}.
Another equation:
\begin{equation}
\label{eq:force}
F = ma
\end{equation}
Conclusion with \cite{newton1687}.
\end{document}"""
    source_file.write_text(source_content)

    # Compute hash
    from humanvoice.protected_objects import _compute_file_hash
    actual_hash = _compute_file_hash(source_file)

    # Source manifest with 4 objects
    source_manifest = {
        "record_type": "SourceProtectedObjectManifest",
        "source_file": "source.tex",
        "source_file_hash": actual_hash,
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "parser_agreement_score": 1.0,
        "equations": [
            {"id": "eq:energy", "hash": "hash_eq_energy", "content": "E = mc^2", "line": 5, "type": "equation"},
            {"id": "eq:force", "hash": "hash_eq_force", "content": "F = ma", "line": 11, "type": "equation"},
        ],
        "citations": [
            {"id": "cite_einstein", "hash": "hash_cite_einstein", "content": r"\cite{einstein1905}", "line": 8, "type": "citation"},
            {"id": "cite_newton", "hash": "hash_cite_newton", "content": r"\cite{newton1687}", "line": 13, "type": "citation"},
        ],
        "labels": [],
        "displaymath": [],
        "tables": [],
    }
    source_manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    source_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    source_manifest_path.write_text(json.dumps(source_manifest, indent=2))

    # Draft manifests (all objects preserved)
    runs_dir = snapshot_dir / ".humanvoice" / "runs" / "run-test-0001"
    runs_dir.mkdir(parents=True, exist_ok=True)

    draft_manifest = {
        "record_type": "DraftCorrespondenceManifest",
        "section_index": 0,
        "section_title": "Main",
        "parent_artifact_hash": actual_hash,
        "correspondence_to_source": {
            "preserved": [
                {"id": "eq:energy", "hash": "hash_eq_energy"},
                {"id": "eq:force", "hash": "hash_eq_force"},
                {"id": "cite_einstein", "hash": "hash_cite_einstein"},
                {"id": "cite_newton", "hash": "hash_cite_newton"},
            ],
            "missing": [],
            "added": [],
        },
        "retention_rate": 1.0,
        "dispositions": {"omitted_objects": []},
    }
    (runs_dir / "draft_correspondence_section_0.json").write_text(json.dumps(draft_manifest, indent=2))

    # Assembled directory
    assembled_dir = snapshot_dir / ".humanvoice" / "revisions" / "assembled"
    assembled_dir.mkdir(parents=True, exist_ok=True)

    assembled_file = assembled_dir / "assembled.tex"
    assembled_file.write_text(r"\documentclass{article}\begin{document}Partial content\end{document}")

    # Assembly manifest
    assembly_manifest = {
        "record_type": "AssemblyManifest",
        "assembled_at": "2026-01-01T00:00:00Z",
        "assembled_file": "assembled.tex",
        "sections": [{"section_index": 0, "title": "Main", "word_count": 2}],
        "total_word_count": 2,
    }
    (assembled_dir / "assembly_manifest.json").write_text(json.dumps(assembly_manifest, indent=2))

    return snapshot_dir


def test_restore_identifies_missing_objects(repair_snapshot):
    """Restore command identifies missing objects from assembly correspondence."""
    from humanvoice.commands.restore_command import find_missing_objects

    assembled_dir = repair_snapshot / ".humanvoice" / "revisions" / "assembled"

    # Assembly correspondence with 2 missing objects (50% retention)
    correspondence_manifest = {
        "record_type": "AssemblyCorrespondenceManifest",
        "parent_artifact_hash": "test_hash",
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "total_draft_objects": 4,
        "preserved_count": 2,
        "retention_vs_drafts": 0.5,
        "retention_vs_source": 0.5,
        "correspondence_to_source": {
            "preserved": [
                {"id": "eq:energy", "hash": "hash_eq_energy"},
                {"id": "cite_einstein", "hash": "hash_cite_einstein"},
            ],
            "missing": [
                {"id": "eq:force", "hash": "hash_eq_force"},
                {"id": "cite_newton", "hash": "hash_cite_newton"},
            ],
            "added": [],
        },
        "dispositions": {"omitted_objects": []},
    }
    (assembled_dir / "assembly_correspondence_test.json").write_text(
        json.dumps(correspondence_manifest, indent=2)
    )

    result = find_missing_objects(repair_snapshot)

    assert result["missing_count"] == 2
    assert result["retention_vs_drafts"] == 0.5
    assert len(result["missing_objects"]) == 2

    # Check that missing objects have source details
    missing_hashes = {obj["hash"] for obj in result["missing_objects"]}
    assert "hash_eq_force" in missing_hashes
    assert "hash_cite_newton" in missing_hashes

    # Verify source line numbers are present
    for obj in result["missing_objects"]:
        assert obj["source_line"] is not None
        assert obj["content"] != ""


def test_restore_proposes_restoration_strategies(repair_snapshot):
    """Restore command generates restoration proposals with source context."""
    from humanvoice.commands.restore_command import find_missing_objects, propose_repairs

    assembled_dir = repair_snapshot / ".humanvoice" / "revisions" / "assembled"

    correspondence_manifest = {
        "record_type": "AssemblyCorrespondenceManifest",
        "parent_artifact_hash": "test_hash",
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "total_draft_objects": 4,
        "preserved_count": 3,
        "retention_vs_drafts": 0.75,
        "retention_vs_source": 0.75,
        "correspondence_to_source": {
            "preserved": [
                {"id": "eq:energy", "hash": "hash_eq_energy"},
                {"id": "eq:force", "hash": "hash_eq_force"},
                {"id": "cite_einstein", "hash": "hash_cite_einstein"},
            ],
            "missing": [
                {"id": "cite_newton", "hash": "hash_cite_newton"},
            ],
            "added": [],
        },
        "dispositions": {"omitted_objects": []},
    }
    (assembled_dir / "assembly_correspondence_test.json").write_text(
        json.dumps(correspondence_manifest, indent=2)
    )

    analysis = find_missing_objects(repair_snapshot)
    proposals = propose_repairs(repair_snapshot, analysis["missing_objects"])

    assert len(proposals) == 1
    proposal = proposals[0]

    assert proposal["object_hash"] == "hash_cite_newton"
    assert proposal["strategy"] == "copy_from_source"
    assert proposal["source_line"] == 13
    assert proposal["content"] == r"\cite{newton1687}"
    assert "context" in proposal
    assert "13:" in proposal["context"]  # Context includes the line number


def test_restore_handles_no_missing_objects(repair_snapshot):
    """Restore command reports success when no objects are missing."""
    from humanvoice.commands.restore_command import find_missing_objects

    assembled_dir = repair_snapshot / ".humanvoice" / "revisions" / "assembled"

    # Assembly correspondence with 100% retention
    correspondence_manifest = {
        "record_type": "AssemblyCorrespondenceManifest",
        "parent_artifact_hash": "test_hash",
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "total_draft_objects": 4,
        "preserved_count": 4,
        "retention_vs_drafts": 1.0,
        "retention_vs_source": 1.0,
        "correspondence_to_source": {
            "preserved": [
                {"id": "eq:energy", "hash": "hash_eq_energy"},
                {"id": "eq:force", "hash": "hash_eq_force"},
                {"id": "cite_einstein", "hash": "hash_cite_einstein"},
                {"id": "cite_newton", "hash": "hash_cite_newton"},
            ],
            "missing": [],
            "added": [],
        },
        "dispositions": {"omitted_objects": []},
    }
    (assembled_dir / "assembly_correspondence_test.json").write_text(
        json.dumps(correspondence_manifest, indent=2)
    )

    result = find_missing_objects(repair_snapshot)

    assert result["missing_count"] == 0
    assert "No missing objects" in result["detail"]


def test_restore_handles_missing_source_manifest(repair_snapshot):
    """Restore command reports error when source manifest is missing."""
    from humanvoice.commands.restore_command import find_missing_objects

    # Remove source manifest
    source_manifest_path = repair_snapshot / ".humanvoice" / "protected_objects" / "source_manifest.json"
    source_manifest_path.unlink()

    assembled_dir = repair_snapshot / ".humanvoice" / "revisions" / "assembled"

    correspondence_manifest = {
        "record_type": "AssemblyCorrespondenceManifest",
        "parent_artifact_hash": "test_hash",
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "total_draft_objects": 4,
        "preserved_count": 2,
        "retention_vs_drafts": 0.5,
        "retention_vs_source": 0.5,
        "correspondence_to_source": {
            "preserved": [],
            "missing": [
                {"id": "eq:force", "hash": "hash_eq_force"},
                {"id": "cite_newton", "hash": "hash_cite_newton"},
            ],
            "added": [],
        },
        "dispositions": {"omitted_objects": []},
    }
    (assembled_dir / "assembly_correspondence_test.json").write_text(
        json.dumps(correspondence_manifest, indent=2)
    )

    result = find_missing_objects(repair_snapshot)

    assert "error" in result
    assert result["error"] == "no_source_manifest"


def test_restore_handles_objects_not_in_source(repair_snapshot):
    """Restore command handles objects that were added in drafts (not in source)."""
    from humanvoice.commands.restore_command import find_missing_objects

    assembled_dir = repair_snapshot / ".humanvoice" / "revisions" / "assembled"

    # Assembly correspondence with a missing object that's not in source manifest
    correspondence_manifest = {
        "record_type": "AssemblyCorrespondenceManifest",
        "parent_artifact_hash": "test_hash",
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "total_draft_objects": 5,
        "preserved_count": 4,
        "retention_vs_drafts": 0.8,
        "retention_vs_source": 0.8,
        "correspondence_to_source": {
            "preserved": [
                {"id": "eq:energy", "hash": "hash_eq_energy"},
                {"id": "eq:force", "hash": "hash_eq_force"},
                {"id": "cite_einstein", "hash": "hash_cite_einstein"},
                {"id": "cite_newton", "hash": "hash_cite_newton"},
            ],
            "missing": [
                {"id": "draft_added", "hash": "hash_draft_only", "type": "equation", "content": "x = y"},
            ],
            "added": [],
        },
        "dispositions": {"omitted_objects": []},
    }
    (assembled_dir / "assembly_correspondence_test.json").write_text(
        json.dumps(correspondence_manifest, indent=2)
    )

    result = find_missing_objects(repair_snapshot)

    assert result["missing_count"] == 1
    missing_obj = result["missing_objects"][0]
    assert missing_obj["hash"] == "hash_draft_only"
    assert missing_obj["source_line"] is None
    assert "Not found in source manifest" in missing_obj.get("note", "")
