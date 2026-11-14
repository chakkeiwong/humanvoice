"""Regression coverage for real worker exit, same-batch retry and retained charges."""
import multiprocessing
import os
import signal
import time
from pathlib import Path

import capture_recovery as capture
import interrupted_batch as interruption
import pytest
from test_gateway import execute, stage_case

from humanvoice.artifacts import digest, read_json, write_json

pytest_plugins = ['test_gateway', 'test_durable']
durable = capture.previous.durable
gateway, native = capture.gateway, capture.native


def dead_execute(fixture, stage, binding, deadline, label, expected, messages, interrupt=False):
    if interrupt:
        from batch_scheduler import _expired
        signal.signal(signal.SIGTERM, _expired)
    try:
        value = execute(fixture, stage, binding, deadline, label, expected=expected)
        messages.put(('ok', value))
    except BaseException as error:
        messages.put(('error', type(error).__name__ + ': ' + str(error)))
        raise


def wait_for_capture(stage, timeout=30):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        rows = stage._read()['attempts']
        if len(rows) > 1 and rows[-1].get('capture_owner'):
            return rows[-1]
        time.sleep(.02)
    pytest.fail('Fixture worker did not start its capture')


def joined(process, messages):
    process.join(30)
    if process.is_alive():
        process.kill()
        process.join()
        pytest.fail('Fixture worker exceeded its bound')
    assert process.exitcode == 0
    status, value = messages.get(timeout=2)
    assert status == 'ok', value
    process.close()
    return value


def test_actual_successful_worker_exit_and_marker_integrity(fixture, synthetic):
    with stage_case(fixture) as (stage, binding, deadline):
        execute(fixture, stage, binding, deadline, 'old')
        with durable.scope(), durable.rebind.scope(), gateway.scope():
            ctx = multiprocessing.get_context('fork')
            messages = ctx.Queue()
            process = ctx.Process(target=dead_execute, args=(fixture, stage, binding, deadline, 'https', 'success', messages))
            process.start()
            _demand, response, database = joined(process, messages)
            row = stage._read()['attempts'][-1]
            directory = Path(row['runtime_directory'])
            before = native.evidence_tree(directory)
            # This is the actual missing lifecycle transition, not just receipt replay.
            with pytest.raises(native.Blocked, match='Captured launch evidence'):
                capture.ORIGINAL(stage, database, [])
            with capture.scope():
                stage.recover_workers(database, [])
                # A still-incomplete orphan has no record yet; ownership validation
                # is grounded in launch-time evidence and must still be possible.
                record_path = directory / 'record.json'
                raw = record_path.read_bytes()
                record_path.unlink()
                try:
                    stage.recover_workers(database, [])
                finally:
                    record_path.write_bytes(raw)
                mutations = [
                    ('gateway-transition.json', 'slot', 0),
                    ('gateway-transition.json', 'task', digest('foreign')),
                    ('gateway-transition.json', 'endpoint', 'https://foreign.invalid/v1'),
                    ('session-rebind.json', 'active_binding_hash', digest('foreign')),
                    ('durable-settings.json', 'settings_sha256', digest('foreign')),
                    ('inputs/api-request.json', 'source_hash', digest('foreign')),
                    ('inputs/api-request.json', 'implementation', digest('foreign')),
                    ('qualification-capture.json', 'argv_hash', digest('foreign')),
                ]
                for name, key, value in mutations:
                    path = directory / name
                    original = path.read_bytes()
                    changed = read_json(path)
                    changed[key] = value
                    write_json(path, changed)
                    try:
                        with pytest.raises((ValueError, native.Blocked)):
                            stage.recover_workers(database, [])
                    finally:
                        path.write_bytes(original)
                # A live owner still blocks; the adapter changes no ownership checks.
                prior = native.process_identity
                native.process_identity = lambda pid: row['worker_owner'] if pid == row['worker_owner']['pid'] else prior(pid)
                try:
                    with pytest.raises(native.Busy, match='Living'):
                        stage.recover_workers(database, [])
                finally:
                    native.process_identity = prior
            assert native.evidence_tree(directory) == before
            assert len(stage._read()['attempts']) == 2
            assert stage.ledger.record['calls'][1]['usage'] == response.input_tokens + response.output_tokens


