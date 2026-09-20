"""
Concept locality validation utilities.

Ensures concepts reference spans that are close together in the source document,
preventing concepts from spanning large gaps that break assembly.
"""

from typing import Optional
from humanvoice.concept_extraction import ConceptCandidate
from humanvoice.model_extraction import validate_concept_locality
import json


def build_span_position_map(spans_jsonl_path: str) -> dict[str, dict]:
    """
    Build map of span_id -> {byte_start, byte_end} from spans.jsonl.

    Args:
        spans_jsonl_path: Path to spans.jsonl file

    Returns:
        Dictionary mapping span_id to position dict
    """
    span_offsets = {}

    with open(spans_jsonl_path, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            span_id = record['record_id']
            span_offsets[span_id] = {
                'byte_start': record['byte_start'],
                'byte_end': record['byte_end']
            }

    return span_offsets


def validate_all_concepts_locality(
    concepts: list[ConceptCandidate],
    span_offsets: dict[str, dict],
    max_span_range_kb: int = 10
) -> tuple[list[ConceptCandidate], list[dict]]:
    """
    Validate locality for all concepts and separate valid from invalid.

    Args:
        concepts: List of concepts to validate
        span_offsets: Map of span_id -> {byte_start, byte_end}
        max_span_range_kb: Maximum span range in KB

    Returns:
        (valid_concepts, invalid_concepts_info)
        where invalid_concepts_info is a list of dicts with:
        - concept_id
        - span_range_bytes
        - reason
    """
    valid_concepts = []
    invalid_concepts = []

    for concept in concepts:
        is_valid, reason = validate_concept_locality(
            concept,
            span_offsets,
            max_span_range_kb=max_span_range_kb
        )

        if is_valid:
            valid_concepts.append(concept)
        else:
            # Extract span range if available
            span_range_bytes = None
            if reason and "span_range_exceeds_threshold" in reason:
                # Parse bytes from reason string
                import re
                match = re.search(r'(\d+) bytes', reason)
                if match:
                    span_range_bytes = int(match.group(1))

            invalid_concepts.append({
                'concept_id': concept.concept_id,
                'proposition': concept.proposition,
                'span_range_bytes': span_range_bytes,
                'reason': reason
            })

    return valid_concepts, invalid_concepts
