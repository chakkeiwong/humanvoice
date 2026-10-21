"""Verify the punctuation repair, resume exact inventory and continue ZLB."""

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
from tools import inventory_coverage_continuation as continuation
from tools import inventory_punctuation as punctuation
from tools.inventory_coverage_runner import reproduction_dispatch
from tools import run_zlb_ssd_20261021 as previous
from tools.automatic_program_account import ACCOUNT
from tools.parallel_verification_replay import cached_parallel_verification

BASE, EVIDENCE, STAGE = continuation.BASE, continuation.EVIDENCE, continuation.STAGE
scope, inventory = continuation.inventory.scope, continuation.inventory
GRANT, PROGRESS = previous.GRANT, previous.PROGRESS
PROOF, REGRESSION = EVIDENCE / "verification.json", EVIDENCE / "regression.xml"
PLAN = "docs/plans/INVENTORY_PUNCTUATION_REPAIR_2026-10-22.md"
FILES = (*continuation.FILES, "tools/inventory_coverage_runner.py", "tools/inventory_coverage_worker.py",
         "tools/probe_inventory_coverage_20261022.py", "tools/run_inventory_coverage_20261022.py",
         "tools/supervise_inventory_coverage_20261022.py", "tests/test_inventory_punctuation.py",
         "tests/test_inventory_coverage_continuation.py", PLAN)
ACTIVE = False


def verify(*, freeze=False):
    suites = ET.parse(REGRESSION).getroot().findall("testsuite")
    cases = {case.attrib["name"].split("[")[0] for suite in suites for case in suite.findall("testcase")}
    required = {"test_actual_retained_zlb_colon_maps_to_supported_multiplier_without_response_changes",
                "test_incomplete_or_unproven_judgments_stay_blocking", "test_execution_and_baseline_replay_derive_identical_evidence",
                "test_native_baseline_and_planning_accept_reproducible_punctuation",
                "test_replay_preserves_receipts_and_calls_provider_only_after_prefix",
                "test_changed_replay_inputs_refuse_provider_calls", "test_lineage_rejects_changed_or_spent_stage",
                "test_lineage_claim_uses_exact_plan_and_charges_only_new_requests",
                "test_controller_routes_only_zlb_inventory", "test_reproduction_dispatch_routes_and_restores",
                "test_separate_reproduction_verifier_uses_same_worker_as_launch"}
    if not suites or not required <= cases or any(int(suite.attrib.get(key, 0)) for suite in suites
            for key in ("failures", "errors", "skipped")):
        raise ValueError("Coverage repair requires passing native consumer and adversarial regressions")
    upstream, predecessor = previous.verify(), continuation.predecessor_evidence()
    probe = read_json(continuation.PROBE / "verification.json")
    process = read_json(continuation.PROBE / "process.json")
    if (probe["status"] != "pass" or probe["model_calls"] != 0 or probe["inherited_calls"] != 18
            or probe["predecessor_identity"] != digest(predecessor)
            or probe["files"] != {name: digest((ROOT / name).read_bytes()) for name in continuation.FILES}
            or probe["policy"] != punctuation.policy(continuation.PROBE / "snapshot")
            or probe["replay_sha256"] != digest((continuation.PROBE / "replay-log.json").read_bytes())
            or process["status"] != "pass" or process["pid"] == process["parent_pid"]
            or not probe["authority_unchanged"] or not probe["predecessor_unchanged"]):
        raise ValueError("Coverage repair lacks its independent zero-provider prefix probe")
    result = {"version": continuation.VERSION, "status": "pass", "implementation": implementation_hash(),
        "upstream_identity": upstream["identity"], "predecessor_identity": digest(predecessor),
        "probe_sha256": digest((continuation.PROBE / "verification.json").read_bytes()),
        "probe_process_sha256": digest((continuation.PROBE / "process.json").read_bytes()),
        "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
        "regression_sha256": digest(REGRESSION.read_bytes()),
        "regression_tests": sum(int(suite.attrib["tests"]) for suite in suites),
        "inherited_calls": 18, "model_calls": 0, "workers": 16,
        "remaining_logical_calls": 522, "transport_extras": 16}
    result["identity"] = digest(result)
    if freeze:
        continuation.retained.immutable(PROOF, result)
    elif read_json(PROOF) != result:
        raise ValueError("Frozen coverage repair changed")
    return result


