"""
Model-assisted concept extraction with independent verification.

Phase 2 of WP-V2-2: extract concepts from bounded source windows, then verify
with independent reconstruction and coverage critics.

Critical properties:
- Extractor and critics are separate model calls with different prompts
- Critics never self-certify their own extractions
- Abstention on low confidence or malformed output
- All concepts link to source spans via byte ranges
"""

import json
from dataclasses import dataclass, field
from typing import Optional, Tuple
from hashlib import sha256
import logging

from humanvoice.model import ModelAdapter, ModelResponse
from humanvoice.schemas import SchemaRegistry
from humanvoice.concept_extraction import ConceptCandidate, ExtractionWindow

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of concept extraction from one window."""
    window_index: int
    concepts: list[ConceptCandidate]
    abstentions: list[str] = field(default_factory=list)
    prompt_hash: Optional[str] = None
    model_response: Optional[ModelResponse] = None


@dataclass
class ReconstructionVerdict:
    """Independent critic's assessment of extracted concepts."""
    concept_id: str
    verdict: str  # "supported" | "contradicted" | "unresolved"
    reconstruction: str
    comparison: str
    confidence: float
    evidence_span_ids: list[str] = field(default_factory=list)


@dataclass
class CoverageVerdict:
    """Coverage critic's assessment of span-to-concept mapping."""
    span_id: str
    verdict: str  # "covered" | "gap" | "unresolved"
    explanation: str
    mapped_concept_ids: list[str] = field(default_factory=list)


def validate_concept_locality(
    concept: ConceptCandidate,
    span_index: dict[str, dict[str, int]],
    max_span_range_kb: int = 10
) -> Tuple[bool, Optional[str]]:
    """
    Validate that all spans for a concept are within max_span_range_kb.

    Enforces the concept locality constraint: concepts should reference
    spans that are close together in the source document, not scattered
    across the entire document.

    Args:
        concept: ConceptCandidate object to validate
        span_index: Dict mapping span_id -> {'byte_start': int, 'byte_end': int}
        max_span_range_kb: Maximum allowed range in KB (default 10)

    Returns:
        (is_valid, failure_reason)
        - (True, None) if valid
        - (False, reason_string) if invalid

    Example:
        >>> concept = ConceptCandidate(source_span_ids=["span-1", "span-2"])
        >>> span_index = {
        ...     "span-1": {"byte_start": 1000, "byte_end": 1500},
        ...     "span-2": {"byte_start": 2000, "byte_end": 2500}
        ... }
        >>> validate_concept_locality(concept, span_index, max_span_range_kb=10)
        (True, None)
    """
    source_span_ids = concept.source_span_ids

    if not source_span_ids:
        # Concept with no spans should have been filtered at extraction
        return False, "no_source_spans"

    # Get byte positions for all spans
    positions = []
    for span_id in source_span_ids:
        if span_id not in span_index:
            return False, f"span_not_found: {span_id}"

        span = span_index[span_id]
        positions.append((span['byte_start'], span['byte_end']))

    # Sort by start position
    positions.sort()

    # Calculate total range (first start to last end)
    first_start = positions[0][0]
    last_end = positions[-1][1]
    total_range_bytes = last_end - first_start
    max_range_bytes = max_span_range_kb * 1024

    if total_range_bytes > max_range_bytes:
        return False, f"span_range_too_large: {total_range_bytes} bytes > {max_range_bytes} bytes"

    return True, None


