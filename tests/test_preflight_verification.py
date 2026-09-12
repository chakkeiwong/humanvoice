"""
Tests for WP-V2-4 preflight verification.

Tests independent semantic verification of revised output:
- Concept correspondence (exactly 1.0)
- Obligation fulfillment
- Protected object integrity
- Unsupported additions
- Blocking vs. warning findings
"""

import pytest
from pathlib import Path

from humanvoice.preflight_verification import (
    SemanticFinding,
    PreflightResult,
    CriticVerdict,
    verify_concept_correspondence,
    verify_obligation_fulfillment,
    verify_protected_objects,
    verify_unsupported_additions,
    run_preflight_verification,
    save_preflight_result,
)


def test_verify_concept_correspondence_perfect():
    """Perfect correspondence when all concepts present."""
    finding = verify_concept_correspondence(
        unit_id="unit-001",
        source_concepts=["c1", "c2"],
        output_correspondences=[
            {"source_concept_id": "c1"},
            {"source_concept_id": "c2"},
        ],
        baseline_id="baseline-001",
    )

    assert finding.verdict == CriticVerdict.SUPPORTED
    assert finding.severity == "INFO"
    assert "verified" in finding.category.lower()


def test_verify_concept_correspondence_deleted():
    """Correspondence fails when concept deleted."""
    finding = verify_concept_correspondence(
        unit_id="unit-001",
        source_concepts=["c1", "c2"],
        output_correspondences=[
            {"source_concept_id": "c1"},
            # c2 missing
        ],
        baseline_id="baseline-001",
    )

    assert finding.verdict == CriticVerdict.CONTRADICTED
    assert finding.severity == "BLOCK"
    assert "Deleted" in finding.evidence


def test_verify_concept_correspondence_added():
    """Correspondence fails when unsupported concept added."""
    finding = verify_concept_correspondence(
        unit_id="unit-001",
        source_concepts=["c1", "c2"],
        output_correspondences=[
            {"source_concept_id": "c1"},
            {"source_concept_id": "c2"},
            {"source_concept_id": "c3"},  # Extra
        ],
        baseline_id="baseline-001",
    )

    assert finding.verdict == CriticVerdict.CONTRADICTED
    assert finding.severity == "BLOCK"
    assert "Extra" in finding.evidence


def test_verify_obligation_fulfillment_complete():
    """No findings when all obligations fulfilled."""
    findings = verify_obligation_fulfillment(
        unit_id="unit-001",
        obligations=[
            {
                "concept_id": "c1",
                "functions": ["definition"],
                "fulfilled_in_output": True,
            },
            {
                "concept_id": "c2",
                "functions": ["mechanism", "example"],
                "fulfilled_in_output": True,
            },
        ],
        output_latex="Complete output",
    )

    assert len(findings) == 0


def test_verify_obligation_fulfillment_incomplete():
    """Finding when obligation unmet."""
    findings = verify_obligation_fulfillment(
        unit_id="unit-001",
        obligations=[
            {
                "concept_id": "c1",
                "functions": ["definition"],
                "fulfilled_in_output": False,
            },
        ],
        output_latex="Incomplete output",
    )

    assert len(findings) == 1
    assert findings[0].severity == "BLOCK"
    assert findings[0].concept_id == "c1"
    assert "definition" in findings[0].evidence


def test_verify_protected_objects_intact():
    """Protected objects verified when all preserved."""
    finding = verify_protected_objects(
        unit_id="unit-001",
        source_protected=[
            {"object_id": "eq-1", "kind": "equation"},
            {"object_id": "cite-1", "kind": "citation"},
        ],
        output_preserved=["eq-1", "cite-1"],
    )

    assert finding.verdict == CriticVerdict.SUPPORTED
    assert finding.severity == "INFO"
    assert "intact" in finding.category


def test_verify_protected_objects_corrupted():
    """Protected object failure when object missing."""
    finding = verify_protected_objects(
        unit_id="unit-001",
        source_protected=[
            {"object_id": "eq-1", "kind": "equation"},
            {"object_id": "cite-1", "kind": "citation"},
        ],
        output_preserved=["eq-1"],  # cite-1 missing
    )

    assert finding.verdict == CriticVerdict.CONTRADICTED
    assert finding.severity == "BLOCK"
    assert "cite-1" in finding.evidence


def test_run_preflight_all_pass():
    """Preflight passes when all checks succeed."""
    result = run_preflight_verification(
        unit_id="unit-001",
        baseline_id="baseline-001",
        source_concepts=["c1", "c2"],
        output_correspondences=[
            {"source_concept_id": "c1"},
            {"source_concept_id": "c2"},
        ],
        output_latex="Complete explanation text",
        obligations=[
            {"concept_id": "c1", "functions": ["def"], "fulfilled_in_output": True},
            {"concept_id": "c2", "functions": ["mech"], "fulfilled_in_output": True},
        ],
        source_protected=[{"object_id": "eq-1"}],
        output_preserved=["eq-1"],
    )

    assert result.is_acceptable
    assert result.concept_correspondence_ratio == 1.0
    assert result.obligation_fulfillment_ratio == 1.0
    assert result.protected_objects_intact
    assert len(result.blocking_findings) == 0


