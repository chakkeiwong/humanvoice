"""Scoped client-migration integration around unchanged native v3 operations.

Each historical validation selects its own transition. An active migration can
never substitute a current profile into an unrelated historical ancestor.
"""

from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
from threading import RLock

import client_transition as transition
import recovery_identity

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v2 import qualification
from tools.inventory_recovery_v3 import (
    ancestry,
    continuation,
    reprepare,
    runtime,
    stage,
    successor,
)
from tools.inventory_recovery_v3.reservations import RecoveryReservations, regular_path

EXPECTED = ContextVar('current_client_expected_transition', default=None)
PLAN = ContextVar('current_client_runtime_plan', default=None)
INSTALLED = ContextVar('current_client_adapter_installed', default=False)
LOCK = RLock()
require = transition.require


@contextmanager
def selected(variable, value):
    token = variable.set(value)
    try:
        yield
    finally:
        variable.reset(token)


@contextmanager
def replaced(module, name, wrapper):
    original = getattr(module, name)
    setattr(module, name, wrapper)
    try:
        yield
    finally:
        setattr(module, name, original)


def migration_origin(value):
    # A retirement wrapper retains its source exactly. Check that source first;
    # the native retirement verifier still validates its separate stop history.
    return transition.origin(reprepare.source(value))


@contextmanager
def scope():
    require(LOCK.acquire(blocking=False), 'Client migration adapter is owned by another operation')
    try:
        if INSTALLED.get():
            yield
            return
        native_require = successor.require_transition
        native_budget = successor.budget_transition
        native_source = stage.Stage.source_gate
        native_ancestry = ancestry.validate
        native_retained = continuation.retained
        native_runtime = runtime.runtime
        native_reserve = RecoveryReservations.reserve

        def verified(value, *, source_verifier=native_require):
            with selected(EXPECTED, None):
                return transition.verify(value, source_verifier=source_verifier,
                    qualification_verifier=qualification.verify)

        def require_transition(value):
            if value.get('version') == 'inventory-budget-successor-v1' and transition.FIELD in value:
                return verified(value)
            # The native reprepare/continuation verifier reconstructs all fields,
            # including the origin, through the same scoped native entry points.
            if transition.ORIGIN in value:
                require(value.get('version') in {continuation.VERSION, reprepare.VERSION},
                    'Only a native successor may inherit a client migration origin')
            return native_require(value)

        def budget(report, policy, **keywords):
            expected = EXPECTED.get()
            with selected(EXPECTED, None):
                original = native_budget(report, policy, **keywords)
            if expected is None or transition.FIELD not in expected:
                return original
            require(expected.get('version') == 'inventory-budget-successor-v1'
                and expected[transition.FIELD]['source_transition'] == original,
                'Migrated source gate differs from independent native reconstruction')

            def checked_source(value):
                require(value == original, 'Client migration substituted another native source')
                return value

            return verified(expected, source_verifier=checked_source)

        def source(self):
            with selected(EXPECTED, self.transition):
                return native_source(self)

        def ancestor(output, plan, **keywords):
            with selected(EXPECTED, plan[runtime.FIELD]['transition']):
                return native_ancestry(output, plan, **keywords)

        def retained(output):
            value = native_retained(output)
            plan = read_json(regular_path(Path(output) / 'plan.json'))
            initial = migration_origin(plan[runtime.FIELD]['transition'])
            if initial is not None:
                verified(initial)
                value = transition.identified({**value, transition.ORIGIN: deepcopy(initial)})
            return value

        @contextmanager
        def run(plan, output, **keywords):
            with selected(PLAN, plan), native_runtime(plan, output, **keywords):
                yield

        def reserve(journal, **keywords):
            plan = PLAN.get()
            initial = migration_origin(plan[runtime.FIELD]['transition']) if plan is not None else None
            if initial is None:
                return native_reserve(journal, **keywords)
            profile_hash = keywords['profile_hash']
            require(profile_hash == digest(plan['profile']),
                'Client migration reservation differs from the active native plan')
            previous, current = transition.profile_pair(initial, profile_hash)
            frozen_plan = deepcopy(plan)

            def guard():
                require(plan == frozen_plan and PLAN.get() is plan
                    and journal.binding['document'] == plan['bindings']['source']
                    and journal.binding['migration'] == plan[runtime.FIELD]['migration_identity'],
                    'Client migration reservation changed its native plan or journal')
                verified(initial)
                return True

            return recovery_identity.reserve(journal, original_profile_hash=previous,
                current_profile_hash=current, check_migration=guard,
                **{key: value for key, value in keywords.items() if key != 'profile_hash'})

        with ExitStack() as stack:
            stack.enter_context(selected(INSTALLED, True))
            for module, name, wrapper in (
                    (successor, 'require_transition', require_transition),
                    (successor, 'budget_transition', budget),
                    (stage.Stage, 'source_gate', source),
                    (ancestry, 'validate', ancestor),
                    (continuation, 'retained', retained),
                    (runtime, 'runtime', run),
                    (RecoveryReservations, 'reserve', reserve)):
                stack.enter_context(replaced(module, name, wrapper))
            yield
    finally:
        LOCK.release()
