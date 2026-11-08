"""Exercise the supervisor around real child exit, signal, and receipt boundaries."""

import os
import signal
import sys

import pytest
import supervise

from humanvoice.artifacts import read_json, write_json


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(supervise, 'HERE', tmp_path)
    masters = tuple(tmp_path / name for name in ('master.md', 'ensemble.md'))
    for path in masters:
        path.write_text('Retained master content\n')
    monkeypatch.setattr(supervise.program_projection, 'MASTERS', masters)
    output = tmp_path / 'qualification-host'
    output.mkdir()
    record = {'identity': 'approved-fixture', 'window_end_utc': supervise.execution.WINDOW_END}
    plan = {'plan_identity': 'native-plan', 'profile': {'model': 'fixture'}}
    monkeypatch.setattr(supervise.execution, 'approved_inputs',
        lambda: (record, {'output': str(output)}, {}, plan, {}))
    monkeypatch.setattr(supervise, 'require_empty_service', lambda: {'members': [os.getpid()]})
    monkeypatch.setattr(supervise.time, 'time', lambda: supervise.execution.WINDOW_END - 120)
    # Test children run in the same suite sandbox and never invoke a provider.
    command = [sys.executable, '-c', 'raise SystemExit(2)']
    monkeypatch.setattr(supervise.namespace, 'command', lambda _record: command)
    native_sleep = supervise.time.sleep
    monkeypatch.setattr(supervise.time, 'sleep', lambda _seconds: native_sleep(0.01))
    return tmp_path, output, command, plan


@pytest.mark.parametrize('namespace_exit', [False, True])
def test_killed_child_is_reaped_and_reentry_does_not_erase_unknown_receipts(boundary, namespace_exit):
    root, output, command, _plan = boundary
    write_json(output / 'allocation-ledger.json', {'calls': [{'status': 'allocated_unknown'}]})
    before = (output / 'allocation-ledger.json').read_bytes()
    command[-1] = ('raise SystemExit(137)' if namespace_exit else
        'import os, signal; os.kill(os.getpid(), signal.SIGKILL)')
    assert supervise.run() == 75
    first = read_json(root / 'supervisor-status.json')
    assert first['status'] == 'WORKER_CRASHED' and first['launches'] == 1
    assert first['returncode'] == (137 if namespace_exit else -signal.SIGKILL)
    assert first['cleanup']['complete'] and first['descendant_cleanup']['descendants_quiescent']
    # An unresolved native allocation blocks the next worker rather than clearing
    # the ledger. A completed nonzero result is never retried by the supervisor.
    command[-1] = 'raise SystemExit(2)'
    assert supervise.run() == 2
    second = read_json(root / 'supervisor-status.json')
    assert second['restart_mode'] == 'RECONCILE_NATIVE' and second['launches'] == 2
    assert second['status'] == 'QUALIFICATION_BLOCKED'
    assert second['progress']['unresolved'] == 1
    assert 'QUALIFICATION_BLOCKED' in (root / 'master.md').read_text()
    assert 'Retained master content' in (root / 'master.md').read_text()
    assert (output / 'allocation-ledger.json').read_bytes() == before
    with pytest.raises(ValueError, match='durable ownership'):
        supervise.run()


def test_verified_result_is_idempotent_and_does_not_launch_again(boundary):
    root, output, command, plan = boundary
    evidence = {'status': 'QUALIFICATION_VERIFIED', 'profile_hash': supervise.digest(plan['profile']),
        'purposes': supervise.execution.migration_policy.PURPOSES, 'settled': True, 'canary_only': False,
        'output': str(output), 'plan_identity': plan['plan_identity'], 'evaluation_hash': 'fixture-evaluation'}
    write_json(root / 'qualification-verified.json', evidence)
    command[-1] = 'raise SystemExit(0)'
    assert supervise.run() == 0
    before = (root / 'supervisor-status.json').read_bytes()
    command[-1] = 'raise SystemExit(2)'
    assert supervise.run() == 0
    assert (root / 'supervisor-status.json').read_bytes() == before
    assert 'CURRENT_CLIENT_QUALIFICATION_VERIFIED' in (root / 'master.md').read_text()


def test_bad_progress_cannot_hide_terminal_failure_or_prevent_cleanup(boundary):
    root, output, command, _plan = boundary
    (output / 'allocation-ledger.json').write_text('invalid interrupted ledger')
    command[-1] = 'import time; time.sleep(20)'
    assert supervise.run() == 2
    state = read_json(root / 'supervisor-status.json')
    assert state['status'] == 'QUALIFICATION_BLOCKED'
    assert state['progress'] is None and 'Native progress unavailable' in state['error']
    assert state['cleanup']['complete'] and state['descendant_cleanup']['descendants_quiescent']


def test_cleanup_exception_still_cleans_descendants_and_blocks_restart(boundary, monkeypatch):
    root, _output, _command, _plan = boundary
    calls = []
    original = supervise.Descendants.finish

    def finish(owner):
        calls.append('descendants')
        return original(owner)

    def cleanup(*_args, **_kwargs):
        raise OSError('simulated process inspection failure')

    monkeypatch.setattr(supervise, 'cleanup', cleanup)
    monkeypatch.setattr(supervise.Descendants, 'finish', finish)
    assert supervise.run() == 2
    state = read_json(root / 'supervisor-status.json')
    assert state['status'] == 'QUALIFICATION_BLOCKED' and not state['cleanup']['complete']
    assert state['descendant_cleanup']['descendants_quiescent'] and calls == ['descendants']


def test_master_refresh_failure_preserves_completed_cleanup_and_visible_error(boundary, monkeypatch):
    root, _output, _command, _plan = boundary

    def refresh(_state):
        raise OSError('simulated master filesystem failure')

    monkeypatch.setattr(supervise.program_projection, 'refresh', refresh)
    assert supervise.run() == 2
    state = read_json(root / 'supervisor-status.json')
    assert state['status'] == 'QUALIFICATION_BLOCKED' and state['cleanup']['complete']
    assert 'master filesystem failure' in state['master_refresh_error']
