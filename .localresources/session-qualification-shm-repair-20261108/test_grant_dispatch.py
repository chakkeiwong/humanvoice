"""Copied grant readers retain historical dispatch and native drift rejection."""

import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent),
    str(Path(__file__).resolve().parents[2] / 'tests'),
    str(Path(__file__).resolve().parents[1] / 'session-migration-20261107')]

import grant_dispatch
import grant_extension
import pytest
from test_automatic_call_grant import authority, stage_plan

from humanvoice.artifacts import digest, read_json, write_json
from tools import automatic_call_grant as grants
from tools import automatic_program_account as account
from tools.inventory_recovery_v3 import accounting, retired_grants, runtime

__all__ = ['authority']


@pytest.fixture
def settled(authority, tmp_path, monkeypatch):
    grant, account_path = authority
    output = tmp_path / 'historical'
    plan = stage_plan(output, account.HISTORICAL_CEILING, 1)
    original = read_json(grant)
    write_json(output / 'allocation-ledger.json', {'calls': [{'status': 'complete'}]})
    usage = {'plan_identity': plan['plan_identity'], 'output': str(output), 'model_calls': 1}
    write_json(output / 'verified-usage.json', usage)
    record = {'plans': [{'plan_identity': plan['plan_identity'], 'output': str(output)}],
        'events': [{'kind': 'settle', 'usage': usage}]}
    write_json(account_path, record)
    write_json(grant.with_suffix('.stages.json'), {'stages': [{'output': str(output),
        'plan_identity': plan['plan_identity'], 'grant_identity': original['identity'], 'maximum_calls': 1}]})
    # Structural account verification is tested by the real isolated replay;
    # retain all native grant checks here and isolate only historical usage.
    monkeypatch.setattr(grants, 'validate_account', lambda value: value)
    calls = []

    def verify(path):
        calls.append(Path(path))
        return {'report': read_json(Path(path) / 'verified-usage.json')}

    monkeypatch.setattr(accounting, 'verify_settlement', verify)
    extension = {'version': grant_extension.VERSION, 'status': 'USER_AUTHORIZED',
        'authorized_by': 'user', 'authorization': 'Synthetic two-call addition',
        'grant': str(grant), 'grant_identity': original['identity'], 'original_maximum': 3,
        'additional_calls': 2, 'total_maximum': 5, 'no_replenishment_on_reload': True}
    extension['identity'] = digest(extension)
    approval = tmp_path / 'approval.json'
    write_json(approval, extension)
    return grant, output, approval, calls


def test_extension_captures_dispatch_before_later_history_scope(settled, monkeypatch):
    grant, output, approval, calls = settled
    original = grants.settled_usage
    original_bytes = grant.read_bytes()
    with grant_dispatch.scope(), grant_extension.scope(approval, expected_sha256=digest(approval.read_bytes())), (
            monkeypatch.context()) as patch:
        # The extension already copied its globals. A later ambient reader
        # must not replace its independently selected historical profile.
        patch.setattr(grants, 'settled_usage', lambda _: pytest.fail('ambient profile used'))
        status = grants.status(grant)
        assert (status['maximum'], status['used'], status['available']) == (5, 1, 4)
        assert retired_grants.status(grant) == status
    assert calls == [output, output]
    assert grants.settled_usage is original and grant.read_bytes() == original_bytes


def test_nested_native_scope_preserves_independent_dispatch_identity(settled):
    grant, _output, approval, _calls = settled
    original = accounting.completed_usage
    with grant_dispatch.scope(), grant_extension.scope(approval, expected_sha256=digest(approval.read_bytes())), (
            runtime.settlement_scope()):
        assert accounting.completed_usage is original
        assert grants.status(grant)['available'] == 4
        assert grants.settled_usage(_output) == read_json(_output / 'verified-usage.json')
    assert accounting.completed_usage is original


@pytest.mark.parametrize('defect', ['usage', 'receipt', 'plan'])
def test_native_grant_still_rejects_changed_evidence_and_restores_scope(settled, defect, monkeypatch):
    grant, output, approval, _calls = settled
    original = grants.settled_usage
    if defect == 'usage':
        value = read_json(output / 'verified-usage.json')
        value['model_calls'] = 0
        write_json(output / 'verified-usage.json', value)
        expected = 'Stage settlement changed'
    elif defect == 'plan':
        value = read_json(output / 'plan.json')
        value['calls'][0]['input_hash'] = 'changed'
        write_json(output / 'plan.json', value)
        expected = 'stage reservation changed'
    else:
        def fail(_):
            raise ValueError('Native receipt changed')
        monkeypatch.setattr(accounting, 'verify_settlement', fail)
        expected = 'Native receipt changed'
    with pytest.raises(ValueError, match=expected), grant_dispatch.scope(), (
            grant_extension.scope(approval, expected_sha256=digest(approval.read_bytes()))):
        grants.status(grant)
    assert grants.settled_usage is original
