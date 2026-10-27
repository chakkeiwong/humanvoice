"""Adversarial offline bootstrap cuts without substituting for native admission."""

import fcntl
import multiprocessing
import os
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_inventory_recovery_v3_campaign_history import (
    campaign,
    snapshot,
    transition,
    validated,
)
from test_inventory_recovery_v3_policy import policy

from humanvoice.artifacts import digest, read_json, write_json
from tools import sol_inventory_program as original
from tools.inventory_recovery_v3 import (
    campaign_history,
    campaign_initialization,
    campaign_preparation,
    journal_history,
    journal_initialization,
    probe,
    runtime,
)
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.requests import NativeRequests


@pytest.fixture
def bootstrap(tmp_path, monkeypatch):
    root, account, grant = tmp_path / "campaign", tmp_path / "account.json", tmp_path / "grant.json"
    output = root / "generation-00"
    document = policy(inherited_recovery=0)
    write_json(account, {"events": [], "plans": [], "reservation_ceiling": 0, "gross_reservation_ceiling": 0})
    authority = campaign_history.identified({"account": str(account), "fixture": "offline-authority"})
    write_json(grant, authority)
    anchor = {"account_hash": digest(read_json(account)), "events": 0, "plans": 0,
              "reservation_ceiling": 0, "gross_reservation_ceiling": 0, "grant": {"identity": authority["identity"]}}
    transition = campaign_history.identified({"version": "inventory-budget-successor-v1",
                                              "recovery_history": {"identity": "fixture-history"}})
    plan = {"snapshot": str(output / "snapshot"), "bindings": {"source": "fixture-source"}, runtime.FIELD: {
        "migration_identity": "fixture-migration", "policy": document, "transition": transition}}
    plan["plan_identity"] = digest(plan)
    values = {"plan.json": plan, "transition.json": transition, "prepared-authority.json": anchor,
              "admission-probe.json": {"status": "pass", "model_calls": 0, "transition": transition["identity"]},
              "preparation-intent.json": {}, "prepared-snapshot.json": {}, "execution.json": {"status": "prepared"}}
    for name, value in values.items():
        write_json(output / name, value)
    (output / "snapshot").mkdir()
    (output / "snapshot/source.txt").write_text("fixture source")
    monkeypatch.setattr(original.account, "ACCOUNT", account)
    monkeypatch.setattr(original, "GRANT", grant)
    monkeypatch.setattr(runtime, "contract", lambda: {"fixture": "bootstrap-binding"})
    folder = output / "probe" / digest(runtime.contract())[:16]
    for name in ("observations.json", "replay-log.json", "probe-intent.json", "verification.json"):
        write_json(folder / name, {"fixture": name})

    def verified(intent, check):
        assert check() is True
        return campaign_preparation.descriptor(intent, campaign_preparation.evidence(intent))

    def imported(resolver, observations):
        with resolver.journal.locked():
            record = resolver.journal.read()
            if "inherited_recovery" not in record:
                record["inherited_recovery"] = {"history_identity": "fixture-history"}
                resolver.journal.save(record)

    def resolver_init(resolver, plan, output, journal, owner):
        resolver.plan, resolver.output, resolver.journal, resolver.owner = plan, output, journal, owner

    monkeypatch.setattr(NativeRequests, "__init__", resolver_init)
    monkeypatch.setattr(campaign_initialization, "verify_prepared", verified)
    monkeypatch.setattr(probe, "observations", lambda *arguments: [])
    monkeypatch.setattr(NativeRequests, "import_history", imported)
    monkeypatch.setattr(campaign_initialization.accounting, "document_scope", lambda *arguments: nullcontext())
    return SimpleNamespace(root=root, output=output, account=account, grant=grant, verified=verified,
                           imported=imported, intent={"output": str(output), "transition": transition})


