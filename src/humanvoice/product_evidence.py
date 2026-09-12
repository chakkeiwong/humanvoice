"""
Product evidence framework for WP-V2-6.

Calibrated evaluation of humanization quality:
1. ZLB benchmark with human evaluation
2. Second-operator replay and reproduction
3. Held-out manuscript testing
4. Reader comprehension measurement
5. Model critic calibration
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from pathlib import Path
from enum import Enum
import json


class EvaluationDimension(Enum):
    """Dimensions for product evaluation."""
    CONCEPT_RETENTION = "concept_retention"
    EXPLANATION_ADEQUACY = "explanation_adequacy"
    READABILITY = "readability"
    TECHNICAL_ACCURACY = "technical_accuracy"
    COHERENCE = "coherence"


class ReaderLevel(Enum):
    """Reader expertise levels for evaluation."""
    UNDERGRADUATE = "undergraduate"
    GRADUATE = "graduate"
    EXPERT = "expert"


@dataclass
class ReaderEvaluation:
    """One reader's evaluation of one document."""
    reader_id: str
    reader_level: ReaderLevel
    document_id: str
    document_version: str  # "original" or "revised"

    # Ratings (1-5 scale)
    concept_comprehension_score: float = 0.0
    explanation_clarity_score: float = 0.0
    readability_score: float = 0.0
    technical_accuracy_score: float = 0.0
    coherence_score: float = 0.0

    # Qualitative
    concepts_understood: List[str] = field(default_factory=list)
    concepts_confused: List[str] = field(default_factory=list)
    feedback_text: str = ""

    # Time
    reading_time_minutes: float = 0.0
    evaluation_time_minutes: float = 0.0


@dataclass
class BenchmarkResult:
    """Results from one benchmark evaluation."""
    benchmark_id: str
    document_id: str
    snapshot_id: str
    baseline_id: str

    # Reader evaluations
    reader_evaluations: List[ReaderEvaluation] = field(default_factory=list)

    # Aggregate scores
    avg_concept_comprehension: float = 0.0
    avg_explanation_clarity: float = 0.0
    avg_readability: float = 0.0
    avg_technical_accuracy: float = 0.0
    avg_coherence: float = 0.0

    # Comparative (original vs revised)
    original_avg_comprehension: float = 0.0
    revised_avg_comprehension: float = 0.0
    comprehension_improvement: float = 0.0

    # Statistical
    sample_size: int = 0
    statistical_power: float = 0.0


@dataclass
class ReplayResult:
    """Second-operator replay verification."""
    replay_id: str
    original_operator: str
    replay_operator: str

    # Inputs
    snapshot_id: str
    baseline_id: str
    plan_id: str

    # Outputs
    original_result_hash: str = ""
    replay_result_hash: str = ""

    # Comparison
    results_identical: bool = False
    concept_correspondence_match: bool = False
    protected_objects_match: bool = False

    # Divergence
    divergent_units: List[str] = field(default_factory=list)
    divergence_reasons: List[str] = field(default_factory=list)


@dataclass
class CriticCalibration:
    """Calibration of one model critic."""
    critic_name: str
    critic_function: str  # "concept_correspondence", "obligation_fulfillment", etc.

    # Calibration data
    test_cases_total: int = 0
    test_cases_held_out: int = 0

    # Performance
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0

    # Metrics
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    accuracy: float = 0.0

    # Reliability
    calibrated: bool = False
    calibration_date: Optional[str] = None


def aggregate_reader_scores(
    evaluations: List[ReaderEvaluation],
    dimension: EvaluationDimension,
) -> tuple[float, int]:
    """Aggregate reader scores for one dimension.

    Args:
        evaluations: List of reader evaluations
        dimension: Which dimension to aggregate

    Returns:
        Tuple of (average_score, sample_size)
    """
    scores = []

    for eval in evaluations:
        if dimension == EvaluationDimension.CONCEPT_RETENTION:
            scores.append(eval.concept_comprehension_score)
        elif dimension == EvaluationDimension.EXPLANATION_ADEQUACY:
            scores.append(eval.explanation_clarity_score)
        elif dimension == EvaluationDimension.READABILITY:
            scores.append(eval.readability_score)
        elif dimension == EvaluationDimension.TECHNICAL_ACCURACY:
            scores.append(eval.technical_accuracy_score)
        elif dimension == EvaluationDimension.COHERENCE:
            scores.append(eval.coherence_score)

    valid_scores = [s for s in scores if s > 0]

    if not valid_scores:
        return 0.0, 0

    avg = sum(valid_scores) / len(valid_scores)
    return avg, len(valid_scores)


def compare_versions(
    original_evals: List[ReaderEvaluation],
    revised_evals: List[ReaderEvaluation],
    dimension: EvaluationDimension,
) -> tuple[float, float, float]:
    """Compare original vs revised versions.

    Args:
        original_evals: Evaluations of original document
        revised_evals: Evaluations of revised document
        dimension: Which dimension to compare

    Returns:
        Tuple of (original_avg, revised_avg, improvement)
    """
    original_avg, _ = aggregate_reader_scores(original_evals, dimension)
    revised_avg, _ = aggregate_reader_scores(revised_evals, dimension)

    improvement = revised_avg - original_avg

    return original_avg, revised_avg, improvement


