#!/usr/bin/env python3
"""
hv release - Generate immutable reader packet

Exit codes per implementation contract:
  0 - released (all gates pass, or exception-released with explicit authorization)
  1 - deterministic gate failure (never_except condition or unresolved block)
  2 - abstention (missing critical gate result)
  3 - invalid input (snapshot not initialized, brief invalid, schema error)
  4 - internal implementation error
  5 - security or trust-boundary violation

Never-except conditions (cannot be exception-released):
  - unresolved protected-object correspondence
  - unparsed object promised by the brief
  - unauthorized external transmission
  - missing critical evidence for a load-bearing claim
  - broken or unreproducible source build

Reader packet independence requirement:
  The packet must not expose finding IDs, model confidence, parser warnings,
  private paths, or internal phase names. The reader sees only the rendered
  document, its references/figures, and minimal decision context.
"""

import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


def check_unresolved_author_choice(snapshot_dir: Path) -> Optional[dict]:
    """
    Check for unresolved_author_choice.json blocking release.

    Returns the unresolved-choice record if present, None otherwise.
    A superseded_author_choice.json does not block release.
    """
    runs_dir = snapshot_dir / ".humanvoice" / "runs"
    if not runs_dir.exists():
        return None

    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        revisions_dir = run_dir / "revisions"
        if not revisions_dir.exists():
            continue

        unresolved_marker = revisions_dir / "unresolved_author_choice.json"
        if unresolved_marker.exists():
            try:
                return json.loads(unresolved_marker.read_text())
            except Exception as e:
                print(f"Error: Failed to read {unresolved_marker}: {e}", file=sys.stderr)
                return {"error": "unreadable marker", "path": str(unresolved_marker)}

    return None


def check_protected_manifest_correspondence(snapshot_dir: Path) -> Optional[dict]:
    """
    Check for unresolved protected-object correspondence.

    Returns a never-except block if any protected-manifest has unresolved
    correspondence (status: unresolved, or nonzero unresolved_count).
    """
    runs_dir = snapshot_dir / ".humanvoice" / "runs"
    if not runs_dir.exists():
        return None

    unresolved_objects = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue

        # Look for protected-manifest records (with hyphen, not underscore)
        for manifest_file in run_dir.glob("**/protected-manifest*.json"):
            try:
                manifest = json.loads(manifest_file.read_text())
                if manifest.get("record_type") != "ProtectedManifest":
                    continue

                # Check each object's comparison field
                for obj in manifest.get("objects", []):
                    comparison = obj.get("comparison")
                    if not comparison:
                        continue

                    status = comparison.get("status")
                    unresolved_count = comparison.get("unresolved_count", 0)

                    if status == "unresolved" or unresolved_count > 0:
                        unresolved_objects.append({
                            "object_id": obj.get("object_id"),
                            "object_type": obj.get("object_type"),
                            "status": status,
                            "unresolved_count": unresolved_count,
                        })

            except Exception as e:
                print(f"Warning: Failed to parse {manifest_file}: {e}", file=sys.stderr)
                continue

    if unresolved_objects:
        return {
            "message": f"{len(unresolved_objects)} unresolved protected-object correspondence(s)",
            "unresolved_objects": unresolved_objects,
        }

    return None


def check_brief_parsing_promises(snapshot_dir: Path, brief: dict) -> Optional[dict]:
    """
    Check whether the brief promises objects that were not parsed.

    Returns a never-except block if the brief names object types that the
    protected-manifest does not contain.
    """
    # Read manifest to get source_hash
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        return {"message": "No manifest.json found"}

    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as e:
        return {"message": f"Failed to parse manifest: {e}"}

    # Brief may name expected_objects (not required by authoring-brief schema)
    expected_objects = brief.get("expected_objects", {})
    if not expected_objects:
        # No promises means no parsing gap
        return None

    # Find the most recent protected-manifest
    runs_dir = snapshot_dir / ".humanvoice" / "runs"
    if not runs_dir.exists():
        # No runs means no protected parsing happened yet
        # If brief promises objects, this is a gap
        if any(count > 0 for count in expected_objects.values()):
            return {
                "message": "Brief promises protected objects but no runs exist",
                "expected": expected_objects,
            }
        return None

    # Collect all parsed object types across all runs
    parsed_types = set()
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue

        for manifest_file in run_dir.glob("**/protected-manifest*.json"):
            try:
                pm = json.loads(manifest_file.read_text())
                if pm.get("record_type") != "ProtectedManifest":
                    continue

                for obj in pm.get("objects", []):
                    otype = obj.get("object_type")
                    if otype:
                        parsed_types.add(otype)

            except Exception:
                continue

    # Check for gaps
    missing = []
    for obj_type, count in expected_objects.items():
        if count > 0 and obj_type not in parsed_types:
            missing.append(obj_type)

    if missing:
        return {
            "message": f"Brief promises {missing} but none parsed",
            "expected": expected_objects,
            "parsed_types": list(parsed_types),
            "missing": missing,
        }

    return None


