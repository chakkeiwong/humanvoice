"""Reconstruct document-budget attempts with unchanged native receipt semantics."""

import importlib.util
import json
from datetime import datetime
from pathlib import Path

from humanvoice.artifacts import (
    digest,
    read_json,
)
from tools import sol_inventory_execution as frozen_execution
from tools.inventory_recovery_v3 import runtime as adapter

FIELD = adapter.FIELD
specification = importlib.util.spec_from_file_location(
    "tools._document_recovery_execution", frozen_execution.__file__)
predecessor = importlib.util.module_from_spec(specification)
specification.loader.exec_module(predecessor)
predecessor.adapter = adapter.implementation
CANARY = predecessor.retained.canonical_request(None, (), {"prompt": 'Return exactly an empty JSON array: []. Do not use tools.',
          "system_prompt": None, "purpose": "concept_extraction",
          "response_schema": "extraction-response"})


class RecoveryBlocked(RuntimeError):
    def __init__(self, category, detail, *, incident=None):
        self.category = category
        self.incident = incident
        super().__init__(detail)


def _read(output, relative, raw):
    return json.loads(raw(relative)) if raw else read_json(Path(output) / relative)


def _parent(plan):
    parent = plan[FIELD]["parent_failure"]
    if (parent.get("eligible") is not True or not parent.get("runtime_record_hash")
            or not isinstance(parent.get("request"), dict)
            or parent.get("request_hash") != digest(parent["request"])):
        raise ValueError("Successor requires its exact eligible parent request")
    return parent


def _failed(output, index, plan, entry, raw):
    proof = adapter.failure(output, Path(output) / f"calls/{index:04d}", plan, entry, raw=raw)
    if not proof.get("eligible"):
        raise RecoveryBlocked("BLOCKED_ENGINEERING", "Failure is not eligible for transport recovery: " +
                              str(proof.get("reason")), incident=proof)
    journal = _read(output, f"calls/{index:04d}/call.json", raw)
    record = _read(output, "snapshots/primary/snapshot/" + journal["runtime_record"]["path"], raw)
    failed_at = datetime.fromisoformat(record["created_at"])
    if failed_at.tzinfo is None:
        raise ValueError("Recovery receipt has no timezone")
    return {**proof, "request": journal["request"],
            "request_hash": journal["request_hash"], "eligible_after": failed_at.timestamp() + 900}


