"""No-call host probes retain the reviewed mount builder and block remote routes."""

import namespace_probe as probe
import pytest


@pytest.mark.parametrize('kind', ['environment', 'protocol', 'signal'])
def test_offline_probe_uses_exact_live_mount_prefix_with_isolated_network(monkeypatch, kind):
    authority = {'reviewed': 'roots'}
    groups = [(1, 'fixture')]
    properties = ['PrivateUsers=no', 'PrivateMounts=yes', 'PrivateNetwork=yes',
        'User=ubuntu', 'ProtectSystem=strict', 'BindReadOnlyPaths=/fixture:/fixture']
    monkeypatch.setattr(probe, 'inputs', lambda: authority)

    def settings(value, *, groups=None, isolated_network=False):
        assert value == authority and groups == [(1, 'fixture')]
        assert isolated_network is True
        return list(properties)

    monkeypatch.setattr(probe.namespace, 'properties', settings)
    monkeypatch.setattr(probe, 'read_json', lambda _path:
        {'current_binding': {'credentials': {'path': '/fixture/.codex/auth.json'}}})
    result = probe.command(kind, 'parent-network', {'HOME': '/home/ubuntu'}, 'offline-fixture.service', groups=groups)
    actual = [x.removeprefix('--property=') for x in result if x.startswith('--property=')]
    expected = list(properties)
    if kind == 'protocol':
        expected[-1] += ' ' + str(probe.HERE / 'scratch/dummy-auth.json') + ':/home/ubuntu/.codex/auth.json'
    assert actual == ['RuntimeMaxSec=75', 'TimeoutStopSec=10', 'KillMode=control-group', *expected]
    assert result[-4:] == [probe.execution.PYTHON, str(probe.HERE / 'namespace_probe.py'), kind, 'parent-network']


def test_namespace_probe_rejects_unbounded_action_before_mount_construction(monkeypatch):
    monkeypatch.setattr(probe.namespace, 'command', lambda *_args, **_kwargs: pytest.fail('built live command'))
    with pytest.raises(ValueError, match='Unknown fixed namespace probe'):
        probe.command('execute', 'parent-network', {}, 'offline-fixture.service')


def test_preparation_freezes_host_network_even_inside_temporary_command_sandbox(monkeypatch):
    monkeypatch.setattr(probe, 'read_json', lambda _path: {'current_binding': {'server': {'pid': 123}}})
    monkeypatch.setattr(probe.os, 'readlink', lambda path:
        'net:[host]' if path == '/proc/123/ns/net' else 'net:[temporary-sandbox]')
    monkeypatch.setattr(probe, 'inputs', dict)
    monkeypatch.setattr(probe.namespace, 'properties', lambda *_a, **_k: [])
    assert probe.scope(environment={})['parent_network'] == 'net:[host]'
