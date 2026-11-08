"""Authentication reuse never enlarges or silently renews the approved scope."""

import ast
import copy
import json
import socket
import subprocess

import namespace
import pytest
import system_probe as probe


@pytest.fixture
def scope():
    authority = {'account': str(namespace.ROOT / '.localresources/automatic-program/account.json'),
        'grant': str(namespace.ROOT / 'docs/audits/2026-10-05/master-program/automatic-execution/grant.json')}
    authority['writable_roots'] = [str(namespace.HERE), str(namespace.Path(authority['account']).parent),
        str(namespace.Path(authority['grant']).parent), str(namespace.ROOT / 'docs/plans')]
    groups = [(i, 'humanvoice/docs/audits/frozen-' + str(i)) for i in range(27)]
    return {'parent_network': 'net:[123]', 'helper_sha256': 'a' * 64,
        'environment': {'HOME': '/home/ubuntu', 'TMPDIR': str(probe.HERE / 'scratch'),
            'CODEX_SQLITE_HOME': str(probe.HERE / 'scratch/client-state/sqlite')},
        'properties': namespace.properties(authority, isolated_network=True, groups=groups)}


@pytest.fixture
def session(scope, monkeypatch):
    calls = []
    monkeypatch.setattr(probe, 'run_probe', lambda kind, packet: calls.append((kind, packet)) or {'pass': True})
    monkeypatch.setattr(probe.time, 'monotonic', lambda: 1000)
    return probe.Session(scope, 3600), calls


def call(session, action='check', uid=1000):
    return session.handle({'action': action, 'scope_sha256': session.identity}, uid)


def test_eight_batches_reuse_one_unchanged_session_then_refuse_more(session, monkeypatch):
    state, calls = session
    monkeypatch.setattr(probe.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('re-authenticated'))
    deadline = state.deadline
    for number in range(1, 9):
        result = call(state)
        assert result['batches_used'] == number and set(result['reports']) == set(probe.KINDS)
        assert state.deadline == deadline
    with pytest.raises(ValueError, match='exhausted'):
        call(state)
    assert len(calls) == 24
    assert call(state, 'status')['batches_used'] == 8


@pytest.mark.parametrize('change', ['PrivateNetwork=no', 'User=root', 'Group=root',
    'NoNewPrivileges=no', 'CapabilityBoundingSet=CAP_SYS_ADMIN', 'ReadWritePaths=/home/ubuntu',
    'BindPaths=/home/ubuntu/.codex:/home/ubuntu/.codex', 'ExecStart=/bin/sh'])
def test_broader_privilege_or_command_is_rejected_before_service_launch(scope, change):
    key = change.split('=', 1)[0]
    scope['properties'] = [p for p in scope['properties'] if not p.startswith(key + '=')] + [change]
    with pytest.raises(ValueError, match='broadened'):
        probe.Session(scope, 3600)


def test_caller_cannot_change_frozen_mounts_or_environment(session, scope):
    state, calls = session
    scope['environment']['HOME'] = '/root'
    scope['properties'].append('PrivateNetwork=no')
    with pytest.raises(ValueError, match='scope changed'):
        state.handle({'action': 'check', 'scope_sha256': probe.identity(scope)}, 1000)
    assert not calls and state.scope['environment']['HOME'] == '/home/ubuntu'


@pytest.mark.parametrize('uid', [0, 1001, 65534])
def test_peer_credentials_are_required_for_every_action(session, uid):
    state, calls = session
    with pytest.raises(ValueError, match='authenticated ubuntu'):
        call(state, uid=uid)
    assert not calls and state.used == 0


def test_deadline_close_and_failed_attempt_do_not_reset_allowance(session, monkeypatch):
    state, calls = session

    def failure(*_args):
        raise subprocess.TimeoutExpired('offline', 100)

    monkeypatch.setattr(probe, 'run_probe', failure)
    with pytest.raises(subprocess.TimeoutExpired):
        call(state)
    assert state.used == 1
    monkeypatch.setattr(probe.time, 'monotonic', lambda: state.deadline - 100)
    with pytest.raises(ValueError, match='expiry'):
        call(state)
    assert call(state, 'close')['closed']
    with pytest.raises(ValueError, match='closed'):
        call(state)
    assert not calls


def test_expired_session_cannot_be_renewed_by_a_request(session, monkeypatch):
    state, calls = session
    monkeypatch.setattr(probe.time, 'monotonic', lambda: state.deadline)
    with pytest.raises(ValueError, match='expired'):
        call(state)
    assert not calls


def test_unknown_actions_and_extra_commands_are_rejected(session):
    state, calls = session
    with pytest.raises(ValueError, match='Unknown'):
        call(state, 'production')
    with pytest.raises(ValueError, match='scope changed'):
        state.handle({'action': 'check', 'scope_sha256': state.identity, 'command': ['/bin/sh']}, 1000)
    assert not calls


def test_service_arguments_always_bound_command_uid_network_and_lifetime(scope):
    for kind in probe.KINDS:
        command = probe.command(kind, scope, 'test.service')
        assert command[-4:] == [probe.PYTHON, str(probe.HERE / 'namespace_probe.py'), kind, 'net:[123]']
        assert {'--property=PrivateNetwork=yes', '--property=User=ubuntu', '--property=Group=ubuntu',
            '--property=RuntimeMaxSec=75', '--property=KillMode=control-group'} <= set(command)
        assert 'pkexec' not in ' '.join(command)
    with pytest.raises(ValueError):
        probe.command('execute', scope, 'test.service')


def test_socket_message_is_bounded_and_incomplete_disconnect_is_rejected():
    for raw, error in [(b'x' * 33, 'bound'), (b'{', 'disconnected')]:
        reader, writer = socket.socketpair()
        with reader, writer:
            writer.sendall(raw)
            writer.shutdown(socket.SHUT_WR)
            with pytest.raises(ValueError, match=error):
                probe.receive(reader, 32)


def test_privileged_helper_imports_only_standard_library():
    tree = ast.parse(probe.Path(probe.__file__).read_text())
    allowed = {'base64', 'copy', 'fcntl', 'hashlib', 'json', 'os', 're', 'signal',
        'socket', 'stat', 'struct', 'subprocess', 'sys', 'time', 'uuid', 'pathlib'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(item.name in allowed for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed


def test_response_encoding_is_stable_and_scope_cannot_alias_caller(scope):
    state = probe.Session(scope, 3600)
    expected = copy.deepcopy(state.scope)
    scope['environment'].clear()
    assert state.scope == expected
    assert probe.identity(json.loads(json.dumps(expected))) == state.identity
