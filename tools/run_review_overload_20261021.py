"""Verify, refresh and execute the response-free overload continuation."""

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
from tools import reproduction_overload_recovery as continuation
from tools import run_review_size_20261020 as previous
from tools.automatic_call_grant import status as grant_status
from tools.automatic_program_account import ACCOUNT
from tools.inventory_transport_continuation import immutable
from tools.parallel_verification_replay import cached_parallel_verification

scope = continuation.scope
BASE, EVIDENCE = continuation.BASE, continuation.EVIDENCE
PROOF, REGRESSION, PROBE = EVIDENCE / "verification.json", EVIDENCE / "regression-02.xml", EVIDENCE / "probe/verification.json"
GUARD_REGRESSION = EVIDENCE / "regression-guard.xml"
PLAN = "docs/plans/REVIEW_OVERLOAD_RECOVERY_2026-10-21.md"
SUFFIX = "review-overload-20261021-01"
GRANT, PROGRESS = previous.GRANT, previous.PROGRESS
FILES = (*continuation.FILES, "tools/probe_review_overload_20261021.py", "tools/run_review_overload_20261021.py",
         "tools/supervise_review_overload_20261021.py", "tests/test_review_overload_recovery.py", PLAN)
ACTIVE = False


def regressions():
    suites = [suite for path in (REGRESSION, GUARD_REGRESSION) for suite in ET.parse(path).getroot().findall("testsuite")]
    cases = {case.attrib["name"].split("[")[0] for suite in suites for case in suite.findall("testcase")}
    required = {"test_overload_requires_exact_prospective_native_evidence",
                "test_native_overload_retry_preserves_failed_charge",
                "test_overload_pipeline_restores_functions", "test_overload_bound_does_not_replenish",
                "test_overload_accounting_requires_exact_activity", "test_overload_controller_routes_and_restores",
                "test_overload_first_request_checked_before_transmission",
                "test_native_resume_preserves_cached_assembled_findings", "test_persistent_fifteen_minute_delay"}
    if not suites or not required <= cases or any(int(suite.attrib.get(key, 0)) for suite in suites
            for key in ("failures", "errors", "skipped")):
        raise ValueError("Overload continuation requires passing native regressions without skips")
    return sum(int(suite.attrib["tests"]) for suite in suites)


def verify(*, freeze=False):
    count = regressions()
    parent, probe = continuation.predecessor_evidence(), read_json(PROBE)
    if (probe["status"] != "pass" or probe["model_calls"] != 0 or probe["workers"] != 16
            or not probe["independent_process"] or probe["retained_assembled_reviews"] != parent["retained_assembled_reviews"]
            or not all(probe[key] for key in ("account_bytes_unchanged", "grant_bytes_unchanged", "predecessor_bytes_unchanged"))
            or probe["extension"] != continuation.extension() or probe["predecessor_identity"] != digest(parent)
            or probe["first_request_hash"] != parent["first_request_hash"]
            or any(digest((PROBE.parent / name).read_bytes()) != expected for name, expected in probe["process_evidence"].items())):
        raise ValueError("Overload continuation lost its independent interrupted-request probe")
    result = {"version": "review-overload-master-v1", "status": "pass", "workers": 16,
              "implementation": implementation_hash(), "extension": continuation.extension(),
              "upstream_identity": continuation.report()["upstream_identity"],
              "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
              "regression_sha256": digest(REGRESSION.read_bytes()), "probe_sha256": digest(PROBE.read_bytes()),
              "guard_regression_sha256": digest(GUARD_REGRESSION.read_bytes()),
              "regression_tests": count, "remaining_logical_calls": parent["remaining_calls"],
              "maximum_new_attempts": parent["remaining_calls"] + parent["remaining_transport_extras"],
              "model_calls": 0, "completed_responses_repeated": False, "unknown_tokens_released": False}
    result["identity"] = digest(result)
    if freeze:
        immutable(PROOF, result)
    elif read_json(PROOF) != result:
        raise ValueError("Frozen overload continuation changed")
    return result


