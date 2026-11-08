"""Prepare a current-client campaign through unchanged native preparation code.

Only this invocation's initial transition and public source closure are projected.
Historical source reconstruction continues through the native successor module.
"""

import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import FunctionType, SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MIGRATION = ROOT / '.localresources/session-migration-20261107'
sys.path[:0] = [str(MIGRATION), str(ROOT), str(ROOT / 'src')]

import campaign_context
import client_transition
import grant_extension
import migration_policy
import migration_runtime

from humanvoice.artifacts import digest
from tools import finalization_cache
from tools import prepare_inventory_recovery_v3 as native
from tools import review_inventory_recovery_v3 as review

require = client_transition.require
FILES = ('binding_migration.py', 'client_protocol.py', 'migration_policy.py',
    'recovery_identity.py', 'client_transition.py', 'migration_runtime.py', 'grant_extension.py')


def dependencies(paths=()):
    members = [*(MIGRATION / name for name in FILES), Path(__file__),
        *campaign_context.sources(), *map(Path, paths)]
    require(len(set(members)) == len(members), 'Migration dependencies repeat a source')
    result = {}
    for path in members:
        require(path.is_absolute() and path.is_relative_to(ROOT)
            and path.resolve() == path and path.is_file(),
            'Migration dependency must be a regular file in the working tree')
        result[str(path.relative_to(ROOT))] = digest(path.read_bytes())
    return result


@contextmanager
def source_scope(paths=()):
    """Every prospective reader derives the same source-bound preparation path."""
    original = review.sources
    before = dependencies(paths)
    retained = original()
    require(not set(before) & set(retained), 'Migration cannot replace native source members')

    def sources():
        require(before == dependencies(paths) and retained == original(),
            'Migration source changed during prospective preparation or configuration')
        return {**retained, **before}

    with migration_runtime.replaced(review, 'sources', sources):
        yield sources()


def projected_prepare(candidate, qualification, protocol):
    """Clone only the preparation function's globals, leaving native modules intact."""
    frozen = deepcopy((candidate, qualification, protocol))
    original_budget = native.successor.budget_transition

    def budget(*arguments, **keywords):
        require((candidate, qualification, protocol) == frozen,
            'Migration preparation inputs changed')
        source = original_budget(*arguments, **keywords)
        requirements = migration_policy.requirements(source['profile'], candidate)
        attestation = migration_policy.fresh_attestation(source['profile'], candidate,
            requirements, qualification, native.qualification.verify)
        return client_transition.construct(source, candidate, requirements, attestation, protocol)

    class Journal(native.RecoveryReservations):
        def reserve(self, **keywords):
            # Native preparation performs this check after leaving its receipt
            # replay context. Bind the exact resolver's plan for that operation.
            plan = getattr(self, 'migration_plan', None)
            require(plan is not None, 'Preparation journal lacks its native request resolver')
            with migration_runtime.selected(migration_runtime.PLAN, plan):
                return super().reserve(**keywords)

    class Requests(native.NativeRequests):
        def __init__(self, plan, output, journal, owner):
            super().__init__(plan, output, journal, owner)
            require(isinstance(journal, Journal) and not hasattr(journal, 'migration_plan'),
                'Migration preparation cannot rebind its journal to another resolver')
            journal.migration_plan = plan

    namespace = {**native.prepare.__globals__,
        'successor': SimpleNamespace(budget_transition=budget),
        'RecoveryReservations': Journal, 'NativeRequests': Requests}
    projected = FunctionType(native.prepare.__code__, namespace, native.prepare.__name__,
        native.prepare.__defaults__, native.prepare.__closure__)
    projected.__kwdefaults__ = native.prepare.__kwdefaults__
    return projected


def prepare(candidate, qualification, protocol, *, authorization_path, authorization_sha256,
            additional_sources=(), progress=None):
    paths = (authorization_path, *additional_sources)
    with campaign_context.scope(), grant_extension.scope(authorization_path, expected_sha256=authorization_sha256), (
            migration_runtime.scope()), source_scope(paths), finalization_cache.scope():
        return projected_prepare(candidate, qualification, protocol)(progress=progress)
