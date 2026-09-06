"""
Findings framework for WP3.

Per v1.1 §4.3: findings contain location, observation, consequence or question,
rule/version, and author disposition field. Priority orders work; it is not a
document-quality score.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
from humanvoice.parser import SourceLocation


class FindingCategory(Enum):
    """Finding categories per fixture types."""
    REGISTER = "register"
    EQUATION_CHANGE = "equation_change"
    CITATION_IDENTITY = "citation_identity"
    TABLE_CHANGE = "table_change"
    ADDED_ASSERTION = "added_assertion"
    PACING = "pacing"
    FIRST_USE = "first_use"
    REPETITION = "repetition"


class FindingSeverity(Enum):
    """Severity levels."""
    BLOCKING = "blocking"  # Must be resolved before release
    QUESTION = "question"  # Human review needed
    OBSERVATION = "observation"  # Informational


@dataclass
class Finding:
    """
    Located, reviewable finding per implementation contract §7.

    No command in WP3 mutates canonical input. Findings surface questions
    for human review, not automated fixes.
    """
    finding_id: str
    category: FindingCategory
    severity: FindingSeverity
    location: SourceLocation
    observation: str  # What was detected
    consequence: str  # Why it matters to the reader
    rule_id: str  # Which rule/version produced this
    priority: int  # 0-100, orders work (not quality score)
    author_disposition: Optional[str] = None  # Human decision
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


def create_register_finding(
    term: str,
    location: SourceLocation,
    term_type: str = "workflow_label"
) -> Finding:
    """Create a register finding for private vocabulary."""
    return Finding(
        finding_id=f"register_{location.char_offset}",
        category=FindingCategory.REGISTER,
        severity=FindingSeverity.BLOCKING,
        location=location,
        observation=f"Private {term_type} '{term}' in reader-facing text",
        consequence="Reader cannot act on internal vocabulary",
        rule_id="R10_register_v1",
        priority=90,
        metadata={"term": term, "term_type": term_type}
    )


def create_equation_change_finding(
    baseline_raw: str,
    revised_raw: str,
    location: SourceLocation,
    change_type: str = "substantive"
) -> Finding:
    """Create finding for equation change."""
    severity = FindingSeverity.BLOCKING if change_type == "substantive" else FindingSeverity.OBSERVATION

    return Finding(
        finding_id=f"eq_change_{location.char_offset}",
        category=FindingCategory.EQUATION_CHANGE,
        severity=severity,
        location=location,
        observation=f"Equation changed: {change_type}",
        consequence="Mathematical claim may have changed" if change_type == "substantive" else "Formatting updated",
        rule_id="R5_protected_objects_v1",
        priority=85 if change_type == "substantive" else 20,
        metadata={
            "baseline": baseline_raw[:50],
            "revised": revised_raw[:50],
            "change_type": change_type
        }
    )


def create_citation_identity_finding(
    cite_key: str,
    location: SourceLocation,
    identity_status: str = "unresolved"
) -> Finding:
    """Create finding for citation that needs identity verification."""
    severity_map = {
        "missing": FindingSeverity.BLOCKING,
        "unresolved": FindingSeverity.QUESTION,
        "verified": FindingSeverity.OBSERVATION
    }

    return Finding(
        finding_id=f"cite_{location.char_offset}",
        category=FindingCategory.CITATION_IDENTITY,
        severity=severity_map.get(identity_status, FindingSeverity.QUESTION),
        location=location,
        observation=f"Citation identity: {identity_status}",
        consequence="Verify bibliographic identity before checking source-to-claim support",
        rule_id="R6_citation_identity_v1",
        priority=70,
        metadata={"cite_key": cite_key, "identity_status": identity_status}
    )


def create_added_assertion_finding(
    assertion_text: str,
    location: SourceLocation,
    assertion_type: str = "number"
) -> Finding:
    """Create finding for newly added uncited claim."""
    return Finding(
        finding_id=f"assertion_{location.char_offset}",
        category=FindingCategory.ADDED_ASSERTION,
        severity=FindingSeverity.QUESTION,
        location=location,
        observation=f"Added {assertion_type}: {assertion_text[:50]}",
        consequence="New quantitative or causal claim requires evidence anchor",
        rule_id="R6_R20_evidence_v1",
        priority=75,
        metadata={"assertion_type": assertion_type, "text": assertion_text}
    )


if __name__ == '__main__':
    # Test finding creation
    loc = SourceLocation(char_offset=100, line=5, column=10, length=15)

    findings = [
        create_register_finding("WP3", loc),
        create_equation_change_finding("a^2", "a^3", loc, "substantive"),
        create_citation_identity_finding("smith2020", loc, "unresolved"),
        create_added_assertion_finding("accuracy increased by 15%", loc)
    ]

    for f in findings:
        print(f"{f.category.value:20} {f.severity.value:10} pri={f.priority:2} | {f.observation}")
