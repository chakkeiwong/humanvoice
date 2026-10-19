"""Derive one strictly bounded identifier correction from retained writer evidence."""

import json
import re
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from humanvoice import artifacts, codex_runtime
from humanvoice.artifacts import confined_path, digest, read_json, validated_session, write_json
from tools import writer_input_budget_diagnostic as replay
from tools import writer_size_continuation as previous
from tools.inventory_transport_continuation import immutable

ROOT, BASE = previous.ROOT, previous.BASE
PRIOR = BASE / "held-out-reproduction-writer-size-20261019-01"
EVIDENCE = BASE / "writer-identifier-recovery-20261019"
DIAGNOSTIC = EVIDENCE / "diagnostic.json"
VERSION = "retained-writer-identifier-repair-v1"
INSTRUCTION = "repair this mistake, refresh the master program, git commit, and continue the execution."
POLICY = {"maximum_corrections": 1, "maximum_deleted_characters": 2,
          "valid_identifiers_changed": False, "candidate_text_changed": False,
          "semantic_rerolls": False, "provider_calls_for_correction": 0,
          "independent_semantic_review": "required"}


def deletion_match(shorter, longer):
    difference = len(longer) - len(shorter)
    return 1 <= difference <= POLICY["maximum_deleted_characters"] and any(
        longer[:position] + longer[position + difference:] == shorter
        for position in range(len(longer) - difference + 1))


def correct_payload(payload, required_ids, all_ids):
    result = deepcopy(payload)
    rows = result.get("concept_correspondences", [])
    identifiers = [row.get("source_concept_id") for row in rows]
    required, universe = set(required_ids), set(all_ids)
    if (len(required) != len(required_ids) or not required <= universe
            or any(not isinstance(key, str) or not re.fullmatch(r"concept-[0-9a-f]{24}", key) for key in universe)
            or any(not isinstance(key, str) for key in identifiers)
            or len(identifiers) != len(required) or len(set(identifiers)) != len(identifiers)):
        raise ValueError("Identifier repair requires complete unique correspondence membership")
    missing, extra = required - set(identifiers), set(identifiers) - required
    if len(missing) != 1 or len(extra) != 1:
        raise ValueError("Identifier repair requires exactly one malformed identifier")
    wrong, expected = next(iter(extra)), next(iter(missing))
    if (not re.fullmatch(r"concept-[0-9a-f]{22,23}", wrong)
            or [key for key in sorted(universe) if deletion_match(wrong, key)] != [expected]):
        raise ValueError("Identifier repair is ambiguous or exceeds its deletion-only scope")
    position = identifiers.index(wrong)
    rows[position]["source_concept_id"] = expected
    return result, {"index": position, "field": "source_concept_id", "original": wrong, "corrected": expected}


def original_call():
    call = read_json(PRIOR / "calls/0008/call.json")
    if (call["status"] != "complete" or call["request_hash"] != digest(call["request"])
            or call["prompt_hash"] != digest(call["request"]["prompt"])
            or call["request"]["purpose"] != "source_grounded_rewrite"
            or previous.previous.repair.writer.request_context(call["request"])["unit_id"] != "unit-014"):
        raise ValueError("Identifier repair lost its exact retained writer")
    return call


def derive(snapshot, session, baseline, plan):
    call = original_call()
    receipt = codex_runtime.validate_codex_record(snapshot, call["runtime_record"])
    folder = confined_path(snapshot, call["runtime_record"]["path"]).parent
    response = read_json(folder / "response.json")
    if (receipt["termination"] != "complete" or response["text"] != call["response_text"]
            or (folder / "inputs/prompt.txt").read_text() != call["request"]["prompt"]
            or any(response[key] != call[key] for key in ("input_tokens", "output_tokens"))):
        raise ValueError("Identifier correction changed original provider evidence")
    original = replay.replay(snapshot, call, receipt, session, baseline, plan)
    payload, correction = correct_payload(json.loads(call["response_text"]), original.input_concept_ids,
                                         [entry.concept_id for entry in baseline.concept_entries])
    expected_error = "incomplete_concept_mapping: missing, duplicate or extra concept IDs: " + str([correction["corrected"]])
    if original.is_acceptable or original.failure_stage != "writer_evidence" or original.rejection_reasons != [expected_error]:
        raise ValueError("Identifier repair cannot hide another native writer failure: " + "; ".join(original.rejection_reasons))
    changed = dict(call, response_text=json.dumps(payload))
    result = replay.replay(snapshot, changed, receipt, session, baseline, plan)
    if not result.is_acceptable or result.output_latex != original.output_latex:
        raise ValueError("Corrected identifier failed unchanged native writer checks")
    result.raw_response = call["response_text"]
    return asdict(result), asdict(original), payload, correction


def report():
    value = read_json(DIAGNOSTIC)
    if (value.get("identity") != digest({key: item for key, item in value.items() if key != "identity"})
            or value.get("version") != VERSION or value.get("instruction") != INSTRUCTION
            or value.get("policy") != POLICY or value.get("status") != "pass"
            or value.get("phase_admitted") is not False or value.get("model_calls") != 0):
        raise ValueError("Identifier diagnostic authority or verification changed")
    return value


