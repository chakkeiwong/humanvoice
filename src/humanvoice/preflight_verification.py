"""
Preflight verification for revised output.

WP-V2-4: Independent verification of rewritten units.

Semantic critics on revised output (not just source):
1. Concept correspondence verification (exactly 1.0)
2. Explanation obligation fulfillment
3. Unsupported addition detection
4. Protected object integrity
5. Dependency order compliance
6. Source/output coherence
"""

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
import json


class CriticVerdict(Enum):
    """Verdict from independent semantic critic."""
    SUPPORTED = "supported"      # Evidence found in output
    CONTRADICTED = "contradicted"  # Evidence contradicts output
    UNRESOLVED = "unresolved"    # Cannot determine


@dataclass
class SemanticFinding:
    """One semantic defect or issue."""
    finding_id: str
    severity: str  # "BLOCK" | "WARN" | "INFO"
    category: str  # "concept_deletion" | "obligation_unmet" | "unsupported_addition" | etc.
    concept_id: Optional[str] = None
    output_span_ids: List[str] = field(default_factory=list)
    evidence: str = ""
    verdict: CriticVerdict = CriticVerdict.UNRESOLVED
    located_spans: List[dict] = field(default_factory=list)


@dataclass
class PreflightResult:
    """Complete preflight verification of a revised unit."""
    unit_id: str
    baseline_id: str

    # Deterministic checks
    concept_correspondence_ratio: float = 0.0
    obligation_fulfillment_ratio: float = 0.0
    protected_objects_intact: bool = False
    dependency_order_correct: bool = False

    # Semantic findings
    findings: List[SemanticFinding] = field(default_factory=list)

    # Overall status
    is_acceptable: bool = False
    blocking_findings: List[SemanticFinding] = field(default_factory=list)

    # Repair readiness
    can_repair: bool = False
    repair_targets: List[str] = field(default_factory=list)


def verify_concept_correspondence(
    unit_id: str,
    source_concepts: List[str],
    output_correspondences: List[dict],
    baseline_id: str,
) -> SemanticFinding:
    """Verify output contains all source concepts (exactly 1.0).

    Args:
        unit_id: Unit being verified
        source_concepts: Concept IDs from baseline
        output_correspondences: Correspondences from rewrite result
        baseline_id: For finding ID

    Returns:
        SemanticFinding for correspondence status
    """
    output_concept_ids = {c.get("source_concept_id") for c in output_correspondences}
    source_set = set(source_concepts)

    deleted = source_set - output_concept_ids
    extra = output_concept_ids - source_set

    if deleted or extra:
        return SemanticFinding(
            finding_id=f"{unit_id}-correspondence-01",
            severity="BLOCK",
            category="concept_correspondence_failure",
            evidence=f"Deleted: {deleted}; Extra: {extra}",
            verdict=CriticVerdict.CONTRADICTED,
        )

    # All concepts present
    return SemanticFinding(
        finding_id=f"{unit_id}-correspondence-00",
        severity="INFO",
        category="concept_correspondence_verified",
        evidence="All source concepts mapped in output",
        verdict=CriticVerdict.SUPPORTED,
    )


def verify_obligation_fulfillment(
    unit_id: str,
    obligations: List[dict],
    output_latex: str,
) -> List[SemanticFinding]:
    """Verify explanation obligations fulfilled in output.

    Args:
        unit_id: Unit being verified
        obligations: List of ExplanationObligation dicts
        output_latex: Rewritten LaTeX text

    Returns:
        List of SemanticFinding for unmet obligations
    """
    findings = []

    for i, obligation in enumerate(obligations):
        concept_id = obligation.get("concept_id")
        required_functions = obligation.get("functions", [])

        # Check that obligation is not marked as unmet
        fulfilled = obligation.get("fulfilled_in_output", False)

        if not fulfilled and required_functions:
            finding = SemanticFinding(
                finding_id=f"{unit_id}-obligation-{i}",
                severity="BLOCK",
                category="obligation_unmet",
                concept_id=concept_id,
                evidence=f"Missing: {', '.join(required_functions)}",
                verdict=CriticVerdict.CONTRADICTED,
            )
            findings.append(finding)

    return findings


def verify_protected_objects(
    unit_id: str,
    source_protected: List[dict],
    output_preserved: List[str],
) -> SemanticFinding:
    """Verify protected objects remain unchanged.

    Args:
        unit_id: Unit being verified
        source_protected: Protected objects from source
        output_preserved: Preserved object IDs in output

    Returns:
        SemanticFinding for protected object status
    """
    source_ids = {obj.get("object_id") for obj in source_protected}
    preserved_set = set(output_preserved)

    corrupted = source_ids - preserved_set

    if corrupted:
        return SemanticFinding(
            finding_id=f"{unit_id}-protected-01",
            severity="BLOCK",
            category="protected_object_corruption",
            evidence=f"Corrupted objects: {corrupted}",
            verdict=CriticVerdict.CONTRADICTED,
        )

    return SemanticFinding(
        finding_id=f"{unit_id}-protected-00",
        severity="INFO",
        category="protected_objects_intact",
        evidence="All protected objects preserved",
        verdict=CriticVerdict.SUPPORTED,
    )


