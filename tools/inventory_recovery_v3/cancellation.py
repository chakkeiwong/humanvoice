"""Retain exact zero-launch stops and require bound authorization for retirement."""

import json
import math
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v2 import control
from tools.inventory_recovery_v3.failures import RecoveryStop, validate_failure
from tools.inventory_recovery_v3.reservations import persist, regular_path


def stop_bindings(configuration):
    bindings = configuration.get("stop_bindings", [])
    if (not isinstance(bindings, list)
            or any(not isinstance(row, dict) or set(row) != {"root", "contract"} for row in bindings)
            or len({row["root"] for row in bindings}) != len(bindings)):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Admission lost its canonical stop authorities")
    for binding in bindings:
        path = regular_path(Path(binding["root"]) / "user-stop.json")
        if str(path.parent) != binding["root"]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Stop authority requires a canonical absolute root")
    return bindings


def require_running(configuration):
    for binding in stop_bindings(configuration):
        control.require_running(binding["root"], contract=binding["contract"])


def describe(plan, output, directory, owner, failure, *, association):
    if failure["category"] != "USER_STOPPED":
        return None
    stops = []
    for binding in stop_bindings(owner.authority.configuration):
        path = regular_path(Path(binding["root"]) / "user-stop.json")
        if not path.exists():
            continue
        content = path.read_bytes().decode("utf-8")
        if json.loads(content).get("status") != "USER_STOPPED":
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Stop record lost its explicit user status")
        try:
            control.require_running(binding["root"], contract=binding["contract"])
        except RuntimeError as error:
            if getattr(error, "category", None) != "USER_STOPPED":
                raise
            stops.append({**binding, "stop_bytes": content, "stop_sha256": digest(content.encode())})
    if not stops:
        return None
    value = {"version": "native-zero-launch-cancellation-v1",
             "binding_identity": association["identity"], "stops": stops,
             "authority_identity": digest(owner.authority.configuration),
             "failure_identity": failure["identity"], "process_started": False}
    return {**value, "identity": digest(value)}


def capture(plan, output, directory, owner, failure):
    from tools.inventory_recovery_v3.runtime_binding import bind

    if failure["category"] != "USER_STOPPED":
        return None
    association = bind(plan, output, directory, owner=owner, rejected=True)
    proof = describe(plan, output, directory, owner, failure, association=association)
    if proof is not None:
        persist(regular_path(Path(directory) / "local-cancellation.json"), proof)
    return proof


def evidence(plan, output, entry, index, journal, *, raw=None):
    from tools.inventory_recovery_v3.runtime_binding import verify

    def content(relative):
        return raw(relative) if raw else regular_path(Path(output) / relative).read_bytes()

    def read(relative):
        return json.loads(content(relative))

    reference = journal.get("runtime_record", {})
    relative = Path(reference.get("path", ""))
    if relative.is_absolute() or ".." in relative.parts or relative.name != "record.json":
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Cancellation lost its confined runtime reference")
    folder = str(Path("snapshots/primary/snapshot") / relative.parent)
    receipt = read(folder + "/record.json")
    hashes = receipt.get("extensions", {}).get("evidence_hashes", {})
    if "local-cancellation.json" not in hashes:
        return None
    association = verify(plan, output, entry, index, journal, raw=raw)
    proof = read(folder + "/local-cancellation.json")
    failure = validate_failure(read(folder + "/prelaunch-rejection.json"))
    process = read(folder + "/process.json")
    if (proof.get("version") != "native-zero-launch-cancellation-v1"
            or proof.get("identity") != digest({key: value for key, value in proof.items() if key != "identity"})
            or proof.get("binding_identity") != association["identity"]
            or proof.get("failure_identity") != failure["identity"]
            or failure["category"] != "USER_STOPPED"
            or proof.get("process_started") is not False
            or not proof.get("authority_identity") or not proof.get("stops")
            or process.get("process_started") is not False
            or process.get("status") != "error" or process.get("returncode") is not None
            or process.get("group_quiescent") is not True or process.get("remaining_group_members") != []
            or "process-start.json" in hashes
            or receipt.get("termination") != "error"
            or journal.get("status") != "failed"
            or any(receipt.get(name) is not None for name in ("input_tokens", "output_tokens"))
            or any(content(folder + "/" + name) for name in
                   ("events.jsonl", "stderr.log", "response-envelope.json"))):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Cancellation lacks exact zero-launch proof")
    for stop in proof["stops"]:
        if (set(stop) != {"root", "contract", "stop_bytes", "stop_sha256"}
                or digest(stop["stop_bytes"].encode()) != stop["stop_sha256"]
                or json.loads(stop["stop_bytes"]).get("status") != "USER_STOPPED"):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Cancellation stop identity changed")
    for name, expected in hashes.items():
        if Path(name).is_absolute() or ".." in Path(name).parts or digest(content(folder + "/" + name)) != expected:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Cancellation receipt evidence changed")
    if raw is None and any((root / relative.parent / "process-start.json").exists() for root in
                           (Path(plan["snapshot"]), Path(output) / "snapshots/primary/snapshot")):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Cancellation conflicts with provider process evidence")
    return {**proof, "runtime_record_hash": reference["hash"]}


