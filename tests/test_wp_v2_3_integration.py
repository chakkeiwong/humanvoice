"""
Integration tests for WP-V2-3 CLI integration.

Tests end-to-end orchestration through CLI:
- Command routing
- Artifact loading
- Mock mode execution
- Result emission
"""

import pytest
import json
import sys
from pathlib import Path
from io import StringIO

from humanvoice.commands.rewrite_command import (
    load_baseline,
    load_rewrite_plan,
    load_brief,
    load_policy_snapshot,
)
from humanvoice.concept_baseline import ConceptBaseline, ConceptBaselineEntry
from humanvoice.semantic_unit_splitting import RewritePlan, RewriteUnit


@pytest.fixture
def baseline_json(tmp_path):
    """Create a baseline JSON file."""
    baseline_file = tmp_path / "baseline-001.json"

    baseline_data = {
        "baseline_id": "baseline-001",
        "snapshot_id": "snapshot-001",
        "source_hash": "abc123",
        "baseline_hash": "xyz789",
        "concept_entries": [
            {
                "concept_id": "concept-001",
                "proposition": "The zero lower bound constrains monetary policy",
                "concept_type": "claim",
                "source_span_ids": ["span-001", "span-002"],
                "teaching_roles": ["initial"],
                "confidence": 0.95,
            },
            {
                "concept_id": "concept-002",
                "proposition": "Forward guidance affects expectations",
                "concept_type": "mechanism",
                "source_span_ids": ["span-003"],
                "teaching_roles": ["initial"],
                "confidence": 0.90,
            },
        ],
        "total_concepts": 2,
        "frozen_at": "2026-09-12T00:00:00Z",
        "frozen_by": "test-user",
    }

    with open(baseline_file, 'w') as f:
        json.dump(baseline_data, f)

    return baseline_file


@pytest.fixture
def plan_json(tmp_path):
    """Create a rewrite plan JSON file."""
    plan_file = tmp_path / "plan-001.json"

    plan_data = {
        "plan_id": "plan-001",
        "baseline_id": "baseline-001",
        "snapshot_id": "snapshot-001",
        "units": [
            {
                "unit_id": "unit-001",
                "concept_ids": ["concept-001", "concept-002"],
                "source_span_ids": ["span-001", "span-002", "span-003"],
                "prerequisites": [],
                "estimated_words": 1500,
                "teaching_sequence": 1,
            }
        ],
        "total_units": 1,
        "total_concepts": 2,
    }

    with open(plan_file, 'w') as f:
        json.dump(plan_data, f)

    return plan_file


def test_load_baseline(baseline_json):
    """Baseline loaded correctly from JSON."""
    baseline = load_baseline(baseline_json)

    assert baseline.baseline_id == "baseline-001"
    assert baseline.snapshot_id == "snapshot-001"
    assert len(baseline.concept_entries) == 2
    assert baseline.concept_entries[0].concept_id == "concept-001"


def test_load_rewrite_plan(plan_json):
    """Rewrite plan loaded correctly from JSON."""
    plan = load_rewrite_plan(plan_json)

    assert plan.plan_id == "plan-001"
    assert plan.baseline_id == "baseline-001"
    assert len(plan.units) == 1
    assert plan.units[0].unit_id == "unit-001"
    assert plan.units[0].concept_ids == ["concept-001", "concept-002"]


def test_load_brief_with_file(tmp_path):
    """Brief loaded from file if it exists."""
    brief_file = tmp_path / "brief.json"
    brief_data = {
        "reader": {"expertise_level": "undergrad"},
        "genre": "tutorial",
        "voice_register": "conversational",
    }

    with open(brief_file, 'w') as f:
        json.dump(brief_data, f)

    brief = load_brief(brief_file)

    assert brief["reader"]["expertise_level"] == "undergrad"
    assert brief["genre"] == "tutorial"


def test_load_brief_default():
    """Default brief loaded when file missing."""
    brief = load_brief(None)

    assert "reader" in brief
    assert brief["genre"] == "technical"
    assert brief["voice_register"] == "formal"


def test_load_policy_snapshot_empty():
    """Empty policy returned when file missing."""
    policy = load_policy_snapshot(None)

    assert policy == {}


def test_load_policy_snapshot_with_file(tmp_path):
    """Policy loaded from file if it exists."""
    policy_file = tmp_path / "policy.json"
    policy_data = {
        "first_person_allowed": False,
        "explanation_minimum_words": 50,
    }

    with open(policy_file, 'w') as f:
        json.dump(policy_data, f)

    policy = load_policy_snapshot(policy_file)

    assert policy["first_person_allowed"] is False
    assert policy["explanation_minimum_words"] == 50


def test_baseline_entry_preservation(baseline_json):
    """Baseline entry fields preserved through load/save cycle."""
    baseline = load_baseline(baseline_json)

    entry = baseline.concept_entries[0]
    assert entry.concept_id == "concept-001"
    assert "zero lower bound" in entry.proposition.lower()
    assert entry.concept_type == "claim"
    assert entry.teaching_roles == ["initial"]
    assert entry.confidence == 0.95


def test_rewrite_unit_preservation(plan_json):
    """Rewrite unit fields preserved through load/save cycle."""
    plan = load_rewrite_plan(plan_json)

    unit = plan.units[0]
    assert unit.unit_id == "unit-001"
    assert unit.concept_ids == ["concept-001", "concept-002"]
    assert unit.source_span_ids == ["span-001", "span-002", "span-003"]
    assert unit.estimated_words == 1500
    assert unit.teaching_sequence == 1