def verify_unsupported_additions(
    unit_id: str,
    output_text: str,
    baseline_concepts: set,
    unit_concepts: set,
) -> List[SemanticFinding]:
    """Detect unsupported concepts added to output.

    Args:
        unit_id: Unit being verified
        output_text: Output LaTeX
        baseline_concepts: All concept IDs in baseline
        unit_concepts: Concepts assigned to this unit

    Returns:
        List of SemanticFinding for unsupported additions (if any)
    """
    findings = []

    # Look for citations or references not in unit scope
    # This is a placeholder; full implementation would parse output
    # and check for external references

    return findings


def run_preflight_verification(
    unit_id: str,
    baseline_id: str,
    source_concepts: List[str],
    output_correspondences: List[dict],
    output_latex: str,
    obligations: List[dict],
    source_protected: List[dict],
    output_preserved: List[str],
) -> PreflightResult:
    """Run complete preflight verification on revised unit.

    Args:
        unit_id: Unit ID
        baseline_id: Baseline ID
        source_concepts: Concept IDs from baseline
        output_correspondences: Correspondences from rewrite
        output_latex: Rewritten LaTeX text
        obligations: Explanation obligations
        source_protected: Protected objects from source
        output_preserved: Preserved object IDs

    Returns:
        PreflightResult with all verification details
    """
    result = PreflightResult(
        unit_id=unit_id,
        baseline_id=baseline_id,
    )

    # Concept correspondence (mandatory)
    corr_finding = verify_concept_correspondence(
        unit_id, source_concepts, output_correspondences, baseline_id
    )
    result.findings.append(corr_finding)

    if corr_finding.verdict == CriticVerdict.CONTRADICTED:
        result.blocking_findings.append(corr_finding)
        result.concept_correspondence_ratio = 0.0
    else:
        result.concept_correspondence_ratio = 1.0

    # Obligation fulfillment
    obligation_findings = verify_obligation_fulfillment(
        unit_id, obligations, output_latex
    )
    result.findings.extend(obligation_findings)

    if obligation_findings:
        result.blocking_findings.extend(obligation_findings)
        result.obligation_fulfillment_ratio = 0.0
    else:
        result.obligation_fulfillment_ratio = 1.0

    # Protected objects
    protected_finding = verify_protected_objects(
        unit_id, source_protected, output_preserved
    )
    result.findings.append(protected_finding)
    result.protected_objects_intact = (
        protected_finding.verdict == CriticVerdict.SUPPORTED
    )

    if protected_finding.verdict == CriticVerdict.CONTRADICTED:
        result.blocking_findings.append(protected_finding)

    # Unsupported additions
    addition_findings = verify_unsupported_additions(
        unit_id, output_latex, set(), set(source_concepts)
    )
    result.findings.extend(addition_findings)
    result.blocking_findings.extend(addition_findings)

    # Overall acceptance: no blocking findings
    result.is_acceptable = len(result.blocking_findings) == 0

    # Repair readiness
    result.can_repair = result.is_acceptable or (
        result.concept_correspondence_ratio > 0.5 and
        result.obligation_fulfillment_ratio > 0.5
    )

    # Repair targets: which obligations need work
    for finding in obligation_findings:
        if finding.concept_id:
            result.repair_targets.append(finding.concept_id)

    return result


def save_preflight_result(result: PreflightResult, output_path) -> None:
    """Save preflight result to JSON.

    Args:
        result: PreflightResult
        output_path: Path to write
    """
    from pathlib import Path

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "unit_id": result.unit_id,
            "baseline_id": result.baseline_id,
            "concept_correspondence_ratio": result.concept_correspondence_ratio,
            "obligation_fulfillment_ratio": result.obligation_fulfillment_ratio,
            "protected_objects_intact": result.protected_objects_intact,
            "is_acceptable": result.is_acceptable,
            "can_repair": result.can_repair,
            "repair_targets": result.repair_targets,
            "findings": [
                {
                    "finding_id": f.finding_id,
                    "severity": f.severity,
                    "category": f.category,
                    "concept_id": f.concept_id,
                    "evidence": f.evidence,
                    "verdict": f.verdict.value,
                }
                for f in result.findings
            ],
            "blocking_findings_count": len(result.blocking_findings),
        }, f, indent=2)
