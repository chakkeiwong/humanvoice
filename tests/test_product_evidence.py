"""
Tests for WP-V2-6 product evidence framework.

Tests evaluation and calibration infrastructure:
- Reader evaluation aggregation
- Version comparison (original vs revised)
- Benchmark result computation
- Critic calibration metrics
- Result persistence
"""

import pytest
from pathlib import Path

from humanvoice.product_evidence import (
    EvaluationDimension,
    ReaderLevel,
    ReaderEvaluation,
    BenchmarkResult,
    ReplayResult,
    CriticCalibration,
    aggregate_reader_scores,
    compare_versions,
    compute_benchmark_aggregates,
    compute_critic_metrics,
    save_benchmark_result,
    save_critic_calibration,
)


@pytest.fixture
def sample_evaluations():
    """Sample reader evaluations for testing."""
    return [
        ReaderEvaluation(
            reader_id="r1",
            reader_level=ReaderLevel.GRADUATE,
            document_id="doc1",
            document_version="revised",
            concept_comprehension_score=4.5,
            explanation_clarity_score=4.0,
            readability_score=4.2,
            technical_accuracy_score=4.8,
            coherence_score=4.3,
        ),
        ReaderEvaluation(
            reader_id="r2",
            reader_level=ReaderLevel.GRADUATE,
            document_id="doc1",
            document_version="revised",
            concept_comprehension_score=4.2,
            explanation_clarity_score=3.8,
            readability_score=4.0,
            technical_accuracy_score=4.5,
            coherence_score=4.1,
        ),
    ]


def test_reader_evaluation_initialization():
    """ReaderEvaluation initializes with correct fields."""
    eval = ReaderEvaluation(
        reader_id="reader-001",
        reader_level=ReaderLevel.GRADUATE,
        document_id="doc-001",
        document_version="revised",
    )

    assert eval.reader_id == "reader-001"
    assert eval.reader_level == ReaderLevel.GRADUATE
    assert eval.document_version == "revised"
    assert eval.concept_comprehension_score == 0.0


def test_aggregate_reader_scores_concept_retention(sample_evaluations):
    """Reader scores aggregated for concept retention."""
    avg, sample_size = aggregate_reader_scores(
        sample_evaluations,
        EvaluationDimension.CONCEPT_RETENTION,
    )

    assert sample_size == 2
    assert avg == pytest.approx((4.5 + 4.2) / 2)


def test_aggregate_reader_scores_readability(sample_evaluations):
    """Reader scores aggregated for readability."""
    avg, sample_size = aggregate_reader_scores(
        sample_evaluations,
        EvaluationDimension.READABILITY,
    )

    assert sample_size == 2
    assert avg == pytest.approx((4.2 + 4.0) / 2)


def test_aggregate_reader_scores_empty():
    """Aggregation returns 0.0 for empty evaluations."""
    avg, sample_size = aggregate_reader_scores(
        [],
        EvaluationDimension.CONCEPT_RETENTION,
    )

    assert avg == 0.0
    assert sample_size == 0


def test_aggregate_reader_scores_filters_zero():
    """Aggregation filters out zero scores."""
    evals = [
        ReaderEvaluation("r1", ReaderLevel.GRADUATE, "doc1", "revised", concept_comprehension_score=4.0),
        ReaderEvaluation("r2", ReaderLevel.GRADUATE, "doc1", "revised", concept_comprehension_score=0.0),  # Filtered
        ReaderEvaluation("r3", ReaderLevel.GRADUATE, "doc1", "revised", concept_comprehension_score=5.0),
    ]

    avg, sample_size = aggregate_reader_scores(
        evals,
        EvaluationDimension.CONCEPT_RETENTION,
    )

    assert sample_size == 2
    assert avg == pytest.approx((4.0 + 5.0) / 2)