def admission_for(diagnostic, result):
    return {"version": VERSION, "diagnostic_identity": diagnostic["identity"],
            "original_call_hash": diagnostic["call_hash"], "correction": diagnostic["correction"],
            "original_response_hash": diagnostic["response_hash"],
            "corrected_payload_hash": diagnostic["corrected_payload_hash"],
            "result_hash": digest(result), "runtime_record": result["runtime_record"],
            "provider_response_modified": False, "candidate_text_changed": False,
            "model_calls": 0, "independent_semantic_review": "required"}


def validate_result(snapshot, result):
    diagnostic, call = report(), original_call()
    native = {key: value for key, value in result.items() if key != "writer_identifier_admission"}
    expected = admission_for(diagnostic, native)
    relative = ".humanvoice/writer-identifier-admissions/" + call["request_hash"] + ".json"
    payload = read_json(confined_path(snapshot, relative.replace(".json", "-payload.json")))
    source_payload = json.loads(call["response_text"])
    correction = diagnostic["correction"]
    source_payload["concept_correspondences"][correction["index"]][correction["field"]] = correction["corrected"]
    journal = ".humanvoice/rewrites/attempts/identifier-retained-" + call["request_hash"] + "/unit-014/001.json"
    folder = confined_path(snapshot, call["runtime_record"]["path"]).parent
    receipt = codex_runtime.validate_codex_record(snapshot, call["runtime_record"])
    if (digest(call) != diagnostic["call_hash"] or digest(native) != diagnostic["result_hash"]
            or native["raw_response"] != call["response_text"] or not native["is_acceptable"]
            or digest(payload) != diagnostic["corrected_payload_hash"] or payload != source_payload
            or digest(read_json(confined_path(snapshot, journal))) != diagnostic["original_result_hash"]
            or receipt["termination"] != "complete" or read_json(folder / "response.json")["text"] != call["response_text"]
            or result.get("writer_identifier_admission") != {"path": relative, "hash": digest(expected)}
            or read_json(confined_path(snapshot, relative)) != expected):
        raise ValueError("Derived identifier admission changed")
    return result


def materialize(snapshot):
    snapshot = Path(snapshot)
    diagnostic = report()
    session, baseline, plan, _ = validated_session(snapshot, require_complete=False)
    if "unit-014" in session["results"] or session["units_completed"] != [unit.unit_id for unit in plan.units[:-1]]:
        raise ValueError("Identifier continuation requires its exact thirteen retained writers")
    result, original, payload, correction = derive(snapshot, session, baseline, plan)
    if (digest(result) != diagnostic["result_hash"] or digest(payload) != diagnostic["corrected_payload_hash"]
            or correction != diagnostic["correction"]):
        raise ValueError("Identifier replay differs from its frozen diagnostic")
    call = original_call()
    journal = ".humanvoice/rewrites/attempts/identifier-retained-" + call["request_hash"] + "/unit-014/001.json"
    immutable(snapshot / journal, original)
    admission = admission_for(diagnostic, result)
    relative = ".humanvoice/writer-identifier-admissions/" + call["request_hash"] + ".json"
    immutable(snapshot / relative, admission)
    immutable(snapshot / ".humanvoice/writer-identifier-admissions" / (call["request_hash"] + "-payload.json"), payload)
    result["writer_identifier_admission"] = {"path": relative, "hash": digest(admission)}
    directory = snapshot / ".humanvoice/rewrites"
    result_path = "writer-identifier-results/" + call["request_hash"] + ".json"
    immutable(directory / result_path, result)
    updated = deepcopy(session)
    updated.update(parent_session_id=session["session_id"], session_id="identifier-" + call["request_hash"][:16])
    updated["results"]["unit-014"] = {"path": result_path, "hash": digest(result)}
    results = {unit.unit_id: artifacts.load_unit_result(snapshot, updated, unit.unit_id) for unit in plan.units}
    if not all(value["is_acceptable"] for value in results.values()):
        raise ValueError("Identifier repair lost a retained accepted writer")
    updated.update(units_completed=list(results), units_failed=[], total_completed=len(results), total_failed=0, status="complete")
    updated["mapped_concept_ids"] = [row["source_concept_id"] for value in results.values() for row in value["concept_correspondences"]]
    updated["total_concepts_mapped"] = len(set(updated["mapped_concept_ids"]))
    updated["total_concepts_unmet"] = len(baseline.concept_entries) - updated["total_concepts_mapped"]
    name = "session-" + updated["session_id"] + ".json"
    immutable(directory / name, updated)
    write_json(directory / "current.json", {"path": name})
    validate_result(snapshot, result)
    return {"unit_id": "unit-014", "reference": updated["results"]["unit-014"], "result_sha256": digest(result)}


@contextmanager
def consumer_validation():
    native = artifacts.load_unit_result

    def load(snapshot, session, unit_id):
        result = native(snapshot, session, unit_id)
        if ("writer_identifier_admission" in result
                or session["results"][unit_id]["path"].startswith("writer-identifier-results/")):
            validate_result(snapshot, result)
        return result

    with previous.runtime.previous.replaced_aliases(native, load):
        yield
