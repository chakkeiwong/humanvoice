"""Repair command: hash-targeted restoration of missing protected objects.

The repair command implements Phase 5 of the Gate 4 remedy: when assembly
correspondence falls below 99%, it identifies missing protected objects by
hash and attempts to restore them from source or drafts.

Workflow:
1. Read assembly correspondence manifest to identify missing objects
2. For each missing object:
   - Locate it in source manifest by hash
   - Extract content and context from source file
   - Propose restoration strategy (direct copy, section merge, etc.)
3. Generate repair instructions for manual or semi-automated application

Contract:
- Missing objects are identified by cryptographic hash (identity-preserving)
- Repair proposals include source line numbers for verification
- Human approval required before applying repairs to assembly
- Repairs preserve the correspondence chain (source → draft → assembly)
"""

import json
import sys
from pathlib import Path
from typing import Optional

from humanvoice.protected_objects import _compute_file_hash


def find_missing_objects(snapshot_dir: Path) -> dict:
    """
    Analyze assembly correspondence and identify missing protected objects.

    Returns a dict with:
    - missing_count: number of missing objects
    - missing_objects: list of {hash, type, content, source_line}
    - retention_vs_drafts: current retention rate
    - assembly_manifest_path: path to the manifest analyzed
    """
    assembled_dir = snapshot_dir / ".humanvoice" / "revisions" / "assembled"
    if not assembled_dir.exists():
        return {
            "error": "no_assembly",
            "detail": "No assembled directory found. Run 'hv assemble' first."
        }

    # Find latest assembly correspondence manifest
    assembly_manifests = list(assembled_dir.glob("assembly_correspondence_*.json"))
    if not assembly_manifests:
        return {
            "error": "no_manifest",
            "detail": "No assembly correspondence manifest found."
        }

    latest_manifest_path = sorted(assembly_manifests)[-1]
    try:
        assembly_data = json.loads(latest_manifest_path.read_text())
    except Exception as e:
        return {
            "error": "manifest_unreadable",
            "detail": f"Failed to read manifest: {e}"
        }

    retention_vs_drafts = assembly_data.get("retention_vs_drafts", 0.0)
    retention_vs_source = assembly_data.get("retention_vs_source", 0.0)

    correspondence = assembly_data.get("correspondence_to_source", {})
    missing_objects_raw = correspondence.get("missing", [])

    if not missing_objects_raw:
        return {
            "missing_count": 0,
            "retention_vs_drafts": retention_vs_drafts,
            "retention_vs_source": retention_vs_source,
            "detail": "No missing objects. Assembly correspondence is complete."
        }

    # Load source manifest to get content and location for each missing object
    source_manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    if not source_manifest_path.exists():
        return {
            "error": "no_source_manifest",
            "detail": "Source manifest not found. Cannot locate missing objects."
        }

    try:
        source_manifest = json.loads(source_manifest_path.read_text())
    except Exception as e:
        return {
            "error": "source_manifest_unreadable",
            "detail": f"Failed to read source manifest: {e}"
        }

    # Build hash lookup from source manifest
    source_objects_by_hash = {}
    for obj_type in ["equations", "labels", "citations", "displaymath", "tables"]:
        for obj in source_manifest.get(obj_type, []):
            obj_hash = obj.get("hash")
            if obj_hash:
                source_objects_by_hash[obj_hash] = {
                    "type": obj_type.rstrip("s"),  # "equations" -> "equation"
                    "content": obj.get("content", ""),
                    "line": obj.get("line"),
                    "id": obj.get("id"),
                }

    # Enrich missing objects with source details
    missing_objects_enriched = []
    for missing_obj in missing_objects_raw:
        obj_hash = missing_obj.get("hash")
        if obj_hash and obj_hash in source_objects_by_hash:
            source_details = source_objects_by_hash[obj_hash]
            missing_objects_enriched.append({
                "hash": obj_hash,
                "type": source_details["type"],
                "content": source_details["content"],
                "source_line": source_details["line"],
                "id": source_details["id"],
            })
        else:
            # Object missing from source manifest (added in draft, then lost in assembly)
            missing_objects_enriched.append({
                "hash": obj_hash,
                "type": missing_obj.get("type", "unknown"),
                "content": missing_obj.get("content", ""),
                "source_line": None,
                "id": missing_obj.get("id", ""),
                "note": "Not found in source manifest (may be draft-added object)"
            })

    return {
        "missing_count": len(missing_objects_enriched),
        "missing_objects": missing_objects_enriched,
        "retention_vs_drafts": retention_vs_drafts,
        "retention_vs_source": retention_vs_source,
        "assembly_manifest_path": str(latest_manifest_path),
    }


