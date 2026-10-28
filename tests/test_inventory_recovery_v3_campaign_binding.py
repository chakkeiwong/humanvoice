"""Offline binding rejects authority loss without freezing lawful consumption."""

import multiprocessing
import os
from copy import deepcopy

import pytest
from test_inventory_recovery_v3_bootstrap import bootstrap
from test_inventory_recovery_v3_campaign_history import snapshot, transition, validated
from test_inventory_recovery_v3_policy import reserve

from humanvoice.artifacts import digest, read_json, write_json
from tools import sol_inventory_program as original
from tools.inventory_recovery_v3 import (
    binding_publication,
    campaign_history,
    campaign_initialization,
    campaign_preparation,
    runtime,
)
from tools.inventory_recovery_v3 import campaign_binding as binding
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import RecoveryReservations

__all__ = ["bootstrap"]


@pytest.fixture
def candidate(bootstrap, monkeypatch):
    case = bootstrap
    rights = case.output / "snapshot/.humanvoice/rights/current.json"
    write_json(rights, {"fixture": "bound rights"})
    prepared_tree = {str(path.relative_to(case.output / "snapshot")): digest(path.read_bytes())
                     for path in (case.output / "snapshot").rglob("*") if path.is_file()}
    write_json(case.output / "prepared-snapshot.json", prepared_tree)
    campaign_initialization.initialize(case.root, check=lambda: True)
    monkeypatch.setattr(campaign_preparation, "verify_prepared", case.verified)
    monkeypatch.setattr(original.account, "validate_account", lambda account: account)
    monkeypatch.setattr(original, "grant_status", lambda path: {"identity": read_json(path)["identity"]})
    return case


def journal(case):
    proposal = read_json(case.root / "campaign-proposal.json")
    return RecoveryReservations(case.root / "recovery-journal", proposal["policy"], {
        "document": proposal["document"], "migration": proposal["migration"], "authority": proposal["identity"]})


def test_binding_is_read_only_on_reopen_and_cannot_dispatch(candidate):
    case = candidate
    result = binding.create(case.root, check=lambda: True)
    before = snapshot(case.root.parent)
    assert result["status"] == "OFFLINE_CAMPAIGN_BOUND"
    assert not result["live_execution_enabled"] and not result["dispatch_allowed"]
    assert result["model_calls"] == result["account_writes"] == result["grant_writes"] == 0
    assert binding.create(case.root, check=lambda: True) == result
    assert binding.inspect(case.root, check=lambda: True) == result
    assert before == snapshot(case.root.parent)


def test_binding_allows_append_only_account_journal_and_campaign_growth(candidate):
    case = candidate
    original_binding = binding.create(case.root, check=lambda: True)["binding"]
    account = read_json(case.account)
    account["events"].append({"fixture": "sibling consumption"})
    account["plans"].append({"output": str(case.root.parent / "sibling"), "plan_identity": "sibling"})
    account["reservation_ceiling"] += 10
    account["gross_reservation_ceiling"] += 10
    write_json(case.account, account)
    reserve(journal(case))
    current = campaign_history.CampaignHistory(case.root, read_json(case.root / "seed.json"), check=lambda: True)
    with current.owned():
        current.begin(transition(current))
    assert binding.inspect(case.root, check=lambda: True)["campaign"]["status"] == "PENDING"
    with current.owned():
        current.reconcile(validated)
    write_json(case.output / "execution.json", {"status": "executing"})
    result = binding.inspect(case.root, check=lambda: True)
    assert result["binding"] == original_binding and result["campaign"]["cursor"]["generation"] == 1
    assert result["dispatch_allowed"] is False


@pytest.mark.parametrize("change", ["missing_member", "extra_member", "root", "seed_identity",
    "proposal_identity", "grant_identity", "journal", "live", "floor"])
def test_rehashed_binding_cannot_omit_or_replace_derived_membership(candidate, change):
    case = candidate
    record = deepcopy(binding.create(case.root, check=lambda: True)["binding"])
    if change == "missing_member":
        del record["immutable"][next(iter(record["immutable"]))]
    elif change == "extra_member":
        record["immutable"][str(case.root / "foreign.json")] = "foreign"
    elif change in {"root", "seed_identity", "proposal_identity", "grant_identity"}:
        record[change] = "foreign"
    elif change == "journal":
        record["recovery_journal"]["path"] = str(case.root / "foreign/reservations.json")
    elif change == "live":
        record["live_execution_enabled"] = True
    else:
        record["account_floor"]["events"] = -1
    write_json(case.root / binding.FILENAME, campaign_history.identified(record))
    before = snapshot(case.root.parent)
    with pytest.raises(RecoveryStop):
        binding.inspect(case.root, check=lambda: True)
    assert before == snapshot(case.root.parent)


