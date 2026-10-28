"""Bind offline native campaign evidence without granting live execution."""

import json
from pathlib import Path

from humanvoice.artifacts import digest
from tools import sol_inventory_program as original
from tools.inventory_recovery_v3 import (
    accounting,
    ancestry,
    binding_publication,
    campaign_history,
    campaign_initialization,
    campaign_preparation,
    journal_binding,
    runtime,
)
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.installed_authority import canonical_path
from tools.inventory_recovery_v3.reservations import (
    RecoveryReservations,
    persist,
    regular_path,
)

VERSION = "offline-native-campaign-binding-v1"
FILENAME = "campaign-binding.json"


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_ACCOUNTING", detail)


def immutable_paths(root, contract):
    output = root / "generation-00"
    folder = output / "probe" / digest(contract)[:16]
    return sorted([*(root / name for name in ("campaign-proposal.json", "seed.json",
        "initialization-intent.json", "initialized.json")),
        *(output / name for name in campaign_preparation.FILES if name != "execution.json"),
        *(folder / name for name in ("observations.json", "replay-log.json",
                                    "probe-intent.json", "verification.json")),
        canonical_path(original.GRANT)])


def account_floor(path, account):
    return {"path": str(path), "events": len(account["events"]),
        "events_hash": digest(account["events"]), "plans": len(account["plans"]),
        "plans_hash": digest(account["plans"]),
        "fixed": {name: value for name, value in account.items() if name not in {
            "events", "plans", "reservation_ceiling", "gross_reservation_ceiling"}}}


def require_floor(floor, path, account):
    current = account_floor(path, account)
    require(set(floor) == set(current) and floor["path"] == current["path"]
            and floor["fixed"] == current["fixed"]
            and all(type(floor[name]) is int and 0 <= floor[name] <= current[name]
                    and digest(account[name][:floor[name]]) == floor[name + "_hash"]
                    for name in ("events", "plans")),
            "Campaign binding lost its original account consumption")


def snapshot_membership(output, prepared, allocated):
    from tools.inventory_recovery_v3.stage import bridge

    snapshot = canonical_path(output / "snapshot")
    current = bridge.original.lifecycle.retained.tree_hashes(snapshot)
    require(isinstance(prepared, dict) and bool(prepared) and all(
        isinstance(name, str) and str(Path(name)) == name and not Path(name).is_absolute()
        and ".." not in Path(name).parts and isinstance(value, str) and value
        for name, value in prepared.items()), "Campaign lost its prepared snapshot manifest")
    if not allocated:
        require(current == prepared, "Unallocated campaign snapshot membership changed")
    else:
        mutable = ".humanvoice/inventory/"
        additions = (mutable, ".humanvoice/runtime/", ".humanvoice/cli/")
        require(all(current.get(name) == value for name, value in prepared.items()
                    if not name.startswith(mutable))
                and all(name in prepared or name.startswith(additions) for name in current),
                "Allocated campaign changed immutable snapshot input membership")
    return current


def observe(root, check):
    root = canonical_path(root)
    if check() is not True:
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign binding requires its current offline owner")
    observed = {}

    def read(path, optional=False):
        path = regular_path(canonical_path(path))
        content = path.read_bytes() if path.exists() else None
        require(optional or content is not None, "Campaign binding lost evidence: " + str(path))
        observed[path] = content
        if content is None:
            return None
        value = json.loads(content)
        require(isinstance(value, dict), "Campaign binding evidence must be an object")
        return value

    contract = runtime.contract()
    seed = read(root / "seed.json")
    require(seed.get("version") == campaign_history.NATIVE_VERSION,
            "Campaign binding requires native initialized evidence")
    history = campaign_history.CampaignHistory(root, seed, check=check)
    state = history.status()
    require(state["status"] in {"READY", "PENDING"}, "Campaign binding requires coherent initialized history")
    output = root / "generation-00"
    proposal = read(root / "campaign-proposal.json")
    plan, transition = read(output / "plan.json"), read(output / "transition.json")
    account_path, grant_path = canonical_path(original.account.ACCOUNT), canonical_path(original.GRANT)
    account, grant = read(account_path), read(grant_path)
    require(grant.get("identity") == digest({key: value for key, value in grant.items() if key != "identity"})
            and grant.get("account") == str(account_path), "Campaign grant lost its canonical account")
    require(proposal == campaign_initialization.proposal(root, plan, transition, seed["binding"]["prepared"])
            and proposal["contract"] == contract
            and seed["maximum_generations"] == proposal["policy"]["maximum_generations"],
            "Campaign proposal differs from independently derived authority")
    ancestry.anchored_account(read(output / "prepared-authority.json"), account, grant)
    journal = RecoveryReservations(root / "recovery-journal", proposal["policy"], {
        "document": proposal["document"], "migration": proposal["migration"], "authority": proposal["identity"]})
    descriptor = journal_binding.descriptor(journal)
    require(seed["journal"] == descriptor, "Campaign binding cannot replace its canonical journal")
    for name in ("reservations.json", "consumption-head.json", "initialized.json"):
        read(journal.root / name)
    record = journal.read()
    journal_binding.require_extension(seed["binding"]["initial_journal"], record)
    stage_path = grant_path.with_suffix(".stages.json")
    stage_record = read(stage_path, optional=True)
    require(stage_record is None or set(stage_record) == {"stages"}
            and isinstance(stage_record["stages"], list), "Campaign grant lost its stage membership")
    stages = stage_record["stages"] if stage_record is not None else []
    with accounting.document_scope(transition):
        original.account.validate_account(account)
        report = original.grant_status(grant_path)
    require(report["identity"] == grant["identity"], "Campaign grant identity changed during validation")
    allocated = any(row.get("output") == str(output) and row.get("plan_identity") == plan["plan_identity"]
                    for row in account["plans"])
    snapshot_manifest = read(output / "prepared-snapshot.json")
    snapshot = snapshot_membership(output, snapshot_manifest, allocated)
    paths = immutable_paths(root, contract)
    for path in paths:
        content = regular_path(path).read_bytes()
        require(path not in observed or observed[path] == content, "Campaign immutable evidence changed")
        observed[path] = content

    def stable():
        if check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign binding ownership was vetoed")
        require(runtime.contract() == contract and history.status() == state
                and snapshot_membership(output, snapshot_manifest, allocated) == snapshot
                and all((regular_path(path).read_bytes() if path.exists() else None) == content
                        for path, content in observed.items()), "Campaign evidence changed during observation")
        return True

    stable()
    return {"root": root, "contract": contract, "seed": seed, "state": state,
        "proposal": proposal, "account": account, "account_path": account_path,
        "grant": grant, "grant_path": grant_path, "stages": stages, "journal": record,
        "journal_descriptor": descriptor, "immutable": {str(path): digest(observed[path]) for path in paths},
        "stable": stable}


