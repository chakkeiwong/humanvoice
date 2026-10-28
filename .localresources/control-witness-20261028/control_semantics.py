"""Exact stop/resume semantics for a separately authenticated host publisher.

This module is pure: constructing a command or genesis does not authorize it.
The protected writer and admitted reader own provenance and publication.
"""

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path

from control_witness import VERSION as WITNESS_VERSION
from control_witness import encode, hash_value, identity, require

VERSION = "inventory-control-publication-v1"
EVIDENCE = "runtime-authenticated-stop-history-v1"
FLOOR = "runtime-initial-stop-floor-v1"


def native_digest(value):
    """Exact compatibility with humanvoice.artifacts.digest, without host imports."""
    if isinstance(value, str):
        value = value.encode("utf-8")
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def identified(value):
    value = {key: item for key, item in value.items() if key != "identity"}
    return {**value, "identity": native_digest(value)}


def path(value):
    selected = Path(value)
    require(isinstance(value, str) and selected.anchor == "/" and str(selected) == value
            and ".." not in selected.parts, "Control root must be canonical")
    return selected


def stop(content):
    require(isinstance(content, str) and bool(content), "Stop bytes are missing")
    value = json.loads(content)
    require(isinstance(value, dict) and value.get("status") == "USER_STOPPED"
            and isinstance(value.get("request_id"), str) and bool(value["request_id"])
            and type(value.get("requested_at")) in (int, float)
            and math.isfinite(value["requested_at"]) and value["requested_at"] > 0,
            "Stop identity or time is malformed")
    return value


def append(rows, content):
    value = stop(content)
    previous = [stop(row["stop_bytes"]) for row in rows]
    require(value["request_id"] not in {row["request_id"] for row in previous}
            and (not previous or value["requested_at"] > previous[-1]["requested_at"]),
            "Stop request reused or time did not advance")
    return [*rows, identified({"sequence": len(rows) + 1,
        "previous": rows[-1]["identity"] if rows else None, "stop_bytes": content})]


def resume(binding, rows, content):
    require(bool(rows) and isinstance(content, str), "Resume requires the latest exact stop")
    value = json.loads(content)
    require(isinstance(value, dict) and value.get("action") == "explicit-resume"
            and value.get("authorized_by") == "user"
            and native_digest(value.get("contract")) == native_digest(binding["contract"])
            and value.get("stop_sha256") == native_digest(rows[-1]["stop_bytes"]),
            "Resume does not bind the latest stop and original contract")
    return value


def genesis(configuration, directory, approved_resumes):
    """Host action must explicitly approve this exact complete initial resume set."""
    directory = str(path(str(directory)))
    floor = configuration["stop_floor"]
    bindings = configuration["stop_bindings"]
    require(isinstance(bindings, list) and bool(bindings)
            and isinstance(floor, dict) and set(floor) == {"version", "roots", "identity"}
            and floor == identified(floor) and floor["version"] == FLOOR
            and isinstance(floor["roots"], list)
            and all(isinstance(row, dict) and set(row) == {"root", "contract", "stop_bytes"}
                    for row in floor["roots"])
            and [{k: row[k] for k in ("root", "contract")} for row in floor["roots"]] == bindings,
            "Genesis lost its exact transfer-time stop floor")
    roots = [row["root"] for row in bindings]
    require(len(set(roots)) == len(roots) and isinstance(approved_resumes, dict)
            and set(approved_resumes) == set(roots), "Initial control root/resume membership differs")
    histories = {}
    for row in floor["roots"]:
        root = path(row["root"])
        require(root != Path(directory) and not Path(directory).is_relative_to(root)
                and not root.is_relative_to(directory), "Control projection directory overlaps stop roots")
        rows = append([], row["stop_bytes"]) if row["stop_bytes"] is not None else []
        histories[str(root)] = rows
        if approved_resumes[str(root)] is not None:
            resume(row, rows, approved_resumes[str(root)])
    return identity({"version": VERSION, "configuration": native_digest(configuration),
        "directory": directory, "bindings": deepcopy(bindings), "stop_floor": deepcopy(floor),
        "initial": {"histories": histories, "resumes": deepcopy(approved_resumes)}})


def validate_anchor(anchor):
    require(isinstance(anchor, dict) and set(anchor) == {"version", "configuration", "directory",
            "bindings", "stop_floor", "initial", "identity"}
            and anchor["version"] == VERSION and hash_value(anchor["configuration"])
            and anchor == identity({k: v for k, v in anchor.items() if k != "identity"}),
            "Control genesis is malformed or changed")
    path(anchor["directory"])
    expected = genesis({"stop_bindings": anchor["bindings"], "stop_floor": anchor["stop_floor"]},
                       anchor["directory"], anchor["initial"]["resumes"])
    require(expected["initial"] == anchor["initial"], "Genesis initial histories changed")
    return anchor


