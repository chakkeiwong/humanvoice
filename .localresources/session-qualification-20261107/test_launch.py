"""The grouped launch has one fixed service, deadline and human-reviewed scope."""

import launch
import pytest


@pytest.fixture(autouse=True)
def mounts(monkeypatch):
    monkeypatch.setattr(launch.namespace, 'properties', lambda authority: ['User=ubuntu',
        'PrivateUsers=no', 'ProtectSystem=strict', 'ProtectHome=read-only'])
    monkeypatch.setattr(launch.namespace, 'environment', lambda: {'HUMANVOICE_AUDIT_WORKERS': '16'})


def test_service_command_keeps_fixed_total_deadline_and_bounded_crash_reentry():
    command = launch.service_command({}, now=launch.execution.WINDOW_END - 7200)
    assert command[:3] == ['/usr/bin/pkexec', '/usr/bin/systemd-run', '--unit=' + launch.supervise.UNIT]
    assert '--property=RuntimeMaxSec=7200' in command
    assert '--no-block' in command
    assert '--property=RestartPreventExitStatus=2' in command
    assert '--property=KillMode=control-group' in command
    assert '--property=StartLimitBurst=3' in command
    assert command[-3:] == [launch.execution.PYTHON, str(launch.HERE / 'supervise.py'), 'run']
    assert '--setenv=HUMANVOICE_AUDIT_WORKERS=16' in command
    assert '--property=User=ubuntu' in command and '--property=PrivateUsers=no' in command
    assert '--property=ProtectSystem=strict' in command and '--property=ProtectHome=read-only' in command


@pytest.mark.parametrize('offset', [0, -1, 172801])
def test_service_command_rejects_expired_or_extended_window(offset):
    with pytest.raises(ValueError, match='renewed execution window'):
        launch.service_command({}, now=launch.execution.WINDOW_END - offset)
