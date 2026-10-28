"""Public candidate inspection derives evidence without live authority."""

import json
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_inventory_history_live import history
from test_inventory_recovery_v3_bootstrap import bootstrap
from test_inventory_recovery_v3_campaign_binding import candidate
from test_inventory_recovery_v3_campaign_history import snapshot, transition

from humanvoice.artifacts import digest, read_json, write_json
from tools import durable_program_supervisor as durable
from tools import inventory_history_handover as native
from tools import review_inventory_recovery_v3 as review
from tools.inventory_recovery_v2 import campaign as historical_campaign
from tools.inventory_recovery_v3 import (
    binding_publication,
    campaign_binding,
    campaign_history,
    configuration,
    public,
    runtime,
)
from tools.inventory_recovery_v3.failures import RecoveryStop

__all__ = ["bootstrap", "candidate"]
pytestmark = pytest.mark.parametrize("bootstrap", ["public-configuration"], indirect=True)


def installed_for(root, account, grant, monkeypatch, usage=0, pending=False):
    from tools import inventory_history_live as live

    old, expected, current, contract = history(root.parent, usage=usage, pending=pending)
    adopted = native.proposal(old, expected, current, contract)
    prior = {**expected, "maximum_worker_restarts": adopted["maximum_worker_restarts"],
             "adoption_identity": adopted["identity"]}
    write_json(current / "config.json", prior)
    write_json(current / "state.json", {"config_identity": durable.fingerprint(prior),
        "run_id": "current-supervisor", "sequence": 0, "worker_restarts": 0})
    historical_root = root.parent / "old-campaign"
    historical_output = historical_root / "generation-02"
    monkeypatch.setattr(historical_campaign, "ROOT", historical_root)
    cursor = {"generation": 2, "output": str(historical_output)}
    write_json(historical_root / "cursor.json", cursor)
    write_json(historical_output / "plan.json", {"historical": True})
    # The caller may have patched cursor() for a different native predecessor.
    # Bind the same fixture cursor used in the installed record before deriving locks.
    monkeypatch.setattr(historical_campaign, "cursor",
                        lambda: read_json(historical_root / "cursor.json"))
    shared = sorted(str(path) for path in live.shared_locks())
    evidence = {str(path): digest(path.read_bytes()) for path in (account, grant,
                grant.with_suffix(".stages.json"), historical_root / "cursor.json")}
    installed = campaign_history.identified({"version": "installed-history-authority-v1",
        "sources": review.sources(), "account": str(account), "grant": str(grant),
        "records": [adopted], "root": str(current), "configuration": prior,
        "stop_bindings": [{"root": str(historical_root), "contract": {"historical": True}}],
        "shared_locks": shared, "cursor": cursor, "evidence": evidence,
        "environment": "fixture", "live_execution_enabled": False})
    installed_path = root.parent / "installed.json"
    write_json(installed_path, installed)
    monkeypatch.setattr(configuration.installed_authority, "capture", lambda: read_json(installed_path))
    return installed_path


