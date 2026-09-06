"""
hv preflight - Run independent critics and structural checks.

Deterministic mode (WP1/WP2): parser-backed structural checks, no model invocation.
Model-assisted mode (WP4): adds bounded authoring critics.

Implements R10 (register checking), R13 (JSON output), R15 (abstention).
WP2 adds: parser integration, protected-object extraction, source maps.
"""

import json
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
from humanvoice.parser import parse_latex
from humanvoice.paths import new_run_dir, mint_run_id


def _load_snapshot_manifest(snapshot_dir: Path) -> dict:
    """Load and validate snapshot manifest."""
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Snapshot manifest not found: {manifest_path}")

    with open(manifest_path, 'r') as f:
        manifest = json.load(f)

    if not manifest.get('snapshot_immutable'):
        raise ValueError("Snapshot is not marked immutable")

    return manifest


def _check_register_violations(source_text: str, brief: dict) -> list[dict]:
    """
    Check for private workflow vocabulary in reader-facing text.

    This is the deterministic preflight check for fixture F-REGISTER-001.
    Detects:
    - Work package labels (WP0-WP6)
    - Private filesystem paths
    - Internal phase labels

    Returns findings with abstention when project vocabulary config is needed.
    """
    findings = []

    # Pattern 1: Work package labels (WP0-WP6)
    wp_pattern = r'\bWP[0-6]\b'
    wp_matches = list(re.finditer(wp_pattern, source_text))

    for match in wp_matches:
        findings.append({
            "category": "register",
            "severity": "deterministic_failure",
            "location": {
                "char_offset": match.start(),
                "matched_text": match.group()
            },
            "message": "Private workflow label found in reader-facing text",
            "reader_consequence": "Reader cannot act on internal phase labels",
            "source_terms": [match.group()]
        })

    # Pattern 2: Filesystem paths that look internal
    # Stop at LaTeX commands (backslash) or whitespace
    path_pattern = r'(?:/srv/|/home/|/var/|C:\\)[a-zA-Z0-9_/\\.-]+?(?=\s|\\|\{|\}|$)'
    path_matches = list(re.finditer(path_pattern, source_text))

    for match in path_matches:
        path = match.group()
        # Skip common public paths (like /usr/bin in examples)
        if path.startswith(('/srv/', '/home/', '/var/lib', '/var/log')):
            findings.append({
                "category": "register",
                "severity": "deterministic_failure",
                "location": {
                    "char_offset": match.start(),
                    "matched_text": path
                },
                "message": "Private filesystem path found in reader-facing text",
                "reader_consequence": "Reader cannot access internal paths",
                "source_terms": [path]
            })

    return findings


