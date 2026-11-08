"""A successful old process alone cannot activate changed or unfinished evidence."""

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location('campaign_continuation', HERE / 'continue.py')
continuation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(continuation)

import pytest

from humanvoice.artifacts import write_json


@pytest.fixture
def completed(tmp_path, monkeypatch):
    evidence = {'profile_hash': 'current', 'status': 'QUALIFICATION_VERIFIED'}
    state = {'status': 'CURRENT_CLIENT_QUALIFICATION_VERIFIED',
        'progress': {'completed': 212, 'allocated': 212, 'unresolved': 0, 'terminal': 'pass'},
        'cleanup': {'complete': True}, 'descendant_cleanup': {'descendants_quiescent': True},
        'evidence': evidence}
    monkeypatch.setattr(continuation, 'QUALIFICATION', tmp_path)
    monkeypatch.setattr(continuation.execution.migration_policy, 'validate_fresh_evidence', lambda *args: True)
    monkeypatch.setattr(continuation.entry.migration_runtime.transition, 'protocol_evidence', lambda *args: True)
    return state, evidence, tmp_path


@pytest.mark.parametrize('defect', ['none', 'failed', 'missing-call', 'unresolved', 'cleanup', 'children', 'evidence'])
def test_activation_requires_exact_completed_cleanup_and_evidence(completed, defect):
    state, evidence, root = completed
    state = deepcopy(state)
    if defect == 'failed': state['status'] = 'QUALIFICATION_BLOCKED'
    elif defect == 'missing-call': state['progress']['completed'] = 211
    elif defect == 'unresolved': state['progress']['unresolved'] = 1
    elif defect == 'cleanup': state['cleanup']['complete'] = False
    elif defect == 'children': state['descendant_cleanup']['descendants_quiescent'] = False
    elif defect == 'evidence': state['evidence']['profile_hash'] = 'another-client'
    write_json(root / 'supervisor-status.json', state)
    candidate = {'identity': 'candidate', 'profiles': [{}], 'original_routing_index': 0}
    if defect != 'none':
        with pytest.raises(ValueError, match='completed and cleaned-up'):
            continuation.activation_record(candidate, evidence, {}, {})
    else:
        value = continuation.activation_record(candidate, evidence, {}, {})
        assert value['status'] == 'QUALIFIED_PENDING_HOST_ADMISSION'
        assert value['production_admitted'] is False


def test_changed_authority_or_source_and_expiry_block_offline_continuation(tmp_path, monkeypatch):
    monkeypatch.setattr(continuation, 'OUTPUT', tmp_path)
    monkeypatch.setattr(continuation, 'MANIFEST', tmp_path / 'manifest.json')
    source = tmp_path / 'source.py'
    source.write_text('original')
    value = {'immutable': {str(source): continuation.digest(source.read_bytes())},
        'authority': {'account': 'original'}, 'bindings': {'original': True}}
    write_json(continuation.MANIFEST, value)
    monkeypatch.setattr(continuation.time, 'time', lambda: continuation.WINDOW_END - 10)
    monkeypatch.setattr(continuation.monitored, 'authority', lambda: {'account': 'original'})
    assert continuation.stable() == value['bindings']
    source.write_text('changed')
    with pytest.raises(ValueError, match='source or input changed'):
        continuation.stable()
    source.write_text('original')
    monkeypatch.setattr(continuation.monitored, 'authority', lambda: {'account': 'changed'})
    with pytest.raises(ValueError, match='spending or production cursor'):
        continuation.stable()
    monkeypatch.setattr(continuation.time, 'time', lambda: continuation.WINDOW_END)
    with pytest.raises(ValueError, match='expired'):
        continuation.stable()
