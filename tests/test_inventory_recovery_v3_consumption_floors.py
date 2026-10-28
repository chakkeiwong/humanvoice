"""Native spending has durable monotonic floors through every publication cut."""

import fcntl
import multiprocessing
import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_failure_first_native import baseline, codex, prepared

from humanvoice.artifacts import digest, read_json, write_json
from tools import automatic_call_grant as grants
from tools import sol_inventory_program as original
from tools.inventory_recovery_v2 import execution as native_execution
from tools.inventory_recovery_v2 import runtime as adapter
from tools.inventory_recovery_v3 import claim as claims
from tools.inventory_recovery_v3 import consumption_floors as floors
from tools.inventory_recovery_v3 import native_consumption
from tools.inventory_recovery_v3.campaign_binding import account_floor
from tools.inventory_recovery_v3.failures import RecoveryStop

__all__ = ["baseline", "codex", "prepared"]


def bind(configuration, check):
    scope = configuration["execution_authority"]
    account, grant = Path(scope["account"]), Path(scope["grant"])
    stages = grant.with_suffix(".stages.json")
    binding = floors.identified({"account_floor": account_floor(account, read_json(account)),
        "grant": str(grant), "grant_identity": scope["grant_identity"],
        "grant_stages_floor": read_json(stages)["stages"] if stages.exists() else [],
        "immutable": {str(grant): digest(grant.read_bytes())}})
    configuration["campaign_binding_identity"] = binding["identity"]
    return floors.ConsumptionFloors(configuration, binding, check=check)


@pytest.fixture
def native_floors(prepared, tmp_path):
    _codex, account, plan, output, _request = prepared
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        grant = tmp_path / "calls.json"
        authority = grants.create(grant, 4 * original.epoch.call_limit(plan), "offline floor fixture", account=account)
        configuration = {"campaign_root": str(tmp_path / "campaign"),
            "execution_authority": {"account": str(account), "grant": str(grant), "grant_identity": authority["identity"]}}
        control = {"allowed": True}
        guard = bind(configuration, lambda: control["allowed"])
        yield guard, account, grant, plan, output, control


def stage_value(guard, plan, output):
    return {"stages": [{"output": str(output), "plan_identity": plan["plan_identity"],
        "grant_identity": guard.seed["grant_identity"], "maximum_calls": grants.call_limit(plan)}]}


def reserve_value(account, plan, output):
    value = read_json(account)
    entry = {"plan_identity": plan["plan_identity"], "output": str(output),
        "calls": original.epoch.call_limit(plan),
        "reserved_tokens": original.epoch.call_limit(plan) * original.epoch.native.RESERVATION,
        "prior_reservation_ceiling": plan["prior_reservation_ceiling"],
        "account_allowance": original.epoch.ALLOWANCE}
    value["plans"].append(entry)
    value["events"].append({"kind": "reserve", "entry": deepcopy(entry)})
    value["reservation_ceiling"] += entry["reserved_tokens"]
    value["gross_reservation_ceiling"] += entry["reserved_tokens"]
    return value


@contextmanager
def resource_lock(guard, resource):
    path = guard.path(resource) if resource == "account" else Path(guard.seed["grant"])
    with path.with_suffix(".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def test_native_hold_reserve_settle_and_read_only_reopen(native_floors):
    guard, account, grant, plan, output, _control = native_floors
    guard.initialize()
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in guard.root.iterdir()}
    assert guard.inspect("account")["status"] == "READY"
    guard.initialize()
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in guard.root.iterdir()}
    with resource_lock(guard, "stages"):
        guard.write("stages", stage_value(guard, plan, output), operation="hold", writer=write_json)
    with resource_lock(guard, "account"):
        guard.write("account", reserve_value(account, plan, output), operation="reserve", writer=write_json)
    original.epoch.claim(plan, output, account_path=account)
    write_json(output / "execution.json", {"status": "nonpass", "plan_identity": plan["plan_identity"],
        "required": len(plan["calls"]), "attempted": 0})
    original.account.settle(output, account=account)
    assert guard.inspect("account")["status"] == "EXTENDED"
    with resource_lock(guard, "account"):
        assert guard.reconcile("account")["status"] == "READY"
    assert len(guard.inspect("account")["head"]["history"]) == 2
    assert grants.status(grant)["available"] == read_json(grant)["maximum_new_calls"]


