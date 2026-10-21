"""Archived source bytes stay immutable while new ZLB work runs on SSD."""

import runpy
import shutil
import sys
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest
import test_codex_runtime
from test_assembled_budget_runtime import authorized

from humanvoice.artifacts import FORMAT_VERSION, digest, read_json, validate_snapshot, write_json
from humanvoice.model import ModelAdapter
from tools import archive_evidence as archive
from tools import automatic_manuscript_stage as manuscript
from tools import inventory_stage_runtime as inventory
from tools import run_zlb_ssd_20261021 as controller
from tools import zlb_ssd_workspace as workspace
from tools.inventory_transport_continuation import tree_hashes
from tools.ensemble_closure_contract import AllocationLedger

codex = test_codex_runtime.codex


@pytest.fixture
def archived_snapshot(tmp_path):
    physical = tmp_path / "archive/snapshot"
    (physical / "source").mkdir(parents=True)
    (physical / "source/source.tex").write_bytes(b"Original source.\n")
    hashes = {"source/source.tex": digest((physical / "source/source.tex").read_bytes())}
    brief = {"reader": "test"}
    write_json(physical / "manifest.json", {"format_version": FORMAT_VERSION, "file_hashes": hashes,
        "source_hash": digest(hashes), "brief": brief, "brief_hash": digest(brief)})
    write_json(physical / ".humanvoice/policy.json", {"retained": True})
    logical = tmp_path / "logical/snapshot"
    logical.parent.mkdir()
    logical.symlink_to(physical, target_is_directory=True)
    mapping = archive.Archive({logical: physical}, {"test": "verified"})
    return logical, physical, mapping, tmp_path / "ssd", tmp_path / "origin.json"


def test_workspace_preserves_archive_and_allows_new_outputs(archived_snapshot):
    source, physical, mapping, destination, receipt = archived_snapshot
    before = tree_hashes(physical)
    with archive.access(mapping):
        proof = workspace.workspace(source, destination, receipt, archive_identity=mapping.identity)
        assert tree_hashes(destination) == before
        assert proof["source_files"] == before and proof["model_calls"] == 0
        write_json(destination / ".humanvoice/inventory/result.json", {"new": True})
        assert workspace.workspace(source, destination, receipt, archive_identity=mapping.identity,
                                   allow_progress=True) == proof
        assert validate_snapshot(source) == validate_snapshot(destination)
    assert tree_hashes(physical) == before and source.is_symlink()


@pytest.mark.parametrize("defect", ["changed", "missing", "added", "origin", "link", "source"])
def test_workspace_rejects_changed_evidence(archived_snapshot, defect):
    source, physical, mapping, destination, receipt = archived_snapshot
    with archive.access(mapping):
        workspace.workspace(source, destination, receipt, archive_identity=mapping.identity)
    if defect == "changed":
        (destination / ".humanvoice/policy.json").write_text("{}")
    elif defect == "missing":
        (destination / ".humanvoice/policy.json").unlink()
    elif defect == "added":
        (destination / "unaccounted").write_text("unexpected initial output")
    elif defect == "origin":
        write_json(receipt, {"changed": True})
    elif defect == "link":
        (destination / "unexpected").symlink_to(physical)
    else:
        (physical / ".humanvoice/policy.json").write_text("{}")
    with archive.access(mapping), pytest.raises(ValueError):
        workspace.workspace(source, destination, receipt, archive_identity=mapping.identity)


def test_workspace_refuses_unknown_destination_and_symlink(archived_snapshot):
    source, physical, mapping, destination, receipt = archived_snapshot
    destination.mkdir()
    with archive.access(mapping), pytest.raises(ValueError, match="origin receipt"):
        workspace.workspace(source, destination, receipt, archive_identity=mapping.identity)
    destination.rmdir()
    destination.symlink_to(physical, target_is_directory=True)
    with archive.access(mapping), pytest.raises(ValueError, match="separate"):
        workspace.workspace(source, destination, receipt, archive_identity=mapping.identity)


