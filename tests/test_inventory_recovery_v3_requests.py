"""Observe actual native prompts while preserving source ownership across replay."""

import shutil
import time
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest
from test_inventory_recovery_v3_owner import campaign
from test_inventory_recovery_v3_stage import (
    NATIVE_INVOKE,
    baseline,
    codex,
    exhausted,
    native_case,
)

from humanvoice import codex_runtime
from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.commands import inventory_command
from humanvoice.model import ModelAdapter
from tools.inventory_recovery_v2 import semantics
from tools.inventory_recovery_v3 import (
    dispatcher,
    execution,
    journal_binding,
    runtime,
    stage,
)
from tools.inventory_recovery_v3 import semantics as document_semantics
from tools.inventory_recovery_v3.reservations import RecoveryReservations
from tools.inventory_recovery_v3.stage_authority import CampaignAuthority
from tools.inventory_recovery_v3.stage_owner import owned_stage

__all__ = ["baseline", "codex", "exhausted", "native_case"]


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_consumer_derives_critic_ownership_from_retained_extraction(exhausted, tmp_path, monkeypatch):
    current = stage.Stage(tmp_path / "successor", exhausted.transition)
    plan = current.prepare()
    journal = RecoveryReservations(tmp_path / "pairs", plan[runtime.FIELD]["policy"], {
        "document": plan["bindings"]["source"], "migration": plan[runtime.FIELD]["migration_identity"],
        "authority": "offline-fixture"})
    journal.initialize()
    before = exhausted.output / "allocation-ledger.json"
    original_bytes = before.read_bytes()

    def respond(model, **keywords):
        request = execution.predecessor.retained.canonical_request(model, (), keywords)
        if request == execution.CANARY:
            write_json(exhausted.codex.settings, {"response": []})
            return NATIVE_INVOKE(model, **keywords)
        return exhausted.response(model, **keywords)

    monkeypatch.setattr(ModelAdapter, "invoke", respond)
    actual_time, offset = time.time, [exhausted.clock_offset]

    class ReceiptClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(time.time(), tz)

    native_wait = dispatcher.network.wait_until

    def wait(path, identity, failed_at, **keywords):
        offset[0] += max(0, failed_at + 900 - time.time())
        return native_wait(path, identity, failed_at, clock=time.time)

    monkeypatch.setattr(time, "time", lambda: actual_time() + offset[0])
    monkeypatch.setattr(codex_runtime, "datetime", ReceiptClock)
    monkeypatch.setattr(dispatcher.network, "wait_until", wait)
    native_dispatch = journal.dispatch

    def dispatch(*arguments, **keywords):
        return native_dispatch(*arguments, **keywords, clock=time.time)

    monkeypatch.setattr(journal, "dispatch", dispatch)
    prepared = exhausted.codex, exhausted.account, plan, current.output, exhausted.transition["proof"]["failed_request"]
    with campaign(prepared, tmp_path / "campaign", monkeypatch, retained_grant=exhausted.grant,
                  recovery_journal=journal_binding.descriptor(journal)) as fixture, (
            runtime.settlement_scope()):
        authority = CampaignAuthority(fixture.implementation, **fixture.arguments)
        with owned_stage(current.output, plan, authority=authority) as (owner, ledger, _reservation), (
                document_semantics.transition_runtime(exhausted.transition)) as observations, dispatcher.accounted_model(
                    current.output, plan, ledger, journal=journal, owner=owner), current.replay(
                    plan, current.output, exhausted.transition["proof"], codex_runtime.validate_codex_record) as checked, (
                runtime.runtime(plan, current.output, live=True, owner=owner, historical_validate=checked)), (
                semantics.context.runtime()):
            assert inventory_command.run(SimpleNamespace(
                snapshot=current.snapshot, freeze=True, mock=False, timeout=900)) == 0
            assert execution.layout(current.output, plan, ledger.record["calls"])["logical"] == 2
            assert len(ledger.record["calls"]) == 3
            ownership = [read_json(path) for path in sorted((current.output / "request-lineages").glob("*.json"))]
            assert [row["source_scope"]["purpose"] for row in ownership] == [
                "reconstruction_verification", "coverage_verification"]
            assert ownership[0]["source_scope"]["window"] == ownership[1]["source_scope"]["window"]
            assert len(journal.read()["lineages"]) == 3
            assert len(journal.read()["inherited_recovery"]["sequences"]) == 2
            assert read_json(current.output / "replay-log.json")["inherited"] == exhausted.transition["proof"]["prefix"]
            from tools.inventory_recovery_v3.requests import NativeRequests

            resolver = NativeRequests(plan, current.output, journal, owner)
            retained = journal.path.read_bytes()
            last = observations["observations"][-1]
            assert resolver.resolve(1, last["request"]) == ownership[1]["lineage"]
            for change in ("request", "owned", "source", "depth"):
                altered = deepcopy(last)
                if change == "request":
                    altered["request"]["prompt"] += " changed"
                elif change == "owned":
                    altered["owned"] = ["foreign"]
                elif change == "source":
                    altered["context"]["spans"][0]["exact_text"] = "changed"
                else:
                    altered["depth"] += 1
                observations["observations"][-1] = altered
                with pytest.raises((ValueError, RuntimeError)):
                    resolver.resolve(1, last["request"])
            observations["observations"][-1] = last
            assert journal.path.read_bytes() == retained
            write_json(current.output / "execution.json", {"status": "nonpass", "plan_identity": plan["plan_identity"],
                "required": 2, "attempted": 3})
        usage = stage.bridge.original.account.settle(current.output, account=exhausted.account)["usage"]
        assert usage["allocated_calls"] == 3 and usage["retained_tokens"] == 3 * 544000
        assert current.validate() == plan
    assert before.read_bytes() == original_bytes