def require_resume(owner, proof):
    from tools.inventory_recovery_v3 import control_history

    owner.check()
    configuration = owner.authority.configuration
    bindings = stop_bindings(configuration)
    if proof["authority_identity"] != digest(configuration):
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Cancellation belongs to another admitted campaign")
    if any({name: stop[name] for name in ("root", "contract")} not in bindings for stop in proof["stops"]):
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Cancellation lost its admitted control root")
    path = regular_path(owner.output / "cancellation-authorizations" / (proof["identity"] + ".json"))
    value = {"version": "native-cancellation-authorization-v1",
             **{name: proof[name] for name in
                ("binding_identity", "authority_identity", "runtime_record_hash")},
             "cancellation_identity": proof["identity"]}
    if path.exists():
        retained = read_json(path)
        if (retained.get("identity") != digest({key: item for key, item in retained.items() if key != "identity"})
                or any(retained.get(name) != item for name, item in value.items())
                or len(retained.get("stops", [])) != len(proof["stops"])):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Retained cancellation authorization changed")
        for stop, authorized in zip(proof["stops"], retained["stops"], strict=True):
            if {name: authorized.get(name) for name in stop} != stop:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Cancellation authorization changed its stop")
            validate_authorization(authorized)
    else:
        authorized_stops = []
        for stop in proof["stops"]:
            current = read_authorization(stop)
            if current["stop_bytes"] != stop["stop_bytes"]:
                raise RecoveryStop("USER_STOPPED", "Unretired cancellation requires its exact stop authorization")
            authorized_stops.append(current)
        value["stops"] = authorized_stops
        retained = {**value, "identity": digest(value)}
        owner.check()
        path.parent.mkdir(parents=True, exist_ok=True)
        control_history.initialize(path, retained)
        persist(path, retained)
    control_history.advance(owner, path, retained)
    owner.check()
    return [{"stop_sha256": stop["stop_sha256"], "resume_sha256": stop["resume_sha256"],
             "authorization_identity": retained["identity"]} for stop in retained["stops"]]


def validate_authorization(value):
    stop, resume = json.loads(value["stop_bytes"]), json.loads(value["resume_bytes"])
    if (stop.get("status") != "USER_STOPPED"
            or type(stop.get("requested_at")) not in (int, float)
            or not math.isfinite(stop["requested_at"]) or stop["requested_at"] <= 0
            or not isinstance(stop.get("request_id"), str) or not stop["request_id"]
            or value.get("stop_sha256") != digest(value["stop_bytes"].encode())
            or value.get("resume_sha256") != digest(value["resume_bytes"].encode())
            or resume.get("stop_sha256") != value["stop_sha256"]
            or resume.get("contract") != value["contract"]
            or resume.get("authorized_by") != "user" or resume.get("action") != "explicit-resume"):
        raise RecoveryStop("USER_STOPPED", "Cancellation requires exact source-bound resume evidence")
    return value


def read_authorization(binding):
    path = regular_path(Path(binding["root"]) / "user-stop.json")
    resume = regular_path(path.with_name("resume-authorization.json"))
    if not path.exists() or not resume.exists():
        raise RecoveryStop("USER_STOPPED", "Cancellation requires its retained stop and explicit resume")
    stop_bytes, resume_bytes = path.read_bytes().decode("utf-8"), resume.read_bytes().decode("utf-8")
    value = {name: binding[name] for name in ("root", "contract")}
    value.update(stop_bytes=stop_bytes, stop_sha256=digest(stop_bytes.encode()),
                 resume_bytes=resume_bytes, resume_sha256=digest(resume_bytes.encode()))
    return validate_authorization(value)
