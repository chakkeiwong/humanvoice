"""Check prospective preparation without mutating native reconstruction."""

import sys
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'session-migration-20261107')]

import preparation_adapter as adapter
import pytest
import test_client_transition

profiles = test_client_transition.profiles
case = test_client_transition.case


def test_only_preparation_constructor_projects_fresh_transition(case, monkeypatch):
    source, migrated, qualification = case
    marker = migrated[adapter.client_transition.FIELD]
    seen = []

    def budget(*args, **kwargs):
        seen.append((args, kwargs))
        return deepcopy(source)

    def verify(output, profile):
        assert output == qualification['output']
        assert adapter.digest(profile) == qualification['profile_hash']
        return deepcopy(qualification)

    monkeypatch.setattr(adapter.native.successor, 'budget_transition', budget)
    monkeypatch.setattr(adapter.native.qualification, 'verify', verify)
    projected = adapter.projected_prepare(marker['candidate'], qualification, marker['protocol'])
    constructor = projected.__globals__['successor'].budget_transition
    assert constructor('report', 'policy', account_path='account') == migrated
    assert seen == [(('report', 'policy'), {'account_path': 'account'})]
    assert adapter.native.successor.budget_transition is budget
    assert adapter.native.prepare.__globals__['successor'] is adapter.native.successor
    assert projected.__code__ is adapter.native.prepare.__code__
    qualification['settled'] = False
    with pytest.raises(ValueError, match='inputs changed'):
        constructor('report', 'policy')
    assert len(seen) == 1


def test_preparation_retry_check_retains_the_native_resolvers_plan(case, monkeypatch, tmp_path):
    _source, migrated, qualification = case
    marker = migrated[adapter.client_transition.FIELD]
    projected = adapter.projected_prepare(marker['candidate'], qualification, marker['protocol'])
    journal_class = projected.__globals__['RecoveryReservations']
    requests_class = projected.__globals__['NativeRequests']
    monkeypatch.setattr(adapter.native.RecoveryReservations, '__init__', lambda *_: None)
    monkeypatch.setattr(adapter.native.NativeRequests, '__init__', lambda *_: None)
    monkeypatch.setattr(adapter.native.RecoveryReservations, 'reserve',
        lambda *_args, **_kwargs: adapter.migration_runtime.PLAN.get())
    journal = journal_class(None, None, None)
    with pytest.raises(ValueError, match='lacks its native request resolver'):
        journal.reserve(check_only=True)
    plan = {'profile': migrated['profile'], adapter.native.runtime.FIELD: {'transition': migrated}}
    requests_class(plan, tmp_path, journal, object())
    assert journal.reserve(check_only=True) is plan
    assert adapter.migration_runtime.PLAN.get() is None
    with pytest.raises(ValueError, match='rebind'):
        requests_class(deepcopy(plan), tmp_path, journal, object())


def test_source_closure_preserves_native_members_and_rejects_midflight_changes(monkeypatch):
    native = {'tools/native.py': 'a' * 64}
    current = {'.localresources/migration.py': 'b' * 64}
    original = lambda: deepcopy(native)
    monkeypatch.setattr(adapter.review, 'sources', original)
    monkeypatch.setattr(adapter, 'dependencies', lambda _paths: deepcopy(current))
    with adapter.source_scope() as sources:
        assert sources == {**native, **current}
        assert adapter.review.sources() == sources
        current['.localresources/migration.py'] = 'c' * 64
        with pytest.raises(ValueError, match='source changed'):
            adapter.review.sources()
    assert adapter.review.sources is original
