#!/usr/bin/env python3
"""
Validate corpus rights clearance status (Blocker 1).

Reads docs/survey/evidence/corpus_rights_manifest.json and reports which items
are cleared for external release and which still block it.

Exit codes:
  0 - all items cleared for external release
  1 - one or more items still pending clearance
  2 - manifest missing, unreadable, or schema-invalid

Usage:
    python tools/check_corpus_rights.py
    python tools/check_corpus_rights.py --json
    python tools/check_corpus_rights.py --scope internal
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "docs" / "survey" / "evidence" / "corpus_rights_manifest.json"
SCHEMA = REPO / "schemas" / "corpus-item.schema.json"

# A status in this set means the item may ship in an external release.
CLEARED_FOR_EXTERNAL = frozenset({
    "cleared-public",
})

# Internal evaluation is already authorized (G4 decision, Option A), so these
# statuses are acceptable for internal scope but not for external release.
CLEARED_FOR_INTERNAL = CLEARED_FOR_EXTERNAL | frozenset({
    "cleared-internal",
    "pending-clearance",
})


def load_manifest():
    if not MANIFEST.exists():
        return None, f"Manifest not found: {MANIFEST}"
    try:
        return json.loads(MANIFEST.read_text()), None
    except Exception as e:
        return None, f"Manifest unreadable: {e}"


def validate_items(manifest):
    """Validate each corpus item against its schema, if jsonschema is available."""
    errors = []
    if not SCHEMA.exists():
        return errors

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return errors

    try:
        schema = json.loads(SCHEMA.read_text())
    except Exception as e:
        return [f"corpus-item schema unreadable: {e}"]

    validator = Draft202012Validator(schema)
    for item in manifest.get("items", []):
        rid = item.get("record_id", "<no record_id>")
        for err in validator.iter_errors(item):
            errors.append(f"{rid}: {err.message}")
    return errors


def assess(manifest, scope):
    allowed = CLEARED_FOR_EXTERNAL if scope == "external" else CLEARED_FOR_INTERNAL

    cleared, blocking = [], []
    for item in manifest.get("items", []):
        status = item.get("redistribution_status")
        entry = {
            "record_id": item.get("record_id"),
            "source": item.get("source_path_or_url"),
            "owner": item.get("owner"),
            "redistribution_status": status,
            "consent_date": item.get("consent_date"),
            "source_hash": item.get("source_hash"),
        }

        # A cleared status still needs the supporting facts recorded: an item
        # marked cleared with no consent date and no real hash is not evidence
        # of clearance, it is an unfinished edit.
        if status in allowed and status != "pending-clearance":
            missing = []
            if not item.get("consent_date"):
                missing.append("consent_date")
            hash_val = item.get("source_hash") or ""
            if not hash_val or hash_val.startswith("pending"):
                missing.append("source_hash")
            if missing:
                entry["incomplete_fields"] = missing
                blocking.append(entry)
            else:
                cleared.append(entry)
        elif status in allowed:
            # pending-clearance under internal scope
            cleared.append(entry)
        else:
            blocking.append(entry)

    return cleared, blocking


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--scope",
        choices=["internal", "external"],
        default="external",
        help="Which release scope to check against (default: external)",
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    manifest, err = load_manifest()
    if err:
        print(f"Error: {err}", file=sys.stderr)
        return 2

    schema_errors = validate_items(manifest)
    cleared, blocking = assess(manifest, args.scope)
    total = len(manifest.get("items", []))

    report = {
        "manifest_id": manifest.get("manifest_id"),
        "manifest_status": manifest.get("status"),
        "scope": args.scope,
        "total_items": total,
        "cleared_count": len(cleared),
        "blocking_count": len(blocking),
        "cleared": cleared,
        "blocking": blocking,
        "schema_errors": schema_errors,
        "release_permitted": not blocking and not schema_errors,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Corpus rights: {manifest.get('manifest_id')}")
        print(f"Scope: {args.scope}")
        print(f"Items: {len(cleared)}/{total} cleared\n")

        if cleared:
            print("Cleared:")
            for c in cleared:
                print(f"  + {c['record_id']}: {c['redistribution_status']}")
            print()

        if blocking:
            print("Blocking:")
            for b in blocking:
                note = b.get("incomplete_fields")
                detail = (
                    f"marked cleared but missing {', '.join(note)}"
                    if note else b["redistribution_status"]
                )
                print(f"  - {b['record_id']}: {detail}")
                print(f"      owner: {b['owner']}")
            print()

        if schema_errors:
            print("Schema errors:")
            for e in schema_errors:
                print(f"  ! {e}")
            print()

        if report["release_permitted"]:
            print(f"Result: corpus may ship in an {args.scope} release.")
        else:
            print(
                f"Result: corpus may NOT ship in an {args.scope} release. "
                f"{len(blocking)} item(s) blocking."
            )
            if args.scope == "external":
                print("See docs/survey/rights_clearance/README.md for the process.")

    return 0 if report["release_permitted"] else 1


if __name__ == "__main__":
    sys.exit(main())
