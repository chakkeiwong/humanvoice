#!/usr/bin/env python3
"""Check v2 master-program structure and report V2-G0 readiness separately.

The program, its change record, the requirement register, the contract, and the
record catalogue must agree before any v2 semantic implementation begins. This
checker enforces that agreement structurally: it does not judge whether the
plan is a good plan, only whether the authority documents say the same thing
and whether they avoid claiming evidence states they have not earned.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = "docs/plans/humanvoice_master_program_v2.md"
CHANGE_RECORD = "docs/plans/humanvoice_v2_contract_change_2026-09-11.md"
REQUIRED_PATHS = (
    PROGRAM,
    CHANGE_RECORD,
    "docs/plans/templates/gate_decision_record.md",
    "docs/survey/humanvoice_product_requirements.json",
    "docs/survey/humanvoice_survey.tex",
    "docs/survey/proposal/21_implementation_contract.tex",
    "fixtures/manifest.json",
    "fixtures/historical_sources.json",
    "schemas/implementation_contract.json",
    "schemas/record_catalog.json",
    "security/runtime_profile.json",
    "security/inference_profile.json",
    "requirements-dev.txt",
)

CONTRACT_ID = "HV-IC-2026-09-11"
CATALOG_ID = "HV-RECORD-CATALOG-2026-09-11"
CURRENT_RECORD_COUNT = 21
LEGACY_RECORD_COUNT = 3

WORK_PACKAGES = tuple(f"WP-V2-{number}" for number in range(7))
GATES = tuple(f"V2-G{number}" for number in range(7))
EVIDENCE_STATES = (
    "specified",
    "implemented",
    "test-verified",
    "independently reproduced",
    "human-evidenced",
)

# Program prose that must survive any edit, because each sentence is the only
# place a specific v1 failure mode is ruled out.
REQUIRED_PROGRAM_CLAIMS = (
    ("hv humanize", "the sole production orchestrator"),
    ("exactly 1.0", "the retention invariant"),
    ("Mention does not satisfy explanation", "the explanation invariant"),
    ("2,000-word", "the split-trigger-not-target rule"),
    ("cannot satisfy a v2 gate", "the v1 evidence boundary"),
    ("named human reader", "human promotion authority"),
    ("distinct teaching role", "the useful-repetition invariant"),
)

# Claims the program must NOT make while it is only specified.
FORBIDDEN_PROGRAM_CLAIMS = (
    (r"product\s+(?:is\s+)?work(?:s|ing)\b", "an unearned product-working claim"),
    (r"V2-G[1-6][^\n]{0,40}(?<!not )(?<!never )\bpassed\b", "an unearned v2 gate pass"),
    (r"\bproduction[- ]ready\b", "an unearned production-ready claim"),
    (r"reader\s+acceptance\s+(?:is\s+)?(?:achieved|demonstrated)", "unearned reader evidence"),
)

LIFECYCLE_STATES = {"planned", "ready", "unavailable", "not-applicable"}
MANIFEST_STATUSES = {"inventory-only", "partial-readiness", "ready"}
EVALUATION_SCOPES = {
    "engineering-only",
    "internal-evaluation",
    "external-reader",
    "excluded",
}
CATALOGUE_FIXTURE_TYPES = {
    "macro",
    "equation",
    "table",
    "citation",
    "qualification",
    "register",
    "intentional-pattern",
    "pacing",
    "first-use",
    "assertion",
    "reader",
}
THREAT_FIXTURE_TYPES = {f"threat-T{number}" for number in range(1, 6)}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def section(text: str, heading: str) -> str:
    """Return one heading's body, stopping at the next heading of any depth."""
    start = text.find(heading)
    if start < 0:
        return ""
    offset = start + len(heading)
    positions = [
        text.find(f"\n{'#' * depth} ", offset) for depth in (2, 3, 4)
    ]
    candidates = [position for position in positions if position >= 0]
    end = min(candidates) if candidates else len(text)
    return text[start:end]


def _resolve_historical_path(root: Path, repository: str, relative: str) -> Path:
    if repository == root.name:
        return root / relative
    return root.parent / repository / relative


