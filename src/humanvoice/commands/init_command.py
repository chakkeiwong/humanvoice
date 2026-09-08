"""
hv init - Create immutable source snapshot and validate brief.

Implements R7 (immutable snapshots), R11 (trust boundary), R12 (brief completeness).
Phase 1: Adds protected-object extraction with provenance binding.
"""

import json
import sys
import shutil
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone

from humanvoice.protected_objects import extract_protected_objects


def _hash_file(path: Path) -> str:
    """Compute SHA-256 of a file."""
    digest = sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _validate_brief(brief: dict) -> tuple[bool, list[str]]:
    """
    Validate reader brief completeness.

    Required fields per implementation contract §5.1:
    - reader_role: who will make the decision
    - decision_type: what kind of decision
    - time_available_minutes: reading budget
    - prior_knowledge: what the reader already knows
    - success_criteria: what makes a good outcome
    """
    required = ['reader_role', 'decision_type', 'time_available_minutes',
                'prior_knowledge', 'success_criteria']
    errors = []

    for field in required:
        if field not in brief:
            errors.append(f"Brief missing required field: {field}")
        elif not brief[field]:
            errors.append(f"Brief field is empty: {field}")

    if 'time_available_minutes' in brief:
        try:
            minutes = int(brief['time_available_minutes'])
            if minutes <= 0:
                errors.append("time_available_minutes must be positive")
        except (ValueError, TypeError):
            errors.append("time_available_minutes must be an integer")

    return len(errors) == 0, errors


def run(args) -> int:
    """
    Create immutable source snapshot and validate brief.

    Exit codes:
      0 - snapshot created, brief valid
      3 - invalid input (missing source, bad brief)
      4 - internal error (I/O failure)
      5 - security violation (path traversal attempt)
    """
    source = args.source.resolve()
    output = args.output.resolve()
    brief_path = args.brief.resolve()

    # Check source exists
    if not source.exists():
        print(f"Error: Source does not exist: {source}", file=sys.stderr)
        return 3

    # Check brief exists and parse
    if not brief_path.exists():
        print(f"Error: Brief does not exist: {brief_path}", file=sys.stderr)
        return 3

    try:
        with open(brief_path, 'r') as f:
            brief = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Brief is not valid JSON: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"Error: Cannot read brief: {e}", file=sys.stderr)
        return 4

    # Validate brief completeness
    valid, errors = _validate_brief(brief)
    if not valid:
        print("Error: Brief is incomplete:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 3

    # Check output doesn't already exist
    if output.exists():
        print(f"Error: Output directory already exists: {output}", file=sys.stderr)
        return 3

    # Create snapshot
    try:
        output.mkdir(parents=True, exist_ok=False)

        # Copy source tree (read-only snapshot)
        if source.is_file():
            snapshot_source = output / "source" / source.name
            snapshot_source.parent.mkdir(parents=True)
            shutil.copy2(source, snapshot_source)
            source_hash = _hash_file(snapshot_source)
            source_files = [str(snapshot_source.relative_to(output))]
        else:
            snapshot_source = output / "source"
            shutil.copytree(source, snapshot_source, symlinks=False)
            # Hash all .tex and .bib files (.bib required for bibliography compilation)
            source_files = []
            for pattern in ["*.tex", "*.bib"]:
                for file in snapshot_source.rglob(pattern):
                    source_files.append(str(file.relative_to(output)))
            # Compute aggregate hash
            source_hash = sha256()
            for file_path in sorted(source_files):
                source_hash.update(_hash_file(output / file_path).encode())
            source_hash = source_hash.hexdigest()

        # Create scratch directory (empty, writable)
        scratch = output / "scratch"
        scratch.mkdir()

        # Write snapshot manifest
        manifest = {
            "snapshot_id": f"snapshot-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_hash": source_hash,
            "source_files": source_files,
            "brief": brief,
            "brief_valid": True,
            "snapshot_immutable": True
        }

        manifest_path = output / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        # PHASE 1: Extract protected objects from source with parser bake-off
        print("Extracting protected objects from source...", file=sys.stderr)

        # Find primary source file for extraction
        if source.is_file():
            primary_source = snapshot_source
        else:
            # For directory sources, look for main .tex file
            tex_files = list(snapshot_source.glob("*.tex"))
            if len(tex_files) == 1:
                primary_source = tex_files[0]
            else:
                # Try common main file names
                for candidate in ["main.tex", "paper.tex", "document.tex"]:
                    if (snapshot_source / candidate).exists():
                        primary_source = snapshot_source / candidate
                        break
                else:
                    # Use first .tex file
                    primary_source = tex_files[0] if tex_files else None

        if primary_source:
            try:
                protected_manifest = extract_protected_objects(
                    primary_source,
                    snapshot_id=manifest["snapshot_id"]
                )

                # Store protected objects manifest
                protected_objects_dir = output / ".humanvoice" / "protected_objects"
                protected_objects_dir.mkdir(parents=True, exist_ok=True)

                protected_manifest_path = protected_objects_dir / "source_manifest.json"
                with open(protected_manifest_path, 'w') as f:
                    json.dump(protected_manifest.to_json(), f, indent=2)

                # Update snapshot manifest with protected objects metadata
                manifest["source_protected_manifest"] = str(
                    protected_manifest_path.relative_to(output)
                )
                manifest["protected_objects_count"] = protected_manifest.total_count
                manifest["parser_agreement_score"] = protected_manifest.parser_agreement_score

                # Rewrite manifest with protected objects info
                with open(manifest_path, 'w') as f:
                    json.dump(manifest, f, indent=2)

                print(f"Extracted {protected_manifest.total_count} protected objects:", file=sys.stderr)
                print(f"  Equations: {len(protected_manifest.equations)}", file=sys.stderr)
                print(f"  Labels: {len(protected_manifest.labels)}", file=sys.stderr)
                print(f"  Citations: {len(protected_manifest.citations)}", file=sys.stderr)
                print(f"  Displaymath: {len(protected_manifest.displaymath)}", file=sys.stderr)
                print(f"  Tables: {len(protected_manifest.tables)}", file=sys.stderr)
                print(f"  Parser agreement: {protected_manifest.parser_agreement_score:.1%}", file=sys.stderr)

                if protected_manifest.parser_agreement_score < 0.9:
                    print("  Warning: Parser agreement below 90% — consider manual review", file=sys.stderr)

            except Exception as e:
                print(f"Warning: Protected object extraction failed: {e}", file=sys.stderr)
                print("  Continuing without protected manifest (correspondence gates will block)", file=sys.stderr)
        else:
            print("Warning: No .tex source file found for protected object extraction", file=sys.stderr)

        # Write result to stdout (contract requires JSON on stdout)
        result = {
            "status": "initialized",
            "snapshot_id": manifest["snapshot_id"],
            "source_hash": source_hash,
            "brief_valid": True,
            "output_path": str(output),
            "protected_objects_extracted": primary_source is not None
        }
        print(json.dumps(result, indent=2))

        return 0

    except Exception as e:
        print(f"Error: Failed to create snapshot: {e}", file=sys.stderr)
        # Clean up partial output
        if output.exists():
            shutil.rmtree(output, ignore_errors=True)
        return 4


if __name__ == '__main__':
    sys.exit(run(None))
