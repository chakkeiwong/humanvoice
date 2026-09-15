"""
rewrite_command.py: WP-V2-3 source-grounded rewriting.

Usage:
  hv rewrite <snapshot_path> --baseline-id <id> --plan-id <id> [--mock]

Orchestrates source-grounded humanization of frozen concepts:
1. Load immutable source snapshot + frozen baseline + teaching plan
2. Prepare rewrite context per unit
3. Call rewrite engine for each unit
4. Verify mutation safety
5. Accumulate acceptable rewrites
6. Persist results and correspondence
"""

import sys
import json
from pathlib import Path
from typing import Optional
import argparse

from humanvoice.wp_v2_3_workflow import (
    run_rewrite_phase,
    save_rewrite_session,
    verify_rewrite_correspondence,
)
from humanvoice.concept_baseline import load_baseline
from humanvoice.semantic_unit_splitting import load_rewrite_plan
from humanvoice.model import ModelAdapter


def load_baseline(baseline_path: Path):
    """Load frozen baseline from JSON."""
    with open(baseline_path) as f:
        data = json.load(f)

    from humanvoice.concept_baseline import ConceptBaseline, ConceptBaselineEntry

    entries = [
        ConceptBaselineEntry(
            concept_id=e["concept_id"],
            proposition=e["proposition"],
            concept_type=e["concept_type"],
            source_span_ids=e.get("source_span_ids", []),
            teaching_roles=e.get("teaching_roles", []),
            confidence=e.get("confidence", 0.0),
        )
        for e in data.get("concept_entries", [])
    ]

    baseline = ConceptBaseline(
        baseline_id=data["baseline_id"],
        snapshot_id=data["snapshot_id"],
        source_hash=data.get("source_hash", ""),
        concept_entries=entries,
        total_concepts=data.get("total_concepts", 0),
        frozen_at=data.get("frozen_at"),
        frozen_by=data.get("frozen_by"),
    )

    if "baseline_hash" in data:
        baseline.baseline_hash = data["baseline_hash"]

    return baseline


def load_rewrite_plan(plan_path: Path):
    """Load rewrite plan from JSON."""
    with open(plan_path) as f:
        data = json.load(f)

    from humanvoice.semantic_unit_splitting import RewritePlan, RewriteUnit

    units = [
        RewriteUnit(
            unit_id=u["unit_id"],
            concept_ids=u.get("concept_ids", []),
            source_span_ids=u.get("source_span_ids", []),
            prerequisites=u.get("prerequisites", []),
            estimated_words=u.get("estimated_words", 0),
            teaching_sequence=u.get("teaching_sequence", 0),
        )
        for u in data.get("units", [])
    ]

    plan = RewritePlan(
        plan_id=data["plan_id"],
        baseline_id=data["baseline_id"],
        snapshot_id=data["snapshot_id"],
        units=units,
        total_units=data.get("total_units", 0),
        total_concepts=data.get("total_concepts", 0),
    )

    return plan


def load_brief(brief_path: Optional[Path] = None) -> dict:
    """Load humanization brief from JSON or return default."""
    if brief_path and brief_path.exists():
        with open(brief_path) as f:
            return json.load(f)

    # Default brief for technical writing
    return {
        "reader": {
            "expertise_level": "graduate_student",
            "prior_knowledge": ["basic_economics"],
        },
        "genre": "technical",
        "voice_register": "formal",
    }


def load_policy_snapshot(policy_path: Optional[Path] = None) -> dict:
    """Load policy snapshot or return empty."""
    if policy_path and policy_path.exists():
        with open(policy_path) as f:
            return json.load(f)
    return {}