def _validate_program_text(program_text: str, errors: list[str]) -> None:
    """The program must name every work package, gate, and invariant."""
    for work_package in WORK_PACKAGES:
        if f"### {work_package}" not in program_text:
            errors.append(f"program omits work package {work_package}")
    for gate in GATES:
        if f"**{gate}:**" not in program_text:
            errors.append(f"program omits an exit criterion for {gate}")
    for state in EVIDENCE_STATES:
        if state not in program_text:
            errors.append(f"program omits evidence state {state}")
    for fragment, label in REQUIRED_PROGRAM_CLAIMS:
        if fragment not in program_text:
            errors.append(f"program no longer states {label}")
    for pattern, label in FORBIDDEN_PROGRAM_CLAIMS:
        match = re.search(pattern, program_text, flags=re.IGNORECASE)
        if match:
            errors.append(f"program makes {label}: {match.group(0)!r}")

    # V2-G6 is the only gate that can authorize release, and its human
    # evidence is the one requirement that has no automated substitute.
    g6 = section(program_text, "### WP-V2-6")
    if "Only V2-G6" not in g6:
        errors.append("program does not reserve release authorization to V2-G6")
    if "cannot be waived" not in g6:
        errors.append("program does not make missing human evidence unwaivable")


def _validate_change_record(text: str, errors: list[str]) -> None:
    """The change record is what keeps R1-R24 from being silently reinterpreted."""
    for heading in (
        "## Defect requiring a major version",
        "## Authority decision",
        "## Required interpretation of retained requirements",
        "## Added requirements",
        "## Migration rules",
        "## Superseded behavior",
        "## Evidence status at decision",
    ):
        if heading not in text:
            errors.append(f"change record omits {heading}")
    added = section(text, "## Added requirements")
    for requirement in ("R25", "R26", "R27", "R28", "R29"):
        if requirement not in added:
            errors.append(f"change record does not introduce {requirement}")
    migration = section(text, "## Migration rules")
    if not re.search(
        r"(re-initial|copied into a new v2 immutable snapshot)",
        migration,
        flags=re.IGNORECASE,
    ):
        errors.append("change record omits the v1 re-initialization rule")


def _validate_contract_alignment(
    root: Path, program_text: str, errors: list[str]
) -> set[str]:
    contract = load_json(root / "schemas/implementation_contract.json")
    if contract.get("contract_id") != CONTRACT_ID:
        errors.append("contract names the wrong contract id")
    if contract.get("status") != "specified":
        errors.append("contract claims an evidence state beyond specified")

    packages = [row.get("id") for row in contract.get("work_packages", [])]
    if packages != list(WORK_PACKAGES):
        errors.append("contract work packages are not WP-V2-0 through WP-V2-6")
    gates = [row.get("id") for row in contract.get("gates", [])]
    if gates != list(GATES):
        errors.append("contract gates are not V2-G0 through V2-G6")

    # Every gate the contract defines must have the same exit text in the
    # program. Divergence here is how a gate quietly loses a requirement.
    for row in contract.get("gates", []):
        gate_id = row.get("id")
        if isinstance(gate_id, str) and f"**{gate_id}:**" not in program_text:
            errors.append(f"program omits contract gate {gate_id}")

    if contract.get("authority", {}).get("program") != PROGRAM:
        errors.append("contract does not name the v2 program as authority")
    if contract.get("authority", {}).get("change_record") != CHANGE_RECORD:
        errors.append("contract does not name the v2 change record")

    requirements = load_json(root / "docs/survey/humanvoice_product_requirements.json")
    rows = requirements.get("requirements", [])
    requirement_ids = {row.get("id") for row in rows}
    expected = {f"R{number}" for number in range(1, 30)}
    if requirements.get("requirement_count") != 29 or requirement_ids != expected:
        errors.append("requirement register is not exactly R1-R29")
    if requirements.get("change_record") != CHANGE_RECORD:
        errors.append("requirement register does not cite the v2 change record")
    allowed_phases = {f"P{number}" for number in range(6)}
    allowed_phases |= {f"V2-P{number}" for number in range(6)}
    for row in rows:
        phases = {
            value.strip()
            for value in str(row.get("phase", "")).split(",")
            if value.strip()
        }
        if not phases or not phases <= allowed_phases:
            errors.append(f"requirement {row.get('id')} has an invalid phase mapping")
    return requirement_ids


