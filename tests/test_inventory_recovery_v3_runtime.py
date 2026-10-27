"""Document policy isolation and frozen native attempt membership."""

from copy import deepcopy

import pytest
from test_failure_first_native import baseline, codex, prepared

from humanvoice import automatic_recovery, codex_runtime
from humanvoice.artifacts import digest, write_json
from tools.inventory_recovery_v2 import execution as historical_execution
from tools.inventory_recovery_v2 import runtime as historical
from tools.inventory_recovery_v3 import execution, runtime
from tools.inventory_recovery_v3.native_dispatch import modules
from tools.inventory_recovery_v3.policy import proposal

__all__ = ["baseline", "codex", "prepared"]


def document_plan(template, **changes):
    document = proposal(**{"remaining_requests": len(template["calls"]), "inherited_recovery": 17,
        "incident_allowance": 32, "split_allowance": 32, "qualification_calls": 0,
        "available_calls": 600, "available_tokens": 326400000, **changes})
    return runtime.bind_plan(template, document, parent_failure=template[historical.FIELD]["parent_failure"],
                             inherited_recovery=document["inherited_recovery"], migration_identity="fixture")


def rehash(plan):
    plan["plan_identity"] = digest({key: value for key, value in plan.items() if key != "plan_identity"})
    return plan


def test_document_policy_retains_seventeen_charges_without_relabeling_history(prepared):
    _codex, _account, template, output, _request = prepared
    original = deepcopy(template)
    historical_contract = historical.contract()
    plan = document_plan(template)
    assert plan[runtime.FIELD]["policy"]["recovery_ceiling"] == 113
    assert plan["recovery"]["maximum_total"] == 96
    assert plan["recovery"]["maximum_per_case"] == 6
    assert automatic_recovery.call_limit(plan) == len(plan["calls"]) + 96
    assert execution.layout(output, plan, [])["logical"] == 0
    assert modules(plan) == (execution, runtime)
    assert modules(template) == (historical_execution, historical)
    assert historical.validate_plan(template) == original
    with pytest.raises(ValueError):
        historical.validate_plan(plan)
    with runtime.runtime(plan, output):
        assert automatic_recovery.attempt_layout(output, plan, [])["mode"] == "canary"
    assert historical.contract() == historical_contract
    assert template == original


@pytest.mark.parametrize("field,value", [("inherited", 16), ("inherited", True), ("inherited", -1),
    ("inherited", 114), ("total", 97), ("per_case", 100), ("deadline", 901),
    ("backoff", 0), ("migration", ""), ("profile", "foreign"), ("source", "foreign"),
    ("eligible_after", float("inf")), ("eligible_after", 899), ("calls", "duplicate"),
    ("calls", "hash"), ("historical", True)])
def test_rehashed_stage_mutations_are_rejected(prepared, field, value):
    plan = document_plan(prepared[2])
    marker = plan[runtime.FIELD]
    if field == "inherited":
        marker["recovery_sessions_used"] = value
    elif field in {"total", "per_case", "deadline", "backoff"}:
        plan["recovery"][{"total": "maximum_total", "per_case": "maximum_per_case",
                          "deadline": "deadline_seconds", "backoff": "backoff_seconds"}[field]] = value
    elif field == "eligible_after":
        marker["parent_failure"][field] = value
    elif field == "calls":
        if value == "duplicate":
            plan["calls"][1] = deepcopy(plan["calls"][0])
        else:
            plan["calls"][0]["input_hash"] = "foreign"
    elif field == "historical":
        plan[historical.FIELD] = deepcopy(prepared[2][historical.FIELD])
    else:
        marker[{"migration": "migration_identity", "profile": "profile_hash", "source": "source_hash"}[field]] = value
    with pytest.raises((ValueError, TypeError)):
        runtime.validate_plan(rehash(plan))


@pytest.mark.parametrize("defect", ["none", "repeat", "foreign_hash", "wrong_role", "wrong_incident", "early_wait"])
def test_unknown_tail_requires_exact_canary_membership(prepared, defect):
    plan = document_plan(prepared[2])
    output = prepared[3]
    incident = plan[runtime.FIELD]["parent_failure"]
    index = len(plan["calls"])
    call = automatic_recovery.attempt_calls(plan)[index]
    entry = {"key": call["key"], "input_hash": call["input_hash"],
             "invocation_id": "native-id", "status": "allocated_unknown"}
    descriptor = {"plan_identity": plan["plan_identity"], "logical": 0, "index": index,
        "kind": "canary", "request": execution.CANARY, "request_hash": digest(execution.CANARY),
        "incident_hash": digest(incident)}
    wait = {"failure_hash": digest(incident), "eligible_after": incident["eligible_after"],
        "failed_at": incident["eligible_after"] - 900, "backoff_seconds": 900,
        "status": "eligible", "observed_at": incident["eligible_after"]}
    if defect == "foreign_hash":
        entry["input_hash"] = "foreign"
    elif defect == "wrong_role":
        descriptor["kind"] = "request"
    elif defect == "wrong_incident":
        descriptor["incident_hash"] = "foreign"
    elif defect == "early_wait":
        wait["observed_at"] -= 1
    write_json(output / f"reconnect-attempts/{index:04d}.json", descriptor)
    write_json(output / "reconnect-waits" / (digest(incident) + ".json"), wait)
    if defect == "none":
        state = execution.layout(output, plan, [entry])
        assert state["mode"] == "ambiguous" and state["pending"] == index
        assert state["recoveries"] == 1 and state["selected"] == {}
    else:
        with pytest.raises(ValueError):
            execution.layout(output, plan, [entry, entry] if defect == "repeat" else [entry])


def test_unreviewed_live_runtime_remains_closed(prepared):
    plan = document_plan(prepared[2])
    with pytest.raises(ValueError, match="reviewed paired"), runtime.runtime(plan, prepared[3], live=True, lock_fd=3):
        pytest.fail("Unadmitted runtime launched")


@pytest.mark.parametrize("capture", [None, "older", "current"])
def test_receipt_dispatch_preserves_capture_contract_and_prefix_membership(tmp_path, monkeypatch, capture):
    folder = tmp_path / ".humanvoice/runtime/retained"
    reference = {"path": ".humanvoice/runtime/retained/record.json", "hash": "retained-receipt"}
    profile = {"identity": "original-profile"}
    write_json(folder / "inputs/api-request.json", {"profile": profile})
    if capture is not None:
        write_json(folder / "qualification-capture.json", {
            "contract": runtime.contract() if capture == "current" else {"version": "older"}})
    called = []

    def native(root, selected, **keywords):
        called.append("current")
        return "current-validated"

    def historical_validator(root, selected, original_profile):
        if root != tmp_path or selected != reference or original_profile != profile:
            raise ValueError("Receipt is not in the exact retained prefix")
        called.append("historical")
        return "historical-validated"

    monkeypatch.setattr(codex_runtime, "validate_codex_record", native)
    with runtime.receipt_scope(historical_validator):
        expected = "current" if capture == "current" else "historical"
        assert codex_runtime.validate_codex_record(tmp_path, reference) == expected + "-validated"
        assert called == [expected]
        if capture != "current":
            with pytest.raises(ValueError, match="exact retained prefix"):
                codex_runtime.validate_codex_record(tmp_path, {**reference, "hash": "foreign"})
    if capture != "current":
        with runtime.receipt_scope(None), pytest.raises(ValueError, match="exact retained receipt"):
            codex_runtime.validate_codex_record(tmp_path, reference)
