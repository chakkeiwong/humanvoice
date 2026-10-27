"""Exercise independent installed authority derivation without live calls."""

from types import SimpleNamespace

import pytest
from test_inventory_history_live import history

from humanvoice.artifacts import digest, read_json, write_json
from tools import inventory_history_handover as native
from tools import inventory_history_live as live
from tools import inventory_history_live_admission as admission
from tools import inventory_history_services as services
from tools import review_inventory_recovery_v3 as review
from tools.inventory_recovery_v2 import campaign, program
from tools.inventory_recovery_v3 import installed_authority


@pytest.fixture
def installed(tmp_path, monkeypatch):
    old, expected, current, contract = history(tmp_path)
    adopted = native.proposal(old, expected, current, contract)
    configuration = {**expected, "maximum_worker_restarts": adopted["maximum_worker_restarts"],
                     "adoption_identity": adopted["identity"], "repair_contract": contract}
    monkeypatch.setattr(live, "SUPERVISION", current)
    monkeypatch.setattr(live, "ADMISSION", tmp_path / "admission.json")
    monkeypatch.setattr(live, "ADOPTION", tmp_path / "adoption.json")
    monkeypatch.setattr(live, "contract", lambda: contract)
    monkeypatch.setattr(live, "config", lambda: configuration)
    monkeypatch.setattr(live, "adoption", lambda: native.validate(
        read_json(live.ADOPTION), old, expected, current, contract))
    monkeypatch.setattr(admission.repair, "ROOT", tmp_path)
    monkeypatch.setattr(program, "BASE", tmp_path)
    monkeypatch.setattr(program, "GRANT", tmp_path / "grant.json")
    monkeypatch.setattr(program, "predecessor", SimpleNamespace(
        account=SimpleNamespace(ACCOUNT=tmp_path / "account.json")))
    monkeypatch.setattr(campaign, "ROOT", tmp_path / "campaign")
    monkeypatch.setattr(campaign, "contract", lambda: {"campaign": True})
    monkeypatch.setattr(campaign, "cursor", lambda: read_json(campaign.ROOT / "cursor.json"))
    monkeypatch.setattr(review, "sources", lambda: {"candidate.py": digest((tmp_path / "candidate.py").read_bytes())})
    monkeypatch.setattr(services, "TARGET", tmp_path / "units")
    units = {"monitor.service": b"isolated monitor", "report.service": b"isolated report"}
    monkeypatch.setattr(services, "units", lambda: units)
    monkeypatch.setattr(services, "environment", lambda: "admitted-environment")
    services.TARGET.mkdir()
    for name, content in units.items():
        (services.TARGET / name).write_bytes(content)
    (tmp_path / "candidate.py").write_text("source")
    write_json(live.ADOPTION, adopted)
    write_json(current / "config.json", configuration)
    write_json(campaign.ROOT / "cursor.json", {"generation": 2,
               "output": str(campaign.ROOT / "generation-02"), "contract": campaign.contract()})
    for name in ("account.json", "grant.json", "grant.stages.json"):
        write_json(tmp_path / name, {"fixture": name})
    for name in ("first", "second"):
        write_json(campaign.ROOT / "qualification" / name / "plan.json", {"name": name})
    preflight = {"status": "pass", "contract": contract,
        "config_identity": digest(configuration), "adoption": adopted,
        "environment": "admitted-environment", "live_execution_enabled": False,
        "model_calls": 0, "account_writes": 0, "grant_writes": 0,
        "services": {"units": {name: digest(content) for name, content in units.items()}}}
    write_json(tmp_path / "preflight.json", preflight)
    authorization = {"action": "install-and-start-history-repair", "authorized_by": "user",
        "contract_sha256": digest(contract), "adoption_identity": adopted["identity"],
        "preflight_sha256": digest((tmp_path / "preflight.json").read_bytes()),
        "approval_policy": "on-request", "approvals_reviewer": "user"}
    write_json(tmp_path / "authorization.json", authorization)
    record = {"status": "ADMITTED", "contract": contract, "config_identity": digest(configuration),
        "approval_policy": "on-request", "approvals_reviewer": "user",
        **{name: {"path": name + ".json", "sha256": digest((tmp_path / (name + ".json")).read_bytes())}
           for name in ("preflight", "authorization")}}
    write_json(live.ADMISSION, record)
    return tmp_path