def _extraction_prompt(window: ExtractionWindow, brief: dict, adjacent_context: dict, span_texts: dict) -> str:
    """Generate prompt for concept extraction from one window.

    Args:
        window: Source spans to extract from
        brief: HumanizationBrief with reader knowledge, genre, exemplars
        adjacent_context: Previously accepted terminology and structure
        span_texts: Map of span_id -> exact text content

    Returns:
        Prompt text requesting schema-valid SourceConcept records
    """
    # Collect source text from window spans
    source_lines = []
    for span_id in window.span_ids:
        text = span_texts.get(span_id, "[text unavailable]")
        source_lines.append(f"[{span_id}]: {text}")

    source_block = "\n".join(source_lines)

    return f"""Extract substantive concepts from the following source passage.

A concept is a meaning-bearing proposition: definition, distinction, claim,
mechanism, assumption, derivation step, qualification, example, counterexample,
evidence interpretation, or teaching transition.

Source text with span IDs:
{source_block}

Reader profile:
{json.dumps(brief.get('reader', {}), indent=2)}

Genre: {brief.get('genre', 'technical')}

For each concept:
1. Identify the proposition (what is being taught)
2. Classify the concept type
3. Note the teaching role (initial, repeated, expanded, contrasted)
4. Link to source span IDs — ONLY the minimal spans that directly state this concept
5. List supporting span IDs (for evidence, equations, citations)
6. State confidence (0.0-1.0)

CRITICAL: source_span_ids must be DISJOINT across concepts.
- If multiple concepts come from one long span, you must identify which sentences/clauses ground each concept
- Each span ID should appear in exactly ONE concept's source_span_ids
- If a span provides context but not the core claim, use supporting_spans instead
- When in doubt, assign the span to the most specific concept

Abstain (return empty list) if:
- Source is purely structural (headings, labels, navigation)
- Cannot determine proposition boundaries
- Ambiguous whether content is substantive

Return a JSON array of objects with these fields:
- concept_id: string (unique identifier)
- proposition: string (the actual concept/claim being taught)
- concept_type: string (definition|distinction|claim|mechanism|derivation|finding|example|counterexample)
- source_span_ids: array of strings (span IDs where this concept is directly stated)
- teaching_roles: array of strings (initial|repeated|qualified|contrasted|example|prerequisite)
- supporting_spans: array of strings (span IDs providing evidence/support)
- prerequisites: array of strings (concepts reader needs first)
- confidence: number (0.0-1.0)

Example response format:
[
  {{
    "concept_id": "concept-001",
    "proposition": "Zero lower bound constrains monetary policy when nominal rates approach zero",
    "concept_type": "claim",
    "source_span_ids": ["span-001"],
    "teaching_roles": ["initial"],
    "supporting_spans": ["span-002"],
    "prerequisites": ["monetary_policy_basics"],
    "confidence": 0.9
  }},
  {{
    "concept_id": "concept-002",
    "proposition": "When rates hit zero, central banks lose their primary policy lever",
    "concept_type": "mechanism",
    "source_span_ids": ["span-002"],
    "teaching_roles": ["initial"],
    "supporting_spans": [],
    "prerequisites": ["concept-001"],
    "confidence": 0.85
  }}
]"""


def _reconstruction_prompt(concepts: list[ConceptCandidate], source_text: str) -> str:
    """Generate prompt for reconstruction critic.

    Given extracted concepts, reconstruct the source meaning independently,
    then compare to actual source.
    """
    concept_summary = json.dumps([{
        'concept_id': c.concept_id,
        'proposition': c.proposition,
        'concept_type': c.concept_type,
        'teaching_roles': c.teaching_roles,
    } for c in concepts], indent=2)

    return f"""You are an independent verification critic. Your task:

1. Read the extracted concepts below
2. Reconstruct what the source passage teaches (without seeing it)
3. Compare your reconstruction to the actual source
4. Report: supported | contradicted | unresolved

Extracted concepts:
{concept_summary}

Now here is the actual source:
{source_text}

For each concept:
- verdict: "supported" if source clearly contains it
- verdict: "contradicted" if source contradicts or lacks it
- verdict: "unresolved" if ambiguous or boundary unclear
- reconstruction: what you inferred from concept alone
- comparison: how source matches/differs

Return JSON array of ReconstructionVerdict records."""


def _coverage_prompt(spans: list[dict], concepts: list[ConceptCandidate]) -> str:
    """Generate prompt for coverage critic.

    Check that every substantive source span maps to at least one concept.
    """
    return f"""You are a coverage verification critic. Your task:

1. For each source span, determine if it's covered by extracted concepts
2. A span is "covered" if its substantive meaning appears in ≥1 concept
3. A span is a "gap" if it contains teaching content but no concept captures it
4. A span is "unresolved" if ambiguous

Source spans:
{json.dumps([{
    'span_id': s['record_id'],
    'span_kind': s['span_kind'],
    'text_preview': s.get('exact_text', '')[:100],
} for s in spans], indent=2)}

Extracted concepts:
{json.dumps([{
    'concept_id': c.concept_id,
    'proposition': c.proposition,
    'source_span_ids': c.source_span_ids,
} for c in concepts], indent=2)}

For each span:
- verdict: "covered" if its meaning is in concepts
- verdict: "gap" if substantive but unmapped
- verdict: "unresolved" if unclear
- mapped_concept_ids: which concepts cover it
- explanation: brief rationale

Skip spans with kind "whitespace", "command", "float" (these are structural).

Return JSON array of CoverageVerdict records."""