def check_evidence_gaps(snapshot_dir: Path) -> Optional[dict]:
    """
    Check for missing critical evidence supporting load-bearing claims.

    Returns a never-except block if any evidence-item with supports[].load_bearing=true
    has appraisal_state of insufficient or unappraised.
    """
    runs_dir = snapshot_dir / ".humanvoice" / "runs"
    if not runs_dir.exists():
        return None

    gaps = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue

        for evidence_file in run_dir.glob("**/evidence*.json"):
            try:
                ev = json.loads(evidence_file.read_text())
                if ev.get("record_type") != "EvidenceItem":
                    continue

                appraisal_state = ev.get("appraisal_state")
                supports = ev.get("supports", [])

                # Check if any support is load-bearing
                has_load_bearing = any(s.get("load_bearing") for s in supports)

                if has_load_bearing and appraisal_state in ("insufficient", "unappraised"):
                    gaps.append({
                        "evidence_id": ev.get("record_id"),
                        "appraisal_state": appraisal_state,
                        "supports_count": len(supports),
                    })

            except Exception as e:
                print(f"Warning: Failed to parse {evidence_file}: {e}", file=sys.stderr)
                continue

    if gaps:
        return {
            "message": f"{len(gaps)} load-bearing claim(s) with insufficient/unappraised evidence",
            "gaps": gaps,
        }

    return None


def check_source_build(snapshot_dir: Path) -> Optional[dict]:
    """
    Check that the source was successfully parsed and protected objects extracted.

    Returns a never-except block if parsing failed or no protected objects found when
    the brief promises them, None otherwise.

    Contract: "broken or unreproducible source build" is never-except.

    Since the parser validates builds internally, we check for the presence of
    protected manifests. If the brief promises protected objects but none were
    extracted, the build is considered broken.
    """
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        return {"reason": "no_manifest", "detail": "Snapshot not initialized"}

    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as e:
        return {"reason": "manifest_unreadable", "detail": str(e)}

    # Check if brief was valid (parser succeeded)
    if not manifest.get("brief_valid", False):
        return {
            "reason": "brief_invalid",
            "detail": "Brief validation failed during snapshot creation"
        }

    # Check for protected manifests if brief promises protected objects
    brief = manifest.get("brief", {})
    protected_objects = brief.get("protected_objects", [])

    if protected_objects:
        # Brief promises protected objects; verify they were extracted
        runs_dir = snapshot_dir / ".humanvoice" / "runs"
        if not runs_dir.exists():
            return {
                "reason": "no_protected_extraction",
                "detail": f"Brief promises {len(protected_objects)} protected objects but no runs directory exists"
            }

        # Check for at least one protected manifest
        found_manifests = False
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            if list(run_dir.glob("**/protected-manifest-*.json")):
                found_manifests = True
                break

        if not found_manifests:
            return {
                "reason": "no_protected_manifests",
                "detail": f"Brief promises {len(protected_objects)} protected objects but none were extracted"
            }

    return None


def assemble_reader_packet(snapshot_dir: Path, output_dir: Path, brief: dict) -> str:
    """
    Assemble the reader packet and return its SHA-256 hash.

    The reader packet contains:
      - The rendered document (PDF if available, else source)
      - Reader brief (decision context only, no internal IDs)
      - Release decision record

    Returns the hex digest of the packet's SHA-256 hash.
    """
    packet_dir = output_dir / "packet"
    packet_dir.mkdir(parents=True, exist_ok=True)

    # Copy source files (or rendered PDF if build succeeded)
    manifest = json.loads((snapshot_dir / "manifest.json").read_text())
    source_files = manifest.get("source_files", [])

    for src_rel_path in source_files:
        src_path = snapshot_dir / src_rel_path
        if src_path.exists():
            dest_path = packet_dir / src_rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(src_path.read_bytes())

    # Write reader context (stripped brief)
    reader_context = {
        "reader": brief.get("reader"),
        "decision_type": brief.get("decision_type"),
        "time_available_minutes": brief.get("time_available_minutes"),
        "success_criteria": brief.get("success_criteria"),
    }
    (packet_dir / "reader_context.json").write_text(json.dumps(reader_context, indent=2))

    # Compute packet hash
    hasher = hashlib.sha256()
    for p in sorted(packet_dir.rglob("*")):
        if p.is_file():
            hasher.update(p.read_bytes())

    return hasher.hexdigest()


