"""Route retained review evidence through the native separate boundary verifier."""

from contextlib import contextmanager
from pathlib import Path

from humanvoice.artifacts import read_json
from tools import manuscript_transport_restart
from tools import reproduction_overload_recovery as continuation
from tools.automatic_program_account import ACCOUNT

BASE, ROOT = continuation.BASE, continuation.ROOT
EVIDENCE = BASE / "review-boundary-dispatch-20261021"
STAGE = BASE / "held-out-reproduction-review-overload-20261021-01"
NATIVE = "verify-manuscript-boundary-20261007.py"
VERSION = "review-boundary-dispatch-v1"


def selected(plan):
    return plan.get("technical_restart", {}).get("version") == continuation.VERSION


@contextmanager
def dispatch(plan):
    if not selected(plan):
        raise ValueError("Review boundary dispatch requires the retained overload continuation")
    continuation.validate_extension(plan)
    expected = plan["technical_restart"]
    native = manuscript_transport_restart.predecessor_evidence

    def predecessor(output, snapshot, maximum, *, account):
        if Path(output).resolve() != Path(expected["predecessor"]).resolve():
            return native(output, snapshot, maximum, account=account)
        if (Path(account).resolve() != Path(ACCOUNT).resolve()
                or str(Path(snapshot).resolve()) != plan["snapshot"]
                or type(maximum) is not int or maximum != len(plan["calls"])):
            raise ValueError("Review boundary changed its account, snapshot or remaining bound")
        proof = continuation.predecessor_evidence(output)
        if proof != expected:
            raise ValueError("Review boundary predecessor evidence changed")
        return proof

    manuscript_transport_restart.predecessor_evidence = predecessor
    try:
        yield predecessor
    finally:
        manuscript_transport_restart.predecessor_evidence = native


def preflight(output):
    output = Path(output).resolve()
    plan = read_json(output / "plan.json")
    if read_json(output / "execution.json")["status"] != "pass":
        raise ValueError("Review boundary requires an already completed stage")
    with dispatch(plan) as predecessor:
        return predecessor(plan["technical_restart"]["predecessor"], Path(plan["snapshot"]),
                           len(plan["calls"]), account=ACCOUNT)