def test_interrupted_worker_retry_uses_same_batch_counters_and_actual_native_receipts(fixture, synthetic, monkeypatch):
    from batch_scheduler import Context
    from batch_store import Store
    with stage_case(fixture) as (stage, binding, deadline):
        execute(fixture, stage, binding, deadline, 'old')
        with durable.scope(), durable.rebind.scope(), gateway.scope(), capture.scope():
            failed = gateway.live.Stage(fixture.output, binding=binding, native=stage.native)
            config = read_json(fixture.codex.settings)
            write_json(fixture.codex.settings, {**config, 'timeout': True})
            ctx = multiprocessing.get_context('fork')
            messages = ctx.Queue()
            process = ctx.Process(target=dead_execute,
                args=(fixture, failed, binding, deadline, 'interrupted', 'blocked', messages, True))
            process.start()
            row = wait_for_capture(failed)
            assert row['slot'] == 1
            os.kill(process.pid, signal.SIGTERM)
            demand, _, database = joined(process, messages)
            write_json(fixture.codex.settings, config)
            data = failed._read()
            row = data['attempts'][-1]
            original_completion = (failed._directory(row) / 'completion.json').read_bytes()
            files = {}
            for root in (Path(row['runtime_directory']), failed._directory(row)):
                files.update({str(root / name): value for name, value in native.evidence_tree(root).items()})
            with Store(database) as store:
                attempts = [dict(r) for r in store.db.execute(
                    'SELECT id,task,token,state,charged_tokens FROM attempts ORDER BY id')]
            value = {'version': interruption.VERSION, 'cause': 'Blocked: Captured launch evidence changed',
                'database': str(database), 'rows': [row], 'attempts': data['attempts'],
                'allocations': failed.ledger.record['calls'], 'files': files,
                'scheduler_attempts': attempts, 'known_tasks': [], 'interrupted_tasks': [row['task']],
                'charges_released': 0, 'counters_reset': 0}
            path = fixture.output / 'incident.json'
            write_json(path, value)
            monkeypatch.setattr(interruption, 'PATH', path)
            interruption.eligible(failed, database)
            with Store(database) as store:
                before = [dict(r) for r in store.db.execute('SELECT * FROM attempts')]
                first = interruption.reopen(store, value)
                assert interruption.reopen(store, value) == first
                assert [dict(r) for r in store.db.execute('SELECT * FROM attempts')] == before
                attempt = store.reserve()
                assert attempt['id'] == 2
                _, _, until = store.begin(attempt['id'], attempt['token'], os.getpid())
                context = Context(str(database), attempt['id'], attempt['token'], attempt['task'], until, False)
                outcome = failed.execute(demand, context, before_start=lambda d,c: c.check(), classify=lambda d,r:'success')
                assert outcome.kind == 'success', outcome.error
                store.finish(attempt['id'], attempt['token'], outcome)
                assert store.report()['complete']
                assert store.report()['charged_calls'] == 2
                assert store.report()['charged_tokens'] == 2 * native.RESERVATION
                assert dict(store.db.execute('SELECT * FROM attempts WHERE id=1').fetchone()) == before[0]
                assert store.reserve() is None
            assert (failed._directory(row) / 'completion.json').read_bytes() == original_completion
            assert len(failed._read()['attempts']) == 3
            assert failed.ledger.record['calls'][1]['usage'] is None
            assert failed.ledger.record['calls'][2]['status'] == 'complete'


