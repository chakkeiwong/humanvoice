"""Root probe setup owns only its unique service and cleans a timed-out run."""

import subprocess
from types import SimpleNamespace

import pytest
import system_probe as probe


@pytest.fixture
def service(monkeypatch):
    state = SimpleNamespace(active=False, stopped=False, returncode=0, timeout=False, commands=[])

    def show(_unit):
        return {'LoadState': 'loaded' if state.active else 'not-found',
            'ActiveState': 'active' if state.active else 'inactive',
            'MainPID': '123' if state.active else '0', 'ControlPID': '0'}

    class Child:
        returncode = None

        def communicate(self, **_kwargs):
            if state.timeout and not state.stopped:
                raise subprocess.TimeoutExpired('offline-probe', 100)
            self.returncode = state.returncode
            state.active = False
            return b'{"offline":true}', b''

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

    def start(command, **_kwargs):
        state.active = True
        state.commands.append(command)
        return Child()

    def stop(command, **_kwargs):
        assert command[:2] == ['/usr/bin/systemctl', 'stop']
        state.stopped = True
        state.active = False
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(probe, 'show', show)
    monkeypatch.setattr(probe, 'command', lambda kind, scope, unit: [kind, unit])
    monkeypatch.setattr(probe.subprocess, 'Popen', start)
    monkeypatch.setattr(probe.subprocess, 'run', stop)
    return state


@pytest.mark.parametrize('code', [0, 1, 137])
def test_terminal_probe_retains_status_and_confirms_cleanup(service, code):
    service.returncode = code
    result = probe.run_probe('signal', {'parent_network': 'net:[1]', 'environment': {}})
    assert result['returncode'] == code and result['cleanup']['complete']
    assert not service.active
    assert service.commands[0][1].startswith('humanvoice-qualification-offline-signal-')


def test_timed_out_probe_stops_owned_service_and_reaps_launcher(service):
    service.timeout = True
    with pytest.raises(subprocess.TimeoutExpired):
        probe.run_probe('environment', {'parent_network': 'net:[1]', 'environment': {}})
    assert service.stopped and not service.active
