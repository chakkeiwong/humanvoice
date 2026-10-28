"""Native spending with the complete retained closure and provider lease.

External admission/control publication and campaign preparation are fixture
authority here; these tests do not establish public deployment permission.
"""

import fcntl
import importlib.util
import os
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_failure_first_native import baseline, codex, prepared
from test_inventory_recovery_v3_consumption_floors import bind
from test_inventory_recovery_v3_runtime_closure import closure_case, installed
from test_inventory_recovery_v3_runtime_predicates import (
    controls,
    initialize_controls,
    issue_resume,
    issue_stop,
)

from humanvoice import automatic_recovery
from humanvoice.artifacts import read_json, write_json
from tools import automatic_call_grant as grants
from tools import durable_program_supervisor as durable
from tools import inventory_history_job as jobs
from tools import sol_inventory_program as original
from tools import sol_inventory_supervisor_v2 as supervisor
from tools.inventory_recovery_v2 import program
from tools.inventory_recovery_v2 import runtime as adapter
from tools.inventory_recovery_v3 import (
    campaign_history,
    consumption_floors,
    job_ownership,
    native_consumption,
    ownership,
    ownership_roles,
    runtime_predicates,
    stop_authority,
)
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.stage_authority import CampaignAuthority
from tools.inventory_recovery_v3.stage_owner import owned_stage

__all__ = ["baseline", "codex", "prepared"]


@contextmanager
def complete_campaign(prepared, tmp_path, monkeypatch, *, recovery_journal=None):
    _codex, account, plan, _output, _request = prepared
    installation = tmp_path / "installed"
    installation.mkdir()
    installed.__wrapped__(installation, monkeypatch)
    monkeypatch.setattr(program, "predecessor", SimpleNamespace(account=SimpleNamespace(ACCOUNT=account)))
    grant = installation / "grant.json"
    grant.unlink()
    write_json(grant.with_suffix(".stages.json"), {"stages": []})
    with ExitStack() as stack:
        stack.enter_context(original.epoch.accounting_scope())
        stack.enter_context(adapter.settlement_scope())
        stack.enter_context(adapter.implementation.qualified.accounting.accounting_scope())
        report = grants.create(grant, original.epoch.call_limit(plan), "offline complete ownership", account=account)
        adoption, closure = closure_case.__wrapped__(installation, monkeypatch)
        root = Path(adoption["replacement"])
        campaign = installation / "new-campaign"
        output = campaign / "generation-00"
        write_json(output / "plan.json", plan)
        configuration = {"handover": adoption, "runtime_closure": closure,
            "campaign_root": str(campaign), "contract": adoption["contract"],
            "run": ["offline", "execute"], "admission": ["offline", "verify"],
            "cwd": str(tmp_path), "poll_seconds": 1,
            "execution_authority": {"program_base": str(installation),
                "supervisor_root": str(root), "account": str(account),
                "grant": str(grant), "grant_identity": report["identity"]}}
        configuration["stop_bindings"] = [*adoption["stop_bindings"],
            {"root": str(campaign), "contract": configuration["contract"]}]
        if recovery_journal is not None:
            configuration["recovery_journal"] = recovery_journal
        configuration["stop_floor"] = stop_authority.capture(configuration["stop_bindings"])
        floors = bind(configuration, lambda: True)
        initialize_controls(configuration)
        leaf = runtime_predicates.RuntimeLeaf(configuration,
            require_admission=lambda: deepcopy(configuration), require_controls=controls)
        floors.check = leaf
        floors.initialize()
        seed = campaign_history.identified({"version": campaign_history.VERSION, "root": str(campaign),
            "binding": {"fixture": "complete-ownership-component"}, "maximum_generations": 3,
            "journal": {"fixture": "offline-native-stage"}, "initial": {"generation": 0,
                "output": str(output), "plan_identity": plan["plan_identity"],
                "transition_identity": "fixture-preparation"}})
        history = campaign_history.CampaignHistory(campaign, seed, check=leaf)
        root.mkdir()
        request = {"phase": "RUNNING", "command": configuration["run"], "cwd": str(tmp_path),
            "run_id": "fixture", "job_id": "job-0001", "poll_seconds": 1,
            "config_identity": durable.fingerprint(configuration)}
        directory = root / "jobs/job-0001"
        write_json(root / "config.json", configuration)
        write_json(root / "state.json", {"phase": "RUNNING", "status": "RUNNING", "job": "job-0001",
            "run_id": "fixture", "config_identity": durable.fingerprint(configuration),
            "request_identity": durable.fingerprint(request)})
        write_json(directory / "request.json", request)
        write_json(directory / "ack.json", {"phase": "RUNNING", "owner": durable.identity(os.getpid()),
            "request_identity": durable.fingerprint(request), "ownership_protocol": "inherited-worker-lock-v1"})
        spec = importlib.util.spec_from_file_location("tools._complete_owner_fixture", supervisor.__file__)
        implementation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(implementation)
        implementation.config = lambda: configuration
        implementation.OUTPUT = root
        derive = lambda role: lambda: ownership_roles.expected(configuration, role, **({} if role == "monitor"
            else {"job": "job-0001", "checked_request": implementation.checked_request}))
        monitor = stack.enter_context(ownership.acquire(derive("monitor"), leaf=leaf))
        worker = stack.enter_context(ownership.extend(monitor, derive("worker"), leaf=leaf))
        lease = stack.enter_context(ownership.extend(worker, derive("campaign"), leaf=leaf))
        stack.enter_context(history.owned(descriptor=lease.descriptor("campaign")))
        history.initialize()
        guards = runtime_predicates.OwnedPredicates(leaf, lease)
        monkeypatch.setenv("HUMANVOICE_SUPERVISOR_JOB", "job-0001")
        monkeypatch.setenv(jobs.CAPSULE, job_ownership.prepare(root, "job-0001", request,
                                                             (lease.descriptor("job"),)))
        arguments = {"program_descriptor": lease.descriptor("program"), "command": configuration["run"],
            "require_admission": lambda: deepcopy(configuration), "stop_check": leaf,
            "consumption": floors, "predicates": guards, "history": history}
        authority = CampaignAuthority(implementation, **arguments)
        yield SimpleNamespace(authority=authority, implementation=implementation, arguments=arguments,
            configuration=configuration, leaf=leaf, lease=lease, history=history, floors=floors,
            account=account, grant=grant, plan=plan, output=output)


