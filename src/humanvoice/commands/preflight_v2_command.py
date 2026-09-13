"""
hv preflight-v2 - Independent verification of rewritten units.

WP-V2-4: Runs semantic critics against the candidate revision, not the source
snapshot. Reads the rewrite session produced by `hv rewrite` and verifies each
unit independently:

1. Concept correspondence (exactly 1.0 -- no partial credit)
2. Explanation obligation fulfillment
3. Protected object integrity
4. Unsupported addition detection

Exit codes:
  0 - all units acceptable
  1 - one or more units have blocking findings
  3 - invalid input (missing session, baseline, or plan)
  4 - internal error
"""

import json
import sys
from pathlib import Path

from humanvoice.concept_baseline import load_baseline
from humanvoice.preflight_verification import (
    run_preflight_verification,
    save_preflight_result,
)
from humanvoice.semantic_unit_splitting import load_rewrite_plan


def _load_source_protected(snapshot_dir: Path) -> list[dict]:
    """Load protected objects the rewrite was required to preserve.

    Reads the same artifact the rewrite phase reads so both phases agree on
    what "protected" means. A missing links file means inventory recorded no
    protected objects, which is distinct from failing to check.
    """
    links_path = snapshot_dir / ".humanvoice" / "inventory" / "protected_links.json"
    if not links_path.exists():
        return []

    with open(links_path) as f:
        data = json.load(f)

    return list(data.get("protected_objects", []))


