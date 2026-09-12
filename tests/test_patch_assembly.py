"""
Tests for WP-V2-5 patch assembly.

Tests patch-based document assembly:
- Patch sorting and application
- Offset preservation
- Document integrity verification
- Result persistence
"""

import pytest
from pathlib import Path
from hashlib import sha256

from humanvoice.patch_assembly import (
    SourcePatch,
    PatchAssemblyResult,
    sort_patches_reverse,
    apply_patch,
    assemble_document,
    verify_document_integrity,
    save_patched_source,
    save_assembly_result,
)


@pytest.fixture
def sample_source():
    """Sample LaTeX source for testing."""
    return """\\documentclass{article}
\\begin{document}

The zero lower bound constrains monetary policy.
Forward guidance affects expectations.

\\end{document}
"""


def test_sort_patches_reverse():
    """Patches sorted by offset descending."""
    patches = [
        SourcePatch("u1", [], 10, 20, "text1", "replacement1"),
        SourcePatch("u3", [], 50, 60, "text3", "replacement3"),
        SourcePatch("u2", [], 30, 40, "text2", "replacement2"),
    ]

    sorted_patches = sort_patches_reverse(patches)

    assert sorted_patches[0].end_offset == 60
    assert sorted_patches[1].end_offset == 40
    assert sorted_patches[2].end_offset == 20


def test_apply_patch_valid():
    """Patch applied successfully."""
    source = "The quick brown fox"
    patch = SourcePatch(
        unit_id="u1",
        source_span_ids=["s1"],
        start_offset=4,
        end_offset=9,
        original_text="quick",
        replacement_text="slow",
    )

    result = apply_patch(source, patch)

    assert result == "The slow brown fox"


def test_apply_patch_beginning():
    """Patch at beginning of source."""
    source = "The quick brown"
    patch = SourcePatch(
        unit_id="u1",
        source_span_ids=[],
        start_offset=0,
        end_offset=3,
        original_text="The",
        replacement_text="A",
    )

    result = apply_patch(source, patch)

    assert result == "A quick brown"


def test_apply_patch_end():
    """Patch at end of source."""
    source = "The quick brown"
    patch = SourcePatch(
        unit_id="u1",
        source_span_ids=[],
        start_offset=10,
        end_offset=15,
        original_text="brown",
        replacement_text="fox",
    )

    result = apply_patch(source, patch)

    assert result == "The quick fox"


def test_apply_patch_offset_mismatch():
    """Patch fails with offset mismatch."""
    source = "The quick brown"
    patch = SourcePatch(
        unit_id="u1",
        source_span_ids=[],
        start_offset=4,
        end_offset=9,
        original_text="wrong",  # Should be "quick"
        replacement_text="slow",
    )

    with pytest.raises(ValueError, match="Original text mismatch"):
        apply_patch(source, patch)


def test_apply_patch_out_of_bounds():
    """Patch fails with offsets out of bounds."""
    source = "The quick"
    patch = SourcePatch(
        unit_id="u1",
        source_span_ids=[],
        start_offset=0,
        end_offset=100,  # Beyond source length
        original_text="The quick",
        replacement_text="A fast",
    )

    with pytest.raises(ValueError, match="out of bounds"):
        apply_patch(source, patch)


def test_assemble_document_single_patch():
    """Document assembled with single patch."""
    source = "The quick brown fox"
    patch = SourcePatch(
        unit_id="u1",
        source_span_ids=[],
        start_offset=4,
        end_offset=9,
        original_text="quick",
        replacement_text="slow",
        concept_ids=["c1"],
        verified=True,
    )

    revised, failed = assemble_document(source, [patch])

    assert revised == "The slow brown fox"
    assert len(failed) == 0


def test_assemble_document_multiple_patches():
    """Document assembled with multiple patches (reverse offset order)."""
    source = "The quick brown fox"

    patches = [
        SourcePatch("u1", [], 10, 15, "brown", "red", ["c1"], True),
        SourcePatch("u2", [], 4, 9, "quick", "slow", ["c2"], True),
    ]

    revised, failed = assemble_document(source, patches)

    assert revised == "The slow red fox"
    assert len(failed) == 0


def test_assemble_document_with_failure():
    """Patch failure tracked but doesn't stop assembly."""
    source = "The quick brown fox"

    patches = [
        SourcePatch("u1", [], 10, 15, "brown", "red", ["c1"], True),
        SourcePatch("u2", [], 0, 3, "wrong", "slow", ["c2"], True),  # Will fail
        SourcePatch("u3", [], 4, 9, "quick", "fast", ["c3"], True),
    ]

    revised, failed = assemble_document(source, patches)

    # u2 should fail, but others should apply
    assert "u2" in failed
    assert revised == "The fast red fox"