def test_workspace_resumes_interrupted_copy_only_after_verification(archived_snapshot, monkeypatch):
    source, physical, mapping, destination, receipt = archived_snapshot
    original = shutil.copytree

    def interrupted(selected_source, output, *arguments, **keywords):
        result = original(selected_source, output, *arguments, **keywords)
        if selected_source == source:
            raise RuntimeError("synthetic interruption")
        return result

    with archive.access(mapping):
        monkeypatch.setattr(shutil, "copytree", interrupted)
        with pytest.raises(RuntimeError, match="interruption"):
            workspace.workspace(source, destination, receipt, archive_identity=mapping.identity)
        assert receipt.exists() and not destination.exists()
        monkeypatch.setattr(shutil, "copytree", original)
        workspace.workspace(source, destination, receipt, archive_identity=mapping.identity)
        assert tree_hashes(destination) == tree_hashes(source)


def test_workspace_routing_checks_source_and_retained_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "BASE", tmp_path)
    monkeypatch.setattr(workspace, "SOURCE", tmp_path / "archive")
    monkeypatch.setattr(workspace, "WORK", tmp_path / "ssd")
    monkeypatch.setattr(workspace, "STAGE", tmp_path / "stage")
    calls = []
    monkeypatch.setattr(workspace, "ensure", lambda **kwargs: calls.append(kwargs))
    row = {"snapshot": "archive", "inventory_maximum_logical_calls": 540}
    assert workspace.route("held-out", row) is row and not calls
    assert workspace.route("zlb", row) == {**row, "snapshot": "ssd"}
    assert row["snapshot"] == "archive"
    with pytest.raises(ValueError, match="source selection"):
        workspace.route("zlb", {"snapshot": "other"})
    write_json(workspace.STAGE / "plan.json", {"snapshot": str(workspace.WORK)})
    assert workspace.route("zlb", row)["snapshot"] == "ssd"
    write_json(workspace.STAGE / "plan.json", {"snapshot": "other"})
    with pytest.raises(ValueError, match="another working"):
        workspace.route("zlb", row)


@pytest.mark.parametrize("interrupted", [False, True])
def test_ssd_controller_routes_and_restores(monkeypatch, interrupted):
    review_size = controller.previous.previous.previous
    before = controller.previous.refresh, controller.previous.EVIDENCE, controller.scope.command, controller.previous.recovery_command
    calls = []
    original_row = {"snapshot": "archive"}
    monkeypatch.setattr(workspace, "route", lambda name, row: row if name == "held-out" else {**row, "snapshot": "ssd"})

    def benchmark(name, row, campaign, bounds):
        calls.append((name, row))

    monkeypatch.setattr(review_size, "benchmark_chain", benchmark)

    def run():
        assert controller.ACTIVE and controller.previous.refresh is controller.refresh
        assert controller.previous.EVIDENCE == controller.EVIDENCE
        command = controller.scope.command("run-manuscript-with-300-grant-20261008.py", "execute", "--live")
        assert command[1] == str(controller.ROOT / "tools/zlb_stage_runner.py")
        assert command[2:] == ["run-manuscript-with-300-grant-20261008.py", "execute", "--live"]
        assert controller.previous.recovery_command is controller.recovery_command
        review_size.benchmark_chain("held-out", original_row, None, None)
        review_size.benchmark_chain("zlb", original_row, None, None)
        if interrupted:
            raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(controller.previous, "run", run)
    if interrupted:
        with pytest.raises(RuntimeError, match="interruption"):
            controller.run()
    else:
        controller.run()
    assert calls == [("held-out", original_row), ("zlb", {"snapshot": "ssd"})]
    assert original_row == {"snapshot": "archive"}
    assert review_size.benchmark_chain is benchmark and not controller.ACTIVE
    assert before == (controller.previous.refresh, controller.previous.EVIDENCE, controller.scope.command,
                      controller.previous.recovery_command)


