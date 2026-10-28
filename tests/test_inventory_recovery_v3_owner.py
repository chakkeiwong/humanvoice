"""Real native ownership precedes reservation and executor metadata publication."""

import fcntl
import importlib.util
import os
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace

import pytest
from test_failure_first_native import baseline, codex, prepared
from test_inventory_recovery_v3_claim import sibling_reservation

from humanvoice import automatic_recovery
from humanvoice.artifacts import digest, read_json, write_json
from tools import automatic_call_grant as grants
from tools import durable_program_supervisor as durable
from tools import inventory_history_job as jobs
from tools import sol_inventory_program as original
from tools import sol_inventory_supervisor_v2 as supervisor
from tools.inventory_recovery_v2 import runtime as adapter
from tools.inventory_recovery_v3 import stage_owner
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.policy import proposal
from tools.inventory_recovery_v3.reservations import RecoveryReservations
from tools.inventory_recovery_v3.stage_authority import CampaignAuthority
from tools.inventory_recovery_v3.stage_capacity import earmark_pair
from tools.inventory_recovery_v3.stage_owner import owned_stage

__all__ = ["baseline", "codex", "prepared"]


@pytest.mark.parametrize("boundary", ["native", "head", "receipt", "ledger"])
def test_owned_stage_cold_repairs_claim_tail_before_grant_status(prepared, tmp_path, monkeypatch, boundary):
    from pathlib import Path

    from tools.inventory_recovery_v3 import claim as claims
    from tools.inventory_recovery_v3 import consumption_floors

    with campaign(prepared, tmp_path, monkeypatch, consumption=True) as fixture:
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        fixture.consumption.check = authority.check
        native_write, native_persist = original.epoch.write_json, consumption_floors.persist
        native_ledger = claims.guarded_ledger
        fired = []

        def interrupt(label):
            if label == boundary and not fired:
                fired.append(label)
                raise OSError("owned claim cut")

        def write(path, value):
            native_write(path, value)
            if Path(path) == fixture.account_path:
                interrupt("native")
            elif Path(path).name == "account-reservation.json":
                interrupt("receipt")

        def persist(path, value, **keywords):
            native_persist(path, value, **keywords)
            if path.name == "account-head.json" and value["pending"] is None:
                interrupt("head")

        def ledger(*arguments, **keywords):
            result = native_ledger(*arguments, **keywords)
            interrupt("ledger")
            return result

        with monkeypatch.context() as patch:
            patch.setattr(original.epoch, "write_json", write)
            patch.setattr(consumption_floors, "persist", persist)
            patch.setattr(claims, "guarded_ledger", ledger)
            with pytest.raises(OSError, match="owned claim cut"), owned_stage(fixture.output, fixture.plan, authority=authority):
                pytest.fail("Claim cut failed to interrupt")
        before = fixture.account_path.read_bytes()
        with owned_stage(fixture.output, fixture.plan, authority=authority) as (owner, _ledger, _receipt):
            assert owner.check()
            assert fixture.consumption.inspect("account")["status"] == "READY"
        assert fixture.account_path.read_bytes() == before
        assert read_json(fixture.output / "native-claim-intent.json")["status"] == "complete"


@pytest.mark.parametrize("resource", ["account", "stages"])
@pytest.mark.parametrize("defect", ["head", "transition", "rollback"])
def test_post_claim_dispatch_checks_reject_lost_floor_membership(prepared, tmp_path, monkeypatch, resource, defect):
    with campaign(prepared, tmp_path, monkeypatch, consumption=True) as fixture:
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        fixture.consumption.check = authority.check
        resource_path = fixture.consumption.path(resource)
        before = resource_path.read_bytes() if resource_path.exists() else None
        with owned_stage(fixture.output, fixture.plan, authority=authority) as (owner, ledger, _receipt):
            retained = resource_path.read_bytes()
            target = fixture.consumption.root / (resource + ("-head.json" if defect == "head" else "-00000001.json"))
            retained_evidence = target.read_bytes()
            if defect == "rollback":
                if before is None:
                    resource_path.unlink()
                else:
                    resource_path.write_bytes(before)
            else:
                (fixture.consumption.root / (resource + ("-head.json" if defect == "head" else "-00000001.json"))).unlink()
            with pytest.raises((RecoveryStop, OSError, ValueError)):
                owner.check()
            assert ledger.record["calls"] == []
            resource_path.write_bytes(retained)
            target.write_bytes(retained_evidence)


