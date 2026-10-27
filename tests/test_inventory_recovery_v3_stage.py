"""Native consumer migration, source replay and interrupted successor preparation."""

import multiprocessing
import os
import time
from contextlib import ExitStack, contextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest
from test_inventory_size_recovery import native_case
from test_qualification_capture import codex, profile_for
from test_token_epoch_20261025 import baseline

from humanvoice import codex_runtime
from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.commands import inventory_command
from humanvoice.model import ModelAdapter
from tools import automatic_call_grant as grants
from tools import sol_inventory_program as original
from tools.inventory_recovery_v2 import campaign, control, execution, program, semantics
from tools.inventory_recovery_v2 import runtime as historical
from tools.inventory_recovery_v3 import stage, successor
from tools.inventory_recovery_v3.migration import inspect_parent
from tools.inventory_recovery_v3.policy import proposal

__all__ = ["baseline", "codex", "native_case"]
NATIVE_INVOKE = ModelAdapter.invoke


@pytest.fixture
def exhausted(codex, native_case, baseline, tmp_path, monkeypatch, request):
    account, epoch_output, _record = baseline
    original.epoch.activate(path=account, output=epoch_output)
    monkeypatch.setattr(original.account, "ACCOUNT", account)
    snapshot = native_case.snapshot
    profile = profile_for(SimpleNamespace(**{**vars(codex), "snapshot": snapshot}), monkeypatch)
    response, captured = ModelAdapter.invoke, []
    native_case.fail_at = -1

    def boundary(model, **keywords):
        captured.append(original.lifecycle.retained.canonical_request(model, (), keywords))
        raise original.lifecycle.retained.ReplayBoundary()

    monkeypatch.setattr(ModelAdapter, "invoke", boundary)
    with historical.implementation.active.runtime(profile), semantics.runtime(), semantics.context.runtime(), (
            pytest.raises(original.lifecycle.retained.ReplayBoundary)):
        inventory_command.run(SimpleNamespace(snapshot=snapshot, freeze=True, mock=False, timeout=900))
    first_request = captured[0]
    output, grant = tmp_path / "parent", tmp_path / "calls.json"
    monkeypatch.setattr(original, "GRANT", grant)
    monkeypatch.setattr(program, "GRANT", grant)
    cancellation = getattr(request, "param", None)
    cancelled = cancellation in {"cancel_canary", "cancel_retry"}
    monkeypatch.setattr(campaign, "ROOT", tmp_path / "old-campaign")
    with ExitStack() as history:
        history.enter_context(original.epoch.accounting_scope())
        history.enter_context(historical.settlement_scope())
        history.enter_context(historical.implementation.qualified.accounting.accounting_scope())
        grants.create(grant, 20, "offline native successor fixture", account=account)
        plan = program.plan_for(snapshot, {"prefix": [], "remaining_calls": 3, "failed_request": first_request},
            profile, {"fixture": True}, read_json(account), grants.status(grant), inherited=13 if cancelled else 14,
            parent={"eligible": True, "runtime_record_hash": "fixture-parent", "request": first_request,
                    "request_hash": digest(first_request), "eligible_after": 1000})
        write_json(output / "plan.json", plan)

        def respond(model, **keywords):
            actual = original.lifecycle.retained.canonical_request(model, (), keywords)
            if actual == execution.CANARY:
                write_json(codex.settings, {"response": []})
            elif actual["purpose"] == "concept_extraction":
                return response(model, **keywords)
            else:
                write_json(codex.settings, {"transport_failures": [{"purpose": actual["purpose"], "status": 504}]})
            return NATIVE_INVOKE(model, **keywords)

        monkeypatch.setattr(ModelAdapter, "invoke", respond)
        actual_time, native_wait, offset = time.time, execution.network.wait_until, [0]

        class ReceiptClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromtimestamp(time.time(), tz)

        def wait(path, identity, failed_at, **keywords):
            offset[0] += max(0, failed_at + 900 - time.time())
            return native_wait(path, identity, failed_at, clock=time.time)

        with monkeypatch.context() as clocks, grants.stage(grant, output):
            clocks.setattr(time, "time", lambda: actual_time() + offset[0])
            clocks.setattr(codex_runtime, "datetime", ReceiptClock)
            clocks.setattr(execution.network, "wait_until", wait)
            original.epoch.claim(plan, output, account_path=account)
            ledger = original.epoch.EpochLedger(output / "allocation-ledger.json", plan)
            with historical.implementation.automatic_recovery.exclusive_execution(output), historical.runtime(
                    plan, output, live=True, lock_fd=historical.implementation.automatic_recovery.execution_fds()[0]):
                def consume():
                    with execution.accounted_model(output, plan, ledger), semantics.runtime(), semantics.context.runtime():
                        return inventory_command.run(SimpleNamespace(snapshot=snapshot, freeze=True, mock=False, timeout=900))

                if cancelled:
                    native_attempt, stopped = execution.predecessor.attempt, []

                    def stop_attempt(*arguments):
                        is_canary = arguments[4] == execution.CANARY
                        if not stopped and is_canary == (cancellation == "cancel_canary"):
                            stopped.append(True)
                            control.stop()
                        return native_attempt(*arguments)

                    with monkeypatch.context() as interruption:
                        interruption.setattr(execution.predecessor, "attempt", stop_attempt)
                        with pytest.raises(semantics.context.InvocationStopped, match="resume"):
                            consume()
                    write_json(campaign.ROOT / "resume-authorization.json", {
                        "stop_sha256": digest((campaign.ROOT / "user-stop.json").read_bytes()),
                        "contract": campaign.contract(), "authorized_by": "user", "action": "explicit-resume"})
                with pytest.raises(semantics.context.InvocationStopped, match="allowance"):
                    consume()
                write_json(output / "execution.json", {"status": "nonpass", "plan_identity": plan["plan_identity"],
                                                       "attempted": len(ledger.record["calls"]), "required": 3})
                original.account.settle(output, account=account)
        expected = ["complete", "complete", "incomplete", "complete"]
        if cancelled:
            expected.insert(0 if cancellation == "cancel_canary" else 1, "incomplete")
        assert [entry["status"] for entry in ledger.record["calls"]] == expected
        report = inspect_parent(output, account, verify_settlement=historical.verify_settlement,
            reconstruct=stage.reconstruct, verify_qualification=lambda *arguments: None)
        assert report["retained_responses"] == 1 and report["remaining_requests"] == 2
        policy = proposal(remaining_requests=2, inherited_recovery=17, incident_allowance=2,
                          split_allowance=1, qualification_calls=0,
                          available_calls=grants.status(grant)["available"],
                          available_tokens=read_json(account)["allowance"] - read_json(account)["reservation_ceiling"])
        transition = successor.budget_transition(report, policy, account_path=account,
            verify_settlement=historical.verify_settlement, reconstruct=stage.reconstruct,
            verify_qualification=lambda *arguments: None)
        monkeypatch.setattr(ModelAdapter, "invoke", NATIVE_INVOKE)
        if getattr(request, "param", None) == "cold":
            history.close()
        yield SimpleNamespace(account=account, grant=grant, output=output, transition=transition,
                              codex=codex, response=response, native_case=native_case, clock_offset=offset[0],
                              close_history=history.close)


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("cut", [None, "snapshot-copy.json", "observations.json", "verification.json", "preparation-intent.json", "transition.json", "admission-probe.json",
                                 "prepared-snapshot.json", "prepared-authority.json", "plan.json", "execution.json"])