def _validate_catalog(root: Path, errors: list[str], blockers: list[str]) -> None:
    catalog = load_json(root / "schemas/record_catalog.json")
    rows = catalog.get("records", [])
    concept_ids = [row.get("concept_id") for row in rows]
    if len(concept_ids) != len(set(concept_ids)):
        errors.append("record catalogue repeats a conceptual object")
    if catalog.get("catalog_id") != CATALOG_ID:
        errors.append("record catalogue names the wrong catalogue id")
    if catalog.get("contract_id") != CONTRACT_ID:
        errors.append("record catalogue names the wrong contract")
    policy = catalog.get("compatibility_policy", {})
    if policy.get("unknown_top_level_fields") != "reject":
        errors.append("record catalogue does not reject unknown top-level fields")

    current = 0
    legacy = 0
    for row in rows:
        schema_path = root / str(row.get("schema_path", ""))
        status = row.get("schema_status")
        if status == "present":
            current += 1
            if not schema_path.is_file():
                errors.append(
                    f"record {row.get('concept_id')} names a missing present schema"
                )
        elif status == "legacy_v1":
            legacy += 1
            if row.get("required_by") != "audit-only":
                errors.append(
                    f"legacy record {row.get('concept_id')} is not marked audit-only"
                )
        elif status == "planned":
            if schema_path.exists():
                errors.append(
                    f"record {row.get('concept_id')} still marks an existing schema planned"
                )
        else:
            errors.append(f"record {row.get('concept_id')} has unknown schema status")

    if current != CURRENT_RECORD_COUNT:
        errors.append(
            f"catalogue lists {current} current records; expected {CURRENT_RECORD_COUNT}"
        )
    if legacy != LEGACY_RECORD_COUNT:
        errors.append(
            f"catalogue lists {legacy} legacy_v1 records; expected {LEGACY_RECORD_COUNT}"
        )
    if catalog.get("status") != "specified":
        errors.append(
            "record catalogue must report only specified at V2-G0; "
            f"found {catalog.get('status')!r}"
        )


def _validate_inference_profile(root: Path, errors: list[str], blockers: list[str]) -> None:
    """The v1 profile claimed readiness for a gate that no longer exists."""
    profile = load_json(root / "security/inference_profile.json")
    if profile.get("contract_version") != "2.0.0":
        errors.append("inference profile is not bound to contract 2.0.0")
    if "g2_readiness" in profile:
        errors.append("inference profile still claims v1 G2 readiness")
    budget = profile.get("budget", {})
    for field in budget:
        if "word" in field.lower():
            errors.append(f"inference profile carries a word budget: {field}")
    prompt = profile.get("prompt_template", {})
    inline = {
        name
        for name in json.dumps(prompt)
        .replace('"', " ")
        .split()
        if name in {"PLAN_SCHEMA", "DRAFT_SCHEMA", "REPAIR_SCHEMA"}
    }
    if inline:
        errors.append(
            "inference profile names removed inline schemas: " + ", ".join(sorted(inline))
        )
    if profile.get("profile_status") not in {"specified", "calibration-pending"}:
        errors.append(
            "inference profile claims an evidence state beyond specification"
        )
    calibration = profile.get("calibration")
    if "calibration" not in profile:
        errors.append("inference profile omits the calibration field")
    elif calibration not in (None, {}, []):
        # Recorded calibration must name its held-out set and the critic it
        # licenses; an unlabelled blob would let a critic claim readiness.
        if not isinstance(calibration, dict) or not {
            "held_out_set",
            "critics",
        } <= set(calibration):
            errors.append(
                "inference profile calibration does not name a held-out set and critics"
            )