def propose_repairs(snapshot_dir: Path, missing_objects: list) -> list:
    """
    Generate repair proposals for missing protected objects.

    Each proposal includes:
    - object_hash: identity of the missing object
    - strategy: restoration strategy (copy_from_source, copy_from_draft, manual_review)
    - source_file: file containing the object
    - source_line: line number in source
    - content: the missing content
    - context: surrounding text for verification
    """
    source_manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    if not source_manifest_path.exists():
        return []

    try:
        source_manifest = json.loads(source_manifest_path.read_text())
    except Exception:
        return []

    source_file_path = snapshot_dir / source_manifest.get("source_file", "")
    if not source_file_path.exists():
        return []

    # Read source file for context extraction
    try:
        source_lines = source_file_path.read_text().splitlines()
    except Exception:
        source_lines = []

    proposals = []
    for obj in missing_objects:
        obj_hash = obj.get("hash")
        obj_type = obj.get("type")
        content = obj.get("content")
        line = obj.get("source_line")

        if line is None or line < 1 or line > len(source_lines):
            # Object not in source or line out of bounds
            proposals.append({
                "object_hash": obj_hash,
                "strategy": "manual_review",
                "reason": "Source location not available",
                "content": content,
                "type": obj_type,
            })
            continue

        # Extract context (3 lines before and after)
        start_line = max(1, line - 3)
        end_line = min(len(source_lines), line + 3)
        context_lines = source_lines[start_line - 1:end_line]
        context = "\n".join(f"{start_line + i}: {line}" for i, line in enumerate(context_lines))

        proposals.append({
            "object_hash": obj_hash,
            "strategy": "copy_from_source",
            "source_file": str(source_file_path.relative_to(snapshot_dir)),
            "source_line": line,
            "content": content,
            "type": obj_type,
            "context": context,
        })

    return proposals


def run(args):
    """
    Run the repair command to identify and propose fixes for missing objects.

    Usage:
        hv repair <snapshot-dir>

    Output:
        JSON report with missing objects and repair proposals.
    """
    snapshot_dir = Path(args.snapshot_dir).resolve()
    if not snapshot_dir.exists():
        print(json.dumps({
            "error": "snapshot_not_found",
            "detail": f"Snapshot directory not found: {snapshot_dir}"
        }), file=sys.stderr)
        return 1

    # Find missing objects
    analysis = find_missing_objects(snapshot_dir)

    if "error" in analysis:
        print(json.dumps(analysis, indent=2), file=sys.stderr)
        return 1

    missing_count = analysis.get("missing_count", 0)
    if missing_count == 0:
        print(json.dumps(analysis, indent=2))
        return 0

    # Generate repair proposals
    missing_objects = analysis.get("missing_objects", [])
    proposals = propose_repairs(snapshot_dir, missing_objects)

    # Output repair report
    report = {
        "status": "repairs_needed",
        "missing_count": missing_count,
        "retention_vs_drafts": analysis.get("retention_vs_drafts"),
        "retention_vs_source": analysis.get("retention_vs_source"),
        "assembly_manifest": analysis.get("assembly_manifest_path"),
        "proposals": proposals,
    }

    print(json.dumps(report, indent=2))
    return 0
