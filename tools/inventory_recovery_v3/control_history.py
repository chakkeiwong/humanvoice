"""Commit monotonic control history without treating missing records as empty."""

from copy import deepcopy

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path


def save(path, value):
    value = {key: item for key, item in value.items() if key != "identity"}
    persist(path, {**value, "identity": digest(value)})


def initial(authorization):
    return {"version": "cancellation-control-head-v1", "authorization_identity": authorization["identity"],
            "histories": {digest(stop): [] for stop in authorization["stops"]}, "pending": None}


def initialize(path, authorization):
    head = regular_path(path.with_name(path.stem + "-head.json"))
    expected = initial(authorization)
    if head.exists():
        if read_json(head) != {**expected, "identity": digest(expected)}:
            raise RecoveryStop("USER_STOPPED", "Unpublished authorization conflicts with retained control history")
    else:
        save(head, expected)


def newer(previous, current):
    import json

    from tools.inventory_recovery_v3.cancellation import validate_authorization

    validate_authorization(previous)
    validate_authorization(current)
    prior_stop, next_stop = json.loads(previous["stop_bytes"]), json.loads(current["stop_bytes"])
    if (any(previous.get(name) != current.get(name) for name in ("root", "contract"))
            or next_stop["requested_at"] <= prior_stop["requested_at"]
            or next_stop["request_id"] == prior_stop["request_id"]):
        raise RecoveryStop("USER_STOPPED", "Current control event rolled back its retained history")


def advance(owner, path, authorization):
    from tools.inventory_recovery_v3.cancellation import read_authorization

    head_path = regular_path(path.with_name(path.stem + "-head.json"))
    if not head_path.exists():
        raise RecoveryStop("USER_STOPPED", "Retained authorization lost its monotonic control head")
    head = read_json(head_path)
    base = initial(authorization)
    if (not isinstance(head, dict)
            or head.get("identity") != digest({key: item for key, item in head.items() if key != "identity"})
            or any(head.get(name) != base[name] for name in ("version", "authorization_identity"))
            or not isinstance(head.get("histories"), dict)
            or set(head["histories"]) != set(base["histories"])
            or any(not isinstance(rows, list) for rows in head["histories"].values())):
        raise RecoveryStop("USER_STOPPED", "Retained control head changed its authorization binding")
    folder = regular_path(path.parent / path.stem / "unused.json").parent
    latest, files = {}, {}

    def verify(transition, origin, previous, generation):
        if (not isinstance(transition, dict)
                or transition.get("version") != "cancellation-stop-supersession-v2"
                or transition.get("authorization_identity") != authorization["identity"]
                or transition.get("identity") != digest({key: item for key, item in transition.items() if key != "identity"})
                or transition.get("origin") != origin
                or transition.get("previous") != previous
                or type(transition.get("generation")) is not int or transition["generation"] != generation
                or not isinstance(transition.get("current"), dict)):
            raise RecoveryStop("USER_STOPPED", "Retained control transition lost its exact chain")
        newer(previous, transition["current"])
        return transition["current"]

    for stop in authorization["stops"]:
        identity, previous = digest(stop), stop
        for position, reference in enumerate(head["histories"][identity], 1):
            if not isinstance(reference, dict):
                raise RecoveryStop("USER_STOPPED", "Control head lost its committed transition membership")
            relative = reference.get("file")
            if not isinstance(relative, str) or relative != reference.get("identity", "") + ".json":
                raise RecoveryStop("USER_STOPPED", "Control head lost its committed transition membership")
            target = regular_path(folder / relative)
            if not target.exists() or digest(target.read_bytes()) != reference.get("sha256"):
                raise RecoveryStop("USER_STOPPED", "Committed control transition disappeared or changed")
            transition = read_json(target)
            if not isinstance(transition, dict) or transition.get("identity") != reference["identity"]:
                raise RecoveryStop("USER_STOPPED", "Control transition identity changed")
            previous = verify(transition, stop, previous, position)
            files[relative] = transition
        latest[identity] = previous
    pending = head.get("pending")
    if pending is not None:
        if not isinstance(pending, dict) or not isinstance(pending.get("origin"), dict):
            raise RecoveryStop("USER_STOPPED", "Pending control transition lost its origin")
        identity = digest(pending["origin"])
        origin = next((stop for stop in authorization["stops"] if digest(stop) == identity), None)
        if origin is None:
            raise RecoveryStop("USER_STOPPED", "Pending control transition lost its origin")
        verify(pending, origin, latest[identity], len(head["histories"][identity]) + 1)
        files[pending["identity"] + ".json"] = pending
    if any(target.name not in files for target in folder.glob("*.json")):
        raise RecoveryStop("USER_STOPPED", "Control head lost a retained transition")

    def commit(transition):
        target = regular_path(folder / (transition["identity"] + ".json"))
        owner.check()
        folder.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if read_json(target) != transition:
                raise RecoveryStop("USER_STOPPED", "Pending control transition bytes changed")
        else:
            persist(target, transition)
        identity = digest(transition["origin"])
        head["histories"][identity].append({"file": target.name, "identity": transition["identity"],
                                           "sha256": digest(target.read_bytes())})
        head["pending"] = None
        owner.check()
        save(head_path, head)
        latest[identity] = transition["current"]

    if pending is not None:
        commit(pending)
    for stop in authorization["stops"]:
        identity = digest(stop)
        current = read_authorization(stop)
        previous = latest[identity]
        if current["stop_bytes"] == previous["stop_bytes"]:
            continue
        newer(previous, current)
        value = {"version": "cancellation-stop-supersession-v2",
                 "authorization_identity": authorization["identity"], "origin": stop,
                 "previous": previous, "current": current, "generation": len(head["histories"][identity]) + 1}
        transition = {**value, "identity": digest(value)}
        head["pending"] = deepcopy(transition)
        owner.check()
        save(head_path, head)
        commit(transition)
