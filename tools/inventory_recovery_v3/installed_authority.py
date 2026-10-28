"""Derive the fixed installed historical authority without granting execution."""

import json
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.reservations import regular_path


def canonical_path(value):
    path = Path(value)
    if path.anchor != "/" or str(path) != str(value) or ".." in path.parts:
        raise ValueError("Installed authority requires canonical absolute paths")
    regular_path(path / ".authority-path-check")
    return path


def capture():
    from tools import inventory_history_live as live
    from tools import inventory_history_live_admission as admission
    from tools import inventory_history_services as services
    from tools import review_inventory_recovery_v3 as candidate
    from tools.inventory_recovery_v2 import campaign, program

    evidence = {}

    def observe(path):
        path = regular_path(canonical_path(path))
        content = path.read_bytes()
        evidence[str(path)] = digest(content)
        value = json.loads(content)
        if not isinstance(value, dict):
            raise TypeError("Installed authority evidence must be an object")
        return value

    def reference(value):
        return observe(admission.evidence(value))

    source = candidate.sources()
    root = canonical_path(live.SUPERVISION)
    record = observe(live.ADMISSION)
    adopted = observe(live.ADOPTION)
    configuration = observe(root / "config.json")
    contract = live.contract()
    if (adopted != live.adoption() or configuration != live.config()
            or record.get("status") != "ADMITTED"
            or record.get("contract") != contract
            or record.get("config_identity") != digest(configuration)
            or record.get("approval_policy") != "on-request"
            or record.get("approvals_reviewer") != "user"):
        raise ValueError("Installed supervisor differs from its admitted authority")
    preflight = reference(record["preflight"])
    authorization = reference(record["authorization"])
    expected_authorization = {"action": "install-and-start-history-repair",
        "authorized_by": "user", "contract_sha256": digest(contract),
        "adoption_identity": adopted["identity"],
        "preflight_sha256": record["preflight"]["sha256"],
        "approval_policy": "on-request", "approvals_reviewer": "user"}
    if (authorization != expected_authorization or preflight.get("status") != "pass"
            or preflight.get("contract") != contract
            or preflight.get("config_identity") != digest(configuration)
            or preflight.get("adoption") != adopted
            or not isinstance(preflight.get("environment"), str)
            or not preflight["environment"]
            or preflight.get("live_execution_enabled") is not False
            or any(type(preflight.get(key)) is not int or preflight[key] != 0
                   for key in ("model_calls", "account_writes", "grant_writes"))):
        raise ValueError("Installed admission lost its approved preflight binding")
    units = services.units()
    for name, content in units.items():
        path = regular_path(canonical_path(services.TARGET / name))
        if (path.read_bytes() != content
                or preflight.get("services", {}).get("units", {}).get(name) != digest(content)):
            raise ValueError("Installed service bytes differ from admitted commands")
        evidence[str(path)] = digest(content)
    cursor = campaign.cursor()
    observe(campaign.ROOT / "cursor.json")
    if read_json(campaign.ROOT / "cursor.json") != cursor:
        raise ValueError("Installed campaign cursor changed during observation")
    account = canonical_path(program.predecessor.account.ACCOUNT)
    grant = canonical_path(program.GRANT)
    for path in (account, grant, grant.with_suffix(".stages.json")):
        observe(path)
    stops = [{"root": str(canonical_path(campaign.ROOT)), "contract": campaign.contract()}]
    locks = sorted({str(canonical_path(path)) for path in live.shared_locks()})
    if (source != candidate.sources() or any(digest(regular_path(path).read_bytes()) != expected
                                            for path, expected in evidence.items())
            or cursor != campaign.cursor()
            or locks != sorted({str(canonical_path(path)) for path in live.shared_locks()})):
        raise ValueError("Installed authority changed during observation")
    value = {"version": "installed-history-authority-v1", "root": str(root),
             "records": [adopted], "configuration": configuration,
             "stop_bindings": stops, "shared_locks": locks, "cursor": cursor,
             "account": str(account), "grant": str(grant),
             "environment": preflight["environment"], "sources": source,
             "evidence": evidence, "live_execution_enabled": False}
    return {**value, "identity": digest(value)}


def require_environment(binding):
    from tools import inventory_history_services as services

    if services.environment() != binding["environment"]:
        raise ValueError("Handover requires the admitted service environment and human approvals")


def immutable_projection(binding):
    if (not isinstance(binding, dict) or binding.get("version") != "installed-history-authority-v1"
            or binding.get("identity") != digest({key: value for key, value in binding.items() if key != "identity"})
            or not isinstance(binding.get("evidence"), dict)):
        raise ValueError("Immutable installation projection requires intact transfer evidence")
    mutable = {str(canonical_path(binding["account"])),
               str(canonical_path(binding["grant"]).with_suffix(".stages.json"))}
    if not mutable <= binding["evidence"].keys() or str(canonical_path(binding["grant"])) not in binding["evidence"]:
        raise ValueError("Installed transfer evidence lost its canonical consumption resources")
    value = {key: item for key, item in binding.items() if key not in {"identity", "evidence"}}
    value["evidence"] = {path: checksum for path, checksum in binding["evidence"].items() if path not in mutable}
    return {**value, "identity": digest(value)}
