"""Verify the sentence-context repair, refresh both masters, and continue ZLB."""

import argparse
import fcntl
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import digest, implementation_hash, read_json, write_json
from tools import inventory_context_continuation as continuation
from tools import inventory_context as context
from tools import run_inventory_coverage_20261022 as previous
from tools.inventory_context_runner import reproduction_dispatch
from tools.automatic_program_account import ACCOUNT
from tools.parallel_verification_replay import cached_parallel_verification

BASE, EVIDENCE, STAGE = continuation.BASE, continuation.EVIDENCE, continuation.STAGE
inventory, scope = continuation.inventory, continuation.inventory.scope
GRANT, PROGRESS = previous.GRANT, previous.PROGRESS
PROOF, REGRESSION = EVIDENCE / "verification.json", EVIDENCE / "regression.xml"
PLAN = "docs/plans/INVENTORY_CONTEXT_REPAIR_2026-10-22.md"
FILES = (*continuation.FILES, "tools/inventory_context_runner.py", "tools/inventory_context_worker.py",
         "tools/probe_inventory_context_20261022.py", "tools/run_inventory_context_20261022.py",
         "tools/supervise_inventory_context_20261022.py", "tests/test_inventory_context.py",
         "tests/test_inventory_context_continuation.py", PLAN)
ACTIVE = False


def verify(*, freeze=False):
    suites = ET.parse(REGRESSION).getroot().findall("testsuite")
    cases = {case.attrib["name"].split("[")[0] for suite in suites for case in suite.findall("testcase")}
    required = {"test_actual_failed_window_gets_complete_math_and_sentence_context",
                "test_native_context_repair_replays_negative_and_positive_judgments",
                "test_repair_exhaustion_stays_blocking", "test_unmarked_snapshot_keeps_legacy_requests",
                "test_context_lineage_retains_all_responses_and_network_charge",
                "test_context_controller_routes_only_zlb", "test_context_worker_used_for_launch_and_verification"}
    if not suites or not required <= cases or any(int(suite.attrib.get(key, 0)) for suite in suites
            for key in ("failures", "errors", "skipped")):
        raise ValueError("Context repair requires complete native and adversarial regressions")
    upstream, predecessor = previous.verify(), continuation.predecessor_evidence()
    probe, process = read_json(continuation.PROBE / "verification.json"), read_json(continuation.PROBE / "process.json")
    if (probe["status"] != "pass" or probe["model_calls"] != 0 or probe["inherited_calls"] != 24
            or probe["superseded_calls_retained"] != 3 or probe["predecessor_identity"] != digest(predecessor)
            or probe["files"] != {name: digest((ROOT / name).read_bytes()) for name in continuation.FILES}
            or probe["policy"] != context.policy(continuation.PROBE / "snapshot", continuation.STARTS)
            or probe["replay_sha256"] != digest((continuation.PROBE / "replay-log.json").read_bytes())
            or process["status"] != "pass" or process["pid"] == process["parent_pid"]
            or not probe["authority_unchanged"] or not probe["predecessor_unchanged"]):
        raise ValueError("Context repair lacks an independent exact-prefix probe")
    result = {"version": continuation.VERSION, "status": "pass", "implementation": implementation_hash(),
        "upstream_identity": upstream["identity"], "predecessor_identity": digest(predecessor),
        "probe_sha256": digest((continuation.PROBE / "verification.json").read_bytes()),
        "process_sha256": digest((continuation.PROBE / "process.json").read_bytes()),
        "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
        "regression_sha256": digest(REGRESSION.read_bytes()),
        "regression_tests": sum(int(suite.attrib["tests"]) for suite in suites),
        "inherited_calls": 24, "superseded_calls_retained": 3, "model_calls": 0, "workers": 16,
        "remaining_base_calls": 516, "maximum_repair_calls": 24, "transport_extras": 16}
    result["identity"] = digest(result)
    if freeze:
        continuation.retained.immutable(PROOF, result)
    elif read_json(PROOF) != result:
        raise ValueError("Frozen inventory context repair changed")
    return result


