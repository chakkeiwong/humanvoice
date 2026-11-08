"""Qualification orchestration preserves native judgment and accounting boundaries."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import execution
import pytest

from humanvoice.artifacts import digest, write_json


@pytest.fixture
def admitted(tmp_path, monkeypatch):
    monkeypatch.setattr(execution, 'HERE', tmp_path)
    output = tmp_path / 'qualification-host'
    output.mkdir()
    authority = tmp_path / 'execution-authorization.json'
    authority.write_text('reviewed fixture authorization')
    reference = tmp_path / 'call-authorization.json'
    reference.write_text('reviewed fixture addition')
    profile = {'model': 'fixture'}
    plan = {'profile': profile, 'plan_identity': 'native-plan'}
    record = {'window_end_utc': execution.WINDOW_END,
        'sources': {str(reference): digest(reference.read_bytes())}, 'qualification_contract': {'native': 1}}
    candidate = {'current_binding': {'fixture': 'active-session'}}
    evidence = {'status': 'QUALIFICATION_VERIFIED', 'profile_hash': digest(profile),
        'purposes': execution.migration_policy.PURPOSES, 'settled': True, 'canary_only': False,
        'output': str(output), 'plan_identity': 'native-plan', 'evaluation_hash': 'native-evaluation'}
    seen = []
    values = (record, {'output': str(output)}, candidate, plan,
        {'grant': str(tmp_path / 'grant.json')})
    monkeypatch.setattr(execution, 'approved_inputs', lambda: values)
    monkeypatch.setattr(execution.time, 'time', lambda: execution.WINDOW_END - 100)
    monkeypatch.setattr(execution.qualification, 'contract', lambda: {'native': 1})
    monkeypatch.setattr(execution.control, 'require_running', lambda *_args, **_kwargs: seen.append('stop'))
    monkeypatch.setattr(execution.migration.settings, 'verify', lambda value: seen.append(('parity', value)))

    @contextmanager
    def budget(*_args, **_kwargs):
        seen.append('budget-enter')
        try:
            yield
        finally:
            seen.append('budget-exit')

    @contextmanager
    def history():
        seen.append('history-enter')
        try:
            yield
        finally:
            seen.append('history-exit')

    def verify(path, selected):
        assert path == output and selected == profile
        seen.append('verify')
        return deepcopy(evidence)

    monkeypatch.setattr(execution.grant_extension, 'scope', budget)
    monkeypatch.setattr(execution.accounting, 'history_scope', history)
    monkeypatch.setattr(execution.qualification, 'verify', verify)
    return values, seen, evidence


@pytest.mark.parametrize('terminal', ['pass', 'QUALIFICATION_VERIFIED', 'nonpass'])
def test_native_semantic_result_is_never_rerolled_or_reallocated(admitted, monkeypatch, terminal):
    values, seen, evidence = admitted

    def native(output, profile, grant, *, publish):
        assert str(output) == values[1]['output'] and profile == values[3]['profile']
        assert str(grant) == values[4]['grant']
        execution.control.require_running()
        seen.append('execute-once')
        publish({'status': 'QUALIFYING_FALLBACK'})
        return {'status': terminal}

    monkeypatch.setattr(execution.qualification, 'execute', native)
    code = execution.execute()
    assert seen.count('execute-once') == 1
    assert seen.index('budget-enter') < seen.index('execute-once') < seen.index('budget-exit')
    if terminal == 'nonpass':
        assert code == 2 and 'verify' not in seen
        assert not (execution.HERE / 'qualification-verified.json').exists()
    else:
        assert code == 0 and seen.count('verify') == 1
        assert execution.read_json(execution.HERE / 'qualification-verified.json') == evidence
    assert seen.count('history-enter') == seen.count('history-exit')


@pytest.mark.parametrize('cause', ['deadline', 'stop', 'changed-source'])
def test_lost_authority_stops_before_budget_scope_or_native_spending(admitted, monkeypatch, cause):
    values, seen, _evidence = admitted
    if cause == 'deadline':
        monkeypatch.setattr(execution.time, 'time', lambda: execution.WINDOW_END)
    elif cause == 'stop':
        (execution.HERE / 'STOP').touch()
    else:
        Path(next(iter(values[0]['sources']))).write_text('changed')
    monkeypatch.setattr(execution.qualification, 'execute', lambda *_args, **_kwargs: pytest.fail('spent'))
    with pytest.raises(ValueError):
        execution.execute()
    assert 'budget-enter' not in seen


def test_existing_conflicting_verified_evidence_is_preserved(admitted, monkeypatch):
    _values, seen, _evidence = admitted
    target = execution.HERE / 'qualification-verified.json'
    write_json(target, {'different': 'native result'})
    before = target.read_bytes()
    monkeypatch.setattr(execution.qualification, 'execute', lambda *_args, **_kwargs: {'status': 'pass'})
    with pytest.raises(ValueError, match='Prior verified qualification changed'):
        execution.execute()
    assert target.read_bytes() == before
    assert seen.count('budget-enter') == seen.count('budget-exit') == 1