def test_complete_provider_union_and_native_callbacks(prepared, tmp_path, monkeypatch):
    with complete_campaign(prepared, tmp_path, monkeypatch) as fixture:
        baseline = automatic_recovery.execution_fds()
        with owned_stage(fixture.output, fixture.plan, authority=fixture.authority) as (owner, ledger, receipt):
            expected = ownership_roles.expected(fixture.configuration, "provider",
                job="job-0001", checked_request=fixture.implementation.checked_request,
                history=fixture.history, stage={"output": str(fixture.output), "plan": fixture.plan})
            assert owner.lease.membership == expected
            assert len(owner.execution_descriptors) == len(expected.roles)
            assert automatic_recovery.execution_fds() == owner.execution_descriptors
            assert owner.executor_descriptor == owner.lease.descriptor("executor")
            assert ledger.record["calls"] == [] and receipt
            with monkeypatch.context() as patch:
                def forbidden(*args, **kwargs):
                    pytest.fail("Owned native callback recursively read floors or acquired a lock")
                patch.setattr(fixture.floors, "status", forbidden)
                patch.setattr(fcntl, "flock", forbidden)
                assert fixture.floors.check() is True
                assert owner.owned_check() is True
            assert owner.dispatch_check() is True
        assert automatic_recovery.execution_fds() == baseline
        assert fixture.floors.check == fixture.authority.owned_check
        with pytest.raises(RecoveryStop):
            owner.owned_check()
        write_json(fixture.output / "execution.json", {"status": "nonpass",
            "plan_identity": fixture.plan["plan_identity"], "required": len(fixture.plan["calls"]), "attempted": 0})
        native_consumption.settle(original.account.settle, fixture.output, fixture.authority)
        assert len(fixture.floors.inspect("account")["head"]["history"]) == 2


