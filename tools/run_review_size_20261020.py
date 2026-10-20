"""Verify and execute bounded automatic recovery of oversized assembled reviews."""

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
from tools import reproduction_review_size_recovery as continuation
from tools import run_reproduction_semantic_20261020 as previous
from tools.automatic_call_grant import status as grant_status
from tools.automatic_program_account import ACCOUNT
from tools.inventory_transport_continuation import immutable
from tools.parallel_verification_replay import cached_parallel_verification

scope = continuation.scope
BASE, EVIDENCE = continuation.BASE, continuation.EVIDENCE
PROOF, REGRESSION, PROBE = EVIDENCE / "verification.json", EVIDENCE / "regression-02.xml", EVIDENCE / "probe-02/verification.json"
PLAN = "docs/plans/ASSEMBLED_REVIEW_SIZE_RECOVERY_2026-10-20.md"
SUFFIX = "review-size-20261020-01"
GRANT, PROGRESS = previous.GRANT, previous.PROGRESS
FILES = (*continuation.FILES, "tools/probe_review_size_20261020.py", "tools/run_review_size_20261020.py",
         "tools/supervise_review_size_20261020.py", "tests/test_assembled_size_recovery.py",
         "tests/test_review_size_continuation.py", PLAN)
ACTIVE = False


def regressions():
    suites = ET.parse(REGRESSION).getroot().findall("testsuite")
    cases = {case.attrib["name"].split("[")[0] for suite in suites for case in suite.findall("testcase")}
    required = {"test_partition_preserves_full_context_and_exact_obligations",
                "test_partition_stops_at_indivisible_or_depth_limit",
                "test_native_review_splits_preserve_receipts_and_cached_reviews",
                "test_inherited_split_does_not_retry_unrelated_error",
                "test_native_size_accounting_preserves_failed_charge",
                "test_review_guard_rejects_completed_or_changed_work",
                "test_review_size_pipeline_restores_functions",
                "test_review_size_controller_routes_and_restores",
                "test_native_resume_preserves_cached_assembled_findings",
                "test_activation_waits_for_in_progress_validation"}
    if not suites or not required <= cases or any(int(suite.attrib.get(key, 0)) for suite in suites
            for key in ("failures", "errors", "skipped")):
        raise ValueError("Review size recovery requires passing native regressions without skips")
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
        raise ValueError("Review size recovery lost its independent exact-child probe")
    result = {"version": "review-size-master-v1", "status": "pass", "workers": 16,
              "implementation": implementation_hash(), "extension": continuation.extension(),
              "upstream_identity": continuation.report()["upstream_identity"],
              "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
              "regression_sha256": digest(REGRESSION.read_bytes()), "probe_sha256": digest(PROBE.read_bytes()),
              "regression_tests": count, "remaining_logical_calls": parent["remaining_calls"],
              "maximum_new_attempts": parent["remaining_calls"] + parent["remaining_transport_extras"],
              "model_calls": 0, "completed_responses_repeated": False, "unknown_tokens_released": False}
    result["identity"] = digest(result)
    if freeze:
        immutable(PROOF, result)
    elif read_json(PROOF) != result:
        raise ValueError("Frozen review size recovery changed")
    return result


