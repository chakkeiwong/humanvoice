"""Oversized complete reviews split without rerolls or lost obligations."""

import json
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace

import pytest
import test_codex_runtime
from test_assembled_budget_runtime import authorized
from live_admission_fixture import responder

from humanvoice import assembled_review, codex_runtime
from humanvoice.artifacts import digest, read_json, write_json
from humanvoice.commands import preflight_v2_command
from tools import assembled_budget_runtime as budget
from tools import assembled_size_recovery as recovery
from tools import reproduction_review_size_recovery as continuation
from tools.inventory_transport_continuation import canonical_request

codex = test_codex_runtime.codex


def review_job(count=8):
    concepts = [{"concept_id": f"concept-{number}", "proposition": f"Claim {number}",
                 "required_functions": ["definition", "mechanism"],
                 "prerequisites": [f"concept-{number - 1}"] if number else [],
                 "qualifications": ["Source qualification"]} for number in range(count)]
    job = {"source": "Entire source with cross-boundary relationships.",
           "candidate": "Entire candidate with cross-boundary relationships.",
           "concepts": concepts, "scope": "complete assembled candidate"}
    job["prompt"] = assembled_review.assembled_prompt(job["source"], job["candidate"], concepts,
                                                       {}, "main.tex", job["scope"])
    return job


def test_partition_preserves_full_context_and_exact_obligations():
    job = review_job()
    children = recovery.partition(job, digest(job["prompt"]), 0)
    assert [row for child in children for row in child["concepts"]] == job["concepts"]
    assert all(child[key] == job[key] for child in children for key in ("source", "candidate"))
    assert children == recovery.partition(job, digest(job["prompt"]), 0)
    assert all(child["prompt"] != job["prompt"] for child in children)


@pytest.mark.parametrize("count,depth", [(1, 0), (8, 3), (8, -1)])
def test_partition_stops_at_indivisible_or_depth_limit(count, depth):
    with pytest.raises(ValueError, match="indivisible"):
        recovery.partition(review_job(count), "root", depth)


def test_classifier_rejects_non_size_or_incomplete_failures():
    request = {"purpose": "assembled_candidate_verification", "response_schema": "critic-response",
               "profile": {"budget": {"max_input_tokens_per_unit": 60000}},
               "assembled_input_budget": {"authorized_input_limit": 80000},
               "output_acceptance_limit": 32000, "reservation_tokens": 544000, "timeout_seconds": 900}
    response = {"status": "error", "failure_kind": "invocation", "error": recovery.ERROR,
                "usage_status": "reported", "text": "native response", "thread_id": "thread",
                "input_tokens": 76106, "output_tokens": 40963}
    process = {"status": "complete", "returncode": 0, "process_started": True,
               "elapsed_seconds": 480, "deadline_seconds": 900}
    assert recovery.classify(request, response, process, [])["semantic_check"] == "pass"
    for changes in ({"text": ""}, {"output_tokens": 32000}, {"input_tokens": 544000},
                    {"error": "timeout"}, {"input_tokens": True}):
        with pytest.raises(ValueError, match="solely"):
            recovery.classify(request, response | changes, process, [])
    with pytest.raises(ValueError, match="solely"):
        recovery.classify(request, response, process | {"status": "timeout"}, [])


def test_review_recovery_preserves_remaining_network_allowance():
    assert continuation.bounds(27, 15, 5, 10) == {"remaining_calls": 179,
        "remaining_transport_extras": 5, "remaining_roots": 11,
        "retained_assembled_reviews": 15, "root_windows": 27}
    with pytest.raises(ValueError):
        continuation.bounds(27, 15, 11, 10)


