"""Exercise real native receipts through the owned document dispatcher offline."""

import multiprocessing
import os
import time
from datetime import datetime

import pytest
from test_failure_first_native import baseline, codex, prepared
from test_inventory_recovery_v3_owner import campaign as admitted_campaign
from test_inventory_recovery_v3_runtime import document_plan

from humanvoice import automatic_settlement, codex_runtime
from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.model import ModelAdapter, ModelConfig
from tools import sol_inventory_program as original
from tools.inventory_recovery_v3 import dispatcher, execution, journal_binding, runtime
from tools.inventory_recovery_v3.failures import RecoveryStop, failure_record
from tools.inventory_recovery_v3.reservations import RecoveryReservations
from tools.inventory_recovery_v3.runtime_binding import verify
from tools.inventory_recovery_v3.stage_authority import CampaignAuthority
from tools.inventory_recovery_v3.stage_owner import owned_stage

__all__ = ["baseline", "codex", "prepared"]


def campaign(prepared, tmp_path, monkeypatch, **keywords):
    journal = RecoveryReservations(tmp_path / "pairs", prepared[2][runtime.FIELD]["policy"],
        {"document": prepared[2]["bindings"]["source"], "migration": "fixture", "authority": "fixture"})
    return admitted_campaign(prepared, tmp_path, monkeypatch,
                             recovery_journal=journal_binding.descriptor(journal), **keywords)


