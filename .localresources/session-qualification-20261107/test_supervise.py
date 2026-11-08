"""Supervisor progress and restart decisions cannot invent completed work."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
import supervise

from humanvoice.artifacts import write_json


@pytest.mark.parametrize(('previous', 'alive', 'expected'), [
    (None, False, 'START'),
    ({'status': 'STARTING'}, False, 'RECONCILE_BEFORE_RESTART'),
    ({'status': 'RUNNING', 'child_owner': {'pid': 123}}, True, 'OBSERVE_OWNED_CHILD'),
    ({'status': 'RUNNING', 'child_owner': {'pid': 123}}, False, 'RECONCILE_BEFORE_RESTART'),
    ({'status': 'QUALIFICATION_BLOCKED'}, False, 'RECONCILE_BEFORE_RESTART'),
    ({'status': 'RUNNING', 'launches': 1}, False, 'RECONCILE_NATIVE'),
    ({'status': 'WORKER_CRASHED', 'launches': 2}, False, 'RECONCILE_NATIVE'),
    ({'status': 'WORKER_CRASHED', 'launches': 3}, False, 'RECONCILE_BEFORE_RESTART'),
    ({'status': 'WORKER_CRASHED', 'launches': True}, False, 'RECONCILE_BEFORE_RESTART'),
    ({'status': 'QUALIFICATION_BLOCKED', 'launches': 1}, False, 'RECONCILE_BEFORE_RESTART'),
    ({'status': 'CURRENT_CLIENT_QUALIFICATION_VERIFIED', 'child_owner': {'pid': 123}},
        True, 'OBSERVE_OWNED_CHILD'),
    ({'status': 'CURRENT_CLIENT_QUALIFICATION_VERIFIED'}, False, 'DONE'),
])
def test_restart_never_duplicates_a_recorded_or_ambiguous_launch(previous, alive, expected):
    assert supervise.disposition(previous, alive=lambda _owner: alive) == expected


def test_progress_counts_native_completed_and_unknown_allocations_separately(tmp_path):
    write_json(tmp_path / 'execution.json', {'status': 'paused_availability'})
    write_json(tmp_path / 'allocation-ledger.json', {'calls': [
        {'status': 'complete'}, {'status': 'incomplete'}, {'status': 'allocated_unknown'}]})
    observed = supervise.inspect_progress(tmp_path)
    assert (observed['allocated'], observed['completed'], observed['unresolved']) == (3, 1, 1)
    assert observed['terminal'] == 'paused_availability'
    assert supervise.inspect_progress(tmp_path) == observed


def test_prepared_qualification_needs_no_synthetic_ledger(tmp_path):
    observed = supervise.inspect_progress(tmp_path)
    assert observed == {'allocated': 0, 'completed': 0, 'unresolved': 0,
        'terminal': None, 'ledger_sha256': None}
