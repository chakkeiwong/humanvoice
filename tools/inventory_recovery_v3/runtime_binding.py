"""Persist the allocation-to-runtime join before any native provider launch."""

import json
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_history_handover import safe_path
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path


def identity(plan, output, entry, index, descriptor, journal, directory, request):
    output, directory = safe_path(output), safe_path(directory)
    snapshot = safe_path(plan["snapshot"])
    if (directory.parent != snapshot / ".humanvoice/runtime"
            or journal.get("invocation_id") != entry["invocation_id"]
            or journal.get("call_contract_hash") != entry["input_hash"]
            or descriptor.get("plan_identity") != plan["plan_identity"]
            or descriptor.get("index") != index
            or descriptor.get("request") != journal.get("request")
            or descriptor.get("request_hash") != digest(journal.get("request"))
            or journal.get("request_hash") != descriptor["request_hash"]
            or request.get("prompt_hash") != digest(journal["request"]["prompt"])
            or any(request.get(name) != journal["request"].get(name)
                   for name in ("purpose", "response_schema", "system_prompt"))
            or request.get("profile") != plan["profile"]
            or request.get("source_hash") != plan["bindings"]["source"]
            or request.get("implementation") != plan["bindings"]["implementation"]
            or request.get("timeout_seconds") != plan["recovery"]["deadline_seconds"]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Runtime differs from its exact allocated request")
    value = {"version": "allocated-runtime-binding-v1", "plan_identity": plan["plan_identity"],
             "output": str(output), "invocation_id": entry["invocation_id"],
             "key": entry["key"], "input_hash": entry["input_hash"], "index": index,
             "descriptor_hash": digest(descriptor), "request_hash": journal["request_hash"],
             "runtime_path": str((directory / "record.json").relative_to(snapshot)),
             "api_request_hash": digest(request)}
    return {**value, "identity": digest(value)}


def bind(plan, output, directory, *, owner, rejected=False):
    from humanvoice.automatic_recovery import attempt_calls

    if not rejected:
        owner.check()
    elif any((Path(directory) / name).exists() for name in ("process-start.json", "process.json", "record.json")):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Rejected runtime already has process evidence")
    output, directory = safe_path(output), safe_path(directory)
    entries = read_json(regular_path(output / "allocation-ledger.json"))["calls"]
    if not entries or entries[-1]["status"] != "allocated_unknown":
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Runtime requires a pending native allocation")
    entry = entries[-1]
    index = next(index for index, call in enumerate(attempt_calls(plan)) if call["key"] == entry["key"])
    descriptor = read_json(regular_path(output / f"reconnect-attempts/{index:04d}.json"))
    journal = read_json(regular_path(output / f"calls/{index:04d}/call.json"))
    request = read_json(regular_path(directory / "inputs/api-request.json"))
    expected = identity(plan, output, entry, index, descriptor, journal, directory, request)
    path = regular_path(output / f"calls/{index:04d}/runtime-binding.json")
    paths = (path, regular_path(directory / "allocation-binding.json"))
    if any(retained.exists() and (not rejected or read_json(retained) != expected) for retained in paths):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Runtime launch was already bound; reconcile without retransmission")
    if (journal.get("status") != "requesting"
            or (directory / "inputs/prompt.txt").read_bytes() != journal["request"]["prompt"].encode()):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Runtime launch lost its pending native journal")
    if not rejected:
        owner.check()
    for retained in paths:
        if not retained.exists():
            persist(retained, expected)
    if not rejected:
        owner.check()
    return expected


def verify(plan, output, entry, index, journal, *, raw=None):
    output = Path(output)

    def read(relative):
        return json.loads(raw(relative)) if raw else read_json(regular_path(output / relative))

    reference = journal["runtime_record"]
    relative = Path(reference["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Runtime reference escaped its snapshot")
    directory = Path(plan["snapshot"]) / relative.parent
    copied = str(Path("snapshots/primary/snapshot") / relative.parent)
    descriptor = read(f"reconnect-attempts/{index:04d}.json")
    request = read(copied + "/inputs/api-request.json")
    expected = identity(plan, output, entry, index, descriptor, journal, directory, request)
    binding = read(f"calls/{index:04d}/runtime-binding.json")
    retained = read(copied + "/allocation-binding.json")
    receipt = read(copied + "/record.json")
    binding_bytes = raw(copied + "/allocation-binding.json") if raw else (
        regular_path(output / copied / "allocation-binding.json").read_bytes())
    if (binding != expected or retained != expected or digest(receipt) != reference["hash"]
            or receipt.get("record_id") != directory.name
            or receipt.get("extensions", {}).get("evidence_hashes", {}).get("allocation-binding.json")
            != digest(binding_bytes)):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Runtime receipt lost its launch-time allocation binding")
    return expected
