"""Bind native stage ownership to admitted campaign and grant authority."""

import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import read_json
from tools import automatic_call_grant as grants
from tools import inventory_history_job as job_ownership
from tools.inventory_history_handover import safe_path
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path


class CampaignAuthority:
    def __init__(self, implementation, *, program_descriptor, command, require_admission, stop_check):
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
        self.check()

    def check(self):
        from tools.inventory_recovery_v3.cancellation import require_running

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


@contextmanager
def grant_stage(authority, output):
    path, output = authority.grant_path, safe_path(output)
    with grants.locked(path):
        authority.check()
        grant = read_json(regular_path(path))
        report = grants.status(path)
        if (regular_path(grant["account"]) != authority.account_path
                or report["identity"] != authority.scope["grant_identity"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Grant differs from admitted account authority")
        plan = read_json(regular_path(output / "plan.json"))
        reservation = {"output": str(output), "plan_identity": plan["plan_identity"],
                       "grant_identity": report["identity"], "maximum_calls": grants.call_limit(plan)}
        reservation_path = regular_path(path.with_suffix(".stages.json"))
        reservations = read_json(reservation_path)["stages"] if reservation_path.exists() else []
        retained = next((row for row in reservations if row["output"] == str(output)
                         or row["plan_identity"] == plan["plan_identity"]), None)
        if retained is None:
            from tools.inventory_recovery_v3.claim import readiness

            readiness(plan, output, account_path=authority.account_path, check=authority.check)
            if ((output / "allocation-ledger.json").exists()
                    or reservation["maximum_calls"] > report["available"]):
                raise RecoveryStop("BLOCKED_BUDGET", "Fresh stage exceeds available call authority")
            authority.check()
            reservations.append(reservation)
            persist(reservation_path, {"stages": reservations})
        elif retained != reservation:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Retained grant-stage authority changed")
        grants.status(path)
        try:
            yield
        finally:
            persist(regular_path(path.with_suffix(".usage.json")), grants.status(path))
