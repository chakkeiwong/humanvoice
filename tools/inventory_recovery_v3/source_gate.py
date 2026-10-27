"""Validate a budget-stop migration without using the old successor constructor."""

from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.migration import (
    inspect_parent,
    require_account_extension,
)
from tools.inventory_recovery_v3.policy import require_capacity


def budget_source_gate(report, policy, *, account_path, verify_settlement, reconstruct,
                       verify_qualification):
    from tools import token_epoch_20261025 as epoch

    account_before = Path(account_path).read_bytes()
    epoch.validate_account(read_json(account_path))
    require_capacity(policy)
    if (not isinstance(report, dict)
            or report.get("version") != "inventory-budget-migration-v1"
            or report.get("identity") != digest({key: value for key, value in report.items()
                                                   if key != "identity"})
            or report.get("derived_category") != "BLOCKED_BUDGET"
            or report.get("live_execution_enabled") is not False
            or report.get("canary_reuse_authorized") is not False
            or policy["remaining_requests"] != report.get("remaining_requests")
            or policy["inherited_recovery"] != report.get("legacy_successor_charge")):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Budget continuation lost its exact migration boundary")
    checked = inspect_parent(report["parent"], account_path, verify_settlement=verify_settlement,
                             reconstruct=reconstruct, verify_qualification=verify_qualification)
    require_account_extension(report["account_boundary"], account_path)
    compared = deepcopy(checked)
    compared["account_boundary"] = report["account_boundary"]
    account_key = str(Path(account_path))
    compared["evidence"][account_key] = report["evidence"][account_key]
    compared["identity"] = digest({key: value for key, value in compared.items() if key != "identity"})
    if compared != report or account_before != Path(account_path).read_bytes():
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Migration source or qualification changed after inspection")
    plan = read_json(Path(report["parent"]) / "plan.json")
    value = {"version": "inventory-budget-source-gate-v1",
             "migration_identity": report["identity"], "policy_identity": policy["identity"],
             "parent_plan_identity": plan["plan_identity"], "source_hash": plan["bindings"]["source"],
             "profile": deepcopy(plan["profile"]), "qualification": deepcopy(report["qualification"]),
             "retained_prefix": deepcopy(report["retained_prefix"]),
             "unfinished_request": deepcopy(report["unfinished_request"]),
             "legacy_successor_charge": report["legacy_successor_charge"],
             "new_qualification_calls": 0, "canary_reuse_authorized": False,
             "live_execution_enabled": False}
    return {**value, "identity": digest(value)}