@pytest.fixture
def configured(candidate, monkeypatch, request):
    case = candidate
    plan = read_json(case.output / "plan.json")
    monkeypatch.setattr(runtime, "validate_plan", lambda value: value)
    write_json(case.grant.with_suffix(".stages.json"), {"stages": []})
    bound = campaign_binding.create(case.root, check=lambda: True)["binding"]
    usage, pending = getattr(request, "param", (0, False))
    monkeypatch.setattr(configuration.program, "BASE", case.root.parent / "program")
    installed_path = installed_for(case.root, case.account, case.grant, monkeypatch, usage, pending)
    monkeypatch.setattr(configuration.program, "GRANT", case.grant)
    monkeypatch.setattr(configuration.program, "predecessor", SimpleNamespace(
        account=SimpleNamespace(ACCOUNT=case.account)))
    transition = read_json(case.output / "transition.json")
    ownership = {"historical_sequences": 1, "root_counts": {"root": 1},
        "lineage_counts": {"lineage": 1}, "unfinished_lineage": "lineage",
        "unfinished_root": "root", "unfinished_scope": {"source_file": "fixture",
            "window": "window", "purpose": "concept_extraction"},
        "unfinished_root_sequences": 1, "unfinished_lineage_sequences": 1,
        "observations": 2, "new_reservations": 0, "import_idempotent": True}
    monkeypatch.setattr(configuration.ownership_preflight, "inspect",
                        lambda *arguments: deepcopy(ownership))
    write_json(case.root.parent / "ownership-preflight.json", ownership)
    authority_bytes = {str(path): path.read_text() for path in
                       (case.account, case.grant, case.grant.with_suffix(".stages.json"))}
    write_json(case.root.parent / "preparation-authority.json", authority_bytes)
    preparation = {"status": "OFFLINE_PREPARATION_PASS", "sources": review.sources(),
        "ownership": ownership, "authority": {path: digest(content.encode())
            for path, content in authority_bytes.items()},
        "source_unchanged": True, "authority_unchanged": True, "live_execution_enabled": False,
        "model_calls": 0, "account_writes": 0, "grant_writes": 0,
        "successor": str(case.output), "plan_identity": plan["plan_identity"],
        "transition_identity": transition["identity"], "campaign_binding_identity": bound["identity"],
        "campaign_seed_identity": bound["seed_identity"], "recovery_journal": bound["recovery_journal"]}
    write_json(case.root.parent / "preparation.json", preparation)

    case.installed_path = installed_path
    return case


def test_installed_fixture_uses_its_cursor_and_program_lock(bootstrap, monkeypatch):
    case = bootstrap
    write_json(case.grant.with_suffix(".stages.json"), {"stages": []})
    base = case.root.parent / "program"
    monkeypatch.setattr(configuration.program, "BASE", base)
    monkeypatch.setattr(historical_campaign, "cursor",
                        lambda: {"generation": 2, "output": str(case.root.parent / "exhausted")})
    installed = read_json(installed_for(case.root, case.account, case.grant, monkeypatch))
    expected_output = case.root.parent / "old-campaign/generation-02"
    assert installed["cursor"] == historical_campaign.cursor()
    assert installed["cursor"]["output"] == str(expected_output)
    assert installed["shared_locks"] == sorted([
        str(base / "active-session-program.lock"),
        str(expected_output / "execution.lock"),
        str(expected_output / "executor.lock"),
    ])


def test_public_configuration_is_read_only_and_canonical(configured):
    case = configured
    before = snapshot(review.OUTPUT)
    report = configuration.status()
    value = report["configuration"]
    assert value == configuration.derive() == configuration.validate(value)
    assert set(value["execution_authority"]) == {"program_base", "supervisor_root", "account",
                                               "grant", "grant_identity"}
    assert value["campaign_root"] == str(case.root)
    assert value["recovery_journal"] == read_json(case.root / "seed.json")["journal"]
    assert value["stop_bindings"][:-1] == read_json(case.installed_path)["stop_bindings"]
    assert value["stop_bindings"][-1]["root"] == str(case.root)
    assert value["inherited_worker_restarts"] == 2
    assert value["maximum_worker_restarts"] == 14
    assert value["run"][:2] == [configuration.PYTHON, "-I"]
    assert Path(value["run"][2]).is_file()
    assert value["approval_policy"] == "on-request" and value["approvals_reviewer"] == "user"
    assert value["model_routing_policy"]["production_requires_qualification"] is True
    assert not value["dispatch_allowed"] and not value["live_execution_enabled"]
    assert report["model_calls"] == report["account_writes"] == report["grant_writes"] == 0
    assert snapshot(review.OUTPUT) == before


@pytest.mark.parametrize("field", ["run", "worker", "monitor", "repair", "admission", "cwd",
    "sources", "execution_authority", "recovery_journal", "stop_bindings", "policy", "initial_profile",
    "maximum_worker_restarts", "handover", "approval_policy", "approvals_reviewer",
    "verify", "diagnose", "model_routing_policy", "inherited_worker_restarts",
    "live_execution_enabled", "dispatch_allowed", "runtime_closure", "stop_floor"])
