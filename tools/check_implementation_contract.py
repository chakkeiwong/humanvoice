#!/usr/bin/env python3
"""Validate the v2 implementation contract, catalogue, schemas, and fixtures."""

from __future__ import annotations

import json
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Mapping

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import SchemaError
except ImportError:  # pragma: no cover
    Draft202012Validator = None
    FormatChecker = None
    SchemaError = Exception

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from humanvoice.schemas import SchemaRegistry
except ImportError:  # pragma: no cover
    SchemaRegistry = None

REFERENCE_VALIDATOR_VERSION = "4.26.0"
CONTRACT_ID = "HV-IC-2026-09-11"
CONTRACT_VERSION = "2.0.0"
CATALOG_ID = "HV-RECORD-CATALOG-2026-09-11"
COMMON_RECORD_FIELDS = {
    "record_type", "schema_version", "record_id", "run_id", "created_at"
}
EXPECTED_EVIDENCE_STATES = [
    "specified", "implemented", "test-verified",
    "independently-reproduced", "human-evidenced",
]
EXPECTED_PHASES = {
    "hv init", "hv inventory", "hv plan", "hv rewrite",
    "hv preflight", "hv repair", "hv assemble", "hv release",
}
EXPECTED_REQUIREMENTS = [f"R{index}" for index in range(1, 30)]
EXPECTED_CURRENT_RECORDS = {
    "HumanizationBrief", "SourceSnapshot", "SourceSpan", "SourceConcept",
    "ConceptBaseline", "ConceptDependency", "ExplanationObligation",
    "ScaffoldingDisposition", "RewriteUnit", "ConceptDisposition",
    "ConceptCorrespondence", "SemanticPreflightResult", "ProtectedManifest",
    "Finding", "Revision", "RuntimeManifest", "CliResult", "ReleaseDecision",
    "ReaderDecision", "EvidenceItem", "CorpusItem",
}
EXPECTED_LEGACY_RECORDS = {"AuthoringBrief", "ArgumentBlueprint", "PreflightRun"}
REQUIRED_SEMANTIC_RECORDS = {
    "HumanizationBrief", "SourceSpan", "SourceConcept", "ConceptBaseline",
    "ConceptDependency", "ExplanationObligation", "ScaffoldingDisposition",
    "RewriteUnit", "ConceptDisposition", "ConceptCorrespondence",
    "SemanticPreflightResult",
}
PERMITTED_OPERATIONS = {"retain", "paraphrase", "expand", "merge", "split", "reorder"}
REQUIRED_BUNDLE_CHECKS = {
    "names missing concept",
    "lacks reverse link to scaffolding",
    "lack an accepted rewrite disposition",
    "names unknown protected object",
    "bytes",
    "candidate_hash does not match revision",
}
REQUIRED_NEVER_EXCEPT_TERMS = {
    "unfrozen or incomplete concept baseline",
    "concept correspondence below exactly 1.0",
    "unmet active explanation obligation",
    "unauthorized external transmission",
    "invalid policy or runtime manifest",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _catalogue_entries(catalogue: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = catalogue.get("records", [])
    return [row for row in rows if isinstance(row, Mapping)]


def _load_catalogue_schemas(
    root: Path,
    catalogue: Mapping[str, Any],
    errors: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    schemas: dict[str, dict[str, Any]] = {}
    record_types: dict[str, str] = {}
    paths: set[str] = set()
    for row in _catalogue_entries(catalogue):
        record_type = row.get("record_type")
        schema_path = row.get("schema_path")
        status = row.get("schema_status")
        if not isinstance(record_type, str) or not record_type:
            errors.append("catalogue row has no record_type")
            continue
        if record_type in record_types:
            errors.append(f"catalogue has duplicate record type: {record_type}")
            continue
        if not isinstance(schema_path, str) or not schema_path:
            errors.append(f"catalogue record {record_type} has no schema path")
            continue
        if schema_path in paths:
            errors.append(f"catalogue reuses schema path: {schema_path}")
        paths.add(schema_path)
        path = root / schema_path
        if not path.is_file():
            errors.append(f"catalogue schema is missing: {schema_path}")
            continue
        try:
            schema = load_json(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{schema_path} cannot be loaded: {exc}")
            continue
        schemas[path.name] = schema
        record_types[record_type] = str(status)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"{schema_path} has wrong JSON Schema dialect")
        declared_type = schema.get("properties", {}).get("record_type", {}).get("const")
        if declared_type != record_type:
            errors.append(
                f"catalogue record {record_type} disagrees with schema type {declared_type}"
            )
        if Draft202012Validator is not None:
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                errors.append(f"{schema_path} is not valid Draft 2020-12: {exc.message}")
        required = set(schema.get("required", []))
        missing = COMMON_RECORD_FIELDS - required
        if missing:
            errors.append(
                f"{schema_path} omits common required fields: {', '.join(sorted(missing))}"
            )
        if schema.get("additionalProperties") is not False:
            errors.append(f"{schema_path} permits unknown top-level fields")
        if schema.get("properties", {}).get("extensions", {}).get("type") != "object":
            errors.append(f"{schema_path} has no extensions object")
        pattern = schema.get("properties", {}).get("schema_version", {}).get("pattern", "")
        if status == "present" and "HV-SCHEMA-2" not in pattern:
            errors.append(f"current schema is not restricted to major v2: {schema_path}")
    return schemas, record_types


def _validate_examples(
    root: Path,
    schemas: Mapping[str, Mapping[str, Any]],
    current_record_types: set[str],
    errors: list[str],
) -> None:
    manifest_path = root / "schemas/examples/manifest.json"
    if Draft202012Validator is None or FormatChecker is None or SchemaRegistry is None:
        errors.append("python-jsonschema or humanvoice.schemas is unavailable")
        return
    try:
        installed = version("jsonschema")
    except PackageNotFoundError:
        errors.append("python-jsonschema distribution metadata is missing")
        return
    if installed != REFERENCE_VALIDATOR_VERSION:
        errors.append(f"jsonschema version is {installed}; expected {REFERENCE_VALIDATOR_VERSION}")
    try:
        manifest = load_json(manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"schema example manifest cannot be loaded: {exc}")
        return

    schema_to_type = {
        name: schema.get("properties", {}).get("record_type", {}).get("const")
        for name, schema in schemas.items()
    }
    valid_coverage: set[str] = set()
    invalid_coverage: set[str] = set()
    valid_bundles = 0
    invalid_bundles = 0
    try:
        registry = SchemaRegistry(
            schema_root=root / "schemas",
            catalog_path=root / "schemas/record_catalog.json",
        )
    except Exception as exc:
        errors.append(f"shared schema registry cannot load: {exc}")
        return
    for row in manifest.get("examples", []):
        schema_name = row.get("schema")
        instance_name = row.get("instance")
        expected = row.get("expected")
        if schema_name not in schemas:
            errors.append(f"example {instance_name} names unknown schema {schema_name}")
            continue
        record_type = schema_to_type.get(str(schema_name))
        if record_type not in current_record_types:
            errors.append(f"v2 example manifest includes non-current record: {record_type}")
            continue
        path = root / "schemas/examples" / str(instance_name)
        try:
            instance = load_json(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"schema example {instance_name} cannot be loaded: {exc}")
            continue
        messages = registry.validate(instance, raise_on_error=False)
        if expected == "valid":
            if messages:
                errors.append(f"valid example {instance_name} failed: {messages[0]}")
            else:
                valid_coverage.add(str(record_type))
        elif expected == "invalid":
            if not messages:
                errors.append(f"invalid example {instance_name} unexpectedly passed")
            else:
                invalid_coverage.add(str(record_type))
                marker = row.get("expected_error_contains")
                if marker and not any(str(marker) in message for message in messages):
                    errors.append(
                        f"invalid example {instance_name} failed for wrong reason: "
                        + "; ".join(messages)
                    )
        else:
            errors.append(f"example {instance_name} has unknown expectation {expected}")

    for row in manifest.get("bundles", []):
        instance_name = row.get("instance")
        path = root / "schemas/examples" / str(instance_name)
        try:
            with path.open(encoding="utf-8") as handle:
                bundle = json.load(handle)
            if not isinstance(bundle, list):
                raise ValueError("bundle must be a JSON array")
            messages = registry.validate_bundle(bundle, raise_on_error=False)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"bundle example {instance_name} cannot be loaded: {exc}")
            continue
        expected = row.get("expected")
        if expected == "valid":
            if messages:
                errors.append(f"valid bundle {instance_name} failed: {messages[0]}")
            else:
                valid_bundles += 1
        elif expected == "invalid":
            if not messages:
                errors.append(f"invalid bundle {instance_name} unexpectedly passed")
                continue
            invalid_bundles += 1
            marker = row.get("expected_error_contains")
            if marker and not any(str(marker) in message for message in messages):
                errors.append(
                    f"invalid bundle {instance_name} failed for wrong reason: "
                    + "; ".join(messages)
                )
        else:
            errors.append(f"bundle {instance_name} has unknown expectation {expected}")

    if valid_bundles < 2:
        errors.append("v2 examples lack a baseline and a complete pipeline bundle")
    if invalid_bundles < len(REQUIRED_BUNDLE_CHECKS):
        errors.append(
            "cross-record bundle validation lacks adversarial coverage: "
            f"{invalid_bundles} of {len(REQUIRED_BUNDLE_CHECKS)} required cases"
        )
    covered_markers = {
        str(row.get("expected_error_contains"))
        for row in manifest.get("bundles", [])
        if row.get("expected") == "invalid"
    }
    missing_checks = sorted(REQUIRED_BUNDLE_CHECKS - covered_markers)
    if missing_checks:
        errors.append(
            "no adversarial bundle covers: " + ", ".join(missing_checks)
        )

    missing_valid = current_record_types - valid_coverage
    missing_invalid = current_record_types - invalid_coverage
    if missing_valid:
        errors.append("no valid example for: " + ", ".join(sorted(missing_valid)))
    if missing_invalid:
        errors.append("no invalid example for: " + ", ".join(sorted(missing_invalid)))


def _validate_contract_invariants(
    contract: Mapping[str, Any],
    schemas: Mapping[str, Mapping[str, Any]],
    record_status: Mapping[str, str],
    errors: list[str],
) -> None:
    if contract.get("contract_id") != CONTRACT_ID:
        errors.append("unexpected contract_id")
    if contract.get("contract_version") != CONTRACT_VERSION:
        errors.append("unexpected contract_version")
    if contract.get("status") != "specified":
        errors.append("v2 contract must report only specified at G0")
    if contract.get("evidence_states") != EXPECTED_EVIDENCE_STATES:
        errors.append("evidence state vocabulary or ordering is wrong")
    operation = contract.get("product_operation", {})
    if operation.get("primary") != "finished-manuscript humanization":
        errors.append("primary operation is not finished-manuscript humanization")
    if operation.get("production_entrypoint") != "hv humanize":
        errors.append("production entrypoint is not hv humanize")
    if operation.get("source") != "immutable" or operation.get("output") != "separate child revision":
        errors.append("source/output immutability contract is incomplete")
    if operation.get("required_concept_retention") != 1.0:
        errors.append("required concept retention is not exactly 1.0")
    if operation.get("length_objective") is not None:
        errors.append("v2 has a prose length objective")
    if operation.get("output_estimate_split_words") != 2000:
        errors.append("pre-call split guardrail is not 2,000 words")

    record_policy = contract.get("record_policy", {})
    semantic = set(record_policy.get("semantic_record_types", []))
    if semantic != REQUIRED_SEMANTIC_RECORDS:
        errors.append("semantic record family is incomplete")
    current = {name for name, status in record_status.items() if status == "present"}
    legacy = {name for name, status in record_status.items() if status == "legacy_v1"}
    if current != EXPECTED_CURRENT_RECORDS:
        errors.append("current catalogue record family is incomplete or has extras")
    if legacy != EXPECTED_LEGACY_RECORDS:
        errors.append("legacy_v1 catalogue boundary is wrong")
    if record_policy.get("major_migration") != "v1 records remain legacy_v1 and cannot satisfy v2 gates":
        errors.append("v1-to-v2 gate isolation is not explicit")

    concept = contract.get("concept_contract", {})
    if set(concept.get("correspondence_operations", [])) != PERMITTED_OPERATIONS:
        errors.append("concept operation set differs from the permitted v2 set")
    if concept.get("substantive_omission") != "forbidden":
        errors.append("substantive omission is not forbidden")
    if concept.get("uncertain_match") != "unresolved":
        errors.append("uncertain semantic matches are not unresolved")
    if concept.get("active_obligation_exception") != "forbidden":
        errors.append("active obligations can be exception-released")
    for schema_name in ("concept-disposition.schema.json", "concept-correspondence.schema.json"):
        schema_text = json.dumps(schemas.get(schema_name, {}))
        if '"omit"' in schema_text or '"omission"' in schema_text:
            errors.append(f"{schema_name} exposes an omission operation")

    cli = contract.get("cli", {})
    if cli.get("production_entrypoint") != "hv humanize":
        errors.append("CLI production entrypoint is wrong")
    if set(cli.get("resumable_phases", [])) != EXPECTED_PHASES:
        errors.append("CLI resumable phase surface is incomplete")
    if cli.get("legacy_namespace") != "hv legacy":
        errors.append("CLI legacy namespace is not explicit")
    if set(cli.get("exit_codes", {})) != {"0", "1", "2", "3", "4", "5"}:
        errors.append("CLI exit codes 0-5 are incomplete")
    controls = contract.get("trust_boundary", {}).get("controls", [])
    if {row.get("id") for row in controls if isinstance(row, Mapping)} != {"T1", "T2", "T3", "T4", "T5"}:
        errors.append("trust-boundary controls T1-T5 are incomplete")
    if contract.get("trust_boundary", {}).get("remote_default") != "deny":
        errors.append("remote inference default is not deny")
    if "-no-shell-escape" not in contract.get("runtime", {}).get("build", {}).get("required_flags", []):
        errors.append("build contract omits -no-shell-escape")
    if contract.get("runtime", {}).get("inference", {}).get("runtime") != "Anthropic Messages API":
        errors.append("inference runtime is not the pinned API family")

    controls_values = contract.get("operating_controls", {})
    for field in (
        "max_source_tree_mib", "max_rendered_pages", "max_protected_objects",
        "max_repair_cycles_per_unit", "model_timeout_seconds",
    ):
        if not isinstance(controls_values.get(field), int) or controls_values[field] <= 0:
            errors.append(f"operating control is not a positive integer: {field}")
    if controls_values.get("semantic_compression_from_limit") != "forbidden":
        errors.append("resource limits permit semantic compression")

    never_except = set(contract.get("release_authority", {}).get("never_except", []))
    if not REQUIRED_NEVER_EXCEPT_TERMS <= never_except:
        errors.append("release never-except semantic invariants are incomplete")
    if contract.get("release_authority", {}).get("promotion_authority") != "named human reader":
        errors.append("promotion authority is not a named human reader")
    migration = contract.get("migration", {})
    if migration.get("semantic_record_conversion") != "forbidden":
        errors.append("v1 semantic records can be auto-converted")
    if migration.get("v1_external_release") != "suspended":
        errors.append("v1 external release is not suspended")

    cli_schema = schemas.get("cli-result.schema.json", {})
    stable = set(cli.get("streams", {}).get("stable_stdout_fields", []))
    if not stable <= set(cli_schema.get("required", [])):
        errors.append("CliResult omits stable stdout fields")
    rights = set(contract.get("corpus_rights", {}).get("required_fields", []))
    if not rights <= set(schemas.get("corpus-item.schema.json", {}).get("required", [])):
        errors.append("CorpusItem omits contract rights fields")


def _validate_requirements(root: Path, errors: list[str]) -> None:
    try:
        requirements = load_json(root / "docs/survey/humanvoice_product_requirements.json")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"requirements cannot be loaded: {exc}")
        return
    rows = requirements.get("requirements", [])
    ids = [row.get("id") for row in rows if isinstance(row, Mapping)]
    if requirements.get("requirement_count") != 29 or ids != EXPECTED_REQUIREMENTS:
        errors.append("machine-readable requirements are not the canonical R1-R29 register")
    if requirements.get("register_version") != "2.0.0":
        errors.append("requirement register is not v2")
    for identifier in ("R25", "R26", "R27", "R28", "R29"):
        row = next((item for item in rows if item.get("id") == identifier), None)
        if not row or not row.get("acceptance_test") or not row.get("statement"):
            errors.append(f"{identifier} is incomplete")


def _validate_rights(root: Path, registry: Any, contract: Mapping[str, Any], errors: list[str]) -> None:
    try:
        manifest = load_json(root / "docs/survey/evidence/corpus_rights_manifest.json")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"rights manifest cannot be loaded: {exc}")
        return
    allowed = set(contract.get("corpus_rights", {}).get("allowed_statuses", []))
    items = manifest.get("items", [])
    if not items:
        errors.append("rights manifest is empty")
    for item in items:
        record_id = item.get("record_id", "?")
        if item.get("redistribution_status") not in allowed:
            errors.append(f"rights item {record_id} has unknown status")
        # Existing clearance records are historical v1 evidence. They remain
        # audit-readable but cannot themselves satisfy a v2 semantic gate.
        if item.get("schema_version", "").startswith("HV-SCHEMA-1."):
            continue
        messages = registry.validate(item, raise_on_error=False)
        if messages:
            errors.append(f"rights item {record_id} fails its schema: {messages[0]}")


