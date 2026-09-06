"""
Protected-object comparison for WP3.

Implements correspondence matching per implementation contract §6.3:
- unchanged: both raw and normalized forms match
- explained_change: normalized forms match, raw differs (whitespace, formatting)
- substantive_change: normalized forms differ
- added: object in v' but not v
- removed: object in v but not v'
- unresolved: cannot determine correspondence (triggers abstention)

Per R12: hv refuses to compare a single document against itself.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
from humanvoice.parser import ProtectedObject, ObjectType


class CorrespondenceStatus(Enum):
    """Correspondence outcomes per implementation contract."""
    UNCHANGED = "unchanged"
    EXPLAINED_CHANGE = "explained_change"
    SUBSTANTIVE_CHANGE = "substantive_change"
    ADDED = "added"
    REMOVED = "removed"
    UNRESOLVED = "unresolved"


@dataclass
class Correspondence:
    """
    Matched pair of protected objects between versions.

    Per contract §6.3: preserve both objects and the correspondence status
    so human review can audit the automated classification.
    """
    object_v: Optional[ProtectedObject]  # Object in version v (baseline)
    object_v_prime: Optional[ProtectedObject]  # Object in version v' (revised)
    status: CorrespondenceStatus
    confidence: float  # 0.0-1.0, for abstention threshold
    rationale: str  # Why this status was assigned


def _normalize_equation(raw: str) -> str:
    """
    Normalize equation for comparison.

    Declared normalization per fixture F-EQUATION-001:
    - Strip leading/trailing whitespace
    - Collapse internal whitespace to single space
    - Remove comments

    Does NOT normalize:
    - Exponents (2^3 vs 2^2 is substantive)
    - Coefficients
    - Variable names
    """
    import re

    # Remove LaTeX comments
    text = re.sub(r'%.*$', '', raw, flags=re.MULTILINE)

    # Collapse whitespace
    text = ' '.join(text.split())

    return text.strip()


def _normalize_citation(raw: str) -> str:
    """
    Normalize citation for comparison.

    Extracts cite key(s), strips formatting variations.
    """
    import re

    # Extract key from \cite{key} or \citep{key1,key2}
    match = re.search(r'\\cite\w*\{([^}]+)\}', raw)
    if match:
        keys = match.group(1)
        # Normalize whitespace around commas
        keys = ','.join(k.strip() for k in keys.split(','))
        return keys

    return raw.strip()


def normalize_object(obj: ProtectedObject) -> str:
    """
    Normalize protected object for correspondence matching.

    Normalization rules are type-specific and documented in fixture answer keys.
    """
    if obj.object_type == ObjectType.EQUATION:
        return _normalize_equation(obj.raw_form)
    elif obj.object_type == ObjectType.CITATION:
        return _normalize_citation(obj.raw_form)
    elif obj.object_type == ObjectType.LABEL:
        # Labels normalize to their name only
        return obj.normalized_form or obj.raw_form.strip()
    elif obj.object_type == ObjectType.TABLE:
        # WP3: simple whitespace normalization; cell-level in WP4
        return ' '.join(obj.raw_form.split())
    else:
        # Default: preserve raw form
        return obj.raw_form.strip()


def match_objects(
    objects_v: List[ProtectedObject],
    objects_v_prime: List[ProtectedObject]
) -> List[Correspondence]:
    """
    Match protected objects between two versions.

    Strategy:
    1. Match by ID if both have stable IDs (labels)
    2. Match by normalized form + type
    3. Match by position proximity + type
    4. Mark unmatched as added/removed

    Returns all correspondences including unmatched objects.
    """
    correspondences = []
    matched_v = set()
    matched_v_prime = set()

    # Phase 1: Match by normalized form + type
    for i, obj_v in enumerate(objects_v):
        norm_v = normalize_object(obj_v)

        for j, obj_v_prime in enumerate(objects_v_prime):
            if j in matched_v_prime:
                continue

            if obj_v.object_type != obj_v_prime.object_type:
                continue

            norm_v_prime = normalize_object(obj_v_prime)

            if norm_v == norm_v_prime:
                # Normalized forms match
                if obj_v.raw_form == obj_v_prime.raw_form:
                    status = CorrespondenceStatus.UNCHANGED
                    rationale = "raw and normalized forms both match"
                else:
                    status = CorrespondenceStatus.EXPLAINED_CHANGE
                    rationale = "normalized forms match; raw differs (formatting)"

                correspondences.append(Correspondence(
                    object_v=obj_v,
                    object_v_prime=obj_v_prime,
                    status=status,
                    confidence=1.0,
                    rationale=rationale
                ))

                matched_v.add(i)
                matched_v_prime.add(j)
                break

    # Phase 2: Check for substantive changes (same type, nearby position)
    for i, obj_v in enumerate(objects_v):
        if i in matched_v:
            continue

        # Look for nearby object of same type
        best_match = None
        best_distance = float('inf')

        for j, obj_v_prime in enumerate(objects_v_prime):
            if j in matched_v_prime:
                continue

            if obj_v.object_type != obj_v_prime.object_type:
                continue

            # Position distance (char offset)
            distance = abs(obj_v.location.char_offset - obj_v_prime.location.char_offset)

            if distance < best_distance and distance < 1000:  # Within 1000 chars
                best_distance = distance
                best_match = j

        if best_match is not None:
            obj_v_prime = objects_v_prime[best_match]

            correspondences.append(Correspondence(
                object_v=obj_v,
                object_v_prime=obj_v_prime,
                status=CorrespondenceStatus.SUBSTANTIVE_CHANGE,
                confidence=0.7,  # Lower confidence for position-based match
                rationale=f"same type, nearby position (offset Δ={best_distance}); normalized forms differ"
            ))

            matched_v.add(i)
            matched_v_prime.add(best_match)

    # Phase 3: Mark unmatched as removed/added
    for i, obj_v in enumerate(objects_v):
        if i not in matched_v:
            correspondences.append(Correspondence(
                object_v=obj_v,
                object_v_prime=None,
                status=CorrespondenceStatus.REMOVED,
                confidence=1.0,
                rationale="object in baseline but not in revision"
            ))

    for j, obj_v_prime in enumerate(objects_v_prime):
        if j not in matched_v_prime:
            correspondences.append(Correspondence(
                object_v=None,
                object_v_prime=obj_v_prime,
                status=CorrespondenceStatus.ADDED,
                confidence=1.0,
                rationale="object in revision but not in baseline"
            ))

    return correspondences


def compare_documents(
    objects_baseline: List[ProtectedObject],
    objects_revised: List[ProtectedObject],
    min_confidence: float = 0.5
) -> Tuple[List[Correspondence], List[str]]:
    """
    Compare two document versions and produce correspondences.

    Returns:
        correspondences: matched object pairs with status
        abstentions: reasons for unresolved correspondences
    """
    correspondences = match_objects(objects_baseline, objects_revised)

    abstentions = []
    for corr in correspondences:
        if corr.confidence < min_confidence:
            abstentions.append(
                f"Low-confidence match ({corr.confidence:.2f}): "
                f"{corr.object_v.object_id if corr.object_v else 'none'} -> "
                f"{corr.object_v_prime.object_id if corr.object_v_prime else 'none'}"
            )
            corr.status = CorrespondenceStatus.UNRESOLVED

    return correspondences, abstentions


if __name__ == '__main__':
    # Test normalization
    from humanvoice.parser import SourceLocation

    eq1 = ProtectedObject(
        object_id="eq_0",
        object_type=ObjectType.EQUATION,
        raw_form="a^2 + b^2 = c^2",
        normalized_form=None,
        location=SourceLocation(100, length=20),
        metadata={}
    )

    eq2 = ProtectedObject(
        object_id="eq_0",
        object_type=ObjectType.EQUATION,
        raw_form="a^2  +  b^2  =  c^2",  # Extra whitespace
        normalized_form=None,
        location=SourceLocation(105, length=25),
        metadata={}
    )

    eq3 = ProtectedObject(
        object_id="eq_1",
        object_type=ObjectType.EQUATION,
        raw_form="a^3 + b^3 = c^3",  # Different exponent
        normalized_form=None,
        location=SourceLocation(110, length=20),
        metadata={}
    )

    correspondences, abstentions = compare_documents([eq1], [eq2, eq3])

    for corr in correspondences:
        print(f"{corr.status.value}: {corr.rationale}")

    print(f"\nAbstentions: {len(abstentions)}")