def layout(output, plan, entries, *, raw=None, runtime_snapshot=None):
    adapter.validate_plan(plan)
    parent = _parent(plan)
    count = len(plan["calls"])
    calls = adapter.implementation.automatic_recovery.attempt_calls(plan)
    by_key = {call["key"]: index for index, call in enumerate(calls)}
    inherited = plan[FIELD]["recovery_sessions_used"]
    ceiling = plan[FIELD]["policy"]["recovery_ceiling"]
    if type(inherited) is not int or not 0 <= inherited <= ceiling:
        raise ValueError("Invalid inherited recovery usage")
    selected, indices, failures, attempts, receipts = {}, [], [], {}, set()
    current, extra, mode, incident = 0, 0, "canary", parent
    last_canary = None
    originals = {0: parent["request"]}
    for position, entry in enumerate(entries):
        if mode not in {"canary", "request"}:
            raise ValueError("A blocked incident cannot allocate another invocation")
        index = by_key.get(entry.get("key"))
        if index is None or index in indices or entry.get("input_hash") != calls[index]["input_hash"]:
            raise ValueError("Recovery allocation changed or repeated membership")
        descriptor = _read(output, f"reconnect-attempts/{index:04d}.json", raw)
        expected_extra = mode == "canary" or current in selected
        ordinal = attempts.get(current, 0) + 1 if expected_extra else 0
        expected_index = current + ordinal * count
        if (current >= count or index != expected_index or descriptor.get("logical") != current
                or descriptor.get("kind") != mode or descriptor.get("index") != index
                or descriptor.get("plan_identity") != plan["plan_identity"]
                or descriptor.get("incident_hash") != (digest(incident) if incident else None)):
            raise ValueError("Recovery role, order or incident binding changed")
        request = descriptor.get("request")
        if (not isinstance(request, dict) or descriptor.get("request_hash") != digest(request)
                or mode == "canary" and request != CANARY
                or mode == "request" and current in originals and request != originals[current]):
            raise ValueError("Canary or exact manuscript request changed")
        if expected_extra:
            extra += 1
            attempts[current] = ordinal
        if inherited + extra > ceiling or len(entries) > count + plan["recovery"]["maximum_total"]:
            raise RecoveryBlocked("BLOCKED_BUDGET", "Cumulative recovery session allowance exhausted")
        if mode == "canary":
            wait = _read(output, "reconnect-waits/" + digest(incident) + ".json", raw)
            if (wait.get("failure_hash") != digest(incident)
                    or wait.get("eligible_after") != incident["eligible_after"]
                    or wait.get("failed_at") != incident["eligible_after"] - 900
                    or wait.get("backoff_seconds") != 900
                    or wait.get("status") != "eligible"
                    or type(wait.get("observed_at")) not in (int, float)
                    or not wait["observed_at"] >= wait["eligible_after"]):
                raise ValueError("Canary requires a completed receipt-bound wait")
        indices.append(index)
        if entry["status"] == "allocated_unknown":
            if position != len(entries) - 1:
                raise ValueError("Unreconciled allocation cannot have a successor")
            return {"selected": selected, "indices": indices, "recoveries": extra,
                    "failures": failures, "pending": index, "mode": "ambiguous",
                    "logical": current, "incident": incident, "attempts": attempts}
        journal = _read(output, f"calls/{index:04d}/call.json", raw)
        if journal["request"] != request or journal["request_hash"] != digest(request):
            raise ValueError("Retained request differs from its recovery role")
        if (journal.get("invocation_id") != entry["invocation_id"]
                or journal.get("call_contract_hash") != entry["input_hash"]):
            raise ValueError("Recovery journal lost its allocated invocation")
        from tools.inventory_recovery_v3.runtime_binding import verify

        verify(plan, output, entry, index, journal, raw=raw)
        result = _read(output, f"calls/{index:04d}/result.json", raw)
        if (entry.get("result_hash") != digest(result) or result.get("status") != entry["status"]
                or result.get("evidence_error") is not None):
            raise ValueError("Recovery result lacks valid native evidence")
        reference = journal.get("runtime_record", {})
        if not reference.get("hash") or reference["hash"] in receipts:
            raise ValueError("Recovery invocation reuses or lacks a runtime receipt")
        receipts.add(reference["hash"])
        if entry["status"] == "incomplete":
            from tools.inventory_recovery_v3.cancellation import (
                evidence as local_cancellation,
            )

            cancelled = local_cancellation(plan, output, entry, index, journal, raw=raw)
            if cancelled is not None:
                if mode == "request":
                    originals.setdefault(current, request)
                    selected[current] = index
                original_request = originals[current]
                incident = {"eligible": True, "recovery_kind": "local_cancellation",
                    "reason": "explicit_user_cancelled_before_launch", "transport_retry": False,
                    "runtime_record_hash": reference["hash"], "cancellation_identity": cancelled["identity"],
                    "request": original_request, "request_hash": digest(original_request),
                    "eligible_after": incident["eligible_after"] if incident else datetime.fromisoformat(
                        _read(output, "snapshots/primary/snapshot/" + reference["path"], raw)["created_at"]).timestamp() + 900}
                mode, last_canary = "canary", None
                continue
            from tools.inventory_recovery_v2.cancellation import evidence

            cancelled = evidence(output, Path(output) / f"calls/{index:04d}", plan, entry, raw=raw)
            if cancelled is not None:
                if mode == "request":
                    originals.setdefault(current, request)
                    selected[current] = index
                continue
        if mode == "canary":
            if entry["status"] != "complete":
                try:
                    _failed(output, index, plan, entry, raw)
                except RecoveryBlocked as error:
                    incident = {"eligible": False, "proof": error.incident,
                                "primary_error": result.get("error"),
                                "call": f"calls/{index:04d}/call.json"}
                    mode = "engineering_block"
                else:
                    mode = "external_block"
            elif json.loads(journal["response_text"]) != []:
                mode = "protocol_block"
            else:
                relative = "snapshots/primary/snapshot/" + str(Path(reference["path"]).parent)
                receipt = _read(output, relative + "/record.json", raw)
                if digest(receipt) != reference["hash"]:
                    raise ValueError("Canary receipt identity changed")
                for name, expected in receipt["extensions"]["evidence_hashes"].items():
                    if Path(name).is_absolute() or ".." in Path(name).parts:
                        raise ValueError("Canary evidence escaped its runtime directory")
                    content = raw(relative + "/" + name) if raw else (Path(output) / relative / name).read_bytes()
                    if digest(content) != expected:
                        raise ValueError("Canary runtime evidence changed")
                response = _read(output, relative + "/response.json", raw)
                native_request = _read(output, relative + "/inputs/api-request.json", raw)
                started = _read(output, relative + "/process-start.json", raw)["started_at"]
                created = datetime.fromisoformat(receipt["created_at"])
                prompt = (raw(relative + "/inputs/prompt.txt").decode() if raw else
                          (Path(output) / relative / "inputs/prompt.txt").read_text())
                if raw is None:
                    validated = adapter.implementation.capture.validate_record(
                        Path(plan["snapshot"]), journal["runtime_record"])
                    if validated != receipt:
                        raise ValueError("Original canary receipt differs from settled copy")
                if (receipt["termination"] != "complete"
                        or native_request.get("profile") != plan["profile"]
                        or native_request.get("source_hash") != plan["bindings"]["source"]
                        or native_request.get("implementation") != plan["bindings"]["implementation"]
                        or prompt != request["prompt"]
                        or native_request.get("prompt_hash") != digest(request["prompt"])
                        or any(native_request.get(field) != request.get(field)
                               for field in ("purpose", "response_schema", "system_prompt"))
                        or type(started) not in (int, float) or not started >= wait["observed_at"]
                        or created.tzinfo is None or not created.timestamp() >= started
                        or journal.get("response_text") != response.get("text")
                        or any(journal.get(field) != receipt.get(field)
                               or response.get(field) != receipt.get(field)
                               for field in ("input_tokens", "output_tokens"))):
                    raise ValueError("Canary differs from its native completed receipt")
                last_canary = index
                mode = "request"
        else:
            originals.setdefault(current, request)
            selected[current] = index
            if entry["status"] == "complete":
                current += 1
                mode, incident, last_canary = "request", None, None
            elif entry["status"] == "incomplete":
                if position == len(entries) - 1:
                    try:
                        incident = _failed(output, index, plan, entry, raw)
                    except RecoveryBlocked as error:
                        incident = {"eligible": False, "proof": error.incident,
                                    "primary_error": result.get("error"),
                                    "call": f"calls/{index:04d}/call.json",
                                    "request_hash": journal["request_hash"],
                                    "runtime_record": journal.get("runtime_record")}
                        mode = "engineering_block"
                        continue
                else:
                    incident = _failed(output, index, plan, entry, raw)
                failures.append({"logical_index": current, "attempt_index": index, **incident})
                mode = ("size_decomposition_required" if incident.get("recovery_kind") == "output_limit" else
                        "decomposition_required" if last_canary is not None else "canary")
            else:
                raise ValueError("Unexpected recovery allocation status")
    return {"selected": selected, "indices": indices, "recoveries": extra,
            "failures": failures, "mode": mode, "logical": current,
            "incident": incident, "attempts": attempts, "pending": None}
