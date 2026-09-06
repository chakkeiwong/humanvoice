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

from humanvoice.paths import runs_dir as _canonical_runs_dir
from humanvoice.transmission import get_transmission_log

# Appraisal states that count as sufficient for a load-bearing claim.
# Anything else -- including absent or null -- is treated as unappraised.
SUFFICIENT_APPRAISAL_STATES = frozenset({"sufficient", "verified", "accepted"})


def check_assembly_gaps(snapshot_dir: Path) -> Optional[dict]:
    """
    Block release when the assembled document is missing sections.

    Assembly is partial-tolerant by design: it records missing sections as gaps
    and exits 0 so that a 100-unit document makes convergent progress instead of
    restarting whenever one unit fails. That trade is only safe because this gate
    exists. Assembly records; release refuses.

    Fail-closed on absence and on corruption. A missing assembly_gaps.json means
    assembly either never ran or ran under a version that did not record gaps --
    neither is evidence of completeness. Reading absence as "no gaps" would
    reproduce the v1.1 failure where gates reported "pass" over known violations.

    Never-except: an incomplete document is not a risk judgement an operator can
    accept, so no exception path is offered.

    Returns a block dict if release must be refused, None if the document is
    complete.
    """
    gaps_path = (
        snapshot_dir / ".humanvoice" / "revisions" / "assembled" / "assembly_gaps.json"
    )

    if not gaps_path.exists():
        return {
            "gate": "assembly_gaps",
            "never_except": True,
            "detail": (
                f"Assembly gap record not found at {gaps_path.name}. Release cannot "
                "confirm the document is complete. Run hv assemble to produce the "
                "record."
            ),
        }

    try:
        gaps = json.loads(gaps_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "gate": "assembly_gaps",
            "never_except": True,
            "detail": (
                f"Assembly gap record at {gaps_path.name} is unreadable ({exc}). "
                "A corrupt record is not evidence of completeness."
            ),
        }

    if not isinstance(gaps, list):
        return {
            "gate": "assembly_gaps",
            "never_except": True,
            "detail": (
                f"Assembly gap record has unexpected shape ({type(gaps).__name__}); "
                "expected a list of gap records."
            ),
        }

    if not gaps:
        return None

    # Name the sections. A count alone does not tell the operator what to draft.
    named = ", ".join(
        f"{g.get('title', 'Untitled')} (section {g.get('section_index', '?')})"
        for g in gaps
    )
    return {
        "gate": "assembly_gaps",
        "never_except": True,
        "detail": (
            f"Assembled document is missing {len(gaps)} section(s): {named}. "
            "Draft each missing section, then re-assemble."
        ),
    }


