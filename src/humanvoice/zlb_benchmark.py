"""
ZLB benchmark setup for WP-V2-6.

Master Program v2 requires "the complete ZLB benchmark" as part of V2-G6.

This module prepares the ZLB (Zero Lower Bound) manuscript for:
1. Source snapshot creation
2. Concept inventory extraction
3. Teaching plan generation
4. Full pipeline execution
5. Reader evaluation collection
"""

from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path
import json


@dataclass
class ZLBBenchmarkConfig:
    """Configuration for ZLB benchmark."""
    benchmark_id: str
    source_manuscript_path: Path
    output_dir: Path

    # Reader evaluation
    target_reader_level: str = "graduate"  # Graduate economics students
    target_reader_count: int = 10
    evaluation_dimensions: List[str] = field(default_factory=lambda: [
        "concept_comprehension",
        "explanation_clarity",
        "readability",
        "technical_accuracy",
        "coherence",
    ])

    # Evaluation protocol
    within_subjects: bool = True  # Each reader sees both versions
    counterbalanced: bool = True  # Order of versions randomized


@dataclass
class ZLBFixture:
    """One test fixture for ZLB benchmark."""
    fixture_id: str
    fixture_type: str  # "unit" | "mutation" | "full_pipeline"

    # Inputs
    source_text: str
    concepts: List[str] = field(default_factory=list)
    obligations: List[str] = field(default_factory=list)

    # Expected outputs
    expected_concept_retention: float = 1.0
    expected_mutations_blocked: List[str] = field(default_factory=list)

    # Metadata
    description: str = ""
    rationale: str = ""


def create_zlb_benchmark_config(output_dir: Path) -> ZLBBenchmarkConfig:
    """Create default ZLB benchmark configuration.

    Args:
        output_dir: Directory for benchmark outputs

    Returns:
        ZLBBenchmarkConfig with defaults
    """
    config = ZLBBenchmarkConfig(
        benchmark_id="zlb-benchmark-001",
        source_manuscript_path=Path("fixtures/zlb_source.tex"),
        output_dir=output_dir,
    )

    return config


def create_unit_fixture(
    fixture_id: str,
    source_text: str,
    concepts: List[str],
    description: str,
) -> ZLBFixture:
    """Create a unit-level test fixture.

    Args:
        fixture_id: Unique fixture identifier
        source_text: Source LaTeX text
        concepts: Concept IDs that should be retained
        description: Human-readable description

    Returns:
        ZLBFixture for unit testing
    """
    fixture = ZLBFixture(
        fixture_id=fixture_id,
        fixture_type="unit",
        source_text=source_text,
        concepts=concepts,
        description=description,
        expected_concept_retention=1.0,
    )

    return fixture


def create_mutation_fixture(
    fixture_id: str,
    source_text: str,
    mutation_type: str,
    description: str,
) -> ZLBFixture:
    """Create a mutation test fixture.

    Args:
        fixture_id: Unique fixture identifier
        source_text: Source LaTeX text
        mutation_type: Type of mutation to test (deletion, addition, truncation)
        description: Human-readable description

    Returns:
        ZLBFixture for mutation testing
    """
    fixture = ZLBFixture(
        fixture_id=fixture_id,
        fixture_type="mutation",
        source_text=source_text,
        description=description,
        expected_mutations_blocked=[mutation_type],
    )

    return fixture


def save_zlb_config(config: ZLBBenchmarkConfig, output_path: Path) -> None:
    """Save ZLB benchmark configuration to JSON.

    Args:
        config: ZLBBenchmarkConfig
        output_path: Path to write JSON
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "benchmark_id": config.benchmark_id,
            "source_manuscript_path": str(config.source_manuscript_path),
            "output_dir": str(config.output_dir),
            "target_reader_level": config.target_reader_level,
            "target_reader_count": config.target_reader_count,
            "evaluation_dimensions": config.evaluation_dimensions,
            "within_subjects": config.within_subjects,
            "counterbalanced": config.counterbalanced,
        }, f, indent=2)


def save_fixture(fixture: ZLBFixture, output_path: Path) -> None:
    """Save test fixture to JSON.

    Args:
        fixture: ZLBFixture
        output_path: Path to write JSON
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "fixture_id": fixture.fixture_id,
            "fixture_type": fixture.fixture_type,
            "source_text": fixture.source_text,
            "concepts": fixture.concepts,
            "obligations": fixture.obligations,
            "expected_concept_retention": fixture.expected_concept_retention,
            "expected_mutations_blocked": fixture.expected_mutations_blocked,
            "description": fixture.description,
            "rationale": fixture.rationale,
        }, f, indent=2)


def load_fixture(fixture_path: Path) -> ZLBFixture:
    """Load test fixture from JSON.

    Args:
        fixture_path: Path to fixture JSON

    Returns:
        ZLBFixture loaded from file
    """
    with open(fixture_path) as f:
        data = json.load(f)

    fixture = ZLBFixture(
        fixture_id=data["fixture_id"],
        fixture_type=data["fixture_type"],
        source_text=data["source_text"],
        concepts=data.get("concepts", []),
        obligations=data.get("obligations", []),
        expected_concept_retention=data.get("expected_concept_retention", 1.0),
        expected_mutations_blocked=data.get("expected_mutations_blocked", []),
        description=data.get("description", ""),
        rationale=data.get("rationale", ""),
    )

    return fixture


# Example ZLB unit fixtures
ZLB_UNIT_FIXTURES = [
    {
        "fixture_id": "zlb-unit-001",
        "source_text": "When nominal interest rates approach zero, the central bank cannot cut rates further to stimulate the economy.",
        "concepts": ["zlb-constraint", "monetary-policy-limit"],
        "description": "Core ZLB constraint explanation",
    },
    {
        "fixture_id": "zlb-unit-002",
        "source_text": "Forward guidance about future policy rates can influence current expectations and economic decisions.",
        "concepts": ["forward-guidance", "expectations-channel"],
        "description": "Forward guidance mechanism",
    },
    {
        "fixture_id": "zlb-unit-003",
        "source_text": "Quantitative easing involves central bank purchases of long-term securities to lower long-term interest rates.",
        "concepts": ["quantitative-easing", "asset-purchases"],
        "description": "QE definition and mechanism",
    },
]


# Example ZLB mutation fixtures
ZLB_MUTATION_FIXTURES = [
    {
        "fixture_id": "zlb-mutation-001",
        "source_text": "The zero lower bound constrains monetary policy. Forward guidance can help.",
        "mutation_type": "concept_deletion",
        "description": "Test blocking of concept deletion (remove 'forward guidance')",
    },
    {
        "fixture_id": "zlb-mutation-002",
        "source_text": "Interest rates cannot go below zero.",
        "mutation_type": "unsupported_addition",
        "description": "Test blocking of adding concepts not in source",
    },
    {
        "fixture_id": "zlb-mutation-003",
        "source_text": "The central bank uses various tools including...",
        "mutation_type": "truncation",
        "description": "Test blocking of incomplete output",
    },
]
