"""Renewal changes time authority, not paid evidence or accounting bounds."""

import time
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest
import session_program as program

from humanvoice.artifacts import digest, read_json, write_json
from tools.ensemble_closure_contract import AllocationLedger

r = program.renewal


@pytest.fixture
def renewal_case(tmp_path, monkeypatch):
    state, output = tmp_path / 'state', tmp_path / 'stage'
    state.mkdir()
    output.mkdir()
    old = time.time() - 3600
    admission = {'deadline': old, 'binding': {'frozen': True}}
    write_json(state / 'admission.json', admission)
    value = {**r.RECORD, 'authorized_at': time.time(), 'prior_deadline': old, 'stage': str(output),
             'admission_sha256': digest((state / 'admission.json').read_bytes())}
    value['deadline'] = value['authorized_at'] + 168 * 3600
    path = tmp_path / 'renewal.json'
    write_json(path, value)
    monkeypatch.setattr(r, 'PATH', path)
    monkeypatch.setattr(r, 'RECORD', value)
    monkeypatch.setattr(r, 'RECORD_HASH', digest(path.read_bytes()))
    monkeypatch.setattr(r.live, 'STATE', state)
    monkeypatch.setattr(r.live, 'OUTPUT', output)
    return output, old, value, state


def test_renewal_preserves_original_admission(renewal_case):
    output, old, value, state = renewal_case
    before = (state / 'admission.json').read_bytes()
    assert r.deadline_for(output, old) == value['deadline']
    assert (state / 'admission.json').read_bytes() == before


@pytest.mark.parametrize('fault', ['changed_record', 'wrong_stage', 'wrong_prior', 'changed_admission', 'hours',
                                  'calls', 'workers', 'provider', 'attempt', 'backoff', 'infinite'])
def test_renewal_rejects_other_changes(renewal_case, monkeypatch, fault):
    output, old, value, state = renewal_case
    if fault == 'changed_record':
        write_json(r.PATH, {**value, 'authorization': 'different'})
    elif fault == 'wrong_stage':
        output = output / 'foreign'
    elif fault == 'wrong_prior':
        old -= 1
    elif fault == 'changed_admission':
        write_json(state / 'admission.json', {'deadline': old, 'binding': 'changed'})
    else:
        field, changed = {'hours': ('hours', 169), 'calls': ('additional_calls', 1), 'workers': ('workers', 17),
                          'provider': ('provider_seconds', 901), 'attempt': ('attempt_seconds', 1051),
                          'backoff': ('network_backoff_seconds', 1), 'infinite': ('deadline', float('inf'))}[fault]
        altered = {**value, field: changed}
        write_json(r.PATH, altered)
        monkeypatch.setattr(r, 'RECORD', altered)
        monkeypatch.setattr(r, 'RECORD_HASH', digest(r.PATH.read_bytes()))
    with pytest.raises(ValueError):
        r.deadline_for(output, old)


def test_exact_native_substitutions_refuse_source_drift():
    with pytest.raises(ValueError, match='one native'):
        r.adapt(program.live.guard, [('not a native expression', 'False')])
    assert len(r.changes()) == 6
    assert all(len(row['replacements']) == 1 for row in r.changes().values())


def test_guard_keeps_authority_stop_qualification_and_expiry(renewal_case, monkeypatch):
    output, old, value, state = renewal_case
    admission = read_json(state / 'admission.json')
    authority = {'deadline': old}
    admission.update(inventory_authority=digest(authority), qualification_tree={'frozen': True},
                     binding={'qualification': {}, 'profile': {}})
    write_json(state / 'admission.json', admission)
    value['admission_sha256'] = digest((state / 'admission.json').read_bytes())
    write_json(r.PATH, value)
    monkeypatch.setattr(r, 'RECORD_HASH', digest(r.PATH.read_bytes()))
    monkeypatch.setattr(program.live, 'original_authority', lambda: authority)
    checked = []
    monkeypatch.setattr(program.live, 'bound_sources', lambda binding: checked.append('source'))
    monkeypatch.setattr(program.context.demand_probe, 'qualification_bytes', lambda *a: checked.append('qualification'))
    monkeypatch.setattr(program.context.qualification_bridge, 'tree', lambda *a: {'frozen': True})
    monkeypatch.setattr(program.live.os, 'statvfs', lambda p: SimpleNamespace(f_flag=program.live.os.ST_RDONLY))
    guard = r.ADAPTERS[0][2]
    guard()
    assert checked == ['source', 'qualification']
    (output / 'STOP').touch()
    with pytest.raises(ValueError, match='stop|deadline'):
        guard()
    (output / 'STOP').unlink()
    authority['foreign'] = True
    with pytest.raises(ValueError, match='authority'):
        guard()
    authority.pop('foreign')
    monkeypatch.setattr(program.live.time, 'time', lambda: value['deadline'] + 1)
    with pytest.raises(ValueError, match='deadline'):
        guard()


