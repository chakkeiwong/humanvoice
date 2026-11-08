"""A missing immutable input is repairable only before any model allocation."""

from copy import deepcopy

import pytest
import repair


@pytest.fixture
def stopped():
    progress = {'allocated': 0, 'completed': 0, 'unresolved': 0,
        'terminal': 'prepared', 'ledger_sha256': None}
    return ({'status': 'QUALIFICATION_BLOCKED', 'launches': 1,
        'cleanup': {'complete': True}, 'descendant_cleanup': {'descendants_quiescent': True},
        'progress': deepcopy(progress)}, {'status': 'QUALIFICATION_BLOCKED', 'error': repair.EXPECTED_ERROR}, progress)


def test_exact_failure_can_resume_without_resetting_original_launch_counter(stopped, monkeypatch):
    state, failure, progress = stopped
    repair.check_unspent(state, failure, progress, alive=lambda _: False)
    monkeypatch.setattr(repair.supervise, 'inspect_progress', lambda _: progress)
    assert repair.disposition(state, lambda _: 'BLOCK', {'prior_status': state, 'prior_failure': failure}) == 'RECONCILE_NATIVE'
    assert state['launches'] == 1 and progress['allocated'] == 0


@pytest.mark.parametrize('defect', ['wrong-error', 'semantics', 'spent', 'unknown', 'settled',
    'ledger', 'cleanup', 'descendants', 'live', 'exhausted', 'boolean'])
def test_restart_never_erases_spending_or_bypasses_ambiguous_ownership(stopped, defect):
    state, failure, progress = stopped
    alive = lambda _: defect == 'live'
    if defect == 'wrong-error': failure['error'] = 'another missing file'
    elif defect == 'semantics': state['status'] = 'QUALIFICATION_NONPASS'
    elif defect == 'spent': progress['allocated'] = 1
    elif defect == 'unknown': progress['unresolved'] = 1
    elif defect == 'settled': progress['terminal'] = 'pass'
    elif defect == 'ledger': progress['ledger_sha256'] = 'a' * 64
    elif defect == 'cleanup': state['cleanup']['complete'] = False
    elif defect == 'descendants': state['descendant_cleanup']['descendants_quiescent'] = False
    elif defect == 'exhausted': state['launches'] = 3
    elif defect == 'boolean': state['launches'] = True
    with pytest.raises(ValueError):
        repair.check_unspent(state, failure, progress, alive=alive)


def test_receipt_substitution_preserves_validation_and_restores_on_failure(tmp_path, monkeypatch):
    receipt = tmp_path / 'receipt.json'
    receipt.write_text('{"historical": true}')
    monkeypatch.setattr(repair.archive, 'RECEIPT_SHA256', repair.digest(receipt.read_bytes()))
    original = repair.archive.RECEIPT
    with pytest.raises(RuntimeError), repair.receipt_scope(receipt):
        assert repair.archive.RECEIPT == receipt
        raise RuntimeError('native failure')
    assert repair.archive.RECEIPT == original
    receipt.write_text('changed')
    with pytest.raises(ValueError, match='exact-byte'), repair.receipt_scope(receipt):
        pytest.fail('accepted drift')


def test_fresh_process_initializer_receives_same_receipt_before_native_validation(tmp_path, monkeypatch):
    receipt = tmp_path / 'receipt.json'
    receipt.write_text('{"historical": true}')
    monkeypatch.setattr(repair.archive, 'RECEIPT_SHA256', repair.digest(receipt.read_bytes()))
    registered, seen = [], []
    original = repair.archive.RECEIPT
    monkeypatch.setattr(repair.atexit, 'register', lambda *args: registered.append(args))
    monkeypatch.setattr(repair, 'NATIVE_INITIALIZE_WORKER', lambda: seen.append(repair.archive.RECEIPT))
    with repair.receipt_scope(receipt):
        initializer = repair.archive.initialize_worker
    assert repair.archive.RECEIPT == original
    initializer()
    assert seen == [receipt]
    callback, *args = registered.pop()
    callback(*args)
    assert repair.archive.RECEIPT == original


def test_reentry_after_first_repair_uses_original_supervisor_rules(stopped):
    state, failure, _progress = stopped
    previous = {**state, 'launches': 2, 'status': 'WORKER_CRASHED'}
    seen = []
    assert repair.disposition(previous, lambda value: seen.append(value) or 'NATIVE',
        {'prior_status': state, 'prior_failure': failure}) == 'NATIVE'
    assert seen == [previous]


def test_offline_mounts_keep_archive_exceptions_after_writable_parent_binds(monkeypatch):
    monkeypatch.setattr(repair, 'read_json', lambda _: {})
    monkeypatch.setattr(repair.namespace, 'writable_roots', lambda _: ['/fixture/output'])
    monkeypatch.setattr(repair.namespace, 'mounts', lambda: [('/fixture/ssd', '/fixture/output/archive')])
    command = repair.preflight_command()
    assert '--unshare-net' in command and '--unshare-user' in command
    assert command.index('/fixture/output') < command.index('/fixture/output/archive')
    assert command[-3:-1] == [str(repair.HERE / 'repair.py'), 'inside-preflight']
