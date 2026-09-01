#!/usr/bin/env python3
"""
Bounded repair with cycle tracking and oscillation detection.

Repairs style findings in drafts while preventing infinite loops through:
- Cycle limits (MAX_REPAIR_CYCLES)
- Finding signature tracking (detects repeated violations)
- Oscillation detection (detects alternating states)
- Content hash tracking
"""

import hashlib
import json
import re
import secrets
import shutil
from pathlib import Path
from typing import Any, Optional

MAX_REPAIR_CYCLES = 3


def _content_hash(text: str) -> str:
    """Compute SHA-256 hash of text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _finding_signature(findings: list[dict]) -> str:
    """
    Compute order-independent signature of findings list.

    Two finding lists with the same findings in different order produce
    the same signature.
    """
    if not findings:
        return _content_hash("[]")

    # Sort findings by a canonical representation
    canonical = sorted(
        json.dumps(f, sort_keys=True) for f in findings
    )
    return _content_hash("".join(canonical))


def _assign_finding_ids(findings: list[dict]) -> list[dict]:
    """
    Assign sequential finding IDs (F001, F002, ...) to findings.

    Preserves existing finding_id if present.
    """
    result = []
    counter = 1
    for finding in findings:
        if "finding_id" not in finding:
            finding = {**finding, "finding_id": f"F{counter:03d}"}
            counter += 1
        else:
            counter += 1
        result.append(finding)
    return result


def _load_revision_history(revisions_dir: Path) -> list[dict]:
    """
    Load revision history from revisions directory.

    Returns list of manifests sorted by cycle number.
    Ignores staging directories and unreadable manifests.
    """
    if not revisions_dir.exists():
        return []

    history = []
    for rev_dir in revisions_dir.iterdir():
        if not rev_dir.is_dir():
            continue
        if rev_dir.name.startswith(".staging-"):
            continue

        manifest_path = rev_dir / "revision_manifest.json"
        if not manifest_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text())
            history.append(manifest)
        except Exception:
            # Unreadable manifest counts as a consumed cycle
            history.append({
                "cycle": len(history) + 1,
                "revision_id": rev_dir.name,
                "content_hash": "unreadable",
                "finding_signature": "unreadable",
            })

    return sorted(history, key=lambda m: m.get("cycle", 0))


def _check_stop_conditions(history: list[dict], finding_signature: str) -> Optional[dict]:
    """
    Check pre-model stop conditions.

    Returns None if repair should proceed, or a stop reason dict if blocked.
    """
    # Check cycle limit
    if len(history) >= MAX_REPAIR_CYCLES:
        return {
            "stop_condition": "cycle_limit",
            "cycles_used": MAX_REPAIR_CYCLES,
            "author_choice": "Manual intervention required - exceeded max repair cycles",
        }

    # Check for repeated finding signature
    for entry in history:
        if entry.get("finding_signature") == finding_signature:
            return {
                "stop_condition": "repeated_finding_signature",
                "first_seen_cycle": entry.get("cycle", 0),
            }

    return None


def _check_oscillation(
    history: list[dict],
    parent_hash: str,
    revised_hash: str,
) -> Optional[dict]:
    """
    Check post-model oscillation conditions.

    Returns None if repair should proceed, or a stop reason dict if blocked.
    """
    # No-op repair: revision identical to parent
    if parent_hash == revised_hash:
        return {
            "stop_condition": "no_op_repair",
            "author_choice": "Repair produced no changes",
        }

    # Check if revised content returns to an earlier state
    for entry in history:
        if entry.get("content_hash") == revised_hash:
            return {
                "stop_condition": "alternating_parent_hashes",
                "seen_at_cycle": entry.get("cycle", 0),
            }

    return None


def _exempt_digits(findings: Optional[list[dict]]) -> set[str]:
    """
    Extract digits from matched_text in findings.

    Used to allow removal of digits that are part of offending labels
    (e.g., "WP2" contains "2" which should be exempt from numeric validation).
    """
    if not findings:
        return set()

    exempt = set()
    for finding in findings:
        matched = finding.get("location", {}).get("matched_text", "")
        for char in matched:
            if char.isdigit():
                exempt.add(char)

    return exempt


def _validate_revision(
    original: str,
    revised: str,
    brief: dict,
    findings: Optional[list[dict]] = None,
) -> list[str]:
    """
    Validate that revision preserves protected content.

    Returns list of validation failures (empty if valid).
    """
    failures = []

    # Empty revision
    if not revised.strip():
        return ["revision is empty"]

    # Extract protected objects from brief
    protected_objects = brief.get("protected_objects", [])

    # Check for dropped citations
    original_citations = set(re.findall(r'\\cite\{[^}]+\}', original))
    revised_citations = set(re.findall(r'\\cite\{[^}]+\}', revised))
    dropped_citations = original_citations - revised_citations
    if dropped_citations:
        failures.append(f"dropped citation: {', '.join(sorted(dropped_citations))}")

    # Check for dropped protected objects
    for obj in protected_objects:
        if obj in original and obj not in revised:
            failures.append(f"removed protected object: {obj}")

    # Check for dropped or altered numeric values
    exempt = _exempt_digits(findings)

    # Extract numbers from both texts
    original_numbers = re.findall(r'\d[\d,\\.\\{\\}]*\d|\d', original)
    revised_numbers = re.findall(r'\d[\d,\\.\\{\\}]*\d|\d', revised)

    # Normalize numbers (remove LaTeX formatting)
    def normalize_number(n):
        return re.sub(r'[{},\\]', '', n)

    original_normalized = {normalize_number(n) for n in original_numbers}
    revised_normalized = {normalize_number(n) for n in revised_numbers}

    # Remove exempt single digits
    original_normalized = {n for n in original_normalized if len(n) > 1 or n not in exempt}
    revised_normalized = {n for n in revised_normalized if len(n) > 1 or n not in exempt}

    dropped_numbers = original_normalized - revised_normalized
    if dropped_numbers:
        for num in sorted(dropped_numbers):
            failures.append(f"dropped or altered numeric value: {num}")

    # Check for introduced first-person pronouns
    first_person = r'\b(we|us|our|I|me|my)\b'
    original_first_person = set(re.findall(first_person, original, re.IGNORECASE))
    revised_first_person = set(re.findall(first_person, revised, re.IGNORECASE))
    introduced_first_person = revised_first_person - original_first_person
    if introduced_first_person:
        failures.append(f"introduced first-person register: {', '.join(sorted(introduced_first_person))}")

    return failures


def _apply_changes(draft_text: str, changes: list[dict]) -> tuple[str, list[dict], list[dict]]:
    """
    Apply verbatim replacements to draft text.

    Returns (revised_text, applied_changes, refused_changes).

    Changes must contain 'original' and 'revised' fields.
    Original text must match exactly once in the draft.
    """
    revised = draft_text
    applied = []
    refused = []

    for change in changes:
        finding_id = change.get("finding_id", "unknown")
        original = change.get("original", "")
        replacement = change.get("revised", "")

        # Empty original
        if not original:
            refused.append({
                "finding_id": finding_id,
                "refusal": "empty original string",
            })
            continue

        # Count occurrences
        count = revised.count(original)

        if count == 0:
            refused.append({
                "finding_id": finding_id,
                "refusal": f"original text not found verbatim: {original[:50]}",
            })
        elif count > 1:
            refused.append({
                "finding_id": finding_id,
                "refusal": f"original text is ambiguous ({count} occurrences): {original[:50]}",
            })
        else:
            # Apply replacement
            revised = revised.replace(original, replacement, 1)
            applied.append(change)

    return revised, applied, refused


def _publish_revision(
    revisions_dir: Path,
    cycle: int,
    revised_text: str,
    manifest: dict,
    draft_filename: str,
) -> Path:
    """
    Atomically publish a revision to the revisions directory.

    Returns the path to the published revision directory.
    """
    revision_id = manifest["revision_id"]
    final_dir = revisions_dir / revision_id

    if final_dir.exists():
        raise ValueError(f"Revision {revision_id} already published at cycle {cycle}")

    # Create staging directory
    staging_dir = revisions_dir / f".staging-{revision_id}"
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Write revision files
        (staging_dir / draft_filename).write_text(revised_text)
        (staging_dir / "revision_manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )

        # Atomic rename
        staging_dir.rename(final_dir)

    finally:
        # Clean up staging if it still exists
        if staging_dir.exists():
            shutil.rmtree(staging_dir)

    return final_dir


def _clear_unresolved_marker(revisions_dir: Path, final_revision: Path) -> None:
    """
    Clear unresolved_author_choice marker after successful repair.

    Preserves the marker inside the final revision for audit purposes.
    """
    marker = revisions_dir / "unresolved_author_choice.json"
    if marker.exists():
        # Preserve for audit
        archive = final_revision / "superseded_author_choice.json"
        shutil.copy(marker, archive)
        marker.unlink()


def _resolve_parent_draft(base_draft: Path, revisions_dir: Path) -> tuple[Path, int]:
    """
    Resolve parent draft for next repair cycle.

    Returns (parent_path, next_cycle_number).
    """
    history = _load_revision_history(revisions_dir)

    if not history:
        # First cycle uses base draft
        return base_draft, 1

    # Find latest revision
    latest = max(history, key=lambda m: m.get("cycle", 0))
    cycle = latest.get("cycle", 0)
    revision_id = latest.get("revision_id")

    parent_path = revisions_dir / revision_id / base_draft.name

    return parent_path, cycle + 1


def run(args) -> int:
    """
    Run repair command.

    Args should have: draft, findings, brief, output_dir, mock attributes.

    Returns:
    - 0: repair succeeded
    - 1: repair blocked by validation
    - 2: repair abstained (stop condition)
    """
    draft_path = Path(args.draft)
    findings_path = Path(args.findings)
    brief_path = Path(args.brief)

    # Load inputs
    draft_text = draft_path.read_text()
    findings_data = json.loads(findings_path.read_text())
    findings = findings_data.get("findings", [])
    brief = json.loads(brief_path.read_text())

    # Assign finding IDs
    findings = _assign_finding_ids(findings)

    # Resolve parent and cycle
    revisions_dir = draft_path.parent / "revisions"
    parent_draft, cycle = _resolve_parent_draft(draft_path, revisions_dir)

    # Load history
    history = _load_revision_history(revisions_dir)

    # Check pre-model stop conditions
    finding_sig = _finding_signature(findings)
    stop = _check_stop_conditions(history, finding_sig)
    if stop:
        print(f"Repair stopped: {stop['stop_condition']}")
        return 2

    # For now, mock behavior: just validate the draft as-is
    # Real implementation would call model to generate repairs
    if args.mock or True:  # Always mock for now
        # Simulate: no changes made
        revised_text = draft_text
        parent_hash = _content_hash(draft_text)
        revised_hash = _content_hash(revised_text)

        # Check oscillation
        osc = _check_oscillation(history, parent_hash, revised_hash)
        if osc:
            print(f"Repair stopped: {osc['stop_condition']}")
            return 2

        # Validate
        failures = _validate_revision(draft_text, revised_text, brief, findings)
        if failures:
            print(f"Validation failed: {failures}")
            return 1

        print("Mock repair: no changes needed")
        return 0

