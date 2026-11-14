"""Reopen only interrupted tasks in their existing bounded scheduler batch."""
import json
from pathlib import Path

import capture_recovery as capture

from humanvoice.artifacts import digest, read_json
from tools.durable_program_supervisor import identity as process_identity

HERE, previous = capture.bootstrap.HERE, capture.previous
live, native = previous.live, capture.native
recovery, Store = previous.base.recovery, previous.base.batch_store.Store
PATH = HERE / 'incident.json'
VERSION = 'gateway-worker-interruption-retirement-v1'
EVENT = 'verified_gateway_worker_recovery'
MESSAGE = 'KeyboardInterrupt: Cooperative stop before original attempt deadline'


def interrupted(completion, record, response, process, envelope):
    """Only a quiescent, empty local interruption is eligible for another call."""
    return (completion['kind'] == 'blocked'
        and completion.get('failure_class') == 'capture_limit_or_local_failure'
        and completion.get('error') == MESSAGE
        and completion['response'] is None and completion['usage'] is None
        and completion.get('observed_usage') is None
        and not completion['journal'].get('evidence_error')
        and not completion['journal'].get('response_text')
        and record['termination'] == 'error'
        and all(record.get(k) is None for k in ('input_tokens', 'output_tokens'))
        and response.get('text') == '' and envelope == b''
        and process['process_started'] is True and process['status'] == 'error'
        and process['returncode'] == -9 and process['limit_reason'] == 'local_exception'
        and process['group_quiescent'] is True and process['remaining_group_members'] == [])


def incident():
    value = read_json(PATH)
    live.require(value['version'] == VERSION and value['cause'] == 'Blocked: Captured launch evidence changed'
                 and value['charges_released'] == value['counters_reset'] == 0,
                 'Different interruption repair authority')
    data = read_json(live.OUTPUT / 'native-attempts.json')
    calls = read_json(live.OUTPUT / 'allocation-ledger.json')['calls']
    live.require(data['attempts'][:len(value['attempts'])] == value['attempts']
                 and calls[:len(value['allocations'])] == value['allocations'],
                 'Interrupted native attempt/account prefix changed')
    return value


def eligible(stage, database):
    value = incident()
    database = str(Path(database).resolve())
    live.require(database == value['database'], 'Interruption retirement is for another batch')
    data = stage._read()
    rows = [r for r in data['attempts'] if r['id'] in {original['id'] for original in value['rows']}]
    live.require(rows == value['rows'], 'Interrupted batch gained or lost an attempt')
    for path, expected in value['files'].items():
        live.require(digest(Path(path).read_bytes()) == expected, 'Interrupted evidence changed: ' + path)
    stage.recover_workers(database, [])
    interruptions, known = [], []
    for row in rows:
        for owner in (row['worker_owner'], row['capture_owner']['owner']):
            live.require(process_identity(owner['pid']) != owner, 'Interrupted worker/client is still alive')
        directory = stage._directory(row)
        completion = read_json(directory / 'completion.json')
        live.require(row['done'] and digest(completion) == row['completion_hash'],
                     'Interrupted completion changed')
        reference = completion['journal']['runtime_record']
        record, response = stage.native.verify(stage.plan['snapshot'], reference, stage.plan['profile'])
        runtime = Path(row['runtime_directory'])
        if completion['kind'] in {'success', 'negative'}:
            live.require(completion['response'] is not None and record['termination'] == 'complete',
                         'Known answer lost its original response')
            native_response = native.ModelResponse(**completion['response'])
            stage._verify_response(row, native_response)
            known.append(row['task'])
        else:
            live.require(interrupted(completion, record, response, read_json(runtime / 'process.json'),
                                     (runtime / 'response-envelope.json').read_bytes()),
                         'Known response or unrelated local/semantic failure cannot be retried')
            live.require(not (directory / 'received-model.json').exists()
                         and stage.ledger.record['calls'][row['slot']]['usage'] is None,
                         'Interrupted call has a received answer or released charge')
            interruptions.append(row['task'])
    live.require(sorted(interruptions) == sorted(value['interrupted_tasks'])
                 and sorted(known) == sorted(value['known_tasks']), 'Incident outcomes changed')
    return value


def reopen(store, value):
    """Keep the same batch, attempts, charges, successful answers and retry cap."""
    repair_hash = digest(value)
    with store.transaction():
        events = store.db.execute('SELECT detail FROM events WHERE kind=?', (EVENT,)).fetchall()
        if events:
            live.require(len(events) == 1 and json.loads(events[0]['detail'])['incident'] == repair_hash,
                         'Different or duplicate worker recovery transition')
            return json.loads(events[0]['detail'])
        store.guard()
        live.require(not store.running(), 'Cannot repair a live batch')
        report = store.report()
        live.require(report['circuit_error'] is None, 'Network circuit requires its original recovery')
        rows = [dict(r) for r in store.db.execute('SELECT id,task,token,state,charged_tokens FROM attempts ORDER BY id')]
        live.require(rows == value['scheduler_attempts'], 'Incident scheduler attempts/charges changed')
        blocked = sorted(r['id'] for r in report['tasks'] if r['state'] == 'blocked')
        live.require(blocked == sorted(value['interrupted_tasks']), 'Different blocked task set')
        for key in value['known_tasks']:
            live.require(store.task(key)[0]['state'] in {'success', 'negative'}, 'Known answer is not terminal')
        for key in value['interrupted_tasks']:
            live.require(store.db.execute('SELECT COUNT(*) FROM attempts WHERE task=?', (key,)).fetchone()[0]
                         < store.manifest()['policy']['max_attempts'], 'Original retry allowance exhausted')
            store.db.execute("UPDATE tasks SET state='pending',eligible=0,outcome=NULL,error=NULL WHERE id=?", (key,))
        detail = {'incident': repair_hash, 'reopened': value['interrupted_tasks'],
                  'retained_attempts': len(rows), 'retained_tokens': sum(r['charged_tokens'] for r in rows),
                  'charges_released': 0, 'counters_reset': 0}
        store.event(EVENT, detail)
        return detail


def transition():
    value = incident()
    stage = recovery.Stage(live.OUTPUT, binding=read_json(live.STATE / 'admission.json')['binding'])
    database = Path(value['database'])
    with native.locked(database.with_name(database.name + '.supervisor.lock'), wait=False):
        eligible(stage, database)
        with Store(database) as store:
            return reopen(store, value)


def may_retry(stage, row, outcome, context):
    """The original local-failure result stays terminal; only dispatch changes."""
    if outcome.kind != 'blocked':
        return False
    value = incident()
    matched = next((r for r in value['rows'] if r['id'] == row['id']), None)
    if matched is None or row['task'] not in value['interrupted_tasks']:
        return False
    live.require(row == matched and row['database'] == context.database == value['database'],
                 'Interrupted retry must use the same original batch and attempt counter')
    with Store(context.database) as store:
        events = store.db.execute('SELECT detail FROM events WHERE kind=?', (EVENT,)).fetchall()
        live.require(len(events) == 1 and json.loads(events[0]['detail'])['incident'] == digest(value),
                     'Interrupted retry lacks its verified repair transition')
        live.require(store.db.execute('SELECT COUNT(*) FROM attempts WHERE task=?', (row['task'],)).fetchone()[0]
                     <= store.manifest()['policy']['max_attempts'], 'Original retry allowance exceeded')
    # Prefix and exact failed bytes remain immutable after the transition.
    for path, expected in value['files'].items():
        live.require(digest(Path(path).read_bytes()) == expected, 'Interrupted evidence changed')
    return True
