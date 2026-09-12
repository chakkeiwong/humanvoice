"""
Tests for ZLB benchmark setup and fixtures.

Tests benchmark configuration and fixture management:
- Configuration creation and persistence
- Unit fixture creation
- Mutation fixture creation
- Fixture loading and validation
"""

import pytest
from pathlib import Path

from humanvoice.zlb_benchmark import (
    ZLBBenchmarkConfig,
    ZLBFixture,
    create_zlb_benchmark_config,
    create_unit_fixture,
    create_mutation_fixture,
    save_zlb_config,
    save_fixture,
    load_fixture,
    ZLB_UNIT_FIXTURES,
    ZLB_MUTATION_FIXTURES,
)


def test_create_zlb_benchmark_config(tmp_path):
    """ZLB benchmark config created with defaults."""
    config = create_zlb_benchmark_config(tmp_path)

    assert config.benchmark_id == "zlb-benchmark-001"
    assert config.target_reader_level == "graduate"
    assert config.target_reader_count == 10
    assert "concept_comprehension" in config.evaluation_dimensions


def test_zlb_config_fields():
    """ZLBBenchmarkConfig contains all required fields."""
    config = ZLBBenchmarkConfig(
        benchmark_id="bench-001",
        source_manuscript_path=Path("source.tex"),
        output_dir=Path("output"),
    )

    assert config.benchmark_id == "bench-001"
    assert config.target_reader_level == "graduate"
    assert config.within_subjects
    assert config.counterbalanced


def test_create_unit_fixture():
    """Unit fixture created with correct fields."""
    fixture = create_unit_fixture(
        fixture_id="unit-001",
        source_text="The ZLB constrains policy.",
        concepts=["zlb", "constraint"],
        description="Test ZLB concept",
    )

    assert fixture.fixture_id == "unit-001"
    assert fixture.fixture_type == "unit"
    assert "ZLB" in fixture.source_text
    assert len(fixture.concepts) == 2
    assert fixture.expected_concept_retention == 1.0


def test_create_mutation_fixture():
    """Mutation fixture created with correct fields."""
    fixture = create_mutation_fixture(
        fixture_id="mut-001",
        source_text="Test text",
        mutation_type="deletion",
        description="Test concept deletion blocking",
    )

    assert fixture.fixture_id == "mut-001"
    assert fixture.fixture_type == "mutation"
    assert "deletion" in fixture.expected_mutations_blocked


def test_save_and_load_zlb_config(tmp_path):
    """ZLB config persisted and loaded correctly."""
    config = ZLBBenchmarkConfig(
        benchmark_id="bench-001",
        source_manuscript_path=Path("source.tex"),
        output_dir=tmp_path,
        target_reader_count=15,
    )

    config_file = tmp_path / "config.json"
    save_zlb_config(config, config_file)

    assert config_file.exists()

    import json
    with open(config_file) as f:
        data = json.load(f)

    assert data["benchmark_id"] == "bench-001"
    assert data["target_reader_count"] == 15


def test_save_and_load_unit_fixture(tmp_path):
    """Unit fixture persisted and loaded correctly."""
    fixture = create_unit_fixture(
        fixture_id="unit-001",
        source_text="Test text",
        concepts=["c1", "c2"],
        description="Test fixture",
    )

    fixture_file = tmp_path / "fixture.json"
    save_fixture(fixture, fixture_file)

    loaded = load_fixture(fixture_file)

    assert loaded.fixture_id == "unit-001"
    assert loaded.fixture_type == "unit"
    assert loaded.concepts == ["c1", "c2"]
    assert loaded.expected_concept_retention == 1.0


def test_save_and_load_mutation_fixture(tmp_path):
    """Mutation fixture persisted and loaded correctly."""
    fixture = create_mutation_fixture(
        fixture_id="mut-001",
        source_text="Test text",
        mutation_type="truncation",
        description="Test truncation blocking",
    )

    fixture_file = tmp_path / "fixture.json"
    save_fixture(fixture, fixture_file)

    loaded = load_fixture(fixture_file)

    assert loaded.fixture_id == "mut-001"
    assert loaded.fixture_type == "mutation"
    assert "truncation" in loaded.expected_mutations_blocked


def test_zlb_unit_fixtures_predefined():
    """Predefined ZLB unit fixtures available."""
    assert len(ZLB_UNIT_FIXTURES) > 0

    first = ZLB_UNIT_FIXTURES[0]
    assert "fixture_id" in first
    assert "source_text" in first
    assert "concepts" in first


def test_zlb_mutation_fixtures_predefined():
    """Predefined ZLB mutation fixtures available."""
    assert len(ZLB_MUTATION_FIXTURES) > 0

    first = ZLB_MUTATION_FIXTURES[0]
    assert "fixture_id" in first
    assert "mutation_type" in first


def test_zlb_fixture_with_obligations():
    """ZLB fixture supports obligations."""
    fixture = ZLBFixture(
        fixture_id="unit-001",
        fixture_type="unit",
        source_text="Text",
        concepts=["c1"],
        obligations=["definition", "example"],
    )

    assert len(fixture.obligations) == 2
    assert "definition" in fixture.obligations


def test_evaluation_dimensions_complete():
    """All required evaluation dimensions present."""
    config = create_zlb_benchmark_config(Path("/tmp"))

    required = [
        "concept_comprehension",
        "explanation_clarity",
        "readability",
        "technical_accuracy",
        "coherence",
    ]

    for dimension in required:
        assert dimension in config.evaluation_dimensions


def test_within_subjects_design():
    """Within-subjects design configured correctly."""
    config = create_zlb_benchmark_config(Path("/tmp"))

    assert config.within_subjects
    assert config.counterbalanced


def test_fixture_rationale_field():
    """Fixture supports rationale field."""
    fixture = ZLBFixture(
        fixture_id="unit-001",
        fixture_type="unit",
        source_text="Text",
        rationale="Tests core ZLB concept retention",
    )

    assert fixture.rationale == "Tests core ZLB concept retention"
