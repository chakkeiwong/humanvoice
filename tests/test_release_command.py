#!/usr/bin/env python3
"""
Tests for hv release command.

Release gates:
  - Never-except: unresolved protected-object correspondence, unparsed brief promises,
    missing critical evidence, unauthorized transmission, broken build
  - Ordinary: unresolved author choice from repair oscillation/cycle-limit

Exit codes:
  0 - released (all gates pass)
  1 - deterministic gate failure
  2 - abstention
  3 - invalid input
"""

import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from humanvoice.commands import init_command, release_command

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_SCHEMA = json.loads(
    (REPO_ROOT / "schemas" / "release-decision.schema.json").read_text()
)

BRIEF = {
    "record_type": "AuthoringBrief",
    "reader": "domain-expert",
    "reader_role": "technical reviewer",
    "decision_type": "technical-accept-reject",
    "time_available_minutes": 45,
    "prior_knowledge": "familiar",
    "success_criteria": "Can assess feasibility",
}


def make_args(cls, **kwargs):
    """Helper to create args object with attributes."""
    obj = cls()
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def init_snapshot(tmp_path, brief_overrides=None):
    """Create a source file, brief, and initialized snapshot. Returns (snapshot, brief)."""
    source = tmp_path / "test.tex"
    source.write_text(r"\documentclass{article}\begin{document}Test\end{document}")

    brief_doc = dict(BRIEF)
    if brief_overrides:
        brief_doc.update(brief_overrides)
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps(brief_doc))

    snapshot_dir = tmp_path / "snapshot"
    rc = init_command.run(make_args(type("Args", (), {}),
        source=source, brief=brief, output=snapshot_dir))
    assert rc == 0

    # A releasable snapshot has been assembled, and assembly always records its
    # gap list. Empty means every blueprint section was found. Without this the
    # assembly_gaps gate blocks -- correctly, since an unassembled snapshot has
    # no document to publish -- so these fixtures record a complete assembly.
    write_assembly_gaps(snapshot_dir, [])

    return snapshot_dir, brief


def write_assembly_gaps(snapshot_dir, gaps):
    """Write the assembly gap record that the assembly_gaps release gate reads."""
    assembled_dir = snapshot_dir / ".humanvoice" / "revisions" / "assembled"
    assembled_dir.mkdir(parents=True, exist_ok=True)
    (assembled_dir / "assembly_gaps.json").write_text(json.dumps(gaps))
    return assembled_dir / "assembly_gaps.json"


def release(snapshot_dir, brief, output=None):
    """Call release_command.run() with proper brief path handling."""
    # If brief is a dict, write it to a temp file
    if isinstance(brief, dict):
        brief_path = snapshot_dir.parent / "brief.json"
        brief_path.write_text(json.dumps(brief))
    else:
        brief_path = brief

    return release_command.run(make_args(type("Args", (), {}),
        snapshot=snapshot_dir, brief=brief_path, output=output))


def read_decision(snapshot_dir, output=None):
    base = output if output else snapshot_dir / "release"
    return json.loads((base / "release_decision.json").read_text())


def write_run_record(snapshot_dir, filename, record, run_name="test-run"):
    """Write a record under .humanvoice/runs/<run_name>/."""
    run_dir = snapshot_dir / ".humanvoice" / "runs" / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / filename).write_text(json.dumps(record))
    return run_dir / filename