def test_rehashed_candidate_cannot_replace_derived_authority(configured, field):
    value = configuration.derive()
    value[field] = True if field in {"live_execution_enabled", "dispatch_allowed"} else "foreign"
    with pytest.raises(RecoveryStop, match="independently derived"):
        configuration.validate(campaign_history.identified(value))


@pytest.mark.parametrize("field", ["status", "sources", "source_unchanged", "authority_unchanged",
    "live_execution_enabled", "model_calls", "account_writes", "grant_writes", "successor",
    "plan_identity", "transition_identity", "campaign_binding_identity", "campaign_seed_identity",
    "recovery_journal", "ownership", "authority"])
def test_preparation_must_bind_exact_native_evidence(configured, field):
    path = configured.root.parent / "preparation.json"
    value = read_json(path)
    value[field] = "foreign"
    write_json(path, value)
    with pytest.raises(RecoveryStop):
        configuration.derive()


@pytest.mark.parametrize("field", ["model_calls", "account_writes", "grant_writes"])
def test_boolean_zero_does_not_prove_no_authority_changes(configured, field):
    path = configured.root.parent / "preparation.json"
    write_json(path, {**read_json(path), field: False})
    with pytest.raises(RecoveryStop):
        configuration.derive()


@pytest.mark.parametrize("defect", ["missing", "pending", "symlink", "source", "late"])
def test_incomplete_or_changed_inputs_cannot_create_admission(configured, monkeypatch, defect):
    case = configured
    path = case.root.parent / "preparation.json"
    if defect == "missing":
        path.unlink()
    elif defect == "pending":
        bound = read_json(case.root / campaign_binding.FILENAME)
        write_json(case.root / binding_publication.MARKER, binding_publication.marker(bound, "pending"))
    elif defect == "symlink":
        saved = path.with_suffix(".original")
        path.rename(saved)
        path.symlink_to(saved)
    elif defect == "source":
        monkeypatch.setattr(review, "sources", lambda: {"foreign": "identity"})
    else:
        native_capture = configuration.installed_authority.capture

        def changed():
            result = native_capture()
            path.write_bytes(path.read_bytes() + b" ")
            return result

        monkeypatch.setattr(configuration.installed_authority, "capture", changed)
    with pytest.raises((RecoveryStop, ValueError, FileNotFoundError)):
        configuration.derive()
    assert not (case.root.parent / "admission.json").exists()


@pytest.mark.parametrize("action", ["monitor", "worker", "campaign-execute", "campaign-verify",
                                    "campaign-repair"])