def test_verify_document_integrity_complete():
    """Document integrity verified when all content present."""
    source = "concept-001 and concept-002 with protected-obj-001"

    is_valid, missing = verify_document_integrity(
        source,
        expected_concepts={"concept-001", "concept-002"},
        expected_protected={"protected-obj-001"},
    )

    assert is_valid
    assert len(missing) == 0


def test_verify_document_integrity_missing_concept():
    """Document integrity fails when concept missing."""
    source = "concept-001 with protected-obj-001"

    is_valid, missing = verify_document_integrity(
        source,
        expected_concepts={"concept-001", "concept-002"},
        expected_protected={"protected-obj-001"},
    )

    assert not is_valid
    assert "concept:concept-002" in missing


def test_verify_document_integrity_missing_protected():
    """Document integrity fails when protected object missing."""
    source = "concept-001 and concept-002"

    is_valid, missing = verify_document_integrity(
        source,
        expected_concepts={"concept-001", "concept-002"},
        expected_protected={"protected-obj-001"},
    )

    assert not is_valid
    assert "protected:protected-obj-001" in missing


def test_patch_assembly_result_initialization():
    """PatchAssemblyResult initializes with default values."""
    result = PatchAssemblyResult(snapshot_id="snapshot-001")

    assert result.snapshot_id == "snapshot-001"
    assert result.total_patches == 0
    assert result.patches_applied == 0
    assert not result.assembly_complete
    assert not result.document_builds


def test_save_patched_source(tmp_path):
    """Revised source saved to disk."""
    output_file = tmp_path / "revised.tex"
    source_text = "\\documentclass{article}\n\\begin{document}\nRevised content\n\\end{document}"

    save_patched_source(source_text, output_file)

    assert output_file.exists()

    with open(output_file) as f:
        content = f.read()

    assert content == source_text


def test_save_assembly_result(tmp_path):
    """Assembly result saved to JSON."""
    result = PatchAssemblyResult(
        snapshot_id="snapshot-001",
        total_patches=3,
        patches_applied=3,
        patches_failed=[],
        original_source_hash="abc123",
        revised_source_hash="def456",
        untouched_bytes_count=500,
        revised_bytes_count=520,
        assembly_complete=True,
        document_builds=True,
        comparison_generated=True,
    )

    output_file = tmp_path / "result.json"
    save_assembly_result(result, output_file)

    assert output_file.exists()

    import json
    with open(output_file) as f:
        data = json.load(f)

    assert data["snapshot_id"] == "snapshot-001"
    assert data["patches_applied"] == 3
    assert data["assembly_complete"]


def test_source_patch_fields():
    """SourcePatch contains all required fields."""
    patch = SourcePatch(
        unit_id="u1",
        source_span_ids=["s1", "s2"],
        start_offset=10,
        end_offset=20,
        original_text="text",
        replacement_text="revised",
        concept_ids=["c1"],
        verified=True,
    )

    assert patch.unit_id == "u1"
    assert patch.source_span_ids == ["s1", "s2"]
    assert patch.start_offset == 10
    assert patch.end_offset == 20
    assert patch.verified
    assert patch.concept_ids == ["c1"]


def test_assemble_preserves_untouched_regions(sample_source):
    """Assembly preserves regions not touched by patches."""
    # Find actual offset of "The zero lower bound constrains" in sample_source
    target_text = "The zero lower bound constrains"
    start_offset = sample_source.find(target_text)
    end_offset = start_offset + len(target_text)

    patch = SourcePatch(
        unit_id="u1",
        source_span_ids=[],
        start_offset=start_offset,
        end_offset=end_offset,
        original_text=target_text,
        replacement_text="ZLB is a constraint on",
    )

    revised, failed = assemble_document(sample_source, [patch])

    # Check that beginning and end are unchanged
    assert revised.startswith(sample_source[:start_offset])
    assert revised.endswith(sample_source[end_offset:])
    assert len(failed) == 0


def test_patch_ordering_critical():
    """Patch ordering is critical for correctness."""
    source = "ABCDEFGH"

    # Both patches target the same region but at different offsets
    patches = [
        SourcePatch("u1", [], 2, 4, "CD", "XY", [], True),  # offset 2-4
        SourcePatch("u2", [], 0, 2, "AB", "12", [], True),  # offset 0-2
    ]

    revised, failed = assemble_document(source, patches)

    # Applied in reverse order: u1 first (higher offset), then u2
    assert revised == "12XYEFGH"
    assert len(failed) == 0
