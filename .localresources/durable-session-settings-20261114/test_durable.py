"""Configuration fidelity survives editor exit without weakening receipts."""
import json
import pickle
from copy import deepcopy
from pathlib import Path

import durable_program as program
import durable_settings as durable
import pytest
from test_gateway import execute, stage_case

from humanvoice.artifacts import digest, read_json, write_json

pytest_plugins = ['test_gateway']


def effective_for(binding):
    s = binding['settings']
    config = {'model_provider': s['provider_id'], 'approval_policy': 'on-request',
              'approvals_reviewer': 'user', 'sandbox_mode': 'workspace-write',
              'model_providers': {s['provider_id']: deepcopy(s['provider'])},
              'features': deepcopy(s['transport_features']), **s['model_settings']}
    context = {k: s[k] for k in ('model', 'effort', 'provider_id', 'approval_policy', 'approvals_reviewer')}
    return {'config': config, 'layers': deepcopy(s['layers'])}, context


def test_real_configuration_verification_survives_dead_original_editor():
    # Uses the actual installed config reader, current config, thread context,
    # inherited environment and credential hashes. The supplied binding is the
    # original now-dead editor anchor, whose PID must never be dereferenced.
    expected = durable.rebind.load()['active_binding']
    original = Path('/proc') / str(expected['server']['pid'])
    assert not original.exists() or original.joinpath('stat').read_text().split()[21] != expected['server']['start_ticks']
    assert durable.verify(expected) == digest(expected)


@pytest.mark.parametrize('change', ['model', 'effort', 'url', 'approval', 'reviewer', 'sandbox',
                                   'retry', 'feature', 'layers', 'credential', 'environment', 'store'])
def test_settings_drift_rejected(change):
    expected = durable.load()
    effective, context = effective_for(expected)
    env_hash, auth_hash = (expected['credentials'][k] for k in ('environment_sha256', 'file_sha256'))
    if change in ('model', 'effort'): context[change] = 'foreign'
    elif change == 'url': effective['config']['model_providers'][context['provider_id']]['base_url'] = 'https://foreign.invalid/v1'
    elif change == 'approval': effective['config']['approval_policy'] = 'never'
    elif change == 'reviewer': effective['config']['approvals_reviewer'] = 'automatic'
    elif change == 'sandbox': effective['config']['sandbox_mode'] = 'danger-full-access'
    elif change == 'retry': effective['config']['model_providers'][context['provider_id']]['stream_max_retries'] = 900
    elif change == 'feature': effective['config']['features']['responses_websockets'] = True
    elif change == 'layers': effective['layers'].append({'name': {'type': 'foreign'}, 'version': 'changed'})
    elif change == 'credential': auth_hash = digest('changed')
    elif change == 'environment': env_hash = digest('changed')
    else: effective['config']['cli_auth_credentials_store'] = 'keyring'
    with pytest.raises(ValueError):
        durable.checked_configuration(expected, effective, context,
                                      environment_hash=env_hash, credential_hash=auth_hash)


@pytest.mark.parametrize('field', ['thread_id', 'session_path', 'executable_sha256', 'cli_version'])
def test_only_pid_and_start_ticks_are_excluded(field):
    original = durable.load()
    altered = deepcopy(original)
    altered['server']['pid'], altered['server']['start_ticks'] = 999999999, '0'
    assert durable.stable(altered) == durable.stable(original)
    altered[field] = 'foreign'
    assert durable.stable(altered) != durable.stable(original)
    with pytest.raises(ValueError, match='Unadmitted'):
        durable.verify(altered)


@pytest.fixture
def synthetic(fixture, monkeypatch, tmp_path):
    old = durable.routing.binding_for(fixture.new)
    current = deepcopy(old)
    current['server'].update(pid=999999999, start_ticks='0')
    rebind_value = {'version': durable.rebind.VERSION, 'active_binding': current,
                    'request_client': fixture.new['runtime']['codex']}
    control = tmp_path / 'current-session.json'
    rebind_path = tmp_path / 'session-rebind.json'
    write_json(control, current)
    write_json(rebind_path, rebind_value)
    monkeypatch.setattr(durable, 'PATH', control)
    monkeypatch.setattr(durable.rebind, 'PATH', rebind_path)
    monkeypatch.setattr(durable.rebind, 'load', lambda: deepcopy(rebind_value))
    monkeypatch.setattr(durable, 'load', lambda: deepcopy(current))
    def verified(binding):
        assert durable.stable(binding) == durable.stable(current)
        return digest(binding)
    monkeypatch.setattr(durable, 'verify', verified)
    return current