def refresh(next_action, stop=None):
    state, account, grant = read_json(BASE / "status.json"), read_json(ACCOUNT), grant_status(GRANT)
    cursor = read_json(EVIDENCE / "cursor.json") if (EVIDENCE / "cursor.json").exists() else {}
    progress = read_json(PROGRESS) if PROGRESS.exists() else {}
    settled = [row["usage"] for row in account["events"] if row["kind"] == "settle"]
    output = Path(cursor.get("output", str(continuation.PRIOR)))
    cause = continuation.previous.failure_summary(output) if stop else None
    state.update(master_version="3.31", ensemble_version=121, local_date="2026-10-20", repair_plan=PLAN,
        status="review_size_stopped" if stop else "review_size_running" if ACTIVE else
               "review_size_ready" if PROOF.exists() else "review_size_validation",
        review_size_cursor=cursor, review_size_execution=read_json(PROOF) if PROOF.exists() else None,
        next_action=next_action, stop=stop, failure_cause=cause, active_model_execution=None,
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
    note = (f"\nCurrent execution: master 3.31 / ensemble 121; observed {datetime.now(timezone.utc).isoformat()}.\n"
        f"Status: {state['status']}. Repair: {PLAN}.\n"
        "Both directed writer repairs and their unit reviews passed. Fifteen of twenty-seven assembled reviews are retained.\n"
        "The next review completed with 76,106 input and 40,963 output tokens; output exceeded the unchanged 32,000 ceiling.\n"
        "Its seventy concepts and ninety-eight functions pass native semantic checks, but the oversized answer is not admitted.\n"
        "Automatically partition only proven size failures, preserving full source/candidate context and all concept obligations.\n"
        "Resume native release against the original session and assembly, preserving the identity of cached findings.\n"
        "Never repurchase the failed parent or completed reviews. Substantive rejection, malformed evidence and unknown failures stop.\n"
        "Held-out successor: 179 finite logical slots plus five unspent network extras, at most 184 attempts; actual use may be lower.\n"
        "Review limits remain 80,000 input / 32,000 output; writer limits remain 100,000 input / 32,000 output.\n"
        "Both size mechanisms allow depth 3 and at most 14 child calls/root. All failed receipts and incomplete charges remain intact.\n"
        "Independent zero-provider exact-child probe and native accounting/admission regressions are required before execution.\n"
        "Use 16 verification workers; provider calls/accounting remain sequential. Eligible network failures wait 900 seconds.\n"
        "Audits remain 900 seconds/$4. SSD is working storage; verified archive aliases remain read-only.\n"
        f"Calls: {grant['used']}/{grant['maximum']} used; {grant['available']} available; {grant['reserved_remaining']} reserved.\n"
        f"Settlements: {len(settled)}/{len(account['plans'])}; token ceiling {account['reservation_ceiling']:,}/{account['allowance']:,}.\n"
        "Remaining: held-out assembled reviews and reproduction verification; full ZLB inventory/humanization/review/release;\n"
        "independent ZLB reproduction; automatic final admission; human acceptance of the immutable actual ZLB output.\n"
        "Only final acceptance requires human content review. Every phase boundary or stop: inspect, settle, verify, repair, refresh both masters.\n"
        f"Next: {next_action}\nStop: {stop or 'none'}.\n"
        f"Cause: {json.dumps(cause, ensure_ascii=False) if cause else 'historical review output-size breach; successor not yet failed'}.\n")
    write_json(BASE / "status.json", state)
    for name in ("humanvoice_master_program_v2.md", "ENSEMBLE_MASTER_PROGRAM_2026-09-30.md"):
        path = ROOT / "docs/plans" / name
        content = path.read_text()
        heading = content.split("\n", 1)[0]
        _, tail = content.split("<!-- end-current-benchmark-execution -->", 1)
        intro = ("\nOperational refresh, 20 October 2026: master 3.31 / ensemble 121.\n"
                 "The [assembled-review size recovery](ASSEMBLED_REVIEW_SIZE_RECOVERY_2026-10-20.md) preserves completed work.\n"
                 "Only final acceptance of the immutable actual ZLB output requires human content review.\n\n")
        path.write_text(heading + "\n" + intro + "<!-- current-benchmark-execution -->" + note
                        + "<!-- end-current-benchmark-execution -->" + tail)
    for path in (BASE / "CURRENT_EXECUTION_20261014.md", EVIDENCE / "STATUS.md"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Assembled review size recovery and execution\n" + note)
    print(json.dumps({"status": state["status"], "next": next_action, "stop": stop}), flush=True)


def recovery_command(command):
    actual = scope.recovery_command(command)
    return [actual[0], str(ROOT / "tools/reproduction_review_size_runner.py"), *actual[2:]]


def split_bound(snapshot, logical):
    from humanvoice.concept_baseline import load_baseline
    from humanvoice.semantic_unit_splitting import load_rewrite_plan

    baseline = load_baseline(snapshot / ".humanvoice/inventory/baseline.json")
    plan = load_rewrite_plan(snapshot / f".humanvoice/plans/plan-{baseline.baseline_id}.json")
    roots = logical - 2 * len(plan.units)
    maximum = logical + (len(plan.units) + roots) * continuation.recovery.POLICY["maximum_child_calls_per_root"]
    if roots < 1 or maximum > 600:
        raise ValueError("Writer/review size allowance requires bounded stage batching before activation")
    return maximum


def benchmark_chain(name, row, campaign, bounds):
    if name != "held-out":
        return previous.previous.previous.benchmark_chain(name, row, campaign, bounds)
    proof = continuation.predecessor_evidence()
    snapshot, calls = Path(proof["snapshot"]), proof["remaining_calls"]
    output = BASE / f"{name}-reproduction-{SUFFIX}"
    if not (output / "plan.json").exists():
        write_json(EVIDENCE / "cursor.json", {"phase": "prepare", "output": str(output)})
        refresh("Prepare exact remaining reviews and their finite split reservations.")
        campaign.script("run-manuscript-with-300-grant-20261008.py", "prepare", "--output", output,
            "--snapshot", snapshot, "--stage", "reproduction", "--max-calls", calls,
            "--call-grant", GRANT, "--technical-predecessor", continuation.PRIOR)
    suffix = campaign.SUFFIX
    try:
        campaign.SUFFIX = SUFFIX
        write_json(EVIDENCE / "cursor.json", {"phase": "execute", "output": str(output)})
        refresh("Split the oversized review, finish remaining windows and independently verify reproduction.")
        campaign.manuscript(name, "reproduction", snapshot, calls, "E7-RB-" + name)
    finally:
        campaign.SUFFIX = suffix
    packets = list((snapshot / "release").iterdir())
    if len(packets) != 1:
        raise ValueError("Final admission requires one immutable packet")
    progress = read_json(PROGRESS)
    progress.setdefault("reproductions", {})[name] = {"snapshot": str(snapshot), "output": str(output / "reproduction"),
        "full_call_bound": calls + proof["remaining_transport_extras"]}
    write_json(PROGRESS, progress)
    write_json(EVIDENCE / "cursor.json", {"phase": "verified_reproduction", "output": str(output)})
    refresh("Held-out reproduction independently verified and settled; continue to full ZLB.")
    return {"snapshot": snapshot, "packet": packets[0], "reproduction": output / "reproduction"}


def run():
    global ACTIVE
    identifier, sized = previous.previous.previous, previous.previous.previous.previous
    with ExitStack() as bindings:
        bindings.callback(setattr, scope, "RUNNER", scope.RUNNER)
        scope.RUNNER = ROOT / "tools/reproduction_review_size_runner.py"
        for module in (identifier, sized):
            for name, value in (("refresh", refresh), ("continuation", continuation), ("recovery_command", recovery_command),
                                ("EVIDENCE", EVIDENCE), ("SUFFIX", SUFFIX)):
                bindings.callback(setattr, module, name, getattr(module, name))
                setattr(module, name, value)
        for name, value in (("benchmark_chain", benchmark_chain), ("split_bound", split_bound)):
            bindings.callback(setattr, sized, name, getattr(sized, name))
            setattr(sized, name, value)
        ACTIVE = True
        try:
            refresh("Verified review size recovery activated; prepare its bounded successor.")
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
                    refresh("Finish native accounting regressions and the independent exact-child probe before live activation.")
                    return 0
                if not continuation.DIAGNOSTIC.exists():
                    refresh("Verify retained reviews, precise size failure, independent process and settlement.")
                    with scope.verification_only():
                        continuation.diagnose()
                if arguments.action == "diagnose":
                    refresh("Diagnosis passes; independently probe the first split review without provider calls.")
                    return 0
                if arguments.action in {"probe", "activate"} and not PROBE.exists():
                    from tools.probe_review_size_20261020 import probe

                    refresh("Run the independent zero-provider probe of the exact first split review.")
                    probe(PROBE.parent)
                if arguments.action == "probe":
                    refresh("Exact-child probe passes; finish regression verification and freeze before activation.")
                    return 0
                result = verify(freeze=arguments.action == "freeze" or arguments.action == "activate" and not PROOF.exists())
                print(json.dumps({"status": result["status"], "regression_tests": result["regression_tests"]}), flush=True)
                if arguments.action == "activate":
                    run()
                else:
                    refresh("Review size recovery proof passes; continue the supervised program.")
            except BaseException as error:
                refresh("Inspect retained cause, repair prospectively and refresh before further execution.",
                        type(error).__name__ + ": " + str(error))
                raise
    return 0


if __name__ == "__main__":
    with continuation.archive.access():
        raise SystemExit(main())
