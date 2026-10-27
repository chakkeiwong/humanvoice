"""Conserve restart, lock and stop authority across a second adoption."""

import fcntl
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from test_inventory_history_live import history

from humanvoice.artifacts import digest, read_json, write_json
from tools import durable_program_supervisor as durable
from tools import inventory_history_handover as native
from tools.inventory_recovery_v2 import control
from tools.inventory_recovery_v3 import handover


def second_adoption(tmp_path, monkeypatch, usage=2, pending=True):
    old, expected, current, contract = history(tmp_path, usage, pending)
    first = native.proposal(old, expected, current, contract)
    configuration = {**expected, "maximum_worker_restarts": first["maximum_worker_restarts"],
                     "adoption_identity": first["identity"]}
    write_json(current / "config.json", configuration)
    write_json(current / "state.json", {"config_identity": durable.fingerprint(configuration),
               "run_id": "new-owner", "sequence": 0, "worker_restarts": 0})
    stop_bindings = [{"root": str(tmp_path / "campaign"), "contract": {"original": True}}]
    installed = {"records": [first], "root": str(current), "configuration": configuration,
                 "stop_bindings": stop_bindings, "shared_locks": [str(tmp_path / "execution.lock")]}
    write_json(tmp_path / "installed.json", installed)
    monkeypatch.setattr(handover.installed_authority, "capture", lambda: read_json(tmp_path / "installed.json"))
    monkeypatch.setattr(handover.installed_authority, "require_environment", lambda binding: None)
    return handover.proposal([first], current, configuration, tmp_path / "third",
                             {"new": True}, stop_bindings=stop_bindings)


def test_second_handover_counts_pending_intent_and_both_transfers(tmp_path, monkeypatch):
    record = second_adoption(tmp_path, monkeypatch)
    assert record["cumulative_restarts"] == 4
    assert record["remaining_restarts"] == 12
    assert handover.validate(record) == record
    with handover.lease(record) as leases:
        assert len(leases) == 2
        for held in leases:
            held.check()
    assert handover.validate(record) == record


def test_old_campaign_stop_is_still_authoritative(tmp_path, monkeypatch):
    record = second_adoption(tmp_path, monkeypatch)
    binding = record["stop_bindings"][0]
    control.stop(binding["root"])
    with pytest.raises(RuntimeError, match="resume authorization"), handover.lease(record):
        pytest.fail("Old user stop was ignored")


@pytest.mark.parametrize("name", ["user-stop.json", "resume-authorization.json"])
def test_dangling_stop_or_resume_symlink_cannot_bypass_veto(tmp_path, monkeypatch, name):
    record = second_adoption(tmp_path, monkeypatch)
    root = Path(record["stop_bindings"][0]["root"])
    root.mkdir()
    (root / name).symlink_to(root / "missing")
    with pytest.raises(ValueError, match="symlinks"), handover.lease(record):
        pytest.fail("Dangling stop authority was treated as absent")


def test_chained_adoption_rejects_removed_predecessor_and_changed_destination(tmp_path, monkeypatch):
    record = second_adoption(tmp_path, monkeypatch)
    changed = deepcopy(record)
    changed["records"] = changed["records"][1:]
    changed["identity"] = digest({key: value for key, value in changed.items() if key != "identity"})
    with pytest.raises(ValueError):
        handover.validate(changed)
    changed = deepcopy(record)
    changed["replacement"] = str(tmp_path / "competing")
    changed["identity"] = digest({key: value for key, value in changed.items() if key != "identity"})
    with pytest.raises(ValueError, match="changed exclusions"):
        handover.validate(changed)


def test_missing_prior_config_stops_chain_replay(tmp_path, monkeypatch):
    record = second_adoption(tmp_path, monkeypatch)
    original = tmp_path / "old/config.json"
    configuration = read_json(original)
    write_json(original, {**configuration, "maximum_worker_restarts": 15})
    with pytest.raises(ValueError):
        handover.validate(record)


@pytest.mark.parametrize("defect", ["omit", "replace", "contract", "duplicate", "installed"])
def test_rehashed_stop_omission_never_redefines_installed_authority(tmp_path, monkeypatch, defect):
    record = second_adoption(tmp_path, monkeypatch)
    if defect == "omit":
        record["stop_bindings"] = []
    elif defect == "replace":
        record["stop_bindings"][0]["root"] = str(tmp_path / "unrelated")
    elif defect == "contract":
        record["stop_bindings"][0]["contract"] = {"changed": True}
    elif defect == "duplicate":
        record["stop_bindings"] *= 2
    else:
        record["installed"]["stop_bindings"] = []
    record["identity"] = digest({key: value for key, value in record.items() if key != "identity"})
    with pytest.raises(ValueError):
        handover.validate(record)