@pytest.mark.parametrize("name", ["campaign-proposal.json", "seed.json", "initialized.json",
    "generation-00/plan.json", "generation-00/prepared-authority.json",
    "generation-00/preparation-intent.json", "generation-00/transition.json",
    "generation-00/admission-probe.json", "recovery-journal/initialized.json"])
@pytest.mark.parametrize("mutation", ["missing", "bytes", "symlink"])
def test_immutable_binding_loss_never_repairs_or_overwrites_evidence(candidate, name, mutation):
    case = candidate
    binding.create(case.root, check=lambda: True)
    path = case.root / name
    if mutation == "missing":
        path.unlink()
    elif mutation == "bytes":
        path.write_bytes(path.read_bytes() + b" ")
    else:
        target = case.root.parent / "saved.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    before = snapshot(case.root.parent)
    with pytest.raises((RecoveryStop, ValueError, FileNotFoundError)):
        binding.inspect(case.root, check=lambda: True)
    assert before == snapshot(case.root.parent)


@pytest.mark.parametrize("kind", ["floor_events", "floor_plans", "fixed", "grant", "stages", "contract"])
def test_account_and_grant_floors_survive_reopen(candidate, monkeypatch, kind):
    case = candidate
    account = read_json(case.account)
    account["events"] = [{"fixture": "retained"}]
    account["plans"] = [{"output": "sibling", "plan_identity": "sibling"}]
    write_json(case.account, account)
    write_json(case.grant.with_suffix(".stages.json"), {"stages": [{"output": "sibling"}]})
    binding.create(case.root, check=lambda: True)
    if kind.startswith("floor_"):
        account[kind.removeprefix("floor_")] = []
        write_json(case.account, account)
    elif kind == "fixed":
        write_json(case.account, {**account, "authority": "replaced"})
    elif kind == "grant":
        write_json(case.grant, campaign_history.identified({**read_json(case.grant), "changed": True}))
    elif kind == "stages":
        case.grant.with_suffix(".stages.json").unlink()
    else:
        monkeypatch.setattr(runtime, "contract", lambda: {"changed": True})
    before = snapshot(case.root.parent)
    with pytest.raises((RecoveryStop, ValueError)):
        binding.inspect(case.root, check=lambda: True)
    assert before == snapshot(case.root.parent)


@pytest.mark.parametrize("kind", ["journal", "hold", "allocation", "stopped", "late_change"])
def test_new_binding_refuses_spending_or_veto_before_publication(candidate, monkeypatch, kind):
    case = candidate
    if kind == "journal":
        reserve(journal(case))
    elif kind == "hold":
        write_json(case.grant.with_suffix(".stages.json"), {"stages": [{"output": str(case.output)}]})
    elif kind == "allocation":
        write_json(case.output / "allocation-ledger.json", {})
    elif kind == "late_change":
        native = case.verified

        def verify(intent, check):
            result = native(intent, check)
            write_json(case.account, {**read_json(case.account), "changed": True})
            return result

        monkeypatch.setattr(campaign_preparation, "verify_prepared", verify)
    with pytest.raises(RecoveryStop):
        binding.create(case.root, check=lambda: kind != "stopped")
    assert not (case.root / binding.FILENAME).exists()


@pytest.mark.parametrize("alias", ["double_slash", "dot", "parent", "relative", "symlink"])
def test_binding_refuses_noncanonical_roots(candidate, alias):
    case = candidate
    path = str(case.root)
    if alias == "double_slash":
        path = "/" + path
    elif alias == "dot":
        path += "/."
    elif alias == "parent":
        path += "/../campaign"
    elif alias == "relative":
        path = "relative/campaign"
    else:
        link = case.root.parent / "linked"
        link.symlink_to(case.root, target_is_directory=True)
        path = str(link)
    with pytest.raises(ValueError):
        binding.create(path, check=lambda: True)
    assert not (case.root / binding.FILENAME).exists()


@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("boundary", range(4))
def test_binding_process_death_reopens_without_renewing_authority(candidate, after, boundary):
    case = candidate

    def child():
        native = binding.persist
        calls = []

        def publish(*arguments, **keywords):
            selected = len(calls) == boundary
            calls.append(True)
            if selected and not after:
                os._exit(73)
            native(*arguments, **keywords)
            if selected:
                os._exit(73)

        binding.persist = publish
        binding.create(case.root, check=lambda: True)
        os._exit(74)

    worker = multiprocessing.get_context("fork").Process(target=child)
    worker.start()
    worker.join(10)
    if worker.is_alive():
        worker.kill()
        worker.join(5)
    assert worker.exitcode == 73
    assert (case.root / binding.FILENAME).exists() is (boundary + int(after) >= 3)
    if boundary + int(after) < 4:
        before = snapshot(case.root.parent)
        with pytest.raises(RecoveryStop):
            binding.inspect(case.root, check=lambda: True)
        assert before == snapshot(case.root.parent)
    result = binding.create(case.root, check=lambda: True)
    retained = snapshot(case.root.parent)
    assert binding.create(case.root, check=lambda: True) == result
    assert retained == snapshot(case.root.parent)


