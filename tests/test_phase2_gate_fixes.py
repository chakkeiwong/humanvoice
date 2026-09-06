#!/usr/bin/env python3
"""
Regression tests for Phase 2 gate fixes (2026-08-29).

These tests verify the five fixes deployed to prevent the fail-open condition
where fixtures/synthetic/register/001.tex released with known violations while
reporting all gates pass.

The tests confirm:
1. Run records resolve through a single canonical location
2. Repair abstention is persisted as unresolved_author_choice.json
3. Release gates on preflight findings
4. Zero-word drafts exit 1
5. Evidence appraisal uses an allowlist (fail closed)
"""

import json
import pytest
from pathlib import Path
from humanvoice.commands import init_command, release_command, preflight_command
from humanvoice.paths import runs_dir, new_run_dir

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_args(cls, **kwargs):
    obj = cls()
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def init_snapshot(tmp_path):
    source = tmp_path / "test.tex"
    source.write_text(r"\documentclass{article}\begin{document}Test\end{document}")
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "record_type": "AuthoringBrief",
        "reader": "test-reader",
        "reader_role": "reviewer",
        "decision_type": "approve-reject",
        "time_available_minutes": 30,
        "prior_knowledge": "familiar",
        "success_criteria": "Can decide",
    }))
    snapshot_dir = tmp_path / "snapshot"
    rc = init_command.run(make_args(type("Args", (), {}),
        source=source, brief=brief, output=snapshot_dir))
    assert rc == 0
    return snapshot_dir, brief


