"""Exercise native admission, exact replay and continuation routing."""

import json
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from humanvoice.artifacts import digest, load_spans, read_json, write_json
from humanvoice.model import ModelAdapter
from tools import inventory_coverage_continuation as continuation
from tools import inventory_coverage_runner as runner
from tools import inventory_punctuation as punctuation
from tools import run_inventory_coverage_20261022 as controller
from test_manuscript_transport_recovery import codex, manuscript, invoke, finish


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_baseline_and_planning_accept_reproducible_punctuation(codex, tmp_path, monkeypatch):
    from humanvoice.baseline_evidence import verify_inventory_semantics
    from humanvoice.baseline_review import require_baseline_review
    from humanvoice.commands import init_command, inventory_command, plan_v2_command
    from humanvoice.concept_baseline import load_baseline
    from humanvoice.corpus_rights import install_rights
    from rights_fixture import fixture_rights

    source = tmp_path / "punctuation.tex"
    source.write_text("\\documentclass{article}\n\\begin{document}\nA nonnegative multiplier \\(x\\geq0\\):\n"
                      "\\[xy=0\\]\nThe product is zero.\n\\end{document}\n")
    snapshot = tmp_path / "punctuation"
    brief = tmp_path / "punctuation-brief.json"
    write_json(brief, read_json(codex.snapshot / "manifest.json")["brief"])
    assert init_command.run(SimpleNamespace(source=source, brief=brief, output=snapshot)) == 0
    rights = fixture_rights(snapshot)
    record = read_json(rights)
    record["extensions"].update(provider="VisionCoder", destinations=["https://cn.origincoder.com/v1/responses"])
    write_json(rights, record)
    install_rights(snapshot, rights)
    native = ModelAdapter.invoke

    def respond(model, **keywords):
        spans = list(load_spans(snapshot).values())
        prose = [row for row in spans if row["span_kind"] == "prose" and row["exact_text"].strip()]
        math = [row for row in spans if row["span_kind"] == "math"]
        concept = {"concept_id": "multiplier", "proposition": "A nonnegative multiplier has zero product.",
            "concept_type": "definition", "source_span_ids": [row["record_id"] for row in prose if row["exact_text"].strip() != ":"]
                + [math[0]["record_id"]], "supporting_spans": [math[1]["record_id"]],
            "teaching_roles": ["initial"], "prerequisites": [], "confidence": 1.0}
        if keywords["purpose"] == "concept_extraction":
            payload = [concept]
        elif keywords["purpose"] == "reconstruction_verification":
            payload = [{"concept_id": "multiplier", "verdict": "supported", "reconstruction": concept["proposition"],
                        "comparison": "Synthetic source agrees.", "confidence": 1.0,
                        "evidence_span_ids": concept["source_span_ids"] + concept["supporting_spans"]}]
        else:
            payload = [{"span_id": row["record_id"], "verdict": "covered", "explanation": "Synthetic coverage.",
                        "mapped_concept_ids": [] if row["exact_text"].strip() == ":" else ["multiplier"]} for row in prose]
        write_json(codex.settings, {"response": payload})
        return native(model, **keywords)

    monkeypatch.setattr(ModelAdapter, "invoke", respond)
    punctuation.enable(snapshot)
    with punctuation.runtime():
        assert inventory_command.run(SimpleNamespace(snapshot=snapshot, mock=False, freeze=True)) == 0
        baseline = load_baseline(snapshot / ".humanvoice/inventory/baseline.json")
        assert require_baseline_review(snapshot, baseline)["status"] == "pass"
        assert plan_v2_command.run(SimpleNamespace(snapshot=snapshot, max_unit_size=2000)) == 0
        evidence = read_json(snapshot / ".humanvoice/inventory/inventory_result.json")
        owned = [row for row in evidence["coverage"] if "punctuation_ownership" in row]
        assert len(owned) == 1 and owned[0]["punctuation_ownership"]["raw_coverage"]["mapped_concept_ids"] == []
        raw = read_json(snapshot / ".humanvoice/inventory" / evidence["model_calls"][-1]["path"])
        assert any(row["mapped_concept_ids"] == [] for row in json.loads(raw["response_text"]))
        assert owned[0]["span_id"] in baseline.concept_entries[0].supporting_spans
        changed = deepcopy(evidence)
        next(row for row in changed["coverage"] if "punctuation_ownership" in row)["punctuation_ownership"]["owner_sha256"] = "changed"
        with pytest.raises(ValueError, match="summaries differ"):
            verify_inventory_semantics(snapshot, baseline, changed)


