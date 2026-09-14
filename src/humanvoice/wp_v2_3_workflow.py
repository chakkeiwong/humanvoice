"""
WP-V2-3 integration: orchestrates source-grounded humanization workflow.

End-to-end coordination of rewriting process:
1. Load frozen baseline + teaching plan
2. Prepare rewrite context per unit
3. Call rewrite engine
4. Verify mutation safety
5. Accumulate acceptable rewrites
6. Track correspondence for V2-G3 verification
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import json
import sys


@dataclass
class RewriteSession:
    """Session state for rewriting a manuscript."""
    session_id: str
    baseline_id: str
    plan_id: str
    snapshot_id: str
    units_to_rewrite: list
    units_completed: list = field(default_factory=list)
    units_failed: list = field(default_factory=list)
    total_concepts_mapped: int = 0
    total_concepts_unmet: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


def run_rewrite_phase(
    baseline,
    plan,
    snapshot_dir,
    model,
    brief,
    policy_snapshot,
    mock: bool = False,
) -> RewriteSession:
    """Run WP-V2-3 rewrite phase on all units.

    Args:
        baseline: Frozen ConceptBaseline
        plan: RewritePlan with units
        snapshot_dir: Snapshot directory path
        model: ModelAdapter for inference
        brief: HumanizationBrief
        policy_snapshot: Applicable policies
        mock: If True, run in mock mode (no model calls)

    Returns:
        RewriteSession with results
    """
    from datetime import datetime
    from humanvoice.rewrite_engine import rewrite_unit, save_rewrite_result

    session = RewriteSession(
        session_id=f"rewrite-{datetime.utcnow().isoformat()}",
        baseline_id=baseline.baseline_id,
        plan_id=plan.plan_id,
        snapshot_id=baseline.snapshot_id,
        units_to_rewrite=plan.units or [],
        started_at=datetime.utcnow().isoformat(),
    )

    # Load source texts
    source_texts = _load_source_texts(snapshot_dir)
    protected_objects = _load_protected_objects(snapshot_dir)

    print(f"WP-V2-3: Rewrite phase starting", file=sys.stderr)
    print(f"  Baseline: {baseline.baseline_id}", file=sys.stderr)
    print(f"  Plan: {plan.plan_id}", file=sys.stderr)
    print(f"  Units: {len(session.units_to_rewrite)}", file=sys.stderr)
    print(f"  Mock mode: {mock}", file=sys.stderr)
    print(f"", file=sys.stderr)

    for i, unit in enumerate(session.units_to_rewrite, 1):
        print(f"  Unit {i}/{len(session.units_to_rewrite)}: {unit.unit_id}", file=sys.stderr)

        if mock:
            # Mock rewrite for testing
            result = _mock_rewrite_unit(unit, baseline)
        else:
            # Real rewrite
            result = rewrite_unit(
                unit=unit,
                baseline=baseline,
                plan=plan,
                model=model,
                source_texts=source_texts,
                protected_objects=protected_objects,
                brief=brief,
                policy_snapshot=policy_snapshot,
            )

        # Save result
        result_path = snapshot_dir / ".humanvoice" / "rewrites" / f"{unit.unit_id}.json"
        save_rewrite_result(result, result_path)

        # Track results
        if result.is_acceptable:
            session.units_completed.append(result.unit_id)
            session.total_concepts_mapped += len(result.concept_correspondences)
        else:
            session.units_failed.append(result.unit_id)
            session.total_concepts_unmet += len(unit.concept_ids)

        # Report
        status = "✓" if result.is_acceptable else "✗"
        print(f"    {status} {len(result.concept_correspondences)} concepts mapped", file=sys.stderr)
        if result.rejection_reasons:
            for reason in result.rejection_reasons[:1]:  # Show first reason
                print(f"      Reason: {reason}", file=sys.stderr)

    session.completed_at = datetime.utcnow().isoformat()

    print(f"", file=sys.stderr)
    print(f"WP-V2-3: Rewrite phase complete", file=sys.stderr)
    print(f"  Completed: {len(session.units_completed)}/{len(session.units_to_rewrite)}", file=sys.stderr)
    print(f"  Failed: {len(session.units_failed)}", file=sys.stderr)
    print(f"  Concepts mapped: {session.total_concepts_mapped}", file=sys.stderr)
    print(f"", file=sys.stderr)

    return session


def _load_source_texts(snapshot_dir) -> dict:
    """Load all source texts by reading from source files using span byte offsets."""
    source_texts = {}
    spans_path = snapshot_dir / ".humanvoice" / "inventory" / "spans.jsonl"

    # Load source files into memory
    source_dir = snapshot_dir / "source"
    source_files = {}

    if spans_path.exists():
        with open(spans_path) as f:
            for line in f:
                span = json.loads(line)
                source_file = span.get("source_file")

                # Load source file if not already loaded
                if source_file and source_file not in source_files:
                    source_path = source_dir / source_file
                    if source_path.exists():
                        source_files[source_file] = source_path.read_bytes()

                # Extract text using byte offsets
                if source_file and source_file in source_files:
                    byte_start = span.get("byte_start", 0)
                    byte_end = span.get("byte_end", 0)
                    exact_text = source_files[source_file][byte_start:byte_end].decode('utf-8', errors='replace')
                    source_texts[span["record_id"]] = exact_text

    return source_texts


def _load_protected_objects(snapshot_dir) -> dict:
    """Load protected objects from links file."""
    protected_objects = {}
    links_path = snapshot_dir / ".humanvoice" / "inventory" / "protected_links.json"

    if links_path.exists():
        with open(links_path) as f:
            data = json.load(f)
            for entry in data.get("protected_objects", []):
                span_id = entry["span_id"]
                if span_id not in protected_objects:
                    protected_objects[span_id] = []
                protected_objects[span_id].append(entry)

    return protected_objects


def _mock_rewrite_unit(unit, baseline):
    """Create mock rewrite result for testing."""
    from humanvoice.rewrite_engine import RewriteResult, ConceptCorrespondence
    from hashlib import sha256

    # Generate mock output
    output_latex = f"% Mock rewrite of {unit.unit_id}\n"
    output_latex += "This is a mock rewrite that preserves all concepts.\n"
    output_latex += "Each concept is explained adequately for the reader.\n"

    # Mock correspondence (all concepts retained)
    correspondences = [
        ConceptCorrespondence(
            source_concept_id=cid,
            output_span_ids=[f"mock-{cid}"],
            mapping_type="paraphrase",
            rationale="Mock rewrite",
        )
        for cid in unit.concept_ids
    ]

    result = RewriteResult(
        unit_id=unit.unit_id,
        source_span_ids=unit.source_span_ids,
        output_latex=output_latex,
        output_hash=sha256(output_latex.encode()).hexdigest(),
        concept_correspondences=correspondences,
        is_acceptable=True,
    )

    return result


def save_rewrite_session(session: RewriteSession, output_path) -> None:
    """Save rewrite session to disk."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "session_id": session.session_id,
            "baseline_id": session.baseline_id,
            "plan_id": session.plan_id,
            "snapshot_id": session.snapshot_id,
            "units_completed": session.units_completed,
            "units_failed": session.units_failed,
            "total_completed": len(session.units_completed),
            "total_failed": len(session.units_failed),
            "total_concepts_mapped": session.total_concepts_mapped,
            "total_concepts_unmet": session.total_concepts_unmet,
            "started_at": session.started_at,
            "completed_at": session.completed_at,
        }, f, indent=2)


def verify_rewrite_correspondence(session: RewriteSession, baseline) -> dict:
    """Verify that rewrite session achieved 1.0 correspondence.

    Per Master Program v2 V2-G3: deletion of any concept blocks acceptance.

    Args:
        session: RewriteSession with results
        baseline: Frozen baseline for reference

    Returns:
        Dict with verification results
    """
    total_concepts = len(baseline.concept_entries)
    concepts_mapped = session.total_concepts_mapped
    correspondence_ratio = concepts_mapped / total_concepts if total_concepts > 0 else 0.0

    return {
        "total_concepts_in_baseline": total_concepts,
        "concepts_mapped": concepts_mapped,
        "correspondence_ratio": correspondence_ratio,
        "acceptable": correspondence_ratio >= 1.0,  # Must be exactly 1.0
        "unmet_concepts": total_concepts - concepts_mapped,
    }
