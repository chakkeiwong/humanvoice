"""
Phase 3 gate enforcement tests: exercise check_protected_manifest_correspondence directly.

The Phase 0 tests in test_correspondence_gates.py assert arithmetic about thresholds
without calling the gate. That validates the plan's reasoning, not the implementation:
a placeholder that recomputes 50/100 == 0.5 passes whether or not the gate exists.

These tests construct fixtures on disk and call the real gate, asserting on the
returned block reason. Each of the 7 fail-closed checks gets a test that fails if
the gate stops enforcing it.
"""

import json
from pathlib import Path

import pytest

from humanvoice.commands.release_command import check_protected_manifest_correspondence
from humanvoice.protected_objects import extract_protected_objects, _compute_file_hash


SOURCE_TEX = r"""\documentclass{article}
\begin{document}
\section{Intro}\label{sec:intro}

\begin{equation}\label{eq:one}
E = mc^2
\end{equation}

\begin{equation}\label{eq:two}
F = ma
\end{equation}

\begin{equation}\label{eq:three}
a^2 + b^2 = c^2
\end{equation}

\end{document}
"""


def _build_snapshot(tmp_path, source_text=SOURCE_TEX):
    """Create a snapshot with source + extracted source manifest. Returns (snapshot, manifest)."""
    snapshot = tmp_path / "snapshot"
    (snapshot / ".humanvoice" / "protected_objects").mkdir(parents=True)
    (snapshot / ".humanvoice" / "runs").mkdir(parents=True)

    source = snapshot / "source.tex"
    source.write_text(source_text)

    manifest = extract_protected_objects(source, snapshot_id="gate-test")
    data = manifest.to_json()
    # Store source_file as snapshot-relative so the gate's staleness check can resolve it
    data["source_file"] = "source.tex"
    (snapshot / ".humanvoice" / "protected_objects" / "source_manifest.json").write_text(
        json.dumps(data, indent=2)
    )
    return snapshot, data


def _all_objects(manifest_data):
    objs = []
    for key in ("equations", "labels", "citations", "displaymath", "tables"):
        objs.extend(manifest_data.get(key, []))
    return objs


def _write_draft_manifest(snapshot, preserved, missing, dispositions=None, run="run-1"):
    """Write a draft correspondence manifest with the given preserved/missing objects."""
    run_dir = snapshot / ".humanvoice" / "runs" / run
    run_dir.mkdir(parents=True, exist_ok=True)

    if dispositions is None:
        # Default: every missing object approved, so disposition check passes and
        # the test isolates whatever check it is actually targeting.
        dispositions = [
            {
                "hash": o["hash"],
                "type": o.get("type", "equation"),
                "reason": "not_relevant",
                "human_approved": True,
                "approver": "test@example.com",
                "approval_timestamp": "2026-09-01T00:00:00Z",
            }
            for o in missing
        ]

    record = {
        "record_type": "DraftCorrespondenceManifest",
        "schema_version": "HV-SCHEMA-1.0",
        "section_title": "Section",
        "parent_artifact_hash": "irrelevant-for-these-checks",
        "extraction_timestamp": "2026-09-01T00:00:00Z",
        "correspondence_to_source": {
            "preserved": [
                {"type": o.get("type", "equation"), "hash": o["hash"], "content": o.get("content", "")}
                for o in preserved
            ],
            "missing": [
                {"type": o.get("type", "equation"), "hash": o["hash"], "content": o.get("content", "")}
                for o in missing
            ],
            "added": [],
        },
        "retention_rate": len(preserved) / (len(preserved) + len(missing)) if (preserved or missing) else 1.0,
        "dispositions": {"omitted_objects": dispositions},
    }
    (run_dir / "draft_correspondence_section.json").write_text(json.dumps(record, indent=2))


# --- Check 1: source manifest must exist -----------------------------------


def test_gate_blocks_when_source_manifest_absent(tmp_path):
    snapshot = tmp_path / "snapshot"
    (snapshot / ".humanvoice" / "runs").mkdir(parents=True)

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None
    assert block["reason"] == "missing_source_manifest"


def test_gate_blocks_on_corrupt_source_manifest(tmp_path):
    snapshot, _ = _build_snapshot(tmp_path)
    (snapshot / ".humanvoice" / "protected_objects" / "source_manifest.json").write_text("{not json")

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None
    assert block["reason"] == "corrupt_source_manifest"


# --- Check 2: staleness ----------------------------------------------------