def refresh(next_action, stop=None):
    state, account, grant = read_json(BASE / "status.json"), read_json(ACCOUNT), continuation.grant_status(GRANT)
    progress = read_json(PROGRESS) if PROGRESS.exists() else {}
    settled = sum(event["kind"] == "settle" for event in account["events"])
    terminal = read_json(STAGE / "execution.json") if (STAGE / "execution.json").exists() else {}
    state.update(master_version="3.36", ensemble_version=126, local_date="2026-10-22", repair_plan=PLAN,
        status="inventory_context_stopped" if stop else "inventory_context_running" if ACTIVE else
               "inventory_context_ready" if PROOF.exists() else "inventory_context_validation",
        next_action=next_action, stop=stop, failure_cause=stop,
        active_model_execution=str(STAGE) if ACTIVE and not stop and terminal.get("status") == "executing" else None,
        resume_controller=str(Path(__file__).relative_to(ROOT)), zlb_working_snapshot=str(continuation.SNAPSHOT),
        parallel_workers=16, network_retry_seconds=900,
        held_out_assembled_reviews={"passed": 28, "required": 28, "separate_boundary_pass": True},
        current_call_grant={key: grant[key] for key in ("identity", "used", "available", "reserved_remaining")},
        current_account={"plans": len(account["plans"]), "settled": settled, "unsettled_plans": len(account["plans"]) - settled,
                         "effective_ceiling": account["reservation_ceiling"], "allowance": account["allowance"]})
    for phase in state["phases"]:
        if phase["id"] == "E6-B" and phase["status"] != "completed":
            phase["status"] = "repair_stopped" if stop else "running" if ACTIVE else "repair_validation"
        if phase["id"] == "E7-RB" and phase["status"] != "completed":
            phase["status"] = "held_out_complete_zlb_pending"
        if (phase["id"] == "E6-B" and set(progress.get("humanizations", {})) == {"held-out", "zlb"}
                or phase["id"] == "E7-RB" and set(progress.get("reproductions", {})) == {"held-out", "zlb"}):
            phase["status"] = "completed"
    if progress.get("final_admission"):
        state.update(status="awaiting_final_immutable_ZLB_acceptance", resume_controller=None, active_model_execution=None)
    note = (f"\nCurrent execution: master 3.36 / ensemble 126; observed {datetime.now(timezone.utc).isoformat()}.\n"
        f"Status: {state['status']}. Repair: {PLAN}.\n"
        "The punctuation repair succeeded. Window 10 then stopped on two unresolved fragments: fixed windows cut sentences and coverage omitted math context.\n"
        "Preserve all 27 responses and the charged network failure. Replay 24 accepted requests; replace the rejected three-call window with complete sentence context.\n"
        "Future windows expand to sentence boundaries within 10 KiB; coverage receives all math and prose context.\n"
        "Automatic semantic repairs regenerate concepts and run both independent critics: at most two repairs/window and eight repairs/stage. Every rejected response remains replayable.\n"
        "Reserve 516 base requests, up to 24 changed-input repair requests and 16 response-free transport retries. Existing aggregate authority is unchanged.\n"
        f"Independent zero-provider probe: {'pass' if (continuation.PROBE / 'verification.json').exists() else 'pending'}.\n"
        "Held-out reproduction, all 28 assembled leaf reviews and separate boundary verification pass and are reused.\n"
        f"SSD snapshot: {continuation.SNAPSHOT.relative_to(ROOT)}. Archive remains read-only.\n"
        "Use 16 verification workers; provider calls/accounting remain sequential. Eligible network retries wait 900 seconds.\n"
        "Writer: 100k input/32k output. Assembled reviewer: 80k/32k. Splits: depth 3, 14 children/root. Audits: 900 seconds/$4.\n"
        f"Calls: {grant['used']}/{grant['maximum']} used; {grant['available']} available; {grant['reserved_remaining']} reserved.\n"
        f"Settlements: {settled}/{len(account['plans'])}; token ceiling {account['reservation_ceiling']:,}/{account['allowance']:,}.\n"
        "Remaining: full ZLB inventory/humanization/review/release; independent ZLB reproduction; automatic final admission; final human acceptance.\n"
        "If later split reservations exceed 600 slots, implement and verify bounded batching before launch.\n"
        "At every boundary or stop: inspect, settle, verify, repair and refresh both masters. Only final immutable output acceptance requires human review.\n"
        f"Next: {next_action}\nStop: {stop or 'none'}.\n")
    write_json(BASE / "status.json", state)
    for name in ("humanvoice_master_program_v2.md", "ENSEMBLE_MASTER_PROGRAM_2026-09-30.md"):
        path = ROOT / "docs/plans" / name
        content = path.read_text()
        intro = ("\nOperational refresh, 22 October 2026: master 3.36 / ensemble 126.\n"
                 "The [inventory context repair](INVENTORY_CONTEXT_REPAIR_2026-10-22.md) restores complete source context and bounds automatic semantic repair.\n\n")
        path.write_text(content.split("\n", 1)[0] + "\n" + intro + "<!-- current-benchmark-execution -->" + note
                       + "<!-- end-current-benchmark-execution -->" + content.split("<!-- end-current-benchmark-execution -->", 1)[1])
    for path in (BASE / "CURRENT_EXECUTION_20261014.md", EVIDENCE / "STATUS.md"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Inventory context recovery\n" + note)
    print(json.dumps({"status": state["status"], "next": next_action, "stop": stop}), flush=True)


def command(filename, *arguments):
    actual = scope.command(filename, *arguments)
    return [actual[0], str(ROOT / "tools/inventory_context_runner.py"), *actual[2:]] if filename in scope.NATIVE else actual


def recovery_command(arguments):
    actual = scope.recovery_command(arguments)
    return [actual[0], str(ROOT / "tools/inventory_context_runner.py"), *actual[2:]]


def run_inventory(name, snapshot, maximum, campaign, refresh_callback):
    if name != "zlb" or Path(snapshot) != continuation.previous.workspace.SOURCE or maximum != 540:
        raise ValueError("Context continuation requires the original ZLB inventory scope")
    terminal = read_json(STAGE / "execution.json") if (STAGE / "execution.json").exists() else None
    if terminal is None:
        refresh_callback("Replay 24 accepted requests, then execute the repaired ZLB inventory with bounded semantic repairs.")
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "execute-child", "--live"], cwd=ROOT, check=True)
        terminal = read_json(STAGE / "execution.json")
    if terminal["status"] != "pass":
        raise ValueError("Context inventory is " + terminal["status"] + "; inspect before any new allocation")
    if not (STAGE / "boundary-checkpoint.json").exists():
        continuation.verify_completed()
        subprocess.run(command("verify-manuscript-boundary-20261007.py", STAGE.name, "--phase", "E6-B-zlb",
            "--next", "Continue ZLB humanization after context-repaired inventory admission."), cwd=ROOT, check=True)
    if (read_json(STAGE / "boundary-checkpoint.json")["status"] != "pass_settled_and_separately_verified"
            or read_json(STAGE / "coverage-verification.json")["status"] != "pass"):
        raise ValueError("ZLB inventory lacks its separate native boundary")
    progress = read_json(PROGRESS)
    progress.setdefault("inventories", {})[name] = {"output": str(STAGE), "snapshot": str(continuation.SNAPSHOT)}
    write_json(PROGRESS, progress)
    refresh_callback("ZLB inventory independently verified and settled; continue humanization.")
    return continuation.SNAPSHOT


