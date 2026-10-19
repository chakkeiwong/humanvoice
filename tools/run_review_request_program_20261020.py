"""Verify one diagnostic review retry, then continue the existing master program."""

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
from tools import process_accounting_scope as scope
from tools import review_request_recovery as continuation
from tools import run_writer_identifier_program_20261019 as previous
from tools.automatic_call_grant import status as grant_status
from tools.automatic_program_account import ACCOUNT
from tools.inventory_transport_continuation import immutable
from tools.parallel_verification_replay import cached_parallel_verification

BASE, EVIDENCE = continuation.BASE, continuation.EVIDENCE
PROOF, REGRESSION, PROBE = EVIDENCE / "verification.json", EVIDENCE / "regression.xml", EVIDENCE / "probe-01/verification.json"
PLAN = "docs/plans/REVIEW_REQUEST_RECOVERY_2026-10-20.md"
SUFFIX = "review-request-20261020-01"
GRANT, PROGRESS = previous.GRANT, previous.PROGRESS
FILES = (*continuation.FILES, "tools/probe_review_request_20261020.py", "tools/run_review_request_program_20261020.py",
         "tools/supervise_review_request_program_20261020.py", "tests/test_review_request_recovery.py", PLAN)
ACTIVE = False


def regressions():
    suites = ET.parse(REGRESSION).getroot().findall("testsuite")
    cases = {case.attrib["name"].split("[")[0] for suite in suites for case in suite.findall("testcase")}
    required = {"test_diagnostic_retry_never_overrides_native_rejection", "test_review_guard_stops_later_transmissions",
                "test_review_guard_requires_exact_first_request", "test_review_denials_preserve_failed_receipt",
                "test_failure_summary_preserves_provider_cause", "test_review_pipeline_restores_native_functions",
                "test_review_controller_preserves_successor_bound"}
    if (not suites or not required <= cases or any(int(suite.attrib.get(key, 0)) for suite in suites
            for key in ("failures", "errors", "skipped"))):
        raise ValueError("Review recovery requires its passing regressions without skips")
    return sum(int(suite.attrib["tests"]) for suite in suites)


def verify(*, freeze=False):
    count = regressions()
    upstream = previous.verify()
    parent, probe = continuation.predecessor_evidence(), read_json(PROBE)
    if (probe["status"] != "pass" or probe["model_calls"] != 0 or probe["workers"] != 16
            or not probe["independent_process"] or probe["retained_writers"] != 14
            or not all(probe[key] for key in ("account_bytes_unchanged", "grant_bytes_unchanged", "predecessor_bytes_unchanged"))
            or probe["extension"] != continuation.extension() or probe["predecessor_identity"] != digest(parent)
            or probe["first_request_hash"] != digest(parent["interrupted_request"])
            or any(digest((PROBE.parent / name).read_bytes()) != expected for name, expected in probe["process_evidence"].items())):
        raise ValueError("Review recovery lost its independent exact-request zero-call probe")
    result = {"version": "review-request-master-v1", "status": "pass", "workers": 16,
              "implementation": implementation_hash(), "extension": continuation.extension(),
              "upstream_identity": upstream["identity"], "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
              "regression_sha256": digest(REGRESSION.read_bytes()), "probe_sha256": digest(PROBE.read_bytes()),
              "regression_tests": count, "remaining_logical_calls": parent["remaining_calls"],
              "maximum_new_attempts": parent["remaining_calls"] + parent["remaining_transport_extras"],
              "model_calls": 0, "completed_responses_repeated": False, "unknown_tokens_released": False}
    result["identity"] = digest(result)
    if freeze:
        immutable(PROOF, result)
    elif read_json(PROOF) != result:
        raise ValueError("Frozen review recovery changed")
    return result