@pytest.mark.parametrize("scoped", [False, True])
def test_native_preparation_binds_ssd_snapshot(archived_snapshot, monkeypatch, tmp_path, scoped):
    source, physical, mapping, destination, receipt = archived_snapshot
    native_path = workspace.BASE / "run-manuscript-with-300-grant-20261008.py"
    native = runpy.run_path(str(native_path))["main"]
    globals_ = native.__globals__
    account_path = tmp_path / "account.json"
    account = {"reservation_ceiling": 100, "allowance": 600000000}
    write_json(account_path, account)
    profile = {"runtime": {"type": "codex-cli", "provider": "test", "responses_url": "https://example.invalid"}}
    monkeypatch.setattr(manuscript, "ACCOUNT", account_path)
    monkeypatch.setattr(manuscript, "validate_account", lambda value: value)
    monkeypatch.setattr(manuscript, "require_rights", lambda *args, **kwargs: {"test": True})
    monkeypatch.setattr(manuscript, "selected_profile", lambda: profile)
    monkeypatch.setattr(manuscript, "require_qualified_stage", lambda plan: {"test": True})
    monkeypatch.setitem(globals_, "__file__", str(tmp_path / native_path.name))
    monkeypatch.setitem(globals_, "runtime", lambda *args: nullcontext())
    monkeypatch.setitem(globals_, "status", lambda grant: {"available": 1247})
    output = tmp_path / "stage"
    monkeypatch.setattr(sys, "argv", ["native", "prepare", "--output", str(output), "--snapshot", str(destination),
                                     "--stage", "inventory", "--max-calls", "540"])
    before = tree_hashes(physical), account_path.read_bytes()
    planning = inventory.pipeline(planning=[(destination, "inventory")]) if scoped else nullcontext()
    with archive.access(mapping), planning, controller.scope.verification_only():
        workspace.workspace(source, destination, receipt, archive_identity=mapping.identity)
        with pytest.raises(RuntimeError, match="cannot transmit"):
            ModelAdapter.invoke(None, "forbidden")
        assert native() == 0
    plan = read_json(output / "plan.json")
    assert plan["snapshot"] == str(destination) and len(plan["calls"]) == 540
    assert plan["bindings"]["manifest"] == digest(validate_snapshot(destination))
    assert not (output / "allocation-ledger.json").exists()
    assert before == (tree_hashes(physical), account_path.read_bytes())
    if scoped:
        inventory.validate_extension(plan)
        with archive.access(mapping), inventory.pipeline(planning=[(destination, "inventory")]):
            assert manuscript.plan_for(destination, "inventory", 540, account["reservation_ceiling"],
                                       recovery=True, account_allowance=account["allowance"]) == plan
        assert not list(destination.glob(".humanvoice/*budget*.json"))


def test_inventory_runner_uses_native_scoped_preparation(tmp_path, monkeypatch):
    runner = controller.runner
    native = runner.runpy.run_path
    observed = []
    monkeypatch.setattr(runner.scope, "BASE", tmp_path)
    monkeypatch.setattr(runner.scope, "accounting_scope", nullcontext)
    monkeypatch.setattr(runner, "cached_parallel_verification", lambda **kwargs: nullcontext())
    snapshot = tmp_path / "snapshot"
    base = {"stage": "inventory", "snapshot": str(snapshot), "plan_identity": "native",
            "purposes": sorted(manuscript.PURPOSES["inventory"])}
    monkeypatch.setattr(manuscript, "plan_for", lambda *args, **kwargs: deepcopy(base))
    script = tmp_path / "run-manuscript-with-300-grant-20261008.py"
    script.write_text("from tools import automatic_manuscript_stage as manuscript\n"
                      "from humanvoice.model import ModelAdapter\n"
                      "plan = manuscript.plan_for(snapshot, 'inventory')\n"
                      "ModelAdapter.invoke(None, 'forbidden')\n")

    def run_path(path, **kwargs):
        assert path == str(script)
        observed.append(manuscript.plan_for(snapshot, "inventory"))
        return native(path, init_globals={"snapshot": snapshot}, **kwargs)

    monkeypatch.setattr(runner.runpy, "run_path", run_path)
    arguments = ["runner", script.name, "prepare", "--snapshot", str(snapshot), "--stage", "inventory"]
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(RuntimeError, match="cannot transmit"):
        runner.main()
    assert sys.argv is arguments and len(observed) == 1
    inventory.validate_extension(observed[0])
    assert manuscript.plan_for(snapshot, "inventory") == base