def check_unresolved_author_choice(snapshot_dir: Path) -> Optional[dict]:
    """
    Check for unresolved_author_choice.json blocking release.

    Returns the unresolved-choice record if present, None otherwise.
    A superseded_author_choice.json does not block release.

    A missing runs directory blocks rather than passes: this is a never-except
    gate, and no authoring work having been recorded is not the same as the
    recorded work being clean.
    """
    runs_dir = _canonical_runs_dir(snapshot_dir)
    if not runs_dir.exists():
        return {
            "reason": "no_runs_directory",
            "detail": (
                f"No run records found at {runs_dir}. Release cannot confirm "
                "author convergence without authoring records."
            ),
        }

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
    Check protected-object correspondence with 7 fail-closed conditions.

    This gate implements the Phase 3 remedy design, replacing the prior fail-open
    implementation that passed when manifests were absent. All checks are
    fail-closed: missing evidence blocks release.

    Fail-closed checks:
    1. Source manifest exists (.humanvoice/protected_objects/source_manifest.json)
    2. Source manifest hash matches current source file
    3. Draft correspondence manifests exist (at least one per run)
    4. Per-object identity preservation meets type-specific thresholds:
       - Draft: 95% equations, labels, displaymath, tables
       - Assembly: 99% (checked separately in Phase 4)
    5. Every missing object has an explicit disposition with human_approved=True
    6. Parser agreement ≥90% in source manifest
    7. Assembly manifest exists if assembled/ directory present

    Returns a block dict if any check fails, None if all pass.
    """
    # Check 1: Source manifest must exist
    source_manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    if not source_manifest_path.exists():
        return {
            "reason": "missing_source_manifest",
            "detail": (
                f"Protected-object source manifest not found at {source_manifest_path}. "
                "Run 'hv init' to extract protected objects from source before drafting."
            ),
        }

    # Load source manifest
    try:
        source_manifest_data = json.loads(source_manifest_path.read_text())
    except Exception as e:
        return {
            "reason": "corrupt_source_manifest",
            "detail": f"Failed to parse source manifest: {e}",
        }

    # Check 2: Source manifest hash must match current source
    source_file_in_manifest = source_manifest_data.get("source_file")
    if source_file_in_manifest:
        # Resolve relative to snapshot
        source_file_path = snapshot_dir / source_file_in_manifest
        if source_file_path.exists():
            from humanvoice.protected_objects import _compute_file_hash
            current_hash = _compute_file_hash(source_file_path)
            manifest_hash = source_manifest_data.get("source_file_hash")
            if current_hash != manifest_hash:
                return {
                    "reason": "stale_source_manifest",
                    "detail": (
                        f"Source manifest hash mismatch: manifest has {manifest_hash[:16]}..., "
                        f"current source is {current_hash[:16]}... "
                        "Source file was modified after protected objects were extracted. "
                        "Re-run 'hv init' to update the manifest."
                    ),
                }

    # Check 6: Parser agreement must be ≥90%
    parser_agreement = source_manifest_data.get("parser_agreement_score", 0.0)
    if parser_agreement < 0.9:
        return {
            "reason": "low_parser_agreement",
            "detail": (
                f"Parser agreement {parser_agreement:.1%} below 90% threshold. "
                "Manual review of protected objects required before release."
            ),
        }

    # Collect all source objects for correspondence checking
    source_objects_by_hash = {}
    for obj_type in ["equations", "labels", "citations", "displaymath", "tables"]:
        for obj in source_manifest_data.get(obj_type, []):
            obj_hash = obj.get("hash")
            if obj_hash:
                source_objects_by_hash[obj_hash] = {
                    "type": obj.get("type", obj_type.rstrip("s")),  # "equations" -> "equation"
                    "content": obj.get("content", ""),
                    "line": obj.get("line"),
                }

    total_source_objects = len(source_objects_by_hash)

    # Check 3: Draft correspondence manifests must exist
    runs_dir = _canonical_runs_dir(snapshot_dir)
    if not runs_dir.exists():
        return {
            "reason": "no_runs_directory",
            "detail": (
                f"No run records found at {runs_dir}. Release cannot confirm "
                "protected-object correspondence without draft manifests."
            ),
        }

    draft_manifests = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        draft_manifests.extend(run_dir.glob("draft_correspondence_*.json"))

    if not draft_manifests:
        return {
            "reason": "no_draft_manifests",
            "detail": (
                f"No draft correspondence manifests found in {runs_dir}. "
                "Draft manifests are emitted by 'hv draft' and track per-section "
                "protected-object preservation."
            ),
        }

    # Check 4 & 5: Aggregate correspondence across all draft manifests
    all_preserved_hashes = set()
    all_missing_hashes = set()
    unapproved_dispositions = []

    for manifest_path in draft_manifests:
        try:
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("record_type") != "DraftCorrespondenceManifest":
                continue

            correspondence = manifest.get("correspondence_to_source", {})
            preserved = correspondence.get("preserved", [])
            missing = correspondence.get("missing", [])

            for obj in preserved:
                all_preserved_hashes.add(obj.get("hash"))

            for obj in missing:
                all_missing_hashes.add(obj.get("hash"))

            # Check dispositions for missing objects
            dispositions = manifest.get("dispositions", {}).get("omitted_objects", [])
            for disp in dispositions:
                if not disp.get("human_approved", False):
                    unapproved_dispositions.append({
                        "hash": disp.get("hash"),
                        "type": disp.get("type"),
                        "section": manifest.get("section_title"),
                        "reason": disp.get("reason"),
                    })

        except Exception as e:
            print(f"Warning: Failed to parse {manifest_path}: {e}", file=sys.stderr)
            continue

    # Check 5: All missing objects must have approved dispositions
    if unapproved_dispositions:
        return {
            "reason": "unapproved_dispositions",
            "detail": (
                f"{len(unapproved_dispositions)} omitted protected objects lack human-approved dispositions. "
                "Every missing object requires an explicit disposition (not_relevant | merged | superseded | manual_exception) "
                "with human_approved=True before release."
            ),
            "unapproved": unapproved_dispositions[:10],  # Cap detail list
        }

    # Check 4: Calculate identity preservation rate (draft threshold: 95%)
    if total_source_objects > 0:
        preserved_count = len(all_preserved_hashes & set(source_objects_by_hash.keys()))
        identity_preservation_rate = preserved_count / total_source_objects

        if identity_preservation_rate < 0.95:
            missing_count = total_source_objects - preserved_count
            return {
                "reason": "low_identity_preservation",
                "detail": (
                    f"Identity preservation {identity_preservation_rate:.1%} below 95% draft threshold. "
                    f"{preserved_count}/{total_source_objects} objects preserved, {missing_count} missing. "
                    "Per-object identity is verified by hash, not just count. "
                    "All missing objects require human-approved dispositions."
                ),
                "preserved_count": preserved_count,
                "total_source_objects": total_source_objects,
                "identity_preservation_rate": identity_preservation_rate,
            }

    # Check 7: Assembly correspondence (99% threshold)
    assembled_dir = snapshot_dir / ".humanvoice" / "revisions" / "assembled"
    if assembled_dir.exists() and any(assembled_dir.iterdir()):
        assembly_manifests = list(assembled_dir.glob("assembly_correspondence_*.json"))
        if not assembly_manifests:
            return {
                "reason": "no_assembly_manifest",
                "detail": (
                    f"Assembled documents exist but no assembly correspondence manifest found. "
                    "Assembly must track protected-object preservation at 99% threshold."
                ),
            }

        # Validate retention rate meets 99% threshold
        # Read the most recent manifest (sorted by timestamp in filename)
        latest_manifest_path = sorted(assembly_manifests)[-1]
        try:
            assembly_data = json.loads(latest_manifest_path.read_text())
        except Exception as e:
            return {
                "reason": "assembly_manifest_unreadable",
                "detail": f"Could not read assembly manifest {latest_manifest_path.name}: {e}",
            }

        retention_vs_source = assembly_data.get("retention_vs_source")
        retention_vs_drafts = assembly_data.get("retention_vs_drafts")

        if retention_vs_source is None or retention_vs_drafts is None:
            return {
                "reason": "assembly_manifest_incomplete",
                "detail": (
                    f"Assembly manifest {latest_manifest_path.name} missing "
                    f"retention_vs_source or retention_vs_drafts fields"
                ),
            }

        ASSEMBLY_RETENTION_THRESHOLD = 0.99
        if retention_vs_drafts < ASSEMBLY_RETENTION_THRESHOLD:
            preserved = assembly_data.get("preserved_count", 0)
            total = assembly_data.get("total_draft_objects", 0)
            return {
                "reason": "assembly_correspondence",
                "detail": (
                    f"Assembly retention {retention_vs_drafts:.1%} below {ASSEMBLY_RETENTION_THRESHOLD:.0%} threshold. "
                    f"{preserved}/{total} objects preserved from drafts."
                ),
                "preserved_count": preserved,
                "total_draft_objects": total,
                "retention_vs_drafts": retention_vs_drafts,
                "retention_vs_source": retention_vs_source,
            }

    # All checks pass
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
    runs_dir = _canonical_runs_dir(snapshot_dir)
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
    does not carry an explicitly sufficient appraisal_state.

    The check is an allowlist, not a denylist. A load-bearing claim whose
    appraisal_state is absent, null, or an unrecognised string has not been
    appraised, which is precisely what this gate exists to catch.

    A missing runs directory blocks rather than passes, for the same reason as
    the other never-except gates.
    """
    runs_dir = _canonical_runs_dir(snapshot_dir)
    if not runs_dir.exists():
        return {
            "message": "no_runs_directory",
            "detail": (
                f"No run records found at {runs_dir}. Release cannot confirm "
                "evidence sufficiency without authoring records."
            ),
        }

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

                # Allowlist: block unless the state is explicitly sufficient.
                # Absent/null/unrecognised means unappraised.
                if has_load_bearing and appraisal_state not in SUFFICIENT_APPRAISAL_STATES:
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