def refresh(next_action, stop=None):
    state, account, grant = read_json(BASE / "status.json"), read_json(ACCOUNT), grant_status(GRANT)
    cursor = read_json(EVIDENCE / "cursor.json") if (EVIDENCE / "cursor.json").exists() else {}
    progress = read_json(PROGRESS) if PROGRESS.exists() else {}
    settled = [row["usage"] for row in account["events"] if row["kind"] == "settle"]
    output = Path(cursor.get("output", str(continuation.PRIOR)))
    cause = continuation.failure_summary(output) if stop else None
    state.update(master_version="3.29", ensemble_version=119, local_date="2026-10-20", repair_plan=PLAN,
        status="review_request_stopped" if stop else "review_request_running" if ACTIVE else
               "review_request_ready" if PROOF.exists() else "review_request_validation",
        review_request_cursor=cursor, review_request_execution=read_json(PROOF) if PROOF.exists() else None,
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
    note = (f"\nCurrent execution: master 3.29 / ensemble 119; observed {datetime.now(timezone.utc).isoformat()}.\n"
        f"Status: {state['status']}. Repair: {PLAN}.\n"
        "All fourteen held-out writers are retained, including the separately verified identifier derivation.\n"
        "The first independent review returned no answer or usage; its gateway said the request could not be processed.\n"
        "The same model/profile/schema/instructions have successful prior receipts. The exact cause remains unknown.\n"
        "After native receipt and successful-contract verification, permit one unchanged diagnostic retry after 900 seconds.\n"
        "A repeated unprocessed-request error stops; this message is not added to the general network retry allowlist.\n"
        "The successor retains the failed receipt and its 544,000-token unknown charge, all writer results and denied journals.\n"
        "Require 14 unit reviews and 27 assembled reviews, with 14 remaining transport extras: 55 maximum new attempts.\n"
        "Stop immediately on an unresolved review invocation; report its actual provider diagnostic.\n"
        "No completed response is repurchased. No manual intermediate review or Claude call is needed.\n"
        "Writer limits remain 100,000 input / 32,000 output; proven size failures split to depth 3, at most 14 children/root.\n"
        "Use 16 verification workers; provider calls/accounting remain sequential. Eligible network failures wait 900 seconds.\n"
        "Audits remain 900 seconds/$4. SSD is working storage; historical archive evidence remains read-only.\n"
        f"Calls: {grant['used']}/{grant['maximum']} used; {grant['available']} available; {grant['reserved_remaining']} reserved.\n"
        f"Settlements: {len(settled)}/{len(account['plans'])}; token ceiling {account['reservation_ceiling']:,}/{account['allowance']:,}.\n"
        "Remaining: held-out reviews and reproduction verification; full ZLB inventory/humanization/review/release;\n"
        "independent ZLB reproduction; automatic final admission; human acceptance of the immutable actual ZLB output.\n"
        "Every phase boundary or stop: inspect, settle, verify, repair prospectively, refresh both masters, continue eligible work.\n"
        f"Next: {next_action}\nStop: {stop or 'none'}.\n"
        f"Provider cause: {json.dumps(cause, ensure_ascii=False) if cause else 'none in this successor'}.\n")
    write_json(BASE / "status.json", state)
    for name in ("humanvoice_master_program_v2.md", "ENSEMBLE_MASTER_PROGRAM_2026-09-30.md"):
        path = ROOT / "docs/plans" / name
        content = path.read_text()
        heading = content.split("\n", 1)[0]
        _, tail = content.split("<!-- end-current-benchmark-execution -->", 1)
        intro = ("\nOperational refresh, 20 October 2026: master 3.29 / ensemble 119.\n"
                 "The [bounded review-request recovery](REVIEW_REQUEST_RECOVERY_2026-10-20.md) retains all completed work.\n"
                 "Only final acceptance of the immutable actual ZLB output requires human content review.\n\n")
        path.write_text(heading + "\n" + intro + "<!-- current-benchmark-execution -->" + note
                        + "<!-- end-current-benchmark-execution -->" + tail)
    for path in (BASE / "CURRENT_EXECUTION_20261014.md", EVIDENCE / "STATUS.md"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Review request recovery and execution\n" + note)
    print(json.dumps({"status": state["status"], "next": next_action, "stop": stop, "failure": cause}), flush=True)


def recovery_command(command):
    actual = scope.recovery_command(command)
    return [actual[0], str(ROOT / "tools/review_request_runner.py"), *actual[2:]]


def benchmark_chain(name, row, campaign, bounds):
    if name != "held-out":
        return previous.benchmark_chain(name, row, campaign, bounds)
    proof = continuation.predecessor_evidence()
    snapshot, calls = Path(proof["snapshot"]), proof["remaining_calls"]
    output = BASE / f"{name}-reproduction-{SUFFIX}"
    if not (output / "plan.json").exists():
        write_json(EVIDENCE / "cursor.json", {"phase": "prepare", "output": str(output)})
        refresh("Prepare the exact missing review against the already frozen held-out release.")
        campaign.script("run-manuscript-with-300-grant-20261008.py", "prepare", "--output", output,
            "--snapshot", snapshot, "--stage", "reproduction", "--max-calls", calls,
            "--call-grant", GRANT, "--technical-predecessor", continuation.PRIOR)
    suffix = campaign.SUFFIX
    try:
        campaign.SUFFIX = SUFFIX
        write_json(EVIDENCE / "cursor.json", {"phase": "execute", "output": str(output)})
        refresh("Execute the exact missing review, then remaining reviews; verify and settle before ZLB.")
        campaign.manuscript(name, "reproduction", snapshot, calls, "E7-RB-" + name)
    finally:
        campaign.SUFFIX = suffix
    packets = list((snapshot / "release").iterdir())
    if len(packets) != 1:
        raise ValueError("Final admission requires one immutable packet")
    progress = read_json(PROGRESS)
    progress.setdefault("reproductions", {})[name] = {"snapshot": str(snapshot),
        "output": str(output / "reproduction"), "full_call_bound": 55}
    write_json(PROGRESS, progress)
    write_json(EVIDENCE / "cursor.json", {"phase": "verified_reproduction", "output": str(output)})
    refresh("Held-out reproduction independently verified and settled; continue to full ZLB.")
    return {"snapshot": snapshot, "packet": packets[0], "reproduction": output / "reproduction"}


def run():
    global ACTIVE
    with ExitStack() as bindings:
        bindings.callback(setattr, scope, "RUNNER", scope.RUNNER)
        scope.RUNNER = ROOT / "tools/review_request_runner.py"
        for module in (previous, previous.previous):
            for name, value in (("refresh", refresh), ("continuation", continuation), ("recovery_command", recovery_command),
                                ("EVIDENCE", EVIDENCE), ("SUFFIX", SUFFIX)):
                bindings.callback(setattr, module, name, getattr(module, name))
                setattr(module, name, value)
        bindings.callback(setattr, previous.previous, "benchmark_chain", previous.previous.benchmark_chain)
        previous.previous.benchmark_chain = benchmark_chain
        ACTIVE = True
        try:
            refresh("Verified review recovery activated; prepare its bounded successor.")
            previous.previous.run()
        finally:
            ACTIVE = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("diagnose", "verify", "freeze", "activate"))
    parser.add_argument("--live", action="store_true")
    arguments = parser.parse_args()
    if arguments.action == "activate" and not arguments.live:
        parser.error("Execution requires --live")
    regressions()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with (BASE / "inventory-prefix-controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with scope.accounting_scope(), continuation.pipeline(), cached_parallel_verification(
                workers=16, progress=EVIDENCE / f"controller-{time.time_ns()}.json"):
            try:
                if arguments.action in {"diagnose", "activate"} and not continuation.DIAGNOSTIC.exists():
                    refresh("Verify the failed receipt, all retained writers and the successful request contract.")
                    with scope.verification_only():
                        continuation.diagnose()
                if arguments.action == "diagnose":
                    refresh("Diagnosis passes; run the independent zero-call probe before activating any retry.")
                    return 0
                if arguments.action == "activate" and not PROBE.exists():
                    from tools.probe_review_request_20261020 import probe

                    refresh("Run the independent zero-provider probe of the exact missing review.")
                    probe(PROBE.parent)
                result = verify(freeze=arguments.action == "freeze" or arguments.action == "activate" and not PROOF.exists())
                print(json.dumps({"status": result["status"], "regression_tests": result["regression_tests"]}), flush=True)
                if arguments.action == "activate":
                    run()
                else:
                    refresh("Review recovery proof passes; continue the supervised program.")
            except BaseException as error:
                refresh("Inspect the retained cause, repair prospectively and refresh before further execution.",
                        type(error).__name__ + ": " + str(error))
                raise
    return 0


if __name__ == "__main__":
    with continuation.previous.archive.access():
        raise SystemExit(main())
