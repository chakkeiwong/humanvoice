#!/usr/bin/env python3
"""Check master-program structure and report G0 readiness separately."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = "docs/plans/humanvoice_master_program_v1.1_2026-08-26.md"
REQUIRED_PATHS = (
    PROGRAM,
    "docs/plans/humanvoice_decisions_2026-08-26.md",
    "docs/plans/humanvoice_staffing_plan_2026-08-26.json",
    "docs/plans/templates/gate_decision_record.md",
    "docs/plans/gates/G0_decision_2026-08-26.md",
    "docs/survey/humanvoice_product_requirements.json",
    "fixtures/manifest.json",
    "fixtures/historical_sources.json",
    "schemas/implementation_contract.json",
    "schemas/record_catalog.json",
    "security/runtime_profile.json",
    "requirements-dev.txt",
)
GATE_HEADINGS = {
    "G0": "### G0 - authorization gate (day 5)",
    "G1": "### G1 - protected-core gate (end of week 6)",
    "G2": "### G2 - authoring-extension gate (end of week 9)",
    "G3": "### G3 - reader-session gate (weeks 10-11)",
    "G4": "### G4 - handoff gate (week 12)",
}
WP_HEADINGS = {f"WP{number}" for number in range(7)}
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
LIFECYCLE_STATES = {"planned", "ready", "unavailable", "not-applicable"}
MANIFEST_STATUSES = {"inventory-only", "partial-readiness", "ready"}
EVALUATION_SCOPES = {
    "engineering-only",
    "internal-evaluation",
    "external-reader",
    "excluded",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    next_heading = text.find("\n### ", start + len(heading))
    next_top_heading = text.find("\n## ", start + len(heading))
    candidates = [position for position in (next_heading, next_top_heading) if position >= 0]
    end = min(candidates) if candidates else len(text)
    return text[start:end]


def _resolve_historical_path(root: Path, repository: str, relative: str) -> Path:
    if repository == root.name:
        return root / relative
    return root.parent / repository / relative


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
                errors.append(f"ready fixture {fixture_id} lacks a source or answer-key path/hash")
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
            if row["evaluation_scope"] == "external-reader" and row["rights_status"] != "cleared-public":
                errors.append(f"ready external fixture {fixture_id} is not cleared-public")
            if row["evaluation_scope"] == "internal-evaluation" and row["rights_status"] not in {
                "cleared-internal",
                "cleared-public",
            }:
                errors.append(f"ready internal fixture {fixture_id} lacks internal-use clearance")
        if lifecycle == "unavailable" and not row.get("unavailable_reason"):
            errors.append(f"unavailable fixture {fixture_id} has no reason")
        if lifecycle == "not-applicable" and not outcomes.get("not_applicable_reason"):
            errors.append(f"not-applicable fixture {fixture_id} has no reason")

    missing_catalogue = CATALOGUE_FIXTURE_TYPES - fixture_types
    missing_threats = THREAT_FIXTURE_TYPES - fixture_types
    if missing_catalogue:
        errors.append("fixture inventory omits catalogue types: " + ", ".join(sorted(missing_catalogue)))
    if missing_threats:
        errors.append("fixture inventory omits threat types: " + ", ".join(sorted(missing_threats)))
    if manifest.get("status") == "ready" and counts["ready"] != len(rows):
        errors.append("fixture manifest claims ready while non-ready rows remain")
    if manifest.get("status") == "inventory-only" and counts["ready"]:
        errors.append("fixture manifest claims inventory-only while ready rows exist")
    if manifest.get("status") == "partial-readiness" and counts["ready"] == 0:
        errors.append("fixture manifest claims partial readiness without a ready row")
    return counts


def _validate_catalog(root: Path, errors: list[str], blockers: list[str]) -> None:
    catalog = load_json(root / "schemas/record_catalog.json")
    rows = catalog.get("records", [])
    concept_ids = [row.get("concept_id") for row in rows]
    if len(concept_ids) != 13 or len(set(concept_ids)) != 13:
        errors.append("record catalogue must contain 13 unique conceptual objects")
    if catalog.get("contract_id") != "HV-IC-2026-08-26":
        errors.append("record catalogue names the wrong contract")
    policy = catalog.get("compatibility_policy", {})
    if policy.get("unknown_top_level_fields") != "reject":
        errors.append("record catalogue does not reject unknown top-level fields")
    for row in rows:
        schema_path = root / str(row.get("schema_path", ""))
        status = row.get("schema_status")
        if status == "present" and not schema_path.is_file():
            errors.append(f"record {row.get('concept_id')} names a missing present schema")
        elif status == "planned" and schema_path.exists():
            errors.append(f"record {row.get('concept_id')} still marks an existing schema planned")
        elif status not in {"present", "planned"}:
            errors.append(f"record {row.get('concept_id')} has unknown schema status")
    if catalog.get("status") != "approved":
        blockers.append("record catalogue lacks named sponsor concurrence")


def _validate_historical_sources(
    root: Path, errors: list[str], verify_external: bool
) -> None:
    registry = load_json(root / "fixtures/historical_sources.json")
    rows = registry.get("sources", [])
    ids: set[str] = set()
    for row in rows:
        source_id = row.get("id", "?")
        if source_id in ids:
            errors.append(f"duplicate historical source id: {source_id}")
        ids.add(source_id)
        availability = row.get("availability")
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
                errors.append(f"unavailable historical source {source_id} carries an asserted locator")
        else:
            errors.append(f"historical source {source_id} has unknown availability")
        if row.get("replay_status") == "reproduced" and availability != "ready":
            errors.append(f"historical source {source_id} claims replay without ready evidence")


def validate_program(root: Path = ROOT, verify_external: bool = True) -> dict[str, object]:
    errors: list[str] = []
    blockers: list[str] = []

    for relative in REQUIRED_PATHS:
        if not (root / relative).exists():
            errors.append(f"required program artifact is missing: {relative}")
    if errors:
        return {"program_consistent": False, "g0_ready": False, "errors": errors, "blockers": blockers}

    requirements_dev = (root / "requirements-dev.txt").read_text(encoding="utf-8")
    if "jsonschema==4.26.0" not in requirements_dev:
        errors.append("requirements-dev.txt does not pin jsonschema==4.26.0")

    program_text = (root / PROGRAM).read_text(encoding="utf-8")
    for gate, heading in GATE_HEADINGS.items():
        gate_text = section(program_text, heading)
        if not gate_text:
            errors.append(f"program omits {gate} heading")
        elif "**Decision owners:**" not in gate_text:
            errors.append(f"program omits decision owners for {gate}")
    integration_heading = "### Internal integration gate (end of week 4)"
    integration_text = section(program_text, integration_heading)
    if not integration_text or "**Decision owners:**" not in integration_text:
        errors.append("program omits owners for the internal integration gate")
    for wp in WP_HEADINGS:
        if f"### {wp} -" not in program_text and f"| {wp} -" not in program_text:
            errors.append(f"program omits {wp}")
    if "WP0 is the work that produces the evidence for G0" not in program_text:
        errors.append("program does not distinguish WP0 work from the G0 decision")

    contract = load_json(root / "schemas/implementation_contract.json")
    pre_authorization = contract.get("pre_authorization_package", {})
    if pre_authorization.get("id") != "WP0" or pre_authorization.get("exit") != "G0 decision record":
        errors.append("contract does not identify WP0 as the pre-authorization package")
    if [row.get("id") for row in contract.get("work_packages", [])] != [f"WP{i}" for i in range(1, 7)]:
        errors.append("contract product work-package list must contain WP1-WP6")
    requirements = load_json(root / "docs/survey/humanvoice_product_requirements.json")
    rows = requirements.get("requirements", [])
    expected_requirement_ids = {f"R{number}" for number in range(1, 25)}
    requirement_ids = {row.get("id") for row in rows}
    if requirements.get("requirement_count") != 24 or requirement_ids != expected_requirement_ids:
        errors.append("requirement register is not exactly R1-R24")
    allowed_phases = {f"P{number}" for number in range(6)}
    for row in rows:
        phases = {value.strip() for value in str(row.get("phase", "")).split(",") if value.strip()}
        if not phases or not phases <= allowed_phases:
            errors.append(f"requirement {row.get('id')} has an invalid phase mapping")

    week_six = contract.get("scope", {}).get("protected_core_checkpoint_week")
    week_nine = contract.get("scope", {}).get("full_authoring_path_checkpoint_week")
    if f"end of week {week_six}" not in program_text:
        errors.append("program schedule disagrees with the protected-core checkpoint")
    if f"end of week {week_nine}" not in program_text:
        errors.append("program schedule disagrees with the authoring checkpoint")

    section_nine = section(program_text, "### 9.2 Outcomes")
    if "co-primary outcomes" not in section_nine or "feedback rounds" not in section_nine:
        errors.append("program no longer preserves the agreed evaluation outcomes")

    rights_statuses = set(contract.get("corpus_rights", {}).get("allowed_statuses", []))
    fixture_counts = _validate_fixture_manifest(
        root, requirement_ids, rights_statuses, errors
    )
    _validate_catalog(root, errors, blockers)
    _validate_historical_sources(root, errors, verify_external)

    staffing = load_json(root / "docs/plans/humanvoice_staffing_plan_2026-08-26.json")
    contract_roles = set(contract.get("staffed_roles", []))
    staffing_rows = staffing.get("roles", [])
    staffing_roles = {row.get("role") for row in staffing_rows}
    if staffing_roles != contract_roles or len(staffing_rows) != len(contract_roles):
        errors.append("staffing plan does not cover the contract roles exactly once")
    unassigned = [row.get("role") for row in staffing_rows if not row.get("assignee")]
    incomplete_allocations = [
        row.get("role")
        for row in staffing_rows
        if row.get("assignee") and not row.get("allocation_fte")
    ]
    if incomplete_allocations:
        errors.append("staffed roles lack allocation: " + ", ".join(incomplete_allocations))
    if unassigned:
        blockers.append("unassigned staffed roles: " + ", ".join(unassigned))

    runtime = load_json(root / "security/runtime_profile.json")
    if runtime.get("isolation", {}).get("unsandboxed_fallback") is not False:
        errors.append("runtime profile permits an unsandboxed fallback")
    if runtime.get("profile_status") != "verified" or runtime.get("g0_readiness") != "ready":
        blockers.append("reference runtime has not passed its isolation verification")

    template = (root / "docs/plans/templates/gate_decision_record.md").read_text(
        encoding="utf-8"
    )
    for field in ("**Gate:**", "**Decision date:**", "**Decision:**", "## Inputs", "## Authorized Scope", "## Next Decision"):
        if field not in template:
            errors.append(f"gate decision template omits {field}")

    for planned_runner in (
        "tools/run_fixture_suite.py",
        "tools/run_regression_replay.py",
    ):
        exists = (root / planned_runner).exists()
        runner_section = section(
            program_text,
            "### 7.1 Machine fixture corpus" if "fixture_suite" in planned_runner else "### 7.3 Historical replay quarantine",
        )
        runner_mention = f"`{planned_runner}"
        if runner_mention not in runner_section:
            named_planned = False
        else:
            # Look for "planned" within 200 chars of the backticked runner name,
            # not anywhere in the section (which would catch lifecycle vocabulary).
            mention_pos = runner_section.find(runner_mention)
            context = runner_section[max(0, mention_pos - 100):mention_pos + 100]
            named_planned = "planned" in context

        if not exists and not named_planned:
            errors.append(f"absent runner is not marked planned: {planned_runner}")
        if exists and named_planned:
            errors.append(f"existing runner is still marked planned: {planned_runner}")

    if fixture_counts["ready"] == 0:
        blockers.append("fixture inventory contains no ready executable case")

    gate_record = (root / "docs/plans/gates/G0_decision_2026-08-26.md").read_text(
        encoding="utf-8"
    )
    if "**Decision:** pass" in gate_record and blockers:
        errors.append("G0 decision record claims pass while blockers remain")

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
        help="return failure when the structurally valid program still has G0 blockers",
    )
    parser.add_argument(
        "--skip-external-hash-check",
        action="store_true",
        help="skip sibling-repository hash checks (for isolated mutation tests only)",
    )
    parser.add_argument(
        "--prototype",
        action="store_true",
        help="prototype scale: collapse 8 roles to 2 (owner + agent), defer independent review, record this choice",
    )
    args = parser.parse_args()
    result = validate_program(verify_external=not args.skip_external_hash_check)
    if not result["program_consistent"]:
        for error in result["errors"]:
            print(f"FAIL {error}")
        return 1

    counts = result["fixture_counts"]
    print("PASS program_structure_and_schedule")
    print("PASS requirement_and_record_catalogues")
    print("PASS fixture_lifecycle_and_rights_rules")
    print("PASS historical_locator_registry")
    print(
        "INFO fixture_readiness "
        + " ".join(f"{state}={counts[state]}" for state in sorted(counts))
    )

    # Prototype mode: collapse staffing blockers and record the deferral
    if args.prototype:
        filtered_blockers = [
            b for b in result["blockers"]
            if "staffed roles" not in b and "sponsor concurrence" not in b
        ]
        if not filtered_blockers:
            print("PASS G0_ready (prototype scale: independent review deferred)")
            return 0
        for blocker in filtered_blockers:
            print(f"BLOCKED G0 {blocker}")
        return 1 if args.require_g0_ready else 0

    # Full staffing mode
    if result["g0_ready"]:
        print("PASS G0_ready")
        return 0
    for blocker in result["blockers"]:
        print(f"BLOCKED G0 {blocker}")
    return 1 if args.require_g0_ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