def test_dispatch_rechecks_stage_after_floor_reads(prepared, tmp_path, monkeypatch):
    with complete_campaign(prepared, tmp_path, monkeypatch) as fixture, owned_stage(
            fixture.output, fixture.plan, authority=fixture.authority) as (owner, _ledger, _receipt):
        native = fixture.floors.status

        def status(resource):
            result = native(resource)
            if resource == "stages":
                owner.active = False
            return result

        with monkeypatch.context() as patch:
            patch.setattr(fixture.floors, "status", status)
            with pytest.raises(RecoveryStop, match="ended"):
                owner.dispatch_check()


def test_native_publication_rechecks_provider_ownership(prepared, tmp_path, monkeypatch):
    with complete_campaign(prepared, tmp_path, monkeypatch) as fixture:
        before = fixture.account.read_bytes(), fixture.grant.with_suffix(".stages.json").read_bytes()
        native = fixture.floors.write

        def write(resource, value, **kwargs):
            # Simulate loss after grant inspection but before its publication.
            (fixture.output / "executor.lock").unlink()
            return native(resource, value, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(fixture.floors, "write", write)
            with pytest.raises((RecoveryStop, OSError, ValueError)), owned_stage(
                    fixture.output, fixture.plan, authority=fixture.authority):
                pytest.fail("Lost provider ownership reached spending")
        assert before == (fixture.account.read_bytes(), fixture.grant.with_suffix(".stages.json").read_bytes())
        assert fixture.floors.check == fixture.authority.owned_check
        for name in ("execution.lock", "executor.lock"):
            with (fixture.output / name).open("a") as competitor:
                fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize("resource", ["account", "stages"])
@pytest.mark.parametrize("damage", ["head", "transition", "rollback"])
def test_complete_dispatch_rejects_lost_consumption(prepared, tmp_path, monkeypatch, resource, damage):
    with complete_campaign(prepared, tmp_path, monkeypatch) as fixture:
        path = fixture.floors.path(resource)
        before = path.read_bytes()
        with owned_stage(fixture.output, fixture.plan, authority=fixture.authority) as (owner, ledger, _receipt):
            target = path if damage == "rollback" else fixture.floors.root / (
                resource + ("-head.json" if damage == "head" else "-00000001.json"))
            retained = target.read_bytes()
            try:
                if damage == "rollback":
                    path.write_bytes(before)
                else:
                    target.unlink()
                with pytest.raises((RecoveryStop, OSError, ValueError)):
                    owner.dispatch_check()
                assert ledger.record["calls"] == []
            finally:
                target.write_bytes(retained)


@pytest.mark.parametrize("index", [0, 1])
def test_complete_stop_precedes_new_spending(prepared, tmp_path, monkeypatch, index):
    with complete_campaign(prepared, tmp_path, monkeypatch) as fixture:
        before = fixture.account.read_bytes(), fixture.grant.with_suffix(".stages.json").read_bytes()
        issue_stop(fixture.configuration, index)
        with pytest.raises(RecoveryStop) as caught, owned_stage(
                fixture.output, fixture.plan, authority=fixture.authority):
            pytest.fail("Stopped campaign acquired spending authority")
        assert caught.value.category == "USER_STOPPED"
        assert before == (fixture.account.read_bytes(), fixture.grant.with_suffix(".stages.json").read_bytes())
        assert not (fixture.output / "allocation-ledger.json").exists()
        issue_resume(fixture.configuration, index)
        with owned_stage(fixture.output, fixture.plan, authority=fixture.authority) as (owner, _ledger, _receipt):
            assert owner.dispatch_check()


@pytest.mark.parametrize("boundary", ["native", "head", "receipt", "ledger"])
def test_complete_claim_cut_reopens_without_duplicate_reservation(prepared, tmp_path, monkeypatch, boundary):
    from tools.inventory_recovery_v3 import claim as claims

    with complete_campaign(prepared, tmp_path, monkeypatch) as fixture:
        native_write, native_persist = original.epoch.write_json, consumption_floors.persist
        native_ledger = claims.guarded_ledger
        fired = []

        def interrupt(label):
            if label == boundary and not fired:
                fired.append(label)
                raise OSError("complete claim cut")

        def write(path, value):
            native_write(path, value)
            if Path(path) == fixture.account:
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
            with pytest.raises(OSError, match="complete claim cut"), owned_stage(
                    fixture.output, fixture.plan, authority=fixture.authority):
                pytest.fail("Cut failed to interrupt claim")
        before = fixture.account.read_bytes()
        reopened = CampaignAuthority(fixture.implementation, **fixture.arguments)
        for _attempt in range(2):
            with owned_stage(fixture.output, fixture.plan, authority=reopened) as (owner, ledger, _receipt):
                assert owner.dispatch_check() and ledger.record["calls"] == []
            assert fixture.account.read_bytes() == before
        assert read_json(fixture.output / "native-claim-intent.json")["status"] == "complete"
        assert len(fixture.floors.inspect("account")["head"]["history"]) == 1


@pytest.mark.parametrize("route", ["owned_stage", "cold_reconcile"])
@pytest.mark.parametrize("lock", ["execution.lock", "executor.lock"])
@pytest.mark.parametrize("publication", ["receipt", "ledger", "complete_intent"])
def test_claim_tail_rejects_lost_stage_before_publication(
        prepared, tmp_path, monkeypatch, route, lock, publication):
    from tools.inventory_recovery_v3 import claim as claims
    from tools.inventory_recovery_v3 import claim_tail

    with complete_campaign(prepared, tmp_path, monkeypatch) as fixture:
        native_write = original.epoch.write_json

        def cut(path, value):
            native_write(path, value)
            if Path(path) == fixture.account:
                raise OSError("claim repair cut")

        with monkeypatch.context() as patch:
            patch.setattr(original.epoch, "write_json", cut)
            with pytest.raises(OSError, match="claim repair cut"), owned_stage(
                    fixture.output, fixture.plan, authority=fixture.authority):
                pytest.fail("Expected interrupted reservation")
        before = fixture.account.read_bytes()
        native_ledger, native_reconcile = claims.guarded_ledger, fixture.floors.reconcile
        reached = []

        def lose():
            reached.append(True)
            (fixture.output / lock).unlink()

        def reconcile(resource):
            result = native_reconcile(resource)
            if publication == "receipt" and resource == "account":
                lose()
            return result

        def ledger(*args, **kwargs):
            if publication == "ledger":
                lose()
            result = native_ledger(*args, **kwargs)
            if publication == "complete_intent":
                lose()
            return result

        with monkeypatch.context() as patch:
            patch.setattr(fixture.floors, "reconcile", reconcile)
            patch.setattr(claims, "guarded_ledger", ledger)
            with pytest.raises((RecoveryStop, OSError, ValueError)):
                if route == "cold_reconcile":
                    claim_tail.reconcile(fixture.authority, fixture.output)
                else:
                    with owned_stage(fixture.output, fixture.plan, authority=fixture.authority):
                        pytest.fail("Lost stage ownership reached execution")
        assert reached == [True]
        assert fixture.account.read_bytes() == before
        assert fixture.floors.check == fixture.authority.owned_check
        assert read_json(fixture.output / "native-claim-intent.json")["status"] == "pending"
        if publication == "receipt":
            assert not (fixture.output / "account-reservation.json").exists()
        if publication in {"receipt", "ledger"}:
            assert not (fixture.output / "allocation-ledger.json").exists()
        for name in ("execution.lock", "executor.lock"):
            with (fixture.output / name).open("a") as competitor:
                fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
