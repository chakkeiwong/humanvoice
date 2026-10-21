"""Verify the boundary dispatch repair and continue the retained master program."""

import argparse
import fcntl
import json
import sys
import time
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import digest, implementation_hash, read_json, write_json
from tools import reproduction_boundary_dispatch as boundary
from tools import run_review_overload_20261021 as previous
from tools import run_writer_identifier_program_20261019 as identifier
from tools import run_writer_size_program_20261019 as sized
from tools.automatic_call_grant import status as grant_status
from tools.automatic_program_account import ACCOUNT
from tools.inventory_transport_continuation import immutable
from tools.parallel_verification_replay import cached_parallel_verification

BASE, EVIDENCE, STAGE = boundary.BASE, boundary.EVIDENCE, boundary.STAGE
continuation, scope = boundary.continuation, boundary.continuation.scope
PROOF, REGRESSION = EVIDENCE / "verification.json", EVIDENCE / "regression.xml"
PLAN = "docs/plans/REVIEW_BOUNDARY_DISPATCH_2026-10-21.md"
GRANT, PROGRESS = previous.GRANT, previous.PROGRESS
FILES = ("tools/reproduction_boundary_dispatch.py", "tools/reproduction_boundary_runner.py",
         "tools/run_review_boundary_20261021.py", "tools/supervise_review_boundary_20261021.py",
         "tests/test_review_boundary_dispatch.py", PLAN)
ACTIVE = False


def verify(*, freeze=False):
    suites = ET.parse(REGRESSION).getroot().findall("testsuite")
    cases = {case.attrib["name"].split("[")[0] for suite in suites for case in suite.findall("testcase")}
    required = {"test_native_boundary_consumes_matching_predecessor", "test_dispatch_checks_scope_and_evidence",
                "test_dispatch_delegates_unrelated_predecessor_and_restores", "test_runner_scopes_native_boundary",
                "test_controller_preserves_completed_stage_identity"}
    if (not suites or not required <= cases or any(int(suite.attrib.get(key, 0))
            for suite in suites for key in ("failures", "errors", "skipped"))):
        raise ValueError("Boundary dispatch requires passing native consumer regressions")
    upstream = previous.verify()
    before = ACCOUNT.read_bytes(), GRANT.read_bytes()
    with scope.verification_only():
        parent = boundary.preflight(STAGE)
    if before != (ACCOUNT.read_bytes(), GRANT.read_bytes()):
        raise ValueError("Boundary dispatch preflight changed accounting or grant bytes")
    names = ("plan.json", "execution.json", "allocation-ledger.json", "allocation-seal.json",
             "reproduction/process.json", "reproduction/evaluation.json", "reproduction/master-accounting-calls.json")
    result = {"version": boundary.VERSION, "status": "pass", "implementation": implementation_hash(),
              "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
              "upstream_identity": upstream["identity"], "predecessor_identity": digest(parent),
              "stage": str(STAGE), "stage_files": {name: digest((STAGE / name).read_bytes()) for name in names},
              "regression_sha256": digest(REGRESSION.read_bytes()),
              "regression_tests": sum(int(suite.attrib["tests"]) for suite in suites),
              "model_calls": 0, "account_bytes_unchanged": True, "grant_bytes_unchanged": True,
              "independent_native_boundary_required": True}
    result["identity"] = digest(result)
    if freeze:
        immutable(PROOF, result)
    elif read_json(PROOF) != result:
        raise ValueError("Frozen boundary dispatch repair changed")
    return result


