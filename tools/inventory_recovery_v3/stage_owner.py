"""Own native locks and authority continuously across claim and paired work."""

import fcntl
import os
from contextlib import ExitStack, contextmanager

from humanvoice import automatic_recovery
from humanvoice.artifacts import read_json
from tools import durable_program_supervisor as durable
from tools import token_epoch_20261025 as epoch
from tools.inventory_history_handover import safe_path
from tools.inventory_recovery_v3 import ownership, ownership_roles
from tools.inventory_recovery_v3.claim import claim
from tools.inventory_recovery_v3.descriptors import exclusive_descriptor
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path
from tools.inventory_recovery_v3.stage_authority import CampaignAuthority, grant_stage


class StageOwner:
    def __init__(self, output, plan, handles, authority):
        self.output = output
        self.plan = plan
        self.handles = handles
        self.authority = authority
        self.stop_check = authority.owned_check
        self.lease = None
        self.process = durable.identity(os.getpid())
        self.active = True

    def owned_check(self):
        if not self.active or durable.identity(os.getpid()) != self.process:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Native stage owner ended or moved to another process")
        self.authority.owned_check()
        if self.lease is not None:
            self.lease.check()
        for path, handle in self.handles:
            exclusive_descriptor(path, handle.fileno())
        if ((self.output / "allocation-seal.json").exists()
                or read_json(regular_path(self.output / "plan.json")) != self.plan):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Owned native plan changed or became sealed")
        return True

    def check(self):
        self.owned_check()
        self.authority.check()
        return True

    def dispatch_check(self):
        self.owned_check()
        self.authority.dispatch_check()
        return self.owned_check()

    @property
    def executor_descriptor(self):
        self.check()
        return self.lease.descriptor("executor") if self.lease is not None else self.handles[-1][1].fileno()

    @property
    def execution_descriptors(self):
        self.check()
        return self.lease.capsule()["pass_fds"] if self.lease is not None else (self.executor_descriptor,)


@contextmanager
def stage_ownership(output, plan, *, authority):
    output = safe_path(output)
    if not isinstance(authority, CampaignAuthority):
        raise TypeError("Owned stage requires admitted campaign authority")
    authority.check()
    with ExitStack() as stack:
        handles = []
        for name in ("execution.lock", "executor.lock"):
            path = regular_path(output / name)
            handle = stack.enter_context(os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "a"))
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Native stage or inherited provider still owns execution") from error
            handles.append((path, handle))
        owner = StageOwner(output, plan, handles, authority)
        stack.callback(setattr, owner, "active", False)
        if authority.predicates is not None:
            derive = lambda: ownership_roles.expected(authority.configuration, "provider",
                job=authority.job, checked_request=authority.implementation.checked_request,
                history=authority.history, stage={"output": str(output), "plan": plan})
            owner.lease = stack.enter_context(ownership.extend(authority.predicates.lease, derive,
                leaf=authority.predicates.leaf, borrowed={path.stem: handle.fileno() for path, handle in handles}))
            stack.callback(setattr, authority.consumption, "check", authority.consumption.check)
            authority.consumption.check = owner.owned_check
        owner.check()
        yield owner


@contextmanager
def owned_stage(output, plan, *, authority):
    output = safe_path(output)
    with stage_ownership(output, plan, authority=authority) as owner, ExitStack() as stack:
        terminal_path = regular_path(output / "execution.json")
        if terminal_path.exists() and read_json(terminal_path).get("status") in {"pass", "nonpass"}:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Terminal stage requires settlement, not execution ownership")
        stack.enter_context(grant_stage(authority, output, owner_check=owner.owned_check))
        authority.check()
        reservation = claim(plan, output, account_path=authority.account_path,
                            owner_check=owner.owned_check, stop_check=owner.stop_check, consumption=authority.consumption)
        ledger = epoch.EpochLedger(output / "allocation-ledger.json", plan)
        token = None
        try:
            owner.check()
            token = automatic_recovery._EXECUTION_FDS.set(owner.execution_descriptors)
            persist(regular_path(output / "executor.json"), {"pid": os.getpid(), "status": "executing"})
            yield owner, ledger, reservation
        finally:
            if token is not None:
                automatic_recovery._EXECUTION_FDS.reset(token)
            owner.active = False
            persist(regular_path(output / "executor.json"), {"pid": os.getpid(), "status": "stopped"})
