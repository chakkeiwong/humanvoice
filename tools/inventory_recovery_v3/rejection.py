"""One durable publisher for proven unstarted prospective invocations."""

import json
import os
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.failures import (
    RecoveryStop,
    failure_record,
    validate_failure,
)
from tools.inventory_recovery_v3.reservations import persist, regular_path

INTENT = "prelaunch-intent.json"
STREAMS = ("events.jsonl", "stderr.log", "response-envelope.json")


def identified(value):
    value = {key: item for key, item in value.items() if key != "identity"}
    return {**value, "identity": digest(value)}


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_ACCOUNTING", detail)


def inspect_outputs(directory, expected):
    require(not regular_path(directory / "process-start.json").exists(),
            "Zero-launch rejection conflicts with real process evidence")
    for name in STREAMS:
        path = regular_path(directory / name)
        require(not path.exists() or path.read_bytes() == b"", "Zero-launch stream is not empty")
    for name, value in expected.items():
        path = regular_path(directory / name)
        require(not path.exists() or digest(read_json(path)) == digest(value),
                "Conflicting retained rejection evidence: " + name)


def expected_records(intent):
    return {"prelaunch-rejection.json": intent["failure"],
        "qualification-capture.json": intent["qualification"],
        **({"local-cancellation.json": intent["cancellation"]} if intent["cancellation"] else {}),
        "process.json": intent["process"]}


def verify_association(plan, output, directory, intent):
    from humanvoice.automatic_recovery import attempt_calls
    from tools.inventory_recovery_v3.runtime_binding import identity

    association = intent["association"]
    index = association["index"]
    require(type(index) is int and 0 <= index < len(attempt_calls(plan)), "Invalid rejected attempt index")
    entries = read_json(regular_path(Path(output) / "allocation-ledger.json"))["calls"]
    matches = [row for row in entries if row["invocation_id"] == association["invocation_id"]]
    require(len(matches) == 1 and matches[0]["status"] in {"allocated_unknown", "incomplete"},
            "Rejection lost its exact native allocation")
    entry = matches[0]
    require(attempt_calls(plan)[index]["key"] == entry["key"], "Rejected attempt key changed")
    call = Path(output) / f"calls/{index:04d}"
    journal = read_json(regular_path(call / "call.json"))
    descriptor = read_json(regular_path(Path(output) / f"reconnect-attempts/{index:04d}.json"))
    request = read_json(regular_path(directory / "inputs/api-request.json"))
    expected = identity(plan, output, entry, index, descriptor, journal, directory, request)
    require(digest(expected) == digest(association)
            and regular_path(directory / "inputs/prompt.txt").read_bytes() == journal["request"]["prompt"].encode()
            and digest(read_json(regular_path(call / "runtime-binding.json"))) == digest(expected)
            and digest(read_json(regular_path(directory / "allocation-binding.json"))) == digest(expected),
            "Retained rejection lost its exact request binding")
    return expected


def complete(directory, intent):
    expected = expected_records(intent)
    marker = regular_path(directory / "qualification-capture.json")
    receipt = regular_path(directory / "record.json")
    if marker.exists() and read_json(marker) == {**intent["qualification"], "status": "verified"}:
        require(not receipt.exists(), "Completed receipt cannot change qualification evidence")
        inspect_outputs(directory, {key: value for key, value in expected.items()
                                   if key != "qualification-capture.json"})
        persist(marker, intent["qualification"])
    inspect_outputs(directory, expected)
    require(intent["cancellation"] is not None or not regular_path(directory / "local-cancellation.json").exists(),
            "Unexpected cancellation evidence")
    # A finished runtime receipt is immutable, including evidence membership.
    if receipt.exists():
        hashes = read_json(receipt).get("extensions", {}).get("evidence_hashes", {})
        for name in (*expected, *STREAMS, INTENT, "allocation-binding.json"):
            path = regular_path(directory / name)
            require(path.exists() and hashes.get(name) == digest(path.read_bytes()),
                    "Completed runtime receipt lost rejection evidence")
        return intent["failure"]
    for name in STREAMS:
        path = regular_path(directory / name)
        if not path.exists():
            with path.open("xb") as handle:
                handle.flush()
                os.fsync(handle.fileno())
    for name, value in expected.items():
        path = regular_path(directory / name)
        if not path.exists():
            persist(path, value)
    return intent["failure"]