@pytest.mark.parametrize("defect", ["stage", "purpose", "candidate", "backoff", "extra", "restart", "files"])
def test_inventory_policy_rejects_scope_changes(tmp_path, monkeypatch, defect):
    monkeypatch.setattr(manuscript, "plan_for", lambda *args, **kwargs: {
        "stage": "inventory", "snapshot": str(tmp_path), "plan_identity": "native",
        "purposes": sorted(manuscript.PURPOSES["inventory"])})
    with inventory.pipeline(planning=[(tmp_path, "inventory")]):
        plan = manuscript.plan_for(tmp_path, "inventory")
        inventory.validate_extension(plan)
        if defect == "stage":
            plan["stage"] = "humanize"
        elif defect == "purpose":
            plan["purposes"].append("source_grounded_rewrite")
        elif defect == "candidate":
            plan["math_redline_extension"] = {}
        elif defect == "backoff":
            plan["recovery"]["backoff_seconds"] = 0
        elif defect == "extra":
            plan["recovery"] = inventory.network.policy(15)
        elif defect == "restart":
            plan["technical_restart"] = {}
        else:
            plan["inventory_stage_extension"]["files"] = {}
        plan.pop("plan_identity")
        plan["plan_identity"] = digest(plan)
        with pytest.raises(ValueError):
            inventory.network.validate_extension(plan)


def test_inventory_policy_leaves_candidate_planning_intact(tmp_path, monkeypatch):
    base = {"stage": "humanize", "snapshot": str(tmp_path), "plan_identity": "native"}
    monkeypatch.setattr(manuscript, "plan_for", lambda *args, **kwargs: deepcopy(base))
    with inventory.history.pipeline(planning=[(tmp_path, "humanize")], snapshots=[tmp_path]):
        expected = manuscript.plan_for(tmp_path, "humanize")
    with inventory.pipeline(), inventory.history.pipeline(planning=[(tmp_path, "humanize")], snapshots=[tmp_path]):
        assert manuscript.plan_for(tmp_path, "humanize") == expected
    assert {"math_redline_extension", "writer_size_extension", "assembled_size_extension"} <= set(expected)
    with pytest.raises(ValueError, match="explicit inventory"):
        with inventory.pipeline(planning=[(tmp_path, "humanize")]):
            pytest.fail("Candidate stage accepted by inventory planner")


@pytest.mark.parametrize("boundary", [False, True])
def test_inventory_runner_restores_execution_and_boundary(tmp_path, monkeypatch, boundary):
    runner = controller.runner
    snapshot, output = tmp_path / "snapshot", tmp_path / "stage"
    base = {"stage": "inventory", "snapshot": str(snapshot), "plan_identity": "native",
            "purposes": sorted(manuscript.PURPOSES["inventory"])}
    monkeypatch.setattr(manuscript, "plan_for", lambda *args, **kwargs: deepcopy(base))
    with inventory.pipeline(planning=[(snapshot, "inventory")]):
        plan = manuscript.plan_for(snapshot, "inventory")
    write_json(output / "plan.json", plan)
    monkeypatch.setattr(runner.scope, "BASE", tmp_path)
    monkeypatch.setattr(runner.scope, "accounting_scope", nullcontext)
    workers = []
    monkeypatch.setattr(runner, "cached_parallel_verification", lambda **kwargs: workers.append(kwargs) or nullcontext())
    name = "verify-manuscript-boundary-20261007.py" if boundary else "run-manuscript-with-300-grant-20261008.py"
    arguments = ["runner", name, "stage"] if boundary else ["runner", name, "execute", "--output", str(output), "--live"]
    monkeypatch.setattr(sys, "argv", arguments)
    sentinel = lambda *args, **kwargs: "provider sentinel"
    monkeypatch.setattr(ModelAdapter, "invoke", sentinel)

    def native(path, **kwargs):
        assert path == str(tmp_path / name)
        assert manuscript.plan_for(snapshot, "inventory") == plan
        if boundary:
            with pytest.raises(RuntimeError, match="cannot transmit"):
                ModelAdapter.invoke(None, "forbidden")
        else:
            assert ModelAdapter.invoke(SimpleNamespace(snapshot_dir=snapshot), "allowed") == "provider sentinel"
        raise RuntimeError("native stopped")

    monkeypatch.setattr(runner.runpy, "run_path", native)
    with pytest.raises(RuntimeError, match="native stopped"):
        runner.main()
    assert sys.argv is arguments and ModelAdapter.invoke is sentinel
    assert manuscript.plan_for(snapshot, "inventory") == base
    assert len(workers) == 1 and workers[0]["workers"] == 16


