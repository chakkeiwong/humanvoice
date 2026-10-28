"""Cold and interleaved native spending checks retain exact authority."""

from pathlib import Path

import pytest
from test_failure_first_native import baseline, codex, prepared
from test_inventory_recovery_v3_claim import sibling_reservation
from test_inventory_recovery_v3_consumption_floors import (
    native_floors,
    reserve_value,
    resource_lock,
    stage_value,
)
from test_inventory_recovery_v3_owner import campaign
from test_inventory_recovery_v3_runtime import document_plan

from humanvoice.artifacts import digest, read_json, write_json
from tools import sol_inventory_program as original
from tools.inventory_recovery_v3 import claim as claims
from tools.inventory_recovery_v3 import claim_tail, consumption_floors, runtime
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.stage_authority import CampaignAuthority
from tools.inventory_recovery_v3.stage_owner import owned_stage

__all__ = ["baseline", "codex", "native_floors", "prepared"]


def test_cold_authority_checks_settled_document_without_ambient_scope(prepared, tmp_path, monkeypatch):
    provider, account, template, output, request = prepared
    plan = document_plan(template)
    write_json(output / "plan.json", plan)
    with original.epoch.accounting_scope(), runtime.settlement_scope(), (
            runtime.implementation.qualified.accounting.accounting_scope()):
        original.epoch.claim(plan, output, account_path=account)
        write_json(output / "execution.json", {"status": "nonpass", "plan_identity": plan["plan_identity"],
            "required": len(plan["calls"]), "attempted": 0})
        original.account.settle(output, account=account)
    with pytest.raises(ValueError):
        original.epoch.validate_account(read_json(account))
    with campaign((provider, account, plan, output, request), tmp_path / "cold", monkeypatch,
                  consumption=True, cold=True, replay_scope=runtime.settlement_scope) as fixture:
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in
            (account, fixture.grant_path, *fixture.consumption.root.iterdir())}
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        fixture.consumption.check = authority.check
        assert authority.check()
        assert fixture.consumption.status("account")["status"] == "READY"
        assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before}
        seal = output / "allocation-seal.json"
        retained = read_json(seal)
        write_json(seal, {**retained, "terminal_hash": "0" * 64})
        with pytest.raises(ValueError):
            authority.check()


def interrupt_claim(fixture, authority, monkeypatch):
    native = original.epoch.write_json

    def write(path, value):
        native(path, value)
        if Path(path) == fixture.account_path:
            raise OSError("claim after account")

    with monkeypatch.context() as patch:
        patch.setattr(original.epoch, "write_json", write)
        with pytest.raises(OSError, match="claim after account"), owned_stage(
                fixture.output, fixture.plan, authority=authority):
            pytest.fail("claim cut did not fire")
    assert not (fixture.output / "allocation-ledger.json").exists()


@pytest.mark.parametrize("settled", [False, True])
def test_existing_claim_tail_allows_concurrent_sibling_append(prepared, tmp_path, monkeypatch, settled):
    with campaign(prepared, tmp_path, monkeypatch, consumption=True) as fixture:
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        fixture.consumption.check = authority.check
        interrupt_claim(fixture, authority, monkeypatch)
        native_claim = claim_tail.claim
        observed = []

        def append(*arguments, **keywords):
            sibling_output = tmp_path / "sibling"
            _receipt, sibling = sibling_reservation(fixture.plan, sibling_output, fixture.account_path)
            if settled:
                write_json(sibling_output / "execution.json", {"status": "nonpass",
                    "plan_identity": sibling["plan_identity"], "attempted": 0, "required": len(sibling["calls"])})
                original.account.settle(sibling_output, account=fixture.account_path)
            observed.append(fixture.account_path.read_bytes())
            return native_claim(*arguments, **keywords)

        monkeypatch.setattr(claim_tail, "claim", append)
        assert claim_tail.reconcile(authority, fixture.output)
        assert fixture.account_path.read_bytes() == observed[0]
        assert not claim_tail.reconcile(authority, fixture.output)
        assert read_json(fixture.output / "native-claim-intent.json")["status"] == "complete"
        assert len([event for event in read_json(fixture.account_path)["events"] if event["kind"] == "reserve"
            and event["entry"]["plan_identity"] == fixture.plan["plan_identity"]]) == 1


