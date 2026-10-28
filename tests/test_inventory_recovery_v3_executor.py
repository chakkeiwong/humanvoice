"""Exercise native completion and paused/frozen failure handling through the executor."""

import time
from copy import deepcopy
from datetime import datetime

import pytest
from test_inventory_recovery_v3_owner import campaign
from test_inventory_recovery_v3_stage import (
    NATIVE_INVOKE,
    baseline,
    codex,
    configure_cold_history,
    exhausted,
    native_case,
)

from humanvoice import codex_runtime
from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.model import ModelAdapter
from tools.inventory_recovery_v2 import control
from tools.inventory_recovery_v3 import (
    accounting,
    continuation,
    dispatcher,
    execution,
    executor,
    journal_binding,
    runtime,
    stage,
)
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import RecoveryReservations
from tools.inventory_recovery_v3.stage_authority import CampaignAuthority

__all__ = ["baseline", "codex", "exhausted", "native_case"]


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("fault", [None, "pause", "frozen_cut", "semantic", "stop_before_nonpass",
                                   "stop_after_nonpass", "stop_after_pass", "oversized", "canary_down",
                                   "claim_native_cut", "claim_head_cut", "claim_receipt_cut"])
def test_native_executor_completion_and_failures(exhausted, tmp_path, monkeypatch, fault):
    current = stage.Stage(tmp_path / "successor", exhausted.transition)
    plan = current.prepare()
    journal = RecoveryReservations(tmp_path / "pairs", plan[runtime.FIELD]["policy"], {
        "document": plan["bindings"]["source"], "migration": plan[runtime.FIELD]["migration_identity"],
        "authority": "offline-fixture"})
    journal.initialize()
    paused = []

    def respond(model, **keywords):
        request = execution.predecessor.retained.canonical_request(model, (), keywords)
        if request == execution.CANARY:
            settings = ({"transport_failures": [{"purpose": request["purpose"], "status": 504}]}
                        if fault == "canary_down" else {"response": []})
            write_json(exhausted.codex.settings, settings)
            return NATIVE_INVOKE(model, **keywords)
        if fault == "oversized" and request["purpose"] == "coverage_verification":
            write_json(exhausted.codex.settings, {"raw": "x" * (runtime.bridge.diagnosis.capture.MAX_BYTES + 1)})
            return NATIVE_INVOKE(model, **keywords)
        if fault in {"semantic", "stop_before_nonpass", "stop_after_nonpass"}:
            write_json(exhausted.codex.settings, {"response": []})
            return NATIVE_INVOKE(model, **keywords)
        return exhausted.response(model, **keywords)

    monkeypatch.setattr(ModelAdapter, "invoke", respond)
    actual_time, offset = time.time, [exhausted.clock_offset]

    class ReceiptClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(time.time(), tz)

    native_wait = dispatcher.network.wait_until

    def wait(path, identity, failed_at, **keywords):
        offset[0] += max(0, failed_at + 900 - time.time())
        return native_wait(path, identity, failed_at, clock=time.time)

    native_dispatch = journal.dispatch

    def dispatch(*arguments, **keywords):
        return native_dispatch(*arguments, **keywords, clock=time.time)

    monkeypatch.setattr(time, "time", lambda: actual_time() + offset[0])
    monkeypatch.setattr(codex_runtime, "datetime", ReceiptClock)
    monkeypatch.setattr(dispatcher.network, "wait_until", wait)
    monkeypatch.setattr(journal, "dispatch", dispatch)
    native_bundle = executor.bundle.completed_bundle
    if fault == "frozen_cut":
        def rejected(*arguments):
            raise RuntimeError("offline interruption after baseline publication")
        monkeypatch.setattr(executor.bundle, "completed_bundle", rejected)
    prepared = exhausted.codex, exhausted.account, plan, current.output, exhausted.transition["proof"]["failed_request"]
    stops = {"root": str(tmp_path / "controls"), "contract": {"fixture": "executor-stop"}}
    with campaign(prepared, tmp_path / "campaign", monkeypatch, retained_grant=exhausted.grant,
                  stop_bindings=[stops], recovery_journal=journal_binding.descriptor(journal),
                  consumption=True) as fixture, (
            runtime.settlement_scope()):
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        fixture.consumption.check = authority.check
        statuses = []
        if fault and fault.startswith("claim_"):
            from pathlib import Path

            from tools.inventory_recovery_v3 import consumption_floors

            native_write = current.implementation.epoch.write_json
            native_persist = consumption_floors.persist
            fired = []

            def interrupt(label):
                if fault == "claim_" + label + "_cut" and not fired:
                    fired.append(label)
                    raise OSError("executor claim cut")

            def write(path, value):
                native_write(path, value)
                if Path(path) == exhausted.account:
                    interrupt("native")
                elif Path(path).name == "account-reservation.json":
                    interrupt("receipt")

            def persist(path, value, **keywords):
                native_persist(path, value, **keywords)
                if path.name == "account-head.json" and value["pending"] is None:
                    interrupt("head")

            with monkeypatch.context() as patch:
                patch.setattr(current.implementation.epoch, "write_json", write)
                patch.setattr(consumption_floors, "persist", persist)
                with pytest.raises(OSError, match="executor claim cut"):
                    executor.execute(current, authority=authority, journal=journal, refresh=statuses.append)
            assert fired
            assert not (current.output / "allocation-ledger.json").exists()
            assert len([entry for entry in read_json(exhausted.account)["plans"]
                        if entry["output"] == str(current.output)]) == 1
        if fault is None:
            substitute = RecoveryReservations(tmp_path / "substitute-pairs", journal.policy, journal.binding)
            substitute.initialize()
            unchanged = exhausted.account.read_bytes(), exhausted.grant.read_bytes()
            with pytest.raises(RecoveryStop, match="canonical recovery journal"):
                executor.execute(current, authority=authority, journal=substitute, refresh=statuses.append)
            assert unchanged == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())
            assert not (current.output / "native-claim-intent.json").exists()

        def publish(state):
            statuses.append(state)
            if fault == "pause" and state["status"] == "EXECUTING" and not paused:
                paused.append(True)
                raise RecoveryStop("USER_STOPPED", "offline user stop")

        if fault and fault.startswith("stop_"):
            retained = {}
            native_finalize, native_persist = executor.finalize_failure, executor.persist
            from tools.inventory_recovery_v3 import terminal as terminal_module

            def stop():
                control.stop(stops["root"])
                retained.update(ledger=(current.output / "allocation-ledger.json").read_bytes(),
                    account=exhausted.account.read_bytes(), terminal=(current.output / "execution.json").read_bytes())

            def finalize(*arguments, **keywords):
                if fault == "stop_before_nonpass":
                    stop()
                return native_finalize(*arguments, **keywords)

            def persist(path, value):
                native_persist(path, value)
                if path == current.output / "execution.json" and (
                        fault == "stop_after_nonpass" and value.get("status") == "nonpass"
                        or fault == "stop_after_pass" and value.get("status") == "pass"):
                    stop()

            with monkeypatch.context() as boundary:
                boundary.setattr(executor, "finalize_failure", finalize)
                boundary.setattr(executor, "persist", persist)
                boundary.setattr(terminal_module, "persist", persist)
                with pytest.raises(RuntimeError, match="resume authorization"):
                    executor.execute(current, authority=authority, journal=journal, refresh=publish)
            terminal = read_json(current.output / "execution.json")
            assert terminal["status"] == ("paused_user" if fault == "stop_before_nonpass" else
                                          "pass" if fault == "stop_after_pass" else "nonpass")
            assert not (current.output / "allocation-seal.json").exists()
            assert exhausted.account.read_bytes() == retained["account"]
            assert (current.output / "allocation-ledger.json").read_bytes() == retained["ledger"]
            assert statuses[-1] == read_json(current.output / "progress.json")
            assert statuses[-1]["status"] == "USER_STOPPED"
            assert statuses[-1]["settlement_reconciliation_required"] == (fault != "stop_before_nonpass")
            if fault != "stop_before_nonpass":
                assert (current.output / "execution.json").read_bytes() == retained["terminal"]
            stop_path = tmp_path / "controls/user-stop.json"
            write_json(stop_path.with_name("resume-authorization.json"), {
                "stop_sha256": digest(stop_path.read_bytes()), "contract": stops["contract"],
                "authorized_by": "user", "action": "explicit-resume"})
            summary = executor.execute(current, authority=authority, journal=journal, refresh=statuses.append)
            assert (current.output / "allocation-ledger.json").read_bytes() == retained["ledger"]
        elif fault in {"pause", "frozen_cut"}:
            with pytest.raises(BaseException, match="offline"):
                executor.execute(current, authority=authority, journal=journal, refresh=publish)
            terminal = read_json(current.output / "execution.json")
            assert terminal["status"] == ("paused_user" if fault == "pause" else "blocked_finalization")
            assert not (current.output / "allocation-seal.json").exists()
            if fault == "pause":
                return
            before = (current.output / "allocation-ledger.json").read_bytes()
            consumed = journal.path.read_bytes()
            corrupted = journal.read()
            assert corrupted["sequences"]
            corrupted["sequences"].clear()
            write_json(journal.path, {**corrupted, "identity": digest(
                {key: value for key, value in corrupted.items() if key != "identity"})})
            retained_authority = exhausted.account.read_bytes(), exhausted.grant.read_bytes()
            with pytest.raises(RecoveryStop, match="consumption membership"):
                executor.execute(current, authority=authority, journal=journal, refresh=statuses.append)
            assert retained_authority == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())
            assert not (current.output / journal_binding.CHECKPOINT).exists()
            journal.path.write_bytes(consumed)
            monkeypatch.setattr(executor.bundle, "completed_bundle", native_bundle)
            summary = executor.execute(current, authority=authority, journal=journal, refresh=statuses.append)
            assert (current.output / "allocation-ledger.json").read_bytes() == before
        else:
            summary = executor.execute(current, authority=authority, journal=journal, refresh=statuses.append)
        semantic_failure = fault in {"semantic", "stop_before_nonpass", "stop_after_nonpass"}
        assert summary["status"] == ("nonpass" if semantic_failure or fault in {"oversized", "canary_down"} else "pass")
        if semantic_failure:
            assert summary["failure"]["category"] == "BLOCKED_ENGINEERING"
        usage = accounting.verify_settlement(current.output)["report"]
        assert usage["allocated_calls"] == summary["attempted"]
        assert fixture.consumption.inspect("account")["status"] == "READY"
        assert fixture.consumption.inspect("stages")["status"] == "READY"
        assert len(fixture.consumption.inspect("account")["head"]["history"]) == 2
        before = (current.output / "allocation-ledger.json").read_bytes(), exhausted.account.read_bytes()
        assert executor.execute(current, authority=authority, journal=journal, refresh=statuses.append) == summary
        assert before == ((current.output / "allocation-ledger.json").read_bytes(), exhausted.account.read_bytes())
        assert statuses[-1] == summary
        if fault in {"oversized", "canary_down"}:
            retained = continuation.retained(current.output)
            assert continuation.require_transition(retained) == retained
            assert retained["recovery_sessions_used"] == (19 if fault == "oversized" else 18)
            assert len(retained["proof"]["prefix"]) == (2 if fault == "oversized" else 1)
            changed = deepcopy(retained)
            changed["recovery_sessions_used"] -= 1
            with pytest.raises(RuntimeError, match="independently settled"):
                continuation.require_transition(continuation.identified(changed))
            discovery = stage.Stage(tmp_path / "discovery", retained).probe(discovery=True)
            assert discovery["first_request"] == retained["proof"]["failed_request"]
            if fault == "oversized":
                transition = continuation.split_successor(retained, discovery["observation"])
                next_stage = stage.Stage(tmp_path / "split-successor", transition)
                next_plan = next_stage.prepare()
                assert next_plan[runtime.FIELD]["parent_failure"]["request"] != retained["proof"]["failed_request"]
                assert len(next_plan["calls"]) == 2
                assert next_plan[runtime.FIELD]["recovery_sessions_used"] == 20
                assert stage.Stage(next_stage.output, transition).validate() == next_plan
                from tools.inventory_recovery_v3 import ancestry

                assert ancestry.validate(next_stage.output, next_plan) == next_plan
                folder = current.output / "probe" / digest(runtime.contract())[:16]
                paths = [folder / "observations.json", folder / "verification.json", current.output / "admission-probe.json"]
                saved = {path: path.read_bytes() for path in paths}
                authority_before = exhausted.account.read_bytes(), exhausted.grant.read_bytes(), (current.output / "allocation-ledger.json").read_bytes()
                for mutation in ("remove", "reorder"):
                    observations = read_json(paths[0])
                    if mutation == "remove":
                        observations["observations"].pop(0)
                    else:
                        observations["observations"].insert(0, deepcopy(observations["observations"][-1]))
                    report = read_json(paths[1])
                    report["observations_hash"] = digest(observations)
                    write_json(paths[0], observations)
                    for path in paths[1:]:
                        write_json(path, report)
                    try:
                        for validate in (lambda: ancestry.validate(current.output, plan), lambda: continuation.retained(current.output)):
                            with pytest.raises(RuntimeError, match="transcript differs from its sealed plan"):
                                validate()
                    finally:
                        for path, content in saved.items():
                            path.write_bytes(content)
                assert authority_before == (exhausted.account.read_bytes(), exhausted.grant.read_bytes(), (current.output / "allocation-ledger.json").read_bytes())
                for name in ("preparation-intent.json", "admission-probe.json", "transition.json"):
                    path = current.output / name
                    content = path.read_bytes()
                    write_json(path, {})
                    try:
                        with pytest.raises((ValueError, RuntimeError, KeyError)):
                            continuation.retained(current.output)
                    finally:
                        path.write_bytes(content)
                with ancestry.visit(current.output, plan), pytest.raises(RuntimeError, match="ancestry repeats"):
                    ancestry.validate(current.output, plan)
                before_next = exhausted.account.read_bytes(), exhausted.grant.read_bytes()
                assert next_stage.prepare() == next_plan
                assert before_next == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())
                monkeypatch.setattr(ModelAdapter, "invoke", lambda model, **keywords: (
                    respond(model, **keywords) if execution.predecessor.retained.canonical_request(model, (), keywords)
                    == execution.CANARY else exhausted.response(model, **keywords)))
                substitute = RecoveryReservations(tmp_path / "second-stage-substitute", journal.policy, journal.binding)
                substitute.initialize()
                with pytest.raises(RecoveryStop, match="canonical recovery journal"):
                    executor.execute(next_stage, authority=authority, journal=substitute, refresh=statuses.append)
                assert before_next == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())
                consumed = journal.path.read_bytes()
                changed = journal.read()
                changed["sequences"].clear()
                write_json(journal.path, {**changed, "identity": digest(
                    {key: value for key, value in changed.items() if key != "identity"})})
                try:
                    with pytest.raises(RecoveryStop, match="consumption membership"):
                        executor.execute(next_stage, authority=authority, journal=journal, refresh=statuses.append)
                    assert before_next == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())
                finally:
                    journal.path.write_bytes(consumed)
                result = executor.execute(next_stage, authority=authority, journal=journal, refresh=statuses.append)
                assert result["status"] == "pass"
                assert sum(row["extra_calls"] for row in journal.read()["splits"].values()) == 1
                unchanged = exhausted.account.read_bytes(), (next_stage.output / "allocation-ledger.json").read_bytes()
                assert executor.execute(next_stage, authority=authority, journal=journal, refresh=statuses.append) == result
                assert unchanged == (exhausted.account.read_bytes(), (next_stage.output / "allocation-ledger.json").read_bytes())
    if fault is None:
        exhausted.close_history()
        configure_cold_history(exhausted, tmp_path, monkeypatch, completed=2)
        before = exhausted.account.read_bytes(), exhausted.grant.read_bytes()
        with accounting.history_scope():
            assert accounting.verify_settlement(current.output)["report"] == usage
            current.implementation.account.validate_account(read_json(exhausted.account))
        assert before == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())
