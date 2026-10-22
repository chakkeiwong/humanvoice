"""Retry only fully evidenced, response-free inventory process deadlines."""

import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from humanvoice.automatic_evaluation import evidence_path
from tools import inventory_stage_runtime as inventory
from tools import overload_network_runtime as overload
from tools import parallel_verification_replay as verification
from tools.request_timeout_recovery import WARNING

ROOT, network = inventory.ROOT, inventory.network
VERSION = "inventory-response-free-deadline-v1"
FIELD = "inventory_deadline_policy"
NATIVE = (overload.failure_evidence,)
SETTLEMENT = (inventory.verify_settlement,)
ACTIVE = ContextVar("inventory_deadline_runtime", default=False)


def policy():
    return {"version": VERSION, "implementation": digest(Path(__file__).read_bytes()),
            "deadline_seconds": 900, "backoff_seconds": 900, "maximum_total": 16,
            "unknown_tokens_released": False, "scope": "inventory-only", "changed_request": False}


def classify(root, directory, proof, *, raw=None):
    if proof.get("reason") != "unproven_transport_failure" or not proof.get("provider_receipt"):
        return proof
    root, directory = Path(root), Path(directory)

    def content(path):
        relative = str(path.relative_to(root))
        return raw(relative) if raw is not None else evidence_path(root, relative).read_bytes()

    journal = json.loads(content(directory / "call.json"))
    folder = root / "snapshots/primary/snapshot" / Path(journal["runtime_record"]["path"]).parent
    process = json.loads(content(folder / "process.json"))
    events = [json.loads(line) for line in content(folder / "events.jsonl").decode().splitlines() if line.strip()]
    elapsed = process.get("elapsed_seconds")
    if (process.get("status") != "timeout" or process.get("returncode") != -9
            or process.get("process_started") is not True or process.get("deadline_seconds") != 900
            or process.get("enforcement") != "process-group-deadline-only"
            or type(elapsed) not in (int, float) or not 900 <= elapsed <= 960
            or not events or events[0].get("type") != "thread.started"
            or events[-1] != {"type": "turn.started"}):
        return proof
    if (set(events[0]) != {"type", "thread_id"}
            or any(event.get("type") != "item.completed" or set(event) != {"type", "item"}
                   or set(event["item"]) != {"id", "type", "message"}
                   or event["item"].get("type") != "error"
                   or not (event["item"].get("message", "").startswith("Under-development features enabled:")
                           or event["item"].get("message") == WARNING) for event in events[1:-1])):
        return proof
    return {**proof, "eligible": True, "reason": "response_free_process_deadline"}


def failure_evidence(root, directory, plan, entry, **keywords):
    proof = NATIVE[0](root, directory, plan, entry, **keywords)
    if FIELD not in plan:
        return proof
    if (plan[FIELD] != policy() or plan.get("stage") != "inventory"
            or plan.get("inventory_stage_extension") != inventory.extension()
            or plan.get("recovery") != network.policy()):
        raise ValueError("Inventory deadline recovery changed its frozen scope or bounds")
    return classify(root, directory, proof, raw=keywords.get("raw"))


def verify_settlement(output):
    with inventory.history.archive.access():
        plan = read_json(Path(output) / "plan.json")
        if FIELD not in plan:
            return SETTLEMENT[0](output)
        if plan[FIELD] != policy():
            raise ValueError("Inventory deadline settlement policy changed")
        with inventory.scope.accounting_scope(), inventory.pipeline(), runtime():
            return SETTLEMENT[0](output)


@contextmanager
def runtime():
    if ACTIVE.get():
        yield
        return
    token = ACTIVE.set(True)
    try:
        with overload.runtime(), network.replaced_aliases(NATIVE[0], failure_evidence), (
                network.replaced_aliases(SETTLEMENT[0], verify_settlement)), (
                network.replaced_aliases(verification.verify_settlement, verify_settlement)):
            yield
    finally:
        ACTIVE.reset(token)