def setup_minimal_runs(snapshot_dir):
    """
    Write minimal run records so release gates don't block on absent records.

    After the 2026-08-29 gate fixes, four never-except gates block when no
    runs directory exists (they distinguish "no work done" from "work done and
    clean"). This helper plants a passing preflight record so tests of other
    gate logic can proceed.

    After Blocker 3 (transmission tracking), also need to initialize an empty
    transmission log in the manifest so the unauthorized_transmission gate passes.

    After Phase 3 (fail-closed correspondence), the gate blocks when draft
    manifests are missing. For zero-object sources, synthesize a minimal
    draft manifest with 100% retention (nothing to preserve).

    The document_assembly gate (from prior sessions) also blocks when no
    assembly exists. Synthesize a minimal assembled document.
    """
    # Initialize transmission log first (Blocker 3)
    manifest_path = snapshot_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            if "transmission_log" not in manifest:
                manifest["transmission_log"] = []
                manifest_path.write_text(json.dumps(manifest, indent=2))
        except Exception as e:
            print(f"Warning: failed to initialize transmission_log: {e}")

    write_run_record(snapshot_dir, "preflight-20260101-000000.json", {
        "record_type": "PreflightRun",
        "preflight_id": "preflight-20260101-000000",
        "mode": "deterministic",
        "snapshot_id": "test",
        "checked_at": "2026-01-01T00:00:00+00:00",
        "status": "pass",
        "exit_code": 0,
        "findings": [],
        "deterministic_gate": "pass",
    })

    # Phase 3: Synthesize minimal draft correspondence manifest for zero-object sources.
    # The gate blocks when draft manifests are missing, even for empty sources.
    # This is correct: zero objects may indicate parser failure, and the gate must
    # verify correspondence was measured, not silently skip it.
    source_manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    if source_manifest_path.exists():
        try:
            source_manifest = json.loads(source_manifest_path.read_text())
            total_count = source_manifest.get("total_count", 0)
            source_hash = source_manifest.get("source_file_hash", "")

            # Emit one draft correspondence manifest showing 100% retention (nothing to preserve)
            write_run_record(snapshot_dir, "draft_correspondence_test_section.json", {
                "record_type": "DraftCorrespondenceManifest",
                "schema_version": "HV-SCHEMA-1.0",
                "section_title": "Test Section",
                "parent_artifact_hash": source_hash,
                "extraction_timestamp": "2026-01-01T00:00:00Z",
                "correspondence_to_source": {
                    "preserved": [],
                    "missing": [],
                    "added": [],
                },
                "retention_rate": 1.0 if total_count == 0 else 0.0,
                "dispositions": {
                    "omitted_objects": []
                }
            })
        except Exception as e:
            print(f"Warning: failed to synthesize draft manifest: {e}")

    # Synthesize minimal assembly (from prior sessions, not Phase 3)
    assembled_dir = snapshot_dir / ".humanvoice" / "revisions" / "assembled"
    assembled_dir.mkdir(parents=True, exist_ok=True)

    assembled_file = assembled_dir / "assembled.tex"
    assembled_file.write_text(r"\documentclass{article}\begin{document}Test assembled\end{document}")

    assembly_manifest = {
        "record_type": "AssemblyManifest",
        "assembled_at": "2026-01-01T00:00:00Z",
        "assembled_file": str(assembled_file.relative_to(snapshot_dir)),
        "sections": [{"section_index": 0, "title": "Test", "source": "test.tex", "word_count": 2}],
        "total_word_count": 2,
    }
    (assembled_dir / "assembly_manifest.json").write_text(json.dumps(assembly_manifest, indent=2))

    # Assembly correspondence manifest (Phase 3, check 7)
    if source_manifest_path.exists():
        try:
            source_manifest = json.loads(source_manifest_path.read_text())
            source_hash = source_manifest.get("source_file_hash", "")

            (assembled_dir / "assembly_correspondence_test.json").write_text(json.dumps({
                "record_type": "AssemblyCorrespondenceManifest",
                "schema_version": "HV-SCHEMA-1.0",
                "parent_artifact_hash": source_hash,
                "extraction_timestamp": "2026-01-01T00:00:00Z",
                "correspondence_to_source": {
                    "preserved": [],
                    "missing": [],
                    "added": [],
                },
                "retention_vs_drafts": 1.0,
                "retention_vs_source": 1.0,
                "retention_rate": 1.0,
                "dispositions": {"omitted_objects": []}
            }, indent=2))
        except Exception:
            pass

    # The runs directory now exists and holds a passing preflight, so the
    # four block-on-absent gates will pass unless the test plants a violation.



