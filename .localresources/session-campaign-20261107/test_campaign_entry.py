"""Command migration retains every native ownership and spending field."""

from copy import deepcopy

import campaign_entry as entry
import pytest


def native_configuration():
    command = [entry.configuration.PYTHON, '-I', str(entry.ROOT / 'tools/finalization_public.py')]
    value = {key: command + [action] for key, action in entry.finalization_configuration.ACTIONS.items()}
    value.update(execution_authority={'account': '/native/account', 'grant': '/native/grant'},
        stop_floor={'identity': 'retained'}, policy={'remaining_requests': 439},
        approval_policy='on-request', approvals_reviewer='user', sandbox_mode='workspace-write')
    return {**value, 'identity': entry.digest(value)}


def test_public_child_commands_share_one_adapter_without_changing_authority():
    before = native_configuration()
    original = deepcopy(before)
    active = {'identity': 'qualified-activation', 'candidate_identity': 'current-client'}
    changed = entry.project(before, active)
    assert before == original
    for key, action in entry.finalization_configuration.ACTIONS.items():
        assert changed[key] == [entry.configuration.PYTHON, '-I', str(entry.HERE / 'campaign_entry.py'), action]
    for key, value in before.items():
        if key not in entry.finalization_configuration.ACTIONS and key != 'identity':
            assert changed[key] == value
    assert changed['identity'] == entry.digest({k: v for k, v in changed.items() if k != 'identity'})


@pytest.mark.parametrize('defect', ['rehashed-command', 'tampered-authority', 'already-projected'])
def test_public_projection_rejects_changed_native_command_or_identity(defect):
    value = native_configuration()
    if defect == 'rehashed-command':
        value['worker'][-1] = 'campaign-execute'
        value['identity'] = entry.digest({k: v for k, v in value.items() if k != 'identity'})
    elif defect == 'tampered-authority':
        value['approval_policy'] = 'never'
    else:
        value['current_client_adapter'] = {}
    with pytest.raises(ValueError):
        entry.project(value, {'identity': 'qualified-activation', 'candidate_identity': 'current-client'})
