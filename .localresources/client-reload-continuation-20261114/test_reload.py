"""Reload must preserve exact provider settings, native receipts and charges."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
import session_rebind as rebind
from test_gateway import execute, stage_case

from humanvoice.artifacts import digest, read_json, write_json

pytest_plugins = ["test_gateway"]


@pytest.fixture
def rebound(fixture, monkeypatch, tmp_path):
    current = deepcopy(rebind.routing.binding_for(fixture.new))
    current.update(cli_version='new-editor', executable_sha256=digest('new-editor'))
    current['server'].update(pid=98765, start_ticks='6789', executable='/new/editor/codex')
    value = {'version': rebind.VERSION, 'active_binding': current,
             'request_client': fixture.new['runtime']['codex']}
    path = tmp_path / 'session-rebind.json'
    write_json(path, value)
    monkeypatch.setattr(rebind, 'PATH', path)
    monkeypatch.setattr(rebind, 'load', lambda: deepcopy(value))
    monkeypatch.setattr(rebind, 'NATIVE_VERIFY', lambda b: digest(b))
    return value


def test_new_control_client_keeps_exact_qualified_request_client(fixture, rebound):
    rebind.compatible(rebind.routing.binding_for(fixture.new), rebound['active_binding'])
    current = rebind.active_profile(rebound)
    assert current['runtime']['codex']['executable'] == '/new/editor/codex'
    assert fixture.new['runtime']['codex']['executable'] != '/new/editor/codex'
    with stage_case(fixture) as (stage, binding, deadline):
        old_demand, old_response, old_db = execute(fixture, stage, binding, deadline, 'old')
        with rebind.scope(), rebind.transport.scope():
            demand, response, new_db = execute(fixture, stage, binding, deadline, 'rebound')
            directory = fixture.codex.snapshot / Path(response.runtime_record['path']).parent
            command = read_json(directory / 'command.json')['argv']
            assert command[0] == rebound['request_client']['executable']
            assert read_json(directory / 'inputs/api-request.json')['profile'] == fixture.new
            assert read_json(directory / 'session-rebind.json')['active_binding_hash'] == digest(rebound['active_binding'])
            for d, r in ((old_demand, old_response), (demand, response)):
                rebuilt = rebind.transport.native.reconstruct(fixture.codex.snapshot, d, r.runtime_record, profile=fixture.old)
                assert rebuilt.runtime_record == r.runtime_record
            data = stage._read()
            batches = {str(db): rebind.transport.completion.batch_state(db, data['batches'][str(db)], binding)
                       for db in (old_db, new_db)}
            _, bank = rebind.transport.completion.allocation_evidence(stage, data, batches)
            assert set(bank) == {old_demand['key'], demand['key']}
            write_json(fixture.output / 'execution.json', {'status': 'pass', 'required': 177,
                       'attempted': 2, 'plan_identity': stage.plan['plan_identity']})
            assert rebind.transport.USAGE(fixture.output, require_seal=False)['allocated_calls'] == 2
        with rebind.scope(), rebind.transport.scope():
            before = rebind.transport.native.evidence_tree(directory)
            assert stage.reconcile()['allocated_calls'] == 2
            assert rebind.transport.native.evidence_tree(directory) == before
            marker = directory / 'session-rebind.json'
            original = marker.read_bytes()
            for field in ('rebind_sha256', 'active_binding_hash', 'request_client', 'gateway_marker_hash'):
                value = json.loads(original)
                value[field] = 'foreign'
                marker.write_text(json.dumps(value))
                with pytest.raises(ValueError, match='exact active-session'):
                    rebind.transport.native.reconstruct(fixture.codex.snapshot, demand, response.runtime_record, profile=fixture.old)
                marker.write_bytes(original)
            marker.unlink()
            with pytest.raises(FileNotFoundError):
                rebind.transport.native.reconstruct(fixture.codex.snapshot, demand, response.runtime_record, profile=fixture.old)
            marker.write_bytes(original)


def test_failed_capture_keeps_unknown_charge_under_rebound_session(fixture, rebound):
    with stage_case(fixture) as (stage, binding, deadline):
        execute(fixture, stage, binding, deadline, 'old')
        configuration = read_json(fixture.codex.settings)
        configuration['transport_failures'] = [{'purpose': 'source_grounded_rewrite', 'status': 504}]
        write_json(fixture.codex.settings, configuration)
        with rebind.scope(), rebind.transport.scope():
            failed = rebind.state.live.Stage(fixture.output, binding=binding, native=stage.native)
            execute(fixture, failed, binding, deadline, 'new-failure', expected='unknown')
            row = failed._read()['attempts'][1]
            saved = read_json(failed._directory(row) / 'completion.json')
            assert saved['failure_class'] == 'transport_unknown'
            assert 'evidence_error' not in saved['journal']
            assert failed.reconcile()['allocated_calls'] == 2
            assert failed.ledger.record['calls'][1]['usage'] is None


@pytest.mark.parametrize('field', ['model', 'effort', 'url', 'credentials', 'approval', 'thread', 'path',
                                  'overrides', 'layers', 'features', 'provider-retry'])
def test_unrelated_session_drift_is_rejected(fixture, rebound, field):
    current = deepcopy(rebound['active_binding'])
    if field in ('model', 'effort'): current['settings'][field] = 'changed'
    elif field == 'url': current['settings']['provider']['base_url'] = 'https://foreign.invalid/v1'
    elif field == 'credentials': current['credentials'] = {'foreign': True}
    elif field == 'approval': current['settings']['approvals_reviewer'] = 'automatic'
    elif field == 'thread': current['thread_id'] = 'foreign'
    elif field == 'path': current['session_path'] = '/foreign'
    elif field == 'overrides': current['server']['overrides'] = ['foreign=true']
    elif field == 'layers': current['settings']['layers'] = ['foreign']
    elif field == 'features': current['settings']['transport_features'] = {'foreign': True}
    else: current['settings']['provider']['stream_max_retries'] = 999
    with pytest.raises(ValueError, match='Reload changed'):
        rebind.compatible(rebind.routing.binding_for(fixture.new), current)


def test_verification_reads_new_control_process_and_propagates_failure(fixture, rebound, monkeypatch):
    calls = []
    def checked(binding):
        calls.append(binding)
        return digest(binding)
    monkeypatch.setattr(rebind, 'NATIVE_VERIFY', checked)
    for profile in (fixture.old, fixture.new):
        binding = rebind.routing.binding_for(profile)
        assert rebind.verify(binding) == digest(binding)
    assert calls == [rebound['active_binding']] * 2
    def exited(binding):
        raise ValueError('replacement session exited')
    monkeypatch.setattr(rebind, 'NATIVE_VERIFY', exited)
    with pytest.raises(ValueError, match='session exited'):
        rebind.verify(rebind.routing.binding_for(fixture.new))


def test_adoption_uses_actual_control_environment_only(fixture, rebound, monkeypatch):
    profiles = []
    monkeypatch.setattr(rebind, 'NATIVE_ADOPT', lambda p: profiles.append(p))
    rebind.adopt(fixture.old)
    rebind.adopt(fixture.new)
    assert all(rebind.routing.binding_for(p) == rebound['active_binding'] for p in profiles)
    with pytest.raises(ValueError, match='foreign request'):
        rebind.adopt({'foreign': True})


def test_rebind_scope_restores_all_functions_after_exception(fixture, rebound):
    old = (rebind.transport.NATIVE_VERIFY, rebind.base.hv_service_env.adopt,
           rebind.transport.write_marker, rebind.state.recorded_profile)
    with pytest.raises(RuntimeError), rebind.scope(), rebind.transport.scope():
        raise RuntimeError('injected interruption')
    assert old == (rebind.transport.NATIVE_VERIFY, rebind.base.hv_service_env.adopt,
                   rebind.transport.write_marker, rebind.state.recorded_profile)


def test_production_rebind_rejects_changed_pinned_executable(monkeypatch, tmp_path):
    transition = rebind.state.load()
    value = read_json(rebind.PATH)
    changed = tmp_path / 'changed-client'
    changed.write_text('different executable')
    transition = deepcopy(transition)
    value = deepcopy(value)
    transition['profile']['runtime']['codex']['executable'] = str(changed)
    value['request_client']['executable'] = str(changed)
    record = tmp_path / 'rebind.json'
    write_json(record, value)
    monkeypatch.setattr(rebind, 'PATH', record)
    monkeypatch.setattr(rebind.state, 'load', lambda: transition)
    # Keep the independently checked native profile intact for the binding read;
    # this case specifically exercises the file-byte integrity check below it.
    native_binding = rebind.routing.binding_for
    original = read_json(rebind.state.PATH)['profile']
    monkeypatch.setattr(rebind.routing, 'binding_for', lambda p: native_binding(original))
    with pytest.raises(ValueError, match='Pinned qualified request client'):
        rebind.load()


def test_worker_reinstalls_scopes_after_spawn(fixture, rebound, monkeypatch):
    import pickle

    import reload_program as program

    def call(worker, demand, attempt):
        assert rebind.transport.NATIVE_VERIFY is rebind.verify
        assert rebind.state.recorded_profile is rebind.recorded_profile
        assert program.base.recovery.Worker is program.Worker
        return 'scopes-active'

    def recover(worker, database, attempts):
        return call(worker, database, attempts)

    monkeypatch.setattr(program.previous.NATIVE_WORKER, '__call__', call)
    monkeypatch.setattr(program.previous.NATIVE_WORKER, 'recover', recover)
    worker = object.__new__(program.Worker)
    worker = pickle.loads(pickle.dumps(worker))
    assert worker({}, {}) == 'scopes-active'
    assert worker.recover(None, []) == 'scopes-active'
