"""Test approved launch publication and recovery with only systemd simulated."""

import subprocess
from copy import deepcopy
from types import SimpleNamespace

import launch
import pytest

from humanvoice.artifacts import read_json, write_json


@pytest.fixture
def review(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, 'HERE', tmp_path)
    monkeypatch.setattr(launch, 'REVIEW', tmp_path / 'reviewed-execution.json')
    monkeypatch.setattr(launch.time, 'time', lambda: launch.execution.WINDOW_END - 7200)
    grant = tmp_path / 'grant.json'
    write_json(grant, {'identity': 'retained-grant', 'maximum_new_calls': 2000,
        'account': str(tmp_path / 'account/account.json')})
    extension = launch.execution.identified({'version': launch.execution.grant_extension.VERSION,
        'status': 'AWAITING_USER_APPROVAL', 'grant': str(grant), 'grant_identity': 'retained-grant',
        'original_maximum': 2000, 'additional_calls': 235, 'total_maximum': 2235,
        'no_replenishment_on_reload': True})
    state = SimpleNamespace(proposal={'identity': 'budget-proposal', 'extension': extension},
        prepared={'identity': 'prepared'}, candidate={'identity': 'candidate'},
        sources={'fixture.py': 'a' * 64}, calls=[], service='inactive', fail_start=False,
        native_contract={'native': 'unchanged'})
    monkeypatch.setattr(launch, 'reviewed_inputs', lambda: (
        deepcopy(state.proposal), deepcopy(state.prepared), deepcopy(state.candidate), deepcopy(state.sources)))
    monkeypatch.setattr(launch.execution.qualification, 'contract', lambda: deepcopy(state.native_contract))
    monkeypatch.setattr(launch.namespace, 'properties', lambda authority: ['User=ubuntu', 'PrivateUsers=no'])

    def approved():
        state.calls.append('approved-inputs')
        assert read_json(tmp_path / 'call-authorization.json')['additional_calls'] == 235
        assert read_json(tmp_path / 'execution-authorization.json')['production_admitted'] is False

    def systemd(command, **kwargs):
        state.calls.append(command)
        if command[0] == '/usr/bin/systemctl':
            return subprocess.CompletedProcess(command, 0,
                stdout='ActiveState=' + state.service + '\nMainPID=0\nControlPID=0\n')
        assert command[:2] == ['/usr/bin/pkexec', '/usr/bin/systemd-run']
        assert '--no-block' in command and kwargs['timeout'] == 180
        assert state.calls[-2] == 'approved-inputs'
        if state.fail_start:
            raise subprocess.TimeoutExpired(command, 30)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(launch.execution, 'approved_inputs', approved)
    monkeypatch.setattr(launch.subprocess, 'run', systemd)
    launch.prepare()
    state.root = tmp_path
    state.original_grant = grant.read_bytes()
    return state


@pytest.mark.parametrize('drift', ['sources', 'contract', 'prepared', 'budget', 'request'])
def test_review_drift_stops_before_approval_records_or_host_mutation(review, drift):
    if drift == 'sources': review.sources['fixture.py'] = 'b' * 64
    elif drift == 'contract': review.native_contract['native'] = 'changed'
    elif drift == 'prepared': review.prepared['identity'] = 'another'
    elif drift == 'budget': review.proposal['identity'] = 'another'
    else:
        record = read_json(launch.REVIEW)
        record['request'] = 'different authority'
        write_json(launch.REVIEW, launch.execution.identified(record))
    with pytest.raises(ValueError):
        launch.activate()
    assert review.calls == []
    assert not (review.root / 'call-authorization.json').exists()
    assert not (review.root / 'execution-authorization.json').exists()


def test_start_retry_reuses_identical_addition_without_replenishing_calls(review):
    review.fail_start = True
    with pytest.raises(subprocess.TimeoutExpired):
        launch.activate()
    retained = {name: (review.root / name).read_bytes()
        for name in ('call-authorization.json', 'execution-authorization.json')}
    review.fail_start = False
    launch.activate()
    assert all((review.root / name).read_bytes() == raw for name, raw in retained.items())
    assert (review.root / 'grant.json').read_bytes() == review.original_grant
    approved = read_json(review.root / 'execution-authorization.json')
    assert approved['maximum_sessions'] == 276
    assert approved['window_end_utc'] == launch.execution.WINDOW_END
    assert approved['sources'][str(review.root / 'call-authorization.json')] == launch.execution.digest(
        retained['call-authorization.json'])


@pytest.mark.parametrize('retained', ['active-service', 'recorded-worker'])
def test_existing_service_or_worker_state_cannot_start_a_second_qualification(review, retained):
    if retained == 'active-service': review.service = 'active'
    else: write_json(review.root / 'supervisor-status.json', {'status': 'RUNNING'})
    with pytest.raises(ValueError):
        launch.activate()
    assert len(review.calls) == 1 and review.calls[0][0] == '/usr/bin/systemctl'
    assert not (review.root / 'call-authorization.json').exists()
