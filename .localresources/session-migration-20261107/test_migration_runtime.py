"""Adapters restore native operations and select each ancestor's own identity."""

from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import migration_runtime as adapter
import pytest
import test_client_transition

case = test_client_transition.case
profiles = test_client_transition.profiles


@pytest.fixture
def boundary(case, monkeypatch):
    source, migrated, evidence = case
    seen = []

    def native(value):
        seen.append(('require', deepcopy(value)))
        if value != source:
            raise ValueError('native source refused altered transition')
        return value

    def qualify(output, profile):
        assert output == evidence['output'] and adapter.digest(profile) == evidence['profile_hash']
        return deepcopy(evidence)

    def budget(report, policy, **keywords):
        seen.append(('budget', deepcopy(adapter.EXPECTED.get())))
        assert report == source['migration'] and policy == source['policy']
        return deepcopy(source)

    def gate(self):
        expected = adapter.successor.budget_transition(self.transition['migration'], self.transition['policy'])
        assert expected == self.transition
        return expected

    def ancestry(output, plan, **keywords):
        # Re-entering a historical ancestor while verifying the migrated stage
        # must select the ancestor's original source, not the ambient migration.
        return adapter.successor.budget_transition(plan[adapter.runtime.FIELD]['transition']['migration'],
            plan[adapter.runtime.FIELD]['transition']['policy'])

    @contextmanager
    def runtime(plan, output, **keywords):
        seen.append(('runtime', plan))
        yield

    monkeypatch.setattr(adapter.successor, 'require_transition', native)
    monkeypatch.setattr(adapter.successor, 'budget_transition', budget)
    monkeypatch.setattr(adapter.stage.Stage, 'source_gate', gate)
    monkeypatch.setattr(adapter.ancestry, 'validate', ancestry)
    monkeypatch.setattr(adapter.runtime, 'runtime', runtime)
    monkeypatch.setattr(adapter.qualification, 'verify', qualify)
    return SimpleNamespace(source=source, migrated=migrated, seen=seen, native=native)


def test_only_explicit_migrated_source_gate_changes_and_native_operations_restore(boundary):
    source, migrated = boundary.source, boundary.migrated
    native = adapter.successor.budget_transition
    with adapter.scope():
        assert adapter.successor.require_transition(migrated) == migrated
        assert adapter.stage.Stage.source_gate(SimpleNamespace(transition=migrated)) == migrated
        assert adapter.stage.Stage.source_gate(SimpleNamespace(transition=source)) == source
        assert adapter.successor.budget_transition(source['migration'], source['policy']) == source
        with adapter.selected(adapter.EXPECTED, migrated):
            assert adapter.ancestry.validate('/historical', {
                adapter.runtime.FIELD: {'transition': source}}) == source
            assert adapter.EXPECTED.get() == migrated
        assert all(value is None for operation, value in boundary.seen if operation == 'budget')
    assert adapter.successor.budget_transition is native
    assert adapter.successor.require_transition is boundary.native
    assert adapter.EXPECTED.get() is None and adapter.PLAN.get() is None


def test_failed_scope_and_nested_runtime_restore_the_historical_plan(boundary):
    current = {adapter.runtime.FIELD: {'transition': boundary.migrated}}
    historical = {adapter.runtime.FIELD: {'transition': boundary.source}}
    with pytest.raises(OSError, match='interrupted'), adapter.scope(), adapter.runtime.runtime(current, '/current'):
        with adapter.scope(), adapter.runtime.runtime(historical, '/historical'):
            assert adapter.PLAN.get() is historical
        assert adapter.PLAN.get() is current
        raise OSError('interrupted')
    assert not adapter.INSTALLED.get()
    assert adapter.successor.require_transition is boundary.native
    assert adapter.PLAN.get() is None


def test_unmarked_rehashed_transition_cannot_invent_a_migration_origin(boundary):
    value = adapter.transition.identified({**boundary.source,
        adapter.transition.ORIGIN: boundary.migrated})
    with adapter.scope(), pytest.raises(ValueError, match='Only a native successor'):
        adapter.successor.require_transition(value)
