"""Derive a read-only public candidate without granting live admission."""

import json
from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest
from tools import model_routing_policy as routing
from tools import review_inventory_recovery_v3 as review
from tools.inventory_history_adoption import no_inference
from tools.inventory_recovery_v2 import program
from tools.inventory_recovery_v3 import (
    campaign_binding,
    campaign_history,
    handover,
    inspection,
    installed_authority,
    ownership_preflight,
    runtime,
    runtime_closure,
    stop_authority,
)
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import regular_path

VERSION = "inventory-public-configuration-candidate-v1"
PYTHON = "/home/ubuntu/miniforge3/bin/python"
ROOT = Path(__file__).resolve().parents[2]


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_ACCOUNTING", detail)


def derive():
    with no_inference(), inspection.nonpublishing():
        return _derive()


def _derive():
    sources = review.sources()
    directory = installed_authority.canonical_path(
        review.OUTPUT / "preparation" / digest(sources)[:20])
    root = directory / "campaign"
    output = root / "generation-00"
    observed = {}

    def read(path):
        path = regular_path(installed_authority.canonical_path(path))
        content = path.read_bytes()
        observed[path] = content
        value = json.loads(content)
        require(isinstance(value, dict), "Public configuration requires object evidence")
        return value

    def stable():
        require(sources == review.sources() and all(
            regular_path(path).read_bytes() == content for path, content in observed.items()),
            "Public configuration evidence changed during observation")
        return True

    prepared = read(directory / "preparation.json")
    require(prepared.get("status") == "OFFLINE_PREPARATION_PASS"
            and prepared.get("sources") == sources
            and prepared.get("source_unchanged") is True
            and prepared.get("authority_unchanged") is True
            and prepared.get("live_execution_enabled") is False
            and all(type(prepared.get(key)) is int and prepared[key] == 0
                    for key in ("model_calls", "account_writes", "grant_writes"))
            and prepared.get("successor") == str(output),
            "Public configuration requires complete current-source offline preparation")
    report = campaign_binding.inspect(root, check=stable)
    binding = report["binding"]
    proposal = read(root / "campaign-proposal.json")
    plan = read(output / "plan.json")
    transition = read(output / "transition.json")
    runtime.validate_plan(plan)
    require(prepared.get("plan_identity") == plan["plan_identity"]
            and prepared.get("transition_identity") == transition["identity"]
            and prepared.get("campaign_binding_identity") == binding["identity"]
            and prepared.get("campaign_seed_identity") == binding["seed_identity"]
            and prepared.get("recovery_journal") == binding["recovery_journal"]
            and proposal["identity"] == binding["proposal_identity"],
            "Public preparation lost its native campaign membership")
    ownership = read(directory / "ownership-preflight.json")
    require(isinstance(prepared.get("ownership"), dict)
            and digest(prepared["ownership"]) == digest(ownership)
            and digest(ownership) == digest(ownership_preflight.inspect(plan, output, transition, binding, stable)),
            "Public preparation lost its completed native ownership preflight")
    authority_bytes = read(directory / "preparation-authority.json")
    paths = (binding["account_floor"]["path"], binding["grant"],
             str(Path(binding["grant"]).with_suffix(".stages.json")))
    require(set(authority_bytes) == set(paths)
            and all(isinstance(content, str) for content in authority_bytes.values())
            and prepared.get("authority") == {path: digest(content.encode())
                for path, content in authority_bytes.items()},
            "Public preparation lost its original authority observation")
    authority = {path: json.loads(content) for path, content in authority_bytes.items()}
    anchor = read(output / "prepared-authority.json")
    require(campaign_binding.account_floor(Path(paths[0]), authority[paths[0]]) == binding["account_floor"]
            and digest(authority[paths[0]]) == anchor["account_hash"]
            and digest(authority_bytes[paths[1]].encode()) == binding["immutable"][paths[1]]
            and authority[paths[1]]["identity"] == binding["grant_identity"]
            and authority[paths[2]] == {"stages": binding["grant_stages_floor"]},
            "Preparation authority differs from its native bound floors")
    installed = installed_authority.capture()
    account = installed_authority.canonical_path(program.predecessor.account.ACCOUNT)
    grant = installed_authority.canonical_path(program.GRANT)
    require(installed["sources"] == sources and installed["account"] == str(account)
            and installed["grant"] == str(grant)
            and binding["account_floor"]["path"] == str(account)
            and binding["grant"] == str(grant),
            "Public configuration cannot replace installed account or grant authority")
    contract = {"version": VERSION, "sources": sources, "runtime": runtime.contract(),
                "preparation_sha256": digest(observed[directory / "preparation.json"]),
                "campaign_binding_identity": binding["identity"]}
    supervision = directory / "supervision"
    adoption = handover.proposal(installed["records"], installed["root"],
        installed["configuration"], supervision, contract)
    require(adoption["installed"] == installed,
            "Installed transfer authority changed during configuration")
    closure = runtime_closure.capture(adoption)
    stops = [*deepcopy(installed["stop_bindings"]), {"root": str(root), "contract": contract}]
    require(len({row["root"] for row in stops}) == len(stops),
            "Prospective stop root overlaps inherited authority")
    command = [PYTHON, "-I", str(ROOT / "tools/inventory_recovery_v3/public.py")]
    result = campaign_history.identified({
        "version": VERSION, "sources": sources, "contract": contract,
        "cwd": str(ROOT), "campaign_root": str(root), "preparation_root": str(directory),
        "run": command + ["campaign-execute"], "admission": command + ["campaign-verify"],
        "repair": command + ["campaign-repair"], "verify": command + ["campaign-verify"],
        "diagnose": command + ["status"], "worker": command + ["worker"],
        "monitor": command + ["monitor"],
        "execution_authority": {"program_base": str(installed_authority.canonical_path(program.BASE)),
            "supervisor_root": str(supervision), "account": str(account),
            "grant": str(grant), "grant_identity": binding["grant_identity"]},
        "recovery_journal": binding["recovery_journal"], "stop_bindings": stops,
        "stop_floor": stop_authority.capture(stops),
        "campaign_binding_identity": binding["identity"], "handover": adoption,
        "runtime_closure": closure,
        "maximum_worker_restarts": adoption["remaining_restarts"],
        "inherited_worker_restarts": adoption["cumulative_restarts"],
        "policy": proposal["policy"], "initial_profile": plan["profile"],
        "model_routing_policy": routing.policy(),
        "approval_policy": "on-request", "approvals_reviewer": "user",
        "offline_workers": 16, "provider_calls_sequential": True,
        "live_execution_enabled": False, "dispatch_allowed": False})
    require(installed_authority.capture() == installed,
            "Installed authority changed before candidate publication")
    require(campaign_binding.inspect(root, check=stable)["binding"] == binding,
            "Campaign binding changed before candidate publication")
    runtime_closure.verify(closure, adoption=adoption)
    stable()
    return result


def validate(value):
    expected = derive()
    require(isinstance(value, dict) and value == expected,
            "Public candidate differs from independently derived configuration")
    return expected


def status():
    return {"status": "OFFLINE_CONFIGURATION_READY", "configuration": derive(),
            "model_calls": 0, "account_writes": 0, "grant_writes": 0,
            "live_execution_enabled": False, "dispatch_allowed": False}