def run(args) -> int:
    """Verify every unit in a rewrite session against the frozen baseline."""
    snapshot_dir = args.snapshot.resolve()

    if not snapshot_dir.exists():
        print(f"Error: Snapshot does not exist: {snapshot_dir}", file=sys.stderr)
        return 3

    inventory_dir = snapshot_dir / ".humanvoice" / "inventory"
    rewrites_dir = snapshot_dir / ".humanvoice" / "rewrites"
    plans_dir = snapshot_dir / ".humanvoice" / "plans"

    baseline_path = inventory_dir / "baseline.json"
    if not baseline_path.exists():
        print("Error: Baseline not found. Run 'hv inventory --freeze' first.", file=sys.stderr)
        print(f"  Expected: {baseline_path}", file=sys.stderr)
        return 3

    if not rewrites_dir.exists():
        print("Error: No rewrite results found. Run 'hv rewrite' first.", file=sys.stderr)
        print(f"  Expected: {rewrites_dir}", file=sys.stderr)
        return 3

    # Locate the rewrite session. Without a session record there is no record of
    # which units were attempted, so verifying whatever files happen to be on
    # disk would silently skip failed units.
    session_paths = sorted(rewrites_dir.glob("session-*.json"))
    if not session_paths:
        print("Error: No rewrite session record found. Run 'hv rewrite' first.", file=sys.stderr)
        return 3

    session_path = session_paths[-1]
    try:
        with open(session_path) as f:
            session = json.load(f)
    except Exception as e:
        print(f"Error: Cannot read rewrite session: {e}", file=sys.stderr)
        return 4

    try:
        baseline = load_baseline(baseline_path)
    except Exception as e:
        print(f"Error: Cannot load baseline: {e}", file=sys.stderr)
        return 4

    plan_id = session.get("plan_id")
    plan_path = plans_dir / f"{plan_id}.json"
    if not plan_path.exists():
        print(f"Error: Plan referenced by session not found: {plan_path}", file=sys.stderr)
        return 3

    try:
        plan = load_rewrite_plan(plan_path)
    except Exception as e:
        print(f"Error: Cannot load plan: {e}", file=sys.stderr)
        return 4

    unit_concepts = {unit.unit_id: list(unit.concept_ids) for unit in plan.units}
    source_protected = _load_source_protected(snapshot_dir)

    print(f"Verifying rewrite session {session.get('session_id')}", file=sys.stderr)
    print(f"  Baseline: {baseline.baseline_id} ({baseline.total_concepts} concepts)", file=sys.stderr)
    print(f"  Plan: {plan_id} ({plan.total_units} units)", file=sys.stderr)
    print("", file=sys.stderr)

    # A unit that failed rewrite has no acceptable output to verify. Counting it
    # as verified would let a failed rewrite pass the gate.
    units_failed_rewrite = list(session.get("units_failed", []))
    units_to_verify = list(session.get("units_completed", []))

    if not units_to_verify:
        print("Error: Session records no completed units to verify", file=sys.stderr)
        return 3

    preflight_dir = snapshot_dir / ".humanvoice" / "preflight"
    results = []
    unreadable_units = []

    for unit_id in units_to_verify:
        unit_path = rewrites_dir / f"{unit_id}.json"
        if not unit_path.exists():
            print(f"  {unit_id}: MISSING rewrite output", file=sys.stderr)
            unreadable_units.append(unit_id)
            continue

        try:
            with open(unit_path) as f:
                unit_result = json.load(f)
        except Exception as e:
            print(f"  {unit_id}: unreadable rewrite output ({e})", file=sys.stderr)
            unreadable_units.append(unit_id)
            continue

        # Obligations recorded as unmet by the rewrite phase carry forward. The
        # verifier blocks on any obligation whose functions are unfulfilled.
        obligations = list(unit_result.get("unmet_obligations", []))
        obligations.extend(
            o for o in unit_result.get("fulfilled_obligations", [])
            if not o.get("fulfilled_in_output", False)
        )

        result = run_preflight_verification(
            unit_id=unit_id,
            baseline_id=baseline.baseline_id,
            source_concepts=unit_concepts.get(unit_id, []),
            output_correspondences=unit_result.get("concept_correspondences", []),
            output_latex=unit_result.get("output_latex", ""),
            obligations=obligations,
            source_protected=source_protected,
            output_preserved=unit_result.get("protected_objects_preserved", []),
        )

        save_preflight_result(result, preflight_dir / f"{unit_id}.json")
        results.append(result)

        status = "PASS" if result.is_acceptable else "BLOCK"
        print(
            f"  {unit_id}: {status} "
            f"(correspondence {result.concept_correspondence_ratio:.2f}, "
            f"obligations {result.obligation_fulfillment_ratio:.2f}, "
            f"{len(result.blocking_findings)} blocking)",
            file=sys.stderr,
        )

        for finding in result.blocking_findings:
            print(f"      {finding.category}: {finding.evidence}", file=sys.stderr)

    blocked = [r.unit_id for r in results if not r.is_acceptable]
    acceptable = [r.unit_id for r in results if r.is_acceptable]

    summary = {
        "status": "pass" if not (blocked or unreadable_units or units_failed_rewrite) else "blocked",
        "session_id": session.get("session_id"),
        "baseline_id": baseline.baseline_id,
        "plan_id": plan_id,
        "units_verified": len(results),
        "units_acceptable": len(acceptable),
        "units_blocked": len(blocked),
        "blocked_units": blocked,
        "units_missing_output": unreadable_units,
        "units_failed_rewrite": units_failed_rewrite,
        "preflight_dir": str(preflight_dir.relative_to(snapshot_dir)),
    }
    print(json.dumps(summary, indent=2))

    print("", file=sys.stderr)
    if units_failed_rewrite:
        print(
            f"Blocking: {len(units_failed_rewrite)} unit(s) failed rewrite and have no verified output",
            file=sys.stderr,
        )
    if unreadable_units:
        print(
            f"Blocking: {len(unreadable_units)} unit(s) claimed complete but output missing",
            file=sys.stderr,
        )
    if blocked:
        print(f"Blocking: {len(blocked)} unit(s) have blocking findings", file=sys.stderr)

    if blocked or unreadable_units or units_failed_rewrite:
        return 1

    print(f"All {len(acceptable)} unit(s) acceptable", file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(run(None))