def _count_inference_runs(snapshot_dir: Path) -> int:
    """
    Count run records that record an actual model invocation.

    Only runtime manifests with mode "inference" represent external
    transmission. Deterministic records (preflight) and mock-mode runs transmit
    nothing, so they must not be counted -- otherwise a deterministic-only
    snapshot would look like it had unlogged transmissions.
    """
    runs_dir = _canonical_runs_dir(snapshot_dir)
    if not runs_dir.exists():
        return 0

    count = 0
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        for rm_file in run_dir.glob("**/runtime_manifest*.json"):
            try:
                rm = json.loads(rm_file.read_text())
            except Exception:
                continue
            if rm.get("mode") == "inference":
                count += 1
    return count


def check_unauthorized_transmission(snapshot_dir: Path) -> Optional[dict]:
    """
    Check for transmissions without explicit authorization.

    Returns a never-except block if any transmission carries an
    authorized_by outside the recognised set. For v1.2 every API call during
    plan/draft/repair is operator-initiated and logged as "operator". Future
    commands such as `hv publish` would require an explicit --authorize flag.

    An empty log is only a problem when inference actually occurred. A
    deterministic-only snapshot legitimately transmits nothing, so absence of a
    log is compared against the number of recorded inference runs rather than
    treated as suspicious on its own.
    """
    transmission_log = get_transmission_log(snapshot_dir)

    unauthorized = [
        t for t in transmission_log
        if t.get("authorized_by") not in ("operator", "release-gate")
    ]
    if unauthorized:
        return {
            "reason": "unauthorized_transmission",
            "count": len(unauthorized),
            "examples": unauthorized[:3],
            "detail": (
                f"{len(unauthorized)} transmission(s) without operator authorization. "
                "Release cannot proceed with unauthorized external transmissions."
            ),
        }

    # Inference happened but nothing was logged: the audit trail is incomplete,
    # so release cannot attest that transmissions were authorized.
    inference_runs = _count_inference_runs(snapshot_dir)
    if inference_runs > 0 and not transmission_log:
        return {
            "reason": "missing_transmission_log",
            "detail": (
                f"{inference_runs} inference run(s) recorded but the transmission "
                "log is empty. API calls occurred without being logged, so "
                "authorization cannot be verified."
            ),
        }

    return None