def test_inherited_split_keeps_depth_without_consuming_new_expansion(tmp_path):
    from test_inventory_recovery_v3_policy import reservations

    journal = reservations(tmp_path, split_allowance=0)
    root = journal.register_root(purpose="concept_extraction", owned=["one", "two", "three"])
    children = journal.inherit_split(root["identity"], [["one"], ["two", "three"]], evidence="source-rule")
    assert journal.inherit_split(root["identity"], [["one"], ["two", "three"]], evidence="source-rule") == children
    assert children[0]["depth"] == 1 and children[0]["root"] == root["identity"]
    assert journal.read()["splits"][root["identity"]]["extra_calls"] == 0
    before = journal.path.read_bytes()
    with pytest.raises(RuntimeError, match="ancestry"):
        journal.inherit_split(root["identity"], [["one"], ["two", "three"]], evidence="foreign")
    with pytest.raises(RuntimeError, match="expansion"):
        journal.split(children[1]["identity"], [["two"], ["three"]])
    assert journal.path.read_bytes() == before
    assert digest(journal.read()["lineages"][root["identity"]]) == digest(root)


@pytest.mark.parametrize("change", ["metadata", "source", "membership", "depth", "request"])
def test_repeated_extraction_import_binds_immutable_observation(tmp_path, change):
    from dataclasses import asdict

    from test_inventory_recovery_v3_inheritance import history_for
    from test_inventory_recovery_v3_policy import reservations
    from test_inventory_size_recovery import source_rows

    from tools.inventory_recovery_v3.requests import NativeRequests

    window, spans = source_rows(["First. ", "Second."])
    journal = reservations(tmp_path / "pairs", root_sequences=12)
    resolver = object.__new__(NativeRequests)
    resolver.output, resolver.spans = tmp_path / "output", spans
    resolver.journal, resolver.owner = journal, SimpleNamespace(check=lambda: True)
    resolver.size_rules, resolver.rules = [], []
    request = {"prompt": "historical-0", "purpose": "concept_extraction"}
    observation = {"purpose": "concept_extraction", "request": request,
                   "window": asdict(window), "spans": spans, "depth": 0}
    root, _scope = resolver.extraction(observation)
    history, _mapping, handoff = history_for(journal, [root])
    resolver.plan = {"plan_identity": "fixture", runtime.FIELD: {"transition": {
        "recovery_history": history, "diagnostic_handoff": handoff}}}
    altered = deepcopy(observation)
    if change == "metadata":
        for span in altered["spans"].values():
            span["created_at"] = "regenerated"
    elif change == "source":
        next(iter(altered["spans"].values()))["exact_text"] += "changed"
    elif change == "membership":
        altered["window"]["span_ids"].reverse()
    elif change == "depth":
        altered["depth"] += 1
    else:
        altered["request"]["prompt"] += "changed"
    resolver.import_history([observation])
    before = journal.path.read_bytes()
    if change == "metadata":
        resolver.import_history([observation, altered])
        with semantics.runtime() as active:
            active["observations"][:] = [observation]
            identity = resolver.resolve(0, request)
            path = resolver.output / "request-lineages/0000.json"
            ownership = path.read_bytes()
            active["observations"][:] = [altered]
            assert resolver.resolve(0, request) == identity
            assert path.read_bytes() == ownership
    else:
        selected = [altered] if change == "request" else [observation, altered]
        with pytest.raises(RuntimeError, match="native observation|native context"):
            resolver.import_history(selected)
    assert journal.path.read_bytes() == before


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("marked", [False, True])
@pytest.mark.parametrize("purpose", ["reconstruction_verification", "coverage_verification"])
@pytest.mark.parametrize("versioned", [False, True])
def test_actual_semantic_extraction_and_critic_split_ancestry(native_case, tmp_path, monkeypatch, marked, purpose, versioned):
    from test_failure_first_semantics import retained_failure
    from test_inventory_recovery_v3_policy import policy, reservations

    from tools.inventory_recovery_v3 import semantics as document_semantics
    from tools.inventory_recovery_v3.requests import NativeRequests

    selected_semantics = document_semantics if versioned else semantics
    options = {"policy": policy(split_allowance=10), "inherited": []} if versioned else {}
    native_case.fail_at = -1
    if not marked:
        (native_case.snapshot / semantics.context.MARKER).unlink()
    clean = tmp_path / "clean"
    shutil.copytree(native_case.snapshot, clean)
    rules, failures = [], {}
    native_validate = selected_semantics.validate_rules
    monkeypatch.setattr(selected_semantics, "validate_rules", lambda selected, verify_failure=failures.__getitem__, **keywords:
                        native_validate(selected, verify_failure=failures.__getitem__, **keywords))

    def discover(snapshot, selected):
        with selected_semantics.runtime(selected, verify_failure=failures.__getitem__, **options) as observed, semantics.context.runtime():
            assert inventory_command.run(SimpleNamespace(snapshot=snapshot, freeze=True, mock=False, timeout=900)) == 0
        return observed

    observed = discover(native_case.snapshot, rules)
    extraction = next(row for row in observed["observations"] if row["purpose"] == "concept_extraction")
    failed = retained_failure(extraction, 0)
    failures[failed["output"]] = failed
    rules.append(selected_semantics.rule(extraction, failed))
    middle = tmp_path / "middle"
    shutil.copytree(clean, middle)
    observed = discover(middle, rules)
    critic = next(row for row in observed["observations"] if row["purpose"] == purpose)
    failed = retained_failure(critic, 1)
    failures[failed["output"]] = failed
    rules.append(selected_semantics.rule(critic, failed))
    nested = tmp_path / "nested"
    shutil.copytree(clean, nested)
    observed = discover(nested, rules)
    child = next((row for row in observed["observations"] if row["purpose"] == purpose
                  and row["depth"] == 1 and len(row["owned"]) >= 2), None)
    if child is not None:
        failed = retained_failure(child, 2)
        failures[failed["output"]] = failed
        rules.append(selected_semantics.rule(child, failed))
    target = tmp_path / "target"
    shutil.copytree(clean, target)
    shutil.copy2(native_case.snapshot / ".humanvoice/inventory/spans.jsonl", target / ".humanvoice/inventory/spans.jsonl")
    journal = reservations(tmp_path / "pairs", split_allowance=10 if versioned else 0)
    plan = {"snapshot": str(target), "plan_identity": "fixture", runtime.FIELD: {"split_rules": rules}}
    if versioned:
        plan[runtime.FIELD].update(semantic_version=document_semantics.VERSION,
                                   policy=options["policy"], inherited_rules=[])
    owner = SimpleNamespace(check=lambda: True)
    resolver = NativeRequests(plan, tmp_path / "output", journal, owner)
    native = ModelAdapter.invoke
    resolved = []

    def invoke(model, **keywords):
        request = execution.predecessor.retained.canonical_request(model, (), keywords)
        identity = resolver.resolve(len(resolved), request)
        def misplaced(*arguments, **keywords):
            raise AssertionError("Historical rule validation entered a prospective receipt scope")

        with monkeypatch.context() as scoped:
            scoped.setattr(selected_semantics, "validate_rules", misplaced)
            restarted = NativeRequests(plan, tmp_path / "output", journal, owner)
            assert restarted.resolve(len(resolved), request) == identity
            changed = deepcopy(plan)
            changed[runtime.FIELD]["split_rules"] = []
            with pytest.raises(RuntimeError, match="validated semantic rules"):
                NativeRequests(changed, tmp_path / "output", journal, owner)
        resolved.append(identity)
        return native(model, **keywords)

    monkeypatch.setattr(ModelAdapter, "invoke", invoke)
    discover(target, rules)
    record = journal.read()
    assert sum(row["extra_calls"] for row in record["splits"].values()) == (len(rules) if versioned else 0)
    critic_children = [record["lineages"][identity] for identity in resolved
                       if record["lineages"][identity]["purpose"] == purpose]
    assert len(critic_children) >= 2
    assert all(row["depth"] >= 1 for row in critic_children)
    assert len({row["root"] for row in critic_children}) == 1


