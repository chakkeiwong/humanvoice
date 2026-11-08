"""Additional call capacity retains native consumption and unreconciled holds."""

import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))

import grant_extension as extension
import pytest
from test_automatic_call_grant import authority, stage_plan

from humanvoice.artifacts import digest, read_json, write_json
from tools import automatic_call_grant as grants
from tools import automatic_program_account as account
from tools.ensemble_closure_contract import AllocationLedger
from tools.inventory_recovery_v3 import retired_grants

__all__ = ['authority']


@pytest.fixture
def approval(authority, tmp_path):
    grant, _account = authority
    original = read_json(grant)
    value = {'version': extension.VERSION, 'status': 'USER_AUTHORIZED',
        'authorized_by': 'user', 'authorization': 'Synthetic test authority: two more calls',
        'grant': str(grant), 'grant_identity': original['identity'],
        'original_maximum': 3, 'additional_calls': 2, 'total_maximum': 5,
        'no_replenishment_on_reload': True}
    value['identity'] = digest(value)
    path = tmp_path / 'approval.json'
    write_json(path, value)
    return path, value


def test_native_stage_claims_keep_original_grant_and_do_not_replenish_on_reload(authority, approval, tmp_path):
    grant, ledger_path = authority
    path, _ = approval
    original = grant.read_bytes()
    native = grants.status
    output = tmp_path / 'expanded-stage'
    plan = stage_plan(output, account.HISTORICAL_CEILING, 4)
    with pytest.raises(ValueError, match='exceeds available'), grants.stage(grant, output):
        pytest.fail('Unapproved stage entered')
    with extension.scope(path, expected_sha256=digest(path.read_bytes())):
        assert grants.status(grant)['maximum'] == 5
        assert retired_grants.status(grant)['maximum'] == 5
        with grants.stage(grant, output):
            account.claim(plan, output, account=ledger_path)
            ledger = AllocationLedger(output / 'allocation-ledger.json', plan)
            ledger.reserve('primary', 'case-0')
        checked = grants.status(grant)
        assert (checked['used'], checked['reserved_remaining'], checked['available']) == (1, 3, 1)
    assert grants.status is native and grant.read_bytes() == original
    with extension.scope(path, expected_sha256=digest(path.read_bytes())):
        assert grants.status(grant) == checked
        assert retired_grants.status(grant) == checked
        with grants.stage(grant, output):
            ledger.reserve('primary', 'case-1')
        assert (grants.status(grant)['used'], grants.status(grant)['reserved_remaining']) == (2, 2)
        other = tmp_path / 'overspend'
        stage_plan(other, account.HISTORICAL_CEILING, 2)
        with pytest.raises(ValueError, match='exceeds available'), grants.stage(grant, other):
            pytest.fail('Extension renewed reserved capacity')
    assert grant.read_bytes() == original


@pytest.mark.parametrize('defect', ['unapproved', 'authority', 'grant', 'identity', 'base',
    'boolean', 'negative', 'sum', 'reload', 'changed-bytes'])
def test_extension_rejects_wrong_or_changed_authority_before_stage_hold(authority, approval, tmp_path, defect):
    grant, _ = authority
    path, value = approval
    value = deepcopy(value)
    if defect == 'unapproved': value['status'] = 'AWAITING_USER_APPROVAL'
    elif defect == 'authority': value['authorized_by'] = 'agent'
    elif defect == 'grant': value['grant'] = str(tmp_path / 'another-grant.json')
    elif defect == 'identity': value['grant_identity'] = '0' * 64
    elif defect == 'base': value['original_maximum'] = 4
    elif defect == 'boolean': value['additional_calls'] = True
    elif defect == 'negative': value['additional_calls'] = -2
    elif defect == 'sum': value['total_maximum'] = 6
    elif defect == 'reload': value['no_replenishment_on_reload'] = False
    value['identity'] = digest({key: item for key, item in value.items() if key != 'identity'})
    write_json(path, value)
    checksum = digest(path.read_bytes())
    if defect == 'changed-bytes': path.write_bytes(path.read_bytes() + b' ')
    before = grant.read_bytes()
    with pytest.raises(ValueError), extension.scope(path, expected_sha256=checksum):
        grants.status(grant)
    assert not grant.with_suffix('.stages.json').exists()
    assert grant.read_bytes() == before


def test_extension_keeps_native_stage_and_allocation_checks(authority, approval, tmp_path):
    grant, account_path = authority
    path, _ = approval
    with extension.scope(path, expected_sha256=digest(path.read_bytes())):
        output = tmp_path / 'stage'
        plan = stage_plan(output, account.HISTORICAL_CEILING, 4)
        with grants.stage(grant, output):
            account.claim(plan, output, account=account_path)
            AllocationLedger(output / 'allocation-ledger.json', plan).reserve('primary', 'case-0')
        rows = read_json(grant.with_suffix('.stages.json'))
        rows['stages'] = []
        write_json(grant.with_suffix('.stages.json'), rows)
        with pytest.raises(ValueError, match='lost their durable stage authority'):
            grants.status(grant)