def refresh(next_action, stop=None):
    state, account, grant = read_json(BASE / "status.json"), read_json(ACCOUNT), continuation.grant_status(GRANT)
    progress = read_json(PROGRESS) if PROGRESS.exists() else {}
    settled = sum(event["kind"] == "settle" for event in account["events"])
    terminal = read_json(STAGE / "execution.json") if (STAGE / "execution.json").exists() else {}
    state.update(master_version="3.35", ensemble_version=125, local_date="2026-10-22", repair_plan=PLAN,
        status="inventory_coverage_stopped" if stop else "inventory_coverage_running" if ACTIVE else
               "inventory_coverage_ready" if PROOF.exists() else "inventory_coverage_validation",
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
    note = (f"\nCurrent execution: master 3.35 / ensemble 125; observed {datetime.now(timezone.utc).isoformat()}.\n"
        f"Status: {state['status']}. Repair: {PLAN}.\n"
        "ZLB stopped after 18 complete positive calls because a standalone colon lacked concept ownership.\n"
        "The original transport-only continuation correctly refused this completed validation failure.\n"
        "A prospective deterministic rule attaches only unambiguous punctuation bracketed by already supported math spans.\n"
        "Raw critic verdicts, source bytes, receipts and the failed stage stay unchanged; native baseline replay reproduces the derivation.\n"
        "Replay the exact 18 responses, then execute 522 remaining logical calls with 16 existing transport extras.\n"
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
        intro = ("\nOperational refresh, 22 October 2026: master 3.35 / ensemble 125.\n"
                 "The [inventory punctuation repair](INVENTORY_PUNCTUATION_REPAIR_2026-10-22.md) preserves completed judgments and native admission checks.\n\n")
        path.write_text(content.split("\n", 1)[0] + "\n" + intro + "<!-- current-benchmark-execution -->" + note
                        + "<!-- end-current-benchmark-execution -->" + content.split("<!-- end-current-benchmark-execution -->", 1)[1])
    for path in (BASE / "CURRENT_EXECUTION_20261014.md", EVIDENCE / "STATUS.md"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Inventory punctuation recovery\n" + note)
    print(json.dumps({"status": state["status"], "next": next_action, "stop": stop}), flush=True)


def command(filename, *arguments):
    actual = scope.command(filename, *arguments)
    if filename in scope.NATIVE:
        return [actual[0], str(ROOT / "tools/inventory_coverage_runner.py"), *actual[2:]]
    return actual


def recovery_command(arguments):
    actual = scope.recovery_command(arguments)
    return [actual[0], str(ROOT / "tools/inventory_coverage_runner.py"), *actual[2:]]


def run_inventory(name, snapshot, maximum, campaign, refresh_callback):
    if name != "zlb" or Path(snapshot) != continuation.workspace.SOURCE or maximum != 540:
        raise ValueError("Coverage continuation requires the original full ZLB inventory scope")
    terminal = read_json(STAGE / "execution.json") if (STAGE / "execution.json").exists() else None
    if terminal is None:
        refresh_callback("Resume ZLB inventory from the first unrun request, reusing all 18 completed responses.")
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "execute-child", "--live"], cwd=ROOT, check=True)
        terminal = read_json(STAGE / "execution.json")
    if terminal["status"] != "pass":
        raise ValueError("Retained coverage continuation is " + terminal["status"] + "; inspect its evidence before any new allocation")
    if not (STAGE / "boundary-checkpoint.json").exists():
        continuation.verify_completed()
        subprocess.run(command("verify-manuscript-boundary-20261007.py", STAGE.name, "--phase", "E6-B-zlb",
            "--next", "Continue ZLB humanization after repaired inventory admission."), cwd=ROOT, check=True)
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
    boundary = previous.previous
    identifier = boundary.identifier
    engine = identifier.previous.previous.previous.parallel.previous.engine
    prefix = engine.previous.previous.previous.previous.previous
    native_inventory = prefix.inventory
    native_command = scope.command

    def route(name, *arguments):
        return run_inventory(name, *arguments) if name == "zlb" else native_inventory(name, *arguments)

    def dispatch(filename, *arguments):
        actual = native_command(filename, *arguments)
        return [actual[0], str(ROOT / "tools/inventory_coverage_runner.py"), *actual[2:]] if filename in scope.NATIVE else actual

    with ExitStack() as bindings, punctuation.runtime():
        for module, name, value in ((prefix, "inventory", route), (boundary, "refresh", refresh),
                                    (boundary, "EVIDENCE", EVIDENCE), (boundary, "recovery_command", recovery_command),
                                    (scope, "command", dispatch)):
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
    with inventory.history.archive.access(), scope.accounting_scope(), inventory.pipeline(), punctuation.runtime(), reproduction_dispatch():
        if arguments.action == "refresh":
            refresh("Finish regression and native replay verification, freeze repair, then resume ZLB.")
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
                        refresh("Coverage repair is verified and prepared; continue supervised ZLB execution.")
                    print(json.dumps({"status": result["status"], "regression_tests": result["regression_tests"]}))
                except BaseException as error:
                    refresh("Inspect retained failure, repair prospectively, verify and refresh before continuing.",
                            type(error).__name__ + ": " + str(error)[:2000])
                    raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
