"""Plan inventory with native validation and bounded transport recovery only."""

from contextlib import contextmanager
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools import reproduction_overload_recovery as history

ROOT, network, scope = history.ROOT, history.network, history.scope
VERSION = "inventory-stage-policy-v1"
FILES = ("tools/inventory_stage_runtime.py", "tools/zlb_stage_runner.py")
FIELDS = {"inventory_stage_extension", "assembled_input_budget_extension",
          "delayed_network_extension", "overload_network_extension"}
NETWORK_VALIDATOR = (network.validate_extension,)
HISTORY_READER = (history.verify_settlement,)


def extension():
    return {"version": VERSION, "stage": "inventory", "candidate_planning": False,
            "files": {name: digest((ROOT / name).read_bytes()) for name in FILES},
            "provider_calls_sequential": True, "backoff_seconds": 900, "transport_extras": 16}


def validate_extension(plan):
    NETWORK_VALIDATOR[0](plan)
    network.budget.plan_scope(plan)
    if (plan.get("stage") != "inventory" or plan.get("inventory_stage_extension") != extension()
            or plan.get("overload_network_extension") != history.overload.extension()
            or plan.get("purposes") != sorted(history.MANUSCRIPT.PURPOSES["inventory"])
            or plan.get("recovery") != network.policy() or plan.get("technical_retries") != 1
            or "technical_restart" in plan or "execution_snapshot" in plan
            or {name for name in plan if name.endswith("_extension")} != FIELDS):
        raise ValueError("Inventory policy changed its native stage or transport-only scope")
    return plan


def verify_settlement(output):
    with history.archive.access():
        plan = read_json(Path(output) / "plan.json")
        if "inventory_stage_extension" not in plan:
            return HISTORY_READER[0](output)
        validate_extension(plan)
        with scope.accounting_scope(), pipeline(), scope.verification_only():
            return network.SETTLEMENT_READER[0](output)


@contextmanager
def pipeline(*, planning=(), authorization=network.budget.authority.AUTHORITY):
    from tools import automatic_reproduction_worker, parallel_verification_replay

    enabled = {(str(Path(snapshot).resolve()), stage) for snapshot, stage in planning}
    if any(stage != "inventory" for _, stage in enabled):
        raise ValueError("Inventory planning requires explicit inventory scope")
    with history.pipeline():
        native_plan, native_worker = history.MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for
        native_settlement = parallel_verification_replay.verify_settlement
        native_validator = network.validate_extension

        def plan_for(snapshot, stage, *arguments, **keywords):
            plan = native_plan(snapshot, stage, *arguments, **keywords)
            if (str(Path(snapshot).resolve()), stage) in enabled:
                plan.update(version=network.recovery.MANUSCRIPT_VERSION, recovery=network.policy(), technical_retries=1,
                    assembled_input_budget_extension=network.budget.extension(authorization),
                    delayed_network_extension=network.extension(), overload_network_extension=history.overload.extension(),
                    inventory_stage_extension=extension())
                plan.pop("plan_identity")
                plan["plan_identity"] = digest(plan)
                validate_extension(plan)
            return plan

        def validate_network(plan):
            if "inventory_stage_extension" in plan:
                validate_extension(plan)
            else:
                native_validator(plan)

        history.MANUSCRIPT.plan_for = automatic_reproduction_worker.plan_for = plan_for
        network.validate_extension = validate_network
        try:
            with network.replaced_aliases(native_settlement, verify_settlement):
                yield
        finally:
            history.MANUSCRIPT.plan_for, automatic_reproduction_worker.plan_for = native_plan, native_worker
            network.validate_extension = native_validator