def rewrite_command(args):
    """Execute WP-V2-3 rewrite phase.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 on success)
    """
    snapshot_path = Path(args.snapshot)
    baseline_id = args.baseline_id
    plan_id = args.plan_id
    mock = args.mock
    timeout_seconds = args.timeout

    # Resolve paths
    inventory_dir = snapshot_path / ".humanvoice" / "inventory"
    plan_dir = snapshot_path / ".humanvoice" / "plans"

    baseline_path = inventory_dir / "baseline.json"
    plan_path = plan_dir / f"{plan_id}.json"

    brief_path = snapshot_path / ".humanvoice" / "brief.json"
    policy_path = snapshot_path / ".humanvoice" / "policy.json"

    # Validate inputs
    if not snapshot_path.exists():
        print(f"Error: snapshot not found: {snapshot_path}", file=sys.stderr)
        return 1

    if not baseline_path.exists():
        print(f"Error: baseline not found: {baseline_path}", file=sys.stderr)
        return 1

    if not plan_path.exists():
        print(f"Error: plan not found: {plan_path}", file=sys.stderr)
        return 1

    # Load artifacts
    print(f"Loading baseline: {baseline_id}", file=sys.stderr)
    baseline = load_baseline(baseline_path)

    print(f"Loading plan: {plan_id}", file=sys.stderr)
    plan = load_rewrite_plan(plan_path)

    brief = load_brief(brief_path)
    policy = load_policy_snapshot(policy_path)

    # Initialize model (None in mock mode)
    model = None
    if not mock:
        print(f"Initializing model adapter", file=sys.stderr)
        from humanvoice.model import ModelConfig
        config = ModelConfig.from_profile()
        config.timeout_seconds = timeout_seconds
        model = ModelAdapter(
            config=config,
            mock_mode=False,
            snapshot_dir=snapshot_path,
        )
        print(f"  Model adapter ready: {config.model_version}", file=sys.stderr)

    # Run rewrite phase
    print(f"", file=sys.stderr)
    session = run_rewrite_phase(
        baseline=baseline,
        plan=plan,
        snapshot_dir=snapshot_path,
        model=model,
        brief=brief,
        policy_snapshot=policy,
        mock=mock,
    )

    # Verify correspondence
    print(f"", file=sys.stderr)
    print(f"Verifying concept correspondence...", file=sys.stderr)
    correspondence = verify_rewrite_correspondence(session, baseline)

    print(f"Correspondence ratio: {correspondence['correspondence_ratio']:.2%}", file=sys.stderr)
    print(f"Concepts mapped: {correspondence['concepts_mapped']}/{correspondence['total_concepts_in_baseline']}", file=sys.stderr)

    if not correspondence["acceptable"]:
        print(f"Error: Correspondence < 1.0 (Master Program v2 V2-G3 requires 100%)", file=sys.stderr)
        return 1

    # Save session record
    session_path = snapshot_path / ".humanvoice" / "rewrites" / f"session-{session.session_id}.json"
    save_rewrite_session(session, session_path)

    print(f"", file=sys.stderr)
    print(f"Rewrite session saved: {session_path}", file=sys.stderr)
    print(f"Status: COMPLETE", file=sys.stderr)

    # Emit summary JSON to stdout
    summary = {
        "status": "complete" if correspondence["acceptable"] else "failed",
        "session_id": session.session_id,
        "baseline_id": baseline.baseline_id,
        "plan_id": plan.plan_id,
        "units_completed": len(session.units_completed),
        "units_failed": len(session.units_failed),
        "concepts_mapped": session.total_concepts_mapped,
        "correspondence_ratio": correspondence["correspondence_ratio"],
        "session_path": str(session_path),
    }

    print(json.dumps(summary, indent=2))

    return 0


def main():
    """Parse arguments and execute rewrite command."""
    parser = argparse.ArgumentParser(
        description="WP-V2-3 source-grounded rewriting",
    )

    parser.add_argument(
        "snapshot",
        help="Path to snapshot directory",
    )

    parser.add_argument(
        "--baseline-id",
        required=True,
        help="Baseline ID (e.g., baseline-001)",
    )

    parser.add_argument(
        "--plan-id",
        required=True,
        help="Plan ID (e.g., plan-001)",
    )

    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock mode (no model calls)",
    )

    args = parser.parse_args()

    return rewrite_command(args)


if __name__ == "__main__":
    sys.exit(main())
