"""Verify an SSD ZLB workspace and resume the completed held-out program."""

import argparse
import fcntl
import json
import os
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
from tools import inventory_stage_runtime as inventory
from tools import zlb_stage_runner as runner
from tools import run_review_boundary_20261021 as previous
from tools import zlb_ssd_workspace as workspace
from tools.automatic_program_account import ACCOUNT
from tools.inventory_transport_continuation import immutable, tree_hashes
from tools.parallel_verification_replay import cached_parallel_verification

BASE, EVIDENCE = workspace.BASE, workspace.EVIDENCE
continuation, scope = previous.continuation, previous.scope
GRANT, PROGRESS = previous.GRANT, previous.PROGRESS
PROOF, PROBE = EVIDENCE / "verification.json", EVIDENCE / "preparation-probe.json"
REGRESSION = EVIDENCE / "regression-final.xml"
PLAN = "docs/plans/ZLB_SSD_WORKSPACE_2026-10-21.md"
FILES = ("tools/zlb_ssd_workspace.py", "tools/run_zlb_ssd_20261021.py",
         "tools/supervise_zlb_ssd_20261021.py", *inventory.FILES, "tests/test_zlb_ssd_workspace.py", PLAN)
ACTIVE = False


def prepare_child():
    workspace.ensure(allow_progress=True)
    if (workspace.STAGE / "plan.json").exists():
        raise ValueError("Preparation probe must not replace a retained plan")
    before = ACCOUNT.read_bytes(), GRANT.read_bytes(), tree_hashes(workspace.SOURCE)
    original = sys.argv
    command = ["run-manuscript-with-300-grant-20261008.py", "prepare", "--output", str(workspace.STAGE),
               "--snapshot", str(workspace.WORK), "--stage", "inventory", "--max-calls", "540", "--call-grant", str(GRANT)]
    sys.argv = [str(ROOT / "tools/zlb_stage_runner.py"), *command]
    try:
        with scope.verification_only():
            try:
                runner.main()
            except SystemExit as error:
                if error.code not in (None, 0):
                    raise
    finally:
        sys.argv = original
    if before != (ACCOUNT.read_bytes(), GRANT.read_bytes(), tree_hashes(workspace.SOURCE)):
        raise ValueError("Native ZLB preparation changed account, grant or archive")
    plan = inventory.validate_extension(read_json(workspace.STAGE / "plan.json"))
    if (plan["snapshot"] != str(workspace.WORK) or plan["stage"] != "inventory" or len(plan["calls"]) != 540
            or (workspace.STAGE / "allocation-ledger.json").exists()):
        raise ValueError("Native ZLB preparation changed stage scope or transmitted a call")
    immutable(PROBE, {"status": "pass", "pid": os.getpid(), "parent_pid": os.getppid(),
        "model_calls": 0, "plan_sha256": digest((workspace.STAGE / "plan.json").read_bytes()),
        "origin_sha256": digest(workspace.ORIGIN.read_bytes()), "account_bytes_unchanged": True,
        "grant_bytes_unchanged": True, "archive_bytes_unchanged": True})


def prepare():
    workspace.ensure(allow_progress=True)
    if not PROBE.exists():
        attempt = f"preparation-{time.time_ns()}"
        with (EVIDENCE / (attempt + ".stdout.log")).open("xb") as stdout, (EVIDENCE / (attempt + ".stderr.log")).open("xb") as stderr:
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "prepare-child"], cwd=ROOT,
                           stdout=stdout, stderr=stderr, check=True, timeout=900)