def compute_benchmark_aggregates(benchmark: BenchmarkResult) -> BenchmarkResult:
    """Compute aggregate scores for benchmark.

    Args:
        benchmark: BenchmarkResult with reader evaluations

    Returns:
        Updated benchmark with aggregates computed
    """
    benchmark.sample_size = len(benchmark.reader_evaluations)

    # Aggregate each dimension
    benchmark.avg_concept_comprehension, _ = aggregate_reader_scores(
        benchmark.reader_evaluations,
        EvaluationDimension.CONCEPT_RETENTION,
    )

    benchmark.avg_explanation_clarity, _ = aggregate_reader_scores(
        benchmark.reader_evaluations,
        EvaluationDimension.EXPLANATION_ADEQUACY,
    )

    benchmark.avg_readability, _ = aggregate_reader_scores(
        benchmark.reader_evaluations,
        EvaluationDimension.READABILITY,
    )

    benchmark.avg_technical_accuracy, _ = aggregate_reader_scores(
        benchmark.reader_evaluations,
        EvaluationDimension.TECHNICAL_ACCURACY,
    )

    benchmark.avg_coherence, _ = aggregate_reader_scores(
        benchmark.reader_evaluations,
        EvaluationDimension.COHERENCE,
    )

    # Compare original vs revised if both present
    original_evals = [e for e in benchmark.reader_evaluations if e.document_version == "original"]
    revised_evals = [e for e in benchmark.reader_evaluations if e.document_version == "revised"]

    if original_evals and revised_evals:
        benchmark.original_avg_comprehension, benchmark.revised_avg_comprehension, benchmark.comprehension_improvement = \
            compare_versions(original_evals, revised_evals, EvaluationDimension.CONCEPT_RETENTION)

    return benchmark


def compute_critic_metrics(calibration: CriticCalibration) -> CriticCalibration:
    """Compute precision, recall, F1 for critic.

    Args:
        calibration: CriticCalibration with confusion matrix

    Returns:
        Updated calibration with metrics computed
    """
    tp = calibration.true_positives
    fp = calibration.false_positives
    tn = calibration.true_negatives
    fn = calibration.false_negatives

    total = tp + fp + tn + fn

    if total == 0:
        return calibration

    # Precision: TP / (TP + FP)
    if tp + fp > 0:
        calibration.precision = tp / (tp + fp)

    # Recall: TP / (TP + FN)
    if tp + fn > 0:
        calibration.recall = tp / (tp + fn)

    # F1: 2 * (precision * recall) / (precision + recall)
    if calibration.precision + calibration.recall > 0:
        calibration.f1_score = 2 * (calibration.precision * calibration.recall) / (calibration.precision + calibration.recall)

    # Accuracy: (TP + TN) / total
    calibration.accuracy = (tp + tn) / total

    # Calibrated if F1 >= 0.8 and held-out sample >= 20
    calibration.calibrated = (
        calibration.f1_score >= 0.8 and
        calibration.test_cases_held_out >= 20
    )

    return calibration


def save_benchmark_result(result: BenchmarkResult, output_path: Path) -> None:
    """Save benchmark result to JSON.

    Args:
        result: BenchmarkResult
        output_path: Path to write JSON
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "benchmark_id": result.benchmark_id,
            "document_id": result.document_id,
            "snapshot_id": result.snapshot_id,
            "baseline_id": result.baseline_id,
            "sample_size": result.sample_size,
            "avg_concept_comprehension": result.avg_concept_comprehension,
            "avg_explanation_clarity": result.avg_explanation_clarity,
            "avg_readability": result.avg_readability,
            "comprehension_improvement": result.comprehension_improvement,
            "reader_evaluations": [
                {
                    "reader_id": e.reader_id,
                    "reader_level": e.reader_level.value,
                    "document_version": e.document_version,
                    "concept_comprehension_score": e.concept_comprehension_score,
                    "explanation_clarity_score": e.explanation_clarity_score,
                    "readability_score": e.readability_score,
                }
                for e in result.reader_evaluations
            ],
        }, f, indent=2)


def save_critic_calibration(calibration: CriticCalibration, output_path: Path) -> None:
    """Save critic calibration to JSON.

    Args:
        calibration: CriticCalibration
        output_path: Path to write JSON
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "critic_name": calibration.critic_name,
            "critic_function": calibration.critic_function,
            "test_cases_total": calibration.test_cases_total,
            "test_cases_held_out": calibration.test_cases_held_out,
            "precision": calibration.precision,
            "recall": calibration.recall,
            "f1_score": calibration.f1_score,
            "accuracy": calibration.accuracy,
            "calibrated": calibration.calibrated,
            "calibration_date": calibration.calibration_date,
        }, f, indent=2)