def test_gate_blocks_when_source_modified_after_extraction(tmp_path):
    snapshot, data = _build_snapshot(tmp_path)
    objs = _all_objects(data)
    _write_draft_manifest(snapshot, preserved=objs, missing=[])

    # Gate passes before mutation
    assert check_protected_manifest_correspondence(snapshot) is None

    # Mutate the source after the manifest was written
    (snapshot / "source.tex").write_text(SOURCE_TEX.replace("E = mc^2", "E = mc^3"))

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None, "Mutated source must not pass a correspondence gate"
    assert block["reason"] == "stale_source_manifest"


# --- Check 3: draft manifests must exist -----------------------------------


def test_gate_blocks_when_no_runs_directory(tmp_path):
    snapshot, _ = _build_snapshot(tmp_path)
    # Remove the runs dir entirely
    (snapshot / ".humanvoice" / "runs").rmdir()

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None
    assert block["reason"] == "no_runs_directory"


def test_gate_blocks_when_runs_exist_but_no_draft_manifests(tmp_path):
    """The 2026-08-29 fail-open shape: runs recorded, correspondence never measured."""
    snapshot, _ = _build_snapshot(tmp_path)
    run_dir = snapshot / ".humanvoice" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    # A run record that is not a correspondence manifest
    (run_dir / "runtime_manifest_section.json").write_text(json.dumps({"record_type": "RuntimeManifest"}))

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None, "Runs present but correspondence unmeasured must block"
    assert block["reason"] == "no_draft_manifests"


# --- Check 4: per-object identity, not counts ------------------------------


def test_gate_passes_when_all_objects_preserved(tmp_path):
    snapshot, data = _build_snapshot(tmp_path)
    _write_draft_manifest(snapshot, preserved=_all_objects(data), missing=[])

    assert check_protected_manifest_correspondence(snapshot) is None