def _validate_authority_paths(root: Path, contract: Mapping[str, Any], errors: list[str]) -> None:
    for label, relative in contract.get("authority", {}).items():
        if not isinstance(relative, str) or not (root / relative).is_file():
            errors.append(f"authority artifact is missing: {label}")
    try:
        manuscript = (root / "docs/survey/humanvoice_survey.tex").read_text(encoding="utf-8")
        annex = (root / "docs/survey/proposal/21_implementation_contract.tex").read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"normative manuscript artifacts cannot be read: {exc}")
        return
    if "\\input{proposal/21_implementation_contract}" not in manuscript:
        errors.append("canonical manuscript does not include the implementation contract")
    if "\\label{app:implementation-contract}" not in annex:
        errors.append("normative annex has no stable label")
    if re.search(r"\bAC(?:[1-9]|1[0-8])\b", annex):
        errors.append("normative annex still uses legacy AC identifiers")
    _validate_authority_language(root, errors)


# Reader-facing authority prose must describe the v2 product. Each pattern
# names a v1 commitment that the machine-readable contract now contradicts:
# greenfield brief-first drafting, a bounded no-deployment MVP, optional
# revision, or a per-unit prose budget.
SUPERSEDED_AUTHORITY_LANGUAGE: tuple[tuple[str, str], ...] = (
    (r"bounded\s+(?:twelve-week\s+)?MVP", "bounded-MVP framing"),
    (r"\bMVP\s+(?:cap|caps|is\s+complete|does\s+not|deliberately\s+excludes)", "MVP scope framing"),
    (r"not\s+fund\s+deployment|Do\s+not\s+authorize\s+deployment", "no-deployment framing"),
    (r"turns?\s+a\s+(?:reader|complete\s+authoring)\s+brief\s+into", "brief-first product framing"),
    (r"starts\s+with\s+a\s+brief\s+and\s+evidence", "brief-first product framing"),
    (r"argument\s+blueprint", "argument-blueprint pipeline"),
    (r"optional\s+authoring\s+extension|Authoring\s+extension\s*&", "optional-authoring-extension framing"),
    (r"at\s+most\s+2,000\s+tokens|Output\s+tokens\s+per\s+section", "per-unit output budget"),
    (r"schemas/authoring-brief\.schema\.json", "superseded schema path"),
    (r"\bsix\s+commands\b", "superseded command surface"),
)
AUTHORITY_PROSE_FILES = (
    "docs/survey/humanvoice_survey.tex",
    "docs/survey/proposal/00_orientation.tex",
    "docs/survey/proposal/03_product.tex",
    "docs/survey/proposal/06_design.tex",
    "docs/survey/proposal/16_architecture.tex",
    "docs/survey/proposal/21_implementation_contract.tex",
)
REQUIRED_AUTHORITY_TERMS = (
    (r"finished(?:\s|-)manuscript", "the finished-manuscript operation"),
    (r"hv\s+humanize|humaniz", "the humanization entry point"),
)