def test_stale_preparation_does_not_acquire_a_new_grant_hold(prepared, tmp_path, monkeypatch):
    from copy import deepcopy

    _codex, account_path, plan, _output, _request = prepared
    grant_path = tmp_path / "shared-grant.json"
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        grants.create(grant_path, 2 * original.epoch.call_limit(plan), "offline sibling fixture", account=account_path)
        sibling_output = tmp_path / "sibling"
        sibling = deepcopy(plan)
        sibling["bindings"]["snapshot"] = str(sibling_output)
        sibling["plan_identity"] = digest({key: value for key, value in sibling.items() if key != "plan_identity"})
        write_json(sibling_output / "plan.json", sibling)
        with grants.stage(grant_path, sibling_output):
            sibling_reservation(plan, sibling_output, account_path)
    with campaign(prepared, tmp_path / "campaign", monkeypatch, retained_grant=grant_path) as fixture:
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        paths = (account_path, grant_path, grant_path.with_suffix(".stages.json"))
        before = {path: path.read_bytes() for path in paths}
        for _attempt in range(2):
            with pytest.raises(RecoveryStop, match="Stale unspent"), owned_stage(
                    fixture.output, fixture.plan, authority=authority):
                pytest.fail("Stale prepared authority acquired native ownership")
            assert {path: path.read_bytes() for path in paths} == before
        assert not (fixture.output / "native-claim-intent.json").exists()
        assert not (fixture.output / "allocation-ledger.json").exists()


