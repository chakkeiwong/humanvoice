"""Reconstruct sealed generations from their complete preparation and source chain."""

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools import sol_inventory_program as original
from tools.inventory_recovery_v3 import runtime
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import regular_path

ACTIVE = ContextVar("inventory_preparation_ancestors", default=())


@contextmanager
def visit(output, plan):
    output = str(Path(output).absolute())
    ancestors = ACTIVE.get()
    if (any(path == output or identity == plan["plan_identity"] for path, identity in ancestors)
            or len(ancestors) >= plan[runtime.FIELD]["policy"]["maximum_generations"]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Successor ancestry repeats or exceeds document generations")
    token = ACTIVE.set((*ancestors, (output, plan["plan_identity"])))
    try:
        yield
    finally:
        ACTIVE.reset(token)


def anchored_account(anchor, current, grant):
    before = deepcopy(current)
    for name in ("events", "plans"):
        if type(anchor[name]) is not int or not 0 <= anchor[name] <= len(current[name]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Ancestor lost its prepared account prefix")
        before[name] = before[name][:anchor[name]]
    for name in ("reservation_ceiling", "gross_reservation_ceiling"):
        before[name] = anchor[name]
    if digest(before) != anchor["account_hash"] or anchor["grant"]["identity"] != grant["identity"]:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Ancestor changed its original account or grant")
    return before


def validate(output, plan):
    from tools.inventory_recovery_v2 import qualification
    from tools.inventory_recovery_v3 import continuation, successor
    from tools.inventory_recovery_v3.stage import reconstruct

    output = Path(output).absolute()

    def record(relative):
        return read_json(regular_path(output / relative))

    marker = plan[runtime.FIELD]
    report = record("admission-probe.json")
    if marker.get("admission_probe_hash") != digest(report):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Ancestor probe transcript differs from its sealed plan")
    transition = record("transition.json")
    if transition != marker["transition"]:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Ancestor changed its retained source transition")
    with visit(output, plan):
        if transition.get("version") == continuation.VERSION:
            successor.require_transition(transition)
        else:
            expected = successor.budget_transition(transition["migration"], transition["policy"],
                account_path=original.account.ACCOUNT, verify_settlement=runtime.historical.verify_settlement,
                reconstruct=reconstruct, verify_qualification=qualification.verify)
            if expected != transition:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Ancestor changed its original budget source gate")
        with runtime.settlement_scope():
            current = original.account.validate_account(read_json(original.account.ACCOUNT))
            grant = original.grant_status(original.GRANT)
        anchor = record("prepared-authority.json")
        before = anchored_account(anchor, current, grant)
        intent = {"transition": transition["identity"], "anchor": anchor, "plan": plan}
        if record("preparation-intent.json") != {**intent, "identity": digest(intent)}:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Ancestor lost its complete preparation intent")
        folder = Path("probe") / digest(runtime.contract())[:16]
        observations = record(folder / "observations.json")
        log, probe_intent = record(folder / "replay-log.json"), record(folder / "probe-intent.json")
        if (report != record(folder / "verification.json") or report.get("status") != "pass"
                or report.get("model_calls") != 0 or report.get("transition") != transition["identity"]
                or report.get("contract") != runtime.contract()
                or report.get("replay_hash") != digest(log)
                or report.get("probe_intent_hash") != digest(probe_intent)
                or report.get("observations_hash") != digest(observations)
                or observations.get("transition") != transition["identity"]
                or observations.get("contract") != runtime.contract()
                or not observations.get("observations")
                or observations["observations"][-1] != report.get("observation")
                or report["first_request"] != report["observation"].get("request")
                or report.get("inherited_calls") != len(transition["proof"]["prefix"])
                or log != {"inherited": transition["proof"]["prefix"], "new_requests": 1, "reached_unrun_request": True}):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Ancestor lost its exact prepared replay evidence")
        proof = {**deepcopy(transition["proof"]), "failed_request": report["first_request"]}
        if successor._plan_for_verified(plan["snapshot"], transition, before, anchor["grant"],
                proof=proof, admission_report=report) != plan:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Ancestor changed its admitted prefix or cumulative budget")
        probe_before = anchored_account(probe_intent["anchor"], current, grant)
        expected_probe = successor._plan_for_verified(output / folder / "snapshot", transition,
            probe_before, probe_intent["anchor"]["grant"])
        if probe_intent != {"transition": transition["identity"], "anchor": probe_intent["anchor"], "plan": expected_probe}:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Ancestor changed its no-call probe plan")
        evidence = marker.get("fallback_qualification")
        if evidence is not None and qualification.verify(evidence["output"], plan["profile"]) != evidence:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Ancestor changed its independently verified qualification")
    return plan
