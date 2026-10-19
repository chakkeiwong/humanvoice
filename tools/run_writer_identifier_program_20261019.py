"""Verify, refresh and execute the retained identifier repair and ZLB sequence."""

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
from tools import run_writer_size_program_20261019 as previous
from tools import writer_identifier_continuation as continuation
from tools.automatic_call_grant import status as grant_status
from tools.automatic_program_account import ACCOUNT
from tools.inventory_transport_continuation import immutable
from tools.parallel_verification_replay import cached_parallel_verification

BASE, EVIDENCE = continuation.BASE, continuation.EVIDENCE
PROOF = EVIDENCE / "verification.json"
REGRESSION = EVIDENCE / "regression.xml"
PROBE = EVIDENCE / "probe-04/verification.json"
PLAN = "docs/plans/WRITER_IDENTIFIER_REPAIR_2026-10-19.md"
SUFFIX = "writer-identifier-20261019-01"
GRANT, PROGRESS = previous.previous.GRANT, previous.previous.PROGRESS
FILES = (*continuation.FILES, "tools/probe_writer_identifier_20261019.py",
         "tools/run_writer_identifier_program_20261019.py", "tools/supervise_writer_identifier_program_20261019.py",
         "tests/test_writer_identifier_repair.py", "tests/test_archive_evidence.py", PLAN)
ACTIVE = False


def proof_inputs():
    report = continuation.repair.report()
    upstream = read_json(previous.PROOF)
    if (upstream["identity"] != report["upstream_identity"] or upstream["implementation"] != implementation_hash()
            or any(digest((ROOT / name).read_bytes()) != expected for name, expected in report["upstream_files"].items())):
        raise ValueError("Identifier repair lost its frozen size-recovery proof")
    suites = ET.parse(REGRESSION).getroot().findall("testsuite")
    cases = {case.attrib["name"].split("[")[0] for suite in suites for case in suite.findall("testcase")}
    if (not suites or any(int(suite.attrib.get(key, 0)) for suite in suites for key in ("failures", "errors", "skipped"))
            or not {"test_identifier_correction_preserves_every_other_field", "test_identifier_correction_rejects_ambiguous_ids",
                    "test_native_identifier_replay_retains_original_response", "test_identifier_controller_routes_and_restores"} <= cases):
        raise ValueError("Identifier repair lacks its required passing regressions")
    if not {"test_archive_preserves_native_account_reservation_identity",
            "test_archive_settlement_cache_rechecks_original_bytes", "test_archive_individual_file_and_child_process",
            "test_archive_rejects_changed_aliases", "test_archive_rejects_unapproved_symlinks"} <= cases:
        raise ValueError("Identifier repair lacks verified archive regression coverage")
    probe, parent = read_json(PROBE), continuation.predecessor_evidence()
    if (probe["status"] != "pass" or probe["model_calls"] != 0 or probe["workers"] != 16
            or not probe["independent_process"] or probe["retained_writers"] != 13 or probe["derived_writers"] != 1
            or not all(probe[key] for key in ("account_bytes_unchanged", "grant_bytes_unchanged", "predecessor_bytes_unchanged"))
            or probe["extension"] != continuation.extension() or probe["predecessor_identity"] != digest(parent)
            or any(digest((PROBE.parent / name).read_bytes()) != expected for name, expected in probe["process_evidence"].items())):
        raise ValueError("Identifier independent probe evidence changed")
    return {"version": "writer-identifier-master-v1", "status": "pass", "workers": 16,
            "diagnostic_identity": report["identity"], "upstream_identity": upstream["identity"],
            "implementation": implementation_hash(), "extension": continuation.extension(),
            "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
            "regression_sha256": digest(REGRESSION.read_bytes()), "probe_sha256": digest(PROBE.read_bytes()),
            "regression_tests": sum(int(suite.attrib["tests"]) for suite in suites),
            "remaining_logical_calls": parent["remaining_calls"],
            "maximum_new_attempts": parent["remaining_calls"] + parent["remaining_transport_extras"],
            "model_calls": 0, "completed_responses_repeated": False}


def verify(*, freeze=False):
    result = proof_inputs()
    result["identity"] = digest(result)
    if freeze:
        immutable(PROOF, result)
    elif read_json(PROOF) != result:
        raise ValueError("Frozen identifier repair changed")
    return result