def test_inventory_runner_delegates_candidate_and_historical_commands(tmp_path, monkeypatch):
    runner = controller.runner
    calls = []
    monkeypatch.setattr(runner.previous, "main", lambda: calls.append(list(sys.argv)) or 7)
    monkeypatch.setattr(sys, "argv", ["runner", "run-manuscript-with-300-grant-20261008.py", "prepare", "--stage", "humanize"])
    assert runner.main() == 7
    write_json(tmp_path / "plan.json", {"stage": "inventory"})
    monkeypatch.setattr(sys, "argv", ["runner", "run-manuscript-with-300-grant-20261008.py", "execute", "--output", str(tmp_path)])
    assert runner.main() == 7
    monkeypatch.setattr(sys, "argv", ["runner", runner.scope.INVENTORY, "verify-stage", "--output", str(tmp_path)])
    assert runner.main() == 7 and len(calls) == 3


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("partial", [False, True])
def test_inventory_native_retry_preserves_failed_charge(codex, authorized, monkeypatch, partial):
    network, overload = inventory.network, inventory.history.overload
    failure = {"purpose": "concept_extraction", "message": overload.DIAGNOSTIC}
    if partial:
        failure["response"] = "Partial substantive answer"
    write_json(codex.settings, {"response": [], "transport_failures": [failure]})
    monkeypatch.setattr(manuscript, "selected_profile", lambda: codex.profile)
    waits, native_wait = [], network.wait_until

    def wait(path, failure_hash, failed_at):
        now = [failed_at]

        def sleep(seconds):
            now[0] += seconds
            waits.append(seconds)

        native_wait(path, failure_hash, failed_at, clock=lambda: now[0], sleep=sleep)

    monkeypatch.setattr(network, "wait_until", wait)
    output = codex.snapshot.parent / "inventory-stage"
    with inventory.pipeline(planning=[(codex.snapshot, "inventory")], authorization=authorized[0]):
        plan = manuscript.plan_for(codex.snapshot, "inventory", 1, 0, recovery=True)
        write_json(output / "plan.json", plan)
        ledger = AllocationLedger(output / "allocation-ledger.json", plan)
        with manuscript.accounted_model(output, plan, ledger):
            if partial:
                with pytest.raises(RuntimeError):
                    test_codex_runtime.call(codex)
            else:
                assert test_codex_runtime.call(codex).text == "[]"
        ledger.reload()
        assert len(ledger.record["calls"]) == (1 if partial else 2)
        assert sum(waits) == (0 if partial else 900)
        failed = ledger.record["calls"][0]
        assert failed["status"] == "incomplete" and failed["usage"] is None and failed["reservation"] == 544000
        layout = network.attempt_layout(output, plan, ledger.record["calls"])
        assert layout["recoveries"] == (0 if partial else 1)
        if not partial:
            assert ledger.record["calls"][1]["status"] == "complete"
            retained = read_json(output / "retry-waits/0000.json")
            assert retained["eligible_after"] - retained["failed_at"] == 900