@pytest.mark.parametrize("marked", [False, True])
def test_overlapping_windows_do_not_import_other_critic_rules(tmp_path, monkeypatch, marked):
    from dataclasses import asdict, replace

    from test_failure_first_semantics import retained_failure
    from test_inventory_recovery_v3_policy import reservations
    from test_inventory_size_recovery import source_rows

    from humanvoice.concept_extraction import ConceptCandidate
    from humanvoice.model_extraction import CoverageVerdict, ExtractionResult
    from tools.inventory_recovery_v3.requests import NativeRequests

    window, spans = source_rows(["First. ", "Shared one. ", "Shared two. ", "Last."])
    first_window = replace(window, span_ids=list(spans)[:3])
    second_window = replace(window, window_id="window-0001", span_ids=list(spans)[1:])
    models, outputs = [object(), object()], []
    scopes = []
    for selected, model in zip((first_window, second_window), models, strict=True):
        if marked:
            import json

            suffix = "\n\nInventory context request: " + json.dumps({"policy": semantics.context.VERSION,
                "window": selected.window_id, "source_file": "main.tex", "repair_round": 0})
            model = semantics.context.PromptModel(model, suffix)
        scopes.append(model)
    concepts = [[ConceptCandidate("same", label, "claim", list(spans)[1:3])] for label in ("First context", "Second context")]

    def extracted(selected, *arguments):
        index = int(selected.window_id[-1])
        return ExtractionResult(selected.span_ids[0], concepts[index])

    resolvers = []

    def covered(rows, candidates, model, macro_display=None):
        if resolvers:
            observation = semantics.ACTIVE.get()["observations"]["observations"][-1]
            outputs.append(resolvers[0].resolve(len(outputs), observation["request"]))
        return [CoverageVerdict(row["record_id"], "covered", "Bound fixture.", ["same"]) for row in rows]

    monkeypatch.setattr(semantics.model_extraction, "extract_concepts_from_window", extracted)
    monkeypatch.setattr(semantics.model_extraction, "verify_coverage", covered)

    def run(index):
        selected = (first_window, second_window)[index]
        semantics.model_extraction.extract_concepts_from_window(selected, {}, scopes[index], None,
            span_texts={key: spans[key]["exact_text"] for key in selected.span_ids},
            span_index={key: spans[key] for key in selected.span_ids})
        return semantics.model_extraction.verify_coverage(list(spans.values())[1:3], concepts[index], scopes[index])

    with semantics.runtime() as discovered:
        run(0)
    observed = discovered["observations"][-1]
    failure = retained_failure(observed, 0)
    rule = semantics.rule(observed, failure)
    journal = reservations(tmp_path / "pairs", split_allowance=0)
    resolver = object.__new__(NativeRequests)
    resolver.plan = {"plan_identity": "fixture", runtime.FIELD: {"split_rules": [rule]}}
    resolver.output, resolver.spans = tmp_path / "output", spans
    resolver.journal, resolver.owner = journal, SimpleNamespace(check=lambda: True)
    resolver.size_rules, resolver.rules = [], [rule]
    resolvers.append(resolver)
    with semantics.runtime([rule], verify_failure=lambda root: failure):
        run(0)
        run(1)
    lineages = journal.read()["lineages"]
    assert [lineages[identity]["depth"] for identity in outputs] == [1, 1, 0]
    assert lineages[outputs[0]]["root"] == lineages[outputs[1]]["root"]
    assert lineages[outputs[0]]["root"] != lineages[outputs[2]]["root"]
    assert rule["recipe"]["context"]["concepts"] == [asdict(concepts[0][0])]
