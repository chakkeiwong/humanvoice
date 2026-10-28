"""Native receipt checks through the private final-spawn boundary."""

import stat
from pathlib import Path

import pytest
from test_failure_first_native import baseline, codex, prepared
from test_inventory_recovery_v3_execution import setup_document
from test_inventory_recovery_v3_native_ownership import complete_campaign
from test_inventory_recovery_v3_runtime_predicates import issue_stop

from humanvoice import codex_runtime
from humanvoice.artifacts import read_json, write_json
from humanvoice.model import ModelAdapter, ModelConfig
from tools.inventory_recovery_v3 import (
    cancellation,
    dispatcher,
    journal_binding,
    provider_capture,
    provider_runtime,
    rejection,
    runtime,
)
from tools.inventory_recovery_v3.failures import RecoveryStop, failure_record
from tools.inventory_recovery_v3.stage_owner import owned_stage

__all__ = ["baseline", "codex", "prepared"]


def retained(directory):
    return {str(path.relative_to(directory)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in directory.rglob("*") if path.is_file()}


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_runtime_private_collector_forwards_full_lease(prepared, tmp_path, monkeypatch):
    prepared, journal, lineages = setup_document(prepared, tmp_path)
    codex, _account, plan, _output, request = prepared
    native = runtime.bridge.NATIVE_RUNTIME.__wrapped__.__globals__
    qualified, capture = native["qualified"], native["qualified"].capture
    original_launch, original_command = codex_runtime.launch, codex_runtime.command
    capture_launch, native_writer = capture.launch, native["write_json"]
    native_spawn, observations = provider_capture.OwnedPopen, []
    with complete_campaign(prepared, tmp_path, monkeypatch, recovery_journal=journal_binding.descriptor(journal)) as fixture, (
            runtime.settlement_scope()), owned_stage(fixture.output, plan, authority=fixture.authority) as (owner, ledger, _):
        def spawn(args, **kwargs):
            if "--output-last-message" in args:
                observations.append(kwargs["pass_fds"])
                assert kwargs["pass_fds"] == owner.execution_descriptors
                assert len(kwargs["pass_fds"]) > 3
            return native_spawn(args, **kwargs)

        monkeypatch.setattr(provider_capture, "OwnedPopen", spawn)
        with runtime.runtime(plan, fixture.output, live=True, owner=owner), dispatcher.accounted_model(
                fixture.output, plan, ledger, journal=journal, owner=owner, lineages=lineages):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            assert model.invoke(**request).text == "[]"
        assert len(observations) == 2
        assert native["qualified"] is qualified and qualified.capture is capture
        assert capture.launch is capture_launch and native["write_json"] is native_writer
    assert codex_runtime.launch is original_launch and codex_runtime.command is original_command


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("category", ["USER_STOPPED", "BLOCKED_OWNERSHIP"])
def test_final_fifo_veto_has_native_receipt_and_cold_reuse(prepared, tmp_path, monkeypatch, category):
    prepared, journal, lineages = setup_document(prepared, tmp_path)
    codex, _account, plan, _output, request = prepared
    native = provider_capture.launch
    observations = []
    with complete_campaign(prepared, tmp_path, monkeypatch, recovery_journal=journal_binding.descriptor(journal)) as fixture, (
            runtime.settlement_scope()), owned_stage(fixture.output, plan, authority=fixture.authority) as (owner, ledger, _):
        def capture(arguments, prompt, directory, **kwargs):
            final = kwargs["before_spawn"]

            def veto():
                final()
                assert stat.S_ISFIFO((Path(directory) / "response-envelope.json").stat().st_mode)
                observations.append(Path(directory))
                if category == "USER_STOPPED":
                    issue_stop(fixture.configuration, 1)
                    return final()
                raise RecoveryStop(category, "last owned guard")

            return native(arguments, prompt, directory, **{**kwargs, "before_spawn": veto})

        monkeypatch.setattr(provider_capture, "launch", capture)
        with runtime.runtime(plan, fixture.output, live=True, owner=owner), pytest.raises(RuntimeError) as caught, (
                dispatcher.accounted_model(fixture.output, plan, ledger, journal=journal, owner=owner, lineages=lineages)):
            ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot).invoke(**request)
        assert failure_record(caught.value, phase="test")["category"] == category
        assert len(observations) == 1
        directory = observations[0]
        receipt = read_json(directory / "record.json")
        process = read_json(directory / "process.json")
        assert process["process_started"] is False and process["group_quiescent"] is True
        assert not (directory / "process-start.json").exists()
        assert read_json(directory / "qualification-capture.json")["status"] == "rejected_before_process_start"
        assert receipt["termination"] == "error"
        assert all((directory / name).read_bytes() == b"" for name in rejection.STREAMS)
        ledger.reload()
        entry = ledger.record["calls"][-1]
        call = read_json(fixture.output / "calls/0002/call.json")
        with runtime.runtime(plan, fixture.output):
            assert runtime.capture.validate_record(plan["snapshot"], call["runtime_record"]) == receipt
        if category == "USER_STOPPED":
            assert cancellation.evidence(plan, fixture.output, entry, 2, call)["process_started"] is False
        args = read_json(directory / "command.json")["argv"]
        before = retained(directory)
        launch = provider_runtime.launch_boundary(lambda *a: pytest.fail("replayed rejection spawned"),
            plan=plan, output=fixture.output, owner=owner)
        for _attempt in range(2):
            with pytest.raises(RecoveryStop) as repeated:
                launch(args, request["prompt"], directory, plan["recovery"]["deadline_seconds"])
            assert repeated.value.category == category
            assert retained(directory) == before
        write_json(directory / "process.json", {**process, "process_started": True})
        changed = retained(directory)
        with pytest.raises(RecoveryStop, match="Conflicting"):
            launch(args, request["prompt"], directory, plan["recovery"]["deadline_seconds"])
        assert retained(directory) == changed


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("boundary", ["prelaunch-intent.json", "qualification-capture.json",
    "prelaunch-rejection.json", "local-cancellation.json", "process.json"])
