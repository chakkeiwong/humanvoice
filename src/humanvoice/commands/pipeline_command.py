#!/usr/bin/env python3
"""
hv pipeline - Master orchestration for draft→repair→assemble→repair→release cycles.

Automates the full authoring pipeline:
  1. Plan generation (blueprint)
  2. Draft each section with repair cycles
  3. Assembly with repair if retention < 99%
  4. Release gate checks

Exit codes:
  0 - pipeline completed, document released
  1 - deterministic gate failure (blocked release)
  2 - abstention or unresolved policy-dependent result
  3 - invalid input, brief, schema, or command usage
  4 - internal implementation error
  5 - security or trust-boundary violation

Repair strategy:
  - After each draft section: repair if preflight finds violations
  - After assembly: repair if retention_vs_drafts < 99%
  - Max 3 repair cycles per stage with oscillation detection
  - Human approval surfaced when repair hits cycle limit or oscillation

Design principles:
  - Self-correcting: automatically repair losses at each stage
  - Fail-closed: block release on unresolved issues
  - Transparent: emit full audit trail of decisions and repairs
  - Bounded: hard limits on repair attempts prevent infinite loops
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from humanvoice.commands import (
    plan_command,
    draft_command,
    assemble_command,
    preflight_command,
    repair_command,
    release_command,
)
from humanvoice.paths import runs_dir, new_run_dir, mint_run_id


class _StageArgs:
    """
    Argument object for a delegated command's run().

    The sub-commands read their inputs off an argparse.Namespace-shaped object.
    One permissive holder beats a bespoke class per stage: it keeps each call
    site to the field names that stage actually reads.
    """

    def __init__(self, **fields):
        self.__dict__.update(fields)


def _safe_title(section_title: str) -> str:
    """
    Filename stem for a section, matching draft_command._write_draft exactly.

    The pipeline must locate the file the draft stage wrote. Any divergence here
    means the orchestrator reports a missing draft for a draft that exists, so
    this mirrors that sanitisation rather than re-inventing it.
    """
    safe = "".join(
        c if c.isalnum() or c in (" ", "_") else "_"
        for c in section_title.lower()
    )
    return safe.replace(" ", "_")[:50]


class PipelineState:
    """
    Track pipeline execution state across stages.

    Maintains:
    - Run ID for all artifacts
    - Blueprint after plan stage
    - Draft paths and correspondence manifests per section
    - Assembly path and correspondence
    - Repair cycles and outcomes per stage
    - Gate check results
    """

    def __init__(self, snapshot_dir: Path, brief_path: Path, run_id: str = None):
        self.snapshot_dir = snapshot_dir.resolve()
        self.brief_path = brief_path.resolve()
        self.run_id = run_id or mint_run_id()
        self.run_dir = new_run_dir(snapshot_dir, self.run_id)

        # Stage outputs
        self.blueprint_path: Optional[Path] = None
        self.blueprint: Optional[Dict[str, Any]] = None
        self.section_drafts: List[Dict[str, Any]] = []  # {"index", "path", "repaired", "cycles"}
        self.preflight_path: Optional[Path] = None
        self.preflight_findings: int = 0
        self.assembly_path: Optional[Path] = None

        # Gate results
        self.release_status: Optional[str] = None
        self.release_blocks: List[Dict[str, Any]] = []
        self.release_gate_results: Dict[str, Any] = {}

        # Pipeline decision log
        self.decisions: List[Dict[str, Any]] = []

    def log_decision(self, stage: str, decision: str, detail: Dict[str, Any] = None):
        """Record pipeline decision for audit trail."""
        self.decisions.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "decision": decision,
            "detail": detail or {},
        })

    def to_manifest(self) -> Dict[str, Any]:
        """Serialize pipeline state to JSON manifest."""
        return {
            "record_type": "PipelineExecution",
            "schema_version": "HV-SCHEMA-1.1",
            "run_id": self.run_id,
            "snapshot_dir": str(self.snapshot_dir),
            "brief_path": str(self.brief_path),
            "blueprint_path": str(self.blueprint_path) if self.blueprint_path else None,
            "section_drafts": [
                {
                    "index": d["index"],
                    "path": str(d["path"]),
                    "repaired": d["repaired"],
                    "repair_cycles": d["cycles"],
                }
                for d in self.section_drafts
            ],
            "preflight_path": str(self.preflight_path) if self.preflight_path else None,
            "preflight_findings": self.preflight_findings,
            "assembly_path": str(self.assembly_path) if self.assembly_path else None,
            "release_status": self.release_status,
            "release_gate_results": self.release_gate_results,
            "release_blocks": self.release_blocks,
            "decisions": self.decisions,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    def write_manifest(self):
        """Write pipeline manifest to run directory."""
        manifest_path = self.run_dir / "pipeline_manifest.json"
        manifest_path.write_text(json.dumps(self.to_manifest(), indent=2))
        return manifest_path


def _run_plan_stage(state: PipelineState, mock: bool = False) -> int:
    """
    Generate blueprint from brief and evidence.

    Returns:
      0 - blueprint generated
      2 - abstention (ambiguous brief)
      3+ - error
    """
    print(f"\n=== STAGE 1: PLAN ===", file=sys.stderr)
    print(f"Generating blueprint from {state.brief_path}", file=sys.stderr)

    exit_code = plan_command.run(_StageArgs(
        snapshot=state.snapshot_dir,
        brief=state.brief_path,
        run_id=state.run_id,
        mock=mock,
    ))

    if exit_code == 2:
        state.log_decision("plan", "abstention", {"reason": "ambiguous_brief"})
        print("Plan abstained: brief requires clarification", file=sys.stderr)
        return exit_code

    if exit_code != 0:
        return exit_code

    # run_id is threaded into plan_command, so the blueprint lands in this
    # pipeline's run directory. No cross-run search: finding a blueprint from
    # an unrelated run would silently draft against the wrong plan.
    blueprint_path = state.run_dir / "blueprint.json"
    if not blueprint_path.exists():
        print(f"Error: blueprint.json not found at {blueprint_path}", file=sys.stderr)
        return 4

    state.blueprint_path = blueprint_path
    state.blueprint = json.loads(blueprint_path.read_text())
    sections = state.blueprint.get("blueprint", {}).get("sections", [])

    # A zero-section blueprint is not a plan. Proceeding would assemble an empty
    # document and hand it to the release gate as if it were a document, which is
    # exactly the fail-open shape this pipeline exists to prevent.
    if not sections:
        state.log_decision("plan", "abstention", {
            "reason": "empty_blueprint",
            "detail": "Plan returned zero sections; nothing to draft.",
        })
        print(
            "Plan abstained: blueprint contains zero sections. "
            "Check that the brief and snapshot evidence support a plan.",
            file=sys.stderr,
        )
        return 2

    state.log_decision("plan", "blueprint_generated", {"num_sections": len(sections)})
    print(f"Blueprint generated: {len(sections)} sections", file=sys.stderr)
    return 0


def _run_draft_section(
    state: PipelineState,
    section_index: int,
    mock: bool = False,
) -> Tuple[int, Optional[Path]]:
    """
    Draft one section from blueprint.

    Returns:
      (exit_code, draft_path)
      0 - draft produced
      1 - retention gate failure
      2 - abstention
      3+ - error
    """
    print(f"\n=== STAGE 2: DRAFT SECTION {section_index} ===", file=sys.stderr)

    exit_code = draft_command.run(_StageArgs(
        snapshot=state.snapshot_dir,
        blueprint=state.blueprint_path,
        brief=state.brief_path,
        section=section_index,
        run_id=state.run_id,
        mock=mock,
    ))

    if exit_code != 0:
        return exit_code, None

    # draft_command writes draft_<safe_title>.tex directly into the run
    # directory it was given, not into a drafted/ subdirectory.
    section_title = state.blueprint["blueprint"]["sections"][section_index].get(
        "title", f"section_{section_index}"
    )
    draft_path = state.run_dir / f"draft_{_safe_title(section_title)}.tex"

    if not draft_path.exists():
        print(f"Error: draft .tex not found at {draft_path}", file=sys.stderr)
        return 4, None

    state.log_decision("draft", f"section_{section_index}_completed", {"path": str(draft_path)})
    return 0, draft_path


def _run_preflight(state: PipelineState) -> Tuple[int, Optional[Path]]:
    """
    Run deterministic preflight on the snapshot.

    Preflight reads the snapshot's source files, not drafts, so it is a
    property of the snapshot and runs once per pipeline rather than once per
    section. The release gate requires a passing preflight record, so this also
    supplies the record that gate reads.

    Returns:
      (exit_code, findings_path)
      findings_path is the preflight record when it carries findings, else None.
    """
    print(f"\n=== STAGE 2: PREFLIGHT ===", file=sys.stderr)
    print(f"Checking snapshot source against the brief", file=sys.stderr)

    exit_code = preflight_command.run(_StageArgs(
        snapshot=state.snapshot_dir,
        brief=state.brief_path,
        run_id=state.run_id,
        deterministic=True,
    ))

    if exit_code >= 3:
        return exit_code, None

    # preflight_command writes <preflight_id>.json into the run directory.
    preflight_files = sorted(state.run_dir.glob("preflight-*.json"), reverse=True)
    if not preflight_files:
        # Preflight reported a result but left no record. The release gate reads
        # records, not exit codes, so a missing record is an internal fault
        # rather than a clean pass.
        print("Error: preflight left no record in the run directory", file=sys.stderr)
        return 4, None

    findings_path = preflight_files[0]
    findings = json.loads(findings_path.read_text()).get("findings", [])
    state.preflight_path = findings_path
    state.preflight_findings = len(findings)
    state.log_decision("preflight", "completed", {
        "findings": len(findings),
        "exit_code": exit_code,
        "record": str(findings_path),
    })
    print(f"Preflight: {len(findings)} finding(s)", file=sys.stderr)
    return exit_code, findings_path if findings else None


def _run_repair_on_draft(
    state: PipelineState,
    draft_path: Path,
    findings_path: Path,
    mock: bool = False,
) -> Tuple[int, Optional[Path]]:
    """
    Apply repair cycles to a draft.

    Returns:
      (exit_code, repaired_path)
      0 - repair converged
      1 - repair failed (oscillation or cycle limit)
      3+ - error
    """
    print(f"Repairing {draft_path.name}...", file=sys.stderr)

    exit_code = repair_command.run(_StageArgs(
        draft=draft_path,
        findings=findings_path,
        brief=state.brief_path,
        output_dir=None,  # default: <draft dir>/revisions
        mock=mock,
    ))

    if exit_code != 0:
        return exit_code, None

    # repair_command publishes to revisions/rev-<cycle>-<hash>/<draft filename>.
    # A revision counts as published only once its manifest exists, so select on
    # the manifest and take the highest cycle number.
    revisions_dir = draft_path.parent / "revisions"
    published = sorted(revisions_dir.glob("rev-*/revision_manifest.json"))
    if not published:
        print("Error: repair reported success but published no revision", file=sys.stderr)
        return 4, None

    repaired_path = published[-1].parent / draft_path.name
    if not repaired_path.exists():
        print(f"Error: published revision has no {draft_path.name}", file=sys.stderr)
        return 4, None

    print(f"Repair published: {repaired_path.parent.name}", file=sys.stderr)
    return 0, repaired_path


def _repair_section_drafts(
    state: PipelineState,
    findings_path: Path,
    mock: bool = False,
) -> int:
    """
    Repair every drafted section against the standing preflight findings.

    Runs after drafting because repair edits draft text, and after preflight
    because repair needs findings to act on. A section whose repair does not
    converge keeps its unrepaired draft and is recorded as unresolved: the
    release gate reads those records, so leaving the original in place surfaces
    the problem rather than hiding it behind a partial edit.

    Returns 0 when the pass completed (including with unresolved sections), or
    the sub-command's code for an input/internal fault.
    """
    print(f"\n=== STAGE 4: REPAIR ===", file=sys.stderr)
    print(f"Repairing {len(state.section_drafts)} section(s) against preflight findings",
          file=sys.stderr)

    for entry in state.section_drafts:
        exit_code, repaired_path = _run_repair_on_draft(
            state, entry["path"], findings_path, mock
        )

        if exit_code == 0 and repaired_path:
            entry["path"] = repaired_path
            entry["repaired"] = True
            entry["cycles"] = entry["cycles"] + 1
            state.log_decision("repair", f"section_{entry['index']}_converged", {
                "path": str(repaired_path),
            })
        elif exit_code in (1, 2):
            # Oscillation, cycle limit, or abstention. repair_command has
            # written an unresolved_author_choice marker; the release gate reads
            # it, so the pipeline continues and lets that gate speak.
            state.log_decision("repair", f"section_{entry['index']}_unresolved", {
                "exit_code": exit_code,
                "detail": "repair did not converge; unrepaired draft retained",
            })
            print(f"  section {entry['index']}: unresolved, keeping unrepaired draft",
                  file=sys.stderr)
        else:
            return exit_code

    return 0


def _run_assemble_stage(state: PipelineState) -> int:
    """
    Assemble drafted sections into the complete document.

    Assembly re-derives its inputs from the snapshot's run records rather than
    taking this pipeline's in-memory list, and it gates itself on protected-object
    retention against those drafts. Both properties are deliberate: assembly
    verifies the text it actually consumed, so it cannot be talked into passing by
    an upstream stage's account of what it produced.

    Returns:
      0 - assembly succeeded
      2 - abstention (missing drafts, or retention below threshold)
      3+ - error
    """
    print(f"\n=== STAGE 5: ASSEMBLE ===", file=sys.stderr)
    print(f"Assembling {len(state.section_drafts)} section(s)", file=sys.stderr)

    exit_code = assemble_command.run(_StageArgs(
        snapshot=state.snapshot_dir,
        brief=state.brief_path,
        output=None,  # default: <snapshot>/.humanvoice/revisions/assembled
    ))

    if exit_code == 2:
        state.log_decision("assemble", "abstention", {
            "detail": "assembly abstained; see its stderr for the specific reason",
        })
        print("Assembly abstained", file=sys.stderr)
        return exit_code

    if exit_code != 0:
        return exit_code

    assembled_dir = state.snapshot_dir / ".humanvoice" / "revisions" / "assembled"
    assembled_path = assembled_dir / "assembled_document.tex"
    if not assembled_path.exists():
        # Named directly rather than globbed: the directory also holds the
        # blacklined comparison, and a newest-first glob would sometimes pick it.
        print(f"Error: assembled document not found at {assembled_path}", file=sys.stderr)
        return 4

    state.assembly_path = assembled_path

    # Carry assembly's own retention figures into the pipeline record so the
    # audit trail shows what assembly measured, not just that it exited 0.
    correspondence = sorted(assembled_dir.glob("assembly_correspondence_*.json"))
    detail: Dict[str, Any] = {"path": str(assembled_path)}
    if correspondence:
        try:
            record = json.loads(correspondence[-1].read_text())
            detail["retention_vs_drafts"] = record.get("retention_rate")
            detail["retention_vs_source"] = record.get("retention_vs_source")
            detail["correspondence_manifest"] = str(correspondence[-1])
        except Exception as e:
            detail["correspondence_unreadable"] = str(e)

    state.log_decision("assemble", "document_assembled", detail)
    print(f"Assembly complete: {assembled_path.name}", file=sys.stderr)
    return 0


def _run_release_stage(state: PipelineState) -> int:
    """
    Run release gate checks and generate the reader packet if all gates pass.

    Returns:
      0 - release authorized
      1 - release blocked
      3+ - error
    """
    print(f"\n=== STAGE 6: RELEASE ===", file=sys.stderr)
    print(f"Running gate checks on {state.snapshot_dir}", file=sys.stderr)

    exit_code = release_command.run(_StageArgs(
        snapshot=state.snapshot_dir,
        brief=state.brief_path,
        output=None,  # default: <snapshot>/release
    ))

    if exit_code == 0:
        state.release_status = "released"
        state.log_decision("release", "authorized", {})
        print("Release authorized", file=sys.stderr)
    elif exit_code == 1:
        state.release_status = "blocked"
        # release_command writes exactly one record: release/release_decision.json.
        decision_path = state.snapshot_dir / "release" / "release_decision.json"
        if decision_path.exists():
            try:
                decision = json.loads(decision_path.read_text())
                state.release_blocks = decision.get("exceptions", [])
                state.release_gate_results = decision.get("gate_results", {})
            except Exception as e:
                print(f"Warning: release decision unreadable: {e}", file=sys.stderr)
        else:
            print(f"Warning: no release decision record at {decision_path}", file=sys.stderr)

        state.log_decision("release", "blocked", {
            "blocked_gates": [b.get("gate") for b in state.release_blocks],
        })

    return exit_code


def _print_summary(state: PipelineState, exit_code: int, manifest_path: Path) -> None:
    """
    Print the closing account of the run.

    Repaired and unresolved section counts are reported explicitly. A run that
    releases while sections stand unrepaired is a different outcome from a clean
    release, and the difference should not have to be reconstructed from the
    manifest.
    """
    repaired = sum(1 for d in state.section_drafts if d["repaired"])
    unresolved = [
        d["decision"] for d in state.decisions
        if d["stage"] == "repair" and d["decision"].endswith("_unresolved")
    ]

    print(f"\n=== PIPELINE SUMMARY ===", file=sys.stderr)
    print(f"Run:       {state.run_id}", file=sys.stderr)
    print(f"Sections:  {len(state.section_drafts)} drafted, {repaired} repaired", file=sys.stderr)
    print(f"Preflight: {state.preflight_findings} finding(s)", file=sys.stderr)
    if unresolved:
        print(f"Unresolved repairs: {len(unresolved)} section(s)", file=sys.stderr)
    print(f"Manifest:  {manifest_path}", file=sys.stderr)

    if exit_code == 0:
        print("\nPipeline complete: document released", file=sys.stderr)
    elif exit_code == 1:
        gates = [b.get("gate") for b in state.release_blocks] or ["(no record)"]
        print(f"\nPipeline blocked at release by: {', '.join(gates)}", file=sys.stderr)
    elif exit_code == 2:
        print("\nPipeline abstained; see stage output above", file=sys.stderr)


def run(args) -> int:
    """
    Execute the full pipeline: plan → preflight → draft → repair → assemble → release.

    Stage order follows the data, not the seven-command listing: preflight is
    deterministic and reads the snapshot source, so it runs before drafting and
    supplies the findings that the repair stage acts on.

    Exit codes:
      0 - pipeline completed, document released
      1 - deterministic gate failure (release blocked)
      2 - abstention at some stage
      3 - invalid input
      4 - internal error
    """
    snapshot_dir = Path(args.snapshot).resolve()
    brief_path = Path(args.brief).resolve()

    if not snapshot_dir.exists():
        print(f"Error: snapshot directory not found: {snapshot_dir}", file=sys.stderr)
        return 3

    if not brief_path.exists():
        print(f"Error: brief not found: {brief_path}", file=sys.stderr)
        return 3

    # Initialize pipeline state
    state = PipelineState(snapshot_dir, brief_path, run_id=getattr(args, 'run_id', None))

    print(f"Pipeline run ID: {state.run_id}", file=sys.stderr)
    print(f"Snapshot: {snapshot_dir}", file=sys.stderr)
    print(f"Brief: {brief_path}", file=sys.stderr)

    mock = getattr(args, "mock", False)

    try:
        # Stage 1: plan. A failure here has nothing downstream to run.
        exit_code = _run_plan_stage(state, mock=mock)
        if exit_code != 0:
            state.write_manifest()
            return exit_code

        # Stage 2: preflight. Deterministic and source-level, so it runs once and
        # before drafting: its findings are the input the repair stage acts on.
        exit_code, findings_path = _run_preflight(state)
        if exit_code >= 3:
            state.write_manifest()
            return exit_code

        # Stage 3: draft every section. draft_command enforces register
        # compliance itself and refuses to write a violating or empty draft, so a
        # section that fails here has no file to repair. Continue past failures
        # rather than aborting — assembly will record gaps, and those gaps will
        # fail the release gate, giving the user the partial document plus a
        # precise list of what needs manual retry.
        sections = state.blueprint["blueprint"]["sections"]
        print(f"\n=== STAGE 3: DRAFT ({len(sections)} sections) ===", file=sys.stderr)
        draft_failures = []
        for section_idx in range(len(sections)):
            exit_code, draft_path = _run_draft_section(state, section_idx, mock=mock)
            if exit_code != 0:
                section_title = sections[section_idx].get("title", f"Section {section_idx}")
                print(
                    f"✗ Section {section_idx} '{section_title}' failed (exit {exit_code})",
                    file=sys.stderr,
                )
                draft_failures.append({
                    "index": section_idx,
                    "title": section_title,
                    "exit_code": exit_code,
                })
                state.log_decision("draft", f"section_{section_idx}_failed", {
                    "exit_code": exit_code,
                })
                # Continue to next section instead of returning
            else:
                state.section_drafts.append({
                    "index": section_idx,
                    "path": draft_path,
                    "repaired": False,
                    "cycles": 0,
                })

        # Report draft stage summary
        if draft_failures:
            print(f"\nDraft stage: {len(state.section_drafts)}/{len(sections)} succeeded, "
                  f"{len(draft_failures)} failed", file=sys.stderr)
            print("Failed sections:", file=sys.stderr)
            for failure in draft_failures:
                print(f"  Section {failure['index']} '{failure['title']}' (exit {failure['exit_code']})",
                      file=sys.stderr)
            print("Continuing to assembly with partial drafts...", file=sys.stderr)
        else:
            print(f"Draft stage: all {len(sections)} sections succeeded", file=sys.stderr)

        # Stage 4: repair, only when preflight actually found something. Repair
        # with no findings is a no-op that still costs an inference call.
        if findings_path is not None:
            exit_code = _repair_section_drafts(state, findings_path, mock=mock)
            if exit_code >= 3:
                state.write_manifest()
                return exit_code
        else:
            print(f"\n=== STAGE 4: REPAIR (skipped) ===", file=sys.stderr)
            print("No preflight findings; nothing to repair", file=sys.stderr)
            state.log_decision("repair", "skipped", {"reason": "no_preflight_findings"})

        # Stage 5: assemble. Reads the repaired text from the run records.
        exit_code = _run_assemble_stage(state)
        if exit_code != 0:
            state.write_manifest()
            return exit_code

        # Stage 6: release gates.
        exit_code = _run_release_stage(state)

        manifest_path = state.write_manifest()
        _print_summary(state, exit_code, manifest_path)
        return exit_code

    except Exception as e:
        print(f"Pipeline error: {e}", file=sys.stderr)
        state.log_decision("pipeline", "error", {"exception": str(e)})
        state.write_manifest()
        return 4


def main():
    """CLI entry point for testing."""
    parser = argparse.ArgumentParser(
        prog='hv pipeline',
        description='Master orchestration for draft→repair→assemble→repair→release cycles'
    )
    parser.add_argument('snapshot', type=Path, help='Snapshot directory from hv init')
    parser.add_argument('--brief', type=Path, required=True, help='Reader brief (JSON)')
    parser.add_argument('--run-id', type=str, help='Reuse existing run ID')
    parser.add_argument('--mock', action='store_true', help='Use mock mode (no API calls)')

    args = parser.parse_args()
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