@pytest.mark.parametrize("defect", ["missing_intent", "changed_intent", "foreign_hold",
    "active_marker", "changed_marker", "calls", "summary", "missing_reservation"])
def test_existing_claim_tail_rejects_unexplained_evidence(prepared, tmp_path, monkeypatch, defect):
    with campaign(prepared, tmp_path, monkeypatch, consumption=True) as fixture:
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        fixture.consumption.check = authority.check
        original_account = fixture.account_path.read_bytes()
        interrupt_claim(fixture, authority, monkeypatch)
        intent = fixture.output / "native-claim-intent.json"
        if defect == "missing_intent":
            intent.unlink()
        elif defect == "changed_intent":
            value = read_json(intent)
            value["events_prefix"] = "0" * 64
            write_json(intent, consumption_floors.identified(value))
        elif defect == "foreign_hold":
            path = fixture.grant_path.with_suffix(".stages.json")
            value = read_json(path)
            value["stages"][-1]["maximum_calls"] += 1
            write_json(path, value)
        elif defect in {"active_marker", "changed_marker"}:
            write_json(fixture.output / "executor.json", {"pid": 123,
                "status": "executing" if defect == "active_marker" else "stopped",
                **({"unrelated": True} if defect == "changed_marker" else {})})
        elif defect == "calls":
            (fixture.output / "calls").mkdir()
        elif defect == "summary":
            write_json(fixture.output / "summary.json", {"status": "started"})
        else:
            fixture.account_path.write_bytes(original_account)
        before = fixture.account_path.read_bytes()
        with pytest.raises((RecoveryStop, ValueError, OSError)):
            if defect == "missing_reservation":
                claims.claim(fixture.plan, fixture.output, account_path=fixture.account_path,
                    owner_check=authority.check, stop_check=authority.check,
                    consumption=fixture.consumption, existing_only=True)
            else:
                claim_tail.reconcile(authority, fixture.output)
        assert fixture.account_path.read_bytes() == before
        assert not (fixture.output / "allocation-ledger.json").exists()


def test_existing_only_refuses_fresh_claim_without_creating_intent(prepared):
    _provider, account, plan, output, _request = prepared
    before = account.read_bytes()
    with original.epoch.accounting_scope(), pytest.raises(RecoveryStop, match="invent an intent"):
        claims.claim(plan, output, account_path=account, owner_check=lambda: True,
                     stop_check=lambda: None, existing_only=True)
    assert account.read_bytes() == before
    assert not (output / "native-claim-intent.json").exists()


@pytest.mark.parametrize("boundary", ["head", "native", "transition"])
def test_status_retries_real_partial_read_interleavings(native_floors, monkeypatch, boundary):
    guard, account, _grant, plan, output, _control = native_floors
    guard.initialize()
    value = reserve_value(account, plan, output)
    head_path = guard.root / "account-head.json"
    transition = guard.root / "account-00000001.json"
    native_persist = consumption_floors.persist
    if boundary != "head":
        def interrupt(path, record, **keywords):
            native_persist(path, record, **keywords)
            if path == head_path and record["pending"] is not None:
                raise OSError("pending intent")

        with monkeypatch.context() as patch:
            patch.setattr(consumption_floors, "persist", interrupt)
            with pytest.raises(OSError, match="pending intent"):
                guard.write("account", value, operation="reserve", writer=write_json)
    native_read, native_exists = Path.read_bytes, Path.exists
    fired = []

    def publish():
        if fired:
            return
        fired.append(boundary)
        with monkeypatch.context() as patch:
            patch.setattr(Path, "read_bytes", native_read)
            patch.setattr(Path, "exists", native_exists)
            with resource_lock(guard, "account"):
                guard.write("account", value, operation="reserve", writer=write_json)

    reads = []

    def read(path, *arguments, **keywords):
        content = native_read(path, *arguments, **keywords)
        if path == (head_path if boundary == "head" else account):
            reads.append(path)
            if boundary in {"head", "native"} and len(reads) == 2:
                publish()
        return content

    def exists(path):
        result = native_exists(path)
        if boundary == "transition" and path == transition:
            publish()
        return result

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", read)
        patch.setattr(Path, "exists", exists)
        assert guard.status("account")["status"] == "READY"
    assert fired == [boundary]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (account, *guard.root.iterdir())}
    assert guard.status("account")["status"] == "READY"
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before}


