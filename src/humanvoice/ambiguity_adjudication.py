"""
Ambiguity adjudication for concept extraction.

Surfaces unresolved findings from reconstruction and coverage critics
for human review and decision.

Key principles:
- Low-confidence extractions require human confirmation
- Contradicted concepts require human disposition
- Coverage gaps require human classification (substantive vs structural)
- All adjudications are recorded with human approval timestamps
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
import json


@dataclass
class AmbiguityCase:
    """An unresolved finding requiring human adjudication."""
    case_id: str
    case_type: str  # "low_confidence" | "contradicted" | "coverage_gap" | "boundary_unclear"
    window_id: str
    span_ids: list[str]
    concept_id: Optional[str] = None
    extractor_claim: str = ""
    critic_finding: str = ""
    confidence: float = 0.0
    evidence: dict = field(default_factory=dict)
    human_disposition: Optional[str] = None  # "accept" | "reject" | "revise" | "defer"
    human_rationale: Optional[str] = None
    adjudicated_at: Optional[str] = None
    adjudicator: Optional[str] = None


@dataclass
class AdjudicationSession:
    """A batch of ambiguity cases for human review."""
    session_id: str
    snapshot_id: str
    created_at: str
    cases: list[AmbiguityCase] = field(default_factory=list)
    completed_at: Optional[str] = None
    total_cases: int = 0
    adjudicated_count: int = 0


def identify_ambiguities(
    extraction_results: list,
    reconstruction_verdicts: list,
    coverage_verdicts: list,
    confidence_threshold: float = 0.7,
) -> list[AmbiguityCase]:
    """Identify all cases requiring human adjudication.

    Args:
        extraction_results: Results from extract_concepts_from_window
        reconstruction_verdicts: Results from verify_reconstruction
        coverage_verdicts: Results from verify_coverage
        confidence_threshold: Minimum confidence to auto-accept (default 0.7)

    Returns:
        List of AmbiguityCase objects requiring human review
    """
    cases = []
    case_counter = 0

    # Check extraction confidence
    for result in extraction_results:
        for concept in result.concepts:
            if concept.confidence < confidence_threshold:
                case_counter += 1
                cases.append(AmbiguityCase(
                    case_id=f"ambig-{case_counter:04d}",
                    case_type="low_confidence",
                    window_id=result.window_index,
                    span_ids=concept.source_span_ids,
                    concept_id=concept.concept_id,
                    extractor_claim=concept.proposition,
                    critic_finding="",
                    confidence=concept.confidence,
                    evidence={
                        "concept_type": concept.concept_type,
                        "teaching_roles": concept.teaching_roles,
                    },
                ))

    # Check reconstruction verdicts
    for verdict in reconstruction_verdicts:
        if verdict.verdict == "contradicted":
            case_counter += 1
            cases.append(AmbiguityCase(
                case_id=f"ambig-{case_counter:04d}",
                case_type="contradicted",
                window_id="",  # Would need to track from extraction
                span_ids=verdict.evidence_span_ids,
                concept_id=verdict.concept_id,
                extractor_claim=verdict.reconstruction,
                critic_finding=verdict.comparison,
                confidence=verdict.confidence,
                evidence={"verdict": verdict.verdict},
            ))
        elif verdict.verdict == "unresolved":
            case_counter += 1
            cases.append(AmbiguityCase(
                case_id=f"ambig-{case_counter:04d}",
                case_type="boundary_unclear",
                window_id="",
                span_ids=verdict.evidence_span_ids,
                concept_id=verdict.concept_id,
                extractor_claim=verdict.reconstruction,
                critic_finding=verdict.comparison,
                confidence=verdict.confidence,
                evidence={"verdict": verdict.verdict},
            ))

    # Check coverage verdicts
    for verdict in coverage_verdicts:
        if verdict.verdict == "gap":
            case_counter += 1
            cases.append(AmbiguityCase(
                case_id=f"ambig-{case_counter:04d}",
                case_type="coverage_gap",
                window_id="",
                span_ids=[verdict.span_id],
                concept_id=None,
                extractor_claim="",
                critic_finding=verdict.explanation,
                confidence=0.0,
                evidence={
                    "mapped_concepts": verdict.mapped_concept_ids,
                },
            ))

    return cases


def create_adjudication_session(
    snapshot_id: str,
    ambiguity_cases: list[AmbiguityCase],
) -> AdjudicationSession:
    """Create a new adjudication session for batch review.

    Args:
        snapshot_id: Source snapshot identifier
        ambiguity_cases: List of cases requiring adjudication

    Returns:
        AdjudicationSession ready for human review
    """
    session_id = f"adjudication-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    return AdjudicationSession(
        session_id=session_id,
        snapshot_id=snapshot_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        cases=ambiguity_cases,
        total_cases=len(ambiguity_cases),
        adjudicated_count=0,
    )


def save_adjudication_session(session: AdjudicationSession, output_path: str) -> None:
    """Write adjudication session to JSON for human review.

    Args:
        session: AdjudicationSession to save
        output_path: Path to write JSON file
    """
    with open(output_path, 'w') as f:
        json.dump({
            "session_id": session.session_id,
            "snapshot_id": session.snapshot_id,
            "created_at": session.created_at,
            "completed_at": session.completed_at,
            "total_cases": session.total_cases,
            "adjudicated_count": session.adjudicated_count,
            "cases": [
                {
                    "case_id": case.case_id,
                    "case_type": case.case_type,
                    "window_id": case.window_id,
                    "span_ids": case.span_ids,
                    "concept_id": case.concept_id,
                    "extractor_claim": case.extractor_claim,
                    "critic_finding": case.critic_finding,
                    "confidence": case.confidence,
                    "evidence": case.evidence,
                    "human_disposition": case.human_disposition,
                    "human_rationale": case.human_rationale,
                    "adjudicated_at": case.adjudicated_at,
                    "adjudicator": case.adjudicator,
                }
                for case in session.cases
            ],
        }, f, indent=2)


def load_adjudication_session(input_path: str) -> AdjudicationSession:
    """Load adjudication session from JSON.

    Args:
        input_path: Path to adjudication session JSON

    Returns:
        AdjudicationSession with cases loaded
    """
    with open(input_path, 'r') as f:
        data = json.load(f)

    cases = []
    for case_data in data.get("cases", []):
        cases.append(AmbiguityCase(
            case_id=case_data["case_id"],
            case_type=case_data["case_type"],
            window_id=case_data["window_id"],
            span_ids=case_data["span_ids"],
            concept_id=case_data.get("concept_id"),
            extractor_claim=case_data.get("extractor_claim", ""),
            critic_finding=case_data.get("critic_finding", ""),
            confidence=case_data.get("confidence", 0.0),
            evidence=case_data.get("evidence", {}),
            human_disposition=case_data.get("human_disposition"),
            human_rationale=case_data.get("human_rationale"),
            adjudicated_at=case_data.get("adjudicated_at"),
            adjudicator=case_data.get("adjudicator"),
        ))

    return AdjudicationSession(
        session_id=data["session_id"],
        snapshot_id=data["snapshot_id"],
        created_at=data["created_at"],
        cases=cases,
        completed_at=data.get("completed_at"),
        total_cases=data["total_cases"],
        adjudicated_count=data["adjudicated_count"],
    )


def apply_adjudication(
    case: AmbiguityCase,
    disposition: str,
    rationale: str,
    adjudicator: str,
) -> AmbiguityCase:
    """Apply human disposition to an ambiguity case.

    Args:
        case: AmbiguityCase to adjudicate
        disposition: "accept" | "reject" | "revise" | "defer"
        rationale: Human explanation of decision
        adjudicator: Name or identifier of person making decision

    Returns:
        Updated AmbiguityCase with adjudication applied
    """
    case.human_disposition = disposition
    case.human_rationale = rationale
    case.adjudicated_at = datetime.now(timezone.utc).isoformat()
    case.adjudicator = adjudicator

    return case
