"""Real protocol gate must reject failed transport without qualification credit."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from client_transition import protocol_evidence

spec = importlib.util.spec_from_file_location('tested_client_protocol',
    Path(__file__).with_name('client_protocol.py'))
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


@pytest.fixture
def observation():
    return {'status': 'pass', 'provider_calls': 0, 'real_credentials': False,
        'isolation': {'distinct_from_parent': True, 'interfaces': ['lo'],
            'remote_egress': 'blocked_by_network_namespace'},
        'process': {'status': 'complete', 'group_quiescent': True},
        'events': {'accepted': True},
        'requests': [{'kind': 'responses_post', 'request_binding_valid': True}]}


@pytest.mark.parametrize('defect', ['nonpass', 'provider', 'boolean', 'credential',
    'network', 'interface', 'egress', 'process', 'cleanup', 'event', 'requests', 'binding'])
def test_protocol_failure_cannot_yield_credit(observation, defect):
    if defect == 'nonpass': observation['status'] = 'nonpass'
    elif defect == 'provider': observation['provider_calls'] = 1
    elif defect == 'boolean': observation['provider_calls'] = False
    elif defect == 'credential': observation['real_credentials'] = True
    elif defect == 'network': observation['isolation']['distinct_from_parent'] = False
    elif defect == 'interface': observation['isolation']['interfaces'].append('eth0')
    elif defect == 'egress': observation['isolation']['remote_egress'] = 'unknown'
    elif defect == 'process': observation['process']['status'] = 'timeout'
    elif defect == 'cleanup': observation['process']['group_quiescent'] = False
    elif defect == 'event': observation['events']['accepted'] = False
    elif defect == 'requests': observation['requests'].append(deepcopy(observation['requests'][0]))
    else: observation['requests'][0]['request_binding_valid'] = False
    with pytest.raises(ValueError):
        protocol.validate_observation(observation)


@pytest.fixture
def boundary(tmp_path, monkeypatch, observation):
    executable = tmp_path / 'codex'
    executable.write_bytes(b'current client fixture')
    binding = {'server': {'executable': str(executable)},
        'executable_sha256': protocol.digest(executable.read_bytes())}
    value = {'identity': 'f' * 64, 'current_binding': binding}
    state = SimpleNamespace(commands=[], verified=[], returncode=0, result=observation)
    monkeypatch.setattr(protocol.migration.settings, 'verify', lambda item: state.verified.append(item))
    monkeypatch.setattr(protocol, 'source_hashes', lambda:
        {str(path): 'a' * 64 for path in protocol.SOURCES})
    monkeypatch.setattr(protocol, 'DIAGNOSTICS', tmp_path / 'protocol-attempts')

    def run(argv, **keywords):
        state.commands.append(argv)
        assert keywords == {'capture_output': True, 'text': True, 'timeout': 60, 'check': False}
        return SimpleNamespace(returncode=state.returncode, stdout=json.dumps(state.result), stderr='')

    monkeypatch.setattr(protocol.subprocess, 'run', run)
    return value, state


def test_all_authorized_models_use_current_client_and_no_remote_probe(boundary):
    value, state = boundary
    result = protocol.inspect(value)
    assert len(state.commands) == 3 and len(state.verified) == 5
    assert all(binding == value['current_binding'] for binding in state.verified)
    assert [(argv[argv.index('--model') + 1], argv[argv.index('--effort') + 1])
        for argv in state.commands] == list(protocol.migration.routing.ORDER)
    assert all(argv[0:3] == [protocol.PYTHON, '-I', str(protocol.PROBE)]
        and argv[argv.index('--executable') + 1] == value['current_binding']['server']['executable']
        for argv in state.commands)
    assert result['model_calls'] == result['external_calls'] == 0
    assert result['production_admitted'] is result['historical_qualification_reused'] is False
    assert protocol_evidence(value, result) == result


@pytest.mark.parametrize('defect', ['process', 'receipt', 'source', 'binary', 'session'])
def test_failed_matrix_never_returns_a_passing_report(boundary, monkeypatch, defect):
    value, state = boundary
    if defect == 'process': state.returncode = 1
    elif defect == 'receipt': state.result['status'] = 'nonpass'
    elif defect == 'source':
        versions = iter([{'source': 'a' * 64}, {'source': 'b' * 64}])
        monkeypatch.setattr(protocol, 'source_hashes', lambda: next(versions))
    elif defect == 'binary':
        Path(value['current_binding']['server']['executable']).write_bytes(b'replaced')
    else:
        monkeypatch.setattr(protocol.migration.settings, 'verify', lambda value:
            (_ for _ in ()).throw(ValueError('session changed')))
    with pytest.raises(ValueError):
        protocol.inspect(value)


def test_probe_interpreter_survives_private_tmp_and_failure_keeps_diagnostics(boundary):
    value, state = boundary
    assert protocol.PYTHON == '/home/ubuntu/miniforge3/bin/python'
    assert not Path(protocol.PYTHON).is_relative_to('/tmp')
    state.returncode = 1
    with pytest.raises(ValueError, match='diagnostics='):
        protocol.inspect(value)
    records = list(protocol.DIAGNOSTICS.glob('attempt-*/*.json'))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record['returncode'] == 1
    assert records[0].with_suffix('.stdout').read_text() == json.dumps(state.result)
    assert records[0].with_suffix('.stderr').read_text() == ''