def test_scope_restores_on_error():
    before = [(owner, name, getattr(owner, name)) for owner, name, _ in r.ADAPTERS]
    original_clock = program.base.phase_deadlines.scope
    with pytest.raises(RuntimeError, match='fixture'), program.previous.offline_scope(), r.scope():
        assert program.base.run is r.ADAPTERS[-1][2]
        raise RuntimeError('fixture')
    assert all(getattr(owner, name) is original for owner, name, original in before)
    assert program.base.phase_deadlines.scope is original_clock


def test_clock_uses_new_deadline_without_changing_unit_or_repair_limits(renewal_case, monkeypatch):
    _, old, value, _ = renewal_case
    seen = []
    @contextmanager
    def clock(deadline, repairs):
        seen.append((deadline, repairs))
        yield
    monkeypatch.setattr(program.base.phase_deadlines, 'scope', clock)
    with r.scope(), program.base.phase_deadlines.scope(old, 2):
        pass
    assert seen == [(value['deadline'], 2)]


def test_spawned_worker_enters_renewal_scope(monkeypatch):
    calls = []
    @contextmanager
    def scope(**kwargs):
        calls.append('enter')
        yield
        calls.append('exit')
    monkeypatch.setattr(program, 'runtime_scope', scope)
    monkeypatch.setattr(program.NATIVE_WORKER, '__call__', lambda *a: calls.append('call') or 'retained')
    worker = program.Worker('output', {}, None, None, None)
    assert worker({}, None) == 'retained'
    assert calls == ['enter', 'call', 'exit']


def test_next_batch_uses_new_deadline_and_rejects_changed_limits(renewal_case, monkeypatch):
    output, old, value, _ = renewal_case
    db = output / 'wave-new' / 'batch.sqlite'
    store = program.base.batch_store
    policy = store.Policy(value['deadline'], 42, 42 * 544000, 544000)
    binding = {'frozen': True}
    store.create(db, [{'fixture': 'missing repair'}], policy, binding=binding)
    data = {'batches': {}, 'attempts': []}
    saves = []
    stage = SimpleNamespace(output=output, value={'binding': binding, 'deadline': old},
                            check=lambda **k: None, _read=lambda: deepcopy(data), _save=saves.append)
    monkeypatch.setattr(program.context.native_parallel, 'request_for', lambda *a: None)
    attach = r.ADAPTERS[4][2]
    attach(stage, db)
    assert len(saves) == 1 and str(db.resolve()) in saves[0]['batches']
    with store.Store(db) as opened:
        original = opened.manifest
        monkeypatch.setattr(opened, 'manifest', lambda: {**original(), 'policy': {**original()['policy'], 'workers': 17}})
        monkeypatch.setattr(store, 'Store', lambda *a: opened)
        with pytest.raises(ValueError, match='bounds'):
            attach(stage, db)


def test_offline_replay_namespace_has_no_account_or_network_write():
    command = program.namespace('rehearse-child')
    assert '--unshare-net' in command and '--ro-bind' in command
    writable = [command[i + 1] for i, item in enumerate(command[:-1]) if item == '--bind']
    assert writable == [str(program.HERE), str(program.context.MANUSCRIPT)]
    assert '--tmpfs' in command


def test_service_uses_fixed_user_entry_with_sandbox():
    unit = (program.HERE / program.UNIT).read_text()
    assert 'ExecStart=' + program.base.PYTHON + ' -B ' + str(program.HERE / 'session_program.py') + ' run' in unit
    assert 'NoNewPrivileges=yes' in unit and 'sudo' not in unit


