"""Cold restart at unallocated intents and authorized zero-launch cancellations."""

import multiprocessing
import os
import time
from pathlib import Path

import pytest
from test_failure_first_native import baseline, codex, prepared
from test_inventory_recovery_v3_execution import campaign, setup_document

from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.model import ModelAdapter, ModelConfig
from tools.inventory_recovery_v2 import control
from tools.inventory_recovery_v3 import (
    cancellation,
    control_history,
    dispatcher,
    runtime,
)
from tools.inventory_recovery_v3.failures import failure_record
from tools.inventory_recovery_v3.stage_authority import CampaignAuthority
from tools.inventory_recovery_v3.stage_owner import owned_stage

__all__ = ["baseline", "codex", "prepared"]


def cold_run(worker):
    process = multiprocessing.get_context("fork").Process(target=worker)
    process.start()
    process.join(45)
    if process.is_alive():
        process.kill()
        process.join(5)
    assert process.exitcode == 73


def resume(root, contract):
    write_json(root / "resume-authorization.json", {
        "authorized_by": "user", "action": "explicit-resume", "contract": contract,
        "stop_sha256": digest((root / "user-stop.json").read_bytes())})


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("root_count", [1, 2])
@pytest.mark.parametrize("boundary", ["before_allocation", "before_launch"])
@pytest.mark.parametrize("cut,fault", [
    ("none", "none"), ("retire", "none"), ("initial_head", "none"), ("authorization", "none"),
    ("pending_head", "none"), ("transition", "none"), ("committed_head", "none"),
    ("none", "missing_intermediate"), ("none", "missing_latest"), ("none", "missing_head"),
    ("none", "foreign_head"), ("none", "malformed_head"),
])
def test_second_stop_supersedes_retired_authorization_without_renewing_charges(
        prepared, tmp_path, monkeypatch, boundary, cut, fault, root_count):
    prepared, journal, lineages = setup_document(prepared, tmp_path, incident_allowance=3)
    codex, account, plan, output, request = prepared
    root, contract = tmp_path / "control", {"fixture": "repeated-stop"}
    roots = [root] + ([tmp_path / "second-control"] if root_count == 2 else [])
    native = dispatcher.require_dispatch
    stops = []
    enabled = [True]

    def stop(*arguments, **keywords):
        native(*arguments, **keywords)
        if enabled[0]:
            enabled[0] = False
            stops.append(control.stop(root))
            for other in roots[1:]:
                write_json(other / "user-stop.json", stops[-1])
            native(*arguments, **keywords)

    monkeypatch.setattr(dispatcher, "require_dispatch", stop)
    with campaign(prepared, tmp_path, monkeypatch, stop_bindings=[
            {"root": str(selected), "contract": contract} for selected in roots]) as fixture, (
            runtime.settlement_scope()):
        def invoke():
            authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
            with owned_stage(output, plan, authority=authority) as (owner, ledger, _reservation), runtime.runtime(
                    plan, output, live=True, owner=owner):
                model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
                with dispatcher.accounted_model(output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                    return model.invoke(**request)

        with pytest.raises(RuntimeError):
            invoke()
        for selected in roots:
            resume(selected, contract)
        original_control = {path: path.read_bytes() for path in
                            [selected / name for selected in roots for name in
                             ("user-stop.json", "resume-authorization.json")]}

        def crash_after_publish(action):
            native_history, native_authorization = control_history.persist, cancellation.persist

            def history(path, value):
                native_history(path, value)
                pending = value.get("pending")
                committed = any(value.get("histories", {}).values())
                if ((cut == "initial_head" and "histories" in value and not pending and not committed)
                        or cut == "pending_head" and pending
                        or cut == "committed_head" and committed and not pending
                        or cut == "transition" and value.get("version") == "cancellation-stop-supersession-v2"):
                    os._exit(73)

            def authorization(path, value):
                native_authorization(path, value)
                if cut == "authorization":
                    os._exit(73)

            control_history.persist, cancellation.persist = history, authorization
            action()

        def retire():
            authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
            with owned_stage(output, plan, authority=authority) as (owner, ledger, _reservation), runtime.runtime(
                    plan, output, live=True, owner=owner):
                dispatcher.reconcile_pairs(journal, owner, ledger)
            if cut == "retire":
                os._exit(73)

        if cut in {"initial_head", "authorization"}:
            cold_run(lambda: crash_after_publish(retire))
            retire()
        elif cut == "retire":
            cold_run(retire)
        else:
            retire()
        first = next(iter(journal.read()["sequences"].values()))
        charge = read_json(output / "allocation-ledger.json")["calls"][0]
        authorizations = {path: path.read_bytes() for path in (output / "cancellation-authorizations").glob("*.json")
                          if not path.name.endswith("-head.json")}
        assert authorizations and first["slots"]["canary"]["state"] == "cancelled"
        if boundary == "before_allocation":
            control.stop(root)
        else:
            enabled[0] = True
            with pytest.raises(RuntimeError):
                invoke()
        resume(root, contract)
        blocked_root = roots[-1]
        before = (output / "allocation-ledger.json").read_bytes(), journal.path.read_bytes(), account.read_bytes()
        for action in ("missing", "wrong"):
            if action == "missing":
                (blocked_root / "resume-authorization.json").unlink()
            else:
                write_json(blocked_root / "resume-authorization.json", {"authorized_by": "user", "action": "explicit-resume",
                           "contract": contract, "stop_sha256": "old-or-foreign-stop"})
            with pytest.raises(RuntimeError) as caught:
                invoke()
            assert failure_record(caught.value, phase="test")["category"] == "USER_STOPPED"
            assert before == ((output / "allocation-ledger.json").read_bytes(), journal.path.read_bytes(), account.read_bytes())
        for selected in roots:
            resume(selected, contract)
        if cut in {"pending_head", "transition", "committed_head"}:
            cold_run(lambda: crash_after_publish(invoke))
        for _restart in range(2):
            assert invoke().text == "[]"
            entries = read_json(output / "allocation-ledger.json")["calls"]
            assert entries[0] == charge
            assert len(entries) == (3 if boundary == "before_allocation" else 4)
            assert all(path.read_bytes() == content for path, content in authorizations.items())
        assert journal.read()["sequences"][first["identity"]] == first
        assert account.read_bytes() == before[2]
        control.stop(root)
        resume(root, contract)
        before = (output / "allocation-ledger.json").read_bytes(), journal.path.read_bytes(), account.read_bytes()
        for _restart in range(2):
            assert invoke().text == "[]"
            assert before == ((output / "allocation-ledger.json").read_bytes(), journal.path.read_bytes(), account.read_bytes())
        for selected in roots[1:]:
            control.stop(selected)
            with pytest.raises(RuntimeError) as caught:
                invoke()
            assert failure_record(caught.value, phase="test")["category"] == "USER_STOPPED"
            assert before == ((output / "allocation-ledger.json").read_bytes(), journal.path.read_bytes(), account.read_bytes())
            resume(selected, contract)
            assert invoke().text == "[]"
        authorization_path = next(iter(authorizations))
        head_path = authorization_path.with_name(authorization_path.stem + "-head.json")
        head = read_json(head_path)
        assert len(head["histories"]) == root_count
        first_stop = read_json(authorization_path)["stops"][0]
        history = head["histories"][digest(first_stop)]
        assert len(history) == 2 and head["pending"] is None
        if root_count == 2:
            second_stop = read_json(authorization_path)["stops"][1]
            assert len(head["histories"][digest(second_stop)]) == (1 if boundary == "before_allocation" else 2)
        if fault.startswith("missing_"):
            target = head_path if fault == "missing_head" else (
                authorization_path.parent / authorization_path.stem /
                history[0 if fault == "missing_intermediate" else -1]["file"])
            target.unlink()
        elif fault in {"foreign_head", "malformed_head"}:
            if fault == "foreign_head":
                head["authorization_identity"] = "foreign"
            else:
                head["histories"] = []
            control_history.save(head_path, head)
        for path, content in original_control.items():
            path.write_bytes(content)
        with pytest.raises(RuntimeError) as caught:
            invoke()
        assert failure_record(caught.value, phase="test")["category"] == "USER_STOPPED"
        assert before == ((output / "allocation-ledger.json").read_bytes(), journal.path.read_bytes(), account.read_bytes())


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("role", ["canary", "retry"])
@pytest.mark.parametrize("allowance,cut", [(1, "none"), (2, "none"), (2, "before"), (2, "after")])
def test_stop_receipt_requires_exact_resume_and_retires_once(prepared, tmp_path, monkeypatch, role, allowance, cut):
    prepared, journal, lineages = setup_document(prepared, tmp_path, incident_allowance=allowance)
    codex, account, plan, output, request = prepared
    root, contract = tmp_path / "control", {"version": "offline-stop-fixture"}
    native = dispatcher.require_dispatch
    stopped = []

    def stop(*arguments, **keywords):
        native(*arguments, **keywords)
        entries = read_json(output / "allocation-ledger.json")["calls"]
        if not stopped and len(entries) == (1 if role == "canary" else 2):
            stopped.append(control.stop(root))
            native(*arguments, **keywords)

    monkeypatch.setattr(dispatcher, "require_dispatch", stop)
    with campaign(prepared, tmp_path, monkeypatch, stop_bindings=[{"root": str(root), "contract": contract}]) as fixture, (
            runtime.settlement_scope()):
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        with owned_stage(output, plan, authority=authority) as (owner, ledger, _reservation), runtime.runtime(
                plan, output, live=True, owner=owner):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            with pytest.raises(RuntimeError) as caught, dispatcher.accounted_model(
                    output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                model.invoke(**request)
            assert failure_record(caught.value, phase="test")["category"] == "USER_STOPPED"
            ledger.reload()
            charged = ledger.record["calls"][-1]
            assert charged["usage"] is None and charged["status"] == "incomplete"
            sequence = next(iter(journal.read()["sequences"].values()))
            index = sequence["slots"][role]["native_allocation"]["index"]
            retained = read_json(output / f"calls/{index:04d}/call.json")
            folder = codex.snapshot / Path(retained["runtime_record"]["path"]).parent
            assert read_json(folder / "process.json")["process_started"] is False
            assert not (folder / "process-start.json").exists()
        before = ledger.path.read_bytes(), journal.path.read_bytes(), account.read_bytes()
        records = set(codex.snapshot.glob(".humanvoice/runtime/*/record.json"))
        for authorization in (None, {"foreign": True}, {"authorized_by": "user", "action": "explicit-resume",
                "contract": contract, "stop_sha256": "wrong-stop"},
                {"authorized_by": "user", "action": "explicit-resume", "contract": {"wrong": True},
                 "stop_sha256": digest((root / "user-stop.json").read_bytes())}):
            if authorization is not None:
                write_json(root / "resume-authorization.json", authorization)
            with pytest.raises(RuntimeError) as caught, owned_stage(output, plan, authority=authority):
                pytest.fail("Stop was bypassed")
            assert failure_record(caught.value, phase="test")["category"] == "USER_STOPPED"
            assert before == (ledger.path.read_bytes(), journal.path.read_bytes(), account.read_bytes())
        assert records == set(codex.snapshot.glob(".humanvoice/runtime/*/record.json"))
        resume(root, contract)
        if cut != "none":
            def worker():
                native_save = journal.save

                def save(record):
                    cancelled = record["sequences"][sequence["identity"]]["slots"][role]["state"] == "cancelled"
                    if cancelled and cut == "before":
                        os._exit(73)
                    native_save(record)
                    if cancelled:
                        os._exit(73)

                journal.save = save
                with owned_stage(output, plan, authority=CampaignAuthority(fixture.implementation, **fixture.arguments)) as (
                        owner, ledger, _reservation), runtime.runtime(plan, output, live=True, owner=owner):
                    dispatcher.reconcile_pairs(journal, owner, ledger)

            cold_run(worker)
        with owned_stage(output, plan, authority=authority) as (owner, ledger, _reservation), runtime.runtime(
                plan, output, live=True, owner=owner):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            for _restart in range(2):
                with dispatcher.accounted_model(output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                    if allowance == 1:
                        with pytest.raises(RuntimeError) as caught:
                            model.invoke(**request)
                        assert failure_record(caught.value, phase="test")["category"] == "BLOCKED_BUDGET"
                    else:
                        assert model.invoke(**request).text == "[]"
                assert ledger.record["calls"][0 if role == "canary" else 1] == charged
                assert len(ledger.record["calls"]) == (1 if role == "canary" else 2) + (2 if allowance == 2 else 0)
            retired = journal.read()["sequences"][sequence["identity"]]
            assert retired["slots"][role]["state"] == "cancelled"
            assert retired["slots"]["retry"]["state"] == ("retired" if role == "canary" else "cancelled")
            assert journal.status()["unresolved_dispatches"] == 0
            assert account.read_bytes() == before[2]
            assert not (output / "allocation-seal.json").exists()
            stable = ledger.path.read_bytes(), journal.path.read_bytes()
            retained_stop = (root / "user-stop.json").read_bytes()
            (root / "user-stop.json").unlink()
            with pytest.raises(RuntimeError) as caught, dispatcher.accounted_model(
                    output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                model.invoke(**request)
            assert failure_record(caught.value, phase="test")["category"] == "USER_STOPPED"
            assert stable == (ledger.path.read_bytes(), journal.path.read_bytes())
            (root / "user-stop.json").write_bytes(retained_stop)


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("role,defect", [(role, defect) for role in ("canary", "retry")
    for defect in ("stop", "call_evidence", "runtime_evidence", "descriptor", "missing_ledger", "prefix", "expiry")
    if defect != "expiry" or role == "retry"])
def test_unallocated_intent_rechecks_authority_evidence_and_freshness(prepared, tmp_path, monkeypatch, role, defect):
    prepared, journal, lineages = setup_document(prepared, tmp_path)
    codex, account, plan, output, request = prepared
    root, contract = tmp_path / "control", {"fixture": "stop-at-intent"}
    with campaign(prepared, tmp_path, monkeypatch, stop_bindings=[{"root": str(root), "contract": contract}]) as fixture, (
            runtime.settlement_scope()):
        def worker():
            with owned_stage(output, plan, authority=CampaignAuthority(fixture.implementation, **fixture.arguments)) as (
                    owner, ledger, _reservation), runtime.runtime(plan, output, live=True, owner=owner):
                native_save = journal.save

                def save(record):
                    native_save(record)
                    if any(sequence["slots"][role].get("invocation", "").startswith("native-intent:")
                           for sequence in record["sequences"].values()):
                        if defect == "stop":
                            control.stop(root)
                            owner.check()
                        os._exit(73)

                journal.save = save
                model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
                try:
                    with dispatcher.accounted_model(output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                        model.invoke(**request)
                except RuntimeError as error:
                    if defect == "stop" and failure_record(error, phase="test")["category"] == "USER_STOPPED":
                        os._exit(73)
                    raise

        cold_run(worker)
        sequence = next(iter(journal.read()["sequences"].values()))
        intent_path = journal.root / (sequence["identity"] + "-" + role + "-allocation.json")
        intent = read_json(intent_path)
        ledger_path = output / "allocation-ledger.json"
        before = ledger_path.read_bytes(), journal.path.read_bytes(), account.read_bytes()
        records = set(codex.snapshot.glob(".humanvoice/runtime/*/record.json"))
        if defect == "call_evidence":
            write_json(output / f"calls/{intent['index']:04d}/foreign.json", {"conflict": True})
        elif defect == "runtime_evidence":
            write_json(codex.snapshot / ".humanvoice/runtime/foreign/allocation-binding.json",
                       {"output": str(output), "key": intent["key"], "index": intent["index"]})
        elif defect == "descriptor":
            write_json(output / f"reconnect-attempts/{intent['index']:04d}.json", {})
        elif defect == "missing_ledger":
            ledger_path.unlink()
        elif defect == "prefix":
            intent["prefix_hash"] = "foreign"
            intent["identity"] = digest({key: value for key, value in intent.items() if key != "identity"})
            write_json(intent_path, intent)
        elif defect == "expiry":
            actual_time = time.time()
            monkeypatch.setattr(time, "time", lambda: actual_time + 901)
        with pytest.raises((ValueError, RuntimeError, FileNotFoundError)), owned_stage(
                output, plan, authority=CampaignAuthority(fixture.implementation, **fixture.arguments)) as (
                owner, ledger, _reservation), runtime.runtime(plan, output, live=True, owner=owner):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            with dispatcher.accounted_model(output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                model.invoke(**request)
        assert records == set(codex.snapshot.glob(".humanvoice/runtime/*/record.json"))
        assert journal.path.read_bytes() == before[1] and account.read_bytes() == before[2]
        assert not ledger_path.exists() if defect == "missing_ledger" else ledger_path.read_bytes() == before[0]
        if defect == "stop":
            resume(root, contract)
            with owned_stage(output, plan, authority=CampaignAuthority(fixture.implementation, **fixture.arguments)) as (
                    owner, ledger, _reservation), runtime.runtime(plan, output, live=True, owner=owner):
                model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
                with dispatcher.accounted_model(output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
                    assert model.invoke(**request).text == "[]"
                assert len(ledger.record["calls"]) == 2
