"""
Patch-based assembly for WP-V2-5.

Applies accepted replacements to source by offset to create revised document:
1. Collect accepted replacements from preflight verification
2. Apply patches in reverse offset order (to preserve offsets)
3. Verify complete document builds
4. Generate comparison PDF (original vs. revised)
"""

from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path
import json


@dataclass
class SourcePatch:
    """One accepted replacement to apply."""
    unit_id: str
    source_span_ids: List[str]
    start_offset: int        # Byte offset in original source
    end_offset: int          # Byte offset in original source
    original_text: str
    replacement_text: str
    concept_ids: List[str] = field(default_factory=list)
    verified: bool = False   # Passed preflight


@dataclass
class PatchAssemblyResult:
    """Result of patch assembly operation."""
    snapshot_id: str
    total_patches: int = 0
    patches_applied: int = 0
    patches_failed: List[str] = field(default_factory=list)

    # Document state
    original_source_hash: str = ""
    revised_source_hash: str = ""
    untouched_bytes_count: int = 0
    revised_bytes_count: int = 0

    # Status
    assembly_complete: bool = False
    document_builds: bool = False
    comparison_generated: bool = False


def sort_patches_reverse(patches: List[SourcePatch]) -> List[SourcePatch]:
    """Sort patches by end_offset in descending order.

    Reverse order prevents earlier patches from shifting offsets.

    Args:
        patches: List of patches to apply

    Returns:
        Patches sorted by end_offset descending
    """
    return sorted(patches, key=lambda p: p.end_offset, reverse=True)


def apply_patch(
    source_text: str,
    patch: SourcePatch,
) -> str:
    """Apply one patch to source text.

    Args:
        source_text: Original source LaTeX
        patch: Patch to apply

    Returns:
        Source text with patch applied

    Raises:
        ValueError: If patch offsets invalid or original text doesn't match
    """
    if patch.start_offset < 0 or patch.end_offset > len(source_text):
        raise ValueError(
            f"Patch offsets out of bounds: [{patch.start_offset}, {patch.end_offset}] "
            f"in text of length {len(source_text)}"
        )

    extracted = source_text[patch.start_offset:patch.end_offset]

    if extracted != patch.original_text:
        raise ValueError(
            f"Original text mismatch at [{patch.start_offset}, {patch.end_offset}]: "
            f"expected {len(patch.original_text)} chars, got {len(extracted)} chars"
        )

    revised = source_text[:patch.start_offset] + patch.replacement_text + source_text[patch.end_offset:]

    return revised


def assemble_document(
    original_source: str,
    patches: List[SourcePatch],
) -> tuple[str, List[str]]:
    """Assemble revised document by applying patches.

    Patches are applied in reverse offset order to preserve offsets.

    Args:
        original_source: Original LaTeX source
        patches: List of verified patches to apply

    Returns:
        Tuple of (revised_source, list of failed patch unit_ids)
    """
    revised = original_source
    failed = []

    # Sort by offset descending to avoid offset drift
    sorted_patches = sort_patches_reverse(patches)

    for patch in sorted_patches:
        try:
            revised = apply_patch(revised, patch)
        except ValueError as e:
            failed.append(patch.unit_id)

    return revised, failed


def verify_document_integrity(
    source_text: str,
    expected_concepts: set,
    expected_protected: set,
) -> tuple[bool, List[str]]:
    """Verify revised document has expected content.

    Args:
        source_text: Revised LaTeX source
        expected_concepts: Concept IDs that should appear
        expected_protected: Protected object IDs that should appear

    Returns:
        Tuple of (is_valid, list of missing items)
    """
    missing = []

    # Check for concept mentions (placeholder; full check would parse LaTeX)
    for concept_id in expected_concepts:
        if concept_id not in source_text:
            missing.append(f"concept:{concept_id}")

    # Check for protected object markers
    for obj_id in expected_protected:
        if obj_id not in source_text:
            missing.append(f"protected:{obj_id}")

    is_valid = len(missing) == 0

    return is_valid, missing


def save_patched_source(
    source_text: str,
    output_path: Path,
) -> None:
    """Save revised source to disk.

    Args:
        source_text: Revised LaTeX source
        output_path: Path to write .tex file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        f.write(source_text)


def save_assembly_result(result: PatchAssemblyResult, output_path: Path) -> None:
    """Save assembly result metadata to JSON.

    Args:
        result: PatchAssemblyResult
        output_path: Path to write JSON file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "snapshot_id": result.snapshot_id,
            "total_patches": result.total_patches,
            "patches_applied": result.patches_applied,
            "patches_failed": result.patches_failed,
            "original_source_hash": result.original_source_hash,
            "revised_source_hash": result.revised_source_hash,
            "untouched_bytes": result.untouched_bytes_count,
            "revised_bytes": result.revised_bytes_count,
            "assembly_complete": result.assembly_complete,
            "document_builds": result.document_builds,
            "comparison_generated": result.comparison_generated,
        }, f, indent=2)
