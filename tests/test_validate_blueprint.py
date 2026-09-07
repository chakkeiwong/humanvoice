"""
Test blueprint validation against token ceiling
"""

import json
import tempfile
from pathlib import Path

from humanvoice.commands.validate_blueprint_command import (
    validate_blueprint,
    _check_subsection,
    SAFE_CEILING
)


def test_safe_subsection():
    """Test that a 500-word subsection passes validation"""
    subsection = {
        "title": "Safe subsection",
        "word_budget": 500
    }

    is_safe, message = _check_subsection(subsection, 0, 0)
    assert is_safe
    assert "500w" in message
    assert "✓" in message


def test_unsafe_subsection():
    """Test that a 2000-word subsection fails validation"""
    subsection = {
        "title": "Oversized subsection",
        "word_budget": 2000
    }

    is_safe, message = _check_subsection(subsection, 0, 0)
    assert not is_safe
    assert "2000" in message
    assert "✗" in message
    assert "Split into" in message


def test_boundary_subsection():
    """Test subsection at the edge of safe ceiling"""
    # Safe ceiling is 7372 tokens (90% of 8192)
    # At 4 tokens/word with 1.2 variance: max_safe = 7372 / (4 * 1.2) = 1535.8 words
    # So 1536 should pass (barely), but 1537 should fail
    subsection_pass = {
        "title": "Just under boundary",
        "word_budget": 1535
    }
    subsection_fail = {
        "title": "Just over boundary",
        "word_budget": 1537
    }

    is_safe_pass, _ = _check_subsection(subsection_pass, 0, 0)
    is_safe_fail, _ = _check_subsection(subsection_fail, 0, 0)

    assert is_safe_pass
    assert not is_safe_fail


def test_validate_blueprint_all_safe():
    """Test validation of a blueprint with all safe subsections"""
    blueprint = {
        "blueprint": {
            "chapters": [
                {
                    "title": "Chapter 1",
                    "subsections": [
                        {"title": "Sub 1", "word_budget": 500},
                        {"title": "Sub 2", "word_budget": 600}
                    ]
                },
                {
                    "title": "Chapter 2",
                    "subsections": [
                        {"title": "Sub 3", "word_budget": 400}
                    ]
                }
            ]
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(blueprint, f)
        blueprint_path = Path(f.name)

    try:
        result = validate_blueprint(blueprint_path, verbose=False)
        assert result == 0
    finally:
        blueprint_path.unlink()


def test_validate_blueprint_has_unsafe():
    """Test validation of a blueprint with unsafe subsections"""
    blueprint = {
        "blueprint": {
            "chapters": [
                {
                    "title": "Chapter 1",
                    "subsections": [
                        {"title": "Safe", "word_budget": 500},
                        {"title": "Oversized", "word_budget": 2000}
                    ]
                }
            ]
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(blueprint, f)
        blueprint_path = Path(f.name)

    try:
        result = validate_blueprint(blueprint_path, verbose=False)
        assert result == 1
    finally:
        blueprint_path.unlink()


def test_validate_blueprint_missing_file():
    """Test validation with missing blueprint file"""
    result = validate_blueprint(Path("/nonexistent/blueprint.json"), verbose=False)
    assert result == 1
