"""Bind native stage ownership to admitted campaign and grant authority."""

import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools import automatic_call_grant as grants
from tools.inventory_history_handover import safe_path
from tools.inventory_recovery_v3 import job_ownership
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path


class CampaignAuthority:
    def __init__(self, implementation, *, program_descriptor, command, require_admission, stop_check,
                 consumption=None, predicates=None, history=None):
        if not callable(require_admission) or not callable(stop_check):
            raise TypeError("Campaign authority requires admission and stop predicates")
        self.implementation = implementation
        self.require_admission = require_admission
        self.stop_check = stop_check
        self.configuration = deepcopy(require_admission())
        if not isinstance(self.configuration, dict):
            raise TypeError("Admission must return its verified supervisor configuration")
        self.scope = self.configuration.get("execution_authority", {})
        if set(self.scope) != {"program_base", "supervisor_root", "account", "grant", "grant_identity"}:
            raise ValueError("Admission lacks canonical execution authority")
        self.root = safe_path(self.scope["supervisor_root"])
        self.program_lock = regular_path(Path(self.scope["program_base"]) / "active-session-program.lock")
        self.account_path = regular_path(self.scope["account"])
        self.grant_path = regular_path(self.scope["grant"])
        self.program_descriptor = program_descriptor
        self.command = list(command)
        self.job = os.environ.get("HUMANVOICE_SUPERVISOR_JOB", "")
        self.request = None
        self.job_binding = None
        self.consumption = consumption
        self.predicates, self.history = predicates, history
        complete = "runtime_closure" in self.configuration
        if complete or predicates is not None or history is not None:
            from tools.inventory_recovery_v3.campaign_history import CampaignHistory
            from tools.inventory_recovery_v3.ownership import Lease
            from tools.inventory_recovery_v3.runtime_predicates import (
                OwnedPredicates,
                RuntimeLeaf,
            )

            if (not complete or not isinstance(predicates, OwnedPredicates)
                    or not isinstance(predicates.leaf, RuntimeLeaf)
                    or not isinstance(predicates.lease, Lease)
                    or predicates.lease.membership.role != "campaign"
                    or digest(predicates.leaf.configuration) != digest(self.configuration)
                    or not isinstance(history, CampaignHistory)
                    or str(history.root) != self.configuration["campaign_root"]
                    or consumption is None
                    or program_descriptor != predicates.lease.descriptor("program")):
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Complete campaign requires its leaf, lease, history and floors")
        if consumption is not None and (consumption.seed["configuration"] != digest(self.configuration)
                or consumption.path("account") != self.account_path
                or consumption.seed["grant"] != str(self.grant_path)):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native consumption floors differ from campaign authority")
        if predicates is not None:
            self.consumption.check = self.owned_check
        self.check()

    def owned_check(self):
        from tools.inventory_recovery_v3.cancellation import require_running

        if self.predicates is not None:
            self.predicates.check()
        self.stop_check()
        require_running(self.configuration)
        if (self.require_admission() != self.configuration
                or self.implementation.config() != self.configuration
                or safe_path(self.implementation.OUTPUT) != self.root
                or read_json(regular_path(self.root / "config.json")) != self.configuration
                or os.environ.get("HUMANVOICE_SUPERVISOR_JOB", "") != self.job):
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign admission or supervisor scope changed")
        request = self.implementation.checked_request(self.root, self.job)
        if request.get("command") != self.command or self.request is not None and request != self.request:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign command or checked request changed")
        job = job_ownership.require(self.root, self.job, request)
        if self.job_binding is not None and job != self.job_binding:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign inherited job authority changed")
        job_ownership.exclusive_descriptor(self.program_lock, self.program_descriptor)
        self.request, self.job_binding = deepcopy(request), deepcopy(job)
        return True

    def check(self):
        self.owned_check()
        if self.consumption is not None:
            for resource in ("account", "stages"):
                if self.consumption.status(resource)["status"] == "PUBLICATION_IN_PROGRESS":
                    raise RecoveryStop("BLOCKED_EXTERNAL", "Native consumption publication is in progress")
        return True

    def dispatch_check(self):
        self.check()
        if self.predicates is not None:
            self.predicates.dispatch(self.consumption)
        return True


@contextmanager
def grant_stage(authority, output, *, owner_check=None):
    path, output = authority.grant_path, safe_path(output)
    check = authority.owned_check if owner_check is None else owner_check
    with grants.locked(path):
        check()
        if authority.consumption is not None:
            authority.consumption.reconcile("stages")
        from tools.inventory_recovery_v3 import claim_tail

        plan = read_json(regular_path(output / "plan.json"))
        if claim_tail.needed(output) and owner_check is None:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Claim-tail repair requires active stage ownership")
        claim_tail.under_grant(authority, output, plan, owner_check=check)
        grant = read_json(regular_path(path))
        report = grants.status(path)
        if (regular_path(grant["account"]) != authority.account_path
                or report["identity"] != authority.scope["grant_identity"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Grant differs from admitted account authority")
        reservation = {"output": str(output), "plan_identity": plan["plan_identity"],
                       "grant_identity": report["identity"], "maximum_calls": grants.call_limit(plan)}
        reservation_path = regular_path(path.with_suffix(".stages.json"))
        reservations = read_json(reservation_path)["stages"] if reservation_path.exists() else []
        retained = next((row for row in reservations if row["output"] == str(output)
                         or row["plan_identity"] == plan["plan_identity"]), None)
        if retained is None:
            from tools.inventory_recovery_v3.claim import readiness

            readiness(plan, output, account_path=authority.account_path, check=check)
            if ((output / "allocation-ledger.json").exists()
                    or reservation["maximum_calls"] > report["available"]):
                raise RecoveryStop("BLOCKED_BUDGET", "Fresh stage exceeds available call authority")
            check()
            reservations.append(reservation)
            if authority.consumption is None:
                persist(reservation_path, {"stages": reservations})
            else:
                authority.consumption.write("stages", {"stages": reservations}, operation="hold", writer=persist)
        elif retained != reservation:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Retained grant-stage authority changed")
        grants.status(path)
        yield
        persist(regular_path(path.with_suffix(".usage.json")), grants.status(path))
