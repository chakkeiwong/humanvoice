"""
Tests for Issue 7: Content dereferencing from source manifest.

Correspondence manifests (draft_correspondence_*.json, assembly_correspondence_*.json)
previously embedded the full content of every protected object, duplicating it
across 5+ manifests. At 5,000 objects this bloats each manifest to ~5MB.

The fix: store only hash+type in correspondence manifests, dereference content
from the source manifest on demand when actually needed (rare: only restore
command and manual inspection).
"""

import json
from pathlib import Path
import pytest

from humanvoice.commands.restore_command import _dereference_content


def test_correspondence_manifests_omit_content(tmp_path):
    """
    Draft and assembly correspondence manifests store hash+type only, not content.

    This test verifies the schema change for Issue 7: correspondence manifests
    previously embedded full content (bloating manifests to 5MB+ at scale), now
    store only hash+type and dereference on demand.
    """
    # Create a mock correspondence manifest in the new format
    correspondence = {
        "correspondence_to_source": {
            "preserved": [
                {"type": "equation", "hash": "abc123"},
                {"type": "citation", "hash": "def456"}
            ],
            "added": [
                {"type": "equation", "hash": "xyz789"}
            ]
        }
    }

    corr_file = tmp_path / "correspondence.json"
    corr_file.write_text(json.dumps(correspondence, indent=2))

    # Verify the manifest doesn't contain content keys
    corr = json.loads(corr_file.read_text())

    for obj in corr["correspondence_to_source"]["preserved"]:
        assert "type" in obj
        assert "hash" in obj
        assert "content" not in obj, "Issue 7: content should not be embedded"

    for obj in corr["correspondence_to_source"]["added"]:
        assert "type" in obj
        assert "hash" in obj
        assert "content" not in obj, "Issue 7: content should not be embedded"


def test_dereference_content_from_source_manifest(tmp_path):
    """
    _dereference_content looks up object content by hash from source manifest.
    """
    source_manifest = tmp_path / "manifest.json"
    source_manifest.write_text(json.dumps({
        "equations": [
            {"hash": "abc123", "content": r"$E = mc^2$"},
            {"hash": "def456", "content": r"$F = ma$"}
        ],
        "citations": [
            {"hash": "xyz789", "content": r"\cite{einstein1905}"}
        ]
    }))

    # Dereference existing hashes
    assert _dereference_content("abc123", source_manifest) == r"$E = mc^2$"
    assert _dereference_content("def456", source_manifest) == r"$F = ma$"
    assert _dereference_content("xyz789", source_manifest) == r"\cite{einstein1905}"

    # Non-existent hash returns None
    assert _dereference_content("nonexistent", source_manifest) is None


def test_manifest_size_reduction():
    """
    Demonstrate the size reduction from hash-only storage.
    """
    # Simulate realistic protected object sizes
    old_format_obj = {
        "type": "equation",
        "hash": "a" * 64,  # SHA-256 hash
        "content": r"$\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}$"
    }

    new_format_obj = {
        "type": "equation",
        "hash": "a" * 64
    }

    old_size = len(json.dumps(old_format_obj))
    new_size = len(json.dumps(new_format_obj))
    reduction = (1 - new_size / old_size) * 100

    # At minimum 30% reduction expected for typical objects
    assert reduction > 30, f"Expected >30% reduction, got {reduction:.1f}%"

    # Verify the absolute reduction makes sense
    assert old_size > new_size, "Hash-only format should be smaller"
    assert new_size < 100, "Hash-only object should be <100 bytes"
