"""Bind native prepared generation zero and one journal without live admission."""

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from humanvoice.artifacts import digest, read_json
from tools import sol_inventory_program as original
from tools.inventory_history_job import exclusive_descriptor
from tools.inventory_recovery_v3 import (
    accounting,
    ancestry,
    campaign_history,
    journal_binding,
    runtime,
)
from tools.inventory_recovery_v3.campaign_preparation import (
    require_prepared,
    verify_prepared,
)
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import (
    RecoveryReservations,
    persist,
    regular_path,
)

VERSION = "native-campaign-bootstrap-v1"


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_ACCOUNTING", detail)


@contextmanager
def owned(root, check):
    if check() is not True:
        raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign bootstrap requires its offline owner")
    root.mkdir(parents=True, exist_ok=True)
    path = regular_path(root / "campaign.lock")
    with os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Another owner holds campaign bootstrap") from error
        process = os.getpid()

        def guard():
            if os.getpid() != process or check() is not True:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign bootstrap lost its offline owner")
            exclusive_descriptor(path, handle.fileno())
            return True

        guard()
        yield handle.fileno(), guard


def proposal(root, plan, transition, prepared):
    grant_path = regular_path(original.GRANT)
    grant = read_json(grant_path)
    require(grant.get("account") == str(regular_path(original.account.ACCOUNT))
            and grant.get("identity") == digest({key: value for key, value in grant.items() if key != "identity"}),
            "Campaign bootstrap grant lost its canonical account binding")
    return campaign_history.identified({"version": VERSION, "root": str(root), "contract": runtime.contract(),
        "initial_output": str(root / "generation-00"), "transition_identity": transition["identity"],
        "plan_identity": plan["plan_identity"], "document": plan["bindings"]["source"],
        "prepared": prepared,
        "transition_sha256": digest(regular_path(root / "generation-00/transition.json").read_bytes()),
        "migration": plan[runtime.FIELD]["migration_identity"], "policy": plan[runtime.FIELD]["policy"],
        "account": str(regular_path(original.account.ACCOUNT)), "grant": str(grant_path),
        "grant_identity": grant["identity"], "journal_root": str(root / "recovery-journal"),
        "approval_policy": "on-request", "approvals_reviewer": "user", "live_execution_enabled": False})


def initialize(root, *, check):
    from tools.inventory_history_adoption import no_inference
    from tools.inventory_recovery_v3 import probe
    from tools.inventory_recovery_v3.requests import NativeRequests

    root = Path(root).absolute()
    require(".." not in root.parts, "Campaign bootstrap requires a canonical absolute root")
    regular_path(root / "campaign-proposal.json")
    with no_inference(), owned(root, check) as (descriptor, owner_check):
        output = root / "generation-00"
        transition = read_json(regular_path(output / "transition.json"))
        require(transition.get("version") == "inventory-budget-successor-v1",
                "Campaign initial stage must preserve its independently verified budget migration")
        intent = {"output": str(output), "transition": transition}
        prepared = verify_prepared(intent, owner_check)
        require_prepared(intent, prepared)
        plan_bytes = regular_path(output / "plan.json").read_bytes()
        require(digest(plan_bytes) == prepared["plan_sha256"], "Campaign plan changed after verification")
        plan = json.loads(plan_bytes)
        require(plan.get("plan_identity") == prepared["plan_identity"], "Campaign plan lost its verified identity")
        expected = proposal(root, plan, transition, prepared)
        anchor = read_json(regular_path(output / "prepared-authority.json"))

        def guard():
            owner_check()
            require_prepared(intent, prepared)
            require(digest(proposal(root, plan, transition, prepared)) == digest(expected),
                    "Campaign bootstrap source or grant changed before publication")
            account = read_json(regular_path(expected["account"]))
            grant = read_json(regular_path(expected["grant"]))
            ancestry.anchored_account(anchor, account, grant)
            held_path = regular_path(Path(expected["grant"]).with_suffix(".stages.json"))
            held = read_json(held_path)["stages"] if held_path.exists() else []
            require(not any(row.get("output") == str(output) or row.get("plan_identity") == plan["plan_identity"]
                            for row in [*account["plans"], *held]),
                    "Campaign bootstrap acquired a native allocation or call hold")
            owner_check()
            return True

        guard()
        target = regular_path(root / "campaign-proposal.json")
        retained_seed = regular_path(root / "seed.json")
        if target.exists():
            require(digest(read_json(target)) == digest(expected), "Campaign bootstrap proposal changed")
        else:
            require(not retained_seed.exists() and not (root / "initialization-intent.json").exists()
                    and not (root / "recovery-journal").exists(), "Cannot invent a proposal after campaign membership")
            guard()
            persist(target, expected, temporary_prefix=".campaign-publication-")
        journal = RecoveryReservations(expected["journal_root"], expected["policy"], {
            "document": expected["document"], "migration": expected["migration"], "authority": expected["identity"]})
        journal.publication_check = guard
        seed_intent = regular_path(root / "initialization-intent.json")
        prior_seed = read_json(retained_seed) if retained_seed.exists() else (
            read_json(seed_intent) if seed_intent.exists() else None)
        if prior_seed is not None:
            require(prior_seed.get("journal") == journal_binding.descriptor(journal),
                    "Campaign bootstrap cannot replace its retained canonical journal")
            journal_binding.require_extension(prior_seed["binding"]["initial_journal"], journal.read())
        else:
            require(not any(regular_path(root / name).exists() for name in
                            ("head.json", "cursor.json", "initialized.json")),
                    "Committed campaign lost its seed and initialization intent")
            journal.initialize()
        require(not journal.read()["sequences"], "Unadmitted campaign bootstrap contains prospective reservations")
        with accounting.document_scope(transition):
            resolver = NativeRequests(plan, output, journal, SimpleNamespace(check=guard))
            report = read_json(regular_path(output / "admission-probe.json"))
            observations = probe.observations(SimpleNamespace(output=output, transition=transition), report)
            guard()
            resolver.import_history(observations)
        initial_record = journal.read()
        require(initial_record.get("inherited_recovery", {}).get("history_identity")
                == transition["recovery_history"]["identity"], "Campaign journal lost its original consumption")
        guard()
        bound = journal_binding.descriptor(journal)
        seed = campaign_history.identified({"version": campaign_history.NATIVE_VERSION, "root": str(root),
            "binding": {"proposal": expected, "prepared": prepared, "initial_journal": initial_record},
            "maximum_generations": expected["policy"]["maximum_generations"], "journal": bound,
            "initial": {"generation": 0, "output": str(output), "plan_identity": plan["plan_identity"],
                        "transition_identity": transition["identity"]}})
        require(prior_seed is None or digest(seed) == digest(prior_seed), "Campaign bootstrap changed its retained seed")

        def admission_check():
            guard()
            require(digest(read_json(target)) == digest(expected) and runtime.contract() == expected["contract"]
                    and journal_binding.descriptor(journal) == bound,
                    "Campaign source, proposal or canonical journal changed before publication")
            journal_binding.require_extension(initial_record, journal.read())
            return True

        history = campaign_history.CampaignHistory(root, seed, check=admission_check)
        with history.owned(descriptor=descriptor):
            state = history.initialize()
            admission_check()
        return {"status": "OFFLINE_CAMPAIGN_INITIALIZED", "seed": seed, "state": state,
                "model_calls": 0, "account_writes": 0, "grant_writes": 0, "live_execution_enabled": False}