class TestReleaseGates:
    """Test release gate logic."""

    def test_clean_snapshot_releases_and_record_validates(self, tmp_path):
        """A snapshot with no gate failures releases successfully and emits valid record."""
        snapshot_dir, brief = init_snapshot(tmp_path)
        setup_minimal_runs(snapshot_dir)
        rc = release(snapshot_dir, brief)
        assert rc == 0

        decision = read_decision(snapshot_dir)
        assert decision["status"] == "released"
        assert decision["gate_results"]["author_convergence"] == "pass"
        assert decision["packet_hash"]

        # Emitted record must pass its own schema
        errs = list(Draft202012Validator(RELEASE_SCHEMA).iter_errors(decision))
        assert errs == [], f"Schema errors: {[(list(e.path), e.message) for e in errs]}"

    def test_unresolved_author_choice_blocks_release(self, tmp_path):
        """Unresolved author choice from repair blocks release (exit 1)."""
        snapshot_dir, brief = init_snapshot(tmp_path)

        # Plant unresolved marker in revisions/
        run_dir = snapshot_dir / ".humanvoice" / "runs" / "test-run"
        revisions_dir = run_dir / "revisions"
        revisions_dir.mkdir(parents=True)
        (revisions_dir / "unresolved_author_choice.json").write_text(json.dumps({
            "stop_reason": "cycle_limit",
            "cycle": 3,
            "finding_signature": "sig-abc",
            "message": "Repair did not converge",
        }))

        rc = release(snapshot_dir, brief)
        assert rc == 1

        decision = read_decision(snapshot_dir)
        assert decision["status"] == "blocked"
        assert decision["gate_results"]["author_convergence"] == "blocked"
        assert "author_convergence" in decision["unresolved_risks"]

    def test_superseded_author_choice_does_not_block(self, tmp_path):
        """Superseded author choice (resolved in later cycle) does not block."""
        snapshot_dir, brief = init_snapshot(tmp_path)
        setup_minimal_runs(snapshot_dir)

        # Plant superseded (not unresolved) marker
        run_dir = snapshot_dir / ".humanvoice" / "runs" / "test-run"
        revisions_dir = run_dir / "revisions"
        revisions_dir.mkdir(parents=True)
        (revisions_dir / "superseded_author_choice.json").write_text(json.dumps({
            "stop_reason": "cycle_limit",
            "cycle": 2,
            "resolution": "Converged in cycle 3",
        }))

        rc = release(snapshot_dir, brief)
        assert rc == 0

        decision = read_decision(snapshot_dir)
        assert decision["status"] == "released"

    def test_unresolved_protected_correspondence_blocks_never_except(self, tmp_path):
        """Unresolved protected object correspondence is a never-except block."""
        snapshot_dir, brief = init_snapshot(tmp_path)

        # Plant protected-manifest with unresolved correspondence
        protected_manifest = {
            "record_type": "ProtectedManifest",
            "schema_version": "2026-08-25",
            "record_id": "pm-123",
            "run_id": "test-run",
            "created_at": "2026-08-26T12:00:00Z",
            "source_hash": "abc123",
            "objects": [
                {
                    "object_id": "eq-1",
                    "object_type": "equation",
                    "raw_form": "E=mc^2",
                    "normalized_form": "E=mc^2",
                    "location": {"line": 10},
                    "comparison": {
                        "status": "unresolved",
                        "unresolved_count": 1,
                        "details": "Author has not decided"
                    }
                }
            ]
        }
        write_run_record(snapshot_dir, "protected-manifest-000.json", protected_manifest)

        rc = release(snapshot_dir, brief)
        assert rc == 1

        decision = read_decision(snapshot_dir)
        assert decision["status"] == "blocked"
        assert decision["gate_results"]["protected_correspondence"] == "blocked"

        # Blocks array contains exception objects
        blocks = [b for b in decision["exceptions"]
                  if b.get("gate") == "protected_correspondence"]
        assert len(blocks) == 1
        assert blocks[0]["never_except"] is True

    def test_unparsed_brief_promise_blocks_never_except(self, tmp_path):
        """Brief promises object type but parser found none → never-except block."""
        snapshot_dir, _ = init_snapshot(tmp_path)

        # Brief expects equations
        brief_with_promise = BRIEF.copy()
        brief_with_promise["expected_objects"] = {"equation": 3}

        # Plant protected-manifest with NO equations parsed
        protected_manifest = {
            "record_type": "ProtectedManifest",
            "schema_version": "2026-08-25",
            "record_id": "pm-456",
            "run_id": "test-run",
            "created_at": "2026-08-26T12:00:00Z",
            "source_hash": "def456",
            "objects": [
                {
                    "object_id": "cite-1",
                    "object_type": "citation",
                    "raw_form": "\\cite{foo}",
                    "normalized_form": "foo",
                    "location": {"line": 5}
                }
            ]
        }
        write_run_record(snapshot_dir, "protected-manifest-000.json", protected_manifest)

        rc = release(snapshot_dir, brief_with_promise)
        assert rc == 1

        decision = read_decision(snapshot_dir)
        assert decision["status"] == "blocked"
        assert decision["gate_results"]["brief_parsing_promises"] == "blocked"

        blocks = [b for b in decision["exceptions"]
                  if b.get("gate") == "brief_parsing_promises"]
        assert len(blocks) == 1
        assert blocks[0]["never_except"] is True

    def test_load_bearing_evidence_gap_blocks_never_except(self, tmp_path):
        """Load-bearing claim with insufficient evidence is never-except block."""
        snapshot_dir, brief = init_snapshot(tmp_path)

        # Plant evidence-item with load_bearing=true, appraisal_state=insufficient
        evidence_item = {
            "record_type": "EvidenceItem",
            "schema_version": "2026-08-25",
            "record_id": "ev-789",
            "run_id": "test-run",
            "created_at": "2026-08-26T12:00:00Z",
            "file_path": "data.csv",
            "file_hash": "hash123",
            "evidence_type": "dataset",
            "supports": [
                {
                    "claim_id": "claim-1",
                    "relationship": "direct",
                    "load_bearing": True
                }
            ],
            "appraisal_state": "insufficient",
            "appraisal_notes": "Sample size too small"
        }
        write_run_record(snapshot_dir, "evidence-item-000.json", evidence_item)

        rc = release(snapshot_dir, brief)
        assert rc == 1

        decision = read_decision(snapshot_dir)
        assert decision["status"] == "blocked"
        assert decision["gate_results"]["evidence_sufficiency"] == "blocked"

        blocks = [b for b in decision["exceptions"]
                  if b.get("gate") == "evidence_sufficiency"]
        assert len(blocks) == 1
        assert blocks[0]["never_except"] is True

    def test_reader_packet_strips_internal_ids(self, tmp_path):
        """Reader packet context contains only the four allowed fields."""
        snapshot_dir, brief = init_snapshot(tmp_path)
        setup_minimal_runs(snapshot_dir)
        rc = release(snapshot_dir, brief)
        assert rc == 0

        packet_dir = snapshot_dir / "release" / "packet"
        reader_context = json.loads((packet_dir / "reader_context.json").read_text())

        # Only these four fields allowed
        assert set(reader_context.keys()) == {
            "reader", "decision_type", "time_available_minutes", "success_criteria"
        }
        assert "record_id" not in reader_context
        assert "run_id" not in reader_context
        assert "finding_id" not in reader_context
        assert "phase" not in reader_context


class TestReleaseValidation:
    """Test input validation."""

    def test_missing_snapshot_returns_exit_3(self, tmp_path):
        """Nonexistent snapshot directory returns exit 3 (invalid input)."""
        snapshot_dir = tmp_path / "nonexistent"
        brief = BRIEF.copy()
        rc = release(snapshot_dir, brief)
        assert rc == 3

    def test_uninitialized_snapshot_returns_exit_3(self, tmp_path):
        """Snapshot directory without manifest.json returns exit 3."""
        snapshot_dir = tmp_path / "empty"
        snapshot_dir.mkdir()

        rc = release(snapshot_dir, BRIEF)
        assert rc == 3