def run():
    global ACTIVE
    boundary = previous.previous.previous
    engine = boundary.identifier.previous.previous.previous.parallel.previous.engine
    prefix = engine.previous.previous.previous.previous.previous
    native_inventory, native_command = prefix.inventory, scope.command

    def route(name, *arguments):
        return run_inventory(name, *arguments) if name == "zlb" else native_inventory(name, *arguments)

    def dispatch(filename, *arguments):
        actual = native_command(filename, *arguments)
        return [actual[0], str(ROOT / "tools/inventory_context_runner.py"), *actual[2:]] if filename in scope.NATIVE else actual

    with ExitStack() as bindings, context.runtime():
        for module, name, value in ((prefix, "inventory", route), (boundary, "refresh", refresh),
                (boundary, "EVIDENCE", EVIDENCE), (boundary, "recovery_command", recovery_command), (scope, "command", dispatch)):
            bindings.callback(setattr, module, name, getattr(module, name))
            setattr(module, name, value)
        ACTIVE = True
        try:
            boundary.run()
        finally:
            ACTIVE = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("refresh", "freeze", "verify", "activate", "execute-child"))
    parser.add_argument("--live", action="store_true")
    arguments = parser.parse_args()
    if arguments.action in {"activate", "execute-child"} and not arguments.live:
        parser.error("Execution requires --live")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with inventory.history.archive.access(), scope.accounting_scope(), inventory.pipeline(), context.runtime(), reproduction_dispatch():
        if arguments.action == "refresh":
            refresh("Validate complete source context and bounded repair; freeze the proof, then resume ZLB.")
            return 0
        with cached_parallel_verification(workers=16, progress=EVIDENCE / f"controller-{time.time_ns()}.json"):
            if arguments.action == "execute-child":
                verify()
                return 0 if continuation.execute(grant=GRANT)["status"] == "pass" else 1
            with (BASE / "inventory-prefix-controller.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    result = verify(freeze=arguments.action == "freeze")
                    if arguments.action in {"freeze", "activate"} and not (STAGE / "plan.json").exists():
                        continuation.prepare(grant=GRANT)
                    if arguments.action == "activate":
                        run()
                    else:
                        refresh("Context repair is verified and prepared; continue supervised ZLB execution.")
                    print(json.dumps({"status": result["status"], "regression_tests": result["regression_tests"]}))
                except BaseException as error:
                    refresh("Inspect retained failure, repair prospectively, verify and refresh before continuing.",
                            type(error).__name__ + ": " + str(error)[:2000])
                    raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