def refresh(next_action, stop=None):
    state, account, grant = read_json(BASE / "status.json"), read_json(ACCOUNT), grant_status(GRANT)
    cursor = read_json(EVIDENCE / "cursor.json") if (EVIDENCE / "cursor.json").exists() else {}
    progress = read_json(PROGRESS) if PROGRESS.exists() else {}
    settled = [row["usage"] for row in account["events"] if row["kind"] == "settle"]
    output = Path(cursor.get("output", str(continuation.PRIOR)))
    state.update(master_version="3.32", ensemble_version=122, local_date="2026-10-21", repair_plan=PLAN,
        status="review_overload_stopped" if stop else "review_overload_running" if ACTIVE else
               "review_overload_ready" if PROOF.exists() else "review_overload_validation",
        review_overload_cursor=cursor, review_overload_execution=read_json(PROOF) if PROOF.exists() else None,
        next_action=next_action, stop=stop, failure_cause=None, active_model_execution=None,
        resume_controller=str(Path(__file__).relative_to(ROOT)), parallel_workers=16, network_retry_seconds=900,
        current_call_grant={key: grant[key] for key in ("identity", "used", "available", "reserved_remaining")},
        current_account={"plans": len(account["plans"]), "settled": len(settled),
            "unsettled_plans": len(account["plans"]) - len(settled),
            "effective_ceiling": account["reservation_ceiling"], "allowance": account["allowance"]})
    terminal = output / "execution.json"
    if ACTIVE and not stop and terminal.exists() and read_json(terminal)["status"] == "executing":
        state["active_model_execution"] = str(output)
    for phase in state["phases"]:
        if phase["id"] == "E7-RB" and phase["status"] != "completed":
            phase["status"] = "repair_stopped" if stop else "running" if ACTIVE else "repair_validation"
        if (phase["id"] == "E6-B" and set(progress.get("humanizations", {})) == {"held-out", "zlb"}
                or phase["id"] == "E7-RB" and set(progress.get("reproductions", {})) == {"held-out", "zlb"}):
            phase["status"] = "completed"
    if progress.get("final_admission"):
        state.update(status="awaiting_final_immutable_ZLB_acceptance", resume_controller=None, active_model_execution=None)
    note = (f"\nCurrent execution: master 3.32 / ensemble 122; observed {datetime.now(timezone.utc).isoformat()}.\n"
        f"Status: {state['status']}. Repair: {PLAN}.\n"
        "Predecessor retained both writer repairs, all unit reviews and 25 of 28 assembled leaf reviews.\n"
        "Three original review windows remain. The interrupted request has no response or usage; its last gateway error reports overload.\n"
        "Recognize only the exact overload diagnostic after native receipt, process, no-response and no-usage checks.\n"
        "Resume native release with the original session, assembly and completed findings. Never repurchase a completed review or size parent.\n"
        "The 900-second delay survives restarts. Two failed attempts keep their full charges; retries are not replenished.\n"
        "Successor bound: 45 logical slots including possible size splits, plus three inherited network extras; at most 48 attempts.\n"
        "Review limits remain 80,000 input / 32,000 output; writer limits remain 100,000 input / 32,000 output.\n"
        "Both size mechanisms allow depth 3 and at most 14 child calls/root. Semantic rejection and unknown evidence stop.\n"
        "Independent zero-provider request probe and native accounting/admission regressions precede activation.\n"
        "Use 16 verification workers; provider calls/accounting remain sequential. Audits remain 900 seconds/$4.\n"
        "SSD is working storage; checksum-bound archive aliases remain read-only.\n"
        f"Calls: {grant['used']}/{grant['maximum']} used; {grant['available']} available; {grant['reserved_remaining']} reserved.\n"
        f"Settlements: {len(settled)}/{len(account['plans'])}; token ceiling {account['reservation_ceiling']:,}/{account['allowance']:,}.\n"
        "Remaining: finish held-out reviews and independent reproduction verification; full ZLB inventory/humanization/review/release;\n"
        "independent ZLB reproduction; automatic final admission; human acceptance of the immutable actual ZLB output.\n"
        "If ZLB split reservations exceed 600 slots, bounded batching must be implemented and verified before that stage.\n"
        "Every phase boundary or stop: inspect, settle, verify, repair and refresh both masters. Only final output acceptance requires human review.\n"
        f"Next: {next_action}\nStop: {stop or 'none'}.\n")
    write_json(BASE / "status.json", state)
    for name in ("humanvoice_master_program_v2.md", "ENSEMBLE_MASTER_PROGRAM_2026-09-30.md"):
        path = ROOT / "docs/plans" / name
        content = path.read_text()
        heading = content.split("\n", 1)[0]
        _, tail = content.split("<!-- end-current-benchmark-execution -->", 1)
        intro = ("\nOperational refresh, 21 October 2026: master 3.32 / ensemble 122.\n"
                 "The [response-free overload repair](REVIEW_OVERLOAD_RECOVERY_2026-10-21.md) preserves completed work and charges.\n"
                 "Only final acceptance of the immutable actual ZLB output requires human content review.\n\n")
        path.write_text(heading + "\n" + intro + "<!-- current-benchmark-execution -->" + note
                        + "<!-- end-current-benchmark-execution -->" + tail)
    for path in (BASE / "CURRENT_EXECUTION_20261014.md", EVIDENCE / "STATUS.md"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Response-free overload recovery and execution\n" + note)
    print(json.dumps({"status": state["status"], "next": next_action, "stop": stop}), flush=True)


def recovery_command(command):
    actual = scope.recovery_command(command)
    return [actual[0], str(ROOT / "tools/reproduction_overload_runner.py"), *actual[2:]]


def run():
    global ACTIVE
    identifier, sized = previous.previous.previous.previous, previous.previous.previous.previous.previous
    with ExitStack() as bindings:
        bindings.callback(setattr, scope, "RUNNER", scope.RUNNER)
        scope.RUNNER = ROOT / "tools/reproduction_overload_runner.py"
        for module in (previous, identifier, sized):
            for name, value in (("refresh", refresh), ("continuation", continuation), ("recovery_command", recovery_command),
                                ("EVIDENCE", EVIDENCE), ("SUFFIX", SUFFIX)):
                bindings.callback(setattr, module, name, getattr(module, name))
                setattr(module, name, value)
        for name, value in (("benchmark_chain", previous.benchmark_chain), ("split_bound", previous.split_bound)):
            bindings.callback(setattr, sized, name, getattr(sized, name))
            setattr(sized, name, value)
        ACTIVE = True
        try:
            refresh("Verified overload continuation activated; prepare the three remaining reviews.")
            sized.run()
        finally:
            ACTIVE = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("diagnose", "probe", "refresh", "verify", "freeze", "activate"))
    parser.add_argument("--live", action="store_true")
    arguments = parser.parse_args()
    if arguments.action == "activate" and not arguments.live:
        parser.error("Execution requires --live")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with (BASE / "inventory-prefix-controller.lock").open("a") as lock:
        mode = fcntl.LOCK_EX if arguments.action == "activate" else fcntl.LOCK_EX | fcntl.LOCK_NB
        fcntl.flock(lock, mode)
        with scope.accounting_scope(), continuation.pipeline(), cached_parallel_verification(
                workers=16, progress=EVIDENCE / f"controller-{time.time_ns()}.json"):
            try:
                if arguments.action == "refresh":
                    refresh("Verify exact overload evidence and native regressions before supervised continuation.")
                    return 0
                if not continuation.DIAGNOSTIC.exists():
                    refresh("Verify retained reviews, stopped process, overload receipt and settlement.")
                    with scope.verification_only():
                        continuation.diagnose()
                if arguments.action == "diagnose":
                    refresh("Diagnosis passes; independently probe the interrupted request without provider calls.")
                    return 0
                if arguments.action in {"probe", "activate"} and not PROBE.exists():
                    from tools.probe_review_overload_20261021 import probe

                    refresh("Run the independent zero-provider probe of the exact interrupted review.")
                    probe(PROBE.parent)
                if arguments.action == "probe":
                    refresh("Interrupted-request probe passes; verify regressions and freeze before activation.")
                    return 0
                result = verify(freeze=arguments.action == "freeze" or arguments.action == "activate" and not PROOF.exists())
                print(json.dumps({"status": result["status"], "regression_tests": result["regression_tests"]}), flush=True)
                if arguments.action == "activate":
                    run()
                else:
                    refresh("Overload continuation proof passes; continue the supervised program.")
            except BaseException as error:
                refresh("Inspect retained cause, repair prospectively and refresh before further execution.",
                        type(error).__name__ + ": " + str(error))
                raise
    return 0


if __name__ == "__main__":
    with continuation.archive.access():
        raise SystemExit(main())