def test_public_live_commands_refuse_before_inspection_or_spending(configured, monkeypatch, capsys, action):
    def forbidden():
        pytest.fail("Unadmitted execution reached configuration or mutation")

    monkeypatch.setattr(configuration, "status", forbidden)
    before = snapshot(review.OUTPUT)
    assert public.main([action]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "BLOCKED_OWNERSHIP" and not report["dispatch_allowed"]
    assert snapshot(review.OUTPUT) == before


def test_cold_isolated_command_cannot_dispatch(configured):
    before = snapshot(review.OUTPUT)
    result = subprocess.run([configuration.PYTHON, "-I", str(Path(public.__file__)),
                             "campaign-execute"], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "BLOCKED_OWNERSHIP"
    assert snapshot(review.OUTPUT) == before


@pytest.mark.parametrize("filename", ["ownership-preflight.json", "preparation-authority.json"])
@pytest.mark.parametrize("mutation", ["missing", "altered", "symlink", "late"])
def test_completion_evidence_loss_blocks_candidate(configured, monkeypatch, filename, mutation):
    path = configured.root.parent / filename
    if mutation == "missing":
        path.unlink()
    elif mutation == "altered":
        write_json(path, {"foreign": True})
    elif mutation == "symlink":
        saved = path.with_suffix(".original")
        path.rename(saved)
        path.symlink_to(saved)
    else:
        capture = configuration.installed_authority.capture

        def changed():
            result = capture()
            path.write_bytes(path.read_bytes() + b" ")
            return result

        monkeypatch.setattr(configuration.installed_authority, "capture", changed)
    with pytest.raises((RecoveryStop, ValueError, FileNotFoundError)):
        configuration.derive()


@pytest.mark.parametrize("mutation", ["omit_inherited", "omit_prospective", "stop_contract",
    "stop_order", "predecessor", "authority_extra", "authority_missing", "generations"])
def test_structured_rehashed_omissions_never_become_authority(configured, mutation):
    value = configuration.derive()
    if mutation == "omit_inherited":
        value["stop_bindings"].pop(0)
    elif mutation == "omit_prospective":
        value["stop_bindings"].pop()
    elif mutation == "stop_contract":
        value["stop_bindings"][0]["contract"] = {}
    elif mutation == "stop_order":
        value["stop_bindings"].reverse()
    elif mutation == "predecessor":
        value["handover"]["records"].pop(0)
    elif mutation == "authority_extra":
        value["execution_authority"]["recovery_journal"] = value["recovery_journal"]
    elif mutation == "authority_missing":
        value["execution_authority"].pop("account")
    else:
        value["policy"]["maximum_generations"] += 1
    with pytest.raises(RecoveryStop):
        configuration.validate(campaign_history.identified(value))


@pytest.mark.parametrize("action", ["configuration", "status"])
def test_public_read_only_actions_and_errors(configured, capsys, action):
    before = snapshot(review.OUTPUT)
    assert public.main([action]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "OFFLINE_CONFIGURATION_READY"
    assert snapshot(review.OUTPUT) == before
    (configured.root.parent / "ownership-preflight.json").unlink()
    before = snapshot(review.OUTPUT)
    assert public.main([action]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED_ACCOUNTING"
    assert snapshot(review.OUTPUT) == before


@pytest.mark.parametrize("configured", [(2, False), (2, True), (14, True), (15, False)], indirect=True)
def test_public_restart_receipts_and_handover_charges_are_cumulative(configured):
    installed = read_json(configured.installed_path)
    used = installed["records"][0]["predecessor"]["inherited_restarts"]
    before = snapshot(review.OUTPUT)
    if used == 15:
        with pytest.raises(ValueError, match="exhausted"):
            configuration.derive()
    else:
        value = configuration.derive()
        assert value["inherited_worker_restarts"] == used + 2
        assert value["maximum_worker_restarts"] == 14 - used
    assert snapshot(review.OUTPUT) == before


def test_public_inspection_does_not_reconcile_coherent_pending_campaign(configured):
    case = configured
    current = campaign_history.CampaignHistory(case.root, read_json(case.root / "seed.json"),
                                               check=lambda: True)
    with current.owned():
        current.begin(transition(current))
    before = snapshot(review.OUTPUT)
    assert configuration.status()["status"] == "OFFLINE_CONFIGURATION_READY"
    assert current.status()["status"] == "PENDING"
    assert snapshot(review.OUTPUT) == before


@pytest.mark.parametrize("field,replacement", [("new_reservations", False),
    ("import_idempotent", 1), ("historical_sequences", 1.0), ("observations", 2.0),
    ("root_counts", {"root": 1.0}), ("lineage_counts", {"lineage": True})])
def test_paired_completion_type_changes_cannot_rehash_the_candidate(configured, field, replacement):
    path = configured.root.parent / "ownership-preflight.json"
    ownership = read_json(path)
    ownership[field] = replacement
    write_json(path, ownership)
    receipt = configured.root.parent / "preparation.json"
    write_json(receipt, {**read_json(receipt), "ownership": ownership})
    before = snapshot(review.OUTPUT)
    with pytest.raises(RecoveryStop, match="native ownership preflight"):
        configuration.derive()
    assert snapshot(review.OUTPUT) == before


@pytest.mark.parametrize("kind", ["canonical_string", "list", "null"])
def test_embedded_completion_must_be_an_object(configured, kind):
    ownership = read_json(configured.root.parent / "ownership-preflight.json")
    replacement = json.dumps(ownership, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if kind != "canonical_string":
        replacement = [ownership] if kind == "list" else None
    receipt = configured.root.parent / "preparation.json"
    write_json(receipt, {**read_json(receipt), "ownership": replacement})
    before = snapshot(review.OUTPUT)
    with pytest.raises(RecoveryStop, match="native ownership preflight"):
        configuration.derive()
    assert snapshot(review.OUTPUT) == before