def test_compare_versions():
    """Version comparison computes improvement."""
    original_evals = [
        ReaderEvaluation("r1", ReaderLevel.GRADUATE, "doc1", "original", concept_comprehension_score=3.0),
        ReaderEvaluation("r2", ReaderLevel.GRADUATE, "doc1", "original", concept_comprehension_score=3.2),
    ]

    revised_evals = [
        ReaderEvaluation("r1", ReaderLevel.GRADUATE, "doc1", "revised", concept_comprehension_score=4.5),
        ReaderEvaluation("r2", ReaderLevel.GRADUATE, "doc1", "revised", concept_comprehension_score=4.3),
    ]

    original_avg, revised_avg, improvement = compare_versions(
        original_evals,
        revised_evals,
        EvaluationDimension.CONCEPT_RETENTION,
    )

    assert original_avg == pytest.approx(3.1)
    assert revised_avg == pytest.approx(4.4)
    assert improvement == pytest.approx(1.3)


def test_compute_benchmark_aggregates(sample_evaluations):
    """Benchmark aggregates computed from reader evaluations."""
    benchmark = BenchmarkResult(
        benchmark_id="bench-001",
        document_id="doc-001",
        snapshot_id="snap-001",
        baseline_id="base-001",
        reader_evaluations=sample_evaluations,
    )

    result = compute_benchmark_aggregates(benchmark)

    assert result.sample_size == 2
    assert result.avg_concept_comprehension == pytest.approx(4.35)
    assert result.avg_readability == pytest.approx(4.1)


def test_compute_benchmark_aggregates_with_comparison():
    """Benchmark aggregates include original vs revised comparison."""
    original_evals = [
        ReaderEvaluation("r1", ReaderLevel.GRADUATE, "doc1", "original", concept_comprehension_score=3.0),
    ]

    revised_evals = [
        ReaderEvaluation("r2", ReaderLevel.GRADUATE, "doc1", "revised", concept_comprehension_score=4.5),
    ]

    benchmark = BenchmarkResult(
        benchmark_id="bench-001",
        document_id="doc-001",
        snapshot_id="snap-001",
        baseline_id="base-001",
        reader_evaluations=original_evals + revised_evals,
    )

    result = compute_benchmark_aggregates(benchmark)

    assert result.original_avg_comprehension == pytest.approx(3.0)
    assert result.revised_avg_comprehension == pytest.approx(4.5)
    assert result.comprehension_improvement == pytest.approx(1.5)


def test_critic_calibration_initialization():
    """CriticCalibration initializes with correct fields."""
    calibration = CriticCalibration(
        critic_name="concept_correspondence_critic",
        critic_function="concept_correspondence",
    )

    assert calibration.critic_name == "concept_correspondence_critic"
    assert calibration.critic_function == "concept_correspondence"
    assert calibration.test_cases_total == 0
    assert not calibration.calibrated


def test_compute_critic_metrics_perfect():
    """Critic metrics computed for perfect performance."""
    calibration = CriticCalibration(
        critic_name="test_critic",
        critic_function="test",
        test_cases_total=30,
        test_cases_held_out=25,
        true_positives=15,
        false_positives=0,
        true_negatives=10,
        false_negatives=0,
    )

    result = compute_critic_metrics(calibration)

    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1_score == 1.0
    assert result.accuracy == 1.0
    assert result.calibrated  # F1 >= 0.8 and held_out >= 20


def test_compute_critic_metrics_realistic():
    """Critic metrics computed for realistic performance."""
    calibration = CriticCalibration(
        critic_name="test_critic",
        critic_function="test",
        test_cases_total=50,
        test_cases_held_out=25,
        true_positives=18,
        false_positives=2,
        true_negatives=22,
        false_negatives=3,
    )

    result = compute_critic_metrics(calibration)

    # Precision: TP / (TP + FP) = 18 / 20 = 0.9
    assert result.precision == pytest.approx(0.9)

    # Recall: TP / (TP + FN) = 18 / 21 = 0.857
    assert result.recall == pytest.approx(18 / 21)

    # F1: 2 * (P * R) / (P + R)
    assert result.f1_score > 0.0

    # Accuracy: (TP + TN) / total = 40 / 45
    assert result.accuracy == pytest.approx(40 / 45)

    assert result.calibrated  # F1 >= 0.8 and held_out >= 20