def mutate(case, kind):
    if kind == "grant_replaced":
        write_json(case.grant, campaign_history.identified({**read_json(case.grant), "changed": True}))
    elif kind == "grant_missing":
        case.grant.unlink()
    elif kind == "source":
        (case.output / "snapshot/source.txt").write_text("different source")
    elif kind == "allocation":
        write_json(case.output / "allocation-ledger.json", {})
    elif kind == "hold":
        write_json(case.grant.with_suffix(".stages.json"), {"stages": [{"output": str(case.output)}]})
    elif kind == "account_prefix":
        write_json(case.account, {**read_json(case.account), "changed": True})
    elif kind == "plan_rehashed":
        path = case.output / "plan.json"
        plan = {**read_json(path), "changed": True}
        plan["plan_identity"] = digest({key: value for key, value in plan.items() if key != "plan_identity"})
        write_json(path, plan)
    else:
        path = case.output / kind
        path.write_bytes(path.read_bytes() + b" ")


@pytest.mark.parametrize("boundary", ["verified", "imported"])
@pytest.mark.parametrize("kind", ["plan.json", "plan_rehashed", "admission-probe.json", "transition.json",
                                  "prepared-authority.json", "execution.json", "source", "grant_replaced",
                                  "grant_missing", "allocation", "hold", "account_prefix", "contract"])
def test_late_changes_block_before_next_publication(bootstrap, monkeypatch, boundary, kind):
    case, published = bootstrap, []
    native = campaign_history.persist

    def publish(path, value):
        published.append(path.name)
        native(path, value)

    def change():
        if kind == "contract":
            monkeypatch.setattr(runtime, "contract", lambda: {"changed": True})
        else:
            mutate(case, kind)

    if boundary == "verified":
        def verify(intent, check):
            result = case.verified(intent, check)
            change()
            return result

        monkeypatch.setattr(campaign_initialization, "verify_prepared", verify)
    else:
        def imported(resolver, observations):
            case.imported(resolver, observations)
            change()

        monkeypatch.setattr(NativeRequests, "import_history", imported)
    monkeypatch.setattr(campaign_history, "persist", publish)
    with pytest.raises((RecoveryStop, ValueError, FileNotFoundError)):
        campaign_initialization.initialize(case.root, check=lambda: True)
    assert published == []
    assert not (case.root / "initialized.json").exists()
    assert (case.root / "campaign-proposal.json").exists() is (boundary == "imported")


@pytest.mark.parametrize("module,name", [(campaign_initialization, "campaign-proposal.json"),
    (journal_initialization, "initialized.json"), (journal_history, "reservations.json"),
    *[(campaign_history, name) for name in ("initialization-intent.json", "seed.json", "head.json", "cursor.json")]])
@pytest.mark.parametrize("kind", ["plan.json", "grant_replaced", "stop"])
def test_each_publication_rechecks_exact_authority(bootstrap, monkeypatch, module, name, kind):
    case, cuts, stopped = bootstrap, [], []
    attribute = "atomic_persist" if module is journal_initialization else "persist"
    native = getattr(module, attribute)

    def publish(path, value, **keywords):
        native(path, value, **keywords)
        if path.name == name and not cuts:
            cuts.append(path)
            if kind == "stop":
                stopped.append(True)
            else:
                mutate(case, kind)

    monkeypatch.setattr(module, attribute, publish)
    with pytest.raises((RecoveryStop, ValueError)):
        campaign_initialization.initialize(case.root, check=lambda: not stopped)
    assert cuts
    assert not (case.root / "initialized.json").exists()


def test_bootstrap_allows_sibling_growth_without_new_own_allocation(bootstrap, monkeypatch):
    case = bootstrap

    def imported(resolver, observations):
        case.imported(resolver, observations)
        account = read_json(case.account)
        account["plans"].append({"output": str(case.root.parent / "sibling"), "plan_identity": "sibling"})
        account["events"].append({"fixture": "sibling growth"})
        account["reservation_ceiling"] += 1
        account["gross_reservation_ceiling"] += 1
        write_json(case.account, account)

    monkeypatch.setattr(NativeRequests, "import_history", imported)
    result = campaign_initialization.initialize(case.root, check=lambda: True)
    assert result["status"] == "OFFLINE_CAMPAIGN_INITIALIZED"
    assert result["live_execution_enabled"] is False