def test_native_execution_replay_settlement_and_tamper_after_editor_exit(fixture, synthetic):
    gateway = durable.rebind.transport
    with stage_case(fixture) as (stage, binding, deadline):
        old_demand, old_response, old_db = execute(fixture, stage, binding, deadline, 'old')
        with durable.scope(), durable.rebind.scope(), gateway.scope():
            demand, response, db = execute(fixture, stage, binding, deadline, 'durable')
            directory = fixture.codex.snapshot / Path(response.runtime_record['path']).parent
            assert read_json(directory / 'command.json')['argv'][0] == fixture.new['runtime']['codex']['executable']
            record = read_json(directory / 'durable-settings.json')
            assert record['editor_process_lifetime_required'] is False
            for d, r in ((old_demand, old_response), (demand, response)):
                assert gateway.native.reconstruct(fixture.codex.snapshot, d, r.runtime_record, profile=fixture.old).runtime_record == r.runtime_record
            data = stage._read()
            batches = {str(p): gateway.completion.batch_state(p, data['batches'][str(p)], binding) for p in (old_db, db)}
            _, bank = gateway.completion.allocation_evidence(stage, data, batches)
            assert set(bank) == {old_demand['key'], demand['key']}
            write_json(fixture.output / 'execution.json', {'status':'pass', 'required':177,
                'attempted':2, 'plan_identity':stage.plan['plan_identity']})
            assert gateway.USAGE(fixture.output, require_seal=False)['allocated_calls'] == 2
        with durable.scope(), durable.rebind.scope(), gateway.scope():
            before = gateway.native.evidence_tree(directory)
            assert stage.reconcile()['allocated_calls'] == 2
            assert gateway.native.evidence_tree(directory) == before
            path = directory / 'durable-settings.json'
            raw = path.read_bytes()
            altered = json.loads(raw)
            altered['settings_sha256'] = 'foreign'
            write_json(path, altered)
            with pytest.raises(ValueError, match='durable live-settings'):
                gateway.native.reconstruct(fixture.codex.snapshot, demand, response.runtime_record, profile=fixture.old)
            path.unlink()
            with pytest.raises(FileNotFoundError):
                gateway.native.reconstruct(fixture.codex.snapshot, demand, response.runtime_record, profile=fixture.old)
            path.write_bytes(raw)


def test_unknown_charge_preserved_with_durable_verification(fixture, synthetic):
    gateway = durable.rebind.transport
    with stage_case(fixture) as (stage, binding, deadline):
        execute(fixture, stage, binding, deadline, 'old')
        config = read_json(fixture.codex.settings)
        config['transport_failures'] = [{'purpose':'source_grounded_rewrite', 'status':504}]
        write_json(fixture.codex.settings, config)
        with durable.scope(), durable.rebind.scope(), gateway.scope():
            failed = gateway.live.Stage(fixture.output, binding=binding, native=stage.native)
            execute(fixture, failed, binding, deadline, 'failed', expected='unknown')
            assert failed.reconcile()['allocated_calls'] == 2
            row = failed._read()['attempts'][1]
            completion = read_json(failed._directory(row) / 'completion.json')
            assert completion['failure_class'] == 'transport_unknown'
            assert 'evidence_error' not in completion['journal']
            assert failed.ledger.record['calls'][1]['usage'] is None


def test_spawned_worker_and_exception_restore(fixture, synthetic, monkeypatch):
    prior = (durable.rebind.NATIVE_VERIFY, durable.rebind.NATIVE_ADOPT, durable.rebind.write_marker)
    def active(worker, demand, attempt):
        assert durable.rebind.NATIVE_VERIFY is durable.verify
        assert durable.rebind.NATIVE_ADOPT is durable.adopt
        assert durable.rebind.write_marker is durable.write_marker
        assert program.base.recovery.Worker is program.Worker
        return 'verified'
    monkeypatch.setattr(program.previous.previous.NATIVE_WORKER, '__call__', active)
    monkeypatch.setattr(program.previous.previous.NATIVE_WORKER, 'recover', active)
    worker = pickle.loads(pickle.dumps(object.__new__(program.Worker)))
    assert worker({}, {}) == 'verified'
    assert worker.recover(None, []) == 'verified'
    with pytest.raises(RuntimeError), program.scope(reviewed=False):
        raise RuntimeError('interruption')
    assert prior == (durable.rebind.NATIVE_VERIFY, durable.rebind.NATIVE_ADOPT, durable.rebind.write_marker)


def test_service_matches_verified_interactive_client_identification():
    text = (program.HERE / program.UNIT).read_text()
    assert text.count('Environment=CODEX_INTERNAL_ORIGINATOR_OVERRIDE=codex_vscode') == 1
    assert 'NoNewPrivileges=yes' in text
    assert 'EnvironmentFile=' not in text
    record = read_json(program.HERE / 'environment-repair.json')
    assert record['environment_key'] == 'CODEX_INTERNAL_ORIGINATOR_OVERRIDE'
    assert record['environment_value'] == 'codex_vscode'