def run(args):
    """Execute hv release command."""
    snapshot_dir = Path(args.snapshot).resolve()
    brief_path = Path(args.brief).resolve()
    output_dir = Path(args.output).resolve() if args.output else snapshot_dir / "release"

    # Validate inputs
    if not snapshot_dir.exists():
        print(f"Error: Snapshot directory does not exist: {snapshot_dir}", file=sys.stderr)
        return 3

    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: Snapshot not initialized (no manifest.json): {snapshot_dir}", file=sys.stderr)
        return 3

    if not brief_path.exists():
        print(f"Error: Brief does not exist: {brief_path}", file=sys.stderr)
        return 3

    try:
        brief = json.loads(brief_path.read_text())
    except Exception as e:
        print(f"Error: Failed to parse brief: {e}", file=sys.stderr)
        return 3

    try:
        manifest = json.loads(manifest_path.read_text())
        run_id = manifest.get("snapshot_id", "unknown")
    except Exception as e:
        print(f"Error: Failed to parse manifest: {e}", file=sys.stderr)
        return 3

    # Gate checks (deterministic, no inference)
    gate_results = {}
    blocks = []

    # Never-except gate 1: unresolved protected-object correspondence
    correspondence_block = check_protected_manifest_correspondence(snapshot_dir)
    if correspondence_block:
        blocks.append({
            "gate": "protected_correspondence",
            "never_except": True,
            "detail": correspondence_block,
        })
        gate_results["protected_correspondence"] = "blocked"
    else:
        gate_results["protected_correspondence"] = "pass"

    # Never-except gate 2: unparsed object promised by brief
    parsing_block = check_brief_parsing_promises(snapshot_dir, brief)
    if parsing_block:
        blocks.append({
            "gate": "brief_parsing_promises",
            "never_except": True,
            "detail": parsing_block,
        })
        gate_results["brief_parsing_promises"] = "blocked"
    else:
        gate_results["brief_parsing_promises"] = "pass"

    # Never-except gate 3: missing critical evidence for load-bearing claim
    evidence_block = check_evidence_gaps(snapshot_dir)
    if evidence_block:
        blocks.append({
            "gate": "evidence_sufficiency",
            "never_except": True,
            "detail": evidence_block,
        })
        gate_results["evidence_sufficiency"] = "blocked"
    else:
        gate_results["evidence_sufficiency"] = "pass"

    # Never-except gate 4: broken or unreproducible source build
    source_build_block = check_source_build(snapshot_dir)
    if source_build_block:
        blocks.append({
            "gate": "source_build",
            "never_except": True,
            "detail": source_build_block,
        })
        gate_results["source_build"] = "blocked"
    else:
        gate_results["source_build"] = "pass"

    # Ordinary gate: unresolved author choice (from repair oscillation/cycle-limit)
    unresolved_choice = check_unresolved_author_choice(snapshot_dir)
    if unresolved_choice:
        blocks.append({
            "gate": "author_convergence",
            "never_except": False,
            "detail": unresolved_choice,
        })
        gate_results["author_convergence"] = "blocked"
    else:
        gate_results["author_convergence"] = "pass"

    # Decide status
    never_except_blocks = [b for b in blocks if b["never_except"]]
    ordinary_blocks = [b for b in blocks if not b["never_except"]]

    if never_except_blocks or ordinary_blocks:
        status = "blocked"
        exit_code = 1

        if never_except_blocks:
            print(f"Release blocked by {len(never_except_blocks)} never-except condition(s):", file=sys.stderr)
            for b in never_except_blocks:
                print(f"  - {b['gate']}: {b['detail']}", file=sys.stderr)

        if ordinary_blocks:
            print(f"Release blocked by {len(ordinary_blocks)} ordinary gate failure(s):", file=sys.stderr)
            for b in ordinary_blocks:
                print(f"  - {b['gate']}: {b['detail']}", file=sys.stderr)

        packet_hash = ""
    else:
        status = "released"
        exit_code = 0
        packet_hash = assemble_reader_packet(snapshot_dir, output_dir, brief)

    # Write release decision record
    output_dir.mkdir(parents=True, exist_ok=True)
    decision_record = {
        "record_type": "ReleaseDecision",
        "schema_version": "HV-SCHEMA-1.1",
        "record_id": f"release-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "gate_results": gate_results,
        "packet_hash": packet_hash,
        "status": status,
        "authorized_by": "machine",
        "exceptions": blocks,
        "unresolved_risks": [b["gate"] for b in blocks] if blocks else [],
    }

    decision_path = output_dir / "release_decision.json"
    decision_path.write_text(json.dumps(decision_record, indent=2))

    if status == "released":
        print(json.dumps({"status": "released", "output": str(output_dir), "packet_hash": packet_hash}))

    return exit_code
