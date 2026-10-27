"""Replay interrupted native claim commits without renewing account authority."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import pytest
from test_failure_first_native import baseline, codex, prepared

from humanvoice.artifacts import digest, read_json, write_json
from tools import sol_inventory_program as original
from tools.inventory_recovery_v2 import runtime as adapter
from tools.inventory_recovery_v3 import claim as repair
from tools.inventory_recovery_v3.failures import RecoveryStop

__all__ = ["baseline", "codex", "prepared"]


@pytest.mark.parametrize("cut", ["intent", "account", "receipt", "ledger", "complete"])
@pytest.mark.parametrize("prepared_marker", [False, True])
def test_native_claim_crash_is_idempotent(prepared, monkeypatch, cut, prepared_marker):
    _codex, account_path, plan, output, _request = prepared
    if prepared_marker:
        write_json(output / "execution.json", {"status": "prepared", "plan_identity": plan["plan_identity"],
                   "model_calls": 0, "required": len(plan["calls"]), "human_evidence": False})
    prepared_bytes = (output / "execution.json").read_bytes() if prepared_marker else None
    native_write, native_ledger, native_persist = original.epoch.write_json, repair.guarded_ledger, repair.persist
    crashed = []

    def interrupt(label):
        if label == cut and not crashed:
            crashed.append(label)
            raise OSError("injected crash " + label)

    def write(path, record):
        native_write(path, record)
        if Path(path) == account_path:
            interrupt("account")
        elif Path(path).name == "account-reservation.json":
            interrupt("receipt")

    def ledger(*arguments, **keywords):
        value = native_ledger(*arguments, **keywords)
        interrupt("ledger")
        return value

    def persist(path, record):
        native_persist(path, record)
        if Path(path).name == "native-claim-intent.json":
            interrupt("complete" if record["status"] == "complete" else "intent")

    monkeypatch.setattr(original.epoch, "write_json", write)
    monkeypatch.setattr(repair, "guarded_ledger", ledger)
    monkeypatch.setattr(repair, "persist", persist)
    arguments = {"account_path": account_path, "owner_check": lambda: True, "stop_check": lambda: None}
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        before = read_json(account_path)["reservation_ceiling"]
        with pytest.raises(OSError, match="injected crash"):
            repair.claim(plan, output, **arguments)
        assert crashed == [cut]
        receipt = repair.claim(plan, output, **arguments)
        account_bytes = account_path.read_bytes()
        assert repair.claim(plan, output, **arguments) == receipt
        assert account_path.read_bytes() == account_bytes
        record = read_json(account_path)
        events = [event for event in record["events"] if event["kind"] == "reserve"
                  and event["entry"]["plan_identity"] == plan["plan_identity"]]
        assert len(events) == 1
        assert record["reservation_ceiling"] == before + receipt["entry"]["reserved_tokens"]
        assert read_json(output / "allocation-ledger.json")["calls"] == []
        assert read_json(output / "native-claim-intent.json")["status"] == "complete"
        if prepared_marker:
            assert (output / "execution.json").read_bytes() == prepared_bytes


@pytest.mark.parametrize("missing", ["native-claim-intent.json", "account-reservation.json",
                                     "allocation-ledger.json"])
def test_completed_claim_cannot_recreate_lost_evidence(prepared, missing):
    _codex, account_path, plan, output, _request = prepared
    arguments = {"account_path": account_path, "owner_check": lambda: True, "stop_check": lambda: None}
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        repair.claim(plan, output, **arguments)
        before = account_path.read_bytes()
        (output / missing).unlink()
        with pytest.raises(RecoveryStop):
            repair.claim(plan, output, **arguments)
        assert account_path.read_bytes() == before


def test_claim_rejects_user_stop_and_nonowner_without_reserving(prepared):
    _codex, account_path, plan, output, _request = prepared
    before = account_path.read_bytes()
    with pytest.raises(RecoveryStop, match="ownership"):
        repair.claim(plan, output, account_path=account_path,
                     owner_check=lambda: False, stop_check=lambda: None)

    def stop():
        raise RecoveryStop("USER_STOPPED", "stop")

    with pytest.raises(RecoveryStop, match="stop"):
        repair.claim(plan, output, account_path=account_path,
                     owner_check=lambda: True, stop_check=stop)
    assert account_path.read_bytes() == before
    assert not (output / "native-claim-intent.json").exists()


def sibling_reservation(plan, output, account_path):
    sibling = deepcopy(plan)
    sibling["bindings"]["snapshot"] = str(output)
    sibling["prior_reservation_ceiling"] = read_json(account_path)["reservation_ceiling"]
    sibling["plan_identity"] = digest({key: value for key, value in sibling.items() if key != "plan_identity"})
    write_json(output / "plan.json", sibling)
    return original.epoch.claim(sibling, output, account_path=account_path), sibling


@pytest.mark.parametrize("boundary", ["before_intent", "pending_intent", "reserved_target",
                                      "reserved_account_cut", "reserved_receipt_cut"])
@pytest.mark.parametrize("settled", [False, True])
def test_lawful_sibling_growth_has_explicit_claim_disposition(prepared, tmp_path, monkeypatch, boundary, settled):
    _codex, account_path, plan, output, _request = prepared
    arguments = {"account_path": account_path, "owner_check": lambda: True, "stop_check": lambda: None}
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        if boundary == "pending_intent":
            native_persist = repair.persist

            def interrupt(path, record):
                native_persist(path, record)
                if path.name == "native-claim-intent.json":
                    raise OSError("pending intent cut")

            with monkeypatch.context() as patch:
                patch.setattr(repair, "persist", interrupt)
                with pytest.raises(OSError, match="pending intent cut"):
                    repair.claim(plan, output, **arguments)
        elif boundary in {"reserved_account_cut", "reserved_receipt_cut"}:
            native_write = original.epoch.write_json

            def interrupt_reserved(path, record):
                native_write(path, record)
                if (boundary == "reserved_account_cut" and Path(path) == account_path
                        or boundary == "reserved_receipt_cut" and Path(path).name == "account-reservation.json"):
                    raise OSError("reserved publication cut")

            with monkeypatch.context() as patch:
                patch.setattr(original.epoch, "write_json", interrupt_reserved)
                with pytest.raises(OSError, match="reserved publication cut"):
                    repair.claim(plan, output, **arguments)
        elif boundary == "reserved_target":
            repair.claim(plan, output, **arguments)
        sibling_output = tmp_path / "sibling"
        _receipt, sibling = sibling_reservation(plan, sibling_output, account_path)
        if settled:
            write_json(sibling_output / "execution.json", {"status": "nonpass",
                "plan_identity": sibling["plan_identity"], "required": len(sibling["calls"]), "attempted": 0})
            original.account.settle(sibling_output, account=account_path)
        before = account_path.read_bytes()
        intent_path = output / "native-claim-intent.json"
        intent_before = intent_path.read_bytes() if intent_path.exists() else None
        allowed = boundary.startswith("reserved_") or boundary == "before_intent" and settled
        if allowed:
            repair.claim(plan, output, **arguments)
            stable = account_path.read_bytes()
            repair.claim(plan, output, **arguments)
            assert account_path.read_bytes() == stable
            if boundary.startswith("reserved_"):
                assert before == stable
        else:
            for _attempt in range(2):
                with pytest.raises(RecoveryStop, match="Stale unspent") as stopped:
                    repair.claim(plan, output, **arguments)
                assert stopped.value.evidence["disposition"] == "STALE_PREPARED_AUTHORITY"
                assert account_path.read_bytes() == before
                assert (intent_path.read_bytes() if intent_path.exists() else None) == intent_before
            assert not (output / "allocation-ledger.json").exists()


@pytest.mark.parametrize("boundary", ["replay", "native_replay", "intent", "account", "receipt", "ledger"])
@pytest.mark.parametrize("category", ["USER_STOPPED", "BLOCKED_OWNERSHIP"])
def test_claim_rechecks_late_veto_at_publication_boundaries(prepared, monkeypatch, boundary, category):
    _codex, account_path, plan, output, _request = prepared
    veto, after_veto, replays = [], {}, []

    def mark():
        veto.append(True)
        after_veto.update({path: path.read_bytes() for path in output.glob("*.json")})
        after_veto[account_path] = account_path.read_bytes()

    def owner():
        return not veto or category != "BLOCKED_OWNERSHIP"

    def stop():
        if veto and category == "USER_STOPPED":
            raise RecoveryStop(category, "late publication veto")

    native_validate, native_write = original.epoch.validate_account, original.epoch.write_json
    native_persist, native_ledger = repair.persist, repair.guarded_ledger

    def validate(record, **keywords):
        result = native_validate(record, **keywords)
        replays.append(True)
        if (boundary == "replay" and len(replays) == 1
                or boundary == "native_replay" and len(replays) == 2):
            mark()
        return result

    def write(path, record):
        native_write(path, record)
        if boundary == ("account" if Path(path) == account_path else
                         "receipt" if Path(path).name == "account-reservation.json" else None):
            mark()

    def persist(path, record):
        native_persist(path, record)
        if boundary == "intent" and path.name == "native-claim-intent.json":
            mark()

    def ledger(*arguments, **keywords):
        result = native_ledger(*arguments, **keywords)
        if boundary == "ledger":
            mark()
        return result

    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        monkeypatch.setattr(original.epoch, "validate_account", validate)
        monkeypatch.setattr(original.epoch, "write_json", write)
        monkeypatch.setattr(repair, "guarded_ledger", ledger)
        monkeypatch.setattr(repair, "persist", persist)
        with pytest.raises(RecoveryStop) as stopped:
            repair.claim(plan, output, account_path=account_path, owner_check=owner, stop_check=stop)
        assert stopped.value.category == category
        assert veto
        assert {path: path.read_bytes() for path in output.glob("*.json")} == {
            path: value for path, value in after_veto.items() if path != account_path}
        assert account_path.read_bytes() == after_veto[account_path]


@pytest.mark.parametrize("reserved", [False, True])
@pytest.mark.parametrize("category", ["USER_STOPPED", "BLOCKED_OWNERSHIP"])
def test_ledger_lock_rechecks_distinct_veto_before_actual_publication(prepared, monkeypatch, reserved, category):
    _codex, account_path, plan, output, _request = prepared
    veto, recorded = [], {}

    def owner():
        return not veto or category != "BLOCKED_OWNERSHIP"

    def stop():
        if veto and category == "USER_STOPPED":
            raise RecoveryStop("USER_STOPPED", "stop after ledger lock")

    native_lock = original.epoch.EpochLedger.locked

    @contextmanager
    def locked(ledger):
        with native_lock(ledger):
            veto.append(True)
            recorded.update({path: path.read_bytes() for path in output.glob("*.json")})
            recorded[account_path] = account_path.read_bytes()
            yield

    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        if reserved:
            native_write = original.epoch.write_json

            def interrupt(path, record):
                native_write(path, record)
                if Path(path) == account_path:
                    raise OSError("account cut")

            with monkeypatch.context() as patch:
                patch.setattr(original.epoch, "write_json", interrupt)
                with pytest.raises(OSError, match="account cut"):
                    repair.claim(plan, output, account_path=account_path, owner_check=owner, stop_check=stop)
        monkeypatch.setattr(original.epoch.EpochLedger, "locked", locked)
        with pytest.raises(RecoveryStop) as stopped:
            repair.claim(plan, output, account_path=account_path, owner_check=owner, stop_check=stop)
        assert stopped.value.category == category
        assert veto and not (output / "allocation-ledger.json").exists()
        assert read_json(output / "native-claim-intent.json")["status"] == "pending"
        assert {path: path.read_bytes() for path in output.glob("*.json")} == {
            path: value for path, value in recorded.items() if path != account_path}
        assert account_path.read_bytes() == recorded[account_path]


@pytest.mark.parametrize("changes", [{"status": "executing"}, {"status": "paused_user"},
    {"status": "nonpass"}, {"plan_identity": "other"}, {"model_calls": 1}, {"model_calls": False}])
def test_claim_refuses_nonprepared_markers(prepared, changes):
    _codex, account_path, plan, output, _request = prepared
    marker = {"status": "prepared", "plan_identity": plan["plan_identity"],
              "model_calls": 0, "required": len(plan["calls"]), "human_evidence": False, **changes}
    write_json(output / "execution.json", marker)
    before = account_path.read_bytes(), (output / "execution.json").read_bytes()
    with pytest.raises(RecoveryStop, match="exact prepared marker"):
        repair.claim(plan, output, account_path=account_path,
                     owner_check=lambda: True, stop_check=lambda: None)
    assert before == (account_path.read_bytes(), (output / "execution.json").read_bytes())