@pytest.mark.parametrize("resource", ["account", "stages"])
@pytest.mark.parametrize("cut", ["before_intent", "intent", "record", "native", "head"])
@pytest.mark.parametrize("process_death", [False, True])
def test_native_publication_cuts_converge(native_floors, monkeypatch, resource, cut, process_death):
    guard, account, _grant, plan, output, _control = native_floors
    guard.initialize()
    operation = "reserve" if resource == "account" else "hold"
    value = reserve_value(account, plan, output) if resource == "account" else stage_value(guard, plan, output)
    retained_persist = floors.persist
    fired = []

    def interrupt(label):
        if label == cut and not fired:
            fired.append(label)
            if process_death:
                os._exit(73)
            raise OSError("publication cut " + label)

    def persist(path, record, **keywords):
        if path.name == resource + "-head.json" and record["pending"] is not None:
            interrupt("before_intent")
        retained_persist(path, record, **keywords)
        if path.name == resource + "-head.json":
            interrupt("intent" if record["pending"] is not None else "head")
        else:
            interrupt("record")

    def writer(path, record):
        write_json(path, record)
        interrupt("native")

    def run():
        with resource_lock(guard, resource):
            guard.write(resource, value, operation=operation, writer=writer)

    with monkeypatch.context() as patch:
        patch.setattr(floors, "persist", persist)
        if process_death:
            process = multiprocessing.get_context("fork").Process(target=run)
            process.start()
            process.join(timeout=30)
            assert not process.is_alive() and process.exitcode == 73
        else:
            with pytest.raises(OSError, match="publication cut"):
                run()
    state = guard.inspect(resource)
    with resource_lock(guard, resource):
        state = guard.reconcile(resource)
        if state["status"] == "PENDING_BEFORE" or cut == "before_intent":
            guard.write(resource, value, operation=operation, writer=write_json)
        assert guard.reconcile(resource)["status"] == "READY"
    assert floors.same(guard.current(resource), value)
    assert len(guard.inspect(resource)["head"]["history"]) == 1


@pytest.mark.parametrize("cut", ["seed.json", "account-head.json", "stages-head.json", "initialized.json"])
def test_initial_publication_resumes_only_exact_prefix(native_floors, monkeypatch, cut):
    guard, _account, _grant, _plan, _output, _control = native_floors
    original_persist = floors.persist

    def interrupt(path, value, **keywords):
        original_persist(path, value, **keywords)
        if path.name == cut:
            raise OSError("bootstrap cut")

    with monkeypatch.context() as patch:
        patch.setattr(floors, "persist", interrupt)
        with pytest.raises(OSError, match="bootstrap cut"):
            guard.initialize()
    guard.initialize()
    assert guard.inspect("account")["status"] == "READY"


@pytest.mark.parametrize("defect", ["rollback", "rehashed_head", "missing_head", "missing_seed",
    "missing_marker", "missing_transition", "symlink", "grant", "boolean", "foreign_scope"])
def test_lost_or_rehashed_consumption_is_rejected(native_floors, defect):
    guard, account, grant, plan, output, _control = native_floors
    guard.initialize()
    before = account.read_bytes()
    head_before = (guard.root / "account-head.json").read_bytes()
    with resource_lock(guard, "account"):
        guard.write("account", reserve_value(account, plan, output), operation="reserve", writer=write_json)
    if defect == "rollback":
        account.write_bytes(before)
    elif defect == "rehashed_head":
        (guard.root / "account-head.json").write_bytes(head_before)
    elif defect.startswith("missing_"):
        name = {"missing_head": "account-head.json", "missing_seed": "seed.json",
            "missing_marker": "initialized.json", "missing_transition": "account-00000001.json"}[defect]
        (guard.root / name).unlink()
    elif defect == "symlink":
        path = guard.root / "account-head.json"
        path.rename(path.with_suffix(".retained"))
        path.symlink_to(path.with_suffix(".retained"))
    elif defect == "grant":
        value = read_json(grant)
        value["maximum_new_calls"] += 1
        write_json(grant, floors.identified(value))
    else:
        head = read_json(guard.root / "account-head.json")
        if defect == "boolean":
            head["committed"]["plans"] = True
        else:
            head["resource"] = "stages"
        write_json(guard.root / "account-head.json", floors.identified(head))
    with pytest.raises((RecoveryStop, OSError, ValueError)):
        guard.inspect("account")
    with pytest.raises((RecoveryStop, OSError, ValueError)):
        guard.initialize()