def test_compute_critic_metrics_low_f1():
    """Critic not calibrated with low F1."""
    calibration = CriticCalibration(
        critic_name="test_critic",
        critic_function="test",
        test_cases_total=50,
        test_cases_held_out=25,
        true_positives=10,
        false_positives=15,
        true_negatives=10,
        false_negatives=15,
    )

    result = compute_critic_metrics(calibration)

    assert result.f1_score < 0.8
    assert not result.calibrated


def test_compute_critic_metrics_low_sample():
    """Critic not calibrated with low held-out sample."""
    calibration = CriticCalibration(
        critic_name="test_critic",
        critic_function="test",
        test_cases_total=30,
        test_cases_held_out=10,  # Below threshold
        true_positives=8,
        false_positives=0,
        true_negatives=2,
        false_negatives=0,
    )

    result = compute_critic_metrics(calibration)

    assert result.f1_score == 1.0  # Perfect F1
    assert not result.calibrated  # But held_out < 20


def test_save_benchmark_result(tmp_path, sample_evaluations):
    """Benchmark result saved to JSON."""
    benchmark = BenchmarkResult(
        benchmark_id="bench-001",
        document_id="doc-001",
        snapshot_id="snap-001",
        baseline_id="base-001",
        reader_evaluations=sample_evaluations,
    )

    benchmark = compute_benchmark_aggregates(benchmark)

    output_file = tmp_path / "benchmark.json"
    save_benchmark_result(benchmark, output_file)

    assert output_file.exists()

    import json
    with open(output_file) as f:
        data = json.load(f)

    assert data["benchmark_id"] == "bench-001"
    assert data["sample_size"] == 2
    assert len(data["reader_evaluations"]) == 2


def test_save_critic_calibration(tmp_path):
    """Critic calibration saved to JSON."""
    calibration = CriticCalibration(
        critic_name="test_critic",
        critic_function="concept_correspondence",
        test_cases_total=50,
        test_cases_held_out=25,
        true_positives=20,
        false_positives=2,
        true_negatives=23,
        false_negatives=0,
        calibration_date="2026-09-12",
    )

    calibration = compute_critic_metrics(calibration)

    output_file = tmp_path / "calibration.json"
    save_critic_calibration(calibration, output_file)

    assert output_file.exists()

    import json
    with open(output_file) as f:
        data = json.load(f)

    assert data["critic_name"] == "test_critic"
    assert data["f1_score"] > 0.0
    assert data["calibrated"]


def test_evaluation_dimension_enum():
    """EvaluationDimension enum has correct values."""
    assert EvaluationDimension.CONCEPT_RETENTION.value == "concept_retention"
    assert EvaluationDimension.EXPLANATION_ADEQUACY.value == "explanation_adequacy"
    assert EvaluationDimension.READABILITY.value == "readability"


def test_reader_level_enum():
    """ReaderLevel enum has correct values."""
    assert ReaderLevel.UNDERGRADUATE.value == "undergraduate"
    assert ReaderLevel.GRADUATE.value == "graduate"
    assert ReaderLevel.EXPERT.value == "expert"


def test_replay_result_fields():
    """ReplayResult contains all required fields."""
    replay = ReplayResult(
        replay_id="replay-001",
        original_operator="operator-1",
        replay_operator="operator-2",
        snapshot_id="snap-001",
        baseline_id="base-001",
        plan_id="plan-001",
    )

    assert replay.replay_id == "replay-001"
    assert replay.original_operator == "operator-1"
    assert replay.replay_operator == "operator-2"
    assert not replay.results_identical