def _run_deterministic_preflight(snapshot_dir: Path, brief: dict) -> dict:
    """
    Run deterministic preflight checks (no model invocation).

    WP1: Register checking with regex patterns
    WP2: Parser-backed protected-object extraction
    """
    manifest = _load_snapshot_manifest(snapshot_dir)

    # Load all source text
    source_files = manifest.get('source_files', [])
    if not source_files:
        return {
            "status": "abstention",
            "reason": "No source files in snapshot",
            "exit_code": 2
        }

    full_text = []
    for rel_path in source_files:
        source_path = snapshot_dir / rel_path
        if source_path.exists():
            full_text.append(source_path.read_text())

    combined_text = '\n'.join(full_text)

    # WP2: Parse with pylatexenc adapter
    source_hash = manifest.get('source_hash')
    try:
        parse_result = parse_latex(combined_text, source_hash)
        parser_objects = parse_result.objects
        parser_abstentions = parse_result.abstentions
    except Exception as e:
        # Parser failure triggers abstention
        parse_result = None
        parser_objects = []
        parser_abstentions = [{
            'reason': 'parser_failure',
            'message': str(e),
            'construct': 'document'
        }]

    # WP1: Run register check (regex-based)
    findings = _check_register_violations(combined_text, brief)

    # Check if we need to abstain due to missing vocabulary configuration
    # Per F-REGISTER-001 answer key: abstain when project config is required
    ambiguous_terms = []
    if 'technical_terms' not in brief and 'project_vocabulary' not in brief:
        # Look for capitalized acronyms that might be domain-specific
        acronym_pattern = r'\b[A-Z]{2,}\b'
        acronyms = set(re.findall(acronym_pattern, combined_text))
        # Filter out common ones
        common = {'PDF', 'JSON', 'API', 'CLI', 'URL', 'HTTP', 'XML', 'CSV', 'SQL'}
        ambiguous_terms = list(acronyms - common - {f'WP{i}' for i in range(7)})

    # Prepare result
    result = {
        "preflight_id": f"preflight-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "mode": "deterministic",
        "snapshot_id": manifest.get('snapshot_id'),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "findings": findings,
        "deterministic_gate": "fail" if findings else "pass",
        "protected_objects": {
            "count": len(parser_objects),
            "types": {},
            "parser": parse_result.parser_name if parse_result else "none",
            "parse_time_seconds": parse_result.parse_time_seconds if parse_result else 0
        }
    }

    # Count object types
    if parser_objects:
        from collections import Counter
        type_counts = Counter(obj.object_type.value for obj in parser_objects)
        result["protected_objects"]["types"] = dict(type_counts)

        # Add sample objects to result (first 3 of each type)
        samples = {}
        for obj in parser_objects[:10]:  # Limit to first 10 overall
            obj_type = obj.object_type.value
            if obj_type not in samples:
                samples[obj_type] = []
            if len(samples[obj_type]) < 3:
                samples[obj_type].append({
                    'id': obj.object_id,
                    'location': obj.location.char_offset,
                    'length': obj.location.length,
                    'raw_preview': obj.raw_form[:60]
                })
        result["protected_objects"]["samples"] = samples

    # Add parser abstentions
    if parser_abstentions:
        result["parser_abstentions"] = parser_abstentions

    # Add abstention if vocabulary config is needed and ambiguous terms exist
    if ambiguous_terms and len(ambiguous_terms) > 3:
        result["abstention"] = {
            "reason": "Project vocabulary configuration required to classify ambiguous terms",
            "ambiguous_term_count": len(ambiguous_terms),
            "sample_terms": ambiguous_terms[:5]
        }
        result["status"] = "abstention"
        result["exit_code"] = 2
    elif findings:
        result["status"] = "gate_failure"
        result["exit_code"] = 1
    elif parser_abstentions:
        result["status"] = "abstention"
        result["exit_code"] = 2
    else:
        result["status"] = "pass"
        result["exit_code"] = 0

    return result


def run(args) -> int:
    """
    Run preflight checks on snapshot.

    Exit codes:
      0 - pass (no deterministic failures)
      1 - deterministic gate failure
      2 - abstention (missing configuration or policy)
      3 - invalid input (bad snapshot, missing brief)
      4 - internal error
    """
    snapshot_dir = args.snapshot.resolve()
    brief_path = args.brief.resolve()

    # Validate inputs
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        print(f"Error: Snapshot directory does not exist: {snapshot_dir}", file=sys.stderr)
        return 3

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

    # Run checks
    try:
        if args.deterministic:
            result = _run_deterministic_preflight(snapshot_dir, brief)
        else:
            # Model-assisted mode requires WP4
            print("Error: Model-assisted preflight requires WP4 (not implemented)", file=sys.stderr)
            return 3

        # Persist result under the snapshot so release can read it.
        # The preflight gate needs on-disk records, not just stdout.
        # An explicit run_id lets hv pipeline co-locate stage records.
        run_id = getattr(args, "run_id", None) or mint_run_id()
        output_dir = new_run_dir(snapshot_dir, run_id)
        preflight_file = output_dir / f"{result['preflight_id']}.json"
        preflight_file.write_text(json.dumps(result, indent=2))

        # Write result to stdout (per contract: JSON on stdout, diagnostics on stderr)
        print(json.dumps(result, indent=2))

        # Diagnostic summary to stderr
        if result.get('findings'):
            print(f"\nFound {len(result['findings'])} register violations", file=sys.stderr)
        if result.get('abstention'):
            print(f"\nAbstention: {result['abstention']['reason']}", file=sys.stderr)

        return result.get('exit_code', 0)

    except Exception as e:
        print(f"Error: Preflight check failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 4


if __name__ == '__main__':
    sys.exit(run(None))
