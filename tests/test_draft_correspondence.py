"""
Integration test for Phase 2: draft correspondence tracking.

Validates that draft_command:
- Loads the source protected manifest
- Routes protected objects to sections by line number
- Emits per-section draft correspondence manifests
- Reports retention rate
"""

import json
import tempfile
from pathlib import Path
import pytest

from humanvoice.commands import draft_command, init_command


def _make_valid_brief() -> dict:
    """Create a minimal valid brief for testing."""
    return {
        "record_type": "AuthoringBrief",
        "schema_version": "HV-SCHEMA-1.1",
        "reader_role": "test reader",
        "decision_type": "test decision",
        "time_available_minutes": 60,
        "prior_knowledge": "basic knowledge",
        "success_criteria": "test success",
        "reader": "test reader",
        "known_vocabulary": ["LaTeX"],
        "protected_objects": []
    }


def test_draft_routes_protected_objects_by_line_number():
    """
    Draft should route protected objects to sections based on source_start_line
    and source_end_line, replacing the old 3000-char truncation.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Use the baseline fixture source
        baseline_source = Path("fixtures/correspondence_baseline/source.tex")
        assert baseline_source.exists(), "Baseline fixture not found"

        # Init will copy source into output, so just reference the fixture
        brief_path = tmpdir / "brief.json"
        brief_path.write_text(json.dumps(_make_valid_brief()))

        # Run init to create snapshot and extract protected objects
        snapshot_dir = tmpdir / "snapshot"

        class InitArgs:
            source = baseline_source
            brief = brief_path
            output = snapshot_dir

        exit_code = init_command.run(InitArgs())
        assert exit_code == 0, "Init failed"

        # Verify source manifest was created
        source_manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
        assert source_manifest_path.exists(), "Source manifest not created"

        source_manifest = json.loads(source_manifest_path.read_text())
        total_objects = source_manifest["total_count"]
        assert total_objects > 0, "No protected objects extracted"

        # Find the line range that actually contains objects
        all_objects = (source_manifest["equations"] + source_manifest["labels"] +
                      source_manifest["citations"] + source_manifest["displaymath"] +
                      source_manifest["tables"])
        lines = [obj["line"] for obj in all_objects if obj["line"] is not None]
        assert lines, "No objects have line numbers"

        min_line = min(lines)
        max_line = max(lines)

        print(f"Objects span lines {min_line}-{max_line}")

        # Create a blueprint with one section covering the object range
        blueprint_path = tmpdir / "blueprint.json"
        blueprint_path.write_text(json.dumps({
            "blueprint": {
                "sections": [
                    {
                        "title": "Test Section",
                        "purpose": "Test protected object routing",
                        "word_budget": 200,
                        "evidence_needed": [],
                        "source_start_line": min_line,
                        "source_end_line": max_line,
                    }
                ]
            }
        }))

        # Test the routing helper functions
        from humanvoice.commands.draft_command import (
            _load_source_manifest,
            _prepare_section_evidence,
            _emit_draft_manifest,
        )

        loaded_manifest = _load_source_manifest(snapshot_dir)
        assert loaded_manifest is not None, "Failed to load source manifest"

        section = {
            "title": "Test Section",
            "source_start_line": min_line,
            "source_end_line": max_line,
        }

        evidence_text, protected_objects = _prepare_section_evidence(
            section=section,
            source_content="",
            source_manifest=loaded_manifest,
            evidence_files=[],
            snapshot_dir=snapshot_dir,
        )

        # Should have routed all protected objects
        assert len(protected_objects) == total_objects, f"Expected {total_objects} objects, got {len(protected_objects)}"

        # Evidence text should mention protected objects
        assert "Protected Objects in This Section" in evidence_text
        assert "Hash:" in evidence_text

        # A perfect draft is the source document itself. Concatenating object
        # contents would NOT round-trip: a label's content is the bare name
        # ("sec:intro", not "\label{sec:intro}") and an align row's content is the
        # row body without its environment wrapper, so neither re-extracts from a
        # bare concatenation. Re-drafting the source is the honest upper bound.
        draft_latex = (snapshot_dir / "source" / "source.tex").read_text()

        # Emit correspondence manifest
        output_dir = snapshot_dir / ".humanvoice" / "runs" / "test_run"
        output_dir.mkdir(parents=True)

        manifest_path = _emit_draft_manifest(
            output_dir=output_dir,
            section_title="Test Section",
            source_manifest=loaded_manifest,
            protected_objects_in_section=protected_objects,
            draft_latex=draft_latex,
        )

        assert manifest_path.exists(), "Draft correspondence manifest not created"

        # Validate manifest structure
        manifest = json.loads(manifest_path.read_text())

        assert manifest["record_type"] == "DraftCorrespondenceManifest"
        assert manifest["schema_version"] == "HV-SCHEMA-1.0"
        assert manifest["section_title"] == "Test Section"
        assert manifest["parent_artifact_hash"] == loaded_manifest.source_file_hash

        correspondence = manifest["correspondence_to_source"]
        assert "preserved" in correspondence
        assert "missing" in correspondence
        assert "added" in correspondence

        # With source as draft, retention should be 100%
        assert manifest["retention_rate"] == 1.0
        assert len(correspondence["preserved"]) == total_objects
        assert len(correspondence["missing"]) == 0

        # Check dispositions structure
        assert "dispositions" in manifest
        assert "omitted_objects" in manifest["dispositions"]
        assert len(manifest["dispositions"]["omitted_objects"]) == 0  # nothing missing


def test_draft_manifest_tracks_missing_objects():
    """Draft manifest should identify missing protected objects and require disposition."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        baseline_source = Path("fixtures/correspondence_baseline/source.tex")
        snapshot_dir = tmpdir / "snapshot"
        brief_path = tmpdir / "brief.json"
        brief_path.write_text(json.dumps(_make_valid_brief()))

        class InitArgs:
            source = baseline_source
            brief = brief_path
            output = snapshot_dir

        exit_code = init_command.run(InitArgs())
        assert exit_code == 0

        from humanvoice.commands.draft_command import (
            _load_source_manifest,
            _prepare_section_evidence,
            _emit_draft_manifest,
        )

        loaded_manifest = _load_source_manifest(snapshot_dir)

        source_manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
        source_manifest_data = json.loads(source_manifest_path.read_text())
        all_objects = (source_manifest_data["equations"] + source_manifest_data["labels"] +
                      source_manifest_data["citations"] + source_manifest_data["displaymath"] +
                      source_manifest_data["tables"])
        lines = [obj["line"] for obj in all_objects if obj["line"] is not None]
        min_line = min(lines)
        max_line = max(lines)

        section = {"title": "Test", "source_start_line": min_line, "source_end_line": max_line}
        evidence_text, protected_objects = _prepare_section_evidence(
            section, "", loaded_manifest, [], snapshot_dir
        )

        assert len(protected_objects) > 0

        # Draft that omits half the objects
        half_count = len(protected_objects) // 2
        draft_latex = "\n".join([obj["content"] for obj in protected_objects[:half_count]])

        output_dir = snapshot_dir / ".humanvoice" / "runs" / "test_run"
        output_dir.mkdir(parents=True)

        manifest_path = _emit_draft_manifest(
            output_dir, "Test", loaded_manifest, protected_objects, draft_latex
        )

        manifest = json.loads(manifest_path.read_text())

        # Should detect missing objects
        correspondence = manifest["correspondence_to_source"]
        missing_count = len(correspondence["missing"])
        preserved_count = len(correspondence["preserved"])

        assert missing_count > 0, "Should detect missing objects"
        assert preserved_count > 0, "Should detect preserved objects"
        assert missing_count + preserved_count == len(protected_objects)

        # Retention rate should be less than 100%
        assert manifest["retention_rate"] < 1.0

        # Each missing object should have a disposition slot
        dispositions = manifest["dispositions"]["omitted_objects"]
        assert len(dispositions) == missing_count

        for disposition in dispositions:
            assert "hash" in disposition
            assert "type" in disposition
            assert "reason" in disposition
            assert disposition["reason"] is None  # Awaiting human input
            assert disposition["human_approved"] is False


def test_draft_no_manifest_degrades_gracefully():
    """If source manifest doesn't exist, draft should still work without correspondence tracking."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        snapshot_dir = tmpdir / "snapshot"
        snapshot_dir.mkdir()

        from humanvoice.commands.draft_command import _load_source_manifest, _prepare_section_evidence

        # No manifest exists
        loaded_manifest = _load_source_manifest(snapshot_dir)
        assert loaded_manifest is None

        # Prepare evidence without manifest
        section = {"title": "Test", "source_start_line": 1, "source_end_line": 100}
        evidence_text, protected_objects = _prepare_section_evidence(
            section, "", loaded_manifest, [], snapshot_dir
        )

        # Should return empty protected objects, but not crash
        assert protected_objects == []
        assert evidence_text == "[No evidence available]"