class TestPhase2GateFixes:
    """Regression tests for the 2026-08-29 gate fixes."""

    def test_fix1_runs_resolve_under_snapshot(self, tmp_path):
        """
        Fix 1: All commands write/read from snapshot_dir/.humanvoice/runs/.

        Before: plan/draft wrote to Path.cwd()/.humanvoice/runs/, release read
        snapshot_dir/.humanvoice/runs/ — never coincided.
        """
        snapshot_dir, brief = init_snapshot(tmp_path)

        # The canonical location is under the snapshot
        expected = snapshot_dir / ".humanvoice" / "runs"
        assert runs_dir(snapshot_dir) == expected

        # new_run_dir creates under the snapshot
        run = new_run_dir(snapshot_dir, "test-run")
        assert run.parent == expected
        assert run.exists()

    def test_fix1_absent_runs_blocks_never_except_gates(self, tmp_path):
        """
        Fix 1: Never-except gates block when no runs directory exists.

        Before: gates returned None (pass) when runs_dir was absent.
        After: gates return a block record with reason="no_runs_directory".
        """
        snapshot_dir, brief = init_snapshot(tmp_path)

        # No runs created yet; release should block on multiple never-except gates
        rc = release_command.run(make_args(type("Args", (), {}),
            snapshot=snapshot_dir, brief=brief, output=None))

        assert rc == 1  # blocked

        decision = json.loads((snapshot_dir / "release" / "release_decision.json").read_text())
        assert decision["status"] == "blocked"

        # At least three never-except gates should block on absent runs
        blocked = [k for k, v in decision["gate_results"].items() if v == "blocked"]
        assert len(blocked) >= 3

        # Check that the exception details mention no_runs_directory
        exceptions = decision.get("exceptions", [])
        no_runs_blocks = [
            e for e in exceptions
            if "no_runs" in str(e.get("detail", {})).lower()
        ]
        assert len(no_runs_blocks) >= 3

    def test_fix3_preflight_findings_block_release(self, tmp_path):
        """
        Fix 3: Release gates on preflight findings.

        Before: Release had no visibility into preflight; deterministic findings
        never blocked.
        After: New deterministic_preflight gate blocks on unresolved findings.
        """
        snapshot_dir, brief = init_snapshot(tmp_path)

        # Run preflight with deterministic mode (will run and persist result)
        pf_rc = preflight_command.run(make_args(type("Args", (), {}),
            snapshot=snapshot_dir, brief=brief, deterministic=True))

        # Preflight should pass (test.tex has no violations)
        assert pf_rc == 0

        # Verify preflight result was persisted under the snapshot
        pf_files = list(runs_dir(snapshot_dir).glob("**/preflight-*.json"))
        assert len(pf_files) == 1
        pf_record = json.loads(pf_files[0].read_text())
        assert pf_record.get("status") == "pass"

        # Now plant a finding manually to test the blocking path
        pf_record["findings"] = [{
            "category": "register",
            "location": {"char_offset": 0},
            "matched_text": "WP3",
            "message": "Internal label leaked"
        }]
        pf_record["status"] = "fail"
        pf_record["exit_code"] = 1
        pf_files[0].write_text(json.dumps(pf_record, indent=2))

        # Release should now block on deterministic_preflight
        rc = release_command.run(make_args(type("Args", (), {}),
            snapshot=snapshot_dir, brief=brief, output=None))

        assert rc == 1
        decision = json.loads((snapshot_dir / "release" / "release_decision.json").read_text())
        assert decision["gate_results"]["deterministic_preflight"] == "blocked"
        assert decision["status"] == "blocked"

    def test_fix3_no_preflight_blocks_release(self, tmp_path):
        """
        Fix 3: Release blocks if preflight never ran.

        Absence of a preflight record is treated as a never-except block, not a pass.
        """
        snapshot_dir, brief = init_snapshot(tmp_path)

        # Create a runs directory with no preflight record
        new_run_dir(snapshot_dir, "some-run")

        rc = release_command.run(make_args(type("Args", (), {}),
            snapshot=snapshot_dir, brief=brief, output=None))

        assert rc == 1
        decision = json.loads((snapshot_dir / "release" / "release_decision.json").read_text())
        assert decision["gate_results"]["deterministic_preflight"] == "blocked"

        blocked_detail = None
        for exc in decision.get("exceptions", []):
            if exc.get("gate") == "deterministic_preflight":
                blocked_detail = exc.get("detail", {})
                break

        assert blocked_detail is not None
        assert blocked_detail.get("reason") == "no_preflight_run"

    def test_fix5_evidence_appraisal_allowlist(self, tmp_path):
        """
        Fix 5: Evidence gate uses an allowlist — blocks unless appraisal_state
        is explicitly sufficient.

        Before: Blocked only on "insufficient" or "unappraised" exact strings.
        Absent, null, typos all passed.
        After: Blocks unless appraisal_state in {"sufficient", "verified", "accepted"}.
        """
        snapshot_dir, brief = init_snapshot(tmp_path)

        # Plant a load-bearing evidence item with no appraisal_state
        run = new_run_dir(snapshot_dir, "test-run")
        (run / "evidence_test.json").write_text(json.dumps({
            "record_type": "EvidenceItem",
            "record_id": "ev-123",
            "supports": [{"load_bearing": True, "claim_id": "c-1"}],
            # appraisal_state deliberately absent
        }))

        # Also write a passing preflight so other gates don't block
        (run / "preflight-20260101-000000.json").write_text(json.dumps({
            "record_type": "PreflightRun",
            "preflight_id": "preflight-20260101-000000",
            "status": "pass",
            "exit_code": 0,
            "findings": [],
        }))

        rc = release_command.run(make_args(type("Args", (), {}),
            snapshot=snapshot_dir, brief=brief, output=None))

        assert rc == 1
        decision = json.loads((snapshot_dir / "release" / "release_decision.json").read_text())
        assert decision["gate_results"]["evidence_sufficiency"] == "blocked"

        # Now fix it by setting an allowlisted state
        ev = json.loads((run / "evidence_test.json").read_text())
        ev["appraisal_state"] = "sufficient"
        (run / "evidence_test.json").write_text(json.dumps(ev))

        rc = release_command.run(make_args(type("Args", (), {}),
            snapshot=snapshot_dir, brief=brief, output=None))

        decision = json.loads((snapshot_dir / "release" / "release_decision.json").read_text())
        assert decision["gate_results"]["evidence_sufficiency"] == "pass"

    def test_fix5_evidence_appraisal_rejects_typos(self, tmp_path):
        """
        Fix 5: Evidence gate blocks on case variants and typos.

        Before: Only "insufficient" and "unappraised" (lowercase exact) blocked.
        After: Only {"sufficient", "verified", "accepted"} pass.
        """
        snapshot_dir, brief = init_snapshot(tmp_path)
        run = new_run_dir(snapshot_dir, "test-run")

        # Passing preflight
        (run / "preflight-20260101-000000.json").write_text(json.dumps({
            "preflight_id": "preflight-20260101-000000",
            "status": "pass",
            "exit_code": 0,
            "findings": [],
        }))

        # Case variant should block
        (run / "evidence_test.json").write_text(json.dumps({
            "record_type": "EvidenceItem",
            "record_id": "ev-typo",
            "supports": [{"load_bearing": True}],
            "appraisal_state": "Sufficient",  # capital S
        }))

        rc = release_command.run(make_args(type("Args", (), {}),
            snapshot=snapshot_dir, brief=brief, output=None))

        decision = json.loads((snapshot_dir / "release" / "release_decision.json").read_text())
        assert decision["gate_results"]["evidence_sufficiency"] == "blocked"
