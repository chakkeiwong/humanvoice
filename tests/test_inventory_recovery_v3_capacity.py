"""Suballocate native stage holds without double-charging globally held calls."""

import multiprocessing
import os

import pytest
from test_failure_first_native import baseline, codex, prepared

from humanvoice.artifacts import digest, read_json, write_json
from tools import automatic_call_grant as grants
from tools import sol_inventory_program as original
from tools.inventory_recovery_v2 import runtime as adapter
from tools.inventory_recovery_v3.policy import proposal
from tools.inventory_recovery_v3.reservations import RecoveryReservations
from tools.inventory_recovery_v3.stage_capacity import (
    earmark_pair,
    native_stage_capacity,
    pair_capacity,
    require_earmark,
)

__all__ = ["baseline", "codex", "prepared"]


def test_native_pair_uses_existing_holds_when_global_capacity_is_zero(prepared, tmp_path):
    _codex, account_path, plan, output, _request = prepared
    grant_path = tmp_path / "grant.json"
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        maximum = original.epoch.call_limit(plan)
        grants.create(grant_path, maximum, "offline test only", account=account_path)
        with grants.stage(grant_path, output):
            original.epoch.claim(plan, output, account_path=account_path)
            before = account_path.read_bytes(), grant_path.read_bytes(), grant_path.with_suffix(".stages.json").read_bytes()
            stage = native_stage_capacity(output, account_path=account_path, grant_path=grant_path)
            assert stage["global_available"] == 0
            pair = pair_capacity(stage, earmarked_calls=0, unfinished_base_calls=maximum - 1, retry_is_base=True)
            assert pair["extra_calls"] == 1
            assert pair["native_claims"] == pair["native_refunds"] == 0
            assert before == (account_path.read_bytes(), grant_path.read_bytes(), grant_path.with_suffix(".stages.json").read_bytes())
            assert len(read_json(output / "allocation-ledger.json")["calls"]) == 0


@pytest.mark.parametrize("change", ["remove", "replace"])
def test_capacity_never_recreates_or_accepts_changed_ledger(prepared, tmp_path, monkeypatch, change):
    _codex, account_path, plan, output, _request = prepared
    grant_path = tmp_path / "grant.json"
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        grants.create(grant_path, original.epoch.call_limit(plan), "offline test only", account=account_path)
        with grants.stage(grant_path, output):
            original.epoch.claim(plan, output, account_path=account_path)
            ledger_path = output / "allocation-ledger.json"
            original_bytes = ledger_path.read_bytes()
            before = account_path.read_bytes(), grant_path.read_bytes(), (output / "account-reservation.json").read_bytes()
            status = grants.status

            def changed(path):
                result = status(path)
                if change == "remove":
                    ledger_path.unlink()
                else:
                    ledger_path.write_bytes(original_bytes + b" ")
                return result

            monkeypatch.setattr(grants, "status", changed)
            with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
                native_stage_capacity(output, account_path=account_path, grant_path=grant_path)
            assert before == (account_path.read_bytes(), grant_path.read_bytes(), (output / "account-reservation.json").read_bytes())
            assert ledger_path.exists() is (change == "replace")
            monkeypatch.setattr(grants, "status", status)
            ledger_path.write_bytes(original_bytes)


@pytest.mark.parametrize("inherited", [15, 16])
def test_durable_pair_earmark_conserves_last_native_slots(prepared, tmp_path, inherited):
    _codex, account_path, plan, output, request = prepared
    plan[adapter.FIELD]["recovery_sessions_used"] = inherited
    plan["recovery"] = adapter.policy(inherited)
    plan["plan_identity"] = digest({key: value for key, value in plan.items() if key != "plan_identity"})
    write_json(output / "plan.json", plan)
    policy = proposal(remaining_requests=2, inherited_recovery=inherited, incident_allowance=1,
                      split_allowance=0, qualification_calls=0, available_calls=4, available_tokens=2176000)
    journal = RecoveryReservations(tmp_path / "pairs", policy, {"document": plan["bindings"]["source"],
                                   "migration": "fixture", "authority": "fixture"})
    journal.initialize()
    root = journal.register_root(purpose="concept_extraction", owned=["source-member"])
    sequence = journal.reserve(lineage=root["identity"], incident=digest(plan[adapter.FIELD]["parent_failure"]),
                               request_hash=digest(request), profile_hash=digest(plan["profile"]))
    journal.bind_native_stage(sequence["identity"], output, owner_check=lambda: True, stop_check=lambda: None)
    grant_path = tmp_path / "grant.json"
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        maximum = original.epoch.call_limit(plan)
        grants.create(grant_path, maximum, "offline test only", account=account_path)
        with grants.stage(grant_path, output):
            original.epoch.claim(plan, output, account_path=account_path)
            paths = [account_path, grant_path, grant_path.with_suffix(".stages.json"),
                     output / "allocation-ledger.json"]
            before = [path.read_bytes() for path in paths]
            original_journal = journal.path.read_bytes()
            with pytest.raises(RuntimeError, match="durable complete-pair"):
                require_earmark(journal, journal.read(), sequence["identity"])
            if inherited == 16:
                with pytest.raises(RuntimeError, match="Complete recovery pair"):
                    earmark_pair(journal, sequence["identity"], output, account_path=account_path,
                                 grant_path=grant_path, owner_check=lambda: True, stop_check=lambda: None)
                assert original_journal == journal.path.read_bytes()
            else:
                retained = earmark_pair(journal, sequence["identity"], output, account_path=account_path,
                                        grant_path=grant_path, owner_check=lambda: True, stop_check=lambda: None)
                assert retained["capacity"]["extra_calls"] == 1
                reopened = RecoveryReservations(journal.root, policy, journal.binding)
                assert earmark_pair(reopened, sequence["identity"], output, account_path=account_path,
                                    grant_path=grant_path, owner_check=lambda: True, stop_check=lambda: None) == retained
                assert require_earmark(reopened, reopened.read(), sequence["identity"]) == retained
            assert before == [path.read_bytes() for path in paths]