def test_derives_complete_installed_chain_stops_and_stage_locks(installed):
    before = {str(path): (path.read_bytes(), path.stat().st_mtime_ns)
              for path in installed.rglob("*") if path.is_file()}
    result = installed_authority.capture()
    assert result["records"] == [read_json(live.ADOPTION)]
    assert result["stop_bindings"] == [{"root": str(campaign.ROOT), "contract": campaign.contract()}]
    assert result["shared_locks"] == sorted(str(path) for path in live.shared_locks())
    assert len(result["shared_locks"]) == 7
    assert result["live_execution_enabled"] is False
    assert installed_authority.capture() == result
    after = {str(path): (path.read_bytes(), path.stat().st_mtime_ns)
             for path in installed.rglob("*") if path.is_file()}
    assert before == after


@pytest.mark.parametrize("defect", ["admission", "approval", "config", "adoption",
                                  "authorization", "preflight", "service", "missing", "symlink"])
def test_installed_evidence_mutations_are_rejected(installed, defect):
    if defect in {"admission", "approval"}:
        path = live.ADMISSION
        value = read_json(path)
        value["status" if defect == "admission" else "approvals_reviewer"] = "foreign"
        write_json(path, value)
    elif defect in {"authorization", "preflight"}:
        write_json(installed / (defect + ".json"), {"foreign": True})
    elif defect in {"config", "adoption"}:
        write_json(live.SUPERVISION / "config.json" if defect == "config" else live.ADOPTION, {})
    elif defect == "service":
        (services.TARGET / "monitor.service").write_bytes(b"changed")
    elif defect == "missing":
        (installed / "grant.stages.json").unlink()
    else:
        path = live.ADMISSION
        path.rename(path.with_suffix(".original"))
        path.symlink_to(path.with_suffix(".original"))
    with pytest.raises((ValueError, KeyError, OSError)):
        installed_authority.capture()


@pytest.mark.parametrize("value", [None, [], True, 17])
def test_present_nonobject_authority_is_not_missing(installed, value):
    write_json(program.GRANT, value)
    with pytest.raises(TypeError, match="object"):
        installed_authority.capture()


@pytest.mark.parametrize("defect", ["source", "account", "qualification", "cursor"])
def test_observation_rejects_late_source_authority_or_membership_change(installed, monkeypatch, defect):
    original = live.shared_locks
    calls = []

    def mutate():
        result = original()
        calls.append(True)
        if len(calls) == 1:
            if defect == "source":
                (installed / "candidate.py").write_text("changed")
            elif defect == "account":
                write_json(installed / "account.json", {"changed": True})
            elif defect == "qualification":
                write_json(campaign.ROOT / "qualification/third/plan.json", {})
            else:
                value = campaign.cursor()
                write_json(campaign.ROOT / "cursor.json", {**value, "generation": 3})
        return result

    monkeypatch.setattr(live, "shared_locks", mutate)
    with pytest.raises(ValueError, match="changed during"):
        installed_authority.capture()
    assert calls


@pytest.mark.parametrize("value", ["relative", "/tmp/a/../b", "/tmp//b", "/tmp/b/", "//tmp/b"])
def test_noncanonical_path_alias_is_rejected(value):
    with pytest.raises(ValueError, match="canonical"):
        installed_authority.canonical_path(value)


def test_runtime_environment_rechecks_human_approval_policy(installed, monkeypatch):
    binding = installed_authority.capture()
    installed_authority.require_environment(binding)
    monkeypatch.setattr(services, "environment", lambda: "different")
    with pytest.raises(ValueError, match="human approvals"):
        installed_authority.require_environment(binding)
