#!/usr/bin/env python3
"""
Instrumented pilot runner (plan Task 1.3).

Executes the full hv pipeline on a single fixture and records per-command
timestamps, exit codes, stdout/stderr, and token counts.

Wall-clock is measured here rather than read from runtime manifests because
runtime_manifest.latency_ms is written as 0 by every command (see
fixtures/synthetic/large_report/findings_2026-08-29.md).

Usage:
    python tools/instrumented_pilot.py <fixture.tex> <out.json>
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def now():
    return datetime.now(timezone.utc).isoformat()


def run_step(name, argv, expect=None):
    """Run one hv command, timing it and capturing everything."""
    started_mono = time.monotonic()
    started = now()
    proc = subprocess.run(
        [sys.executable, "-m", "humanvoice.cli"] + argv,
        cwd=REPO, capture_output=True, text=True,
    )
    elapsed_ms = int((time.monotonic() - started_mono) * 1000)

    step = {
        "step": name,
        "argv": argv,
        "started_utc": started,
        "ended_utc": now(),
        "wall_clock_ms": elapsed_ms,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    if expect is not None:
        step["expected_exit_code"] = expect
        step["exit_code_as_expected"] = proc.returncode == expect

    print(f"  {name}: exit={proc.returncode} {elapsed_ms}ms", file=sys.stderr)
    return step


def newest_run_dir(after_ts, snapshot_dir=None):
    """
    Most recent run dir created at or after the given wall-clock time.

    Run records live under the snapshot (humanvoice.paths.runs_dir). Older
    builds wrote them to the repo root, so both are checked.
    """
    roots = []
    if snapshot_dir is not None:
        roots.append(Path(snapshot_dir) / ".humanvoice" / "runs")
    roots.append(REPO / ".humanvoice" / "runs")

    candidates = []
    for runs in roots:
        if not runs.exists():
            continue
        candidates += [
            d for d in runs.iterdir()
            if d.is_dir() and d.stat().st_mtime >= after_ts - 1
        ]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)


def collect_tokens(run_dir):
    """Pull token counts out of any runtime manifests in a run dir."""
    if run_dir is None:
        return None
    out = []
    for m in sorted(run_dir.glob("runtime_manifest*.json")):
        try:
            d = json.loads(m.read_text())
        except Exception as e:
            out.append({"manifest": m.name, "parse_error": str(e)})
            continue
        out.append({
            "manifest": m.name,
            "input_tokens": d.get("input_tokens"),
            "output_tokens": d.get("output_tokens"),
            "request_id": d.get("request_id_if_available"),
            "latency_ms_reported": d.get("latency_ms"),
            "mode": d.get("mode"),
        })
    return out or None


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    fixture = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2])
    if not out_path.is_absolute():
        out_path = REPO / out_path

    if not fixture.exists():
        print(f"Fixture not found: {fixture}", file=sys.stderr)
        return 2

    pilot_start_mono = time.monotonic()
    pilot_start_wall = time.time()

    work = REPO / "validation_results" / "pilot_workdir"
    if work.exists():
        import shutil
        shutil.rmtree(work)
    work.mkdir(parents=True)

    brief_path = work / "brief.json"
    # Brief carries all three required-field sets: the JSON schema,
    # init_command, and plan_command each demand a different set.
    brief_path.write_text(json.dumps({
        "reader": "Engineering reviewer deciding whether to approve a proposed review",
        "reader_role": "Engineering reviewer",
        "decision": "Approve or reject the proposed review",
        "decision_type": "approve_or_reject",
        "genre": "technical memo",
        "time_available_minutes": 15,
        "prior_knowledge": "Familiar with the codebase, not with internal phase labels",
        "success_criteria": "Reader can decide without needing internal context",
        "known_vocabulary": ["reader", "review", "path"],
        "exemplars": [],
        "evidence_boundary": ["source/001.tex"],
        "privacy_class": "public",
        "protected_objects": [],
        "unknowns": [],
        "max_words": 300,
    }, indent=2))

    steps = []

    # --- init ---
    snapshot_dir = work / "snapshot"
    steps.append(run_step("init", [
        "init", str(fixture),
        "--brief", str(brief_path),
        "--output", str(snapshot_dir),
    ], expect=0))

    # --- plan ---
    t = time.time()
    plan_step = run_step("plan", [
        "plan", str(snapshot_dir),
        "--brief", str(brief_path),
    ])
    plan_run = newest_run_dir(t, snapshot_dir)
    plan_step["run_dir"] = str(plan_run.relative_to(REPO)) if plan_run else None
    plan_step["tokens"] = collect_tokens(plan_run)
    steps.append(plan_step)

    blueprint = plan_run / "blueprint.json" if plan_run else None
    sections = []
    if blueprint and blueprint.exists():
        try:
            bp = json.loads(blueprint.read_text())
            sections = bp.get("blueprint", {}).get("sections", [])
        except Exception:
            sections = []

    # --- draft (every planned section) ---
    draft_paths = []
    for idx, sec in enumerate(sections):
        t = time.time()
        ds = run_step(f"draft[{idx}]", [
            "draft", str(snapshot_dir),
            "--blueprint", str(blueprint),
            "--brief", str(brief_path),
            "--section", str(idx),
        ])
        ds["section_title"] = sec.get("title")
        ds["word_budget"] = sec.get("word_budget")
        d_run = newest_run_dir(t, snapshot_dir)
        ds["run_dir"] = str(d_run.relative_to(REPO)) if d_run else None
        ds["tokens"] = collect_tokens(d_run)
        if d_run:
            found = sorted(d_run.glob("draft_*.tex"))
            ds["draft_written"] = [str(p.relative_to(REPO)) for p in found]
            draft_paths.extend(found)
        else:
            ds["draft_written"] = []
        steps.append(ds)

    # --- preflight ---
    steps.append(run_step("preflight", [
        "preflight", str(snapshot_dir),
        "--brief", str(brief_path),
        "--deterministic",
    ]))

    # --- repair ---
    # The fixture plants WP3 and /srv/humanvoice/private, so preflight should
    # produce findings. repair needs a findings file plus a draft artifact.
    pf = run_step("preflight_json_for_repair", [
        "preflight", str(snapshot_dir),
        "--brief", str(brief_path),
        "--deterministic",
    ])
    findings_path = work / "findings.json"
    wrote_findings = False
    try:
        findings_path.write_text(pf["stdout"])
        json.loads(pf["stdout"])
        wrote_findings = True
    except Exception as e:
        pf["findings_capture_error"] = str(e)
    steps.append(pf)

    if draft_paths and wrote_findings:
        t = time.time()
        rs = run_step("repair", [
            "repair", str(draft_paths[0]),
            "--findings", str(findings_path),
            "--brief", str(brief_path),
        ])
        r_run = newest_run_dir(t, snapshot_dir)
        rs["tokens"] = collect_tokens(r_run)
        steps.append(rs)
    else:
        steps.append({
            "step": "repair",
            "skipped": True,
            "reason": (
                "no draft artifact available"
                if not draft_paths else
                "preflight stdout was not valid JSON"
            ),
        })

    # --- release ---
    steps.append(run_step("release", [
        "release", str(snapshot_dir),
        "--brief", str(brief_path),
        "--output", str(work / "release"),
    ]))

    total_ms = int((time.monotonic() - pilot_start_mono) * 1000)

    model_steps = [s for s in steps if s.get("tokens")]
    tin = sum(
        t["input_tokens"] or 0
        for s in model_steps for t in s["tokens"]
        if isinstance(t.get("input_tokens"), int)
    )
    tout = sum(
        t["output_tokens"] or 0
        for s in model_steps for t in s["tokens"]
        if isinstance(t.get("output_tokens"), int)
    )
    det = [s for s in steps if not s.get("tokens") and "wall_clock_ms" in s]

    report = {
        "record_type": "InstrumentedPilot",
        "schema_version": "HV-SCHEMA-1.0",
        "pilot_date": datetime.fromtimestamp(
            pilot_start_wall, timezone.utc).isoformat(),
        "fixture": str(fixture.relative_to(REPO)),
        "scope": "internal evaluation (G4 Option A)",
        "runner": "tools/instrumented_pilot.py",
        "operator_present": False,
        "steps": steps,
        "totals": {
            "end_to_end_wall_clock_ms": total_ms,
            "end_to_end_wall_clock_s": round(total_ms / 1000, 1),
            "input_tokens": tin,
            "output_tokens": tout,
            "model_invoking_steps": len(model_steps),
            "deterministic_steps": len(det),
            "deterministic_overhead_ms": sum(s["wall_clock_ms"] for s in det),
        },
        "contract_comparison": {
            "cap_operator_minutes": 180,
            "cap_tokens_usd": 20,
            "measured_wall_clock_minutes": round(total_ms / 60000, 2),
            "operator_wait_time": (
                "not measured - no human in the loop; wall-clock is machine time only"
            ),
            "note": (
                "runtime_manifest.latency_ms is 0 for every command, so per-invocation "
                "API latency is measured externally by this wrapper"
            ),
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {out_path.relative_to(REPO)}", file=sys.stderr)
    print(f"end-to-end {report['totals']['end_to_end_wall_clock_s']}s, "
          f"{tin} in / {tout} out tokens", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