@pytest.fixture
def prefix(manuscript, monkeypatch, tmp_path):
    monkeypatch.setattr(continuation, "selected_profile", lambda: manuscript.codex.profile)
    with continuation.manuscript.accounted_model(manuscript.output, manuscript.plan, manuscript.ledger):
        invoke(manuscript, "completed")
    finish(manuscript)
    path = manuscript.output / "calls/0000/call.json"
    journal = read_json(path)
    manuscript.proof = {"prefix": [{"output": str(manuscript.output), "attempt": 0, "logical": 0,
        "request_hash": journal["request_hash"], "runtime_record": journal["runtime_record"], "call_sha256": digest(path.read_bytes())}]}
    manuscript.first = continuation.retained.canonical_request(manuscript.codex.adapter, ("next",),
        {"purpose": "concept_extraction", "response_schema": "extraction-response"})
    manuscript.replay_output = tmp_path / "replay"
    return manuscript


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_replay_preserves_receipts_and_calls_provider_only_after_prefix(prefix, monkeypatch):
    native, calls = ModelAdapter.invoke, []

    def observed(model, *arguments, **keywords):
        calls.append(continuation.retained.canonical_request(model, arguments, keywords))
        return native(model, *arguments, **keywords)

    monkeypatch.setattr(ModelAdapter, "invoke", observed)
    account = prefix.account.read_bytes()
    with continuation.replay(prefix.replay_output, prefix.plan, prefix.proof, first_request=prefix.first):
        response = invoke(prefix, "completed")
        assert response.runtime_record == prefix.proof["prefix"][0]["runtime_record"]
        assert not calls
        invoke(prefix, "next")
    assert calls == [prefix.first]
    assert prefix.account.read_bytes() == account
    assert read_json(prefix.replay_output / "replay-log.json")["new_requests"] == 1
    assert ModelAdapter.invoke is observed


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("defect", ["prefix", "first", "receipt", "source", "journal", "repeated"])
def test_changed_replay_inputs_refuse_provider_calls(prefix, monkeypatch, defect):
    calls = []

    def forbidden(*arguments, **keywords):
        calls.append(True)
        raise AssertionError("Unexpected new provider request")

    monkeypatch.setattr(ModelAdapter, "invoke", forbidden)
    if defect == "receipt":
        path = prefix.codex.snapshot / prefix.proof["prefix"][0]["runtime_record"]["path"]
        write_json(path.parent / "response.json", {"text": "changed"})
    elif defect == "source":
        (prefix.codex.snapshot / "source/main.tex").write_text("changed")
    elif defect == "journal":
        write_json(prefix.output / "calls/0000/call.json", {"changed": True})
    with pytest.raises((ValueError, KeyError)):
        with continuation.replay(prefix.replay_output, prefix.plan, prefix.proof, first_request=prefix.first):
            invoke(prefix, "changed" if defect == "prefix" else "completed")
            invoke(prefix, "changed" if defect == "first" else "completed" if defect == "repeated" else "next")
    assert not calls and ModelAdapter.invoke is forbidden


