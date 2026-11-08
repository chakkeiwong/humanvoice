"""The receipt repair retains the approved service and never replenishes budget."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import host
import pytest
import resume


@pytest.fixture
def packet(monkeypatch):
    monkeypatch.setattr(host.time, 'time', lambda: 1794158980 - 1000)
    return {'action': 'resume-exact-unspent-qualification', 'unit': host.UNIT,
        'additional_calls': 0, 'total_call_ceiling': 2235, 'prior_launches': 1,
        'maximum_total_launches': 3, 'window_end': 1794158980, 'sources': {},
        'command': ['/usr/bin/systemd-run', '--unit=' + host.UNIT, '--no-block',
            '--property=User=ubuntu', '--property=Group=ubuntu', '--property=NoNewPrivileges=yes',
            '--property=CapabilityBoundingSet=', '--property=ProtectSystem=strict',
            '--property=ProtectHome=tmpfs', '--property=KillMode=control-group',
            '--property=RestartPreventExitStatus=2', '--', host.PYTHON, str(host.SCRIPT), 'run']}


@pytest.mark.parametrize('defect', ['calls', 'launches', 'deadline', 'unit', 'worker', 'root', 'source'])
def test_host_refuses_budget_reset_or_changed_service(packet, defect, tmp_path):
    if defect == 'calls': packet['additional_calls'] = 235
    elif defect == 'launches': packet['prior_launches'] = 0
    elif defect == 'deadline': packet['window_end'] += 1
    elif defect == 'unit': packet['unit'] = 'another.service'
    elif defect == 'worker': packet['command'][-2] = '/tmp/arbitrary.py'
    elif defect == 'root': packet['command'].remove('--property=User=ubuntu')
    elif defect == 'source':
        path = tmp_path / 'source.py'
        path.write_text('changed')
        packet['sources'][str(path)] = 'a' * 64
    with pytest.raises(ValueError):
        host.validate(packet)


def test_restart_changes_only_worker_entry_and_keeps_original_service_properties(packet, monkeypatch):
    original = ['/usr/bin/pkexec', *packet['command'][:-3], host.PYTHON,
        str(resume.PREVIOUS / 'supervise.py'), 'run']
    monkeypatch.setattr(resume.launch, 'service_command', lambda authority, now: list(original))
    result = resume.command({'original': 'authority'})
    assert result == packet['command']
    assert host.validate(packet) == result