def setup_document(prepared, tmp_path, **changes):
    codex, account, template, output, request = prepared
    plan = document_plan(template, **{"incident_allowance": 2, "split_allowance": 0, **changes})
    write_json(output / "plan.json", plan)
    journal = RecoveryReservations(tmp_path / "pairs", plan[runtime.FIELD]["policy"],
        {"document": plan["bindings"]["source"], "migration": "fixture", "authority": "fixture"})
    journal.initialize()
    lineages = [journal.register_root(purpose="concept_extraction", owned=[str(index)])["identity"]
                for index in range(len(plan["calls"]))]
    return (codex, account, plan, output, request), journal, lineages


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_owned_document_pair_replay_and_settlement(prepared, tmp_path, monkeypatch):
    prepared, journal, lineages = setup_document(prepared, tmp_path)
    codex, account_path, plan, output, request = prepared
    with campaign(prepared, tmp_path, monkeypatch) as fixture, runtime.settlement_scope():
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        with owned_stage(output, plan, authority=authority) as (owner, ledger, _reservation), runtime.runtime(
                plan, output, live=True, owner=owner):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            states = []
            with dispatcher.accounted_model(output, plan, ledger, journal=journal, owner=owner,
                                             lineages=lineages, publish=states.append):
                first = model.invoke(**request)
                second = model.invoke(**{**request, "prompt": "Next distinct source request"})
            assert [row["status"] for row in states] == ["RETRY_WAIT", "CANARY", "EXECUTING",
                                                       "VALIDATING", "EXECUTING", "VALIDATING"]
            assert len(ledger.record["calls"]) == 3
            assert journal.status()["completed"] == 2
            assert execution.layout(output, plan, ledger.record["calls"])["logical"] == 2
            before = ledger.path.read_bytes(), journal.path.read_bytes()
            with dispatcher.accounted_model(output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                assert model.invoke(**request).runtime_record == first.runtime_record
                assert model.invoke(**{**request, "prompt": "Next distinct source request"}).runtime_record == second.runtime_record
            assert before == (ledger.path.read_bytes(), journal.path.read_bytes())
            write_json(output / "execution.json", {"status": "nonpass", "plan_identity": plan["plan_identity"],
                                                   "required": 2, "attempted": 3})
        usage = original.account.settle(output, account=account_path)["usage"]
        assert automatic_settlement.completed_usage(output) == usage
        assert usage["allocated_calls"] == 3
        assert usage["retained_tokens"] == 3 * 544000


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_later_failure_pairs_and_identical_canary_substitution(prepared, tmp_path, monkeypatch):
    prepared, journal, lineages = setup_document(prepared, tmp_path)
    codex, _account_path, plan, output, request = prepared
    native = ModelAdapter.invoke
    failures = []
    real_time, offset = time.time, [0]
    monkeypatch.setattr(time, "time", lambda: real_time() + offset[0])
    dispatch_native = journal.dispatch

    def dispatch(*arguments, **keywords):
        return dispatch_native(*arguments, **keywords, clock=time.time)

    monkeypatch.setattr(journal, "dispatch", dispatch)

    class ReceiptClock(datetime):
        @classmethod
        def now(cls, timezone=None):
            return datetime.fromtimestamp(time.time(), timezone)

    monkeypatch.setattr(codex_runtime, "datetime", ReceiptClock)
    wait_native = dispatcher.network.wait_until

    def wait(path, identity, failed_at, **keywords):
        offset[0] += max(0, failed_at + 900 - time.time())
        return wait_native(path, identity, failed_at, clock=time.time)

    def provider(model, *arguments, **keywords):
        if keywords["prompt"] == "Next distinct source request" and not failures:
            failures.append(True)
            write_json(codex.settings, {"transport_failures": [{"purpose": "concept_extraction", "status": 504}]})
        else:
            write_json(codex.settings, {"response": []})
        return native(model, *arguments, **keywords)

    monkeypatch.setattr(dispatcher.network, "wait_until", wait)
    monkeypatch.setattr(ModelAdapter, "invoke", provider)
    with campaign(prepared, tmp_path, monkeypatch) as fixture, runtime.settlement_scope():
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        with owned_stage(output, plan, authority=authority) as (owner, ledger, _reservation), runtime.runtime(
                plan, output, live=True, owner=owner):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            with dispatcher.accounted_model(output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                model.invoke(**request)
                model.invoke(**{**request, "prompt": "Next distinct source request"})
            assert len(ledger.record["calls"]) == 5
            assert journal.status()["completed"] == 4
            assert execution.layout(output, plan, ledger.record["calls"])["logical"] == 2
            first_path = output / "calls/0002/call.json"
            first, second = read_json(first_path), read_json(output / "calls/0003/call.json")
            assert first["request"] == second["request"] == execution.CANARY
            foreign = {**first, **{name: second[name] for name in
                       ("runtime_record", "response_text", "input_tokens", "output_tokens")}}
            write_json(first_path, foreign)
            before = ledger.path.read_bytes(), journal.path.read_bytes()
            with pytest.raises(RuntimeError, match="launch-time allocation"):
                verify(plan, output, ledger.record["calls"][0], 2, foreign)
            assert before == (ledger.path.read_bytes(), journal.path.read_bytes())
            write_json(first_path, first)
            assert verify(plan, output, ledger.record["calls"][0], 2, first)["request_hash"] == digest(execution.CANARY)


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("role", ["canary", "retry"])
@pytest.mark.parametrize("cut", ["intent", "allocation", "runtime_binding", "native_result", "pair_settlement"])
def test_cold_owned_dispatch_never_rebuys_uncertain_calls(prepared, tmp_path, monkeypatch, role, cut):
    from tools.inventory_recovery_v3 import native_settlement, runtime_binding

    prepared, journal, lineages = setup_document(prepared, tmp_path)
    codex, account, plan, output, request = prepared
    with campaign(prepared, tmp_path, monkeypatch) as fixture, runtime.settlement_scope():
        def worker():
            authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
            with owned_stage(output, plan, authority=authority) as (owner, ledger, _reservation), runtime.runtime(
                    plan, output, live=True, owner=owner):
                native_save = journal.save
                native_persist = runtime_binding.persist
                native_finish = ledger.finish
                native_settle = native_settlement.settle_pair

                def selected():
                    ledger.reload()
                    return len(ledger.record["calls"]) == (1 if role == "canary" else 2)

                def save(record):
                    for sequence in record["sequences"].values():
                        if cut == "allocation" and sequence["slots"][role].get("native_allocation"):
                            os._exit(73)
                    native_save(record)
                    if cut == "intent" and any(
                            sequence["slots"][role].get("invocation", "").startswith("native-intent:")
                            for sequence in record["sequences"].values()):
                        os._exit(73)

                def persist(path, record):
                    native_persist(path, record)
                    if cut == "runtime_binding" and path.name == "runtime-binding.json" and selected():
                        os._exit(73)

                def finish(entry, result, path):
                    if cut == "native_result" and selected():
                        write_json(path, result)
                        os._exit(73)
                    return native_finish(entry, result, path)

                def settle(journal, identity, selected_role, **keywords):
                    if cut == "pair_settlement" and selected_role == role:
                        os._exit(73)
                    return native_settle(journal, identity, selected_role, **keywords)

                journal.save = save
                runtime_binding.persist = persist
                ledger.finish = finish
                native_settlement.settle_pair = settle
                model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
                with dispatcher.accounted_model(output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                    model.invoke(**request)

        process = multiprocessing.get_context("fork").Process(target=worker)
        process.start()
        process.join(45)
        if process.is_alive():
            process.kill()
            process.join(5)
        assert process.exitcode == 73
        before = account.read_bytes()
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        with owned_stage(output, plan, authority=authority) as (owner, ledger, _reservation), runtime.runtime(
                plan, output, live=True, owner=owner):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            allocated = len(ledger.record["calls"])
            records = set(codex.snapshot.glob(".humanvoice/runtime/*/record.json"))
            if cut in {"allocation", "runtime_binding"}:
                with pytest.raises((ValueError, RuntimeError, FileNotFoundError)), dispatcher.accounted_model(
                        output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                    model.invoke(**request)
                ledger.reload()
                assert len(ledger.record["calls"]) == allocated
                assert set(codex.snapshot.glob(".humanvoice/runtime/*/record.json")) == records
            else:
                with dispatcher.accounted_model(output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                    assert model.invoke(**request).text == "[]"
                assert len(ledger.record["calls"]) == 2
                assert journal.status()["completed"] == 2
                retained = ledger.path.read_bytes(), journal.path.read_bytes()
                with dispatcher.accounted_model(output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                    assert model.invoke(**request).text == "[]"
                assert retained == (ledger.path.read_bytes(), journal.path.read_bytes())
            assert account.read_bytes() == before


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_stop_immediately_before_provider_launch_retains_typed_cause(prepared, tmp_path, monkeypatch):
    prepared, journal, lineages = setup_document(prepared, tmp_path)
    codex, _account, plan, output, request = prepared
    native = dispatcher.require_dispatch

    def stop(*arguments, **keywords):
        native(*arguments, **keywords)
        raise RecoveryStop("USER_STOPPED", "fixture immediate prelaunch stop")

    monkeypatch.setattr(dispatcher, "require_dispatch", stop)
    original_records = set(codex.snapshot.glob(".humanvoice/runtime/*/record.json"))
    with campaign(prepared, tmp_path, monkeypatch) as fixture, runtime.settlement_scope():
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        with owned_stage(output, plan, authority=authority) as (owner, ledger, _reservation), runtime.runtime(
                plan, output, live=True, owner=owner):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            with pytest.raises(RuntimeError) as caught, dispatcher.accounted_model(
                    output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                model.invoke(**request)
            assert failure_record(caught.value, phase="test")["category"] == "USER_STOPPED"
            records = list(set(codex.snapshot.glob(".humanvoice/runtime/*/record.json")) - original_records)
            assert len(records) == 1
            process = read_json(records[0].with_name("process.json"))
            assert process["process_started"] is False
            assert not records[0].with_name("process-start.json").exists()
            assert len(ledger.record["calls"]) == 1
            assert not (output / "allocation-seal.json").exists()
