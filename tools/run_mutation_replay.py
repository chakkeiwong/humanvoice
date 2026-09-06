#!/usr/bin/env python3
"""
Seeded-mutation replay for the WP3 exit criterion.

The v1.1 program requires that seeded sign, exponent, unit, number, citation,
label, quotation, denominator, and claim-scope mutations are each either caught
(reported as a substantive change) or abstained (reported as unresolved). A
mutation that produces "unchanged" or "explained change" is a miss and fails
the gate: it means the comparator would let a meaning change through silently.

This runner mutates a ready fixture in memory, never on disk, and compares the
baseline parse against the mutated parse.

Exit codes:
  0 - every seeded mutation was caught or abstained
  1 - at least one mutation was missed
  3 - fixtures or manifest could not be read
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from humanvoice.compare import CorrespondenceStatus, compare_documents  # noqa: E402
from humanvoice.parser import parse_latex  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

# Outcomes that satisfy the gate. "unchanged" and "explained_change" do not:
# a seeded meaning change must never be classified as benign.
ACCEPTABLE = {
    CorrespondenceStatus.SUBSTANTIVE_CHANGE,
    CorrespondenceStatus.UNRESOLVED,
    CorrespondenceStatus.ADDED,
    CorrespondenceStatus.REMOVED,
}


@dataclass
class Mutation:
    """One seeded mutation: a literal substring replacement."""

    mutation_id: str
    kind: str
    fixture_id: str
    find: str
    replace: str
    rationale: str


# Each mutation targets a construct that exists in a ready fixture. The find
# string must be present in the fixture or the mutation is reported as an error
# rather than silently skipped.
MUTATIONS = [
    Mutation(
        "M-EXPONENT",
        "exponent",
        "F-EQUATION-001",
        "a^2 + b^2 = c^2",
        "a^3 + b^3 = c^3",
        "Changing an exponent changes the mathematical claim.",
    ),
    Mutation(
        "M-SIGN",
        "sign",
        "F-EQUATION-001",
        "a^2 + b^2 = c^2",
        "a^2 - b^2 = c^2",
        "Flipping an operator sign changes the relation.",
    ),
    Mutation(
        "M-INTEGRAL-BOUND",
        "number",
        "F-EQUATION-001",
        "\\int_{0}^{\\infty}",
        "\\int_{1}^{\\infty}",
        "Changing an integration bound changes the value.",
    ),
    Mutation(
        "M-LABEL",
        "label",
        "F-EQUATION-001",
        "\\label{eq:pythagorean}",
        "\\label{eq:pythagoras}",
        "Renaming a label breaks cross-reference identity.",
    ),
    Mutation(
        "M-CITATION-KEY",
        "citation",
        "F-CITATION-001",
        "\\cite{smith2020}",
        "\\cite{smith2021}",
        "Changing a cite key reattributes the claim.",
    ),
    Mutation(
        "M-CITATION-DROP",
        "citation",
        "F-CITATION-001",
        "\\citep{jones2021,brown2022}",
        "\\citep{jones2021}",
        "Dropping a cite key removes supporting evidence.",
    ),
    Mutation(
        "M-DENOMINATOR",
        "denominator",
        "F-TABLE-001",
        "Baseline & 0.85 & 120",
        "Baseline & 0.65 & 120",
        "Changing a reported figure changes the comparison.",
    ),
    Mutation(
        "M-UNIT",
        "unit",
        "F-TABLE-001",
        "Time (s)",
        "Time (ms)",
        "Changing a unit changes the magnitude the reader infers.",
    ),
    Mutation(
        "M-TABLE-ROW",
        "number",
        "F-TABLE-001",
        "Proposed & 0.92 & 95",
        "Proposed & 0.92 & 59",
        "Transposing digits changes the reported result.",
    ),
]


def _load_ready_fixtures() -> dict[str, Path]:
    manifest = json.loads((ROOT / "fixtures/manifest.json").read_text(encoding="utf-8"))
    ready: dict[str, Path] = {}
    for row in manifest.get("fixtures", []):
        if row.get("lifecycle") == "ready" and row.get("source_path"):
            ready[row["id"]] = ROOT / row["source_path"]
    return ready


def _replay(mutation: Mutation, source_path: Path) -> dict:
    source = source_path.read_text(encoding="utf-8")

    if mutation.find not in source:
        return {
            "mutation": mutation.mutation_id,
            "kind": mutation.kind,
            "fixture": mutation.fixture_id,
            "status": "error",
            "detail": f"target text not present in fixture: {mutation.find!r}",
        }

    mutated = source.replace(mutation.find, mutation.replace, 1)
    if mutated == source:
        return {
            "mutation": mutation.mutation_id,
            "kind": mutation.kind,
            "fixture": mutation.fixture_id,
            "status": "error",
            "detail": "replacement produced an identical document",
        }

    baseline = parse_latex(source, sha256(source.encode()).hexdigest())
    revised = parse_latex(mutated, sha256(mutated.encode()).hexdigest())

    correspondences, _ = compare_documents(baseline.objects, revised.objects)

    statuses = [c.status for c in correspondences]
    caught = [s for s in statuses if s in ACCEPTABLE]

    # A mutation is caught when at least one correspondence reports a
    # non-benign outcome. If every correspondence is unchanged or explained,
    # the comparator missed a real meaning change.
    status = "caught" if caught else "missed"

    return {
        "mutation": mutation.mutation_id,
        "kind": mutation.kind,
        "fixture": mutation.fixture_id,
        "status": status,
        "outcomes": sorted({s.value for s in statuses}),
        "baseline_objects": len(baseline.objects),
        "revised_objects": len(revised.objects),
        "rationale": mutation.rationale,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit the machine record")
    args = parser.parse_args()

    try:
        ready = _load_ready_fixtures()
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL cannot read fixture manifest: {error}", file=sys.stderr)
        return 3

    results = []
    for mutation in MUTATIONS:
        source_path = ready.get(mutation.fixture_id)
        if source_path is None or not source_path.is_file():
            results.append(
                {
                    "mutation": mutation.mutation_id,
                    "kind": mutation.kind,
                    "fixture": mutation.fixture_id,
                    "status": "error",
                    "detail": "fixture is not ready in the manifest",
                }
            )
            continue
        results.append(_replay(mutation, source_path))

    record = {
        "total": len(results),
        "caught": sum(1 for r in results if r["status"] == "caught"),
        "missed": sum(1 for r in results if r["status"] == "missed"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "kinds": sorted({r["kind"] for r in results}),
        "results": results,
    }

    if args.json:
        print(json.dumps(record, indent=2))
    else:
        for result in results:
            marker = "PASS" if result["status"] == "caught" else "FAIL"
            outcomes = ",".join(result.get("outcomes", [])) or result.get("detail", "")
            print(f"{marker} {result['mutation']:18} {result['kind']:12} {outcomes}")
        print(
            "INFO mutation_replay "
            f"total={record['total']} caught={record['caught']} "
            f"missed={record['missed']} errors={record['errors']}"
        )

    return 0 if record["missed"] == 0 and record["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