def refresh(next_action, stop=None):
    state, account = read_json(BASE / "status.json"), read_json(ACCOUNT)
    budget_error = None
    try:
        grant = grant_status(GRANT)
    except ValueError as error:
        if stop is None:
            raise
        budget_error = str(error)
        grant = dict(state["current_call_grant"], maximum=read_json(GRANT)["maximum_new_calls"])
    settled = [row["usage"] for row in account["events"] if row["kind"] == "settle"]
    cursor = read_json(EVIDENCE / "cursor.json") if (EVIDENCE / "cursor.json").exists() else {}
    progress = read_json(PROGRESS) if PROGRESS.exists() else {}
    status = ("writer_identifier_stopped" if stop else "writer_identifier_running" if ACTIVE
              else "writer_identifier_ready" if PROOF.exists() else "writer_identifier_preparation")
    state.update(master_version="3.28", ensemble_version=118, local_date="2026-10-19",
        status=status, repair_plan=PLAN, next_action=next_action, stop=stop,
        writer_identifier_cursor=cursor, writer_identifier_execution=read_json(PROOF) if PROOF.exists() else None,
        resume_controller=str(Path(__file__).relative_to(ROOT)) if PROOF.exists() else None,
        active_model_execution=None, parallel_workers=16, network_retry_seconds=900,
        current_budget_verification_error=budget_error,
        current_call_grant={key: grant[key] for key in ("identity", "used", "available", "reserved_remaining")},
        current_account={"plans": len(account["plans"]), "settled": len(settled),
                         "unsettled_plans": len(account["plans"]) - len(settled),
                         "effective_ceiling": account["reservation_ceiling"], "allowance": account["allowance"]})
    output = Path(cursor.get("output", str(EVIDENCE)))
    if ACTIVE and not stop and (output / "execution.json").exists() and read_json(output / "execution.json")["status"] == "executing":
        state["active_model_execution"] = str(output)
    for phase in state["phases"]:
        if phase["id"] == "E7-RB" and phase["status"] != "completed":
            phase["status"] = "repair_stopped" if stop else "running" if ACTIVE else "repair_ready" if PROOF.exists() else "repair_validation"
        if (phase["id"] == "E6-B" and set(progress.get("humanizations", {})) == {"held-out", "zlb"}
                or phase["id"] == "E7-RB" and set(progress.get("reproductions", {})) == {"held-out", "zlb"}):
            phase["status"] = "completed"
    if progress.get("final_admission"):
        state.update(status="awaiting_final_immutable_ZLB_acceptance", resume_controller=None, active_model_execution=None)
    note = (f"\nCurrent execution: master 3.28 / ensemble 118; observed {datetime.now(timezone.utc).isoformat()}.\n"
        f"Status: {state['status']}. Repair: {PLAN}.\n"
        "Held-out writers 001-013 are accepted and retained. Unit-014 has one malformed concept identifier.\n"
        "Correct only the uniquely matched deletion in its identifier; preserve manuscript text, evidence spans and the original provider response.\n"
        "Derive a separate bound result, replay unchanged native checks, and keep the original rejected attempt and receipt.\n"
        "The isolated continuation performs 14 unit reviews and 27 assembled reviews, with 15 existing transport extras (56 maximum attempts).\n"
        "No writer response is purchased again; no human intermediate review or additional Claude call is required.\n"
        "Writer acceptance remains 100,000 input / 32,000 output; proven size failures split to depth 3 with at most 14 children per root.\n"
        "Use 16 independent verification workers; provider calls and accounting remain sequential.\n"
        "Eligible response-free network failures wait 900 seconds. Audits remain 900 seconds/$4.\n"
        f"Calls{' (last verified; storage-path validation currently blocked)' if budget_error else ''}: "
        f"{grant['used']}/{grant['maximum']} used; {grant['available']} available; {grant['reserved_remaining']} reserved.\n"
        f"Settlements: {len(settled)}/{len(account['plans'])}; token ceiling {account['reservation_ceiling']:,}/{account['allowance']:,}.\n"
        "Historical failed receipts and unknown charges remain unchanged. SSD is working storage; soft is archive-only.\n"
        "Read historical evidence through checksum-bound archive aliases; preserve logical paths and all native content checks.\n"
        "Archived evidence remains read-only; new execution and its outputs stay on SSD.\n"
        "Remaining: held-out independent reviews and reproduction verification; full ZLB inventory/humanization/review/release;\n"
        "independent ZLB reproduction; automatic final admission; human acceptance of the immutable actual ZLB output.\n"
        "Every phase boundary or stop: inspect, settle, independently verify, repair prospectively, refresh both masters, continue eligible work.\n"
        f"Next: {next_action}\nStop: {stop or 'none'}.\n")
    write_json(BASE / "status.json", state)
    for name in ("humanvoice_master_program_v2.md", "ENSEMBLE_MASTER_PROGRAM_2026-09-30.md"):
        path = ROOT / "docs/plans" / name
        content = path.read_text()
        heading, _ = content.split("\n", 1)
        _, tail = content.split("<!-- end-current-benchmark-execution -->", 1)
        intro = ("\nOperational refresh, 19 October 2026: master 3.28 / ensemble 118.\n"
                 "The [identifier correction and continuation](WRITER_IDENTIFIER_REPAIR_2026-10-19.md) preserves all spent writer responses.\n"
                 "Only final acceptance of the immutable actual ZLB output requires human content review.\n\n")
        path.write_text(heading + "\n" + intro + "<!-- current-benchmark-execution -->" + note
                        + "<!-- end-current-benchmark-execution -->" + tail)
    for path in (BASE / "CURRENT_EXECUTION_20261014.md", EVIDENCE / "STATUS.md"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Writer identifier repair and execution\n" + note)
    print(json.dumps({"status": state["status"], "next": next_action, "stop": stop}), flush=True)


def recovery_command(command):
    actual = scope.recovery_command(command)
    return [actual[0], str(ROOT / "tools/writer_identifier_runner.py"), *actual[2:]]


def benchmark_chain(name, row, campaign, bounds):
    engine = previous.previous.previous.parallel.previous.engine
    snapshot = engine.previous.previous.previous.previous.previous.inventory(
        name, BASE / row["snapshot"], row["inventory_maximum_logical_calls"], campaign, refresh)
    maximum = bounds.humanization_bound(name, snapshot)
    refresh("Verify retained release before bounded independent reproduction.")
    snapshot = engine.humanization(name, snapshot, maximum if name == "held-out" else previous.split_bound(snapshot, maximum), campaign)
    if name == "held-out":
        proof = continuation.predecessor_evidence()
        if snapshot != previous.previous.SNAPSHOT or maximum != 55:
            raise ValueError("Identifier continuation changed the frozen held-out benchmark")
        calls = proof["remaining_calls"]
    else:
        calls = previous.split_bound(snapshot, maximum)
    output = BASE / f"{name}-reproduction-{SUFFIX}"
    if not (output / "plan.json").exists():
        arguments = ["prepare", "--output", output, "--snapshot", snapshot, "--stage", "reproduction",
                     "--max-calls", calls, "--call-grant", GRANT]
        if name == "held-out":
            arguments += ["--technical-predecessor", continuation.PRIOR]
        write_json(EVIDENCE / "cursor.json", {"phase": "prepare", "output": str(output)})
        refresh("Prepare independent review of the thirteen retained writers and the identifier derivation.")
        campaign.script("run-manuscript-with-300-grant-20261008.py", *arguments)
    suffix = campaign.SUFFIX
    try:
        campaign.SUFFIX = SUFFIX
        write_json(EVIDENCE / "cursor.json", {"phase": "execute", "output": str(output)})
        refresh("Execute independent reviews; verify and settle before the next phase.")
        campaign.manuscript(name, "reproduction", snapshot, calls, "E7-RB-" + name)
    finally:
        campaign.SUFFIX = suffix
    packets = list((snapshot / "release").iterdir())
    if len(packets) != 1:
        raise ValueError("Final admission requires one immutable packet")
    progress = read_json(PROGRESS)
    progress.setdefault("reproductions", {})[name] = {"snapshot": str(snapshot),
        "output": str(output / "reproduction"), "full_call_bound": maximum}
    write_json(PROGRESS, progress)
    write_json(EVIDENCE / "cursor.json", {"phase": "verified_reproduction", "output": str(output)})
    refresh(name + " reproduction independently verified and settled; continue.")
    return {"snapshot": snapshot, "packet": packets[0], "reproduction": output / "reproduction"}


def run():
    global ACTIVE
    with ExitStack() as bindings:
        bindings.callback(setattr, scope, "RUNNER", scope.RUNNER)
        scope.RUNNER = ROOT / "tools/writer_identifier_runner.py"
        for name, value in (("refresh", refresh), ("continuation", continuation), ("benchmark_chain", benchmark_chain),
                            ("recovery_command", recovery_command), ("EVIDENCE", EVIDENCE)):
            bindings.callback(setattr, previous, name, getattr(previous, name))
            setattr(previous, name, value)
        ACTIVE = True
        try:
            previous.run()
        finally:
            ACTIVE = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("diagnose", "freeze", "verify", "refresh", "activate"))
    parser.add_argument("--live", action="store_true")
    arguments = parser.parse_args()
    if arguments.action == "activate" and not arguments.live:
        parser.error("Execution requires --live")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with (BASE / "inventory-prefix-controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            continuation.ensure_execution_paths()
        except ValueError as error:
            refresh("Verify archive checksums and aliases; rerun the isolated probe, freeze, commit and resume.",
                    str(error))
            raise
        with scope.accounting_scope(), continuation.pipeline(), cached_parallel_verification(
                workers=16, progress=EVIDENCE / f"controller-{time.time_ns()}.json"):
            try:
                if arguments.action == "diagnose":
                    with scope.verification_only():
                        continuation.diagnose()
                    refresh("Validate identifier regressions and the isolated zero-provider probe.")
                elif arguments.action == "refresh":
                    refresh("Complete repair validation, commit the reviewed changes, and resume the supervised program.")
                else:
                    result = verify(freeze=arguments.action == "freeze")
                    print(json.dumps({"status": result["status"], "regression_tests": result["regression_tests"]}), flush=True)
                    if arguments.action == "activate":
                        run()
                    else:
                        refresh("Identifier repair frozen; resume independent reviews and the full ZLB sequence.")
            except BaseException as error:
                refresh("Inspect retained evidence, repair prospectively, verify and resume eligible work.",
                        type(error).__name__ + ": " + str(error))
                raise
    return 0


if __name__ == "__main__":
    with continuation.archive.access():
        raise SystemExit(main())
