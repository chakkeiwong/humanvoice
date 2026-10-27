"""Finish a persisted native result after a ledger-commit crash cut."""

import os
from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_transport_continuation import immutable


def pending_result(output, plan, ledger, *, owner):
    from tools.inventory_recovery_v3 import execution, runtime
    from tools.inventory_recovery_v3.runtime_binding import verify

    owner.check()
    output = Path(output)
    if owner.output != output.absolute() or owner.plan != plan:
        raise ValueError("Reconciliation lost its admitted native stage")
    ledger.reload()
    pending = [entry for entry in ledger.record["calls"] if entry["status"] == "allocated_unknown"]
    if not pending:
        return False
    if len(pending) != 1 or pending[0] != ledger.record["calls"][-1]:
        raise execution.RecoveryBlocked("BLOCKED_ACCOUNTING", "Uncertain allocations are not a single tail")
    descriptors = runtime.implementation.automatic_recovery.execution_fds()
    expected = (output / "executor.lock").stat()
    if not descriptors or not any(
            (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino) == (expected.st_dev, expected.st_ino)
            for descriptor in descriptors):
        raise execution.RecoveryBlocked("BLOCKED_ACCOUNTING", "Reconciliation requires exclusive executor ownership")
    if (output / "allocation-seal.json").exists():
        raise execution.RecoveryBlocked("BLOCKED_ACCOUNTING", "Sealed evidence cannot be reconciled in place")
    entry = deepcopy(pending[0])
    calls = runtime.implementation.automatic_recovery.attempt_calls(plan)
    index = next(index for index, call in enumerate(calls) if call["key"] == entry["key"])
    directory = output / f"calls/{index:04d}"
    paths = [directory / name for name in ("call.json", "result.json")]
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise execution.RecoveryBlocked("BLOCKED_ACCOUNTING", "Uncertain allocation lacks a persisted native result")
    journal, result = (read_json(path) for path in paths)
    reference = journal.get("runtime_record")
    if (not reference or entry.get("result_hash") is not None
            or journal.get("invocation_id") != entry["invocation_id"]
            or journal.get("call_contract_hash") != entry["input_hash"]
            or result.get("input_hash") != entry["input_hash"]
            or result.get("request_hash") != digest(journal.get("request"))
            or journal.get("request_hash") != result["request_hash"]
            or result.get("evidence_error") is not None
            or result.get("status") not in {"complete", "incomplete"}):
        raise execution.RecoveryBlocked("BLOCKED_ACCOUNTING", "Persisted result lost its native invocation binding")
    record = runtime.implementation.capture.validate_record(plan["snapshot"], reference)
    folder = Path(plan["snapshot"]) / Path(reference["path"]).parent
    process = read_json(folder / "process.json")
    request = read_json(folder / "inputs/api-request.json")
    if (process.get("group_quiescent") is not True
            or request.get("profile") != plan["profile"]
            or request.get("source_hash") != plan["bindings"]["source"]
            or request.get("implementation") != plan["bindings"]["implementation"]
            or request.get("prompt_hash") != digest(journal["request"]["prompt"])
            or (folder / "inputs/prompt.txt").read_text() != journal["request"]["prompt"]
            or any(request.get(key) != journal["request"].get(key)
                   for key in ("purpose", "response_schema", "system_prompt"))):
        raise execution.RecoveryBlocked("BLOCKED_ACCOUNTING", "Crash receipt lost request scope or process quiescence")
    copied = output / "snapshots/primary/snapshot" / Path(reference["path"]).parent
    if not copied.exists():
        execution.predecessor.manuscript.capture_runtime(Path(plan["snapshot"]), reference, output)
    if read_json(copied / "record.json") != record:
        raise ValueError("Crash receipt copy differs from its native source")
    for name, expected in record["extensions"]["evidence_hashes"].items():
        relative = Path(name)
        if (relative.is_absolute() or ".." in relative.parts or (copied / name).is_symlink()
                or digest((copied / name).read_bytes()) != expected):
            raise ValueError("Copied crash evidence changed")
    verify(plan, output, entry, index, journal)
    if result["status"] == "incomplete":
        from tools.inventory_recovery_v3.cancellation import evidence, require_resume

        cancellation = evidence(plan, output, entry, index, journal)
        if cancellation is not None:
            require_resume(owner, cancellation)
    if result["status"] == "complete":
        if result.get("error") or any(type(record.get(key)) is not int or record[key] < 0
                                      for key in ("input_tokens", "output_tokens")):
            raise ValueError("Completed crash result lacks valid reported usage")
        execution.predecessor.restored_response(Path(plan["snapshot"]), plan["profile"], journal)
    elif record["termination"] == "complete":
        raise execution.RecoveryBlocked("BLOCKED_ACCOUNTING", "Incomplete result contradicts completed receipt")
    proposed = deepcopy(ledger.record["calls"])
    proposed[-1].update(status=result["status"], result_hash=digest(result))
    execution.layout(output, plan, proposed)
    owner.check()
    if result["status"] == "complete":
        ledger.reconcile(entry, record["input_tokens"], record["output_tokens"])
    ledger.finish(entry, result, directory / "result.json")
    immutable(output / "reconciliations" / (entry["invocation_id"] + ".json"), {
        "plan_identity": plan["plan_identity"], "invocation_id": entry["invocation_id"],
        "runtime_record": reference, "result_hash": digest(result), "new_provider_calls": 0})
    return True
