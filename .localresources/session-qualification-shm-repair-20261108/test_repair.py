"""Shared-memory fix retains budgets and tests the actual service before restart."""

import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import host
import pytest
import repair


@pytest.fixture
def stopped():
    progress = {'allocated': 0, 'completed': 0, 'unresolved': 0,
        'terminal': 'prepared', 'ledger_sha256': None}
    return ({'status': 'QUALIFICATION_BLOCKED', 'launches': 2, 'owner': {}, 'child_owner': {},
        'cleanup': {'complete': True}, 'descendant_cleanup': {'descendants_quiescent': True},
        'progress': deepcopy(progress)}, {'status': 'QUALIFICATION_BLOCKED', 'error': repair.ERROR}, progress)


@pytest.mark.parametrize('defect', ['spent', 'unknown', 'cleanup', 'limit', 'error'])
def test_final_launch_guard_rejects_any_ambiguity_or_changed_failure(stopped, defect):
    state, failure, progress = stopped
    if defect == 'spent': progress['allocated'] = 1
    elif defect == 'unknown': progress['unresolved'] = 1
    elif defect == 'cleanup': state['cleanup']['complete'] = False
    elif defect == 'limit': state['launches'] = 3
    else: failure['error'] = 'semantic failure'
    with pytest.raises(ValueError):
        repair.unspent(state, failure, progress, alive=lambda _: False)


def test_only_private_shared_memory_permissions_change(monkeypatch, stopped):
    repair.unspent(*stopped, alive=lambda _: False)
    baseline = ['User=ubuntu', 'ProtectSystem=strict', 'TemporaryFileSystem=/dev/shm:rw,nosuid,nodev']
    monkeypatch.setattr(repair.namespace, 'properties', lambda authority, isolated_network:
        [*baseline, 'PrivateNetwork=' + ('yes' if isolated_network else 'no')])
    offline, live = (repair.properties({}, offline=mode) for mode in (True, False))
    assert offline == [*baseline[:-1], baseline[-1] + ',mode=1777', 'PrivateNetwork=yes']
    assert live == [*offline[:-1], 'PrivateNetwork=no']


def test_grouped_host_never_submits_live_after_failed_preflight(monkeypatch):
    calls = []
    packet = {'identity': 'fixture', 'offline_command': ['offline'], 'live_command': ['live']}
    monkeypatch.setattr(host.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(host.sys, 'executable', '/usr/bin/python3')
    from types import SimpleNamespace

    monkeypatch.setattr(host.sys, 'flags', SimpleNamespace(isolated=True))
    monkeypatch.setattr(host.sys, 'argv', ['host.py', 'start', host.hashlib.sha256(b'{}').hexdigest()])
    monkeypatch.setattr(host.Path, 'read_bytes', lambda _: b'{}')
    monkeypatch.setattr(host, 'validate', lambda _: packet)
    monkeypatch.setattr(host, 'idle', lambda _: True)
    monkeypatch.setattr(host, 'show', lambda _: {'LoadState': 'not-found', 'ActiveState': 'inactive'})

    def fail(command, **kwargs):
        calls.append(command)
        raise host.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(host.subprocess, 'run', fail)
    with pytest.raises(host.subprocess.CalledProcessError):
        host.main()
    assert calls == [['offline']]