def apply(anchor, state, command):
    require(isinstance(command, dict) and set(command) == {"request_id", "action", "root", "content"}
            and isinstance(command["request_id"], str) and 0 < len(command["request_id"]) <= 256
            and command["action"] in {"stop", "resume"}, "Control command schema differs")
    binding = next((row for row in anchor["bindings"] if row["root"] == command["root"]), None)
    require(binding is not None, "Control command selected a foreign root")
    root, content = command["root"], command["content"]
    result = deepcopy(state)
    if command["action"] == "stop":
        value = stop(content)
        require(set(value) == {"status", "request_id", "requested_at"}
                and value["request_id"] == command["request_id"], "Stop differs from its host request")
        times = [stop(rows[-1]["stop_bytes"])["requested_at"]
                 for rows in state["histories"].values() if rows]
        require(not times or value["requested_at"] > max(times), "Host stop time did not advance")
        result["histories"][root] = append(state["histories"][root], content)
        result["resumes"][root] = None
    else:
        require(state["resumes"][root] is None, "Latest stop is already resumed")
        value = resume(binding, state["histories"][root], content)
        require(set(value) == {"action", "authorized_by", "contract", "stop_sha256", "request_id"}
                and value["request_id"] == command["request_id"], "Resume differs from its host request")
        result["resumes"][root] = content
    return result


def command(anchor, state, action, root, request_id, *, now):
    """Only the authenticated writer supplies its trusted clock to this helper."""
    binding = next((row for row in anchor["bindings"] if row["root"] == root), None)
    require(binding is not None and action in {"stop", "resume"}, "Unknown control action/root")
    if action == "stop":
        content = encode({"status": "USER_STOPPED", "request_id": request_id, "requested_at": now})
    else:
        rows = state["histories"][root]
        require(bool(rows), "Resume requires a retained stop")
        content = encode({"action": "explicit-resume", "authorized_by": "user", "request_id": request_id,
                          "contract": binding["contract"], "stop_sha256": native_digest(rows[-1]["stop_bytes"])})
    value = {"action": action, "root": root, "request_id": request_id, "content": content}
    apply(anchor, state, value)
    return value


def replay(anchor, snapshot):
    validate_anchor(anchor)
    require(isinstance(snapshot, dict) and set(snapshot) == {"version", "genesis", "configuration",
        "nonce", "sequence", "committed_head", "pending", "events", "publication", "identity"}
        and snapshot == identity({k: v for k, v in snapshot.items() if k != "identity"})
        and snapshot["version"] == WITNESS_VERSION and snapshot["genesis"] == anchor["identity"]
        and snapshot["configuration"] == anchor["configuration"] and hash_value(snapshot["nonce"])
        and snapshot["publication"] in {"absent", "pending", "ready"}
        and type(snapshot["sequence"]) is int and snapshot["sequence"] >= 0
        and isinstance(snapshot["events"], list) and len(snapshot["events"]) == snapshot["sequence"],
        "Witness snapshot lost its exact genesis/configuration binding")
    state, previous, seen = deepcopy(anchor["initial"]), anchor["identity"], set()

    def verify(event, number, prior):
        require(isinstance(event, dict) and set(event) == {"version", "genesis", "configuration",
            "sequence", "previous", "command", "identity"}
            and event == identity({k: v for k, v in event.items() if k != "identity"})
            and event["version"] == WITNESS_VERSION and event["genesis"] == anchor["identity"]
            and event["configuration"] == anchor["configuration"]
            and type(event["sequence"]) is int and event["sequence"] == number
            and event["previous"] == prior and event["command"]["request_id"] not in seen,
            "Witness event sequence or request membership changed")
        seen.add(event["command"]["request_id"])

    for number, event in enumerate(snapshot["events"], 1):
        verify(event, number, previous)
        state = apply(anchor, state, event["command"])
        previous = event["identity"]
    require(previous == snapshot["committed_head"], "Witness head differs from exact event prefix")
    after = None
    if snapshot["pending"] is not None:
        event = snapshot["pending"]
        verify(event, snapshot["sequence"] + 1, previous)
        after = apply(anchor, state, event["command"])
    return state, after


def projections(state):
    return {str(Path(root) / name): value for root, rows in state["histories"].items()
            for name, value in (("user-stop.json", rows[-1]["stop_bytes"] if rows else None),
                                ("resume-authorization.json", state["resumes"][root]))}


def evidence(anchor, state):
    return identified({"version": EVIDENCE, "configuration": anchor["configuration"], **deepcopy(state)})