def validate_concept_locality(
    concept: ConceptCandidate,
    span_offsets: dict[str, dict],
    max_span_range_kb: int = 10
) -> tuple[bool, Optional[str]]:
    """
    Validate that all spans for a concept are within max_span_range_kb of each other.

    This enforces the "concept locality" requirement: concepts should reference
    spans that are close together in the source document, not scattered across
    140KB gaps (which breaks assembly).

    Args:
        concept: Concept to validate
        span_offsets: Map of span_id -> {byte_start, byte_end}
        max_span_range_kb: Maximum distance in KB from first to last span

    Returns:
        (is_valid, failure_reason)
        - (True, None) if valid
        - (False, reason_string) if invalid
    """
    if not concept.source_span_ids:
        return False, "no_source_spans"

    # Get byte positions for all spans
    positions = []
    for span_id in concept.source_span_ids:
        if span_id not in span_offsets:
            return False, f"span_id_not_found: {span_id}"

        span = span_offsets[span_id]
        positions.append((span['byte_start'], span['byte_end']))

    # Sort by start position
    positions.sort()

    # Calculate total range (first start to last end)
    first_start = positions[0][0]
    last_end = positions[-1][1]
    total_range = last_end - first_start
    max_range_bytes = max_span_range_kb * 1024

    if total_range > max_range_bytes:
        return False, f"span_range_exceeds_threshold: {total_range} bytes > {max_range_bytes} bytes ({total_range/1024:.1f}KB > {max_span_range_kb}KB)"

    return True, None


def extract_concepts_from_window(
    window: ExtractionWindow,
    brief: dict,
    model: ModelAdapter,
    registry: SchemaRegistry,
    adjacent_context: Optional[dict] = None,
    span_texts: Optional[dict] = None,
    span_index: Optional[dict] = None,
) -> ExtractionResult:
    """Extract concepts from one window with model assistance.

    Args:
        window: Bounded source spans to process
        brief: HumanizationBrief with reader profile
        model: Configured model adapter
        registry: Schema registry for validation
        adjacent_context: Previously accepted terminology (optional)
        span_texts: Map of span_id -> exact text (optional)
        span_index: Map of span_id -> {'byte_start': int, 'byte_end': int} (optional)

    Returns:
        ExtractionResult with concepts or abstentions
    """
    prompt = _extraction_prompt(window, brief, adjacent_context or {}, span_texts or {})
    prompt_hash = sha256(prompt.encode()).hexdigest()

    # Handle None model (testing/placeholder)
    if model is None:
        return ExtractionResult(
            window_index=window.span_ids[0] if window.span_ids else 0,
            concepts=[],
            abstentions=["model_call_not_implemented"],
            prompt_hash=prompt_hash,
            model_response=None,
        )

    try:
        # Request array of concept candidates
        response = model.invoke(
            prompt=prompt,
            record_type=None,  # Expecting array, not single record
            max_tokens=4000,
            purpose="concept_extraction",
        )

        # Handle abstention or error
        if response.abstention:
            return ExtractionResult(
                window_index=window.span_ids[0] if window.span_ids else 0,
                concepts=[],
                abstentions=[response.abstention],
                prompt_hash=prompt_hash,
                model_response=response,
            )

        # Parse concept array
        parsed = None
        try:
            parsed = json.loads(response.text)
        except json.JSONDecodeError:
            return ExtractionResult(
                window_index=window.span_ids[0] if window.span_ids else 0,
                concepts=[],
                abstentions=["invalid_json"],
                prompt_hash=prompt_hash,
                model_response=response,
            )

        if not isinstance(parsed, list):
            return ExtractionResult(
                window_index=window.span_ids[0] if window.span_ids else 0,
                concepts=[],
                abstentions=["expected_array_got_single_record"],
                prompt_hash=prompt_hash,
                model_response=response,
            )

        # Convert to ConceptCandidate objects
        concepts = []
        for item in parsed:
            concept = ConceptCandidate(
                concept_id=item.get("concept_id", ""),
                proposition=item.get("proposition", ""),
                concept_type=item.get("concept_type", "definition"),
                source_span_ids=item.get("source_span_ids", []),
                teaching_roles=item.get("teaching_roles", ["initial"]),
                supporting_spans=item.get("supporting_spans", []),
                prerequisites=item.get("prerequisites", []),
                confidence=item.get("confidence", 0.8),
            )
            concepts.append(concept)

        # Validate concept locality before returning (if span_index provided)
        if span_index:
            validated_concepts = []
            rejected_concepts = []

            for concept in concepts:
                is_valid, reason = validate_concept_locality(
                    concept,
                    span_index,
                    max_span_range_kb=10
                )
                if is_valid:
                    validated_concepts.append(concept)
                else:
                    rejected_concepts.append((concept.concept_id, reason))
                    logger.warning(f"Rejected concept {concept.concept_id}: {reason}")

            abstentions = [f"locality_violation: {c[0]} - {c[1]}" for c in rejected_concepts] if rejected_concepts else []

            return ExtractionResult(
                window_index=window.span_ids[0] if window.span_ids else 0,
                concepts=validated_concepts,
                abstentions=abstentions,
                prompt_hash=prompt_hash,
                model_response=response,
            )
        else:
            # No span_index provided, skip locality validation
            return ExtractionResult(
                window_index=window.span_ids[0] if window.span_ids else 0,
                concepts=concepts,
                abstentions=[],
                prompt_hash=prompt_hash,
                model_response=response,
            )

    except Exception as e:
        return ExtractionResult(
            window_index=window.span_ids[0] if window.span_ids else 0,
            concepts=[],
            abstentions=[f"extraction_failed: {e}"],
            prompt_hash=prompt_hash,
            model_response=None,
        )


