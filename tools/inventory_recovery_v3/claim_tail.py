"""Repair an already-reserved claim before consumers require its native ledger."""

from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools import automatic_call_grant as grants
from tools import token_epoch_20261025 as epoch
from tools.inventory_recovery_v3.claim import claim
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import regular_path


def needed(output):
    output = Path(output)
    return not regular_path(output / "allocation-ledger.json").exists()


def under_grant(authority, output, plan, *, owner_check):
    output = Path(output).absolute()
    if not needed(output):
        return False
    owner_check()
    account = epoch.validate_account(read_json(authority.account_path))
    matches = [row for row in account["plans"] if row["output"] == str(output)
               or row["plan_identity"] == plan["plan_identity"]]
    if not matches:
        return False
    grant = read_json(regular_path(authority.grant_path))
    rows = read_json(regular_path(authority.grant_path.with_suffix(".stages.json")))["stages"]
    expected = {"output": str(output), "plan_identity": plan["plan_identity"],
                "grant_identity": authority.scope["grant_identity"], "maximum_calls": grants.call_limit(plan)}
    retained = [row for row in rows if row["output"] == str(output) or row["plan_identity"] == plan["plan_identity"]]
    if (grant.get("account") != str(authority.account_path)
            or grant.get("identity") != authority.scope["grant_identity"]
            or grant["identity"] != digest({key: value for key, value in grant.items() if key != "identity"})
            or digest(retained) != digest([expected])):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Claim tail lacks its exact already-bound stage hold")
    claim(plan, output, account_path=authority.account_path, owner_check=owner_check,
          stop_check=owner_check, consumption=authority.consumption, existing_only=True)
    return True


def reconcile(authority, output):
    from tools.inventory_recovery_v3.stage_owner import stage_ownership

    if not needed(output):
        return False
    authority.owned_check()
    plan = read_json(regular_path(Path(output) / "plan.json"))
    with stage_ownership(output, plan, authority=authority) as owner, grants.locked(authority.grant_path):
        owner.owned_check()
        return under_grant(authority, output, plan, owner_check=owner.owned_check)