def test_owner_veto_and_native_validator_precede_intent(native_floors):
    guard, account, _grant, plan, output, control = native_floors
    guard.initialize()
    before = account.read_bytes(), (guard.root / "account-head.json").read_bytes()
    value = reserve_value(account, plan, output)
    value["reservation_ceiling"] += 1
    with pytest.raises(ValueError):
        guard.write("account", value, operation="reserve", writer=write_json)
    control["allowed"] = False
    with pytest.raises(RecoveryStop, match="ownership"):
        guard.write("account", reserve_value(account, plan, output), operation="reserve", writer=write_json)
    assert before == (account.read_bytes(), (guard.root / "account-head.json").read_bytes())


@pytest.mark.parametrize("operation", ["reserve", "settle"])
@pytest.mark.parametrize("cut", ["intent", "record", "native", "head"])
@pytest.mark.parametrize("process_death", [False, True])
def test_real_native_claim_and_settlement_cold_recover(native_floors, monkeypatch, operation, cut, process_death):
    guard, account, _grant, plan, output, _control = native_floors
    guard.initialize()
    with resource_lock(guard, "stages"):
        guard.write("stages", stage_value(guard, plan, output), operation="hold", writer=write_json)
    authority = SimpleNamespace(owned_check=lambda: True, consumption=guard, account_path=account)

    def reserve():
        return claims.claim(plan, output, account_path=account, owner_check=lambda: True,
                            stop_check=lambda: None, consumption=guard)

    if operation == "settle":
        reserve()
        write_json(output / "execution.json", {"status": "nonpass", "plan_identity": plan["plan_identity"],
            "required": len(plan["calls"]), "attempted": 0})
    before = len(read_json(account)["events"])
    fired = []
    native_persist = floors.persist
    function = original.epoch.claim if operation == "reserve" else original.account.settle
    native_writer = function.__globals__["write_json"]

    def interrupt(label):
        if label == cut and not fired:
            fired.append(label)
            if process_death:
                os._exit(73)
            raise OSError("native cut " + label)

    def persist(path, record, **keywords):
        native_persist(path, record, **keywords)
        if path.name == "account-head.json":
            interrupt("intent" if record["pending"] is not None else "head")
        elif path.name.startswith("account-"):
            interrupt("record")

    def writer(path, value):
        native_writer(path, value)
        if Path(path) == account:
            interrupt("native")

    def run():
        return reserve() if operation == "reserve" else native_consumption.settle(function, output, authority)

    with monkeypatch.context() as patch:
        patch.setattr(floors, "persist", persist)
        patch.setitem(function.__globals__, "write_json", writer)
        if process_death:
            process = multiprocessing.get_context("fork").Process(target=run)
            process.start()
            process.join(timeout=30)
            assert not process.is_alive() and process.exitcode == 73
        else:
            with pytest.raises(OSError, match="native cut"):
                run()
    run()
    committed = account.read_bytes()
    assert guard.inspect("account")["status"] == "READY"
    assert len(read_json(account)["events"]) == before + 1
    run()
    assert account.read_bytes() == committed


@pytest.mark.parametrize("resource", ["account", "stages"])
@pytest.mark.parametrize("boundary", ["intent", "record", "native"])
def test_late_stop_preserves_pending_membership_without_further_writes(native_floors, monkeypatch, resource, boundary):
    guard, account, _grant, plan, output, control = native_floors
    guard.initialize()
    value = reserve_value(account, plan, output) if resource == "account" else stage_value(guard, plan, output)
    original_persist = floors.persist
    observed = {}

    def stop():
        control["allowed"] = False
        observed.update({path: path.read_bytes() for path in guard.root.iterdir()})
        observed[account] = account.read_bytes()

    def persist(path, record, **keywords):
        original_persist(path, record, **keywords)
        if (boundary == "intent" and path.name == resource + "-head.json"
                or boundary == "record" and path.name == resource + "-00000001.json"):
            stop()

    def writer(path, record):
        write_json(path, record)
        if boundary == "native":
            stop()

    with monkeypatch.context() as patch:
        patch.setattr(floors, "persist", persist)
        with pytest.raises(RecoveryStop, match="ownership"):
            guard.write(resource, value, operation="reserve" if resource == "account" else "hold", writer=writer)
    assert observed and all(path.read_bytes() == content for path, content in observed.items())
    assert guard.inspect(resource)["status"].startswith("PENDING")


