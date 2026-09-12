#!/usr/bin/env python3
"""Generate the locked Humanvoice v2 schema examples."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from humanvoice.schemas import (  # noqa: E402
    baseline_manifest_hash,
    canonical_hash,
    concept_identity_basis,
    obligation_spec_hash,
    rewrite_unit_spec_hash,
)

OUT = ROOT / "schemas" / "examples"
NOW = "2026-09-11T12:00:00Z"
RUN = "run-v2-example"
SCHEMA_VERSION = "HV-SCHEMA-2.0"


def digest(character: str) -> str:
    return character * 64


def common(record_type: str, record_id: str) -> dict[str, Any]:
    return {
        "record_type": record_type,
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "run_id": RUN,
        "created_at": NOW,
    }


def write_json(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def make_baseline_records() -> dict[str, Any]:
    baseline_id = "baseline-1"
    source_hash = digest("a")
    brief = common("HumanizationBrief", "brief-1")
    brief.update({
        "source_entry_point": "main.tex",
        "reader": {
            "role": "trained technical reader",
            "prior_knowledge": ["calculus"],
            "reading_context": "Read the complete survey without repository context.",
        },
        "purpose": "Understand the model and its limiting cases.",
        "decision": None,
        "genre": "technical survey",
        "known_vocabulary": ["derivative"],
        "exemplars": [],
        "evidence_boundary": "Use only the frozen manuscript and linked evidence.",
        "privacy_class": "internal",
        "remote_inference": {
            "authorized": False,
            "provider": None,
            "purpose": None,
            "approved_by": None,
        },
        "voice_constraints": {
            "register": "clear technical prose",
            "person": "source_dependent",
            "additional": [],
        },
        "protected_object_policy": "Preserve exact equations, citations, labels, and numbers.",
        "unresolved_assumptions": [],
        "authorizing_action": {
            "actor": "document-owner",
            "role": "document_owner",
            "action": "humanize_finished_manuscript",
            "authorized_at": NOW,
        },
        "policy_sources": [{"path": "policies/humanizer.md", "sha256": digest("b")}],
    })
    brief_hash = canonical_hash(brief)

    snapshot = common("SourceSnapshot", "snapshot-record-1")
    snapshot.update({
        "snapshot_id": "snapshot-1",
        "source_hash": source_hash,
        "source_entry_point": "main.tex",
        "source_files": [{"path": "main.tex", "sha256": source_hash, "byte_size": 200}],
        "source_tree_bytes": 200,
        "humanization_brief_id": brief["record_id"],
        "humanization_brief_hash": brief_hash,
        "brief_valid": True,
        "snapshot_immutable": True,
        "snapshot_closed_at": NOW,
        "source_root": "/example/source",
        "scratch_path": "scratch",
        "privacy_class": "internal",
    })

    def make_span(
        record_id: str,
        start: int,
        end: int,
        lines: tuple[int, int],
        kind: str,
        disposition: str,
        *,
        concept_ids: list[str] | None = None,
        protected_object_ids: list[str] | None = None,
        scaffolding_ids: list[str] | None = None,
        reader_facing: bool = True,
    ) -> dict[str, Any]:
        span = common("SourceSpan", record_id)
        span.update({
            "snapshot_id": "snapshot-1",
            "source_hash": source_hash,
            "source_file": "main.tex",
            "byte_start": start,
            "byte_end": end,
            "line_start": lines[0],
            "line_end": lines[1],
            "exact_text_hash": canonical_hash([record_id, start, end]),
            "span_kind": kind,
            "reader_facing": reader_facing,
            "structural_parent_id": None,
            "coverage_disposition": disposition,
            "concept_ids": concept_ids or [],
            "protected_object_ids": protected_object_ids or [],
            "scaffolding_disposition_ids": scaffolding_ids or [],
        })
        return span

    # A complete deterministic partition of main.tex: two concept-bearing
    # passages and one non-substantive workflow comment.
    span_one = make_span("span-1", 0, 60, (1, 2), "prose", "concept_bearing", concept_ids=["concept-1"])
    span_two = make_span(
        "span-2", 60, 140, (3, 5), "prose", "concept_bearing",
        concept_ids=["concept-2"], protected_object_ids=["eq_0"],
    )
    span_scaffolding = make_span(
        "span-3", 140, 200, (6, 7), "comment", "non_substantive_scaffolding",
        scaffolding_ids=["scaffolding-1"], reader_facing=False,
    )
    spans = [span_one, span_two, span_scaffolding]

    def make_obligation(
        record_id: str, obligation_id: str, concept_id: str,
        functions: list[str], span_ids: list[str], reader_rationale: str,
    ) -> dict[str, Any]:
        obligation = common("ExplanationObligation", record_id)
        obligation.update({
            "baseline_id": baseline_id,
            "obligation_id": obligation_id,
            "parent_record_id": None,
            "concept_id": concept_id,
            "required_teaching_functions": functions,
            "source_assessment": {"status": "partial", "evidence_span_ids": span_ids},
            "reader_rationale": reader_rationale,
            "genre_rationale": "A survey must teach terminology before using it.",
            "active": True,
            "deactivation": None,
            "fulfillment_status": "unassessed",
            "fulfillment_evidence": [],
        })
        obligation["obligation_spec_hash"] = obligation_spec_hash(obligation)
        return obligation

    obligation = make_obligation(
        "obligation-record-1", "obligation-1", "concept-1",
        ["definition"], ["span-1"],
        "The reader must know what continuity means here before the contrast.",
    )
    obligation_two = make_obligation(
        "obligation-record-2", "obligation-2", "concept-2",
        ["definition", "contrast"], ["span-2"],
        "The reader must distinguish the nearby cases.",
    )

    def make_concept(
        record_id: str, concept_id: str, span_ids: list[str], proposition: str,
        concept_type: str, role: str, obligation_ids: list[str],
        *, protected_object_ids: list[str] | None = None,
        qualifications: list[str] | None = None,
        prerequisites: list[str] | None = None,
    ) -> dict[str, Any]:
        concept = common("SourceConcept", record_id)
        concept.update({
            "baseline_id": baseline_id,
            "snapshot_id": "snapshot-1",
            "concept_id": concept_id,
            "identity_basis": concept_identity_basis(source_hash, span_ids),
            "proposition": proposition,
            "concept_type": concept_type,
            "source_span_ids": span_ids,
            "occurrences": [{"span_id": span_id, "teaching_role": role} for span_id in span_ids],
            "supporting_claims": [],
            "evidence_ids": [],
            "protected_object_ids": protected_object_ids or [],
            "assumptions": [],
            "qualifications": qualifications or [],
            "reader_prerequisites": prerequisites or [],
            "explanation_obligation_ids": obligation_ids,
            "extraction_confidence": 0.91,
            "review_status": "accepted",
            "lineage": {
                "parent_concept_ids": [],
                "change_reason": None,
                "adjudicated_by": None,
                "adjudicated_at": None,
            },
        })
        return concept

    concept = make_concept(
        "concept-record-1", "concept-1", ["span-1"],
        "A continuous map has no jump at the threshold.",
        "definition", "define", ["obligation-1"],
    )
    concept_two = make_concept(
        "concept-record-2", "concept-2", ["span-2"],
        "A kink is distinct from a true discontinuity.",
        "distinction", "contrast", ["obligation-2"],
        protected_object_ids=["eq_0"],
        qualifications=["The distinction concerns continuity of the map itself."],
        prerequisites=["continuous function"],
    )

    dependency = common("ConceptDependency", "dependency-record-1")
    dependency.update({
        "baseline_id": baseline_id,
        "dependency_id": "dependency-1",
        "prerequisite_concept_id": "concept-1",
        "dependent_concept_id": "concept-2",
        "relation": "prerequisite",
        "rationale": "Continuity must be known before the distinction is explained.",
        "preview_exemption": {"active": False, "reason": None, "authorized_by": None},
        "review_status": "accepted",
    })

    scaffolding = common("ScaffoldingDisposition", "scaffolding-record-1")
    scaffolding.update({
        "baseline_id": baseline_id,
        "disposition_id": "scaffolding-1",
        "source_span_ids": ["span-3"],
        "disposition": "remove_nonconcept",
        "reader_relevance_reason": "The text reports internal workflow state only.",
        "embedded_concept_ids": [],
        "backstage_target": None,
        "review_status": "accepted",
        "adjudication": {
            "reviewer": "editor",
            "reviewed_at": NOW,
            "reason": "No domain meaning is present.",
        },
    })

    groups = {
        "source_spans": spans,
        "source_concepts": [concept, concept_two],
        "concept_dependencies": [dependency],
        "explanation_obligations": [obligation, obligation_two],
        "scaffolding_dispositions": [scaffolding],
    }
    baseline = common("ConceptBaseline", "baseline-record-1")
    baseline.update({
        "baseline_id": baseline_id,
        "snapshot_id": "snapshot-1",
        "source_hash": source_hash,
        "humanization_brief_id": brief["record_id"],
        "humanization_brief_hash": brief_hash,
        "parent_baseline_id": None,
        "component_records": {
            name: sorted(row["record_id"] for row in rows) for name, rows in groups.items()
        },
        "component_hashes": {
            name: canonical_hash(sorted(rows, key=lambda row: row["record_id"]))
            for name, rows in groups.items()
        },
        "component_counts": {
            "source_spans": len(groups["source_spans"]),
            "reader_facing_spans": sum(
                row["reader_facing"] is True for row in groups["source_spans"]
            ),
            "source_concepts": len(groups["source_concepts"]),
            "concept_dependencies": len(groups["concept_dependencies"]),
            "active_explanation_obligations": sum(
                row["active"] is True for row in groups["explanation_obligations"]
            ),
            "scaffolding_dispositions": len(groups["scaffolding_dispositions"]),
        },
        "partition": {
            "source_bytes": 200,
            "covered_bytes": 200,
            "reader_facing_complete": True,
            "non_overlapping": True,
            "exact_hashes_verified": True,
        },
        "coverage_reviews": {
            "source_to_concepts": {
                "critic_id": "critic-forward",
                "critic_version": "1.0",
                "prompt_hash": digest("d"),
                "independent_of_extractor": True,
                "verdict": "supported",
                "finding_ids": [],
            },
            "concepts_to_source": {
                "critic_id": "critic-reverse",
                "critic_version": "1.0",
                "prompt_hash": digest("e"),
                "independent_of_extractor": True,
                "verdict": "supported",
                "finding_ids": [],
            },
        },
        "unresolved": {
            "span_ids": [],
            "concept_ids": [],
            "dependency_ids": [],
            "obligation_ids": [],
            "scaffolding_disposition_ids": [],
        },
        "review_decision": {
            "status": "frozen",
            "reviewer": "baseline-reviewer",
            "reviewed_at": NOW,
            "reason": "All surfaced ambiguities were resolved and bidirectional coverage passed.",
        },
        "frozen": True,
        "frozen_at": NOW,
        "baseline_hash": digest("0"),
        "lineage_reason": None,
    })
    baseline["baseline_hash"] = baseline_manifest_hash(baseline)
    return {
        "brief": brief,
        "snapshot": snapshot,
        "span": span_one,
        "spans": spans,
        "concept": concept,
        "concepts": [concept, concept_two],
        "obligation": obligation,
        "obligations": [obligation, obligation_two],
        "dependency": dependency,
        "scaffolding": scaffolding,
        "baseline": baseline,
    }


def make_post_baseline(records: dict[str, Any]) -> dict[str, Any]:
    baseline = records["baseline"]
    baseline_hash = baseline["baseline_hash"]
    dependency = records["dependency"]
    scaffolding = records["scaffolding"]

    def make_unit(
        record_id: str, unit_id: str, span_id: str, concept_id: str,
        obligation_id: str, *, protected_object_ids: list[str] | None = None,
        preceding: list[str] | None = None, following: list[str] | None = None,
        dependency_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        unit = common("RewriteUnit", record_id)
        unit.update({
            "plan_id": "plan-1",
            "baseline_id": baseline["baseline_id"],
            "baseline_hash": baseline_hash,
            "unit_id": unit_id,
            "unit_spec_hash": digest("0"),
            "source_file": "main.tex",
            "source_span_ids": [span_id],
            "source_hash": records["snapshot"]["source_hash"],
            "contiguous": True,
            "concept_ids": [concept_id],
            "dependency_ids": dependency_ids or [],
            "explanation_obligation_ids": [obligation_id],
            "protected_object_ids": protected_object_ids or [],
            "neighbor_context": {
                "preceding_span_ids": preceding or [],
                "following_span_ids": following or [],
                "context_hash": canonical_hash([unit_id, "context"]),
            },
            "planned_operation": "expand",
            "estimated_output_words": 450,
            "segmentation_triggered": False,
            "parent_unit_id": None,
            "child_unit_ids": [],
            "continuation_state": None,
            "status": "ready",
        })
        unit["unit_spec_hash"] = rewrite_unit_spec_hash(unit)
        return unit

    unit = make_unit(
        "rewrite-unit-record-1", "unit-1", "span-1", "concept-1", "obligation-1",
        following=["span-2"],
    )
    unit_two = make_unit(
        "rewrite-unit-record-2", "unit-2", "span-2", "concept-2", "obligation-2",
        protected_object_ids=["eq_0"], preceding=["span-1"],
        dependency_ids=["dependency-1"],
    )

    def make_disposition(
        record_id: str, disposition_id: str, concept_id: str, unit_id: str,
        roles: list[str],
    ) -> dict[str, Any]:
        disposition = common("ConceptDisposition", record_id)
        disposition.update({
            "baseline_id": baseline["baseline_id"],
            "baseline_hash": baseline_hash,
            "plan_id": "plan-1",
            "disposition_id": disposition_id,
            "source_concept_ids": [concept_id],
            "rewrite_unit_ids": [unit_id],
            "operation": "expand",
            "rationale": "Explain the concept more fully without changing its content.",
            "planned_teaching_roles": roles,
            "review_status": "accepted",
        })
        return disposition

    disposition = make_disposition(
        "concept-disposition-record-1", "concept-disposition-1", "concept-1", "unit-1", ["define"],
    )
    disposition_two = make_disposition(
        "concept-disposition-record-2", "concept-disposition-2", "concept-2", "unit-2",
        ["define", "contrast"],
    )

    candidate_hash = digest("1")

    def make_correspondence(
        record_id: str, correspondence_id: str, concept_id: str,
        start: int, end: int, roles: list[str], reason: str,
    ) -> dict[str, Any]:
        correspondence = common("ConceptCorrespondence", record_id)
        correspondence.update({
            "baseline_id": baseline["baseline_id"],
            "baseline_hash": baseline_hash,
            "revision_id": "revision-1",
            "candidate_hash": candidate_hash,
            "correspondence_id": correspondence_id,
            "source_concept_ids": [concept_id],
            "operation": "expand",
            "output_spans": [{
                "output_file": "main.tex",
                "byte_start": start,
                "byte_end": end,
                "text_hash": canonical_hash([correspondence_id, start, end]),
                "teaching_roles": roles,
            }],
            "rationale": "The revised passage states and explains the same content.",
            "writer_report": {"claimed_complete": True},
            "verifier": {
                "critic_id": "retention-critic",
                "critic_kind": "deterministic",
                "prompt_hash": None,
                "model_or_rule_version": "1.0",
                "independent_of_writer": True,
                "calibration_record_id": None,
            },
            "verdict": "supported",
            "verdict_reason": reason,
            "unresolved_reason": None,
        })
        return correspondence

    correspondence = make_correspondence(
        "correspondence-record-1", "correspondence-1", "concept-1", 0, 120, ["define"],
        "The continuity criterion is defined in the output.",
    )
    correspondence_two = make_correspondence(
        "correspondence-record-2", "correspondence-2", "concept-2", 120, 320,
        ["define", "contrast"],
        "Both cases and the continuity criterion are located in the output.",
    )
    source_obligation = records["obligations"][1]
    fulfilled_obligation = copy.deepcopy(source_obligation)
    fulfilled_obligation["record_id"] = "obligation-fulfillment-record-1"
    fulfilled_obligation["parent_record_id"] = source_obligation["record_id"]
    fulfilled_obligation["fulfillment_status"] = "fulfilled"
    fulfilled_obligation["fulfillment_evidence"] = [
        {"teaching_function": function, "output_file": "main.tex", "byte_start": 0, "byte_end": 160, "text_hash": digest("2"), "critic_id": "obligation-critic", "verdict": "supported"}
        for function in ["definition", "contrast"]
    ]

    check = {
        "status": "pass",
        "checked_ids": ["check-1"],
        "failed_ids": [],
        "unresolved_ids": [],
        "evidence_paths": ["audit/check-1.json"],
        "verifier_ids": ["deterministic-critic"],
    }
    preflight = common("SemanticPreflightResult", "preflight-record-1")
    preflight.update({
        "preflight_id": "preflight-1",
        "baseline_id": baseline["baseline_id"],
        "baseline_hash": baseline_hash,
        "revision_id": "revision-1",
        "candidate_hash": digest("1"),
        "critic_records": [{
            "critic_id": "deterministic-critic", "critic_kind": "deterministic", "version": "1.0",
            "prompt_hash": None, "independent_of_writer": True, "calibration_record_id": None,
        }],
        "source_span_coverage": copy.deepcopy(check),
        "concept_coverage": {
            **copy.deepcopy(check),
            "checked_ids": ["concept-1", "concept-2"],
            "frozen_concept_count": 2,
            "supported_concept_count": 2,
            "retention": 1.0,
        },
        "obligation_fulfillment": copy.deepcopy(check),
        "dependency_order": copy.deepcopy(check),
        "unsupported_additions": copy.deepcopy(check),
        "scaffolding": copy.deepcopy(check),
        "exact_object_integrity": copy.deepcopy(check),
        "build_integrity": copy.deepcopy(check),
        "blocking_finding_ids": [],
        "unresolved_finding_ids": [],
        "diagnostic_finding_ids": [],
        "adjudication_status": "not_required",
        "adjudication_ids": [],
        "status": "pass",
    })

    revision = common("Revision", "revision-record-1")
    revision.update({
        "revision_id": "revision-1", "baseline_id": baseline["baseline_id"], "baseline_hash": baseline_hash,
        "snapshot_id": "snapshot-1", "source_hash": records["snapshot"]["source_hash"],
        "parent_revision_id": None, "parent_hash": records["snapshot"]["source_hash"], "child_hash": digest("1"),
        "candidate_tree": "candidate/revision-1",
        "patches": [
            {"patch_id": "patch-1", "source_file": "main.tex", "byte_start": 0, "byte_end": 60, "expected_text_hash": canonical_hash(["span-1", 0, 60]), "replacement_hash": digest("2"), "operation": "replace", "rewrite_unit_ids": ["unit-1"], "move_target": None},
            {"patch_id": "patch-2", "source_file": "main.tex", "byte_start": 60, "byte_end": 140, "expected_text_hash": canonical_hash(["span-2", 60, 140]), "replacement_hash": digest("8"), "operation": "replace", "rewrite_unit_ids": ["unit-2"], "move_target": None},
        ],
        "untouched_bytes_verified": True, "protected_comparison_path": "audit/protected.json",
        "correspondence_paths": ["audit/correspondence-1.json"], "status": "accepted",
        "decision_by": "editor", "decision_at": NOW, "failure_reasons": [],
    })
    return {
        "dependency": dependency,
        "scaffolding": scaffolding,
        "unit": unit,
        "units": [unit, unit_two],
        "disposition": disposition,
        "dispositions": [disposition, disposition_two],
        "correspondence": correspondence,
        "correspondences": [correspondence, correspondence_two],
        "fulfilled_obligation": fulfilled_obligation,
        "preflight": preflight,
        "revision": revision,
    }


def make_support_records(records: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    protected = common("ProtectedManifest", "protected-record-1")
    protected.update({
        "source_hash": records["snapshot"]["source_hash"],
        "objects": [{
            "object_id": "eq_0",
            "object_type": "equation",
            "raw_form": "\\[ f(x) = \\max(x, 0) \\]",
            "normalized_form": "f(x)=\\max(x,0)",
            "location": {"char_offset": 70, "line": 4, "column": 0, "length": 24},
            "metadata": {"environment": "displaymath"},
        }],
        "parser_name": "fixture-parser",
        "parser_version": "1.0",
        "abstentions": [],
        "comparison": None,
    })

    finding = common("Finding", "finding-record-1")
    finding.update({
        "finding_id": "finding-1", "category": "concept_correspondence", "construct": "retention",
        "source_locations": [{"path": "main.tex", "byte_start": 0, "byte_end": 100, "text_hash": digest("c")}],
        "candidate_locations": [], "observation": "The candidate omits the distinction.",
        "consequence": "The frozen concept is unsupported.", "question": "Restore the distinction and explanation.",
        "rule_version": "retention-1.0", "critic": {"critic_id": "critic", "critic_kind": "deterministic", "version": "1.0", "prompt_hash": None, "calibration_record_id": None, "independent_of_writer": True},
        "verdict": "contradicted", "severity": "blocking", "blocking": True,
        "concept_ids": ["concept-1"], "obligation_ids": ["obligation-1"], "status": "open", "resolution": None,
    })

    compiler = {"name": "pdfTeX", "version": "1.40", "executable_sha256": digest("3"), "flags": ["-no-shell-escape", "-halt-on-error", "-file-line-error"]}
    runtime = common("RuntimeManifest", "runtime-record-1")
    runtime.update({
        "activity": "build", "runtime_type": "deterministic-only", "tool_version": "humanvoice-0.2.0",
        "compiler": compiler, "model_version_string": None, "prompt_template_hash": None,
        "policy_snapshot_hash": digest("4"), "schema_hash": None, "sampling": None, "api_endpoint": None,
        "request_id_if_available": None, "authorization_record_id": None, "transmission_record_id": None,
        "started_at": NOW, "latency_ms": 250.0, "input_tokens": None, "output_tokens": None,
        "output_hash": digest("5"), "termination": "complete", "network_policy": "deny",
        "resource_limits": {"wall_clock_seconds": 300, "max_output_tokens": None, "max_memory_mib": 2048},
    })

    cli = common("CliResult", "cli-record-1")
    cli.update({"contract_id": "HV-IC-2026-09-11", "contract_version": "2.0.0", "command": "hv preflight", "status": "pass", "exit_code": 0, "record_paths": ["audit/preflight.json"], "blocking_reasons": [], "source_hash": records["snapshot"]["source_hash"], "result_hash": canonical_hash(post["preflight"])})
    corpus = common("CorpusItem", "corpus-record-1")
    corpus.update({"source_path_or_url": "main.tex", "source_hash": records["snapshot"]["source_hash"], "owner": "document-owner", "license_or_permission": "owner permission", "permitted_use": "internal evaluation", "redistribution_status": "cleared-internal", "retention_class": "project", "consent_date": "2026-09-11"})

    evidence = common("EvidenceItem", "evidence-record-1")
    evidence.update({"source_path_or_url": "main.tex", "source_hash": records["snapshot"]["source_hash"], "observation": "The source distinguishes a kink from a discontinuity.", "provenance": {"kind": "internal-document", "obtained_at": NOW, "obtained_by": "inventory", "measuring_party": None, "measurement_window": None, "citation_key": None}, "appraisal_state": "corroborated", "supports": [{"target_kind": "concept", "target_id": "concept-1", "load_bearing": True}], "limitations": [], "contradicts": [], "privacy_class": "internal", "rights_record_id": corpus["record_id"]})

    reader = common("ReaderDecision", "reader-record-1")
    rubric = []
    for index, construct in enumerate(["problem", "mechanism", "evidence", "distinction", "assumption", "qualification"], 1):
        rubric.append({"question_id": f"q-{index}", "construct": construct, "response": f"Correct reconstruction of {construct}.", "confidence": "high", "adjudication": "correct", "failure_locations": []})
    reader.update({"reader_id": "reader-1", "reader_name": "Independent Technical Reader", "reader_role": "technical reviewer", "technical_qualification": "Graduate training in the manuscript domain.", "independent_from_rule_tuning": True, "repository_context_used": False, "prior_exposure": "topic-familiar", "assignment": "revision", "reader_packet_hash": digest("6"), "source_document_hash": records["snapshot"]["source_hash"], "revised_document_hash": digest("1"), "baseline_id": records["baseline"]["baseline_id"], "revision_id": "revision-1", "rubric_responses": rubric, "comfort": {"rating": 5, "reread_locations": [], "stop_locations": [], "comments": "The distinction is comfortable to follow."}, "elapsed_minutes": 12.0, "decision": "accept", "requested_changes": []})

    gate = {"status": "pass", "evidence_paths": ["audit/evidence.json"]}
    release = common("ReleaseDecision", "release-record-1")
    release.update({"baseline_id": records["baseline"]["baseline_id"], "baseline_hash": records["baseline"]["baseline_hash"], "revision_id": "revision-1", "candidate_hash": digest("1"), "gate_results": {name: copy.deepcopy(gate) for name in ["baseline_complete", "concept_correspondence", "active_obligations", "dependency_order", "unsupported_additions", "scaffolding", "exact_objects", "source_integrity", "assembly_integrity", "revised_build", "blackline_build", "transmission", "policy_manifest", "runtime_manifest"]}, "reader_packet_hash": digest("6"), "audit_packet_hash": digest("7"), "status": "released", "authorized_by": "Independent Technical Reader", "reader_decision_id": reader["record_id"], "adjudication_ids": [], "blocking_reasons": []})

    return {"protected": protected, "finding": finding, "runtime": runtime, "cli": cli, "corpus": corpus, "evidence": evidence, "reader": reader, "release": release}


def main() -> int:
    from humanvoice.schemas import SchemaRegistry

    baseline = make_baseline_records()
    post = make_post_baseline(baseline)
    support = make_support_records(baseline, post)
    valid = {
        "humanization-brief.schema.json": ("humanization-brief.valid.json", baseline["brief"]),
        "source-snapshot.schema.json": ("source-snapshot.valid.json", baseline["snapshot"]),
        "source-span.schema.json": ("source-span.valid.json", baseline["span"]),
        "source-concept.schema.json": ("source-concept.valid.json", baseline["concept"]),
        "concept-baseline.schema.json": ("concept-baseline.valid.json", baseline["baseline"]),
        "concept-dependency.schema.json": ("concept-dependency.valid.json", post["dependency"]),
        "explanation-obligation.schema.json": ("explanation-obligation.valid.json", baseline["obligation"]),
        "scaffolding-disposition.schema.json": ("scaffolding-disposition.valid.json", post["scaffolding"]),
        "rewrite-unit.schema.json": ("rewrite-unit.valid.json", post["unit"]),
        "concept-disposition.schema.json": ("concept-disposition.valid.json", post["disposition"]),
        "concept-correspondence.schema.json": ("concept-correspondence.valid.json", post["correspondence"]),
        "semantic-preflight-result.schema.json": ("semantic-preflight-result.valid.json", post["preflight"]),
        "protected-manifest.schema.json": ("protected-manifest.valid.json", support["protected"]),
        "finding.schema.json": ("finding.valid.json", support["finding"]),
        "revision.schema.json": ("revision.valid.json", post["revision"]),
        "runtime-manifest.schema.json": ("runtime-manifest.valid.json", support["runtime"]),
        "cli-result.schema.json": ("cli-result.valid.json", support["cli"]),
        "release-decision.schema.json": ("release-decision.valid.json", support["release"]),
        "reader-decision.schema.json": ("reader-decision.valid.json", support["reader"]),
        "evidence-item.schema.json": ("evidence-item.valid.json", support["evidence"]),
        "corpus-item.schema.json": ("corpus-item.valid.json", support["corpus"]),
    }
    invalid: dict[str, tuple[str, dict[str, Any], str]] = {}

    def mutate(schema: str, name: str, source: dict[str, Any], marker: str, function) -> None:
        value = copy.deepcopy(source)
        function(value)
        invalid[schema] = (name, value, marker)

    mutate("humanization-brief.schema.json", "humanization-brief-remote-unapproved.invalid.json", baseline["brief"], "provider", lambda value: value["remote_inference"].update({"authorized": True}))
    mutate("source-snapshot.schema.json", "source-snapshot-mutable.invalid.json", baseline["snapshot"], "True was expected", lambda value: value.__setitem__("snapshot_immutable", False))
    mutate("source-span.schema.json", "source-span-reversed-range.invalid.json", baseline["span"], "byte_end must be greater", lambda value: value.__setitem__("byte_end", 0))
    mutate("source-concept.schema.json", "source-concept-wording-identity.invalid.json", baseline["concept"], "identity_basis", lambda value: value["identity_basis"].__setitem__("identity_hash", digest("9")))
    mutate("concept-baseline.schema.json", "concept-baseline-unresolved.invalid.json", baseline["baseline"], "expected to be empty", lambda value: value["unresolved"]["concept_ids"].append("concept-unknown"))
    mutate("concept-dependency.schema.json", "concept-dependency-self.invalid.json", post["dependency"], "cannot depend on itself", lambda value: value.__setitem__("prerequisite_concept_id", value["dependent_concept_id"]))
    fulfilled_missing = copy.deepcopy(post["fulfilled_obligation"])
    fulfilled_missing["fulfillment_evidence"] = fulfilled_missing["fulfillment_evidence"][:1]
    invalid["explanation-obligation.schema.json"] = ("explanation-obligation-mention-only.invalid.json", fulfilled_missing, "lacks supported evidence")
    mutate("scaffolding-disposition.schema.json", "scaffolding-disposition-unreviewed.invalid.json", post["scaffolding"], "adjudication", lambda value: value.__setitem__("adjudication", None))
    mutate("rewrite-unit.schema.json", "rewrite-unit-unsplit.invalid.json", post["unit"], "child_unit_ids", lambda value: value.update({"estimated_output_words": 2001, "segmentation_triggered": False}))
    mutate("concept-disposition.schema.json", "concept-disposition-omission.invalid.json", post["disposition"], "is not one of", lambda value: value.__setitem__("operation", "omit"))
    mutate("concept-correspondence.schema.json", "concept-correspondence-unsupported.invalid.json", post["correspondence"], "should be non-empty", lambda value: value.__setitem__("output_spans", []))
    mutate("semantic-preflight-result.schema.json", "semantic-preflight-partial-pass.invalid.json", post["preflight"], "1.0 was expected", lambda value: value["concept_coverage"].update({"supported_concept_count": 0, "retention": 0.0}))
    mutate("protected-manifest.schema.json", "protected-manifest-unknown-status.invalid.json", support["protected"], "is not one of", lambda value: value.update({"comparison": {"baseline_hash": digest("a"), "revised_hash": digest("1"), "correspondences": [{"object_baseline": None, "object_revised": None, "status": "unknown", "confidence": 0.0, "rationale": "invalid"}], "unresolved_count": 1, "min_confidence": 0.9}}))
    mutate("finding.schema.json", "finding-extra-top-level.invalid.json", support["finding"], "Additional properties", lambda value: value.__setitem__("unexpected", True))

    overlapping = copy.deepcopy(post["revision"])
    second = copy.deepcopy(overlapping["patches"][0]); second["patch_id"] = "patch-2"; second["byte_start"] = 50
    overlapping["patches"].append(second)
    invalid["revision.schema.json"] = ("revision-overlap.invalid.json", overlapping, "patches overlap")
    mutate("runtime-manifest.schema.json", "runtime-unauthorized-api.invalid.json", support["runtime"], "authorization_record_id", lambda value: value.update({"runtime_type": "anthropic-messages-api"}))
    mutate("cli-result.schema.json", "cli-result-missing-source-hash.invalid.json", support["cli"], "source_hash", lambda value: value.pop("source_hash"))
    blocked_release = copy.deepcopy(support["release"])
    blocked_release["gate_results"]["concept_correspondence"]["status"] = "fail"
    invalid["release-decision.schema.json"] = ("release-decision-semantic-failure.invalid.json", blocked_release, "'pass' was expected")
    partial_reader = copy.deepcopy(support["reader"]); partial_reader["rubric_responses"][0]["adjudication"] = "partial"
    invalid["reader-decision.schema.json"] = ("reader-decision-partial-accept.invalid.json", partial_reader, "is not one of")
    mutate("evidence-item.schema.json", "evidence-item-missing-provenance.invalid.json", support["evidence"], "provenance", lambda value: value.pop("provenance"))
    mutate("corpus-item.schema.json", "corpus-item-missing-consent-date.invalid.json", support["corpus"], "consent_date", lambda value: value.pop("consent_date"))

    manifest_rows = []
    registry = SchemaRegistry()
    for schema, (name, value) in valid.items():
        registry.validate(value)
        write_json(name, value)
        manifest_rows.append({"schema": schema, "instance": name, "expected": "valid"})
    for schema, (name, value, marker) in invalid.items():
        errors = registry.validate(value, raise_on_error=False)
        if not errors:
            raise RuntimeError(f"invalid fixture unexpectedly validates: {name}")
        if marker not in "; ".join(errors):
            raise RuntimeError(f"{name} failed for wrong reason: {errors}")
        write_json(name, value)
        manifest_rows.append({"schema": schema, "instance": name, "expected": "invalid", "expected_error_contains": marker})

    baseline_bundle = (
        [baseline["brief"], baseline["snapshot"]]
        + baseline["spans"]
        + baseline["concepts"]
        + baseline["obligations"]
        + [baseline["dependency"], baseline["scaffolding"], baseline["baseline"]]
    )
    registry.validate_bundle(baseline_bundle)
    write_json("concept-baseline.bundle.valid.json", baseline_bundle)

    # The complete pipeline bundle exercises every cross-record validator:
    # partition coverage, dependency and scaffolding links, unit and
    # disposition links, protected-object links, and correspondence binding.
    pipeline_bundle = (
        baseline_bundle
        + [support["protected"]]
        + post["units"]
        + post["dispositions"]
        + [post["revision"]]
        + post["correspondences"]
        + [post["preflight"]]
    )
    registry.validate_bundle(pipeline_bundle)
    write_json("humanization-pipeline.bundle.valid.json", pipeline_bundle)

    bundle_rows: list[dict[str, Any]] = [
        {"instance": "concept-baseline.bundle.valid.json", "expected": "valid"},
        {"instance": "humanization-pipeline.bundle.valid.json", "expected": "valid"},
    ]

    def bundle_mutation(name: str, marker: str, function) -> None:
        candidate = copy.deepcopy(pipeline_bundle)
        function(candidate)
        errors = registry.validate_bundle(candidate, raise_on_error=False)
        if not errors:
            raise RuntimeError(f"invalid bundle unexpectedly validates: {name}")
        if marker not in "; ".join(errors):
            raise RuntimeError(f"{name} failed for wrong reason: {errors}")
        write_json(name, candidate)
        bundle_rows.append(
            {"instance": name, "expected": "invalid", "expected_error_contains": marker}
        )

    def find(records_list: list[dict[str, Any]], record_id: str) -> dict[str, Any]:
        return next(row for row in records_list if row["record_id"] == record_id)

    def drop(records_list: list[dict[str, Any]], record_id: str) -> None:
        records_list.remove(find(records_list, record_id))

    bundle_mutation(
        "bundle-dangling-dependency.invalid.json",
        "names missing concept",
        lambda rows: find(rows, "dependency-record-1").__setitem__(
            "prerequisite_concept_id", "concept-absent"
        ),
    )
    bundle_mutation(
        "bundle-scaffolding-without-reverse-link.invalid.json",
        "lacks reverse link to scaffolding",
        lambda rows: find(rows, "span-3").__setitem__(
            "scaffolding_disposition_ids", ["scaffolding-other"]
        ),
    )
    bundle_mutation(
        "bundle-unplanned-concept.invalid.json",
        "lack an accepted rewrite disposition",
        lambda rows: drop(rows, "concept-disposition-record-2"),
    )
    bundle_mutation(
        "bundle-unknown-protected-object.invalid.json",
        "names unknown protected object",
        lambda rows: find(rows, "protected-record-1").__setitem__("objects", []),
    )
    bundle_mutation(
        "bundle-incomplete-file-coverage.invalid.json",
        "bytes",
        lambda rows: find(rows, "snapshot-record-1")["source_files"][0].__setitem__(
            "byte_size", 260
        ),
    )
    bundle_mutation(
        "bundle-correspondence-wrong-candidate.invalid.json",
        "candidate_hash does not match revision",
        lambda rows: find(rows, "correspondence-record-2").__setitem__(
            "candidate_hash", digest("9")
        ),
    )

    write_json("manifest.json", {
        "example_manifest_version": "2.1",
        "validator": "python-jsonschema==4.26.0",
        "examples": manifest_rows,
        "bundles": bundle_rows,
    })
    print(
        f"generated {len(valid)} valid and {len(invalid)} invalid v2 examples "
        f"and {len(bundle_rows)} bundles"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