def test_installed_predecessor_and_lock_set_are_not_optional(tmp_path, monkeypatch):
    record = second_adoption(tmp_path, monkeypatch)
    first = record["records"][0]
    with pytest.raises(ValueError, match="complete installed"):
        handover.proposal([first], first["predecessor"]["root"],
            read_json(tmp_path / "old/config.json"), tmp_path / "fourth", {})
    with (tmp_path / "execution.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError), handover.lease(record):
            pytest.fail("Caller omitted a busy installed stage lock")


def test_double_slash_alias_cannot_adopt_itself(tmp_path, monkeypatch):
    record = second_adoption(tmp_path, monkeypatch)
    installed = record["installed"]
    with pytest.raises(ValueError, match="canonical"):
        handover.proposal(installed["records"], installed["root"], installed["configuration"],
                          "/" + installed["root"], {"replacement": True})


@pytest.mark.parametrize("defect", ["stop", "installed", "environment", "lock"])
def test_chain_rechecks_late_vetoes(tmp_path, monkeypatch, defect):
    record = second_adoption(tmp_path, monkeypatch)
    with handover.lease(record) as held:
        assert held.check()
        if defect == "stop":
            control.stop(record["stop_bindings"][0]["root"])
        elif defect == "installed":
            installed = read_json(tmp_path / "installed.json")
            installed["shared_locks"].append(str(tmp_path / "new.lock"))
            write_json(tmp_path / "installed.json", installed)
        elif defect == "environment":
            def reject(binding):
                raise ValueError("Changed environment")
            monkeypatch.setattr(handover.installed_authority, "require_environment", reject)
        else:
            path = tmp_path / "old/monitor.lock"
            path.rename(path.with_suffix(".old"))
            path.touch()
        with pytest.raises((RuntimeError, ValueError)):
            held.check()


@pytest.mark.parametrize("defect", ["none", "missing", "duplicate", "foreign", "unheld", "identity"])
def test_cold_child_requires_exact_continuously_held_descriptors(tmp_path, monkeypatch, defect):
    record = second_adoption(tmp_path, monkeypatch)
    write_json(tmp_path / "handover.json", record)
    root = Path(__file__).resolve().parents[1]
    script = ("import sys, json\nfrom pathlib import Path\n"
              f"sys.path[:0] = {[str(root), str(root / 'src')]!r}\n"
              "from humanvoice.artifacts import read_json\n"
              "from tools.inventory_recovery_v3 import handover\n"
              f"root = Path({str(tmp_path)!r})\n"
              "handover.installed_authority.capture = lambda: read_json(root / 'installed.json')\n"
              "handover.installed_authority.require_environment = lambda binding: None\n"
              "with handover.inherited(read_json(root / 'handover.json')) as held:\n"
              "    assert held.check()\n")
    with handover.lease(record) as held, (tmp_path / "foreign.lock").open("a") as foreign:
        options = held.capsule()
        capsule = json.loads(options["environment"][handover.DESCRIPTORS])
        descriptors = capsule["descriptors"]
        inherited = list(options["pass_fds"])
        if defect == "missing":
            descriptors.pop()
        elif defect == "duplicate":
            descriptors[-1] = descriptors[0]
        elif defect == "foreign":
            descriptors[-1] = foreign.fileno()
            inherited.append(foreign.fileno())
        elif defect == "unheld":
            fcntl.flock(descriptors[-1], fcntl.LOCK_UN)
        elif defect == "identity":
            capsule["identity"] = "foreign"
        result = subprocess.run([sys.executable, "-I", "-c", script],
            env={**os.environ, handover.DESCRIPTORS: json.dumps(capsule)},
            pass_fds=tuple(inherited), capture_output=True, text=True, timeout=30, check=False)
        assert (result.returncode == 0) == (defect == "none"), result.stderr
        if defect != "unheld":
            assert held.check()
            with (tmp_path / "old/monitor.lock").open("r") as independent, pytest.raises(BlockingIOError):
                fcntl.flock(independent, fcntl.LOCK_EX | fcntl.LOCK_NB)
