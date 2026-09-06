#!/usr/bin/env python3
"""
Run the machine fixture suite and check results against answer keys.

Per v1.1 program §7.1: every ready fixture is executed and its findings are
compared to the recorded answer key. Planned, unavailable, and not-applicable
rows remain in the denominator but are not executed.

Exit codes:
  0 - every ready fixture matched its answer key
  1 - at least one ready fixture disagreed with its answer key
  3 - manifest or answer key could not be read
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Minimal brief used for engineering fixtures. Register classification that
# depends on project vocabulary is exercised separately.
ENGINEERING_BRIEF = {
    "reader_role": "engineering reviewer",
    "decision_type": "accept or reject a parser result",
    "time_available_minutes": 15,
    "prior_knowledge": "LaTeX, source maps, protected objects",
    "success_criteria": "protected objects are located and typed correctly",
}


def _load_manifest() -> dict:
    return json.loads((ROOT / "fixtures/manifest.json").read_text(encoding="utf-8"))


def _sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def _check_object_expectations(
    answer_key: dict, preflight: dict
) -> tuple[bool, list[str]]:
    """Compare parser output against an object-level answer key."""
    problems: list[str] = []
    protected = preflight.get("protected_objects", {})
    actual_count = protected.get("count", 0)
    actual_types = protected.get("types", {})

    minimum = answer_key.get("minimum_object_count")
    if minimum is not None and actual_count < minimum:
        problems.append(
            f"expected at least {minimum} protected objects, parser reported {actual_count}"
        )

    expected_types: dict[str, int] = {}
    for expected in answer_key.get("expected_objects", []):
        object_type = expected.get("object_type")
        if object_type:
            expected_types[object_type] = expected_types.get(object_type, 0) + 1

    for object_type, expected_n in expected_types.items():
        found_n = actual_types.get(object_type, 0)
        if found_n < expected_n:
            problems.append(
                f"expected {expected_n} {object_type} object(s), parser reported {found_n}"
            )

    return not problems, problems


def _check_finding_expectations(
    answer_key: dict, preflight: dict
) -> tuple[bool, list[str]]:
    """Compare findings against a finding-level answer key (register fixtures)."""
    problems: list[str] = []
    found_terms: list[str] = []
    for finding in preflight.get("findings", []):
        found_terms.extend(finding.get("source_terms", []))

    for expected in answer_key.get("expected_findings", []):
        for term in expected.get("source_terms", []):
            if term not in found_terms:
                problems.append(f"expected finding term not located: {term}")

    return not problems, problems


def _run_fixture(row: dict) -> dict:
    """Run hv init + hv preflight for one ready fixture."""
    fixture_id = row["id"]
    source = ROOT / row["source_path"]
    answer_key_path = ROOT / row["answer_key_path"]

    if not source.is_file():
        return {"fixture": fixture_id, "status": "error", "problems": ["source missing"]}
    if not answer_key_path.is_file():
        return {
            "fixture": fixture_id,
            "status": "error",
            "problems": ["answer key missing"],
        }

    if _sha256_bytes(source.read_bytes()) != row["source_hash"]:
        return {
            "fixture": fixture_id,
            "status": "error",
            "problems": ["source hash does not match the manifest"],
        }
    if _sha256_bytes(answer_key_path.read_bytes()) != row["answer_key_hash"]:
        return {
            "fixture": fixture_id,
            "status": "error",
            "problems": ["answer key hash does not match the manifest"],
        }

    answer_key = json.loads(answer_key_path.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix=f"hv-fixture-{fixture_id}-") as tmpdir:
        work = Path(tmpdir)
        brief_path = work / "brief.json"
        brief_path.write_text(json.dumps(ENGINEERING_BRIEF), encoding="utf-8")
        snapshot = work / "snapshot"

        init = subprocess.run(
            [
                "hv",
                "init",
                str(source),
                "--brief",
                str(brief_path),
                "--output",
                str(snapshot),
            ],
            capture_output=True,
            text=True,
        )
        if init.returncode != 0:
            return {
                "fixture": fixture_id,
                "status": "error",
                "problems": [f"hv init exited {init.returncode}: {init.stderr.strip()}"],
            }

        preflight_proc = subprocess.run(
            [
                "hv",
                "preflight",
                str(snapshot),
                "--brief",
                str(brief_path),
                "--deterministic",
            ],
            capture_output=True,
            text=True,
        )

        try:
            preflight = json.loads(preflight_proc.stdout)
        except json.JSONDecodeError:
            return {
                "fixture": fixture_id,
                "status": "error",
                "problems": ["hv preflight did not emit JSON on stdout"],
            }

    # Object-level answer keys carry expected_objects; register keys carry
    # expected_findings. Check whichever the key declares.
    problems: list[str] = []
    if "expected_objects" in answer_key or "minimum_object_count" in answer_key:
        ok, object_problems = _check_object_expectations(answer_key, preflight)
        problems.extend(object_problems)
    if "expected_findings" in answer_key:
        ok, finding_problems = _check_finding_expectations(answer_key, preflight)
        problems.extend(finding_problems)

    return {
        "fixture": fixture_id,
        "status": "match" if not problems else "mismatch",
        "exit_code": preflight.get("exit_code"),
        "object_count": preflight.get("protected_objects", {}).get("count", 0),
        "problems": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the machine record instead of the human summary",
    )
    args = parser.parse_args()

    try:
        manifest = _load_manifest()
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL cannot read fixture manifest: {error}", file=sys.stderr)
        return 3

    rows = manifest.get("fixtures", [])
    ready = [row for row in rows if row.get("lifecycle") == "ready"]
    results = [_run_fixture(row) for row in ready]

    record = {
        "fixture_manifest_id": manifest.get("fixture_manifest_id"),
        "total_rows": len(rows),
        "ready_rows": len(ready),
        "executed": len(results),
        "matched": sum(1 for r in results if r["status"] == "match"),
        "mismatched": sum(1 for r in results if r["status"] == "mismatch"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }

    if args.json:
        print(json.dumps(record, indent=2))
    else:
        for result in results:
            marker = {"match": "PASS", "mismatch": "FAIL", "error": "FAIL"}[
                result["status"]
            ]
            detail = f" objects={result.get('object_count')}"
            print(f"{marker} {result['fixture']}{detail}")
            for problem in result["problems"]:
                print(f"     {problem}")
        print(
            "INFO fixture_suite "
            f"ready={record['ready_rows']} matched={record['matched']} "
            f"mismatched={record['mismatched']} errors={record['errors']} "
            f"not_executed={record['total_rows'] - record['ready_rows']}"
        )

    return 0 if record["mismatched"] == 0 and record["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