@pytest.mark.parametrize("defect", ["missing", "foreign", "spent"])
def test_lineage_rejects_changed_or_spent_stage(tmp_path, monkeypatch, defect):
    stage, lineage = tmp_path / "stage", tmp_path / "lineage.json"
    monkeypatch.setattr(continuation, "STAGE", stage)
    monkeypatch.setattr(continuation.manuscript, "lineage_for", lambda plan: lineage)
    claims = []
    monkeypatch.setattr(continuation, "claim", lambda *arguments, **keywords: claims.append(True))
    parent = {"plan_identity": "parent", "predecessor": "old"}
    if defect != "missing":
        write_json(lineage, {"plan_identity": "foreign" if defect == "foreign" else "parent", "output": "old"})
    if defect == "spent":
        write_json(stage / "execution.json", {"status": "nonpass"})
    with pytest.raises(ValueError):
        continuation.claim_lineage({"plan_identity": "child"}, parent)
    assert not claims


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_lineage_claim_uses_exact_plan_and_charges_only_new_requests(prefix, monkeypatch, tmp_path):
    from tools import automatic_program_account as account
    from tools.ensemble_closure_contract import AllocationLedger

    stage = tmp_path / "successor"
    monkeypatch.setattr(continuation, "STAGE", stage)
    monkeypatch.setattr(continuation.manuscript, "ACCOUNT", prefix.account)
    prior = read_json(prefix.account)["reservation_ceiling"]
    plan = continuation.manuscript.plan_for(prefix.codex.snapshot, "inventory", 2, prior, recovery=True)
    plan["inventory_coverage_repair"] = {"predecessor": str(prefix.output)}
    plan.pop("plan_identity")
    plan["plan_identity"] = digest(plan)
    write_json(stage / "plan.json", plan)
    proof = {**prefix.proof, "plan_identity": prefix.plan["plan_identity"], "predecessor": str(prefix.output)}
    write_json(continuation.manuscript.lineage_for(plan), {"plan_identity": prefix.plan["plan_identity"], "output": str(prefix.output)})
    before = prefix.account.read_bytes()
    continuation.claim_lineage(plan, proof, account=prefix.account)
    ledger = AllocationLedger(stage / "allocation-ledger.json", plan)
    with continuation.manuscript.accounted_model(stage, plan, ledger), continuation.replay(
            stage, plan, proof, first_request=prefix.first):
        invoke(prefix, "completed")
        assert len(ledger.record["calls"]) == 0
        invoke(prefix, "next")
    write_json(stage / "execution.json", {"status": "pass", "required": 2, "attempted": 1,
                                          "plan_identity": plan["plan_identity"]})
    usage = account.settle(stage, account=prefix.account)["usage"]
    assert usage["allocated_calls"] == 1 and usage["reported_tokens"] == 150
    assert read_json(prefix.output / "execution.json")["status"] == "nonpass"
    assert read_json(stage / "plan.json") == plan
    assert prefix.account.read_bytes() != before
    settled = prefix.account.read_bytes()
    with pytest.raises(ValueError, match="Spent or terminal"):
        continuation.claim_lineage(plan, proof, account=prefix.account)
    assert prefix.account.read_bytes() == settled


@pytest.mark.parametrize("defect", ["negative", "settlement", "terminal", "scope"])
def test_retained_predecessor_rejects_changed_proof_without_authority_mutation(monkeypatch, defect):
    native = continuation.read_json
    before = continuation.ACCOUNT.read_bytes()

    def read(path):
        value = native(path)
        if defect == "terminal" and path == continuation.PRIOR / "execution.json":
            value["status"] = "executing"
        elif defect == "scope" and path == continuation.PRIOR / "plan.json":
            value["profile"] = {"changed": True}
        elif defect == "settlement" and path == continuation.ACCOUNT:
            value["events"] = [event for event in value["events"] if event["kind"] != "settle"
                or event["usage"]["plan_identity"] != native(continuation.PRIOR / "plan.json")["plan_identity"]]
        elif defect == "negative" and path == continuation.PRIOR / "calls/0002/call.json":
            payload = json.loads(value["response_text"])
            payload[0]["verdict"] = "gap"
            value["response_text"] = json.dumps(payload)
        return value

    monkeypatch.setattr(continuation, "read_json", read)
    with continuation.inventory.history.archive.access(), continuation.inventory.scope.accounting_scope(), continuation.inventory.pipeline():
        with pytest.raises(ValueError):
            continuation.predecessor_evidence()
    assert continuation.ACCOUNT.read_bytes() == before