def test_gate_blocks_on_majority_object_loss(tmp_path):
    snapshot, data = _build_snapshot(tmp_path)
    objs = _all_objects(data)
    keep = objs[: max(1, len(objs) // 2)]
    drop = objs[len(keep):]

    _write_draft_manifest(snapshot, preserved=keep, missing=drop)

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None
    assert block["reason"] == "low_identity_preservation"
    assert block["identity_preservation_rate"] < 0.95
    assert block["preserved_count"] == len(keep)


def test_gate_blocks_when_count_matches_but_identities_are_wrong(tmp_path):
    """
    The count-hiding-substitution case: the draft reports as many preserved
    objects as the source has, but the hashes belong to different objects.
    A count-based gate passes this; an identity-based gate must not.
    """
    snapshot, data = _build_snapshot(tmp_path)
    objs = _all_objects(data)

    impostors = [
        {"type": o.get("type", "equation"), "hash": f"deadbeef{i:08d}", "content": "substituted"}
        for i, o in enumerate(objs)
    ]
    # Same number of "preserved" entries as the source has objects, zero real overlap.
    _write_draft_manifest(snapshot, preserved=impostors, missing=[])

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None, "Matching counts with wrong hashes must block"
    assert block["reason"] == "low_identity_preservation"
    assert block["preserved_count"] == 0
    assert block["total_source_objects"] == len(objs)


# --- Check 5: dispositions require human approval --------------------------


def test_gate_blocks_on_unapproved_disposition(tmp_path):
    snapshot, data = _build_snapshot(tmp_path)
    objs = _all_objects(data)
    keep, drop = objs[:-1], objs[-1:]

    _write_draft_manifest(
        snapshot,
        preserved=keep,
        missing=drop,
        dispositions=[
            {
                "hash": drop[0]["hash"],
                "type": drop[0].get("type", "equation"),
                "reason": "not_relevant",
                "human_approved": False,  # model-authored, never reviewed
                "approver": None,
                "approval_timestamp": None,
            }
        ],
    )

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None, "An unapproved omission must block release"
    assert block["reason"] == "unapproved_dispositions"
    assert block["unapproved"][0]["hash"] == drop[0]["hash"]


def test_unapproved_disposition_outranks_threshold_pass(tmp_path):
    """
    A single unapproved omission blocks even when retention is high enough to
    clear the 95% threshold. Approval is not a tie-breaker for borderline runs;
    it is required for every omission.
    """
    many_equations = "\n".join(
        rf"\begin{{equation}}\label{{eq:{i:03d}}}x_{{{i}}} = {i}\end{{equation}}"
        for i in range(60)
    )
    source_text = "\\documentclass{article}\n\\begin{document}\n" + many_equations + "\n\\end{document}\n"

    snapshot, data = _build_snapshot(tmp_path, source_text=source_text)
    objs = _all_objects(data)
    keep, drop = objs[:-1], objs[-1:]

    retention = len(keep) / len(objs)
    assert retention >= 0.95, f"fixture must clear the draft threshold, got {retention:.3f}"

    _write_draft_manifest(
        snapshot,
        preserved=keep,
        missing=drop,
        dispositions=[{
            "hash": drop[0]["hash"],
            "type": drop[0].get("type", "equation"),
            "reason": "merged",
            "human_approved": False,
        }],
    )

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None
    assert block["reason"] == "unapproved_dispositions"


def test_gate_passes_when_omission_is_human_approved(tmp_path):
    """An approved omission is the documented escape hatch and must clear the gate."""
    many_equations = "\n".join(
        rf"\begin{{equation}}\label{{eq:{i:03d}}}x_{{{i}}} = {i}\end{{equation}}"
        for i in range(60)
    )
    source_text = "\\documentclass{article}\n\\begin{document}\n" + many_equations + "\n\\end{document}\n"

    snapshot, data = _build_snapshot(tmp_path, source_text=source_text)
    objs = _all_objects(data)
    keep, drop = objs[:-1], objs[-1:]

    _write_draft_manifest(
        snapshot,
        preserved=keep,
        missing=drop,
        dispositions=[{
            "hash": drop[0]["hash"],
            "type": drop[0].get("type", "equation"),
            "reason": "superseded",
            "human_approved": True,
            "approver": "author@example.com",
            "approval_timestamp": "2026-09-01T00:00:00Z",
        }],
    )

    assert check_protected_manifest_correspondence(snapshot) is None


# --- Check 6: parser agreement --------------------------------------------


def test_gate_blocks_on_low_parser_agreement(tmp_path):
    snapshot, data = _build_snapshot(tmp_path)
    _write_draft_manifest(snapshot, preserved=_all_objects(data), missing=[])

    manifest_path = snapshot / ".humanvoice" / "protected_objects" / "source_manifest.json"
    data["parser_agreement_score"] = 0.42
    manifest_path.write_text(json.dumps(data, indent=2))

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None, "Disagreeing parsers must block rather than pick a winner"
    assert block["reason"] == "low_parser_agreement"


def test_gate_blocks_when_parser_agreement_field_absent(tmp_path):
    """A manifest with no agreement score has not demonstrated agreement."""
    snapshot, data = _build_snapshot(tmp_path)
    _write_draft_manifest(snapshot, preserved=_all_objects(data), missing=[])

    manifest_path = snapshot / ".humanvoice" / "protected_objects" / "source_manifest.json"
    data.pop("parser_agreement_score", None)
    manifest_path.write_text(json.dumps(data, indent=2))

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None
    assert block["reason"] == "low_parser_agreement"


# --- Check 7: assembly correspondence -------------------------------------


def test_gate_blocks_when_assembled_output_has_no_correspondence_manifest(tmp_path):
    snapshot, data = _build_snapshot(tmp_path)
    _write_draft_manifest(snapshot, preserved=_all_objects(data), missing=[])

    assembled = snapshot / ".humanvoice" / "revisions" / "assembled"
    assembled.mkdir(parents=True)
    (assembled / "assembled.tex").write_text(r"\documentclass{article}\begin{document}x\end{document}")

    block = check_protected_manifest_correspondence(snapshot)

    assert block is not None, "Assembled output with unmeasured correspondence must block"
    assert block["reason"] == "no_assembly_manifest"


def test_gate_passes_when_assembly_correspondence_present(tmp_path):
    snapshot, data = _build_snapshot(tmp_path)
    _write_draft_manifest(snapshot, preserved=_all_objects(data), missing=[])

    assembled = snapshot / ".humanvoice" / "revisions" / "assembled"
    assembled.mkdir(parents=True)
    (assembled / "assembled.tex").write_text(r"\documentclass{article}\begin{document}x\end{document}")
    (assembled / "assembly_correspondence_doc.json").write_text(json.dumps({
        "record_type": "AssemblyCorrespondenceManifest",
        "retention_vs_drafts": 1.0,
        "retention_vs_source": 1.0,
        "retention_rate": 1.0,
        "correspondence_to_source": {"preserved": [], "missing": [], "added": []},
        "dispositions": {"omitted_objects": []},
    }))

    assert check_protected_manifest_correspondence(snapshot) is None