def test_status_bounds_sustained_real_publication(native_floors, tmp_path, monkeypatch):
    guard, account, _grant, plan, _output, _control = native_floors
    guard.initialize()
    native_inspect = guard.inspect
    observed = []

    def inspect(resource):
        result = native_inspect(resource)
        observed.append(resource)
        sibling_reservation(plan, tmp_path / ("sibling-" + str(len(observed))), account)
        return result

    floors_before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in guard.root.iterdir()}
    with monkeypatch.context() as patch:
        patch.setattr(guard, "inspect", inspect)
        assert guard.status("account") == {"status": "PUBLICATION_IN_PROGRESS", "dispatch_allowed": False}
    assert len(observed) == 3
    assert floors_before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in guard.root.iterdir()}


def test_each_inspection_replays_account_once_not_per_floor(native_floors, monkeypatch):
    guard, account, _grant, plan, output, _control = native_floors
    guard.initialize()
    guard.write("account", reserve_value(account, plan, output), operation="reserve", writer=write_json)
    native = original.epoch.validate_account
    calls = []

    def validate(value, **keywords):
        calls.append(digest(value))
        return native(value, **keywords)

    monkeypatch.setattr(original.epoch, "validate_account", validate)
    assert guard.status("account")["status"] == "READY"
    assert len(calls) == 1


@pytest.mark.parametrize("operation", ["reserve", "settle", "observe"])
def test_pending_target_survives_sibling_settlement_suffix(native_floors, tmp_path, monkeypatch, operation):
    guard, account, _grant, plan, output, _control = native_floors
    guard.initialize()
    with resource_lock(guard, "stages"):
        guard.write("stages", stage_value(guard, plan, output), operation="hold", writer=write_json)
    if operation in {"settle", "observe"}:
        claims.claim(plan, output, account_path=account, owner_check=lambda: True, stop_check=lambda: None,
                     consumption=guard if operation == "settle" else None)
    persist = consumption_floors.persist

    def cut(path, value, **keywords):
        if path.name == "account-head.json" and value["pending"] is None:
            raise OSError("pending target")
        persist(path, value, **keywords)

    with monkeypatch.context() as patch:
        patch.setattr(consumption_floors, "persist", cut)
        with pytest.raises(OSError, match="pending target"):
            if operation == "reserve":
                guard.write("account", reserve_value(account, plan, output), operation=operation, writer=write_json)
            elif operation == "observe":
                guard.reconcile("account")
            else:
                from types import SimpleNamespace

                from tools.inventory_recovery_v3.native_consumption import settle

                write_json(output / "execution.json", {"status": "nonpass",
                    "plan_identity": plan["plan_identity"], "required": len(plan["calls"]), "attempted": 0})
                settle(original.account.settle, output, SimpleNamespace(
                    owned_check=lambda: True, consumption=guard, account_path=account))
    if operation == "reserve":
        original.epoch.claim(plan, output, account_path=account)
    pending = guard.inspect("account")["head"]["pending"]
    sibling_output = tmp_path / "sibling"
    _receipt, sibling = sibling_reservation(plan, sibling_output, account)
    write_json(sibling_output / "execution.json", {"status": "nonpass",
        "plan_identity": sibling["plan_identity"], "required": len(sibling["calls"]), "attempted": 0})
    original.account.settle(sibling_output, account=account)
    before = account.read_bytes()
    assert guard.status("account")["status"] == "PENDING_EXTENDED"
    with resource_lock(guard, "account"):
        state = guard.reconcile("account")
        assert state["status"] == "READY"
        assert state["head"]["history"][-2] == pending["identity"]
        assert guard.reconcile("account") == state
    assert account.read_bytes() == before