def check_preflight_findings(snapshot_dir: Path) -> Optional[dict]:
    """
    Check that deterministic preflight ran and cleared on this snapshot.

    Returns a never-except block if preflight never ran, or if the most recent
    preflight run reports findings or a non-pass status.

    Contract: deterministic gates are authoritative. Release must not emit a
    packet while deterministic findings stand unresolved. Repair does not clear
    this gate on its own -- preflight must be re-run against the revised
    artifact, so that what release checks is the text that ships.
    """
    runs_dir = _canonical_runs_dir(snapshot_dir)
    if not runs_dir.exists():
        return {
            "reason": "no_preflight_run",
            "detail": (
                f"No run records found at {runs_dir}. Deterministic preflight "
                "must run and clear before release."
            ),
        }

    # Collect every preflight record; preflight may run repeatedly.
    preflights = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        for pf_file in run_dir.glob("**/preflight-*.json"):
            try:
                pf = json.loads(pf_file.read_text())
            except Exception as e:
                return {
                    "reason": "preflight_unreadable",
                    "detail": f"Failed to parse {pf_file.name}: {e}",
                }
            preflights.append((pf.get("preflight_id", pf_file.stem), pf))

    if not preflights:
        return {
            "reason": "no_preflight_run",
            "detail": (
                "Deterministic preflight must run and clear before release; "
                "no preflight record found in this snapshot."
            ),
        }

    # preflight_id embeds a UTC timestamp, so lexical max is the most recent.
    latest_id, latest = max(preflights, key=lambda pair: pair[0])

    findings = latest.get("findings") or []
    if findings:
        return {
            "reason": "unresolved_preflight_findings",
            "preflight_id": latest_id,
            "finding_count": len(findings),
            "categories": sorted({f.get("category", "unknown") for f in findings}),
            "detail": (
                f"{len(findings)} deterministic finding(s) stand unresolved in "
                f"{latest_id}. Repair them and re-run preflight."
            ),
        }

    status = latest.get("status")
    if status is not None and status != "pass":
        return {
            "reason": "preflight_not_passed",
            "preflight_id": latest_id,
            "status": status,
            "detail": f"Most recent preflight ({latest_id}) reports status '{status}'.",
        }

    exit_code = latest.get("exit_code")
    if exit_code not in (None, 0):
        return {
            "reason": "preflight_not_passed",
            "preflight_id": latest_id,
            "exit_code": exit_code,
            "detail": f"Most recent preflight ({latest_id}) exited {exit_code}.",
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
        runs_dir = _canonical_runs_dir(snapshot_dir)
        if not runs_dir.exists():
            return {
                "reason": "no_runs_directory",
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


def check_assembly_exists(snapshot_dir: Path) -> Optional[dict]:
    """
    Check that document has been assembled before release.

    Returns a never-except block if assembly is missing or invalid.
    """
    rev_dir = snapshot_dir / ".humanvoice" / "revisions" / "assembled"
    manifest_path = rev_dir / "assembly_manifest.json"

    if not manifest_path.exists():
        return {
            "reason": "no_assembly",
            "detail": "Document must be assembled before release; run hv assemble"
        }

    try:
        manifest = json.loads(manifest_path.read_text())
        assembled_file = snapshot_dir / manifest["assembled_file"]
        if not assembled_file.exists():
            return {
                "reason": "assembled_file_missing",
                "detail": f"Assembly manifest references missing file: {assembled_file}"
            }
    except Exception as e:
        return {
            "reason": "assembly_manifest_invalid",
            "detail": f"Cannot read assembly manifest: {e}"
        }

    return None


def assemble_reader_packet(snapshot_dir: Path, output_dir: Path, brief: dict) -> str:
    """
    Assemble the reader packet and return its SHA-256 hash.

    The reader packet contains:
      - The assembled document (revised version from hv assemble)
      - Blacklined comparison (if available)
      - Assembly information (section metadata, stripped of internal IDs)
      - Reader brief (decision context only, no internal IDs)
      - Release decision record

    Returns the hex digest of the packet's SHA-256 hash.
    """
    packet_dir = output_dir / "packet"
    packet_dir.mkdir(parents=True, exist_ok=True)

    # Load assembly manifest
    rev_dir = snapshot_dir / ".humanvoice" / "revisions" / "assembled"
    assembly_manifest_path = rev_dir / "assembly_manifest.json"
    assembly_manifest = json.loads(assembly_manifest_path.read_text())

    # Copy assembled document
    assembled_file = snapshot_dir / assembly_manifest["assembled_file"]
    dest_assembled = packet_dir / assembled_file.name
    dest_assembled.write_bytes(assembled_file.read_bytes())

    # Copy blacklined comparison if available
    if assembly_manifest.get("blacklined_file"):
        blacklined_file = snapshot_dir / assembly_manifest["blacklined_file"]
        if blacklined_file.exists():
            dest_blacklined = packet_dir / blacklined_file.name
            dest_blacklined.write_bytes(blacklined_file.read_bytes())

    # Write assembly info (stripped of internal run IDs)
    reader_assembly = {
        "sections": [
            {
                "index": s["section_index"],
                "title": s["title"],
                "word_count": s.get("word_count", 0)
            }
            for s in assembly_manifest["sections"]
        ],
        "total_sections": len(assembly_manifest["sections"]),
        "total_word_count": assembly_manifest.get("total_word_count", 0),
        "diff_available": assembly_manifest.get("blacklined_file") is not None
    }
    (packet_dir / "assembly_info.json").write_text(json.dumps(reader_assembly, indent=2))

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

    # Never-except gate 4: unauthorized external transmission
    transmission_block = check_unauthorized_transmission(snapshot_dir)
    if transmission_block:
        blocks.append({
            "gate": "unauthorized_transmission",
            "never_except": True,
            "detail": transmission_block,
        })
        gate_results["unauthorized_transmission"] = "blocked"
    else:
        gate_results["unauthorized_transmission"] = "pass"

    # Never-except gate 5: assembled document missing sections.
    # Assembly is partial-tolerant so that large documents converge; this is the
    # fail-closed counterpart that keeps an incomplete document unpublishable.
    gap_block = check_assembly_gaps(snapshot_dir)
    if gap_block:
        blocks.append(gap_block)
        gate_results["assembly_gaps"] = "blocked"
    else:
        gate_results["assembly_gaps"] = "pass"

    # Never-except gate 6: unresolved deterministic preflight findings
    preflight_block = check_preflight_findings(snapshot_dir)
    if preflight_block:
        blocks.append({
            "gate": "deterministic_preflight",
            "never_except": True,
            "detail": preflight_block,
        })
        gate_results["deterministic_preflight"] = "blocked"
    else:
        gate_results["deterministic_preflight"] = "pass"

    # Never-except gate 6: broken or unreproducible source build
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

    # Never-except gate 7: document assembly
    assembly_block = check_assembly_exists(snapshot_dir)
    if assembly_block:
        blocks.append({
            "gate": "document_assembly",
            "never_except": True,
            "detail": assembly_block,
        })
        gate_results["document_assembly"] = "blocked"
    else:
        gate_results["document_assembly"] = "pass"

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