def test_native_successor_prepare_survives_publication_cuts(exhausted, tmp_path, cut):
    output = tmp_path / "successor"
    before = {path: path.read_bytes() for path in (exhausted.account, exhausted.grant,
              exhausted.output / "execution.json", exhausted.output / "allocation-ledger.json")}

    def worker():
        native = stage.immutable

        def persist(path, value):
            native(path, value)
            if path.name == cut:
                os._exit(73)

        stage.bridge.immutable = persist
        stage.immutable = persist
        stage.Stage(output, exhausted.transition).prepare()

    if cut:
        process = multiprocessing.get_context("fork").Process(target=worker)
        process.start()
        process.join(60)
        if process.is_alive():
            process.kill()
            process.join(5)
        assert process.exitcode == 73
    current = stage.Stage(output, exhausted.transition)
    plan = current.prepare()
    report = read_json(output / "admission-probe.json")
    assert report["model_calls"] == 0 and report["inherited_calls"] == 1
    assert report["first_request"] == exhausted.transition["parent_failure"]["request"]
    assert report["observation"]["purpose"] == "reconstruction_verification"
    assert read_json(output / "execution.json")["status"] == "prepared"
    assert current.prepare() == plan and current.validate() == plan
    assert all(path.read_bytes() == content for path, content in before.items())
    assert not (output / "allocation-ledger.json").exists()
    assert sum(read_json(path).get("runtime_type") == "codex-cli"
               for path in current.snapshot.glob(".humanvoice/runtime/*/record.json")) == 4
    with grants.stage(exhausted.grant, output):
        original.epoch.claim(plan, output, account_path=exhausted.account)
    retained_account = exhausted.account.read_bytes()
    assert current.validate() == plan
    assert exhausted.account.read_bytes() == retained_account
    with pytest.raises(RuntimeError, match="separate campaign admission"):
        current.run("execute")


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("field", ["maximum_new_calls", "authorization", "account", "baseline"])
def test_prepared_successor_rejects_changed_grant(exhausted, tmp_path, field):
    current = stage.Stage(tmp_path / "successor", exhausted.transition)
    current.prepare()
    grant = read_json(exhausted.grant)
    grant[field] = [{"foreign": True}] if field == "baseline" else "changed"
    write_json(exhausted.grant, grant)
    before = {path: path.read_bytes() for path in (exhausted.account, exhausted.grant, current.output / "plan.json")}
    for action in (current.validate, current.prepare):
        with pytest.raises((ValueError, RuntimeError), match="grant|authority"):
            action()
    assert all(path.read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("growth", ["reserved", "settled", "exhausted"])
def test_preparation_intent_survives_account_growth(exhausted, tmp_path, growth):
    output = tmp_path / "successor"

    def worker():
        native = stage.immutable

        def persist(path, value):
            native(path, value)
            if path.name == "prepared-authority.json":
                os._exit(73)

        stage.immutable = persist
        stage.Stage(output, exhausted.transition).prepare()

    process = multiprocessing.get_context("fork").Process(target=worker)
    process.start()
    process.join(60)
    if process.is_alive():
        process.kill()
        process.join(5)
    assert process.exitcode == 73
    intent = (output / "preparation-intent.json").read_bytes()
    plan = read_json(output / "preparation-intent.json")["plan"]
    sibling = stage.Stage(tmp_path / "sibling", exhausted.transition)
    sibling_plan = sibling.prepare()
    with stage.runtime.settlement_scope(), grants.stage(exhausted.grant, sibling.output):
        original.epoch.claim(sibling_plan, sibling.output, account_path=exhausted.account)
        if growth == "settled":
            write_json(sibling.output / "execution.json", {"status": "nonpass",
                "plan_identity": sibling_plan["plan_identity"], "required": len(sibling_plan["calls"]), "attempted": 0})
            original.account.settle(sibling.output, account=exhausted.account)
    if growth == "exhausted":
        another = stage.Stage(tmp_path / "another", exhausted.transition)
        another_plan = another.prepare()
        with grants.stage(exhausted.grant, another.output):
            original.epoch.claim(another_plan, another.output, account_path=exhausted.account)
    before = {path: path.read_bytes() for path in (exhausted.account, exhausted.grant,
              exhausted.grant.with_suffix(".stages.json"), exhausted.output / "allocation-ledger.json")}
    with stage.runtime.settlement_scope():
        current = stage.Stage(output, exhausted.transition)
        if growth == "exhausted":
            with pytest.raises(RuntimeError, match="no longer fits current authority"):
                current.prepare()
            assert not (output / "plan.json").exists()
        else:
            assert current.prepare() == plan
            assert current.prepare() == plan and current.validate() == plan
    assert all(path.read_bytes() == content for path, content in before.items())
    assert (output / "preparation-intent.json").read_bytes() == intent
    assert not (output / "allocation-ledger.json").exists()


def configure_cold_history(exhausted, tmp_path, monkeypatch, *, completed):
    from test_failure_first_native import initialize_fixture_worker

    from humanvoice import automatic_accounting
    from tools import active_session_program, parallel_verification_replay

    native_pool = parallel_verification_replay.ProcessPoolExecutor
    native_warmup = parallel_verification_replay.cached_parallel_verification

    def pool(**keywords):
        previous = keywords.pop("initializer", None)
        arguments = keywords.pop("initargs", ())
        return native_pool(**keywords, initializer=initialize_fixture_worker, initargs=(
            original.epoch.BASELINE_IDENTITY, original.epoch.BASELINE_BYTES,
            automatic_accounting.TOKEN_AUTHORIZATION_IDENTITY, previous, arguments))

    @contextmanager
    def cold_history(**keywords):
        with native_warmup(account=exhausted.account, workers=16, progress=tmp_path / "warmup.json") as report:
            assert report["completed"] == completed and report["model_calls"] == 0 and report["account_writes"] == 0
            yield report

    monkeypatch.setattr(parallel_verification_replay, "ProcessPoolExecutor", pool)
    monkeypatch.setattr(active_session_program, "cached_parallel_verification", cold_history)


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("exhausted", ["cold"], indirect=True)
def test_successor_public_offline_entrypoint(exhausted, tmp_path, monkeypatch):
    configure_cold_history(exhausted, tmp_path, monkeypatch, completed=1)
    current = stage.Stage(tmp_path / "successor", exhausted.transition)
    before = exhausted.account.read_bytes(), exhausted.grant.read_bytes()
    plan = current.run("prepare")
    assert current.run("validate") == plan
    assert before == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_preparation_has_read_only_campaign_descriptor(exhausted, tmp_path, monkeypatch):
    from tools.inventory_recovery_v3.campaign_preparation import verify_prepared

    current = stage.Stage(tmp_path / "prepared-campaign", exhausted.transition)
    plan = current.prepare()
    exhausted.close_history()
    configure_cold_history(exhausted, tmp_path, monkeypatch, completed=1)
    intent = {"output": str(current.output), "transition": current.transition}
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns)
              for path in current.output.rglob("*") if path.is_file()}
    authority = exhausted.account.read_bytes(), exhausted.grant.read_bytes()
    descriptor = verify_prepared(intent, lambda: True)
    assert descriptor["plan_identity"] == plan["plan_identity"]
    assert descriptor["plan_sha256"] == digest((current.output / "plan.json").read_bytes())
    assert verify_prepared(intent, lambda: True) == descriptor
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns)
                      for path in current.output.rglob("*") if path.is_file()}
    assert authority == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())
    veto = iter([True, False])
    with pytest.raises(RuntimeError, match="ownership changed"):
        verify_prepared(intent, lambda: next(veto))
    marker = current.output / "execution.json"
    write_json(marker, {**read_json(marker), "model_calls": False})
    with pytest.raises(RuntimeError, match="prepared marker"):
        verify_prepared(intent, lambda: True)


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_campaign_initialization_binds_one_journal(exhausted, tmp_path, monkeypatch):
    from tools.inventory_recovery_v3 import campaign_history, campaign_initialization
    from tools.inventory_recovery_v3.failures import RecoveryStop

    root = tmp_path / "native-campaign"
    current = stage.Stage(root / "generation-00", exhausted.transition)
    plan = current.prepare()
    exhausted.close_history()
    configure_cold_history(exhausted, tmp_path, monkeypatch, completed=1)
    authority = exhausted.account.read_bytes(), exhausted.grant.read_bytes()
    native, cuts = campaign_history.persist, []

    def cut(path, value):
        native(path, value)
        if path.name == "cursor.json" and not cuts:
            cuts.append(True)
            raise OSError("campaign seed publication interrupted")

    with monkeypatch.context() as interrupted:
        interrupted.setattr(campaign_history, "persist", cut)
        with pytest.raises(OSError, match="publication interrupted"):
            campaign_initialization.initialize(root, check=lambda: True)
    assert cuts == [True]
    proposal_bytes = (root / "campaign-proposal.json").read_bytes()
    result = campaign_initialization.initialize(root, check=lambda: True)
    assert result["status"] == "OFFLINE_CAMPAIGN_INITIALIZED"
    assert result["state"]["cursor"]["plan_identity"] == plan["plan_identity"]
    assert result["seed"]["journal"]["binding"]["authority"] == read_json(root / "campaign-proposal.json")["identity"]
    assert result["seed"]["binding"]["initial_journal"]["inherited_recovery"]["sequences"]
    assert result["model_calls"] == result["account_writes"] == result["grant_writes"] == 0
    assert result["live_execution_enabled"] is False
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in root.rglob("*") if path.is_file()}
    assert campaign_initialization.initialize(root, check=lambda: True) == result
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in root.rglob("*") if path.is_file()}
    assert (root / "campaign-proposal.json").read_bytes() == proposal_bytes
    assert authority == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())
    (root / "recovery-journal/reservations.json").unlink()
    with pytest.raises(RecoveryStop):
        campaign_initialization.initialize(root, check=lambda: True)
    assert not (root / "recovery-journal/reservations.json").exists()
    assert authority == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("boundary,mutation", [("verified", "plan"), ("verified", "grant"),
                                                ("imported", "grant"), ("imported", "missing_grant")])