def test_runtime_restores_aliases_and_its_own_wrappers():
    originals = (assembled_review.assembled_windows, budget.require_review, recovery.accounting.attempt_layout)
    wrappers = (recovery.windows, recovery.require_review, recovery.attempt_layout)
    for _ in range(2):
        with recovery.runtime():
            assert assembled_review.assembled_windows is wrappers[0]
            assert budget.require_review is wrappers[1]
            assert recovery.accounting.attempt_layout is wrappers[2]
        assert originals == (assembled_review.assembled_windows, budget.require_review, recovery.accounting.attempt_layout)
        assert wrappers == (recovery.windows, recovery.require_review, recovery.attempt_layout)


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("recursive,reject,accounted,transport", [
    (False, False, False, False), (True, False, False, False), (False, True, False, False),
    (False, False, True, False), (True, False, True, False), (False, True, True, False),
    (False, False, True, True),
])
def test_native_review_splits_preserve_receipts_and_cached_reviews(codex, authorized, monkeypatch, recursive, reject, accounted, transport):
    job = review_job()
    files = {"source_files": {"main.tex": digest(job["source"])},
             "candidate_files": {"main.tex": digest(job["candidate"])}}
    native_review, native_layout = recovery.NATIVES[1:]
    root_windows = lambda *args: ([job], files)
    monkeypatch.setattr(assembled_review, "assembled_windows", root_windows)
    monkeypatch.setattr(recovery, "NATIVES", (root_windows, native_review, native_layout))
    monkeypatch.setattr(preflight_v2_command, "ModelAdapter", lambda *args, **kwargs: codex.adapter)
    monkeypatch.setattr("humanvoice.ensemble.require_snapshot_ensemble", lambda *args: None)
    monkeypatch.setattr("humanvoice.finding_records.assembled_findings", lambda *args, **kwargs: {"synthetic": True})
    budget.install(codex.snapshot, authorized[0])
    recovery.install(codex.snapshot)
    native_launch, calls, waits = codex_runtime.launch, [], []

    def launch(arguments, prompt, directory, timeout):
        data = json.loads(prompt.split("REVIEW_DATA:\n", 1)[1])
        calls.append(digest(prompt))
        response = json.loads(responder(codex.snapshot, {"messages": [{"content": prompt}]}))
        oversized = len(data["concepts"]) > (2 if recursive else 4)
        if reject:
            response.update(additions_verdict="contradicted", unsupported_additions=["Unjustified claim"])
        settings = {"response": response, "output_tokens": 40963 if oversized else 100}
        if transport and len(calls) in {1, 3}:
            settings["transport_failures"] = [{"purpose": "assembled_candidate_verification",
                "message": recovery.accounting.network.DIAGNOSTIC}]
        write_json(codex.settings, settings)
        return native_launch(arguments, prompt, directory, timeout)

    monkeypatch.setattr(codex_runtime, "launch", launch)
    monkeypatch.setattr(recovery.accounting.network, "wait_until", lambda *arguments: waits.append(arguments))
    with ExitStack() as stack:
        if accounted:
            from humanvoice import automatic_reproduction
            from tools import automatic_manuscript_stage as manuscript
            from tools.ensemble_closure_contract import AllocationLedger

            accounting = recovery.accounting
            monkeypatch.setattr(manuscript, "selected_profile", lambda: codex.profile)
            stack.enter_context(accounting.network.pipeline(planning=[(codex.snapshot, "humanize")],
                snapshots=[codex.snapshot], authorization=authorized[0]))
            stack.enter_context(accounting.runtime.runtime_extension())
            stack.enter_context(accounting.accounting_extension())
            plan = manuscript.plan_for(codex.snapshot, "humanize", 15, 0, recovery=True)
            plan.update(writer_size_extension=accounting.runtime.extension(), assembled_size_extension=recovery.extension())
            plan.pop("plan_identity")
            plan["plan_identity"] = digest(plan)
            output = codex.snapshot.parent / "review-accounting"
            ledger = AllocationLedger(output / "allocation-ledger.json", plan)
            stack.enter_context(accounting.accounted_model(output, plan, ledger))
        else:
            stack.enter_context(budget.runtime_extension())
        stack.enter_context(recovery.runtime())
        if reject:
            with pytest.raises(ValueError, match="substantive"):
                recovery.require_review(codex.snapshot, {"bindings": {}}, None, codex.snapshot)
            assert len(calls) == 1
            assert not list((codex.snapshot / recovery.DIRECTORY).glob("splits/*.json"))
            return
        result = recovery.require_review(codex.snapshot, {"bindings": {}}, None, codex.snapshot)
        assert len(result["windows"]) == (4 if recursive else 2)
        expected = 7 if recursive else 3
        assert len(set(calls)) == expected
        assert len(calls) == expected + (2 if transport else 0)
        assert len(waits) == (2 if transport else 0)
        if transport:
            assert calls[0] == calls[1] and calls[2] == calls[3] and calls[1] != calls[2]
        assert result == recovery.require_review(codex.snapshot, {"bindings": {}}, None, codex.snapshot, allow_calls=False)
        assert len(calls) == expected + (2 if transport else 0)
        proof = read_json(recovery.split_path(codex.snapshot, job))
        assert proof["failure"]["original_response_admitted"] is False
        assert codex_runtime.validate_codex_record(codex.snapshot, proof["failure"]["runtime_record"])["termination"] == "error"
        leaf = recovery.leaves(codex.snapshot, job)[0]
        request = canonical_request(None, (), {"prompt": leaf["prompt"], "purpose": "assembled_candidate_verification",
            "response_schema": "critic-response"})
        assert recovery.child_token(codex.snapshot, request)["root"] == digest(job["prompt"])
        assert recovery.child_token(codex.snapshot, request | {"prompt": request["prompt"] + " "}) is None
        if accounted:
            ledger.reload()
            layout = recovery.attempt_layout(output, plan, ledger.record["calls"])
            assert layout["child_calls"] == (6 if recursive else 2)
            assert len(layout["selected"]) == len(result["windows"])
            assert len(layout["failures"]) == (3 if recursive else 1) + (2 if transport else 0)
            assert layout["recoveries"] == (2 if transport else 0)
            assert all(entry["usage"] is None and entry["reservation"] == 544000
                       for entry in ledger.record["calls"] if entry["status"] == "incomplete")
            calls = [{"journal": read_json(output / f"calls/{index:04d}/call.json"),
                      "result": read_json(output / f"calls/{index:04d}/result.json")} for index in layout["indices"]]
            root = output / "reproduction"
            write_json(root / "master-accounting-calls.json", {"plan_identity": plan["plan_identity"],
                "ledger": ledger.record, "calls": calls})
            import shutil

            shutil.copytree(codex.snapshot, root / "replica")
            fresh = {row["journal"]["runtime_record"]["path"].split("/")[-2] for row in calls}
            assert automatic_reproduction.validate_accounted_calls(root, plan, fresh)["calls"] == calls


def test_inherited_split_does_not_retry_unrelated_error(tmp_path, monkeypatch):
    recovery.install(tmp_path)
    calls = []

    def failing(*args, **kwargs):
        calls.append(1)
        write_json(tmp_path / recovery.DIRECTORY / "splits/old.json", {})
        raise RuntimeError("unrelated failure")

    monkeypatch.setattr(recovery, "NATIVES", (recovery.NATIVES[0], failing, recovery.NATIVES[2]))
    monkeypatch.setattr(recovery, "windows", lambda *args: ([], {}))
    with pytest.raises(RuntimeError, match="unrelated failure"):
        recovery.require_review(tmp_path, None, None, None)
    assert calls == [1]