def verify(*, freeze=False):
    suites = ET.parse(REGRESSION).getroot().findall("testsuite")
    cases = {case.attrib["name"].split("[")[0] for suite in suites for case in suite.findall("testcase")}
    required = {"test_workspace_preserves_archive_and_allows_new_outputs", "test_workspace_rejects_changed_evidence",
                "test_workspace_routing_checks_source_and_retained_plan", "test_ssd_controller_routes_and_restores",
                "test_native_preparation_binds_ssd_snapshot", "test_inventory_runner_uses_native_scoped_preparation",
                "test_inventory_policy_rejects_scope_changes", "test_inventory_policy_leaves_candidate_planning_intact",
                "test_inventory_runner_restores_execution_and_boundary", "test_inventory_native_retry_preserves_failed_charge"}
    if not suites or not required <= cases or any(int(suite.attrib.get(key, 0)) for suite in suites
            for key in ("failures", "errors", "skipped")):
        raise ValueError("SSD recovery requires passing source and native preparation regressions")
    upstream, origin, probe = previous.verify(), workspace.ensure(allow_progress=True), read_json(PROBE)
    boundary = read_json(previous.STAGE / "boundary-checkpoint.json")
    if (boundary["status"] != "pass_settled_and_separately_verified"
            or boundary["verification_sha256"] != digest((previous.STAGE / "separate-verification.json").read_bytes())
            or probe["status"] != "pass" or probe["model_calls"] != 0 or probe["pid"] == probe["parent_pid"]
            or not all(probe[key] for key in ("account_bytes_unchanged", "grant_bytes_unchanged", "archive_bytes_unchanged"))
            or probe["origin_sha256"] != digest(workspace.ORIGIN.read_bytes())
            or probe["plan_sha256"] != digest((workspace.STAGE / "plan.json").read_bytes())):
        raise ValueError("SSD recovery lost native preparation or completed held-out boundary evidence")
    result = {"version": workspace.VERSION, "status": "pass", "implementation": implementation_hash(),
        "upstream_identity": upstream["identity"], "origin_identity": origin["identity"],
        "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
        "regression_sha256": digest(REGRESSION.read_bytes()), "regression_tests": sum(int(suite.attrib["tests"]) for suite in suites),
        "probe_sha256": digest(PROBE.read_bytes()), "stage_plan_sha256": probe["plan_sha256"],
        "held_out_boundary_sha256": digest((previous.STAGE / "boundary-checkpoint.json").read_bytes()),
        "model_calls": 0, "archive_changed": False, "workers": 16}
    result["identity"] = digest(result)
    if freeze:
        immutable(PROOF, result)
    elif read_json(PROOF) != result:
        raise ValueError("Frozen SSD workspace repair changed")
    return result