def test_native_bootstrap_rejects_changes_after_verified_replay(exhausted, tmp_path, monkeypatch, boundary, mutation):
    from tools.inventory_recovery_v3 import campaign_initialization
    from tools.inventory_recovery_v3.failures import RecoveryStop
    from tools.inventory_recovery_v3.requests import NativeRequests

    root = tmp_path / "native-campaign"
    current = stage.Stage(root / "generation-00", exhausted.transition)
    current.prepare()
    exhausted.close_history()
    configure_cold_history(exhausted, tmp_path, monkeypatch, completed=1)
    authority, changed = exhausted.account.read_bytes(), []

    def change():
        if mutation == "missing_grant":
            exhausted.grant.unlink()
        elif mutation == "grant":
            value = {**read_json(exhausted.grant), "authorization": "different authorization"}
            value["identity"] = digest({key: value for key, value in value.items() if key != "identity"})
            write_json(exhausted.grant, value)
        else:
            path = current.output / "plan.json"
            path.write_bytes(path.read_bytes() + b" ")
        changed.append(True)

    if boundary == "verified":
        native = campaign_initialization.verify_prepared

        def verify(intent, check):
            result = native(intent, check)
            change()
            return result

        monkeypatch.setattr(campaign_initialization, "verify_prepared", verify)
    else:
        native = NativeRequests.import_history

        def imported(resolver, observations):
            native(resolver, observations)
            change()

        monkeypatch.setattr(NativeRequests, "import_history", imported)
    with pytest.raises((RecoveryStop, FileNotFoundError)):
        campaign_initialization.initialize(root, check=lambda: True)
    assert changed == [True]
    assert not (root / "seed.json").exists()
    assert exhausted.account.read_bytes() == authority


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_public_offline_preflight_initializes_canonical_campaign(exhausted, tmp_path, monkeypatch):
    from tools import prepare_inventory_recovery_v3 as preflight

    exhausted.close_history()
    configure_cold_history(exhausted, tmp_path, monkeypatch, completed=1)
    base = tmp_path / "program"
    base.mkdir()
    (base / "active-session-program.lock").touch()
    (exhausted.output / "execution.lock").touch()
    monkeypatch.setattr(preflight.program, "BASE", base)
    monkeypatch.setattr(preflight.review, "OUTPUT", tmp_path / "preflight")
    cursor = {"generation": 2, "output": str(exhausted.output)}
    monkeypatch.setattr(preflight.campaign, "cursor", lambda: cursor)
    monkeypatch.setattr(preflight, "proposal", lambda **keywords: exhausted.transition["policy"])
    authority = exhausted.account.read_bytes(), exhausted.grant.read_bytes()
    assert preflight.prepare() == 0
    directory = preflight.review.OUTPUT / "preparation" / digest(preflight.review.sources())[:20]
    report = read_json(directory / "preparation.json")
    seed = read_json(directory / "campaign/seed.json")
    assert report["status"] == "OFFLINE_PREPARATION_PASS"
    assert report["campaign_seed_identity"] == seed["identity"]
    assert report["recovery_journal"] == seed["journal"]
    assert report["model_calls"] == report["account_writes"] == report["grant_writes"] == 0
    assert report["live_execution_enabled"] is False
    assert not (directory / "ownership-preflight").exists()
    assert authority == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())
    probe_root = directory / "campaign/generation-00/probe" / digest(stage.runtime.contract())[:16]

    def immutable_membership():
        return {path: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in (directory / "campaign").rglob("*") if path.is_file()
                and not any(path.is_relative_to(probe_root / name) for name in ("snapshot", "revalidation"))}

    retained = immutable_membership()
    assert preflight.prepare() == 0
    assert retained == immutable_membership()
    assert authority == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())