def refresh(next_action, stop=None):
    state, account, grant = read_json(BASE / "status.json"), read_json(ACCOUNT), grant_status(GRANT)
    cursor = read_json(EVIDENCE / "cursor.json") if (EVIDENCE / "cursor.json").exists() else {"output": str(STAGE), "phase": "boundary_verification"}
    progress = read_json(PROGRESS) if PROGRESS.exists() else {}
    settled = sum(event["kind"] == "settle" for event in account["events"])
    checkpoint = STAGE / "boundary-checkpoint.json"
    boundary_pass = checkpoint.exists() and read_json(checkpoint)["status"] == "pass_settled_and_separately_verified"
    state.update(master_version="3.33", ensemble_version=123, local_date="2026-10-21", repair_plan=PLAN,
        status="review_boundary_stopped" if stop else "review_boundary_running" if ACTIVE else
               "review_boundary_ready" if PROOF.exists() else "review_boundary_validation",
        review_boundary_cursor=cursor, review_boundary_execution=read_json(PROOF) if PROOF.exists() else None,
        next_action=next_action, stop=stop, failure_cause=stop, active_model_execution=None,
        resume_controller=str(Path(__file__).relative_to(ROOT)), parallel_workers=16, network_retry_seconds=900,
        held_out_assembled_reviews={"passed": 28, "required": 28, "separate_boundary_pass": boundary_pass},
        current_call_grant={key: grant[key] for key in ("identity", "used", "available", "reserved_remaining")},
        current_account={"plans": len(account["plans"]), "settled": settled,
            "unsettled_plans": len(account["plans"]) - settled,
            "effective_ceiling": account["reservation_ceiling"], "allowance": account["allowance"]})
    output = Path(cursor["output"])
    if ACTIVE and not stop and (output / "execution.json").exists() and read_json(output / "execution.json")["status"] == "executing":
        state["active_model_execution"] = str(output)
    for phase in state["phases"]:
        if phase["id"] == "E7-RB" and phase["status"] != "completed":
            phase["status"] = "repair_stopped" if stop else "running" if ACTIVE else "repair_validation"
        if (phase["id"] == "E6-B" and set(progress.get("humanizations", {})) == {"held-out", "zlb"}
                or phase["id"] == "E7-RB" and set(progress.get("reproductions", {})) == {"held-out", "zlb"}):
            phase["status"] = "completed"
    if progress.get("final_admission"):
        state.update(status="awaiting_final_immutable_ZLB_acceptance", resume_controller=None, active_model_execution=None)
    note = (f"\nCurrent execution: master 3.33 / ensemble 123; observed {datetime.now(timezone.utc).isoformat()}.\n"
        f"Status: {state['status']}. Repair: {PLAN}.\n"
        "Held-out reproduction execution passed. All 28 of 28 assembled leaf reviews pass; its last stage used three calls.\n"
        f"Separate held-out boundary: {'passed' if boundary_pass else 'pending verification'}.\n"
        "The prior boundary used a writer-checkpoint verifier for a retained-review continuation and rejected its completed judgments.\n"
        "Route that exact continuation to its frozen predecessor verifier, checking account, snapshot, bound and full proof equality.\n"
        "The native boundary still verifies independent reproduction, actual receipts, settlement and account; provider calls are prohibited during verification.\n"
        "Keep all completed reviews, sealed stage evidence, frozen code and failed charges. Resume the existing stage identity without new model reservations.\n"
        "Use 16 verification workers; provider calls/accounting remain sequential. Eligible response-free network failures wait 900 seconds.\n"
        "Writer limits: 100k input / 32k output. Assembled reviewer: 80k / 32k. Size splits: depth 3 and 14 children/root.\n"
        "Audits: 900 seconds/$4. SSD working storage; checksum-bound archive aliases stay read-only.\n"
        f"Calls: {grant['used']}/{grant['maximum']} used; {grant['available']} available; {grant['reserved_remaining']} reserved.\n"
        f"Settlements: {settled}/{len(account['plans'])}; token ceiling {account['reservation_ceiling']:,}/{account['allowance']:,}.\n"
        "Remaining: complete separate held-out boundary; full ZLB inventory/humanization/review/release; independent ZLB reproduction;\n"
        "automatic final admission; human acceptance of the immutable actual ZLB output.\n"
        "If ZLB split reservations exceed 600 slots, implement and verify bounded batching before activation.\n"
        "At every phase boundary or stop: inspect, settle, verify, repair and refresh both masters. Only final output acceptance requires human review.\n"
        f"Next: {next_action}\nStop: {stop or 'none'}.\n")
    write_json(BASE / "status.json", state)
    for name in ("humanvoice_master_program_v2.md", "ENSEMBLE_MASTER_PROGRAM_2026-09-30.md"):
        path = ROOT / "docs/plans" / name
        content = path.read_text()
        heading, tail = content.split("\n", 1)[0], content.split("<!-- end-current-benchmark-execution -->", 1)[1]
        intro = ("\nOperational refresh, 21 October 2026: master 3.33 / ensemble 123.\n"
                 "The [boundary dispatch repair](REVIEW_BOUNDARY_DISPATCH_2026-10-21.md) preserves all 28 passing held-out reviews.\n"
                 "Only final acceptance of the immutable actual ZLB output requires human content review.\n\n")
        path.write_text(heading + "\n" + intro + "<!-- current-benchmark-execution -->" + note
                        + "<!-- end-current-benchmark-execution -->" + tail)
    for path in (BASE / "CURRENT_EXECUTION_20261014.md", EVIDENCE / "STATUS.md"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Retained review boundary verification\n" + note)
    print(json.dumps({"status": state["status"], "next": next_action, "stop": stop}), flush=True)


def recovery_command(command):
    actual = scope.recovery_command(command)
    return [actual[0], str(ROOT / "tools/reproduction_boundary_runner.py"), *actual[2:]]


def run():
    global ACTIVE
    review_size = previous.previous
    with ExitStack() as bindings:
        bindings.callback(setattr, scope, "RUNNER", scope.RUNNER)
        scope.RUNNER = ROOT / "tools/reproduction_boundary_runner.py"
        for module in (review_size, identifier, sized):
            for name, value in (("refresh", refresh), ("continuation", continuation), ("recovery_command", recovery_command),
                                ("EVIDENCE", EVIDENCE), ("SUFFIX", previous.SUFFIX)):
                bindings.callback(setattr, module, name, getattr(module, name))
                setattr(module, name, value)
        for name, value in (("benchmark_chain", review_size.benchmark_chain), ("split_bound", review_size.split_bound)):
            bindings.callback(setattr, sized, name, getattr(sized, name))
            setattr(sized, name, value)
        ACTIVE = True
        try:
            refresh("Resume separate verification of the completed held-out reproduction, then continue full ZLB.")
            sized.run()
        finally:
            ACTIVE = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("refresh", "verify", "freeze", "activate"))
    parser.add_argument("--live", action="store_true")
    arguments = parser.parse_args()
    if arguments.action == "activate" and not arguments.live:
        parser.error("Execution requires --live")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with (BASE / "inventory-prefix-controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with scope.accounting_scope(), continuation.pipeline(), cached_parallel_verification(
                workers=16, progress=EVIDENCE / f"controller-{time.time_ns()}.json"):
            try:
                if arguments.action == "refresh":
                    refresh("Validate the boundary adapter, then resume the completed stage without repurchasing reviews.")
                    return 0
                result = verify(freeze=arguments.action == "freeze" or arguments.action == "activate" and not PROOF.exists())
                print(json.dumps({"status": result["status"], "regression_tests": result["regression_tests"]}), flush=True)
                if arguments.action == "activate":
                    run()
                else:
                    refresh("Boundary dispatch proof passes; resume native separate verification and full ZLB.")
            except BaseException as error:
                refresh("Inspect the retained cause, repair prospectively and refresh before continuing.",
                        type(error).__name__ + ": " + str(error)[:2000])
                raise
    return 0


if __name__ == "__main__":
    with continuation.archive.access():
        raise SystemExit(main())
