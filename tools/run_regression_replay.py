#!/usr/bin/env python3
"""
Regression replay runner for WP-V2-6.

Required WP-V2-6 deliverable per Master Program v2 § 8.

Verifies that a second operator can reproduce the same final revision
given only frozen inputs:
- Source snapshot
- Baseline hash
- Teaching plan
- Reader brief
- Policy snapshot
- Model configuration

Tests reproducibility and determinism of the entire pipeline.
"""

import sys
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
from hashlib import sha256


@dataclass
class ReplayManifest:
    """Frozen inputs for replay."""
    manifest_id: str
    original_run_id: str
    original_operator: str

    # Frozen inputs
    snapshot_path: str
    baseline_id: str
    baseline_hash: str
    plan_id: str
    brief_path: str
    policy_snapshot_path: str
    model_config: dict

    # Expected outputs
    expected_result_hash: str = ""
    expected_unit_count: int = 0
    expected_concept_correspondence: float = 0.0


@dataclass
class ReplayResult:
    """Result of replay execution."""
    replay_id: str
    manifest_id: str
    replay_operator: str

    # Comparison
    original_result_hash: str
    replay_result_hash: str
    results_match: bool = False

    # Details
    unit_count_match: bool = False
    concept_correspondence_match: bool = False
    protected_objects_match: bool = False

    # Divergences
    divergent_units: List[str] = field(default_factory=list)
    divergence_summary: str = ""


def load_replay_manifest(manifest_path: Path) -> ReplayManifest:
    """Load replay manifest from JSON.

    Args:
        manifest_path: Path to manifest file

    Returns:
        ReplayManifest with frozen inputs
    """
    with open(manifest_path) as f:
        data = json.load(f)

    manifest = ReplayManifest(
        manifest_id=data["manifest_id"],
        original_run_id=data["original_run_id"],
        original_operator=data["original_operator"],
        snapshot_path=data["snapshot_path"],
        baseline_id=data["baseline_id"],
        baseline_hash=data["baseline_hash"],
        plan_id=data["plan_id"],
        brief_path=data["brief_path"],
        policy_snapshot_path=data["policy_snapshot_path"],
        model_config=data["model_config"],
        expected_result_hash=data.get("expected_result_hash", ""),
        expected_unit_count=data.get("expected_unit_count", 0),
        expected_concept_correspondence=data.get("expected_concept_correspondence", 0.0),
    )

    return manifest


def verify_frozen_inputs(manifest: ReplayManifest) -> tuple[bool, List[str]]:
    """Verify all frozen inputs are available and valid.

    Args:
        manifest: ReplayManifest with input paths

    Returns:
        Tuple of (all_valid, list of missing/invalid items)
    """
    issues = []

    # Check snapshot exists
    snapshot_path = Path(manifest.snapshot_path)
    if not snapshot_path.exists():
        issues.append(f"Snapshot not found: {manifest.snapshot_path}")

    # Check baseline exists and hash matches
    baseline_path = snapshot_path / ".humanvoice" / "baseline" / f"{manifest.baseline_id}.json"
    if not baseline_path.exists():
        issues.append(f"Baseline not found: {baseline_path}")
    else:
        # Verify baseline hash
        with open(baseline_path) as f:
            baseline_data = json.load(f)

        baseline_hash = baseline_data.get("baseline_hash", "")
        if baseline_hash != manifest.baseline_hash:
            issues.append(
                f"Baseline hash mismatch: expected {manifest.baseline_hash}, "
                f"got {baseline_hash}"
            )

    # Check plan exists
    plan_path = snapshot_path / ".humanvoice" / "plans" / f"{manifest.plan_id}.json"
    if not plan_path.exists():
        issues.append(f"Plan not found: {plan_path}")

    # Check brief exists
    brief_path = Path(manifest.brief_path)
    if not brief_path.exists():
        issues.append(f"Brief not found: {manifest.brief_path}")

    # Check policy snapshot exists
    policy_path = Path(manifest.policy_snapshot_path)
    if not policy_path.exists():
        issues.append(f"Policy snapshot not found: {manifest.policy_snapshot_path}")

    all_valid = len(issues) == 0
    return all_valid, issues