def refresh(next_action, stop=None):
    state, account, grant = read_json(BASE / "status.json"), read_json(ACCOUNT), previous.grant_status(GRANT)
    progress = read_json(PROGRESS) if PROGRESS.exists() else {}
    settled = sum(event["kind"] == "settle" for event in account["events"])
    active = []
    for entry in account["plans"]:
        output = Path(entry["output"])
        if (output / "execution.json").exists() and read_json(output / "execution.json").get("status") == "executing":
            active.append(str(output))
    state.update(master_version="3.34", ensemble_version=124, local_date="2026-10-21", repair_plan=PLAN,
        status="zlb_ssd_stopped" if stop else "zlb_ssd_running" if ACTIVE else "zlb_ssd_ready" if PROOF.exists() else "zlb_ssd_validation",
        next_action=next_action, stop=stop, failure_cause=stop, active_model_execution=active[0] if ACTIVE and not stop and len(active) == 1 else None,
        resume_controller=str(Path(__file__).relative_to(ROOT)), parallel_workers=16, network_retry_seconds=900,
        zlb_working_snapshot=str(workspace.WORK), held_out_assembled_reviews={"passed": 28, "required": 28, "separate_boundary_pass": True},
        current_call_grant={key: grant[key] for key in ("identity", "used", "available", "reserved_remaining")},
        current_account={"plans": len(account["plans"]), "settled": settled, "unsettled_plans": len(account["plans"]) - settled,
                         "effective_ceiling": account["reservation_ceiling"], "allowance": account["allowance"]})
    for phase in state["phases"]:
        if phase["id"] == "E6-B" and phase["status"] != "completed":
            phase["status"] = "repair_stopped" if stop else "running" if ACTIVE else "repair_ready"
        if phase["id"] == "E7-RB" and phase["status"] != "completed":
            phase["status"] = "held_out_complete_zlb_pending"
        if (phase["id"] == "E6-B" and set(progress.get("humanizations", {})) == {"held-out", "zlb"}
                or phase["id"] == "E7-RB" and set(progress.get("reproductions", {})) == {"held-out", "zlb"}):
            phase["status"] = "completed"
    if progress.get("final_admission"):
        state.update(status="awaiting_final_immutable_ZLB_acceptance", resume_controller=None, active_model_execution=None)
    note = (f"\nCurrent execution: master 3.34 / ensemble 124; observed {datetime.now(timezone.utc).isoformat()}.\n"
        f"Status: {state['status']}. Repair: {PLAN}.\n"
        "Held-out reproduction, all 28 assembled leaf reviews, separate boundary verification and settlement pass.\n"
        "Full ZLB preparation stopped before any provider call because its old working snapshot had been archived read-only.\n"
        "Independent SSD preparation then exposed candidate-only math/redline planning on inventory.\n"
        "Inventory now uses native inventory validation, bounded 900-second transport recovery and current historical accounting readers.\n"
        "Candidate writer/review/redline planning remains scoped to candidate stages; every preparation attempt keeps separate logs.\n"
        f"Continue on SSD at {workspace.WORK.relative_to(ROOT)} using a byte-verified copy of the original snapshot.\n"
        "Keep archive aliases, historical proofs, receipts and all failed charges unchanged. Reuse the completed held-out boundary.\n"
        "Native independent preparation must pass with zero provider calls and unchanged account, grant and archive bytes.\n"
        "Use 16 verification workers with sequential provider calls/accounting; eligible network failures wait 900 seconds.\n"
        "Writer limits: 100k input / 32k output. Assembled reviewer: 80k / 32k. Splits: depth 3, 14 children/root. Audits: 900 seconds/$4.\n"
        f"Calls: {grant['used']}/{grant['maximum']} used; {grant['available']} available; {grant['reserved_remaining']} reserved.\n"
        f"Settlements: {settled}/{len(account['plans'])}; token ceiling {account['reservation_ceiling']:,}/{account['allowance']:,}.\n"
        "Remaining: full ZLB inventory/humanization/review/release; independent ZLB reproduction; automatic final admission; final human acceptance.\n"
        "If split reservations exceed 600 slots, implement and verify bounded batching before that stage.\n"
        "At every boundary or stop: inspect, settle, verify, repair and refresh both masters. Only final immutable output acceptance requires human review.\n"
        f"Next: {next_action}\nStop: {stop or 'none'}.\n")
    write_json(BASE / "status.json", state)
    for name in ("humanvoice_master_program_v2.md", "ENSEMBLE_MASTER_PROGRAM_2026-09-30.md"):
        path = ROOT / "docs/plans" / name
        content = path.read_text()
        intro = ("\nOperational refresh, 21 October 2026: master 3.34 / ensemble 124.\n"
                 "The [ZLB SSD workspace repair](ZLB_SSD_WORKSPACE_2026-10-21.md) preserves the completed held-out test and archived evidence.\n\n")
        path.write_text(content.split("\n", 1)[0] + "\n" + intro + "<!-- current-benchmark-execution -->" + note
                        + "<!-- end-current-benchmark-execution -->" + content.split("<!-- end-current-benchmark-execution -->", 1)[1])
    for path in (BASE / "CURRENT_EXECUTION_20261014.md", EVIDENCE / "STATUS.md"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# ZLB SSD workspace recovery\n" + note)
    print(json.dumps({"status": state["status"], "next": next_action, "stop": stop}), flush=True)


def recovery_command(command):
    actual = scope.recovery_command(command)
    return [actual[0], str(ROOT / "tools/zlb_stage_runner.py"), *actual[2:]]


def run():
    global ACTIVE
    review_size = previous.previous.previous
    native = review_size.benchmark_chain
    native_command = scope.command

    def benchmark(name, row, campaign, bounds):
        return native(name, workspace.route(name, row), campaign, bounds)

    def command(filename, *arguments):
        actual = native_command(filename, *arguments)
        if filename in scope.NATIVE:
            return [actual[0], str(ROOT / "tools/zlb_stage_runner.py"), *actual[2:]]
        return actual

    with ExitStack() as bindings:
        for module, name, value in ((previous, "refresh", refresh), (previous, "EVIDENCE", EVIDENCE),
                                    (previous, "recovery_command", recovery_command),
                                    (scope, "command", command),
                                    (review_size, "benchmark_chain", benchmark)):
            bindings.callback(setattr, module, name, getattr(module, name))
            setattr(module, name, value)
        ACTIVE = True
        try:
            previous.run()
        finally:
            ACTIVE = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare-child", "prepare", "refresh", "freeze", "verify", "activate"))
    parser.add_argument("--live", action="store_true")
    arguments = parser.parse_args()
    if arguments.action == "activate" and not arguments.live:
        parser.error("Execution requires --live")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if arguments.action == "prepare-child":
        prepare_child()
        return 0
    with (BASE / "inventory-prefix-controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with scope.accounting_scope(), inventory.pipeline(), cached_parallel_verification(
                workers=16, progress=EVIDENCE / f"controller-{time.time_ns()}.json"):
            try:
                if arguments.action in {"prepare", "freeze", "activate"}:
                    prepare()
                if arguments.action in {"prepare", "refresh"}:
                    refresh("Verify native SSD preparation and frozen evidence before resuming full ZLB.")
                    return 0
                result = verify(freeze=arguments.action == "freeze" or arguments.action == "activate" and not PROOF.exists())
                print(json.dumps({"status": result["status"], "regression_tests": result["regression_tests"]}), flush=True)
                if arguments.action == "activate":
                    run()
                else:
                    refresh("SSD repair proof passes; continue full ZLB using its prepared inventory stage.")
            except BaseException as error:
                refresh("Inspect retained cause, repair prospectively and refresh before continuing.", type(error).__name__ + ": " + str(error)[:2000])
                raise
    return 0


if __name__ == "__main__":
    with continuation.archive.access():
        raise SystemExit(main())
