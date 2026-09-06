"""
Tests for Issue 4: Subsection decomposition.

Large documents (25k-145k words) need chapters broken into subsections of
800-1200 words each. The blueprint schema gains a two-level hierarchy:
chapters[].subsections[], where unit = subsection.

Draft and assembly commands work per-unit and flatten the hierarchy on load,
maintaining backward compatibility with legacy sections[] blueprints.
"""

import json
from pathlib import Path
import pytest
from argparse import Namespace

from humanvoice.commands import draft_command, assemble_command


def test_draft_loads_legacy_sections_blueprint(tmp_path):
    """
    Legacy blueprints with sections[] still work.
    """
    blueprint = tmp_path / "blueprint.json"
    blueprint.write_text(json.dumps({
        "blueprint": {
            "sections": [
                {"title": "Section 1", "purpose": "test", "word_budget": 500,
                 "source_start_line": 1, "source_end_line": 10},
                {"title": "Section 2", "purpose": "test", "word_budget": 600,
                 "source_start_line": 11, "source_end_line": 20}
            ]
        }
    }))

    loaded = draft_command._load_blueprint(blueprint)
    sections = loaded["blueprint"]["sections"]

    assert len(sections) == 2
    assert sections[0]["title"] == "Section 1"
    assert sections[1]["title"] == "Section 2"


def test_draft_loads_chapters_subsections_blueprint(tmp_path):
    """
    New blueprints with chapters[].subsections[] are flattened to sections[].
    """
    blueprint = tmp_path / "blueprint.json"
    blueprint.write_text(json.dumps({
        "blueprint": {
            "chapters": [
                {
                    "title": "Chapter 1",
                    "subsections": [
                        {"title": "Subsection 1.1", "purpose": "intro",
                         "word_budget": 800, "source_start_line": 1, "source_end_line": 15},
                        {"title": "Subsection 1.2", "purpose": "main",
                         "word_budget": 1000, "source_start_line": 16, "source_end_line": 30}
                    ]
                },
                {
                    "title": "Chapter 2",
                    "subsections": [
                        {"title": "Subsection 2.1", "purpose": "analysis",
                         "word_budget": 900, "source_start_line": 31, "source_end_line": 45}
                    ]
                }
            ]
        }
    }))

    loaded = draft_command._load_blueprint(blueprint)
    sections = loaded["blueprint"]["sections"]

    # Flattened to 3 units
    assert len(sections) == 3

    # First chapter's subsections
    assert sections[0]["title"] == "Subsection 1.1"
    assert sections[0]["chapter_index"] == 0
    assert sections[0]["chapter_title"] == "Chapter 1"
    assert sections[0]["subsection_index"] == 0
    assert sections[0]["word_budget"] == 800

    assert sections[1]["title"] == "Subsection 1.2"
    assert sections[1]["chapter_index"] == 0
    assert sections[1]["chapter_title"] == "Chapter 1"
    assert sections[1]["subsection_index"] == 1

    # Second chapter's subsection
    assert sections[2]["title"] == "Subsection 2.1"
    assert sections[2]["chapter_index"] == 1
    assert sections[2]["chapter_title"] == "Chapter 2"
    assert sections[2]["subsection_index"] == 0


def test_assembly_loads_chapters_subsections_blueprint(tmp_path):
    """
    Assembly command also flattens chapters[].subsections[] for sequential assembly.
    """
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / ".humanvoice" / "runs").mkdir(parents=True)

    # Manifest
    (snapshot / "manifest.json").write_text(json.dumps({
        "source_files": [],
        "protected_objects": []
    }))

    # Blueprint with chapters
    (snapshot / "blueprint.json").write_text(json.dumps({
        "blueprint": {
            "chapters": [
                {
                    "title": "Introduction",
                    "subsections": [
                        {"title": "Background", "purpose": "context",
                         "word_budget": 800, "source_start_line": 1, "source_end_line": 20}
                    ]
                },
                {
                    "title": "Methods",
                    "subsections": [
                        {"title": "Data Collection", "purpose": "methods",
                         "word_budget": 1000, "source_start_line": 21, "source_end_line": 40},
                        {"title": "Analysis", "purpose": "methods",
                         "word_budget": 900, "source_start_line": 41, "source_end_line": 60}
                    ]
                }
            ]
        }
    }))

    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"register": "third-person"}))

    # Assembly should handle the flattened units
    # (This will exit 2 because no drafts exist, but should not error on blueprint structure)
    exit_code = assemble_command.run(Namespace(
        snapshot=snapshot,
        brief=brief
    ))

    # Exit 2 = abstention (missing drafts), not 3 (invalid input)
    assert exit_code == 2


def test_blueprint_without_sections_or_chapters_rejected(tmp_path):
    """
    Blueprints missing both sections[] and chapters[] are rejected.
    """
    blueprint = tmp_path / "blueprint.json"
    blueprint.write_text(json.dumps({
        "blueprint": {}
    }))

    with pytest.raises(ValueError, match="must have 'sections'.*or 'chapters'"):
        draft_command._load_blueprint(blueprint)


def test_chapter_metadata_preserved_through_flattening(tmp_path):
    """
    Chapter context (index, title) is preserved when flattening for assembly.
    """
    blueprint = tmp_path / "blueprint.json"
    blueprint.write_text(json.dumps({
        "blueprint": {
            "chapters": [
                {
                    "title": "Literature Review",
                    "subsections": [
                        {"title": "Prior Work", "purpose": "review",
                         "word_budget": 1200, "source_start_line": 1, "source_end_line": 25}
                    ]
                }
            ]
        }
    }))

    loaded = draft_command._load_blueprint(blueprint)
    unit = loaded["blueprint"]["sections"][0]

    # Chapter metadata should be attached to each unit for assembly grouping
    assert "chapter_index" in unit
    assert "chapter_title" in unit
    assert "subsection_index" in unit
    assert unit["chapter_title"] == "Literature Review"