def _validate_authority_language(root: Path, errors: list[str]) -> None:
    for relative in AUTHORITY_PROSE_FILES:
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"authority prose cannot be read: {relative}: {exc}")
            continue
        for pattern, label in SUPERSEDED_AUTHORITY_LANGUAGE:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                # A mention that explicitly labels the construct legacy or
                # superseded is historical context, not a current commitment.
                window = text[max(0, match.start() - 200):match.end() + 200]
                if re.search(
                    r"legacy|superseded|historical|\bv1\b|cannot satisfy",
                    window,
                    flags=re.IGNORECASE,
                ):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{relative}:{line} still asserts {label}: {match.group(0)!r}"
                )
    product_files = (
        "docs/survey/humanvoice_survey.tex",
        "docs/survey/proposal/03_product.tex",
    )
    for relative in product_files:
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            continue
        for pattern, label in REQUIRED_AUTHORITY_TERMS:
            if not re.search(pattern, text, flags=re.IGNORECASE):
                errors.append(f"{relative} does not state {label}")


def validate_contract(root: Path = ROOT) -> dict[str, object]:
    errors: list[str] = []
    try:
        contract = load_json(root / "schemas/implementation_contract.json")
        catalogue = load_json(root / "schemas/record_catalog.json")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"contract_valid": False, "errors": [f"contract/catalogue cannot be loaded: {exc}"]}

    if catalogue.get("catalog_id") != CATALOG_ID:
        errors.append("unexpected catalogue ID")
    if catalogue.get("catalog_version") != CONTRACT_VERSION:
        errors.append("unexpected catalogue version")
    if catalogue.get("contract_id") != contract.get("contract_id") or catalogue.get("contract_version") != contract.get("contract_version"):
        errors.append("catalogue identity disagrees with implementation contract")
    if catalogue.get("status") != "specified":
        errors.append("catalogue must report specified at G0")
    if catalogue.get("compatibility_policy", {}).get("legacy_v1") != "readable for audit only; cannot satisfy a v2 gate":
        errors.append("catalogue does not isolate legacy_v1 evidence")
    schemas, statuses = _load_catalogue_schemas(root, catalogue, errors)
    _validate_contract_invariants(contract, schemas, statuses, errors)
    _validate_requirements(root, errors)

    if SchemaRegistry is None:
        errors.append("shared schema registry cannot be imported")
    else:
        try:
            registry = SchemaRegistry(
                schema_root=root / "schemas",
                catalog_path=root / "schemas/record_catalog.json",
            )
            _validate_rights(root, registry, contract, errors)
        except Exception as exc:
            errors.append(f"shared schema registry cannot load: {exc}")
    current = {name for name, status in statuses.items() if status == "present"}
    _validate_examples(root, schemas, current, errors)
    _validate_authority_paths(root, contract, errors)

    requirements_dev = root / "requirements-dev.txt"
    try:
        if "jsonschema==4.26.0" not in requirements_dev.read_text(encoding="utf-8"):
            errors.append("requirements-dev.txt does not pin jsonschema==4.26.0")
    except OSError as exc:
        errors.append(f"requirements-dev.txt cannot be read: {exc}")

    return {
        "contract_valid": not errors,
        "errors": errors,
        "current_record_count": len(current),
        "legacy_record_count": len({name for name, status in statuses.items() if status == "legacy_v1"}),
        "evidence_state": contract.get("status"),
    }


def main() -> int:
    result = validate_contract()
    if result["contract_valid"]:
        print("PASS implementation_contract_v2")
        print("PASS catalogue_and_schema_alignment")
        print("PASS shared_registry_and_semantic_examples")
        print("PASS R1-R29_requirement_register")
        print("PASS v1_v2_migration_boundary")
        print("PASS release_and_runtime_invariants")
        print("STATE specified")
        return 0
    for error in result["errors"]:
        print(f"FAIL {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