@pytest.mark.parametrize("after", [False, True])
def test_rejection_publication_cut_never_resends(prepared, tmp_path, monkeypatch, boundary, after):
    prepared, journal, lineages = setup_document(prepared, tmp_path)
    codex, _account, plan, _output, request = prepared
    native_capture, native_persist = provider_capture.launch, rejection.persist
    directories, interrupted = [], []
    with complete_campaign(prepared, tmp_path, monkeypatch, recovery_journal=journal_binding.descriptor(journal)) as fixture, (
            runtime.settlement_scope()), owned_stage(fixture.output, plan, authority=fixture.authority) as (owner, ledger, _):
        def capture(arguments, prompt, directory, **kwargs):
            final = kwargs["before_spawn"]

            def veto():
                final()
                directories.append(Path(directory))
                issue_stop(fixture.configuration, 1)
                return final()

            return native_capture(arguments, prompt, directory, **{**kwargs, "before_spawn": veto})

        def persist(path, value):
            if Path(path).name == boundary and not interrupted:
                interrupted.append(True)
                if after:
                    native_persist(path, value)
                raise OSError("rejection publication cut")
            return native_persist(path, value)

        with monkeypatch.context() as patch:
            patch.setattr(provider_capture, "launch", capture)
            patch.setattr(rejection, "persist", persist)
            with runtime.runtime(plan, fixture.output, live=True, owner=owner), pytest.raises((RuntimeError, OSError)), (
                    dispatcher.accounted_model(fixture.output, plan, ledger, journal=journal, owner=owner, lineages=lineages)):
                ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot).invoke(**request)
        assert interrupted == [True] and len(directories) == 1
        directory = directories[0]
        assert not (directory / "process-start.json").exists()
        args = read_json(directory / "command.json")["argv"]
        launch = provider_runtime.launch_boundary(lambda *a: pytest.fail("interrupted rejection resent"),
            plan=plan, output=fixture.output, owner=owner)
        charged = ledger.path.read_bytes(), fixture.account.read_bytes()
        ambiguous = boundary == "prelaunch-intent.json" and not after
        for _attempt in range(2):
            with pytest.raises(RecoveryStop) as caught:
                launch(args, request["prompt"], directory, plan["recovery"]["deadline_seconds"])
            assert caught.value.category == ("BLOCKED_ACCOUNTING" if ambiguous else "USER_STOPPED")
            assert (ledger.path.read_bytes(), fixture.account.read_bytes()) == charged
        if not ambiguous:
            assert read_json(directory / "process.json")["process_started"] is False
            assert read_json(directory / "qualification-capture.json")["status"] == "rejected_before_process_start"
            assert (directory / "local-cancellation.json").is_file()
        before = retained(directory)
        with pytest.raises(RecoveryStop):
            launch(args, request["prompt"], directory, plan["recovery"]["deadline_seconds"])
        assert retained(directory) == before


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_validation_failure_uses_only_private_rejection_writer(prepared, tmp_path, monkeypatch):
    from tools.inventory_recovery_v3 import runtime_binding

    prepared, journal, lineages = setup_document(prepared, tmp_path)
    codex, _account, plan, _output, request = prepared
    native = runtime.bridge.NATIVE_RUNTIME.__wrapped__.__globals__
    writer, qualified = native["write_json"], native["qualified"]
    capture, launch = qualified.capture, qualified.capture.launch
    with complete_campaign(prepared, tmp_path, monkeypatch, recovery_journal=journal_binding.descriptor(journal)) as fixture, (
            runtime.settlement_scope()), owned_stage(fixture.output, plan, authority=fixture.authority) as (owner, ledger, _):
        def veto(_binding):
            raise RecoveryStop("BLOCKED_OWNERSHIP", "native settings veto")

        native_bind = runtime_binding.bind

        def bind(*args, **kwargs):
            result = native_bind(*args, **kwargs)
            if not kwargs.get("rejected"):
                monkeypatch.setattr(qualified.settings, "verify", veto)
            return result

        monkeypatch.setattr(runtime_binding, "bind", bind)
        with runtime.runtime(plan, fixture.output, live=True, owner=owner), pytest.raises(RuntimeError) as caught, (
                dispatcher.accounted_model(fixture.output, plan, ledger, journal=journal, owner=owner, lineages=lineages)):
            ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot).invoke(**request)
        assert failure_record(caught.value, phase="test")["category"] == "BLOCKED_OWNERSHIP"
        call = read_json(fixture.output / "calls/0002/call.json")
        directory = codex.snapshot / Path(call["runtime_record"]["path"]).parent
        assert read_json(directory / "prelaunch-intent.json")["failure"]["detail"] == "native settings veto"
        assert read_json(directory / "process.json")["process_started"] is False
        assert native["write_json"] is writer and native["qualified"] is qualified
        assert qualified.capture is capture and capture.launch is launch


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_postfork_failure_keeps_spending_and_never_publishes_rejection(prepared, tmp_path, monkeypatch):
    prepared, journal, lineages = setup_document(prepared, tmp_path)
    codex, _account, plan, _output, request = prepared
    native_launch = provider_capture.launch
    calls = []
    with complete_campaign(prepared, tmp_path, monkeypatch, recovery_journal=journal_binding.descriptor(journal)) as fixture, (
            runtime.settlement_scope()), owned_stage(fixture.output, plan, authority=fixture.authority) as (owner, ledger, _):
        def capture(arguments, prompt, directory, **kwargs):
            calls.append(Path(directory))
            native = provider_capture.os.read
            injected = []

            def read(fd, length):
                if length == 50000 and not injected:
                    injected.append(True)
                    raise OSError("post-fork constructor cut")
                return native(fd, length)

            with monkeypatch.context() as patch:
                patch.setattr(provider_capture.os, "read", read)
                return native_launch(arguments, prompt, directory, **kwargs)

        monkeypatch.setattr(provider_capture, "launch", capture)
        with runtime.runtime(plan, fixture.output, live=True, owner=owner), pytest.raises((RuntimeError, OSError)), (
                dispatcher.accounted_model(fixture.output, plan, ledger, journal=journal, owner=owner, lineages=lineages)):
            ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot).invoke(**request)
        assert len(calls) == 1
        directory = calls[0]
        process = read_json(directory / "process.json")
        assert process["process_started"] is True and process["group_quiescent"] is True
        assert not (directory / "prelaunch-intent.json").exists()
        assert not (directory / "local-cancellation.json").exists()
        assert read_json(directory / "qualification-capture.json")["status"] == "verified"
        ledger.reload()
        assert len(ledger.record["calls"]) == 1
        assert ledger.record["calls"][0]["status"] in {"allocated_unknown", "incomplete"}
        charged = fixture.account.read_bytes(), ledger.path.read_bytes()
        before = retained(directory)
        args = read_json(directory / "command.json")["argv"]
        launch = provider_runtime.launch_boundary(lambda *a: pytest.fail("ambiguous invocation resent"),
            plan=plan, output=fixture.output, owner=owner)
        for _attempt in range(2):
            with pytest.raises(RecoveryStop):
                launch(args, request["prompt"], directory, plan["recovery"]["deadline_seconds"])
            assert retained(directory) == before
            assert (fixture.account.read_bytes(), ledger.path.read_bytes()) == charged