@pytest.mark.parametrize('change', ['known', 'negative', 'text', 'envelope', 'usage', 'evidence', 'alive', 'size'])
def test_unrelated_or_known_failures_are_never_retryable(change):
    completion = {'kind':'blocked', 'failure_class':'capture_limit_or_local_failure',
        'error':interruption.MESSAGE, 'response':None, 'usage':None, 'observed_usage':None,
        'journal':{'response_text':''}}
    record={'termination':'error', 'input_tokens':None, 'output_tokens':None}
    response={'text':''}
    process={'process_started':True,'status':'error','returncode':-9,'limit_reason':'local_exception',
             'group_quiescent':True,'remaining_group_members':[]}
    envelope=b''
    assert interruption.interrupted(completion,record,response,process,envelope)
    if change in ('known','negative'): completion['kind']='success' if change=='known' else 'negative'
    elif change=='text': response['text']='retained answer'
    elif change=='envelope': envelope=b'partial known response'
    elif change=='usage': record['input_tokens']=100
    elif change=='evidence': completion['journal']['evidence_error']='changed'
    elif change=='alive': process['group_quiescent']=False
    else: completion['failure_class']='output_size'
    assert not interruption.interrupted(completion,record,response,process,envelope)


@pytest.mark.parametrize('change', ['known_answer', 'retry_cap', 'live', 'charges', 'circuit'])
def test_reopen_refuses_changed_batch_or_exhausted_original_allowance(tmp_path, change):
    from batch_store import Outcome, Policy, Store, create, identity
    demands=[{'request':{'prompt':'known'}},{'request':{'prompt':'interrupted'}}]
    path=tmp_path/'batch.sqlite'
    create(path,demands,Policy(time.time()+3600,10,5440000,544000),binding={'fixture':True})
    with Store(path) as store:
        for kind in ('negative','blocked'):
            a=store.reserve()
            store.begin(a['id'],a['token'],os.getpid())
            store.finish(a['id'],a['token'],Outcome(kind,b'known negative' if kind=='negative' else None,error='fixture'))
        value={'scheduler_attempts':[dict(r) for r in store.db.execute(
                   'SELECT id,task,token,state,charged_tokens FROM attempts ORDER BY id')],
               'known_tasks':[identity(demands[0])],'interrupted_tasks':[identity(demands[1])]}
        if change=='known_answer':
            store.db.execute("UPDATE tasks SET state='pending' WHERE id=?",(value['known_tasks'][0],))
        elif change=='retry_cap':
            # A real three-attempt history reaches the original cap; no counter reset.
            for _ in range(2):
                store.db.execute("UPDATE tasks SET state='pending' WHERE id=?",(value['interrupted_tasks'][0],))
                a=store.reserve()
                store.begin(a['id'],a['token'],os.getpid())
                store.finish(a['id'],a['token'],Outcome('blocked',error='fixture'))
            value['scheduler_attempts']=[dict(r) for r in store.db.execute(
                'SELECT id,task,token,state,charged_tokens FROM attempts ORDER BY id')]
        elif change=='live': store.db.execute("UPDATE attempts SET state='running' WHERE id=2")
        elif change=='charges': store.db.execute('UPDATE attempts SET charged_tokens=0 WHERE id=2')
        else: store.db.execute("UPDATE circuit SET error='Canary attempts exhausted'")
        with pytest.raises(ValueError):
            interruption.reopen(store,value)
        assert not store.db.execute('SELECT 1 FROM events WHERE kind=?',(interruption.EVENT,)).fetchone()


def test_new_worker_installs_recovery_scopes_and_restores(monkeypatch):
    import pickle

    import recovery_program as program
    monkeypatch.setattr(program.previous, 'scope', lambda **_: __import__('contextlib').nullcontext())
    monkeypatch.setattr(program, 'current_review', dict)
    original = native.Stage.recover_workers
    def checked(worker,*args):
        assert native.Stage.recover_workers is capture.recover_workers
        assert native.Stage.execute is capture.execute
        assert program.base.recovery.Worker is program.Worker
        return 'ok'
    monkeypatch.setattr(program.previous.rebind.gateway.NATIVE_WORKER,'__call__',checked)
    monkeypatch.setattr(program.previous.rebind.gateway.NATIVE_WORKER,'recover',checked)
    worker=pickle.loads(pickle.dumps(object.__new__(program.Worker)))
    assert worker({}, {}) == worker.recover(None,[]) == 'ok'
    assert native.Stage.recover_workers is original