def test_native_reservation_resumes_without_changing_manifest_or_spending(renewal_case, monkeypatch):
    output, old, value, state = renewal_case
    source = state / 'snapshot'
    source.mkdir()
    write_json(source / 'manifest.json', {'brief': {'record_type': 'HumanizationBrief'}})
    profile = {'model': {'version_string': 'gpt-6-astra'},
               'sampling': {'temperature': 0.0, 'reasoning_effort': 'xhigh'},
               'budget': {}, 'runtime': {'type': 'codex-cli', 'codex': {'reservation_per_session': 544000}}}
    binding = {'source_hash': digest('source'), 'profile': profile, 'qualification': {}}
    native_binding = {'source': binding['source_hash'], 'implementation': digest('implementation'),
                      'manifest': digest('manifest')}
    plan = {'version': 'automatic-manuscript-stage-v1', 'stage': 'humanize', 'technical_retries': 0,
            'snapshot': str(source), 'profile': profile, 'bindings': native_binding, 'prior_reservation_ceiling': 0,
            'purposes': sorted(r.native.REQUEST_SCHEMAS),
            'calls': [{'key': f'humanize:{i:04d}', 'input_hash': digest({'binding': native_binding, 'slot': i})}
                      for i in range(177)]}
    plan['plan_identity'] = digest(plan)
    write_json(output / 'plan.json', plan)
    grant, account = state / 'grant.json', state / 'account.json'
    write_json(grant, {'identity': digest('fixture-grant')})
    write_json(account, {'plans': [], 'events': []})

    class Native(r.native.Native):
        ledger = AllocationLedger

        @staticmethod
        def lineage_for(plan):
            return state / 'lineage.json'

        @staticmethod
        def preflight(plan):
            assert plan['stage'] == 'humanize'

        @staticmethod
        @contextmanager
        def grant_stage(grant, output):
            row = {'output': str(output), 'plan_identity': plan['plan_identity'],
                   'grant_identity': read_json(grant)['identity'], 'maximum_calls': 177}
            path = grant.with_suffix('.stages.json')
            if path.exists():
                assert read_json(path) == {'stages': [row]}
            else:
                write_json(path, {'stages': [row]})
            yield

        @staticmethod
        def claim(plan, output, account):
            entry = {'output': str(output), 'plan_identity': plan['plan_identity'], 'calls': 177,
                     'reserved_tokens': 177 * 544000, 'prior_reservation_ceiling': 0}
            receipt = {'account': str(account), 'entry': entry, 'entry_hash': digest(entry),
                       'unknown_tokens_released': False}
            path = output / 'account-reservation.json'
            if path.exists():
                assert read_json(path) == receipt
            else:
                write_json(account, {'plans': [entry], 'events': []})
                write_json(path, receipt)
            AllocationLedger(output / 'allocation-ledger.json', plan)
            return receipt

    params = {'grant': grant, 'account': account, 'binding': binding, 'deadline': old,
              'verify_admission': lambda p: None, 'native': Native()}
    real_time = time.time
    with monkeypatch.context() as before:
        before.setattr(time, 'time', lambda: old - 60)
        with r.native.reservation(output, **params):
            pass
    retained = {str(path): digest(path.read_bytes()) for path in output.glob('*.json')}
    retained[str(account)] = digest(account.read_bytes())
    with pytest.raises(r.native.Blocked, match='expired'), r.native.reservation(output, **params):
        pass
    with r.scope(), r.native.reservation(output, **params) as stage:
        stage.check(starting=True)
        (output / 'allocation-seal.json').touch()
        with pytest.raises(r.native.Blocked, match='terminal seal'):
            stage.check(starting=True)
        (output / 'allocation-seal.json').unlink()
        (output / 'STOP').touch()
        with pytest.raises(r.native.Blocked, match='STOP'):
            stage.check(starting=True)
        (output / 'STOP').unlink()
        with monkeypatch.context() as expired:
            expired.setattr(time, 'time', lambda: value['deadline'] + 1)
            with pytest.raises(r.native.Blocked, match='deadline'):
                stage.check(starting=True)
    assert time.time is real_time
    assert retained == {path: digest(program.Path(path).read_bytes()) for path in retained}
