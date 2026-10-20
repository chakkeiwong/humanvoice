"""Prospectively classify proven response-free gateway overloads."""

import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from humanvoice.artifacts import digest
from tools import delayed_network_runtime as network

ROOT = Path(__file__).resolve().parents[1]
VERSION = "response-free-overload-v1"
DIAGNOSTIC = "stream disconnected before completion: Our servers are currently overloaded. Please try again later."
NATIVES = (network.failure_evidence,)
ACTIVE = ContextVar("overload_network_runtime", default=False)


def extension():
    return {"version": VERSION, "diagnostic": DIAGNOSTIC, "backoff_seconds": 900,
            "implementation": digest(Path(__file__).read_bytes()), "unknown_tokens_released": False}


def classify(root, directory, proof, *, raw=None):
    if proof.get("reason") != "unclassified_provider_failure" or not proof.get("provider_receipt"):
        return proof
    root, directory = Path(root), Path(directory)

    def content(path):
        return raw(str(path.relative_to(root))) if raw is not None else path.read_bytes()

    journal = json.loads(content(directory / "call.json"))
    folder = root / "snapshots/primary/snapshot" / Path(journal["runtime_record"]["path"]).parent
    events = [json.loads(line) for line in content(folder / "events.jsonl").decode().splitlines() if line.strip()]
    messages = [event.get("message") for event in events if event.get("type") == "error"]
    messages += [event.get("error", {}).get("message") for event in events if event.get("type") == "turn.failed"]
    warnings = [event["item"].get("message", "") for event in events
                if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "error"]
    allowed = ("Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed; "
               "enable `features.code_mode_host` and install `codex-code-mode-host`.")
    if (messages and all(message == DIAGNOSTIC for message in messages)
            and all(message.startswith("Under-development features enabled:") or message == allowed for message in warnings)):
        return {**proof, "eligible": True, "reason": "stream_server_overloaded"}
    return proof


def failure_evidence(root, directory, plan, entry, **keywords):
    proof = NATIVES[0](root, directory, plan, entry, **keywords)
    policy = plan.get("overload_network_extension")
    if policy is None:
        return proof
    if policy != extension():
        raise ValueError("Overload recovery changed its prospective policy")
    return classify(root, directory, proof, raw=keywords.get("raw"))


@contextmanager
def runtime():
    if ACTIVE.get():
        yield
        return
    token = ACTIVE.set(True)
    try:
        with network.replaced_aliases(NATIVES[0], failure_evidence):
            yield
    finally:
        ACTIVE.reset(token)