@pytest.mark.parametrize("name", ["plan.json", "admission-probe.json", "transition.json"])
@pytest.mark.parametrize("mutation", ["missing", "changed", "null", "list"])
def test_initial_native_membership_is_read_only_and_required(bootstrap, name, mutation):
    case = bootstrap
    result = campaign_initialization.initialize(case.root, check=lambda: True)
    current = campaign_history.CampaignHistory(case.root, result["seed"], check=lambda: True)
    path = case.output / name
    if mutation == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b" " if mutation == "changed" else
                         b"null" if mutation == "null" else b"[]")
    before = snapshot(case.root)
    with pytest.raises((RecoveryStop, ValueError)):
        current.status()
    assert before == snapshot(case.root)


@pytest.mark.parametrize("key", ["proposal", "prepared", "initial_journal", "version"])
def test_native_seed_cannot_silently_fall_back_to_generic_binding(bootstrap, key):
    case = bootstrap
    result = campaign_initialization.initialize(case.root, check=lambda: True)
    seed = deepcopy(result["seed"])
    if key == "version":
        seed["version"] = campaign_history.VERSION
        seed["binding"] = {"fixture": "offline-component-only"}
    else:
        del seed["binding"][key]
    seed = campaign_history.identified(seed)
    with pytest.raises(RecoveryStop):
        campaign_history.CampaignHistory(case.root, seed, check=lambda: True)


@pytest.mark.parametrize("name", ["initialization-intent.json", "seed.json", "head.json", "cursor.json", "initialized.json"])
@pytest.mark.parametrize("value", [b"null", b"[]", b"false", b"0"])
def test_campaign_present_nonobjects_cannot_masquerade_as_missing(tmp_path, name, value):
    current = campaign(tmp_path)
    current.root.mkdir()
    (current.root / name).write_bytes(value)
    before = snapshot(current.root)
    with pytest.raises(RecoveryStop, match="JSON object"):
        current.status()
    assert before == snapshot(current.root)