def replay(plan, output, directory, *, owner, arguments, timeout):
    from tools.inventory_recovery_v3 import runtime

    directory = Path(directory)
    path = regular_path(directory / INTENT)
    if not path.exists():
        return None
    intent = read_json(path)
    require(set(intent) == {"version", "authority", "association", "failure", "qualification",
        "process", "cancellation", "identity"} and intent == identified(intent)
        and intent["version"] == "native-zero-launch-publication-v1"
        and intent["authority"] == digest(owner.authority.configuration),
        "Rejection intent changed its admitted authority")
    validate_failure(intent["failure"])
    require(intent["qualification"] == qualification(runtime, plan, arguments)
            and intent["process"] == process_record(runtime, timeout),
            "Rejection intent changed its command or no-launch proof")
    verify_association(plan, output, directory, intent)
    cancellation = intent["cancellation"]
    if cancellation is not None:
        require(cancellation == identified(cancellation)
                and cancellation.get("version") == "native-zero-launch-cancellation-v1"
                and cancellation.get("process_started") is False
                and cancellation.get("binding_identity") == intent["association"]["identity"]
                and cancellation.get("authority_identity") == intent["authority"]
                and cancellation.get("failure_identity") == intent["failure"]["identity"]
                and intent["failure"]["category"] == "USER_STOPPED"
                and isinstance(cancellation.get("stops"), list) and cancellation["stops"],
                "Rejection cancellation changed its identity")
        for stop in cancellation["stops"]:
            require(set(stop) == {"root", "contract", "stop_bytes", "stop_sha256"}
                    and {key: stop[key] for key in ("root", "contract")} in owner.authority.configuration["stop_bindings"]
                    and digest(stop["stop_bytes"].encode()) == stop["stop_sha256"]
                    and json.loads(stop["stop_bytes"]).get("status") == "USER_STOPPED",
                    "Rejection cancellation lost exact retained stop bytes")
    return complete(directory, intent)


def qualification(runtime, plan, arguments):
    return {"contract": runtime.contract(),
        "binding_hash": digest(runtime.implementation.qualified.routing.binding_for(plan["profile"])),
        "profile_hash": digest(plan["profile"]), "argv_hash": digest(arguments),
        "status": "rejected_before_process_start"}


def process_record(runtime, timeout):
    return {"status": "error", "returncode": None, "process_started": False,
        "elapsed_seconds": 0, "deadline_seconds": timeout, "group_quiescent": True,
        "remaining_group_members": [], "enforcement": runtime.implementation.qualified.capture.ENFORCEMENT}


def publish(plan, output, directory, *, owner, arguments, timeout, error):
    from tools.inventory_recovery_v3 import cancellation, runtime
    from tools.inventory_recovery_v3.runtime_binding import bind

    directory = Path(directory)
    retained = replay(plan, output, directory, owner=owner, arguments=arguments, timeout=timeout)
    failure = failure_record(error, phase="native_launch")
    if retained is not None:
        require(retained == failure, "Repeated rejection changed its failure")
        return retained
    require(not regular_path(directory / "process.json").exists()
            and not regular_path(directory / "record.json").exists(),
            "Unproven retained process evidence requires reconciliation")
    inspect_outputs(directory, {})
    association = bind(plan, output, directory, owner=owner, rejected=True)
    proof = cancellation.describe(plan, output, directory, owner, failure, association=association)
    intent = identified({"version": "native-zero-launch-publication-v1",
        "authority": digest(owner.authority.configuration), "association": association,
        "failure": failure, "qualification": qualification(runtime, plan, arguments),
        "process": process_record(runtime, timeout), "cancellation": proof})
    expected = expected_records(intent)
    # Native checks may already have published a verified pre-spawn marker.
    marker = regular_path(directory / "qualification-capture.json")
    if marker.exists():
        require(read_json(marker) in (expected["qualification-capture.json"],
            {**expected["qualification-capture.json"], "status": "verified"}),
            "Qualification marker conflicts with rejected invocation")
    for name in ("prelaunch-rejection.json", "local-cancellation.json"):
        require(not regular_path(directory / name).exists(), "Uncommitted rejection evidence already exists")
    persist(directory / INTENT, intent)
    if marker.exists() and read_json(marker) != expected["qualification-capture.json"]:
        persist(marker, expected["qualification-capture.json"])
    return complete(directory, intent)
