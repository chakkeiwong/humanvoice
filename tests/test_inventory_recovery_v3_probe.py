"""Replay public probes independently across interruption and rehashed evidence."""

import multiprocessing
import os
from copy import deepcopy

import pytest
from test_inventory_recovery_v3_stage import (
    baseline,
    codex,
    configure_cold_history,
    exhausted,
    native_case,
)

from humanvoice.artifacts import digest, read_json, write_json
from tools.inventory_recovery_v3 import probe, semantics, stage

__all__ = ["baseline", "codex", "exhausted", "native_case"]


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("exhausted", ["cold"], indirect=True)
@pytest.mark.parametrize("cut", ["observations.json", "verification.json", "probe-intent.json"])
def test_public_probe_reentry_is_independent_of_outer_observations(exhausted, tmp_path, monkeypatch, cut):
    configure_cold_history(exhausted, tmp_path, monkeypatch, completed=1)
    current = stage.Stage(tmp_path / "successor", exhausted.transition)
    before = exhausted.account.read_bytes(), exhausted.grant.read_bytes()
    native = stage.immutable
    with semantics.transition_runtime(exhausted.transition) as outer:
        outer["observations"].append({"unrelated": "before"})

        def interrupted(path, value):
            native(path, value)
            if path.name == cut:
                raise OSError("publication interruption")

        with monkeypatch.context() as stopped:
            stopped.setattr(stage, "immutable", interrupted)
            with pytest.raises(OSError, match="publication interruption"):
                current.run("prepare")
        outer["observations"].append({"unrelated": "between"})
        plan = current.run("prepare")
        report = current.run("probe")
        rows = probe.observations(current, report)
        assert rows and all("unrelated" not in row for row in rows)
        assert report["inherited_calls"] == 1
    reopened = stage.Stage(current.output, exhausted.transition)
    assert reopened.run("prepare") == plan
    assert reopened.run("probe") == report
    assert before == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("exhausted", ["cold"], indirect=True)
@pytest.mark.parametrize("change", ["remove", "reorder"])
def test_rehashed_transcript_cannot_pass_cold_preparation(exhausted, tmp_path, monkeypatch, change):
    configure_cold_history(exhausted, tmp_path, monkeypatch, completed=1)
    current = stage.Stage(tmp_path / "successor", exhausted.transition)
    report = current.run("probe")
    folder = probe.folder_for(current)
    record = read_json(folder / "observations.json")
    assert len(record["observations"]) >= 2
    if change == "remove":
        del record["observations"][0]
    else:
        record["observations"].insert(0, deepcopy(record["observations"][-1]))
    report["observations_hash"] = digest(record)
    write_json(folder / "observations.json", record)
    write_json(folder / "verification.json", report)
    before = exhausted.account.read_bytes(), exhausted.grant.read_bytes()
    reopened = stage.Stage(current.output, exhausted.transition)
    with pytest.raises(RuntimeError, match="Frozen successor evidence changed"):
        reopened.run("prepare")
    assert not (current.output / "plan.json").exists()
    assert before == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("cut", ["exception", "process_death"])
def test_cold_probe_interrupt_preserves_original_evidence(exhausted, tmp_path, monkeypatch, cut):
    from tools.inventory_recovery_v2 import replay

    current = stage.Stage(tmp_path / "successor", exhausted.transition)
    report = current.probe()
    folder = probe.folder_for(current)
    before = {path: path.read_bytes() for path in (exhausted.account, exhausted.grant,
              *(folder / name for name in ("verification.json", "observations.json", "probe-intent.json", "replay-log.json")))}

    def worker():
        native = replay.write_json

        def persist(path, value):
            native(path, value)
            if path.name == "replay-log.json" and "revalidation" in path.parts:
                if cut == "process_death":
                    os._exit(73)
                raise OSError("partial cold replay")

        with monkeypatch.context() as stopped:
            stopped.setattr(replay, "write_json", persist)
            stage.Stage(current.output, exhausted.transition).probe()

    if cut == "exception":
        with pytest.raises(semantics.context.InvocationStopped, match="partial cold replay"):
            worker()
    else:
        child = multiprocessing.get_context("fork").Process(target=worker)
        child.start()
        child.join(60)
        if child.is_alive():
            child.kill()
            child.join(5)
        assert child.exitcode == 73
    assert all(path.read_bytes() == value for path, value in before.items())
    assert stage.Stage(current.output, exhausted.transition).probe() == report
    assert all(path.read_bytes() == value for path, value in before.items())
