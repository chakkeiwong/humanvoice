"""Prepare the real budget successor offline under retained execution locks."""

import argparse
import fcntl
import json
import sys
import time
import traceback
from collections import Counter
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from humanvoice.artifacts import digest, read_json
from tools import review_inventory_recovery_v3 as review
from tools.inventory_history_adoption import no_inference
from tools.inventory_history_job import exclusive_descriptor
from tools.inventory_recovery_v2 import campaign, program, qualification, semantics
from tools.inventory_recovery_v3 import (
    accounting,
    campaign_binding,
    campaign_initialization,
    journal_binding,
    probe,
    runtime,
    stage,
    successor,
)
from tools.inventory_recovery_v3.migration import inspect_parent
from tools.inventory_recovery_v3.policy import proposal
from tools.inventory_recovery_v3.requests import NativeRequests
from tools.inventory_recovery_v3.reservations import RecoveryReservations, persist


def prepare():
    sources = review.sources()
    output = review.OUTPUT / "preparation" / digest(sources)[:20]
    output.mkdir(parents=True, exist_ok=True)
    account_path, grant_path = program.predecessor.account.ACCOUNT, program.GRANT
    authority_paths = (account_path, grant_path, grant_path.with_suffix(".stages.json"))
    authority_bytes = {str(path): path.read_text() for path in authority_paths}
    before = {path: digest(content.encode()) for path, content in authority_bytes.items()}
    started = time.time()
    result = {"status": "OFFLINE_PREPARATION_RUNNING", "sources": sources, "authority": before,
              "started_at": started, "model_calls": 0, "account_writes": 0, "grant_writes": 0,
              "live_execution_enabled": False}
    persist(output / "preparation.json", result)
    print(json.dumps({"status": result["status"], "output": str(output)}), flush=True)
    try:
        with ExitStack() as stack:
            value = campaign.cursor()
            parent = Path(value["output"])
            held_locks = []
            for path in (program.BASE / "active-session-program.lock", parent / "execution.lock", parent / "executor.lock"):
                handle = stack.enter_context(path.open("rb"))
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held_locks.append((path, handle.fileno()))

            def check():
                for path, descriptor in held_locks:
                    exclusive_descriptor(path, descriptor)
                if (campaign.cursor() != value or sources != review.sources()
                        or any(digest(Path(path).read_bytes()) != expected for path, expected in before.items())):
                    raise ValueError("Offline campaign source, production cursor or authority changed")
                return True

            check()
            stage.immutable(output / "preparation-authority.json", authority_bytes)
            if campaign.cursor() != value:
                raise ValueError("Production cursor changed before offline preparation")
            log = stack.enter_context((output / "preparation.log").open("a"))
            stack.enter_context(redirect_stdout(log))
            stack.enter_context(redirect_stderr(log))
            stack.enter_context(no_inference())
            parent_plan = read_json(parent / "plan.json")
            legacy_semantics = stack.enter_context(ExitStack())
            legacy_semantics.enter_context(semantics.runtime(parent_plan[program.adapter.FIELD].get("split_rules", [])))
            legacy_semantics.enter_context(accounting.history_scope())
            migration = inspect_parent(parent, account_path, verify_settlement=program.adapter.verify_settlement,
                reconstruct=stage.reconstruct, verify_qualification=qualification.verify)
            account = program.predecessor.account.validate_account(read_json(account_path))
            grant = program.predecessor.grant_status(grant_path)
            policy = proposal(remaining_requests=migration["remaining_requests"],
                inherited_recovery=migration["legacy_successor_charge"], incident_allowance=32,
                split_allowance=32, qualification_calls=0, root_sequences=12, available_calls=grant["available"],
                available_tokens=account["allowance"] - account["reservation_ceiling"])
            transition = successor.budget_transition(migration, policy, account_path=account_path,
                verify_settlement=program.adapter.verify_settlement, reconstruct=stage.reconstruct,
                verify_qualification=qualification.verify)
            legacy_semantics.close()
            stack.enter_context(accounting.document_scope(transition))
            current = stage.Stage(output / "campaign/generation-00", transition)
            plan = current.prepare()
            check()
            initialized = campaign_initialization.initialize(output / "campaign", check=check)
            bound = campaign_binding.create(output / "campaign", check=check)
            journal_descriptor = initialized["seed"]["journal"]
            journal = RecoveryReservations(Path(journal_descriptor["path"]).parent, policy,
                                           journal_descriptor["binding"])
            journal.publication_check = check
            if journal_binding.descriptor(journal) != journal_descriptor:
                raise ValueError("Offline campaign lost its unique recovery journal")
            with current.replay(plan, current.output, transition["proof"],
                    current.implementation.codex_runtime.validate_codex_record) as checked, runtime.runtime(
                    plan, current.output, historical_validate=checked):
                resolver = NativeRequests(plan, current.output, journal, SimpleNamespace(check=check))
            observations = probe.observations(current, current.probe(source_checked=True))
            resolver.import_history(observations)
            last = observations[-1]
            lineage, scope = resolver.extraction(last) if last["purpose"] == "concept_extraction" else resolver.critic(
                last, observations)
            imported = journal.read()["inherited_recovery"]["sequences"]
            root_counts = Counter(row["root"] for row in imported.values())
            lineage_counts = Counter(row["lineage"] for row in imported.values())
            history_bytes = journal.path.read_bytes()
            resolver.import_history(observations)
            if history_bytes != journal.path.read_bytes():
                raise ValueError("Historical ownership import was not idempotent")
            if (root_counts[lineage["root"]] >= policy["root_sequences"]
                    or lineage_counts[lineage["identity"]] >= policy["lineage_sequences"]
                    or resolver.diagnostic_handoff(plan[runtime.FIELD]["parent_failure"]) is None
                    or journal.read()["sequences"]):
                raise ValueError("Inherited ownership cannot admit the first fresh recovery pair")
            parent = plan[runtime.FIELD]["parent_failure"]
            journal.reserve(lineage=lineage["identity"], incident=digest(parent),
                request_hash=digest(last["request"]), profile_hash=digest(plan["profile"]),
                inherited_diagnostic=resolver.diagnostic_handoff(parent), check_only=True)
            if history_bytes != journal.path.read_bytes():
                raise ValueError("Ownership eligibility check changed its reservation journal")
            ownership = {"historical_sequences": len(imported), "root_counts": dict(root_counts),
                "lineage_counts": dict(lineage_counts), "unfinished_lineage": lineage["identity"],
                "unfinished_root": lineage["root"], "unfinished_scope": scope,
                "unfinished_root_sequences": root_counts[lineage["root"]],
                "unfinished_lineage_sequences": lineage_counts[lineage["identity"]],
                "observations": len(observations), "new_reservations": 0, "import_idempotent": True}
            stage.immutable(output / "ownership-preflight.json", ownership)
            if current.validate() != plan or campaign.cursor() != value:
                raise ValueError("Offline preparation changed plan or production cursor")
            check()
            result.update(status="OFFLINE_PREPARATION_PASS", plan_identity=plan["plan_identity"],
                transition_identity=transition["identity"], retained_responses=migration["retained_responses"],
                remaining_requests=migration["remaining_requests"], successor=str(current.output),
                campaign_seed_identity=initialized["seed"]["identity"], recovery_journal=journal_descriptor,
                campaign_binding_identity=bound["binding"]["identity"],
                source_unchanged=True, authority_unchanged=True, ownership=ownership)
    except (OSError, ValueError, RuntimeError, semantics.context.InvocationStopped) as error:
        (output / "preparation-error.txt").write_text(traceback.format_exc())
        result.update(status="OFFLINE_PREPARATION_FAILED", error=type(error).__name__ + ": " + str(error),
            source_unchanged=sources == review.sources(),
            authority_unchanged=all(digest(Path(path).read_bytes()) == expected for path, expected in before.items()))
    result["finished_at"] = time.time()
    persist(output / "preparation.json", result)
    print(json.dumps({**result, "sources": len(sources), "authority": result.get("authority_unchanged"),
                      "output": str(output)}), flush=True)
    return 0 if result["status"] == "OFFLINE_PREPARATION_PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare",))
    parser.parse_args()
    raise SystemExit(prepare())