@contextmanager
def campaign(prepared, tmp_path, monkeypatch, *, grant_account=None, stop_bindings=None, retained_grant=None,
             recovery_journal=None, consumption=False, cold=False, replay_scope=adapter.settlement_scope):
    _codex, account_path, plan, output, request = prepared
    grant_path = retained_grant or tmp_path / "grant.json"
    program_lock = tmp_path / "active-session-program.lock"
    root = tmp_path / "supervision"
    directory = root / "jobs/job-0001"
    directory.mkdir(parents=True)
    with ExitStack() as history, program_lock.open("a") as global_owner, (
            directory / "worker.lock").open("a") as job_owner:
        history.enter_context(original.epoch.accounting_scope())
        history.enter_context(replay_scope())
        history.enter_context(adapter.implementation.qualified.accounting.accounting_scope())
        fcntl.flock(global_owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(job_owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        grant = grants.status(grant_path) if retained_grant else grants.create(
            grant_path, original.epoch.call_limit(plan), "offline fixture", account=grant_account or account_path)
        configuration = {"run": ["offline", "execute"], "admission": ["offline", "verify"],
            "cwd": str(tmp_path), "poll_seconds": 1, "stop_bindings": stop_bindings or [], "execution_authority": {
                "program_base": str(tmp_path), "supervisor_root": str(root),
                "account": str(account_path), "grant": str(grant_path), "grant_identity": grant["identity"]}}
        if recovery_journal is not None:
            configuration["recovery_journal"] = recovery_journal
        floors = None
        if consumption:
            from test_inventory_recovery_v3_consumption_floors import bind

            configuration["campaign_root"] = str(tmp_path / "campaign-history")
            floors = bind(configuration, lambda: True)
            floors.initialize()
        dispatched = {"phase": "RUNNING", "command": configuration["run"], "cwd": str(tmp_path),
            "run_id": "fixture", "job_id": "job-0001", "poll_seconds": 1,
            "config_identity": durable.fingerprint(configuration)}
        write_json(root / "config.json", configuration)
        write_json(root / "state.json", {"phase": "RUNNING", "status": "RUNNING", "job": "job-0001",
            "run_id": "fixture", "config_identity": durable.fingerprint(configuration),
            "request_identity": durable.fingerprint(dispatched)})
        write_json(directory / "request.json", dispatched)
        write_json(directory / "ack.json", {"phase": "RUNNING", "owner": durable.identity(os.getpid()),
            "request_identity": durable.fingerprint(dispatched), "ownership_protocol": "inherited-worker-lock-v1"})
        monkeypatch.setenv("HUMANVOICE_SUPERVISOR_JOB", "job-0001")
        monkeypatch.setenv(jobs.CAPSULE, jobs.prepare(root, "job-0001", dispatched, (job_owner.fileno(),)))
        specification = importlib.util.spec_from_file_location("tools._owner_fixture", supervisor.__file__)
        implementation = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(implementation)
        implementation.config = lambda: configuration
        implementation.OUTPUT = root
        arguments = {"program_descriptor": global_owner.fileno(), "command": configuration["run"],
                     "require_admission": lambda: configuration, "stop_check": lambda: None}
        if floors is not None:
            arguments["consumption"] = floors
        if cold:
            history.close()
        yield SimpleNamespace(implementation=implementation, arguments=arguments, directory=directory,
            global_owner=global_owner, job_owner=job_owner, grant_path=grant_path, root=root, request=request,
            account_path=account_path, plan=plan, output=output, configuration=configuration, consumption=floors)


def test_actual_stage_owner_claims_before_executor_and_earmarks(prepared, tmp_path, monkeypatch):
    with campaign(prepared, tmp_path, monkeypatch) as fixture:
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        policy = proposal(remaining_requests=2, inherited_recovery=1, incident_allowance=1,
                          split_allowance=0, qualification_calls=0, available_calls=4, available_tokens=2176000)
        journal = RecoveryReservations(tmp_path / "pairs", policy, {"document": fixture.plan["bindings"]["source"],
                                       "migration": "fixture", "authority": "fixture"})
        journal.initialize()
        root = journal.register_root(purpose="concept_extraction", owned=["source-member"])
        sequence = journal.reserve(lineage=root["identity"], incident=digest(fixture.plan[adapter.FIELD]["parent_failure"]),
                                   request_hash=digest(fixture.request), profile_hash=digest(fixture.plan["profile"]))
        with owned_stage(fixture.output, fixture.plan, authority=authority) as (owner, ledger, reservation):
            assert owner.check()
            assert automatic_recovery.execution_fds() == (owner.executor_descriptor,)
            assert read_json(fixture.output / "native-claim-intent.json")["status"] == "complete"
            assert read_json(fixture.output / "executor.json")["status"] == "executing"
            assert ledger.record["calls"] == []
            journal.bind_native_stage(sequence["identity"], fixture.output, owner_check=owner.check, stop_check=owner.stop_check)
            earmark_pair(journal, sequence["identity"], fixture.output, account_path=fixture.account_path,
                         grant_path=fixture.grant_path, owner_check=owner.check, stop_check=owner.stop_check)
            with pytest.raises(RuntimeError, match="still owns"), owned_stage(
                    fixture.output, fixture.plan, authority=authority):
                pytest.fail("Second executor acquired native ownership")
        assert not automatic_recovery.execution_fds()
        assert read_json(fixture.output / "executor.json")["status"] == "stopped"
        with pytest.raises(RuntimeError, match="owner ended"):
            owner.check()
        before = fixture.account_path.read_bytes()
        with owned_stage(fixture.output, fixture.plan, authority=authority) as (resumed, _ledger, replay):
            assert resumed.check() and replay == reservation
        assert fixture.account_path.read_bytes() == before


@pytest.mark.parametrize("blocker", ["global_unlocked", "foreign_global", "missing_capsule", "foreign_capsule",
                                     "request", "ack", "stage_busy", "stop", "admission", "command"])
def test_no_stage_claim_without_real_ownership_and_admission(prepared, tmp_path, monkeypatch, blocker):
    def reject():
        raise RuntimeError("fixture veto")

    with campaign(prepared, tmp_path, monkeypatch) as fixture, (tmp_path / "unrelated.lock").open("a") as unrelated, (
            fixture.output / "execution.lock").open("a") as busy:
        fcntl.flock(unrelated, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = {path: path.read_bytes() for path in (fixture.account_path, fixture.grant_path)}
        if blocker == "global_unlocked":
            fcntl.flock(fixture.global_owner, fcntl.LOCK_UN)
        elif blocker == "foreign_global":
            fixture.arguments["program_descriptor"] = unrelated.fileno()
        elif blocker == "stage_busy":
            fcntl.flock(busy, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif blocker in {"missing_capsule", "foreign_capsule"}:
            monkeypatch.setenv(jobs.CAPSULE, "null" if blocker == "missing_capsule" else '{}')
        elif blocker in {"request", "ack"}:
            write_json(fixture.directory / (blocker + ".json"), {})
        elif blocker == "command":
            fixture.arguments["command"] = ["foreign"]
        else:
            fixture.arguments["stop_check" if blocker == "stop" else "require_admission"] = reject
        with pytest.raises((ValueError, RuntimeError)):
            authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
            with owned_stage(fixture.output, fixture.plan, authority=authority):
                pytest.fail("Rejected stage acquired authority")
        assert all(path.read_bytes() == content for path, content in before.items())
        assert not fixture.grant_path.with_suffix(".stages.json").exists()
        assert not (fixture.output / "native-claim-intent.json").exists()
        assert not (fixture.output / "executor.json").exists()


def test_foreign_account_grant_rejected_before_any_reservation(prepared, tmp_path, monkeypatch):
    other_account = tmp_path / "other-account.json"
    other_account.write_bytes(prepared[1].read_bytes())
    with campaign(prepared, tmp_path, monkeypatch, grant_account=other_account) as fixture:
        stages = fixture.grant_path.with_suffix(".stages.json")
        write_json(stages, {"stages": []})
        before = {path: path.read_bytes() for path in (fixture.account_path, other_account, fixture.grant_path, stages)}
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        with pytest.raises(RuntimeError, match="admitted account"), owned_stage(
                fixture.output, fixture.plan, authority=authority):
            pytest.fail("Foreign grant acquired account authority")
        assert all(path.read_bytes() == content for path, content in before.items())
        assert not any((fixture.output / name).exists() for name in (
            "native-claim-intent.json", "account-reservation.json", "allocation-ledger.json", "executor.json"))
        assert not fixture.grant_path.with_suffix(".usage.json").exists()


@pytest.mark.parametrize("boundary", ["body", "post_claim_stop", "late_admission", "pending_claim"])
def test_owner_cleanup_and_resumable_claim_boundaries(prepared, tmp_path, monkeypatch, boundary):
    with campaign(prepared, tmp_path, monkeypatch) as fixture:
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        native_claim = stage_owner.claim
        admission = authority.require_admission

        def reject():
            raise RuntimeError("fixture boundary")

        def claim(*arguments, **keywords):
            if boundary == "pending_claim":
                reject()
            result = native_claim(*arguments, **keywords)
            if boundary == "post_claim_stop":
                authority.stop_check = reject
            elif boundary == "late_admission":
                authority.require_admission = reject
            return result

        monkeypatch.setattr(stage_owner, "claim", claim)
        token = automatic_recovery._EXECUTION_FDS.set((fixture.global_owner.fileno(),))
        try:
            with pytest.raises(RuntimeError, match="fixture boundary"), owned_stage(
                    fixture.output, fixture.plan, authority=authority):
                reject()
            assert automatic_recovery.execution_fds() == (fixture.global_owner.fileno(),)
        finally:
            automatic_recovery._EXECUTION_FDS.reset(token)
        executor = fixture.output / "executor.json"
        if boundary == "pending_claim":
            assert not executor.exists()
        else:
            assert read_json(executor)["status"] == "stopped"
        for name in ("execution.lock", "executor.lock"):
            with (fixture.output / name).open("a") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with grants.locked(fixture.grant_path):
            pass
        authority.stop_check = lambda: None
        authority.require_admission = admission
        monkeypatch.setattr(stage_owner, "claim", native_claim)
        with owned_stage(fixture.output, fixture.plan, authority=authority) as (owner, _ledger, _reservation):
            assert owner.check()


@pytest.mark.parametrize("changed", ["request", "ack", "capsule", "configuration"])
def test_owner_revalidates_campaign_job_during_work(prepared, tmp_path, monkeypatch, changed):
    with campaign(prepared, tmp_path, monkeypatch) as fixture:
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        with owned_stage(fixture.output, fixture.plan, authority=authority) as (owner, _ledger, _reservation):
            if changed == "capsule":
                monkeypatch.setenv(jobs.CAPSULE, "null")
            elif changed == "configuration":
                write_json(fixture.root / "config.json", {})
            else:
                write_json(fixture.directory / (changed + ".json"), {})
            with pytest.raises((ValueError, RuntimeError)):
                owner.check()
