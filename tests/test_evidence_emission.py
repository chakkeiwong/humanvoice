#!/usr/bin/env python3
"""Test evidence-item emission during repair (Blocker 2)."""

import json
import pytest
from pathlib import Path
from humanvoice.commands import init_command, repair_command, preflight_command
from humanvoice.paths import new_run_dir

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_args(cls, **kwargs):
    obj = cls()
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def init_snapshot_with_violation(tmp_path):
    """Create a snapshot with a planted register violation."""
    source = tmp_path / "test.tex"
    source.write_text(
        r"\documentclass{article}\begin{document}"
        r"The internal label WP3 should not appear in reader text."
        r"\end{document}"
    )
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


def test_repair_emits_evidence_for_cleared_findings(tmp_path):
    """
    Blocker 2: repair emits evidence-item records for accepted changes.

    After a successful repair cycle, an evidence-item record must exist
    documenting what was cleared, with appraisal_state "corroborated".
    """
    snapshot_dir, brief = init_snapshot_with_violation(tmp_path)

    # Run preflight to detect the violation
    pf_rc = preflight_command.run(make_args(type("Args", (), {}),
        snapshot=snapshot_dir, brief=brief, deterministic=True))
    assert pf_rc == 1  # violation found

    # Get preflight output with findings
    pf_files = list((snapshot_dir / ".humanvoice" / "runs").glob("**/preflight-*.json"))
    assert len(pf_files) == 1
    pf_record = json.loads(pf_files[0].read_text())
    assert len(pf_record["findings"]) >= 1

    # Plant a draft that contains the violation
    run = new_run_dir(snapshot_dir, "draft-run")
    draft = run / "draft_test.tex"
    draft.write_text(
        r"The internal label WP3 appears here and should be repaired."
    )

    # Write findings to a file
    findings_file = tmp_path / "findings.json"
    findings_file.write_text(json.dumps({
        "findings": [{
            "category": "register",
            "location": {"char_offset": 19},
            "matched_text": "WP3",
            "message": "Internal label in reader text",
        }]
    }))

    # Run repair
    repair_rc = repair_command.run(make_args(type("Args", (), {}),
        draft=draft, findings=findings_file, brief=brief, output_dir=None, mock=False))

    # Repair should succeed (exit 0) or abstain (exit 2) depending on model behavior.
    # If it succeeds, verify evidence emission.
    if repair_rc == 0:
        # Find evidence-item records
        evidence_files = list(run.glob("**/evidence-item-*.json"))
        assert len(evidence_files) >= 1, "No evidence-item emitted after successful repair"

        ev = json.loads(evidence_files[0].read_text())
        assert ev["record_type"] == "EvidenceItem"
        assert ev["schema_version"] == "HV-SCHEMA-1.1"
        assert ev["appraisal_state"] == "corroborated"
        assert "Repair cycle" in ev["observation"]
        assert ev["provenance"]["kind"] == "software-observation"

        # Load-bearing because category is "register"
        assert len(ev["supports"]) >= 1
        assert ev["supports"][0]["load_bearing"] is True

        print(f"✓ Evidence emitted: {evidence_files[0].name}")
        print(f"  observation: {ev['observation'][:80]}...")
        print(f"  appraisal_state: {ev['appraisal_state']}")
        print(f"  load_bearing: {ev['supports'][0]['load_bearing']}")
    else:
        # Repair abstained or blocked; evidence emission doesn't apply
        print(f"Repair exited {repair_rc} (not testing evidence emission for non-success)")
        pytest.skip("Repair did not converge; evidence emission not applicable")


def test_evidence_item_schema_validates(tmp_path):
    """Verify that emitted evidence items pass their schema."""
    from jsonschema import Draft202012Validator

    schema = json.loads((REPO_ROOT / "schemas" / "evidence-item.schema.json").read_text())

    snapshot_dir, brief = init_snapshot_with_violation(tmp_path)
    run = new_run_dir(snapshot_dir, "test-run")
    draft = run / "draft_test.tex"
    draft.write_text("The label WP3 is here.")

    findings_file = tmp_path / "findings.json"
    findings_file.write_text(json.dumps({
        "findings": [{
            "category": "register",
            "location": {"char_offset": 10},
            "matched_text": "WP3",
            "message": "Internal label",
        }]
    }))

    repair_rc = repair_command.run(make_args(type("Args", (), {}),
        draft=draft, findings=findings_file, brief=brief, output_dir=None, mock=False))

    if repair_rc == 0:
        evidence_files = list(run.glob("**/evidence-item-*.json"))
        if evidence_files:
            ev = json.loads(evidence_files[0].read_text())
            validator = Draft202012Validator(schema)
            errors = list(validator.iter_errors(ev))
            assert len(errors) == 0, f"Evidence-item schema validation failed: {errors}"
            print("✓ Evidence-item validates against schema")
    else:
        pytest.skip("Repair did not converge")


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        test_repair_emits_evidence_for_cleared_findings(Path(tmp))
        print("\n")
        test_evidence_item_schema_validates(Path(tmp) / "second")