def verify_reconstruction(
    concepts: list[ConceptCandidate],
    source_spans: list[dict],
    model: ModelAdapter,
) -> list[ReconstructionVerdict]:
    """Independent reconstruction critic.

    Given extracted concepts, reconstruct source meaning and compare.
    This is a separate model call blind to the extractor's reasoning.
    """
    if not concepts:
        return []

    # Collect source text from spans
    source_text = "\n".join(s.get('exact_text', '') for s in source_spans)

    prompt = _reconstruction_prompt(concepts, source_text)

    try:
        # Request array of verdicts
        response = model.invoke(
            prompt=prompt,
            record_type=None,  # Expecting array
            max_tokens=8000,
            purpose="reconstruction_verification",
        )

        # Handle abstention or error
        if response.abstention:
            return []

        # Parse verdict array
        parsed = None
        try:
            parsed = json.loads(response.text)
        except json.JSONDecodeError:
            return []

        if not isinstance(parsed, list):
            return []

        verdicts = []
        for item in parsed:
            verdict = ReconstructionVerdict(
                concept_id=item.get("concept_id", ""),
                verdict=item.get("verdict", "unresolved"),
                reconstruction=item.get("reconstruction", ""),
                comparison=item.get("comparison", ""),
                confidence=item.get("confidence", 0.5),
                evidence_span_ids=item.get("evidence_span_ids", []),
            )
            verdicts.append(verdict)

        return verdicts

    except Exception:
        return []


def verify_coverage(
    spans: list[dict],
    concepts: list[ConceptCandidate],
    model: ModelAdapter,
) -> list[CoverageVerdict]:
    """Independent coverage critic.

    Check that every substantive source span maps to extracted concepts.
    """
    if not spans or not concepts:
        return []

    prompt = _coverage_prompt(spans, concepts)

    try:
        # Request array of verdicts
        response = model.invoke(
            prompt=prompt,
            record_type=None,  # Expecting array
            max_tokens=8000,
            purpose="coverage_verification",
        )

        # Handle abstention or error
        if response.abstention:
            return []

        # Parse verdict array
        parsed = None
        try:
            parsed = json.loads(response.text)
        except json.JSONDecodeError:
            return []

        if not isinstance(parsed, list):
            return []

        verdicts = []
        for item in parsed:
            verdict = CoverageVerdict(
                span_id=item.get("span_id", ""),
                verdict=item.get("verdict", "unresolved"),
                explanation=item.get("explanation", ""),
                mapped_concept_ids=item.get("mapped_concept_ids", []),
            )
            verdicts.append(verdict)

        return verdicts

    except Exception:
        return []