def require_binding(binding, observed):
    root = observed["root"]
    require(isinstance(binding, dict) and binding == campaign_history.identified(binding)
            and set(binding) == {"version", "root", "contract", "seed_identity", "proposal_identity",
                "account_floor", "grant", "grant_identity", "grant_stages_floor", "recovery_journal",
                "initial_journal", "immutable", "live_execution_enabled", "identity"}
            and binding["version"] == VERSION and binding["root"] == str(root)
            and binding["live_execution_enabled"] is False
            and binding["contract"] == observed["contract"]
            and binding["seed_identity"] == observed["seed"]["identity"]
            and binding["proposal_identity"] == observed["proposal"]["identity"]
            and binding["grant"] == str(observed["grant_path"])
            and binding["grant_identity"] == observed["grant"]["identity"]
            and binding["recovery_journal"] == observed["journal_descriptor"]
            and binding["initial_journal"] == observed["seed"]["binding"]["initial_journal"]
            and binding["immutable"] == observed["immutable"],
            "Offline campaign binding changed its exact immutable authority")
    require_floor(binding["account_floor"], observed["account_path"], observed["account"])
    floor = binding["grant_stages_floor"]
    require(isinstance(floor, list) and observed["stages"][:len(floor)] == floor,
            "Campaign binding lost retained grant-stage membership")


def inspect(root, *, check):
    root = canonical_path(root)
    binding, step, publication = binding_publication.observe(root)
    require(step == 4, "Campaign binding publication is incomplete")
    observed = observe(root, check)
    require_binding(binding, observed)
    observed["stable"]()
    binding_publication.stable(root, publication)
    return {"status": "OFFLINE_CAMPAIGN_BOUND", "binding": binding, "campaign": observed["state"],
        "model_calls": 0, "account_writes": 0, "grant_writes": 0,
        "live_execution_enabled": False, "dispatch_allowed": False}


def create(root, *, check):
    from tools.inventory_history_adoption import no_inference

    root = canonical_path(root)
    with no_inference(), campaign_initialization.owned(root, check) as (_descriptor, guard):
        retained, step, publication = binding_publication.observe(root)
        if step == 4:
            return inspect(root, check=guard)
        observed = observe(root, guard)
        seed, state = observed["seed"], observed["state"]
        require(state["status"] == "READY" and state["cursor"]["generation"] == 0
                and observed["journal"] == seed["binding"]["initial_journal"]
                and not observed["journal"]["sequences"],
                "Cannot invent an offline binding after campaign consumption")
        intent = {"output": seed["initial"]["output"],
                  "transition": json.loads(regular_path(root / "generation-00/transition.json").read_bytes())}
        campaign_preparation.require_unallocated(root / "generation-00")
        prepared = campaign_preparation.verify_prepared(intent, guard)
        require(prepared == seed["binding"]["prepared"], "Campaign binding lost independent native preparation")
        require(not any(row.get("output") == seed["initial"]["output"]
                        or row.get("plan_identity") == seed["initial"]["plan_identity"]
                        for row in [*observed["account"]["plans"], *observed["stages"]]),
                "Cannot bind campaign authority after a native allocation or call hold")
        binding = retained or campaign_history.identified({"version": VERSION, "root": str(root),
            "contract": observed["contract"], "seed_identity": seed["identity"],
            "proposal_identity": observed["proposal"]["identity"],
            "account_floor": account_floor(observed["account_path"], observed["account"]),
            "grant": str(observed["grant_path"]), "grant_identity": observed["grant"]["identity"],
            "grant_stages_floor": observed["stages"], "recovery_journal": observed["journal_descriptor"],
            "initial_journal": seed["binding"]["initial_journal"],
            "immutable": observed["immutable"], "live_execution_enabled": False})
        observed["stable"]()
        campaign_preparation.require_unallocated(root / "generation-00")
        binding_publication.stable(root, publication)
        require_binding(binding, observed)

        def publication_check():
            observed["stable"]()
            campaign_preparation.require_unallocated(root / "generation-00")
            return True

        binding_publication.publish(root, binding, persist=persist, check=publication_check)
        return inspect(root, check=guard)
