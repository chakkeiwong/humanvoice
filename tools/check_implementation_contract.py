#!/usr/bin/env python3
"""Validate the implementation contract, record schemas, and examples."""

from __future__ import annotations

import json
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import SchemaError
except ImportError:  # pragma: no cover - reported as a validation error below
    Draft202012Validator = None
    FormatChecker = None
    SchemaError = Exception


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_VALIDATOR_VERSION = "4.26.0"
EXPECTED_SCHEMA_FILES = {
    "authoring-brief.schema.json",
    "argument-blueprint.schema.json",
    "finding.schema.json",
    "revision.schema.json",
    "preflight-run.schema.json",
    "release-decision.schema.json",
    "runtime-manifest.schema.json",
    "cli-result.schema.json",
    "corpus-item.schema.json",
    "source-snapshot.schema.json",
    "protected-manifest.schema.json",
    "evidence-item.schema.json",
    "reader-decision.schema.json",
}
COMMON_RECORD_FIELDS = {
    "record_type",
    "schema_version",
    "record_id",
    "run_id",
    "created_at",
}
RUNTIME_FIELDS = {
    "runtime_type",
    "model_version_string",
    "model_artifact_hash_if_local",
    "prompt_template_hash",
    "sampling",
    "seed_if_applicable",
    "api_endpoint",
    "request_id_if_available",
    "timestamp",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "output_hash",
    "not_applicable_reason",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_examples(root: Path, schemas: dict[str, dict], errors: list[str]) -> None:
    examples_dir = root / "schemas/examples"
    manifest_path = examples_dir / "manifest.json"
    if Draft202012Validator is None or FormatChecker is None:
        errors.append("python-jsonschema is not installed")
        return
    if not manifest_path.exists():
        errors.append("schema example manifest is missing")
        return

    try:
        installed = version("jsonschema")
    except PackageNotFoundError:
        errors.append("python-jsonschema distribution metadata is missing")
        return
    if installed != REFERENCE_VALIDATOR_VERSION:
        errors.append(
            f"jsonschema version is {installed}; expected {REFERENCE_VALIDATOR_VERSION}"
        )

    manifest = load_json(manifest_path)
    rows = manifest.get("examples", [])
    if not rows:
        errors.append("schema example manifest is empty")
        return

    valid_schema_names: set[str] = set()
    for row in rows:
        schema_name = row.get("schema")
        instance_name = row.get("instance")
        expected = row.get("expected")
        if schema_name not in schemas:
            errors.append(f"example {instance_name} names unknown schema {schema_name}")
            continue
        instance_path = examples_dir / str(instance_name)
        if not instance_path.is_file():
            errors.append(f"schema example is missing: {instance_name}")
            continue
        try:
            instance = load_json(instance_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"schema example {instance_name} cannot be loaded: {exc}")
            continue

        validator = Draft202012Validator(
            schemas[schema_name], format_checker=FormatChecker()
        )
        messages = [item.message for item in validator.iter_errors(instance)]
        if expected == "valid" and messages:
            errors.append(f"valid example {instance_name} failed: {messages[0]}")
        elif expected == "valid":
            valid_schema_names.add(schema_name)
        elif expected == "invalid":
            if not messages:
                errors.append(f"invalid example {instance_name} unexpectedly passed")
            marker = row.get("expected_error_contains")
            if marker and messages and not any(marker in message for message in messages):
                errors.append(
                    f"invalid example {instance_name} failed for the wrong reason: "
                    + "; ".join(messages)
                )
        elif expected not in {"valid", "invalid"}:
            errors.append(f"example {instance_name} has unknown expectation {expected}")

    missing_valid = EXPECTED_SCHEMA_FILES - valid_schema_names
    if missing_valid:
        errors.append(
            "schema example manifest lacks valid instances for: "
            + ", ".join(sorted(missing_valid))
        )


def validate_contract(root: Path = ROOT) -> dict[str, object]:
    errors: list[str] = []
    schema_dir = root / "schemas"
    contract_path = schema_dir / "implementation_contract.json"
    requirements_path = root / "docs/survey/humanvoice_product_requirements.json"
    rights_path = root / "docs/survey/evidence/corpus_rights_manifest.json"
    manuscript_path = root / "docs/survey/humanvoice_survey.tex"
    requirements_dev_path = root / "requirements-dev.txt"

    try:
        contract = load_json(contract_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"contract_valid": False, "errors": [f"contract cannot be loaded: {exc}"]}

    try:
        if "jsonschema==4.26.0" not in requirements_dev_path.read_text(encoding="utf-8"):
            errors.append("requirements-dev.txt does not pin jsonschema==4.26.0")
    except OSError as exc:
        errors.append(f"requirements-dev.txt cannot be read: {exc}")

    if contract.get("contract_id") != "HV-IC-2026-08-26":
        errors.append("unexpected contract_id")
    if contract.get("contract_version") not in ("1.0.0", "1.1.0"):
        errors.append("unexpected contract_version")

    present_schema_files = {path.name for path in schema_dir.glob("*.schema.json")}
    if not EXPECTED_SCHEMA_FILES <= present_schema_files:
        errors.append("missing record schema files")

    schemas: dict[str, dict] = {}
    for name in sorted(EXPECTED_SCHEMA_FILES):
        try:
            schema = load_json(schema_dir / name)
            schemas[name] = schema
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                errors.append(f"{name} has wrong JSON Schema dialect")
            if Draft202012Validator is not None:
                try:
                    Draft202012Validator.check_schema(schema)
                except SchemaError as exc:
                    errors.append(f"{name} is not a valid Draft 2020-12 schema: {exc.message}")

            required = set(schema.get("required", []))
            if not COMMON_RECORD_FIELDS <= required:
                missing = sorted(COMMON_RECORD_FIELDS - required)
                errors.append(f"{name} omits common required fields: {', '.join(missing)}")
            if schema.get("additionalProperties") is not False:
                errors.append(f"{name} permits unknown top-level fields")
            if schema.get("properties", {}).get("extensions", {}).get("type") != "object":
                errors.append(f"{name} has no extensions object")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{name} cannot be loaded: {exc}")

    cli_fields = set(contract.get("cli", {}).get("streams", {}).get("stable_stdout_fields", []))
    cli_required = set(schemas.get("cli-result.schema.json", {}).get("required", []))
    if not cli_fields <= cli_required:
        errors.append(
            "cli-result schema omits stable stdout fields: "
            + ", ".join(sorted(cli_fields - cli_required))
        )

    rights_fields = set(contract.get("corpus_rights", {}).get("required_fields", []))
    corpus_required = set(schemas.get("corpus-item.schema.json", {}).get("required", []))
    if not rights_fields <= corpus_required:
        errors.append(
            "corpus-item schema omits contract rights fields: "
            + ", ".join(sorted(rights_fields - corpus_required))
        )

    runtime_required = set(schemas.get("runtime-manifest.schema.json", {}).get("required", []))
    if not RUNTIME_FIELDS <= runtime_required:
        errors.append(
            "runtime-manifest schema omits provenance fields: "
            + ", ".join(sorted(RUNTIME_FIELDS - runtime_required))
        )

    record_requirements = contract.get("record_policy", {}).get("record_requirements", {})
    schema_by_record_type = {
        schema.get("properties", {}).get("record_type", {}).get("const"): schema
        for schema in schemas.values()
    }
    for record_type, fields in record_requirements.items():
        schema = schema_by_record_type.get(record_type)
        if schema is None:
            errors.append(f"contract record requirement names an unknown record type: {record_type}")
            continue
        missing = set(fields) - set(schema.get("required", []))
        if missing:
            errors.append(
                f"{record_type} schema omits contract record fields: "
                + ", ".join(sorted(missing))
            )

    _validate_examples(root, schemas, errors)

    controls = contract.get("trust_boundary", {}).get("controls", [])
    if {row.get("id") for row in controls} != {"T1", "T2", "T3", "T4", "T5"}:
        errors.append("trust-boundary controls T1-T5 are not complete")
    if contract.get("trust_boundary", {}).get("remote_default") != "deny":
        errors.append("remote default is not deny")
    required_flags = contract.get("runtime", {}).get("build", {}).get("required_flags", [])
    if "-no-shell-escape" not in required_flags:
        errors.append("build contract omits -no-shell-escape")
    inference_runtime = contract.get("runtime", {}).get("inference", {}).get("runtime")
    # Accept either llama.cpp (v1.0) or API (v1.1+)
    if inference_runtime not in ("llama.cpp", "API (Claude or OpenAI)"):
        errors.append("inference runtime is not llama.cpp or API")

    envelope = contract.get("operating_envelope", {})
    positive_integer_fields = (
        "max_rendered_pages",
        "max_protected_objects",
        "deterministic_preflight_minutes",
        "model_assisted_preflight_minutes",
        "max_repair_cycles_per_unit",
    )
    for field in positive_integer_fields:
        if not isinstance(envelope.get(field), int) or envelope[field] <= 0:
            errors.append(f"operating envelope field is not a positive integer: {field}")
    if envelope.get("max_repair_cycles_per_unit") != 3:
        errors.append("repair cycle cap is not three")

    cli = contract.get("cli", {})
    if set(cli.get("exit_codes", {})) != {"0", "1", "2", "3", "4", "5"}:
        errors.append("CLI exit codes 0-5 are not complete")
    expected_commands = {
        "hv init",
        "hv plan",
        "hv draft",
        "hv preflight",
        "hv repair",
        "hv release",
    }
    if set(cli.get("commands", [])) != expected_commands:
        errors.append("CLI command surface is not complete")

    if contract.get("release_authority", {}).get("never_except") is None:
        errors.append("release authority has no never-except list")
    roles = set(contract.get("staffed_roles", []))
    for role in (
        "security or policy owner",
        "domain editor and writing reviewer",
        "evaluation lead",
        "product engineer",
    ):
        if role not in roles:
            errors.append(f"staffed role missing: {role}")
    work_packages = contract.get("work_packages", [])
    if len(work_packages) != 6 or [row.get("id") for row in work_packages] != [f"WP{i}" for i in range(1, 7)]:
        errors.append("work-package definition of done is incomplete")
    pre_authorization = contract.get("pre_authorization_package", {})
    if pre_authorization.get("id") != "WP0" or pre_authorization.get("exit") != "G0 decision record":
        errors.append("WP0 pre-authorization package is not recorded")

    try:
        requirements = load_json(requirements_path)
        requirement_rows = requirements.get("requirements", [])
        ids = [row.get("id") for row in requirement_rows]
        if requirements.get("requirement_count") != 24 or ids != [f"R{i}" for i in range(1, 25)]:
            errors.append("machine-readable requirements are not the canonical R1-R24 register")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"requirements cannot be loaded: {exc}")

    try:
        rights = load_json(rights_path)
        statuses = set(contract.get("corpus_rights", {}).get("allowed_statuses", []))
        items = rights.get("items", [])
        if not items:
            errors.append("rights manifest is empty")
        corpus_schema = schemas.get("corpus-item.schema.json")
        corpus_validator = None
        if corpus_schema and Draft202012Validator is not None and FormatChecker is not None:
            corpus_validator = Draft202012Validator(
                corpus_schema, format_checker=FormatChecker()
            )
        for item in items:
            record_id = item.get("record_id", "?")
            if item.get("redistribution_status") not in statuses:
                errors.append(f"rights item {record_id} has unknown status")
            if corpus_validator is not None:
                item_errors = list(corpus_validator.iter_errors(item))
                if item_errors:
                    errors.append(f"rights item {record_id} fails its schema: {item_errors[0].message}")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"rights manifest cannot be loaded: {exc}")

    try:
        manuscript = manuscript_path.read_text(encoding="utf-8")
        if "\\input{proposal/21_implementation_contract}" not in manuscript:
            errors.append("canonical manuscript does not include the implementation contract")
        annex = (root / "docs/survey/proposal/21_implementation_contract.tex").read_text(
            encoding="utf-8"
        )
        if "\\label{app:implementation-contract}" not in annex or "Exit & Meaning" not in annex:
            errors.append("normative annex is incomplete")
        if re.search(r"\bAC(?:[1-9]|1[0-8])\b", annex):
            errors.append("normative annex still uses legacy AC identifiers")
    except OSError as exc:
        errors.append(f"normative manuscript artifacts cannot be read: {exc}")

    return {"contract_valid": not errors, "errors": errors}


def main() -> int:
    result = validate_contract()
    if result["contract_valid"]:
        print("PASS implementation_contract")
        print("PASS record_schema_contract_alignment")
        print("PASS schema_instances_and_negative_examples")
        print("PASS rights_manifest_instances")
        print("PASS cli_and_runtime_contract")
        print("PASS staffed_roles_and_definition_of_done")
        return 0
    for error in result["errors"]:
        print(f"FAIL {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