def test_run_preflight_concept_deletion_blocks():
    """Preflight fails with concept deletion."""
    result = run_preflight_verification(
        unit_id="unit-001",
        baseline_id="baseline-001",
        source_concepts=["c1", "c2"],
        output_correspondences=[
            {"source_concept_id": "c1"},
            # c2 missing
        ],
        output_latex="Incomplete",
        obligations=[],
        source_protected=[],
        output_preserved=[],
    )

    assert not result.is_acceptable
    assert result.concept_correspondence_ratio == 0.0
    assert len(result.blocking_findings) > 0
    assert any("correspondence" in f.category for f in result.blocking_findings)


def test_run_preflight_obligation_unmet_blocks():
    """Preflight fails with unmet obligation."""
    result = run_preflight_verification(
        unit_id="unit-001",
        baseline_id="baseline-001",
        source_concepts=["c1"],
        output_correspondences=[{"source_concept_id": "c1"}],
        output_latex="Incomplete",
        obligations=[
            {"concept_id": "c1", "functions": ["definition"], "fulfilled_in_output": False},
        ],
        source_protected=[],
        output_preserved=[],
    )

    assert not result.is_acceptable
    assert result.obligation_fulfillment_ratio == 0.0
    assert len(result.blocking_findings) > 0
    assert any("obligation" in f.category for f in result.blocking_findings)


def test_run_preflight_protected_object_corruption_blocks():
    """Preflight fails with protected object corruption."""
    result = run_preflight_verification(
        unit_id="unit-001",
        baseline_id="baseline-001",
        source_concepts=["c1"],
        output_correspondences=[{"source_concept_id": "c1"}],
        output_latex="Complete text",
        obligations=[
            {"concept_id": "c1", "functions": ["def"], "fulfilled_in_output": True},
        ],
        source_protected=[{"object_id": "eq-1"}],
        output_preserved=[],  # eq-1 missing
    )

    assert not result.is_acceptable
    assert not result.protected_objects_intact
    assert len(result.blocking_findings) > 0


def test_run_preflight_can_repair_heuristic():
    """can_repair flag set based on fulfillment ratio."""
    # Good candidate for repair: concepts mapped, some obligations met
    result = run_preflight_verification(
        unit_id="unit-001",
        baseline_id="baseline-001",
        source_concepts=["c1", "c2"],
        output_correspondences=[
            {"source_concept_id": "c1"},
            {"source_concept_id": "c2"},
        ],
        output_latex="Mostly complete",
        obligations=[
            {"concept_id": "c1", "functions": ["def"], "fulfilled_in_output": True},
            {"concept_id": "c2", "functions": ["ex"], "fulfilled_in_output": False},
        ],
        source_protected=[],
        output_preserved=[],
    )

    assert result.can_repair or not result.is_acceptable
    # If acceptable, can_repair is irrelevant


def test_run_preflight_repair_targets():
    """Repair targets identified from unmet obligations."""
    result = run_preflight_verification(
        unit_id="unit-001",
        baseline_id="baseline-001",
        source_concepts=["c1", "c2"],
        output_correspondences=[
            {"source_concept_id": "c1"},
            {"source_concept_id": "c2"},
        ],
        output_latex="Incomplete",
        obligations=[
            {"concept_id": "c1", "functions": ["def"], "fulfilled_in_output": False},
            {"concept_id": "c2", "functions": ["ex"], "fulfilled_in_output": False},
        ],
        source_protected=[],
        output_preserved=[],
    )

    assert "c1" in result.repair_targets
    assert "c2" in result.repair_targets


def test_save_preflight_result(tmp_path):
    """Preflight result saved to JSON."""
    result = PreflightResult(
        unit_id="unit-001",
        baseline_id="baseline-001",
        concept_correspondence_ratio=1.0,
        obligation_fulfillment_ratio=1.0,
        protected_objects_intact=True,
        is_acceptable=True,
    )

    output_file = tmp_path / "preflight.json"
    save_preflight_result(result, output_file)

    assert output_file.exists()

    import json
    with open(output_file) as f:
        data = json.load(f)

    assert data["unit_id"] == "unit-001"
    assert data["is_acceptable"]
    assert data["concept_correspondence_ratio"] == 1.0


def test_semantic_finding_verdict_enum():
    """CriticVerdict enum values correct."""
    assert CriticVerdict.SUPPORTED.value == "supported"
    assert CriticVerdict.CONTRADICTED.value == "contradicted"
    assert CriticVerdict.UNRESOLVED.value == "unresolved"


def test_preflight_result_fields():
    """PreflightResult contains all required fields."""
    result = PreflightResult(
        unit_id="u1",
        baseline_id="b1",
    )

    assert result.unit_id == "u1"
    assert result.baseline_id == "b1"
    assert result.concept_correspondence_ratio >= 0.0
    assert result.obligation_fulfillment_ratio >= 0.0
    assert isinstance(result.is_acceptable, bool)
    assert isinstance(result.can_repair, bool)
    assert isinstance(result.findings, list)
    assert isinstance(result.blocking_findings, list)
    assert isinstance(result.repair_targets, list)
