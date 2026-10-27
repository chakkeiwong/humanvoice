"""Retain full native ownership observations alongside an offline replay boundary."""

from copy import deepcopy
from uuid import uuid4

from humanvoice import codex_runtime
from humanvoice.artifacts import digest, read_json
from humanvoice.model import ModelAdapter
from tools.inventory_recovery_v3 import runtime, semantics
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.requests import source_observation
from tools.inventory_recovery_v3.reservations import regular_path


def folder_for(current, discovery=False):
    return current.output / ("discovery" if discovery else "probe") / digest(runtime.contract())[:16]


def observations(current, report, discovery=False):
    folder = folder_for(current, discovery)
    record = read_json(regular_path(folder / "observations.json"))
    if (record.get("transition") != current.transition["identity"]
            or record.get("contract") != runtime.contract()
            or digest(record) != report.get("observations_hash")
            or not record.get("observations")
            or record["observations"][-1] != report["observation"]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Probe lost its complete native ownership observations")
    return record["observations"]


def run(current, *, discovery=False, source_checked=False):
    from tools.inventory_recovery_v3.stage import immutable

    if not source_checked:
        current.source_gate()
    original = current.implementation
    proof = deepcopy(current.transition["proof"])
    split_child = current.transition.get("first_request_requires_probe", False)
    if discovery and split_child:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Discover the failed parent before applying its split transition")
    folder = folder_for(current, discovery)
    verification = regular_path(folder / "verification.json")
    if verification.exists():
        report = read_json(verification)
        log = read_json(regular_path(folder / "replay-log.json"))
        if (report.get("contract") != runtime.contract() or report.get("transition") != current.transition["identity"]
                or report.get("status") != "pass" or report.get("model_calls") != 0
                or report.get("replay_hash") != digest(log) or log.get("inherited") != proof["prefix"]
                or log.get("new_requests") != 1 or log.get("reached_unrun_request") is not True
                or report.get("inherited_calls") != len(proof["prefix"])
                or not split_child and report.get("first_request") != proof["failed_request"]
                or split_child and report.get("first_request") == proof["failed_request"]
                or report.get("first_request") != report.get("observation", {}).get("request")
                or report.get("probe_intent_hash") != digest(read_json(regular_path(folder / "probe-intent.json")))):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Retained successor probe changed its source or transition")
        observations(current, report, discovery)
        if getattr(current, "probe_cache", {}).get(str(folder)) == report:
            return report
    snapshot = folder / "snapshot"
    if not verification.exists():
        current.copy_snapshot(snapshot, proof)
    before = original.account.ACCOUNT.read_bytes(), original.GRANT.read_bytes()
    account, authority = current.current_authority()
    intent_path = regular_path(folder / "probe-intent.json")
    if intent_path.exists():
        intent = read_json(intent_path)
        if intent.get("transition") != current.transition["identity"]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Probe intent changed its transition")
        anchor = intent["anchor"]
        original_account = current.prepared_account(anchor, account, authority)
        plan = current.plan_for(snapshot, proof, original_account, anchor["grant"])
        if plan != intent["plan"]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Probe intent changed its native plan")
    else:
        anchor = {"account_hash": digest(account), "events": len(account["events"]),
                  "plans": len(account["plans"]), "reservation_ceiling": account["reservation_ceiling"],
                  "gross_reservation_ceiling": account["gross_reservation_ceiling"],
                  "grant": {"identity": authority["identity"], "available": authority["available"]}}
        plan = current.plan_for(snapshot, proof, account, authority)
        intent = {"transition": current.transition["identity"], "anchor": anchor, "plan": plan}
        immutable(intent_path, intent)
    native, captured = ModelAdapter.invoke, []
    historical_validator = codex_runtime.validate_codex_record

    def boundary(model, *arguments, **keywords):
        captured.append(original.lifecycle.retained.canonical_request(model, arguments, keywords))
        raise original.lifecycle.retained.ReplayBoundary()

    ModelAdapter.invoke = boundary
    try:
        replay_output = folder / "revalidation" / uuid4().hex if verification.exists() else folder
        replay_output.mkdir(parents=True, exist_ok=True)
        replay = current.capture_boundary if split_child else current.replay
        with semantics.transition_runtime(current.transition) as observed, replay(
                plan, replay_output, proof, historical_validator) as checked, runtime.runtime(
                plan, replay_output, historical_validate=checked), original.lifecycle.runtime():
            start = len(observed["observations"])
            applied_start = len(observed["applied"])
            try:
                original.lifecycle.previous.manuscript.run_manuscript_consumer(replay_output, snapshot, "inventory")
            except original.lifecycle.retained.ReplayBoundary:
                pass
        log = read_json(regular_path(replay_output / "replay-log.json"))
        rows = [source_observation(row) for row in observed["observations"][start:]]
        if (len(captured) != 1 or not split_child and captured != [proof["failed_request"]]
                or split_child and (captured[0] == proof["failed_request"]
                    or current.transition["rules"][-1]["identity"] not in observed["applied"][applied_start:])
                or log["inherited"] != proof["prefix"]
                or not log["reached_unrun_request"] or log["new_requests"] != 1
                or not rows or rows[-1]["request"] != captured[0]
                or before != (original.account.ACCOUNT.read_bytes(), original.GRANT.read_bytes())):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native probe changed authority or lost exact replay membership")
        record = {"transition": current.transition["identity"], "contract": runtime.contract(), "observations": rows}
        report = {"status": "pass", "model_calls": 0, "contract": runtime.contract(),
                  "transition": current.transition["identity"], "first_request": captured[0], "observation": rows[-1],
                  "inherited_calls": len(proof["prefix"]), "replay_hash": digest(log), "observations_hash": digest(record),
                  "probe_intent_hash": digest(intent)}
        immutable(folder / "observations.json", record)
        immutable(verification, report)
        current.probe_cache = {**getattr(current, "probe_cache", {}), str(folder): deepcopy(report)}
        return report
    finally:
        ModelAdapter.invoke = native