@pytest.mark.parametrize("unknown", [False, True])
def test_native_settlement_seal_cut_does_not_release_unknown_tokens(native_floors, monkeypatch, unknown):
    guard, account, _grant, plan, output, _control = native_floors
    guard.initialize()
    with resource_lock(guard, "stages"):
        guard.write("stages", stage_value(guard, plan, output), operation="hold", writer=write_json)
    claims.claim(plan, output, account_path=account, owner_check=lambda: True, stop_check=lambda: None, consumption=guard)
    ledger = original.epoch.EpochLedger(output / "allocation-ledger.json", plan)
    if unknown:
        incident = plan[adapter.FIELD]["parent_failure"]
        index = len(plan["calls"])
        write_json(output / f"reconnect-attempts/{index:04d}.json", {"kind": "canary",
            "plan_identity": plan["plan_identity"], "index": index, "logical": 0,
            "incident_hash": digest(incident), "request": native_execution.CANARY,
            "request_hash": digest(native_execution.CANARY)})
        native_execution.network.wait_until(output / "reconnect-waits" / (digest(incident) + ".json"),
            digest(incident), incident["eligible_after"] - 900, clock=lambda: incident["eligible_after"])
        with adapter.runtime(plan, output):
            ledger.reserve(*original.epoch.attempt_calls(plan)[index]["key"].split(":", 1))
    write_json(output / "execution.json", {"status": "nonpass", "plan_identity": plan["plan_identity"],
        "required": len(plan["calls"]), "attempted": int(unknown)})
    native = original.account.settle
    save = native.__globals__["save"]

    def interrupt(path, record):
        save(path, record)
        raise OSError("seal cut")

    authority = SimpleNamespace(owned_check=lambda: True, consumption=guard, account_path=account)
    before = account.read_bytes()
    with monkeypatch.context() as patch:
        patch.setitem(native.__globals__, "save", interrupt)
        with pytest.raises((ValueError, FileNotFoundError) if unknown else OSError, match=None if unknown else "seal cut"):
            native_consumption.settle(native, output, authority)
    assert account.read_bytes() == before
    assert guard.inspect("account")["status"] == "READY"
    assert (output / "allocation-seal.json").exists() is not unknown
    if not unknown:
        native_consumption.settle(native, output, authority)
        assert len(guard.inspect("account")["head"]["history"]) == 2