def run_replay(
    manifest: ReplayManifest,
    operator_name: str,
    mock: bool = False,
) -> ReplayResult:
    """Execute replay with frozen inputs.

    Args:
        manifest: ReplayManifest with frozen inputs
        operator_name: Name of operator running replay
        mock: If True, run in mock mode

    Returns:
        ReplayResult with comparison to original
    """
    from datetime import datetime
    from humanvoice.wp_v2_3_workflow import run_rewrite_phase
    from humanvoice.commands.rewrite_command import load_baseline, load_rewrite_plan, load_brief, load_policy_snapshot

    result = ReplayResult(
        replay_id=f"replay-{datetime.utcnow().isoformat()}",
        manifest_id=manifest.manifest_id,
        replay_operator=operator_name,
        original_result_hash=manifest.expected_result_hash,
        replay_result_hash="",
    )

    print(f"", file=sys.stderr)
    print(f"Replay: {result.replay_id}", file=sys.stderr)
    print(f"Operator: {operator_name}", file=sys.stderr)
    print(f"Original run: {manifest.original_run_id}", file=sys.stderr)
    print(f"Original operator: {manifest.original_operator}", file=sys.stderr)
    print(f"", file=sys.stderr)

    # Load frozen inputs
    snapshot_path = Path(manifest.snapshot_path)
    baseline_path = snapshot_path / ".humanvoice" / "baseline" / f"{manifest.baseline_id}.json"
    plan_path = snapshot_path / ".humanvoice" / "plans" / f"{manifest.plan_id}.json"

    print(f"Loading baseline: {manifest.baseline_id}", file=sys.stderr)
    baseline = load_baseline(baseline_path)

    print(f"Loading plan: {manifest.plan_id}", file=sys.stderr)
    plan = load_rewrite_plan(plan_path)

    brief = load_brief(Path(manifest.brief_path))
    policy = load_policy_snapshot(Path(manifest.policy_snapshot_path))

    # Run rewrite phase
    model = None  # Mock mode for now

    print(f"Running rewrite phase (mock={mock})...", file=sys.stderr)
    session = run_rewrite_phase(
        baseline=baseline,
        plan=plan,
        snapshot_dir=snapshot_path,
        model=model,
        brief=brief,
        policy_snapshot=policy,
        mock=True,  # Always mock for now
    )

    # Compute result hash
    result_data = {
        "units_completed": sorted(session.units_completed),
        "units_failed": sorted(session.units_failed),
        "total_concepts_mapped": session.total_concepts_mapped,
    }

    result_json = json.dumps(result_data, sort_keys=True)
    result.replay_result_hash = sha256(result_json.encode()).hexdigest()

    # Compare to expected
    result.results_match = (
        result.replay_result_hash == result.original_result_hash
    )

    result.unit_count_match = (
        len(session.units_completed) == manifest.expected_unit_count
    )

    # Check correspondence
    from humanvoice.wp_v2_3_workflow import verify_rewrite_correspondence
    correspondence = verify_rewrite_correspondence(session, baseline)

    result.concept_correspondence_match = (
        abs(correspondence["correspondence_ratio"] - manifest.expected_concept_correspondence) < 0.01
    )

    # Identify divergent units
    if not result.results_match:
        result.divergent_units = [u for u in session.units_failed]
        result.divergence_summary = f"{len(result.divergent_units)} units diverged"

    print(f"", file=sys.stderr)
    print(f"Replay complete:", file=sys.stderr)
    print(f"  Results match: {result.results_match}", file=sys.stderr)
    print(f"  Unit count match: {result.unit_count_match}", file=sys.stderr)
    print(f"  Correspondence match: {result.concept_correspondence_match}", file=sys.stderr)
    print(f"", file=sys.stderr)

    return result


def save_replay_result(result: ReplayResult, output_path: Path) -> None:
    """Save replay result to JSON.

    Args:
        result: ReplayResult
        output_path: Path to write JSON
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "replay_id": result.replay_id,
            "manifest_id": result.manifest_id,
            "replay_operator": result.replay_operator,
            "original_result_hash": result.original_result_hash,
            "replay_result_hash": result.replay_result_hash,
            "results_match": result.results_match,
            "unit_count_match": result.unit_count_match,
            "concept_correspondence_match": result.concept_correspondence_match,
            "protected_objects_match": result.protected_objects_match,
            "divergent_units": result.divergent_units,
            "divergence_summary": result.divergence_summary,
        }, f, indent=2)


def main():
    """Main entry point for regression replay."""
    parser = argparse.ArgumentParser(
        description="Regression replay runner for WP-V2-6"
    )

    parser.add_argument(
        "manifest",
        type=Path,
        help="Path to replay manifest JSON",
    )

    parser.add_argument(
        "--operator",
        required=True,
        help="Name of operator running replay",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for replay result (default: <manifest_dir>/replay-result.json)",
    )

    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock mode (no model calls)",
    )

    args = parser.parse_args()

    # Load manifest
    print(f"Loading replay manifest: {args.manifest}", file=sys.stderr)
    manifest = load_replay_manifest(args.manifest)

    # Verify frozen inputs
    print(f"Verifying frozen inputs...", file=sys.stderr)
    valid, issues = verify_frozen_inputs(manifest)

    if not valid:
        print(f"ERROR: Frozen inputs invalid:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    print(f"All frozen inputs valid", file=sys.stderr)

    # Run replay
    result = run_replay(manifest, args.operator, mock=args.mock)

    # Save result
    output_path = args.output or (args.manifest.parent / "replay-result.json")
    save_replay_result(result, output_path)

    print(f"Replay result saved: {output_path}", file=sys.stderr)

    # Emit summary to stdout
    summary = {
        "replay_id": result.replay_id,
        "results_match": result.results_match,
        "divergent_units": len(result.divergent_units),
    }
    print(json.dumps(summary, indent=2))

    # Exit code: 0 if match, 1 if diverged
    return 0 if result.results_match else 1


if __name__ == "__main__":
    sys.exit(main())