@pytest.mark.parametrize("boundary", ["after_binding", "after_verification"])
@pytest.mark.parametrize("name", ["source.txt", ".humanvoice/rights/current.json"])
@pytest.mark.parametrize("mutation", ["change", "delete", "symlink", "extra"])
def test_snapshot_membership_rechecked_before_publication_and_on_reopen(candidate, monkeypatch, boundary, name, mutation):
    case = candidate

    def mutate():
        path = case.output / "snapshot" / name
        if mutation == "change":
            path.write_bytes(path.read_bytes() + b" changed")
        elif mutation == "delete":
            path.unlink()
        elif mutation == "symlink":
            target = case.root.parent / "saved-input"
            target.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(target)
        else:
            path.with_name("extra-input").write_bytes(b"unexpected")

    if boundary == "after_binding":
        binding.create(case.root, check=lambda: True)
        mutate()
        before = snapshot(case.root.parent)
        with pytest.raises((RecoveryStop, ValueError)):
            binding.create(case.root, check=lambda: True)
        assert before == snapshot(case.root.parent)
    else:
        def verify(intent, check):
            result = case.verified(intent, check)
            mutate()
            return result

        monkeypatch.setattr(campaign_preparation, "verify_prepared", verify)
        with pytest.raises((RecoveryStop, ValueError)):
            binding.create(case.root, check=lambda: True)
        assert not (case.root / binding.FILENAME).exists()
        assert not (case.root / binding_publication.INTENT).exists()


def test_allocated_snapshot_allows_generated_artifacts_not_changed_inputs(candidate):
    case = candidate
    retained = binding.create(case.root, check=lambda: True)["binding"]
    account = read_json(case.account)
    account["plans"].append({"output": str(case.output),
                             "plan_identity": read_json(case.output / "plan.json")["plan_identity"]})
    write_json(case.account, account)
    for name in ("inventory/spans.jsonl", "runtime/new/record.json", "cli/new/record.json"):
        write_json(case.output / "snapshot/.humanvoice" / name, {"fixture": "runtime growth"})
    assert binding.inspect(case.root, check=lambda: True)["binding"] == retained
    (case.output / "snapshot/source.txt").write_bytes(b"changed source")
    with pytest.raises(RecoveryStop):
        binding.inspect(case.root, check=lambda: True)


@pytest.mark.parametrize("kind", ["account", "hold"])
def test_rehashed_valid_shorter_consumption_floors_cannot_replace_publication_anchor(candidate, kind):
    case = candidate
    original_account = read_json(case.account)
    if kind == "account":
        account = deepcopy(original_account)
        account["events"].append({"fixture": "retained sibling consumption"})
        account["plans"].append({"output": "sibling", "plan_identity": "sibling"})
        write_json(case.account, account)
    else:
        write_json(case.grant.with_suffix(".stages.json"), {"stages": [{"output": "unallocated-sibling"}]})
    record = binding.create(case.root, check=lambda: True)["binding"]
    if kind == "account":
        write_json(case.account, original_account)
        record["account_floor"] = binding.account_floor(case.account, original_account)
    else:
        write_json(case.grant.with_suffix(".stages.json"), {"stages": []})
        record["grant_stages_floor"] = []
    write_json(case.root / binding.FILENAME, campaign_history.identified(record))
    before = snapshot(case.root.parent)
    with pytest.raises(RecoveryStop, match="publication anchor"):
        binding.create(case.root, check=lambda: True)
    assert before == snapshot(case.root.parent)


@pytest.mark.parametrize("name", [binding_publication.INTENT, binding_publication.MARKER, binding.FILENAME])
@pytest.mark.parametrize("mutation", ["missing", "nonobject", "changed"])
def test_committed_binding_publication_cannot_rebuild_lost_anchor(candidate, name, mutation):
    case = candidate
    binding.create(case.root, check=lambda: True)
    path = case.root / name
    if mutation == "missing":
        path.unlink()
    elif mutation == "nonobject":
        path.write_text("null")
    else:
        record = read_json(path)
        write_json(path, campaign_history.identified({**record, "changed": True}))
    before = snapshot(case.root.parent)
    with pytest.raises(RecoveryStop):
        binding.create(case.root, check=lambda: True)
    assert before == snapshot(case.root.parent)
