"""Read document-budget stages without changing frozen historical policies."""

import importlib.util
import math
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import FunctionType

from humanvoice import automatic_recovery, automatic_settlement, codex_runtime
from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v2 import runtime as historical
from tools.inventory_recovery_v3 import schema_replay
from tools.inventory_recovery_v3.policy import integer, require_capacity

FIELD = "inventory_document_recovery"
VERSION = "inventory-document-runtime-v3"
ROOT = Path(__file__).resolve().parents[2]
specification = importlib.util.spec_from_file_location("tools._document_recovery_runtime", historical.__file__)
bridge = importlib.util.module_from_spec(specification)
specification.loader.exec_module(bridge)
implementation = bridge.implementation
settlement_specification = importlib.util.spec_from_file_location(
    "humanvoice._document_native_settlement", automatic_settlement.__file__)
settlement_source = importlib.util.module_from_spec(settlement_specification)
settlement_specification.loader.exec_module(settlement_source)
native_usage = FunctionType(settlement_source.completed_usage.__code__, automatic_settlement.__dict__,
                            argdefs=settlement_source.completed_usage.__defaults__)
native_usage.__kwdefaults__ = settlement_source.completed_usage.__kwdefaults__
NATIVE_USAGE = (native_usage,)
HISTORICAL_CONSERVATIVE = (historical.conservative_usage,)


def contract():
    return {"version": VERSION, "historical": historical.contract(),
            "files": {str(path.relative_to(ROOT)): digest(path.read_bytes())
                      for path in sorted((ROOT / "tools/inventory_recovery_v3").glob("*.py"))},
            "historical_eligibility_changed": False, "semantic_reroll": False,
            "backoff_seconds": 900, "provider_calls_sequential": True}


def policy(document, inherited):
    require_capacity(document)
    integer(inherited, "inherited recovery")
    if not document["inherited_recovery"] <= inherited <= document["recovery_ceiling"]:
        raise ValueError("Stage cannot renew or exceed document recovery authority")
    remaining = document["recovery_ceiling"] - inherited
    return {**historical.NATIVE_POLICY(), "version": VERSION,
            "maximum_total": remaining,
            "maximum_per_case": min(remaining, 2 * document["lineage_sequences"])}


def validate_plan(plan):
    marker = plan.get(FIELD, {})
    document = require_capacity(marker["policy"])
    inherited = marker.get("recovery_sessions_used")
    expected_policy = policy(document, inherited)
    parent = marker.get("parent_failure", {})
    eligible_after = parent.get("eligible_after")
    if (historical.FIELD in plan or marker.get("contract") != contract()
            or plan.get("plan_identity") != digest({key: value for key, value in plan.items()
                                                     if key != "plan_identity"})
            or plan.get(historical.predecessor.FIELD, {}).get("contract") != contract()
            or plan.get("version") != automatic_recovery.MANUSCRIPT_VERSION
            or plan.get("stage") != "inventory" or plan.get("technical_retries") != 1
            or plan.get("account_allowance") != implementation.epoch.ALLOWANCE
            or plan.get("purposes") != ["concept_extraction", "coverage_verification", "reconstruction_verification"]
            or plan.get("recovery") != expected_policy
            or parent.get("eligible") is not True or not parent.get("runtime_record_hash")
            or not isinstance(parent.get("request"), dict)
            or parent.get("request_hash") != digest(parent["request"])
            or type(eligible_after) not in (int, float) or not math.isfinite(eligible_after) or eligible_after < 900
            or not isinstance(marker.get("migration_identity"), str) or not marker["migration_identity"]
            or marker.get("profile_hash") != digest(plan.get("profile"))
            or marker.get("source_hash") != plan["bindings"]["source"]):
        raise ValueError("Document stage lost its source, request or policy binding")
    calls = plan.get("calls")
    if (not isinstance(calls, list) or not calls
            or len(calls) > document["remaining_requests"] + document["split_allowance"]
            or automatic_recovery.call_limit(plan) > document["planned_calls"]
            or any(call != {"key": f"inventory:{index:04d}",
                            "input_hash": digest({"binding": plan["bindings"], "slot": index})}
                   for index, call in enumerate(calls))):
        raise ValueError("Document stage changed its native attempt membership")
    qualified = implementation.qualified
    qualified.routing.binding_for(plan["profile"])
    if plan["profile"][qualified.routing.FIELD]["index"] != 0:
        proof = marker.get("fallback_qualification", {})
        if (proof.get("status") != "QUALIFICATION_VERIFIED"
                or proof.get("profile_hash") != digest(plan["profile"])
                or proof.get("purposes") != plan["purposes"]
                or proof.get("settled") is not True or proof.get("canary_only") is not False
                or not all(proof.get(name) for name in ("evaluation_hash", "plan_identity", "output"))):
            raise ValueError("Alternate profile lacks its retained native qualification")
    return plan