@pytest.mark.parametrize("operation", ["reserve", "settle", "hold", "observe"])
@pytest.mark.parametrize("damage", [False, True])
def test_pending_after_sibling_extension_preserves_original_target(native_floors, tmp_path, monkeypatch, operation, damage):
    from test_inventory_recovery_v3_claim import sibling_reservation

    guard, account, grant, plan, output, _control = native_floors
    guard.initialize()
    resource = "stages" if operation == "hold" else "account"
    if operation in {"settle", "observe"}:
        with resource_lock(guard, "stages"):
            guard.write("stages", stage_value(guard, plan, output), operation="hold", writer=write_json)
        claims.claim(plan, output, account_path=account, owner_check=lambda: True,
                     stop_check=lambda: None, consumption=guard if operation == "settle" else None)
    native_persist = floors.persist

    def interrupt(path, value, **keywords):
        if path.name == resource + "-head.json" and value["pending"] is None:
            raise OSError("before committed floor")
        native_persist(path, value, **keywords)

    with monkeypatch.context() as patch:
        patch.setattr(floors, "persist", interrupt)
        with pytest.raises(OSError, match="before committed floor"):
            if operation == "observe":
                with resource_lock(guard, resource):
                    guard.reconcile(resource)
            elif operation == "settle":
                write_json(output / "execution.json", {"status": "nonpass", "plan_identity": plan["plan_identity"],
                    "required": len(plan["calls"]), "attempted": 0})
                native_consumption.settle(original.account.settle, output, SimpleNamespace(
                    owned_check=lambda: True, consumption=guard, account_path=account))
            else:
                with resource_lock(guard, resource):
                    guard.write(resource, reserve_value(account, plan, output) if operation == "reserve" else
                        stage_value(guard, plan, output), operation=operation, writer=write_json)
    if operation == "reserve":
        original.epoch.claim(plan, output, account_path=account)
    pending = guard.inspect(resource)["head"]["pending"]
    sibling_output = tmp_path / "sibling"
    if resource == "account":
        sibling_reservation(plan, sibling_output, account)
    else:
        sibling = deepcopy(plan)
        sibling["bindings"]["snapshot"] = str(sibling_output)
        sibling["plan_identity"] = digest({key: value for key, value in sibling.items() if key != "plan_identity"})
        write_json(sibling_output / "plan.json", sibling)
        with grants.stage(grant, sibling_output):
            pass
    assert guard.status(resource)["status"] == "PENDING_EXTENDED"
    if damage:
        head_path = guard.root / (resource + "-head.json")
        head = read_json(head_path)
        head["pending"]["target_hash"] = "0" * 64
        head["pending"] = floors.identified(head["pending"])
        write_json(head_path, floors.identified(head))
        write_json(guard.root / (resource + f"-{pending['sequence']:08d}.json"), head["pending"])
        with pytest.raises(RecoveryStop, match="exact target"):
            guard.reconcile(resource)
        return
    with resource_lock(guard, resource):
        state = guard.reconcile(resource)
        assert state["status"] == "READY"
        assert state["head"]["history"][-2] == pending["identity"]
        assert guard.reconcile(resource) == state


@pytest.mark.parametrize("resource", ["account", "stages"])
def test_missing_applied_pending_transition_is_not_recreated(native_floors, monkeypatch, resource):
    guard, account, _grant, plan, output, _control = native_floors
    guard.initialize()
    native_persist = floors.persist

    def interrupt(path, value, **keywords):
        if path.name == resource + "-head.json" and value["pending"] is None:
            raise OSError("commit cut")
        native_persist(path, value, **keywords)

    with monkeypatch.context() as patch:
        patch.setattr(floors, "persist", interrupt)
        with pytest.raises(OSError, match="commit cut"):
            guard.write(resource, reserve_value(account, plan, output) if resource == "account" else
                stage_value(guard, plan, output), operation="reserve" if resource == "account" else "hold", writer=write_json)
    target = guard.root / (resource + "-00000001.json")
    target.unlink()
    with pytest.raises(RecoveryStop, match="write-ahead transition"):
        guard.reconcile(resource)
    assert not target.exists()


@pytest.mark.parametrize("boundary", ["head", "native", "transition", "constant"])
def test_status_retries_concurrent_publication_without_writes(native_floors, monkeypatch, boundary):
    guard, account, _grant, plan, output, _control = native_floors
    guard.initialize()
    value = reserve_value(account, plan, output)
    original_inspect = guard.inspect
    calls = []

    def concurrent(resource):
        calls.append(resource)
        if len(calls) == 1:
            if boundary == "constant":
                raise RecoveryStop("BLOCKED_ACCOUNTING", "stable corruption")
            with monkeypatch.context() as patch:
                patch.setattr(guard, "inspect", original_inspect)
                guard.write("account", value, operation="reserve", writer=write_json)
            raise RecoveryStop("BLOCKED_ACCOUNTING", "racing " + boundary)
        return original_inspect(resource)

    monkeypatch.setattr(guard, "inspect", concurrent)
    if boundary == "constant":
        with pytest.raises(RecoveryStop, match="stable corruption"):
            guard.status("account")
        assert len(calls) == 1
    else:
        assert guard.status("account")["status"] == "READY"
        assert len(calls) == 2
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in guard.root.iterdir()}
    guard.status("account")
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in guard.root.iterdir()}