def test_controller_routes_only_zlb_inventory(monkeypatch):
    boundary = controller.previous.previous
    engine = boundary.identifier.previous.previous.previous.parallel.previous.engine
    prefix_module = engine.previous.previous.previous.previous.previous
    original_inventory, original_command = prefix_module.inventory, controller.scope.command
    calls = []
    monkeypatch.setattr(controller, "run_inventory", lambda *arguments: calls.append(arguments) or "repaired")

    def run():
        assert prefix_module.inventory("zlb", "snapshot", 540, "campaign", "refresh") == "repaired"
        command = controller.scope.command("verify-manuscript-boundary-20261007.py", "stage", "--phase", "test", "--next", "test")
        assert command[1] == str(controller.ROOT / "tools/inventory_coverage_runner.py")
        assert boundary.refresh is controller.refresh

    monkeypatch.setattr(boundary, "run", run)
    controller.run()
    assert calls == [("zlb", "snapshot", 540, "campaign", "refresh")]
    assert prefix_module.inventory is original_inventory and controller.scope.command is original_command
    assert controller.ACTIVE is False


def test_reproduction_dispatch_routes_and_restores(tmp_path, monkeypatch):
    module = runner.automatic_reproduction
    snapshot = tmp_path / "snapshot"
    write_json(snapshot / punctuation.MARKER, {})
    monkeypatch.setattr(punctuation, "policy", lambda source: {})
    command = [sys.executable, "-I", "-B", str(runner.ROOT / "tools/reproduction_overload_worker.py"), str(tmp_path / "worker")]
    monkeypatch.setattr(module, "_command", lambda *arguments: command)
    monkeypatch.setattr(module, "launch", lambda snapshot, output: module._command(output, True))
    native = module._command, module.launch
    with runner.reproduction_dispatch():
        assert module.launch(snapshot, tmp_path)[3] == str(runner.ROOT / "tools/inventory_coverage_worker.py")
        assert module.launch(tmp_path / "unrelated", tmp_path) == command
    assert (module._command, module.launch) == native


@pytest.mark.parametrize("changed", [False, True])
def test_separate_reproduction_verifier_uses_same_worker_as_launch(tmp_path, monkeypatch, changed):
    module = runner.automatic_reproduction
    snapshot = tmp_path / "snapshot"
    write_json(snapshot / punctuation.MARKER, {"policy": "changed"} if changed else {})
    monkeypatch.setattr(punctuation, "policy", lambda source: {})
    command = [sys.executable, "-I", "-B", str(runner.ROOT / "tools/reproduction_overload_worker.py"), str(tmp_path)]
    monkeypatch.setattr(module, "_command", lambda *arguments: command)
    monkeypatch.setattr(module, "launch", lambda snapshot, output: module._command(output, True))
    monkeypatch.setattr(module, "evaluate_reproduction", lambda root, **keywords: module._command(root, True))
    write_json(tmp_path / "request.json", {"manifest": {"snapshot_path": str(snapshot)}})
    before = module._command, module.launch, module.evaluate_reproduction
    with runner.reproduction_dispatch():
        if changed:
            with pytest.raises(ValueError, match="policy changed"):
                module.evaluate_reproduction(tmp_path)
        else:
            launched = module.launch(snapshot, tmp_path)
            verified = module.evaluate_reproduction(tmp_path)
            assert launched == verified and verified[3] == str(runner.ROOT / "tools/inventory_coverage_worker.py")
    assert (module._command, module.launch, module.evaluate_reproduction) == before