def bind_plan(template, document, *, parent_failure, inherited_recovery, migration_identity):
    historical.validate_plan(template)
    result = deepcopy(template)
    marker = result.pop(historical.FIELD)
    marker.update(contract=contract(), policy=deepcopy(document), parent_failure=deepcopy(parent_failure),
                  recovery_sessions_used=inherited_recovery, migration_identity=migration_identity,
                  profile_hash=digest(result["profile"]), source_hash=result["bindings"]["source"],
                  template_identity=template["plan_identity"])
    result[FIELD] = marker
    result[historical.predecessor.FIELD]["contract"] = contract()
    result["recovery"] = policy(document, inherited_recovery)
    result["plan_identity"] = digest({key: value for key, value in result.items() if key != "plan_identity"})
    return validate_plan(result)


def attempt_layout(output, plan, entries, **keywords):
    from tools.inventory_recovery_v3.execution import layout

    return layout(output, plan, entries, **keywords)


bridge.FIELD = FIELD
bridge.contract = contract
bridge.validate_plan = validate_plan
implementation.contract = contract
implementation.capture.contract = contract
implementation.validate_plan = validate_plan
implementation.attempt_layout = attempt_layout
failure = bridge.receipt_failure
capture = implementation.capture


def conservative_usage(plan, report):
    if FIELD not in plan:
        return HISTORICAL_CONSERVATIVE[0](plan, report)
    if report.get("active_session_accounting") is None:
        return historical.NATIVE_CONSERVATIVE[0](plan, report)
    native = {key: value for key, value in report.items() if key != "active_session_accounting"}
    native["retained_tokens"] = (report["reported_tokens"] - report.get("unverified_reported_tokens", 0)
                                 + report["unknown_calls"] * 544000)
    if historical.NATIVE_CONSERVATIVE[0](plan, native) != report:
        raise ValueError("Document conservative accounting marker changed")
    return report


bridge.conservative_usage = conservative_usage


@contextmanager
def receipt_scope(historical_validate):
    native = codex_runtime.validate_codex_record

    def validate(root, reference, **keywords):
        relative = Path(reference["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Runtime reference escaped its original snapshot")
        directory = Path(root) / relative.parent
        capture_path = directory / "qualification-capture.json"
        captured = read_json(capture_path) if capture_path.exists() else {}
        if captured.get("contract") == contract():
            return native(root, reference, **keywords)
        if historical_validate is None:
            raise ValueError("Historical capture requires its exact retained receipt validator")
        profile = read_json(directory / "inputs/api-request.json")["profile"]
        return historical_validate(root, reference, profile)

    with implementation.replaced_aliases(native, validate):
        yield


@contextmanager
def runtime(plan, output, *, live=False, lock_fd=None, historical_validate=None, owner=None):
    from tools.inventory_recovery_v3 import provider_runtime
    from tools.inventory_recovery_v3.stage_owner import StageOwner

    if live:
        if not isinstance(owner, StageOwner) or owner.plan != plan or owner.output != Path(output).absolute():
            raise ValueError("Document live execution requires the reviewed paired dispatcher and admission")
        owner.check()
        if lock_fd is not None and lock_fd != owner.executor_descriptor:
            raise ValueError("Document runtime cannot replace its native executor descriptor")
        lock_fd = owner.executor_descriptor
    validate_plan(plan)
    native_runtime = provider_runtime.private_runtime(bridge.NATIVE_RUNTIME, owner=owner, plan=plan, output=output) if (
        live) else bridge.NATIVE_RUNTIME
    with schema_replay.scope(), bridge.conservative_scope(), native_runtime(
            plan, output, live=live, lock_fd=lock_fd, historical_validate=historical_validate), (
            receipt_scope(historical_validate)):
        if not live:
            yield
            return
        native = codex_runtime.launch

        codex_runtime.launch = provider_runtime.launch_boundary(native, plan=plan, output=output, owner=owner)
        try:
            yield
        finally:
            codex_runtime.launch = native


@contextmanager
def settlement_scope():
    from tools import token_epoch_20261025 as epoch

    previous = automatic_settlement.completed_usage
    previous_validate = epoch.validate_account

    def completed_usage(output, **keywords):
        plan = read_json(Path(output) / "plan.json")
        if FIELD not in plan:
            return previous(output, **keywords)
        with runtime(plan, output):
            for path in sorted((Path(output) / "calls").glob("*/call.json")):
                journal = read_json(path)
                if journal.get("runtime_record"):
                    capture.validate_record(plan["snapshot"], journal["runtime_record"])
            return implementation.qualified.accounting.conservative_usage(
                plan, NATIVE_USAGE[0](output, **keywords))

    def validate_account(record, *, usage_reader=None):
        return previous_validate(record, usage_reader=usage_reader or completed_usage)

    with schema_replay.scope(), bridge.conservative_scope(), implementation.replaced_aliases(previous, completed_usage), (
            implementation.replaced_aliases(previous_validate, validate_account)):
        yield