def _validate_fixture_manifest(
    root: Path,
    requirement_ids: set[str],
    rights_statuses: set[str],
    errors: list[str],
) -> dict[str, int]:
    manifest = load_json(root / "fixtures/manifest.json")
    if manifest.get("status") not in MANIFEST_STATUSES:
        errors.append(f"fixture manifest has unknown status: {manifest.get('status')}")
    rows = manifest.get("fixtures", [])
    counts = {state: 0 for state in LIFECYCLE_STATES}
    ids: set[str] = set()
    fixture_types: set[str] = set()
    required_fields = {
        "id",
        "fixture_type",
        "lifecycle",
        "source_path",
        "source_hash",
        "answer_key_path",
        "answer_key_hash",
        "rights_status",
        "owner",
        "evaluation_scope",
        "intended_job",
        "expected_outcomes",
        "requirements",
    }

    for row in rows:
        fixture_id = row.get("id", "?")
        missing = sorted(required_fields - set(row))
        if missing:
            errors.append(f"fixture {fixture_id} lacks fields: {', '.join(missing)}")
            continue
        if fixture_id in ids:
            errors.append(f"duplicate fixture id: {fixture_id}")
        ids.add(fixture_id)
        fixture_types.add(row["fixture_type"])

        lifecycle = row["lifecycle"]
        if lifecycle not in LIFECYCLE_STATES:
            errors.append(f"fixture {fixture_id} has unknown lifecycle {lifecycle}")
            continue
        counts[lifecycle] += 1
        if row["rights_status"] not in rights_statuses:
            errors.append(f"fixture {fixture_id} has unknown rights status")
        if row["evaluation_scope"] not in EVALUATION_SCOPES:
            errors.append(f"fixture {fixture_id} has unknown evaluation scope")
        unknown_requirements = set(row["requirements"]) - requirement_ids
        if unknown_requirements:
            errors.append(
                f"fixture {fixture_id} names unknown requirements: "
                + ", ".join(sorted(unknown_requirements))
            )

        outcomes = row["expected_outcomes"]
        for outcome in ("positive", "negative", "abstention", "not_applicable_reason"):
            if outcome not in outcomes:
                errors.append(f"fixture {fixture_id} lacks expected outcome {outcome}")
        if outcomes.get("abstention") is None and not outcomes.get("not_applicable_reason"):
            errors.append(f"fixture {fixture_id} omits both abstention and N/A reason")

        paths_and_hashes = (
            row["source_path"],
            row["source_hash"],
            row["answer_key_path"],
            row["answer_key_hash"],
        )
        if lifecycle == "planned" and any(value is not None for value in paths_and_hashes):
            errors.append(f"planned fixture {fixture_id} carries a placeholder path or hash")
        if lifecycle == "ready":
            if not all(isinstance(value, str) and value for value in paths_and_hashes):
                errors.append(
                    f"ready fixture {fixture_id} lacks a source or answer-key path/hash"
                )
                continue
            for path_field, hash_field in (
                ("source_path", "source_hash"),
                ("answer_key_path", "answer_key_hash"),
            ):
                artifact = root / row[path_field]
                if not artifact.is_file():
                    errors.append(f"ready fixture {fixture_id} lacks file {row[path_field]}")
                elif sha256_file(artifact) != row[hash_field]:
                    errors.append(f"ready fixture {fixture_id} has wrong {hash_field}")
            if (
                row["evaluation_scope"] == "external-reader"
                and row["rights_status"] != "cleared-public"
            ):
                errors.append(
                    f"ready external fixture {fixture_id} is not cleared-public"
                )
            if row["evaluation_scope"] == "internal-evaluation" and row[
                "rights_status"
            ] not in {"cleared-internal", "cleared-public"}:
                errors.append(
                    f"ready internal fixture {fixture_id} lacks internal-use clearance"
                )
        if lifecycle == "unavailable" and not row.get("unavailable_reason"):
            errors.append(f"unavailable fixture {fixture_id} has no reason")
        if lifecycle == "not-applicable" and not outcomes.get("not_applicable_reason"):
            errors.append(f"not-applicable fixture {fixture_id} has no reason")

    missing_catalogue = CATALOGUE_FIXTURE_TYPES - fixture_types
    missing_threats = THREAT_FIXTURE_TYPES - fixture_types
    if missing_catalogue:
        errors.append(
            "fixture inventory omits catalogue types: " + ", ".join(sorted(missing_catalogue))
        )
    if missing_threats:
        errors.append(
            "fixture inventory omits threat types: " + ", ".join(sorted(missing_threats))
        )
    if manifest.get("status") == "ready" and counts["ready"] != len(rows):
        errors.append("fixture manifest claims ready while non-ready rows remain")
    if manifest.get("status") == "inventory-only" and counts["ready"]:
        errors.append("fixture manifest claims inventory-only while ready rows exist")
    if manifest.get("status") == "partial-readiness" and counts["ready"] == 0:
        errors.append("fixture manifest claims partial readiness without a ready row")
    return counts


def _validate_historical_sources(
    root: Path, errors: list[str], verify_external: bool
) -> None:
    registry = load_json(root / "fixtures/historical_sources.json")
    ids: set[str] = set()
    for row in registry.get("sources", []):
        source_id = row.get("id", "?")
        if source_id in ids:
            errors.append(f"duplicate historical source id: {source_id}")
        ids.add(source_id)
        availability = str(row.get("availability", ""))
        if availability.startswith("located"):
            relative = row.get("repository_relative_path")
            expected_hash = row.get("sha256")
            if not relative or not expected_hash:
                errors.append(f"located historical source {source_id} lacks path or hash")
            elif verify_external:
                artifact = _resolve_historical_path(root, row.get("repository", ""), relative)
                if not artifact.is_file():
                    errors.append(f"located historical source is missing: {source_id}")
                elif sha256_file(artifact) != expected_hash:
                    errors.append(f"located historical source hash changed: {source_id}")
        elif availability == "unavailable":
            if row.get("repository_relative_path") is not None or row.get("sha256") is not None:
                errors.append(
                    f"unavailable historical source {source_id} carries an asserted locator"
                )
        else:
            errors.append(f"historical source {source_id} has unknown availability")
        if row.get("replay_status") == "reproduced" and availability != "ready":
            errors.append(
                f"historical source {source_id} claims replay without ready evidence"
            )


