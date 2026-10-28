"""Runtime evidence survives mutable growth but rejects immutable changes."""

import fcntl
from copy import deepcopy
from pathlib import Path
from types import FunctionType

import pytest
from test_inventory_recovery_v3_installed_authority import installed

from humanvoice.artifacts import digest, read_json, write_json
from tools import durable_program_supervisor as durable
from tools import inventory_history_handover as native
from tools import inventory_history_live as live
from tools import review_inventory_recovery_v3 as review
from tools.inventory_recovery_v2 import campaign
from tools.inventory_recovery_v3 import handover, installed_authority, runtime_closure

__all__ = ["installed"]
NATIVE_SOURCES = review.sources


@pytest.fixture
def closure_case(installed, monkeypatch):
    monkeypatch.setattr(review, "ROOT", installed)
    prior = live.config()
    write_json(live.SUPERVISION / "state.json", {"config_identity": durable.fingerprint(prior),
        "run_id": "current-supervisor", "sequence": 0, "worker_restarts": 0})
    write_json(campaign.ROOT / "generation-02/plan.json", {"sealed": True})
    current = installed_authority.capture()
    adoption = handover.proposal(current["records"], current["root"],
        current["configuration"], installed / "prospective", {"prospective": True})
    return adoption, runtime_closure.capture(adoption)


def forbidden(*args, **kwargs):
    raise AssertionError("Runtime called transfer-time derivation or a native lock")


def test_runtime_reads_retained_closure_without_capture_or_locks(closure_case, monkeypatch):
    adoption, value = closure_case
    for module, name in ((handover, "proposal"), (handover, "validate"),
                         (native, "snapshot"), (installed_authority, "capture"),
                         (runtime_closure, "capture"), (live, "shared_locks"),
                         (fcntl, "flock")):
        monkeypatch.setattr(module, name, forbidden)
    assert runtime_closure.verify(value, adoption=adoption) is True
    # Only native floors decide whether a mutable suffix is lawful. The leaf
    # must not compare these bytes to the sealed transfer capture.
    for name in ("account", "grant"):
        path = Path(adoption["installed"][name])
        if name == "grant":
            path = path.with_suffix(".stages.json")
        write_json(path, {"changed_consumption": True})
    assert runtime_closure.verify(value, adoption=adoption) is True


@pytest.mark.parametrize("target", ["old-config", "current-state", "request", "new-receipt",
    "missing-request", "extra-job", "missing-job", "extra-root-file", "output-log",
    "qualification-bytes", "qualification-added", "qualification-removed",
    "qualification-empty-child", "qualification-late-plan", "cursor", "grant",
    "source", "unit", "sealed-plan", "job-symlink", "plan-symlink", "lock-symlink"])
def test_every_retained_membership_and_byte_mutation_fails(closure_case, target):
    adoption, value = closure_case
    installed = adoption["installed"]
    old = Path(adoption["records"][0]["predecessor"]["root"])
    current = Path(installed["root"])
    base = Path(installed["account"]).parent
    job = old / "jobs/job-0001"
    qualification = Path(value["qualification"]["root"])
    paths = {"old-config": old / "config.json", "current-state": current / "state.json",
        "request": job / "request.json", "new-receipt": job / "heartbeat.json",
        "extra-root-file": old / "unexpected", "output-log": job / "output.log",
        "qualification-bytes": qualification / "first/plan.json",
        "qualification-added": qualification / "third/plan.json",
        "cursor": campaign.ROOT / "cursor.json", "grant": Path(installed["grant"]),
        "source": base / "candidate.py", "unit": base / "units/monitor.service",
        "sealed-plan": campaign.ROOT / "generation-02/plan.json"}
    if target in paths:
        write_json(paths[target], {"mutated": True})
    elif target == "missing-request":
        (job / "request.json").unlink()
    elif target == "extra-job":
        (old / "jobs/job-0002").mkdir()
    elif target == "missing-job":
        job.rename(old / "displaced")
    elif target == "qualification-removed":
        (qualification / "first/plan.json").unlink()
    elif target == "qualification-empty-child":
        (qualification / "third").mkdir()
    elif target == "qualification-late-plan":
        (qualification / "first/plan.json").rename(qualification / "first/plan.old")
    elif target == "job-symlink":
        job.rename(old / "displaced")
        job.symlink_to(old / "displaced", target_is_directory=True)
    elif target == "plan-symlink":
        path = qualification / "first/plan.json"
        path.rename(path.with_suffix(".old"))
        path.symlink_to(path.with_suffix(".old"))
    else:
        (old / "monitor.lock").symlink_to(base / "account.json")
    with pytest.raises((ValueError, OSError)):
        runtime_closure.verify(value, adoption=adoption)


def test_canonical_lock_creation_is_not_new_receipt_membership(closure_case):
    adoption, value = closure_case
    for name in value["lock_slots"]:
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    assert runtime_closure.verify(value, adoption=adoption)
    (Path(adoption["records"][0]["predecessor"]["root"]) / "foreign.lock").touch()
    with pytest.raises(ValueError, match="membership"):
        runtime_closure.verify(value, adoption=adoption)


def test_transfer_rejects_late_receipt_membership(closure_case, monkeypatch):
    adoption, _value = closure_case
    original = handover.validate
    calls = []

    def mutation(record):
        result = original(record)
        calls.append(True)
        if len(calls) == 2:
            root = Path(record["records"][0]["predecessor"]["root"])
            write_json(root / "late.json", {})
        return result

    monkeypatch.setattr(handover, "validate", mutation)
    with pytest.raises(ValueError, match="membership"):
        runtime_closure.capture(adoption)


def test_runtime_record_rehash_cannot_change_adoption(closure_case):
    adoption, value = closure_case
    changed = deepcopy(value)
    changed["adoption_identity"] = "foreign"
    with pytest.raises(ValueError, match="binding"):
        runtime_closure.verify(runtime_closure.identified(changed), adoption=adoption)
    assert read_json(Path(adoption["installed"]["root"]) / "config.json")
    assert digest(value) == digest(runtime_closure.identified(value))


@pytest.mark.parametrize("change", ["add", "rename", "remove", "symlink", "generated"])
def test_native_source_contract_membership_and_generated_exclusion(installed, monkeypatch, change):
    for name in ("tools/inventory_recovery_v3/member.py", "tools/prepare_inventory_recovery_v3.py",
                 "tools/review_inventory_recovery_v3.py"):
        path = installed / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# native source fixture\n")
    source_reader = FunctionType(NATIVE_SOURCES.__code__,
        {**NATIVE_SOURCES.__globals__, "ROOT": installed,
         "__file__": str(installed / "tools/review_inventory_recovery_v3.py")})
    monkeypatch.setattr(review, "sources", source_reader)
    adoption, closure = closure_case.__wrapped__(installed, monkeypatch)
    assert runtime_closure.verify(closure, adoption=adoption)
    path = installed / "tools/inventory_recovery_v3/member.py"
    if change == "add":
        path.with_name("new_member.py").write_text("# new\n")
    elif change == "rename":
        path.rename(path.with_name("renamed.py"))
    elif change == "remove":
        path.unlink()
    elif change == "symlink":
        path.with_name("alias.py").symlink_to(path)
    else:
        write_json(path.with_name("generated.json"), {"preparation": True})
        write_json(installed / "preparation/configuration.json", {"generated": True})
        assert source_reader() == adoption["installed"]["sources"]
        assert runtime_closure.verify(closure, adoption=adoption)
        return
    with pytest.raises((ValueError, OSError)):
        runtime_closure.verify(closure, adoption=adoption)