@pytest.mark.parametrize("cut", ["stage_binding", "journal_commit", "owner_veto", "none"])
def test_pair_earmark_cold_commit_and_single_journal(prepared, tmp_path, cut):
    from tools.inventory_recovery_v3 import journal_history, reservations

    _codex, account_path, plan, output, request = prepared
    policy = proposal(remaining_requests=2, inherited_recovery=1, incident_allowance=1,
                      split_allowance=0, qualification_calls=0, available_calls=4, available_tokens=2176000)
    binding = {"document": plan["bindings"]["source"], "migration": "fixture", "authority": "fixture"}
    journal = RecoveryReservations(tmp_path / "pairs", policy, binding)
    journal.initialize()
    root = journal.register_root(purpose="concept_extraction", owned=["source-member"])
    fields = {"lineage": root["identity"], "incident": digest(plan[adapter.FIELD]["parent_failure"]),
              "request_hash": digest(request), "profile_hash": digest(plan["profile"])}
    sequence = journal.reserve(**fields)
    journal.bind_native_stage(sequence["identity"], output, owner_check=lambda: True, stop_check=lambda: None)
    grant_path = tmp_path / "grant.json"
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        grants.create(grant_path, original.epoch.call_limit(plan), "offline fixture", account=account_path)
        with grants.stage(grant_path, output):
            original.epoch.claim(plan, output, account_path=account_path)
            paths = [account_path, grant_path, grant_path.with_suffix(".stages.json"),
                     output / "account-reservation.json", output / "allocation-ledger.json"]
            before = [path.read_bytes() for path in paths]

            def worker():
                native_persist = reservations.persist

                def crash(path, record):
                    native_persist(path, record)
                    if path.name == ("recovery-pair-journal.json" if cut == "stage_binding" else "reservations.json"):
                        os._exit(73)

                reservations.persist = crash
                journal_history.persist = crash
                earmark_pair(journal, sequence["identity"], output, account_path=account_path,
                             grant_path=grant_path, owner_check=lambda: True, stop_check=lambda: None)

            if cut in {"stage_binding", "journal_commit"}:
                process = multiprocessing.get_context("fork").Process(target=worker)
                process.start()
                process.join(30)
                assert not process.is_alive() and process.exitcode == 73
            if cut == "owner_veto":
                ownership = iter([True, True, False])
                before_journal = journal.path.read_bytes()
                with pytest.raises(RuntimeError, match="ownership changed"):
                    earmark_pair(journal, sequence["identity"], output, account_path=account_path,
                        grant_path=grant_path, owner_check=lambda: next(ownership), stop_check=lambda: None)
                assert journal.path.read_bytes() == before_journal
            reopened = RecoveryReservations(journal.root, policy, binding)
            retained = earmark_pair(reopened, sequence["identity"], output, account_path=account_path,
                                   grant_path=grant_path, owner_check=lambda: True, stop_check=lambda: None)
            assert require_earmark(reopened, reopened.read(), sequence["identity"]) == retained
            other = RecoveryReservations(tmp_path / "other-pairs", policy, binding)
            other.initialize()
            assert other.register_root(purpose="concept_extraction", owned=["source-member"]) == root
            other_sequence = other.reserve(**fields)
            other.bind_native_stage(other_sequence["identity"], output, owner_check=lambda: True, stop_check=lambda: None)
            with pytest.raises(RuntimeError, match="another paired"):
                earmark_pair(other, other_sequence["identity"], output, account_path=account_path,
                             grant_path=grant_path, owner_check=lambda: True, stop_check=lambda: None)
            assert before == [path.read_bytes() for path in paths]