def validate_program(root: Path = ROOT, verify_external: bool = True) -> dict[str, object]:
    errors: list[str] = []
    blockers: list[str] = []

    for relative in REQUIRED_PATHS:
        if not (root / relative).exists():
            errors.append(f"required program artifact is missing: {relative}")
    if errors:
        return {
            "program_consistent": False,
            "g0_ready": False,
            "fixture_counts": {state: 0 for state in LIFECYCLE_STATES},
            "errors": errors,
            "blockers": blockers,
        }

    requirements_dev = (root / "requirements-dev.txt").read_text(encoding="utf-8")
    if "jsonschema==4.26.0" not in requirements_dev:
        errors.append("requirements-dev.txt does not pin jsonschema==4.26.0")

    program_text = (root / PROGRAM).read_text(encoding="utf-8")
    _validate_program_text(program_text, errors)
    _validate_change_record(
        (root / CHANGE_RECORD).read_text(encoding="utf-8"), errors
    )
    requirement_ids = _validate_contract_alignment(root, program_text, errors)

    contract = load_json(root / "schemas/implementation_contract.json")
    rights_statuses = set(contract.get("corpus_rights", {}).get("allowed_statuses", []))
    fixture_counts = _validate_fixture_manifest(
        root, requirement_ids, rights_statuses, errors
    )
    _validate_catalog(root, errors, blockers)
    _validate_inference_profile(root, errors, blockers)
    _validate_historical_sources(root, errors, verify_external)

    runtime = load_json(root / "security/runtime_profile.json")
    if runtime.get("isolation", {}).get("unsandboxed_fallback") is not False:
        errors.append("runtime profile permits an unsandboxed fallback")
    if runtime.get("profile_status") != "verified":
        blockers.append("reference runtime has not passed its isolation verification")

    template = (root / "docs/plans/templates/gate_decision_record.md").read_text(
        encoding="utf-8"
    )
    for field in (
        "**Gate:**",
        "**Decision date:**",
        "**Decision:**",
        "## Inputs",
        "## Authorized Scope",
        "## Next Decision",
    ):
        if field not in template:
            errors.append(f"gate decision template omits {field}")

    # A runner named in the verification ladder must either exist or be
    # explicitly marked a later deliverable. Silence in both directions is
    # how a ladder rung becomes imaginary evidence.
    ladder = section(program_text, "## 8. Verification ladder")
    for runner in ("tools/run_fixture_suite.py", "tools/run_regression_replay.py"):
        if runner not in ladder:
            errors.append(f"verification ladder omits {runner}")
            continue
        if not (root / runner).exists():
            deliverable = re.search(
                r"(regression runner|fixture runner)[^.]{0,120}?(not evidence|deliverable)",
                program_text,
                flags=re.IGNORECASE,
            )
            if not deliverable and "not evidence until implemented" not in program_text:
                errors.append(f"absent runner is not marked a later deliverable: {runner}")

    # No v2 gate record may claim a pass while the program is only specified.
    gates_dir = root / "docs/plans/gates"
    if gates_dir.is_dir():
        for record in sorted(gates_dir.glob("V2-G*.md")):
            text = record.read_text(encoding="utf-8")
            if "**Decision:** pass" in text and blockers:
                errors.append(f"{record.name} claims pass while blockers remain")

    consistent = not errors
    return {
        "program_consistent": consistent,
        "g0_ready": consistent and not blockers,
        "fixture_counts": fixture_counts,
        "errors": errors,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-g0-ready",
        action="store_true",
        help="return failure when the structurally valid program still has V2-G0 blockers",
    )
    parser.add_argument(
        "--skip-external-hash-check",
        action="store_true",
        help="skip sibling-repository hash checks (for isolated mutation tests only)",
    )
    args = parser.parse_args()
    result = validate_program(verify_external=not args.skip_external_hash_check)
    if not result["program_consistent"]:
        for error in result["errors"]:
            print(f"FAIL {error}")
        return 1

    counts = result["fixture_counts"]
    print("PASS v2_program_structure_and_gates")
    print("PASS change_record_and_requirement_register")
    print("PASS contract_and_catalogue_alignment")
    print("PASS fixture_lifecycle_and_rights_rules")
    print("PASS historical_locator_registry")
    print(
        "INFO fixture_readiness "
        + " ".join(f"{state}={counts[state]}" for state in sorted(counts))
    )
    print("STATE specified")

    if result["g0_ready"]:
        print("PASS V2-G0_ready")
        return 0
    for blocker in result["blockers"]:
        print(f"BLOCKED V2-G0 {blocker}")
    return 1 if args.require_g0_ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
