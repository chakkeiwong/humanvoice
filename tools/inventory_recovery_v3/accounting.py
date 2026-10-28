"""Independently replay mixed historical and document-budget settlements."""

from contextlib import contextmanager
from pathlib import Path

from humanvoice.artifacts import read_json
from tools.inventory_recovery_v2 import program, qualification
from tools.inventory_recovery_v3 import runtime, schema_replay

HISTORICAL_VERIFY = (qualification.verify_settlement,)


@schema_replay.scope()
def verify_settlement(output):
    plan = read_json(Path(output) / "plan.json")
    if runtime.FIELD not in plan:
        return HISTORICAL_VERIFY[0](output)
    runtime.validate_plan(plan)
    implementation = runtime.implementation
    with implementation.epoch.accounting_scope(), runtime.settlement_scope(), (
            implementation.qualified.routing.binding_scope()), (
            implementation.qualified.accounting.accounting_scope()):
        return implementation.qualified.NATIVE_PARALLEL[0](output)


@contextmanager
def history_scope():
    with runtime.implementation.replaced_aliases(qualification.verify_settlement, verify_settlement), (
            program.history_scope()), runtime.settlement_scope():
        yield


@contextmanager
def document_scope(transition):
    from tools.inventory_recovery_v3 import semantics

    with semantics.transition_runtime(transition, validation_scope=history_scope) as observed, history_scope():
        yield observed