def test_inherited_descriptor_retains_outer_lock_and_rejects_fork(tmp_path):
    current = campaign(tmp_path)
    with campaign_initialization.owned(current.root, lambda: True) as (descriptor, check):
        with current.owned(descriptor=descriptor):
            assert current.guard() is True
            with pytest.raises(RecoveryStop, match="nested"), current.owned(descriptor=descriptor):
                pytest.fail("Nested owner accepted")

            def child():
                try:
                    current.guard()
                except RecoveryStop:
                    os._exit(73)
                os._exit(74)

            process = multiprocessing.get_context("fork").Process(target=child)
            process.start()
            process.join(10)
            assert process.exitcode == 73
        assert check() is True
        with (current.root / "campaign.lock").open("a") as competing, pytest.raises(BlockingIOError):
            fcntl.flock(competing, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with current.owned():
        assert current.guard() is True


@pytest.mark.parametrize("kind", ["wrong", "unheld", "replaced", "foreign_owner"])
def test_invalid_inherited_descriptors_cannot_publish(tmp_path, kind):
    current = campaign(tmp_path)
    current.root.mkdir()
    path = current.root / "campaign.lock"
    with path.open("a") as handle, (current.root / "other.lock").open("a") as other:
        descriptor = handle.fileno()
        if kind == "wrong":
            descriptor = other.fileno()
        elif kind == "replaced":
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path.unlink()
            path.touch()
        elif kind == "foreign_owner":
            with path.open("a") as competitor:
                fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with pytest.raises(ValueError), current.owned(descriptor=descriptor):
                    pytest.fail("Foreign lock owner accepted")
            return
        with pytest.raises(ValueError), current.owned(descriptor=descriptor):
            pytest.fail("Invalid inherited owner accepted")


@pytest.mark.parametrize("module,name", [(campaign_initialization, "campaign-proposal.json"),
    *[(journal_initialization, name) for name in ("initialization-intent.json", "initialized.json",
                                                "consumption-head.json", "reservations.json")],
    *[(journal_history, name) for name in ("consumption-head.json", "reservations.json")],
    *[(campaign_history, name) for name in ("initialization-intent.json", "seed.json", "head.json",
                                           "cursor.json", "initialized.json")]])
@pytest.mark.parametrize("after", [False, True])
def test_composed_bootstrap_process_death_resumes_exactly_once(bootstrap, module, name, after):
    case = bootstrap

    def worker():
        attribute = "atomic_persist" if module is journal_initialization else "persist"
        native = getattr(module, attribute)

        def publish(path, value, **keywords):
            if path.name == name and not after:
                os._exit(73)
            native(path, value, **keywords)
            if path.name == name:
                os._exit(73)

        setattr(module, attribute, publish)
        campaign_initialization.initialize(case.root, check=lambda: True)
        os._exit(74)

    authority = case.account.read_bytes(), case.grant.read_bytes()
    process = multiprocessing.get_context("fork").Process(target=worker)
    process.start()
    process.join(15)
    assert not process.is_alive() and process.exitcode == 73
    result = campaign_initialization.initialize(case.root, check=lambda: True)
    assert result["state"]["status"] == "READY"
    before = snapshot(case.root)
    assert campaign_initialization.initialize(case.root, check=lambda: True) == result
    assert before == snapshot(case.root)
    assert authority == (case.account.read_bytes(), case.grant.read_bytes())


def test_initial_native_observation_retries_concurrent_plan_change(bootstrap, monkeypatch):
    from pathlib import Path

    case = bootstrap
    result = campaign_initialization.initialize(case.root, check=lambda: True)
    current = campaign_history.CampaignHistory(case.root, result["seed"], check=lambda: True)
    native, observed = Path.read_bytes, []

    def read(path):
        content = native(path)
        if path == case.output / "plan.json" and not observed:
            observed.append(True)
            path.write_bytes(content + b" ")
        return content

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", read)
        with pytest.raises(RecoveryStop, match="descriptor differs"):
            current.status()
    assert observed


@pytest.mark.parametrize("generation", [0, 1, 2])
@pytest.mark.parametrize("missing", ["directory", "plan.json", "admission-probe.json", "campaign-proposal.json"])
def test_initial_native_membership_remains_required_after_successors(bootstrap, generation, missing):
    case = bootstrap
    result = campaign_initialization.initialize(case.root, check=lambda: True)
    current = campaign_history.CampaignHistory(case.root, result["seed"], check=lambda: True)
    with current.owned():
        for _generation in range(generation):
            current.begin(transition(current))
            current.reconcile(validated)
    if missing == "directory":
        case.output.rename(case.root / "lost-initial")
    else:
        root = case.root if missing == "campaign-proposal.json" else case.output
        (root / missing).unlink()
    before = snapshot(case.root)
    with pytest.raises(RecoveryStop):
        current.status()
    assert before == snapshot(case.root)


@pytest.mark.parametrize("kind", ["grant_replaced", "grant_missing", "stop"])
def test_bootstrap_final_check_cannot_report_success_after_late_veto(bootstrap, monkeypatch, kind):
    case, stopped = bootstrap, []
    native = campaign_history.persist

    def publish(path, value):
        native(path, value)
        if path.name == "initialized.json":
            if kind == "stop":
                stopped.append(True)
            else:
                mutate(case, kind)

    monkeypatch.setattr(campaign_history, "persist", publish)
    with pytest.raises((RecoveryStop, FileNotFoundError)):
        campaign_initialization.initialize(case.root, check=lambda: not stopped)
    assert (case.root / "initialized.json").exists()
