"""Shared schema registry and semantic validation for Humanvoice records."""

from __future__ import annotations

import json
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = PROJECT_ROOT / "schemas"
CATALOG_PATH = SCHEMA_ROOT / "record_catalog.json"
LEGACY_STATUS = "legacy_v1"


class RecordValidationError(ValueError):
    """A record failed its schema or semantic contract."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for hashes and manifests."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def baseline_manifest_hash(record: Mapping[str, Any]) -> str:
    """Hash a baseline manifest without its self-referential digest field."""
    payload = dict(record)
    payload.pop("baseline_hash", None)
    return canonical_hash(payload)


def concept_identity_basis(snapshot_hash: str, span_ids: Sequence[str]) -> dict[str, str]:
    """Derive concept identity from immutable source identity, never wording."""
    ordered_span_ids_hash = canonical_hash(list(span_ids))
    identity_hash = canonical_hash(
        {
            "snapshot_hash": snapshot_hash,
            "ordered_span_ids_hash": ordered_span_ids_hash,
        }
    )
    return {
        "snapshot_hash": snapshot_hash,
        "ordered_span_ids_hash": ordered_span_ids_hash,
        "identity_hash": identity_hash,
    }


def obligation_spec_hash(record: Mapping[str, Any]) -> str:
    """Hash the frozen teaching requirement, excluding later fulfillment."""
    keys = (
        "baseline_id",
        "obligation_id",
        "concept_id",
        "required_teaching_functions",
        "source_assessment",
        "reader_rationale",
        "genre_rationale",
        "active",
        "deactivation",
    )
    return canonical_hash({key: record.get(key) for key in keys})


def rewrite_unit_spec_hash(record: Mapping[str, Any]) -> str:
    """Hash the accepted rewrite assignment, excluding execution state."""
    keys = (
        "plan_id",
        "baseline_id",
        "baseline_hash",
        "unit_id",
        "source_file",
        "source_span_ids",
        "source_hash",
        "contiguous",
        "concept_ids",
        "dependency_ids",
        "explanation_obligation_ids",
        "protected_object_ids",
        "neighbor_context",
        "planned_operation",
        "estimated_output_words",
        "segmentation_triggered",
        "parent_unit_id",
        "child_unit_ids",
        "continuation_state",
    )
    return canonical_hash({key: record.get(key) for key in keys})


class SchemaRegistry:
    """Load the catalogue once and expose its schemas by record type or path."""

    def __init__(
        self,
        schema_root: Path = SCHEMA_ROOT,
        catalog_path: Path = CATALOG_PATH,
    ) -> None:
        self.schema_root = schema_root
        self.catalog_path = catalog_path
        self.catalog = _load_json(catalog_path)
        self._entries: dict[str, dict[str, Any]] = {}
        self._schemas: dict[str, dict[str, Any]] = {}
        self._validators: dict[str, Draft202012Validator] = {}
        for entry in self.catalog.get("records", []):
            record_type = entry.get("record_type")
            if not isinstance(record_type, str) or not record_type:
                continue
            if record_type in self._entries:
                raise ValueError(f"duplicate record_type in catalogue: {record_type}")
            self._entries[record_type] = entry

    @property
    def current_record_types(self) -> set[str]:
        return {
            name
            for name, entry in self._entries.items()
            if entry.get("schema_status") != LEGACY_STATUS
        }

    @property
    def legacy_record_types(self) -> set[str]:
        return {
            name
            for name, entry in self._entries.items()
            if entry.get("schema_status") == LEGACY_STATUS
        }

    def entry(self, record_type: str) -> Mapping[str, Any]:
        try:
            return self._entries[record_type]
        except KeyError as exc:
            raise KeyError(f"unknown record type: {record_type}") from exc

    def schema_path(self, record_type: str) -> Path:
        raw_path = self.entry(record_type).get("schema_path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError(f"{record_type} has no schema_path")
        path = Path(raw_path)
        if path.is_absolute():
            return path
        if path.parts and path.parts[0] == "schemas":
            return self.schema_root.joinpath(*path.parts[1:])
        return self.schema_root / path

    def schema(self, record_type: str) -> Mapping[str, Any]:
        if record_type not in self._schemas:
            schema = _load_json(self.schema_path(record_type))
            Draft202012Validator.check_schema(schema)
            declared = (
                schema.get("properties", {})
                .get("record_type", {})
                .get("const")
            )
            if declared != record_type:
                raise ValueError(
                    f"catalogue record type {record_type} does not match schema {declared}"
                )
            self._schemas[record_type] = schema
        return self._schemas[record_type]

    def validator(self, record_type: str) -> Draft202012Validator:
        if record_type not in self._validators:
            self._validators[record_type] = Draft202012Validator(
                self.schema(record_type), format_checker=FormatChecker()
            )
        return self._validators[record_type]

    def validate(
        self,
        record: Mapping[str, Any],
        *,
        record_type: str | None = None,
        allow_legacy: bool = False,
        raise_on_error: bool = True,
    ) -> list[str]:
        """Validate one record against its on-disk schema.

        `record_type`, when given, is the type the caller *expected*. It is
        checked against the record's own `record_type` rather than replacing
        it. This matters for model output: a response that declares a
        different record type than the one requested is not a valid record of
        the requested type, and silently validating it against whichever schema
        it names would let a model choose its own contract.
        """
        declared = record.get("record_type")
        if record_type is not None and declared != record_type:
            errors = [
                f"expected record_type {record_type}, got {declared!r}"
            ]
            if raise_on_error:
                raise RecordValidationError(errors)
            return errors
        record_type = declared
        if not isinstance(record_type, str) or not record_type:
            errors = ["record_type is required"]
        elif record_type not in self._entries:
            errors = [f"unknown record_type: {record_type}"]
        elif record_type in self.legacy_record_types and not allow_legacy:
            errors = [f"legacy_v1 record cannot satisfy a v2 validation: {record_type}"]
        else:
            errors = [
                _format_schema_error(error)
                for error in sorted(
                    self.validator(record_type).iter_errors(record),
                    key=lambda item: (list(item.absolute_path), item.message),
                )
            ]
            errors.extend(_record_semantic_errors(record))
        if errors and raise_on_error:
            raise RecordValidationError(errors)
        return errors

    def validate_bundle(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        raise_on_error: bool = True,
    ) -> list[str]:
        materialized = list(records)
        errors: list[str] = []
        for index, record in enumerate(materialized):
            errors.extend(
                f"record[{index}]: {message}"
                for message in self.validate(record, raise_on_error=False)
            )
        if not errors:
            errors.extend(_bundle_semantic_errors(materialized))
        if errors and raise_on_error:
            raise RecordValidationError(errors)
        return errors


_DEFAULT_REGISTRY: SchemaRegistry | None = None


def get_registry() -> SchemaRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = SchemaRegistry()
    return _DEFAULT_REGISTRY


def load_schema(record_type: str) -> Mapping[str, Any]:
    """Return an on-disk schema from the canonical catalogue."""
    return get_registry().schema(record_type)


def validate_record(
    record: Mapping[str, Any], *, allow_legacy: bool = False
) -> None:
    """Validate one current record and raise RecordValidationError on failure."""
    get_registry().validate(record, allow_legacy=allow_legacy)


def validate_record_bundle(records: Iterable[Mapping[str, Any]]) -> None:
    """Validate records and the semantic links between them."""
    get_registry().validate_bundle(records)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _format_schema_error(error: Any) -> str:
    location = ".".join(str(part) for part in error.absolute_path) or "$"
    return f"{location}: {error.message}"


def _record_semantic_errors(record: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    record_type = record.get("record_type")

    if record_type == "SourceSpan":
        _check_range(record, "byte_start", "byte_end", errors)
        start = record.get("line_start")
        end = record.get("line_end")
        if isinstance(start, int) and isinstance(end, int) and end < start:
            errors.append("line_end must be greater than or equal to line_start")
    elif record_type == "ConceptDependency":
        if record.get("prerequisite_concept_id") == record.get("dependent_concept_id"):
            errors.append("a concept cannot depend on itself")
    elif record_type == "SourceConcept":
        expected = concept_identity_basis(
            str(record.get("identity_basis", {}).get("snapshot_hash", "")),
            record.get("source_span_ids", []),
        )
        if record.get("identity_basis") != expected:
            errors.append("identity_basis does not match snapshot hash and source spans")
        occurrences = {
            row.get("span_id")
            for row in record.get("occurrences", [])
            if isinstance(row, Mapping)
        }
        missing = set(record.get("source_span_ids", [])) - occurrences
        if missing:
            errors.append("source concept has spans without occurrences: " + ", ".join(sorted(missing)))
    elif record_type == "ExplanationObligation":
        if record.get("obligation_spec_hash") != obligation_spec_hash(record):
            errors.append("obligation_spec_hash does not match frozen obligation fields")
        for index, evidence in enumerate(record.get("fulfillment_evidence", [])):
            if isinstance(evidence, Mapping):
                _check_range(
                    evidence,
                    "byte_start",
                    "byte_end",
                    errors,
                    prefix=f"fulfillment_evidence[{index}].",
                )
        if record.get("fulfillment_status") == "fulfilled":
            required = set(record.get("required_teaching_functions", []))
            supported = {
                row.get("teaching_function")
                for row in record.get("fulfillment_evidence", [])
                if isinstance(row, Mapping) and row.get("verdict") == "supported"
            }
            missing = sorted(required - supported)
            if missing:
                errors.append(
                    "fulfilled obligation lacks supported evidence for: "
                    + ", ".join(missing)
                )
    elif record_type == "ConceptCorrespondence":
        for index, span in enumerate(record.get("output_spans", [])):
            if isinstance(span, Mapping):
                _check_range(
                    span,
                    "byte_start",
                    "byte_end",
                    errors,
                    prefix=f"output_spans[{index}].",
                )
    elif record_type == "RewriteUnit":
        if record.get("unit_spec_hash") != rewrite_unit_spec_hash(record):
            errors.append("unit_spec_hash does not match rewrite-unit specification")
    elif record_type == "Revision":
        _check_patch_ranges(record, errors)
    elif record_type == "SemanticPreflightResult":
        coverage = record.get("concept_coverage", {})
        if isinstance(coverage, Mapping):
            frozen = coverage.get("frozen_concept_count")
            supported = coverage.get("supported_concept_count")
            retention = coverage.get("retention")
            if isinstance(frozen, int) and isinstance(supported, int):
                expected = supported / frozen if frozen else None
                if expected is not None and (
                    not isinstance(retention, (int, float))
                    or abs(float(retention) - expected) > 1e-12
                ):
                    errors.append(
                        "concept_coverage.retention must equal "
                        "supported_concept_count / frozen_concept_count"
                    )
                if record.get("status") == "pass" and supported != frozen:
                    errors.append("passing preflight requires every frozen concept supported")
    return errors


def _check_range(
    value: Mapping[str, Any],
    start_name: str,
    end_name: str,
    errors: list[str],
    *,
    prefix: str = "",
) -> None:
    start = value.get(start_name)
    end = value.get(end_name)
    if isinstance(start, int) and isinstance(end, int) and end <= start:
        errors.append(f"{prefix}{end_name} must be greater than {start_name}")


def _check_patch_ranges(record: Mapping[str, Any], errors: list[str]) -> None:
    patches_by_file: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for index, patch in enumerate(record.get("patches", [])):
        if not isinstance(patch, Mapping):
            continue
        _check_range(
            patch,
            "byte_start",
            "byte_end",
            errors,
            prefix=f"patches[{index}].",
        )
        path = patch.get("source_file")
        start = patch.get("byte_start")
        end = patch.get("byte_end")
        patch_id = patch.get("patch_id", str(index))
        if isinstance(path, str) and isinstance(start, int) and isinstance(end, int):
            patches_by_file[path].append((start, end, str(patch_id)))
    for path, spans in patches_by_file.items():
        previous: tuple[int, int, str] | None = None
        for current in sorted(spans):
            if previous is not None and current[0] < previous[1]:
                errors.append(
                    f"patches overlap in {path}: {previous[2]} and {current[2]}"
                )
            if previous is None or current[1] > previous[1]:
                previous = current


def _bundle_semantic_errors(records: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    by_type: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_record_id: dict[str, Mapping[str, Any]] = {}
    for record in records:
        record_type = record.get("record_type")
        if isinstance(record_type, str):
            by_type[record_type].append(record)
        record_id = record.get("record_id")
        if isinstance(record_id, str):
            if record_id in by_record_id:
                errors.append(f"duplicate record_id: {record_id}")
            by_record_id[record_id] = record

    baselines = by_type.get("ConceptBaseline", [])
    for baseline in baselines:
        errors.extend(_baseline_errors(baseline, by_record_id, by_type))
    errors.extend(_dependency_errors(by_type.get("ConceptDependency", [])))
    errors.extend(_concept_link_errors(by_type))
    errors.extend(_dependency_link_errors(by_type))
    errors.extend(_scaffolding_link_errors(by_type))
    errors.extend(_rewrite_unit_link_errors(by_type))
    errors.extend(_disposition_link_errors(by_type))
    errors.extend(_protected_link_errors(by_type))
    errors.extend(_snapshot_coverage_errors(by_type))
    errors.extend(_correspondence_bundle_errors(by_type))
    return errors


def _index(
    by_type: Mapping[str, Sequence[Mapping[str, Any]]],
    record_type: str,
    key: str,
) -> dict[str, Mapping[str, Any]]:
    """Index one record type by its stable semantic identifier."""
    return {
        row[key]: row
        for row in by_type.get(record_type, [])
        if isinstance(row.get(key), str)
    }


def _dependency_link_errors(
    by_type: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    """Reject dependency endpoints that name concepts absent from the bundle."""
    concepts = _index(by_type, "SourceConcept", "concept_id")
    if not concepts:
        return []
    errors: list[str] = []
    for dependency in by_type.get("ConceptDependency", []):
        dependency_id = dependency.get("dependency_id", dependency.get("record_id"))
        for field in ("prerequisite_concept_id", "dependent_concept_id"):
            concept_id = dependency.get(field)
            if isinstance(concept_id, str) and concept_id not in concepts:
                errors.append(
                    f"dependency {dependency_id} names missing concept in {field}: {concept_id}"
                )
    return errors


def _scaffolding_link_errors(
    by_type: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    """Require resolvable spans, reverse links, and embedded-concept extraction."""
    spans = _index(by_type, "SourceSpan", "record_id")
    concepts = _index(by_type, "SourceConcept", "concept_id")
    errors: list[str] = []
    for disposition in by_type.get("ScaffoldingDisposition", []):
        disposition_id = disposition.get("disposition_id")
        for span_id in disposition.get("source_span_ids", []):
            if not spans:
                continue
            span = spans.get(span_id)
            if span is None:
                errors.append(
                    f"scaffolding {disposition_id} names missing source span {span_id}"
                )
            elif disposition_id not in span.get("scaffolding_disposition_ids", []):
                errors.append(
                    f"source span {span_id} lacks reverse link to scaffolding {disposition_id}"
                )
        if concepts:
            for concept_id in disposition.get("embedded_concept_ids", []):
                if concept_id not in concepts:
                    errors.append(
                        f"scaffolding {disposition_id} names missing embedded concept {concept_id}"
                    )
    return errors


def _baseline_errors(
    baseline: Mapping[str, Any],
    by_record_id: Mapping[str, Mapping[str, Any]],
    by_type: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    if not baseline.get("frozen"):
        return []
    errors: list[str] = []
    snapshot = next(
        (
            row
            for row in by_type.get("SourceSnapshot", [])
            if row.get("snapshot_id") == baseline.get("snapshot_id")
        ),
        None,
    )
    if snapshot is None:
        errors.append("frozen baseline has no matching SourceSnapshot")
    else:
        if snapshot.get("source_hash") != baseline.get("source_hash"):
            errors.append("baseline source_hash does not match SourceSnapshot")
        if snapshot.get("humanization_brief_id") != baseline.get("humanization_brief_id"):
            errors.append("baseline brief ID does not match SourceSnapshot")
        if snapshot.get("humanization_brief_hash") != baseline.get("humanization_brief_hash"):
            errors.append("baseline brief hash does not match SourceSnapshot")
    brief = by_record_id.get(str(baseline.get("humanization_brief_id")))
    if brief is None or brief.get("record_type") != "HumanizationBrief":
        errors.append("frozen baseline has no matching HumanizationBrief")
    elif canonical_hash(brief) != baseline.get("humanization_brief_hash"):
        errors.append("baseline humanization_brief_hash does not match brief record")
    expected_types = {
        "source_spans": "SourceSpan",
        "source_concepts": "SourceConcept",
        "concept_dependencies": "ConceptDependency",
        "explanation_obligations": "ExplanationObligation",
        "scaffolding_dispositions": "ScaffoldingDisposition",
    }
    components = baseline.get("component_records", {})
    hashes = baseline.get("component_hashes", {})
    counts = baseline.get("component_counts", {})
    resolved: dict[str, list[Mapping[str, Any]]] = {}
    for group, expected_type in expected_types.items():
        ids = components.get(group, []) if isinstance(components, Mapping) else []
        rows: list[Mapping[str, Any]] = []
        for record_id in ids:
            row = by_record_id.get(record_id)
            if row is None:
                errors.append(f"frozen baseline references missing {group} record: {record_id}")
            elif row.get("record_type") != expected_type:
                errors.append(
                    f"baseline {group} record {record_id} is {row.get('record_type')}, "
                    f"expected {expected_type}"
                )
            else:
                rows.append(row)
        rows.sort(key=lambda row: str(row.get("record_id", "")))
        resolved[group] = rows
        expected_hash = hashes.get(group) if isinstance(hashes, Mapping) else None
        actual_hash = canonical_hash(rows)
        if expected_hash != actual_hash:
            errors.append(f"baseline component hash mismatch: {group}")

    expected_counts = {
        "source_spans": len(resolved["source_spans"]),
        "reader_facing_spans": sum(
            row.get("reader_facing") is True for row in resolved["source_spans"]
        ),
        "source_concepts": len(resolved["source_concepts"]),
        "concept_dependencies": len(resolved["concept_dependencies"]),
        "active_explanation_obligations": sum(
            row.get("active") is True for row in resolved["explanation_obligations"]
        ),
        "scaffolding_dispositions": len(resolved["scaffolding_dispositions"]),
    }
    for name, expected in expected_counts.items():
        if not isinstance(counts, Mapping) or counts.get(name) != expected:
            errors.append(f"baseline component count mismatch: {name}")

    span_lengths = sum(
        row["byte_end"] - row["byte_start"]
        for row in resolved["source_spans"]
        if isinstance(row.get("byte_start"), int)
        and isinstance(row.get("byte_end"), int)
        and row["byte_end"] > row["byte_start"]
    )
    partition = baseline.get("partition", {})
    if not isinstance(partition, Mapping) or partition.get("covered_bytes") != span_lengths:
        errors.append("baseline covered_bytes does not match source spans")
    if isinstance(snapshot, Mapping):
        source_bytes = snapshot.get("source_tree_bytes")
        if not isinstance(partition, Mapping) or partition.get("source_bytes") != source_bytes:
            errors.append("baseline source_bytes does not match SourceSnapshot")
        if span_lengths != source_bytes:
            errors.append("source span partition does not cover the complete source tree")
    errors.extend(_source_partition_errors(resolved["source_spans"]))

    baseline_id = baseline.get("baseline_id")
    snapshot_id = baseline.get("snapshot_id")
    for group, rows in resolved.items():
        for row in rows:
            row_baseline = row.get("baseline_id")
            if row_baseline is not None and row_baseline != baseline_id:
                errors.append(f"{row.get('record_id')} belongs to another baseline")
            row_snapshot = row.get("snapshot_id")
            if row_snapshot is not None and row_snapshot != snapshot_id:
                errors.append(f"{row.get('record_id')} belongs to another snapshot")
    errors.extend(_frozen_component_state_errors(resolved))
    if baseline.get("baseline_hash") != baseline_manifest_hash(baseline):
        errors.append("baseline_hash does not match canonical frozen manifest")
    return errors


def _source_partition_errors(spans: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    by_file: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for span in spans:
        path = span.get("source_file")
        start = span.get("byte_start")
        end = span.get("byte_end")
        if isinstance(path, str) and isinstance(start, int) and isinstance(end, int):
            by_file[path].append((start, end, str(span.get("record_id"))))
    for path, rows in by_file.items():
        ordered = sorted(rows)
        if ordered and ordered[0][0] != 0:
            errors.append(f"source partition for {path} does not start at byte zero")
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] < previous[1]:
                errors.append(f"source partition overlaps in {path}: {previous[2]} and {current[2]}")
            elif current[0] > previous[1]:
                errors.append(f"source partition gap in {path} after {previous[2]}")
    return errors


def _frozen_component_state_errors(
    components: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    errors: list[str] = []
    for span in components["source_spans"]:
        if span.get("reader_facing") and span.get("coverage_disposition") == "unresolved":
            errors.append(f"reader-facing span remains unresolved: {span.get('record_id')}")
    for concept in components["source_concepts"]:
        if concept.get("review_status") != "accepted":
            errors.append(f"concept is not accepted: {concept.get('record_id')}")
    for dependency in components["concept_dependencies"]:
        if dependency.get("review_status") != "accepted":
            errors.append(f"dependency is not accepted: {dependency.get('record_id')}")
    for obligation in components["explanation_obligations"]:
        if obligation.get("source_assessment", {}).get("status") == "unresolved":
            errors.append(f"obligation source assessment unresolved: {obligation.get('record_id')}")
        if obligation.get("fulfillment_status") != "unassessed":
            errors.append(
                f"frozen baseline obligation must be unassessed: {obligation.get('record_id')}"
            )
    for disposition in components["scaffolding_dispositions"]:
        if disposition.get("review_status") != "accepted":
            errors.append(f"scaffolding disposition is not accepted: {disposition.get('record_id')}")
    return errors


def _dependency_errors(dependencies: Sequence[Mapping[str, Any]]) -> list[str]:
    edges: dict[str, set[str]] = defaultdict(set)
    for dependency in dependencies:
        if dependency.get("review_status") != "accepted":
            continue
        if dependency.get("relation") not in {"prerequisite", "sequence"}:
            continue
        before = dependency.get("prerequisite_concept_id")
        after = dependency.get("dependent_concept_id")
        if isinstance(before, str) and isinstance(after, str):
            edges[before].add(after)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in visiting:
            cycle_start = path.index(node) if node in path else 0
            errors.append("dependency cycle: " + " -> ".join(path[cycle_start:] + [node]))
            return
        if node in visited:
            return
        visiting.add(node)
        for child in sorted(edges.get(node, set())):
            visit(child, path + [node])
        visiting.remove(node)
        visited.add(node)

    errors: list[str] = []
    for node in sorted(edges):
        visit(node, [])
    return errors


def _concept_link_errors(
    by_type: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    errors: list[str] = []
    spans = {
        row.get("record_id"): row
        for row in by_type.get("SourceSpan", [])
        if isinstance(row.get("record_id"), str)
    }
    concepts = {
        row.get("concept_id"): row
        for row in by_type.get("SourceConcept", [])
        if isinstance(row.get("concept_id"), str)
    }
    obligations = {
        row.get("obligation_id"): row
        for row in by_type.get("ExplanationObligation", [])
        if isinstance(row.get("obligation_id"), str)
    }
    for concept_id, concept in concepts.items():
        for span_id in concept.get("source_span_ids", []):
            span = spans.get(span_id)
            if span is None:
                errors.append(f"concept {concept_id} links missing source span {span_id}")
            elif concept_id not in span.get("concept_ids", []):
                errors.append(f"source span {span_id} lacks reverse link to concept {concept_id}")
        for obligation_id in concept.get("explanation_obligation_ids", []):
            obligation = obligations.get(obligation_id)
            if obligation is None:
                errors.append(f"concept {concept_id} links missing obligation {obligation_id}")
            elif obligation.get("concept_id") != concept_id:
                errors.append(f"obligation {obligation_id} links another concept")
    for span_id, span in spans.items():
        for concept_id in span.get("concept_ids", []):
            concept = concepts.get(concept_id)
            if concept is None:
                errors.append(f"source span {span_id} links missing concept {concept_id}")
            elif span_id not in concept.get("source_span_ids", []):
                errors.append(f"concept {concept_id} lacks reverse link to span {span_id}")
    return errors


def _rewrite_unit_link_errors(
    by_type: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    """Bind every planned unit to real spans, concepts, obligations, dependencies."""
    units = by_type.get("RewriteUnit", [])
    if not units:
        return []
    spans = _index(by_type, "SourceSpan", "record_id")
    concepts = _index(by_type, "SourceConcept", "concept_id")
    obligations = _index(by_type, "ExplanationObligation", "obligation_id")
    dependencies = _index(by_type, "ConceptDependency", "dependency_id")
    unit_ids = {row.get("unit_id") for row in units if isinstance(row.get("unit_id"), str)}
    errors: list[str] = []
    for unit in units:
        unit_id = unit.get("unit_id")
        for span_id in unit.get("source_span_ids", []):
            if not spans:
                continue
            span = spans.get(span_id)
            if span is None:
                errors.append(f"rewrite unit {unit_id} names missing source span {span_id}")
            elif span.get("source_file") != unit.get("source_file"):
                errors.append(
                    f"rewrite unit {unit_id} span {span_id} belongs to another source file"
                )
        if concepts:
            for concept_id in unit.get("concept_ids", []):
                if concept_id not in concepts:
                    errors.append(f"rewrite unit {unit_id} names missing concept {concept_id}")
        if obligations:
            for obligation_id in unit.get("explanation_obligation_ids", []):
                if obligation_id not in obligations:
                    errors.append(
                        f"rewrite unit {unit_id} names missing obligation {obligation_id}"
                    )
        if dependencies:
            for dependency_id in unit.get("dependency_ids", []):
                if dependency_id not in dependencies:
                    errors.append(
                        f"rewrite unit {unit_id} names missing dependency {dependency_id}"
                    )
        for child_id in unit.get("child_unit_ids", []):
            if unit_ids and child_id not in unit_ids:
                errors.append(f"rewrite unit {unit_id} names missing child unit {child_id}")
        parent_id = unit.get("parent_unit_id")
        if isinstance(parent_id, str) and unit_ids and parent_id not in unit_ids:
            errors.append(f"rewrite unit {unit_id} names missing parent unit {parent_id}")
    return errors


def _disposition_link_errors(
    by_type: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    """Require complete concept coverage and resolvable unit links in the plan."""
    dispositions = by_type.get("ConceptDisposition", [])
    if not dispositions:
        return []
    concepts = _index(by_type, "SourceConcept", "concept_id")
    accepted_concepts = {
        concept_id
        for concept_id, row in concepts.items()
        if row.get("review_status") == "accepted"
    }
    units = {
        row.get("unit_id")
        for row in by_type.get("RewriteUnit", [])
        if isinstance(row.get("unit_id"), str)
    }
    errors: list[str] = []
    planned: set[str] = set()
    for disposition in dispositions:
        disposition_id = disposition.get("disposition_id")
        for concept_id in disposition.get("source_concept_ids", []):
            if concepts and concept_id not in concepts:
                errors.append(
                    f"disposition {disposition_id} names missing concept {concept_id}"
                )
            elif disposition.get("review_status") == "accepted":
                planned.add(concept_id)
        for unit_id in disposition.get("rewrite_unit_ids", []):
            if units and unit_id not in units:
                errors.append(
                    f"disposition {disposition_id} names missing rewrite unit {unit_id}"
                )
    missing = sorted(accepted_concepts - planned)
    if missing:
        errors.append(
            "concepts lack an accepted rewrite disposition: " + ", ".join(missing)
        )
    return errors


def _protected_link_errors(
    by_type: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    """Check exact-object references against the extracted protected manifest."""
    manifests = by_type.get("ProtectedManifest", [])
    if not manifests:
        return []
    known = {
        obj.get("object_id")
        for manifest in manifests
        for obj in manifest.get("objects", [])
        if isinstance(obj, Mapping) and isinstance(obj.get("object_id"), str)
    }
    errors: list[str] = []
    referents = (
        ("SourceSpan", "record_id"),
        ("SourceConcept", "concept_id"),
        ("RewriteUnit", "unit_id"),
    )
    for record_type, key in referents:
        for row in by_type.get(record_type, []):
            for object_id in row.get("protected_object_ids", []):
                if object_id not in known:
                    errors.append(
                        f"{record_type} {row.get(key)} names unknown protected object {object_id}"
                    )
    return errors


def _snapshot_coverage_errors(
    by_type: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    """Require each declared source file to be covered to its exact byte size."""
    spans = by_type.get("SourceSpan", [])
    if not spans:
        return []
    errors: list[str] = []
    covered: dict[str, int] = {}
    for span in spans:
        path = span.get("source_file")
        end = span.get("byte_end")
        if isinstance(path, str) and isinstance(end, int):
            covered[path] = max(covered.get(path, 0), end)
    for snapshot in by_type.get("SourceSnapshot", []):
        declared = {
            row.get("path"): row.get("byte_size")
            for row in snapshot.get("source_files", [])
            if isinstance(row, Mapping) and isinstance(row.get("path"), str)
        }
        for path, size in declared.items():
            if path not in covered:
                errors.append(f"source file has no spans: {path}")
            elif isinstance(size, int) and covered[path] != size:
                errors.append(
                    f"source partition for {path} covers {covered[path]} of {size} bytes"
                )
        for path in sorted(set(covered) - set(declared)):
            errors.append(f"spans reference a file outside the snapshot: {path}")
    return errors


def _correspondence_bundle_errors(
    by_type: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    concepts = {
        row.get("concept_id")
        for row in by_type.get("SourceConcept", [])
        if row.get("review_status") == "accepted" and isinstance(row.get("concept_id"), str)
    }
    correspondences = by_type.get("ConceptCorrespondence", [])
    if not correspondences:
        return []
    errors: list[str] = []
    supported: set[str] = set()
    revisions = _index(by_type, "Revision", "revision_id")
    for correspondence in correspondences:
        revision_id = correspondence.get("revision_id")
        revision = revisions.get(str(revision_id)) if revisions else None
        if revisions and revision is None:
            errors.append(f"correspondence names missing revision: {revision_id}")
        elif revision is not None:
            if revision.get("child_hash") != correspondence.get("candidate_hash"):
                errors.append(
                    f"correspondence candidate_hash does not match revision {revision_id}"
                )
            if revision.get("baseline_id") != correspondence.get("baseline_id"):
                errors.append(
                    f"correspondence baseline does not match revision {revision_id}"
                )
        for concept_id in correspondence.get("source_concept_ids", []):
            if concept_id not in concepts:
                errors.append(f"correspondence links unknown concept: {concept_id}")
            if correspondence.get("verdict") == "supported":
                supported.add(concept_id)
    missing = sorted(concepts - supported)
    if missing:
        errors.append("concepts lack supported correspondence: " + ", ".join(missing))

    for preflight in by_type.get("SemanticPreflightResult", []):
        if preflight.get("status") != "pass":
            continue
        coverage = preflight.get("concept_coverage", {})
        if coverage.get("frozen_concept_count") != len(concepts):
            errors.append("passing preflight frozen concept count does not match bundle")
        if coverage.get("supported_concept_count") != len(supported):
            errors.append("passing preflight supported concept count does not match bundle")
    return errors


__all__ = [
    "CATALOG_PATH",
    "SCHEMA_ROOT",
    "RecordValidationError",
    "SchemaRegistry",
    "baseline_manifest_hash",
    "canonical_hash",
    "canonical_json_bytes",
    "get_registry",
    "load_schema",
    "validate_record",
    "validate_record_bundle",
]
