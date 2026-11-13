"""Real native transport/receipt/accounting across a synthetic gateway change."""
import os
import shutil
import sys
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import gateway_runtime as gateway
import pytest

sys.path.insert(0, str(gateway.state.HERE.parents[1] / 'tests'))
from test_active_session_runtime import binding as fixture_binding
from test_codex_runtime import codex as codex_fixture

from humanvoice.artifacts import (
    digest,
    implementation_hash,
    read_json,
    validate_snapshot,
    write_json,
)
from humanvoice.corpus_rights import install_rights
from humanvoice.model import ModelConfig
from tools.ensemble_closure_contract import AllocationLedger

state, native = gateway.state, gateway.native


@pytest.fixture
def fixture(tmp_path, monkeypatch, request):
    codex = codex_fixture.__wrapped__(tmp_path, monkeypatch, request)
    bind = fixture_binding(codex.profile, model='gpt-6-astra', effort='max')
    bind['settings']['provider']['base_url'] = state.OLD_URL
    bind['settings']['layers'] = ['old-layer']
    base = state.settings.candidate_profile(codex.profile, bind)
    base['budget']['timeout_seconds'] = 900
    base['runtime_options']['codex']['budget'] = deepcopy(base['budget'])
    base = state.stream.candidate_profile(base)
    old = state.routing.candidate_profile(base, 1)
    current = deepcopy(bind)
    current['settings']['provider']['base_url'] = state.NEW_URL
    current['settings']['layers'] = ['new-layer']
    new = state.successor(old, current)
    # Install synthetic consent before writing any runtime, never production rights.
    ref = read_json(codex.snapshot / '.humanvoice/rights/current.json')
    path = codex.snapshot / ref['path']
    rights = read_json(path)
    for item in rights['extensions']['permission_evidence']:
        dest = tmp_path / item['path']
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path.parent / 'evidence' / item['path'], dest)
    rights['extensions']['destinations'] = [state.OLD_URL + '/responses']
    write_json(tmp_path / 'rights.json', rights)
    shutil.rmtree(codex.snapshot / '.humanvoice/rights')
    install_rights(codex.snapshot, tmp_path / 'rights.json')
    write_json(codex.settings, {'response': {'replacement_latex': 'A revised claim.',
                                           'concept_correspondences': [], 'output_spans': []}})
    output = tmp_path / 'stage'
    output.mkdir()
    manifest = validate_snapshot(codex.snapshot)
    value = {'version': 'zlb-gateway-succession-v1', 'stage': str(output),
             'source_hash': manifest['source_hash'], 'old_profile': old, 'profile': new,
             'first_new_slot': 1, 'maximum_slots': 177, 'authorization': 'synthetic active gateway instruction'}
    transition = tmp_path / 'transition.json'
    write_json(transition, value)
    monkeypatch.setattr(state, 'PATH', transition)
    monkeypatch.setattr(state, 'load', lambda: deepcopy(value))
    monkeypatch.setattr(state.live, 'OUTPUT', output)
    monkeypatch.setattr(state.live, 'TRANSMISSION', codex.snapshot)
    monkeypatch.setattr(gateway, 'NATIVE_VERIFY', lambda b: digest(b))
    monkeypatch.setattr(state.settings, 'verify', lambda b: digest(b))
    monkeypatch.setattr(gateway.previous.renewal, 'deadline_for', lambda output, prior: prior)
    return SimpleNamespace(codex=codex, value=value, output=output, old=old, new=new, manifest=manifest)


class FixtureNative(native.Native):
    ledger = AllocationLedger

    @staticmethod
    def lineage_for(plan):
        return Path(plan['snapshot']).parent / 'lineage.json'

    @staticmethod
    def preflight(plan):
        assert plan['stage'] == 'humanize'

    @staticmethod
    @contextmanager
    def grant_stage(grant, output):
        plan = read_json(output / 'plan.json')
        row = {'output': str(output), 'plan_identity': plan['plan_identity'],
               'grant_identity': read_json(grant)['identity'], 'maximum_calls': 177}
        write_json(grant.with_suffix('.stages.json'), {'stages': [row]})
        yield

    @staticmethod
    def claim(plan, output, account):
        entry = {'output': str(output), 'plan_identity': plan['plan_identity'], 'calls': 177,
                 'reserved_tokens': 177 * 544000, 'prior_reservation_ceiling': 0}
        receipt = {'account': str(account), 'entry': entry, 'entry_hash': digest(entry),
                   'unknown_tokens_released': False}
        write_json(account, {'plans': [entry], 'events': []})
        write_json(output / 'account-reservation.json', receipt)
        AllocationLedger(output / 'allocation-ledger.json', plan)
        return receipt


@contextmanager
def stage_case(fixture):
    f = fixture
    binding = {'source_hash': f.manifest['source_hash'], 'profile': f.old, 'qualification': {'fixture': True}}
    bindings = {'source': binding['source_hash'], 'implementation': implementation_hash(), 'manifest': digest(f.manifest)}
    plan = {'version': 'automatic-manuscript-stage-v1', 'stage': 'humanize', 'technical_retries': 0,
            'snapshot': str(f.codex.snapshot), 'profile': f.old, 'bindings': bindings,
            'prior_reservation_ceiling': 0, 'purposes': sorted(native.REQUEST_SCHEMAS),
            'calls': [{'key': f'humanize:{i:04d}', 'input_hash': digest({'binding': bindings, 'slot': i})}
                      for i in range(177)]}
    plan['plan_identity'] = digest(plan)
    write_json(f.output / 'plan.json', plan)
    grant, account = f.output.parent / 'grant.json', f.output.parent / 'account.json'
    write_json(grant, {'identity': digest('synthetic-grant')})
    write_json(account, {'plans': [], 'events': []})
    deadline = time.time() + 3600
    with native.receipt_scope(f.old), native.reservation(f.output, grant=grant, account=account,
            binding=binding, deadline=deadline, verify_admission=lambda p: None, native=FixtureNative()) as stage:
        yield stage, binding, deadline


def execute(fixture, stage, binding, deadline, label, *, expected='success'):
    from batch_scheduler import Context
    from batch_store import Policy, Store, create
    config = asdict(ModelConfig.from_profile())
    request = {'prompt': 'Synthetic source ' + label, 'system_prompt': None, 'schema': None,
               'purpose': 'source_grounded_rewrite', 'max_tokens': None, 'record_type': None,
               'response_schema': 'rewrite-response'}
    demand = {'binding': digest(binding), 'config': config, 'request': request}
    demand['key'] = digest(demand)
    db = fixture.output / (label + '.sqlite')
    create(db, [demand], Policy(deadline, 177, 177*544000, 544000), binding=binding)
    stage.attach_batch(db)
    with Store(db) as store:
        attempt = store.reserve()
        _, _, until = store.begin(attempt['id'], attempt['token'], os.getpid())
        context = Context(str(db), attempt['id'], attempt['token'], attempt['task'], until, False)
        outcome = stage.execute(demand, context, before_start=lambda d, c: c.check(), classify=lambda d, r: 'success')
        assert outcome.kind == expected, outcome.error
        store.finish(attempt['id'], attempt['token'], outcome)
    return demand, native.response_from(outcome) if expected == 'success' else outcome, db


def test_real_native_old_and_new_transport_replay_and_settlement(fixture):
    with stage_case(fixture) as (stage, binding, deadline):
        old_demand, old_response, old_db = execute(fixture, stage, binding, deadline, 'old')
        directory = fixture.codex.snapshot / Path(old_response.runtime_record['path']).parent
        original = native.evidence_tree(directory)
        with gateway.scope():
            demand, response, new_db = execute(fixture, stage, binding, deadline, 'new')
            runtime = fixture.codex.snapshot / Path(response.runtime_record['path']).parent
            request = read_json(runtime / 'inputs/api-request.json')
            record = read_json(runtime / 'record.json')
            command = read_json(runtime / 'command.json')['argv']
            assert request['profile'] == fixture.new
            assert record['api_base_url'] == state.NEW_URL
            assert request['authorization']['destination'] == state.NEW_URL + '/responses'
            assert request['authorization']['gateway_transition']['sha256'] == digest(state.PATH.read_bytes())
            assert any(state.NEW_URL in arg for arg in command) and not any(state.OLD_URL in arg for arg in command)
            assert 'approval_policy="on-request"' in command and 'approvals_reviewer="user"' in command
            for d, r in ((old_demand, old_response), (demand, response)):
                replayed = native.reconstruct(fixture.codex.snapshot, d, r.runtime_record, profile=fixture.old)
                assert asdict(replayed) == asdict(r)
            data = stage._read()
            batches = {str(db): gateway.completion.batch_state(db, data['batches'][str(db)], binding)
                       for db in (old_db, new_db)}
            _, bank = gateway.completion.allocation_evidence(stage, data, batches)
            assert set(bank) == {old_demand['key'], demand['key']}
            write_json(fixture.output / 'execution.json', {'status': 'pass', 'required': 177,
                       'attempted': 2, 'plan_identity': stage.plan['plan_identity']})
            usage = gateway.USAGE(fixture.output, require_seal=False)
            assert usage['allocated_calls'] == 2 and usage['reported_tokens'] == 300
            assert len(stage.ledger.record['calls']) == 2
            # Restart reconciliation consumes existing receipts without another
            # capture or allocation, including after leaving/reentering scopes.
        with gateway.scope():
            before_runtimes = set((fixture.codex.snapshot / '.humanvoice/runtime').iterdir())
            restarted = native.Stage(fixture.output, binding=binding, native=FixtureNative())
            assert restarted.reconcile()['allocated_calls'] == 2
            assert set((fixture.codex.snapshot / '.humanvoice/runtime').iterdir()) == before_runtimes
            marker = runtime / 'gateway-transition.json'
            original_marker = marker.read_bytes()
            for field, invalid in (('slot', 0), ('task', digest('foreign')), ('stage', '/foreign'),
                                   ('endpoint', state.OLD_URL), ('runtime_id', 'foreign')):
                changed = read_json(marker)
                changed[field] = invalid
                write_json(marker, changed)
                try:
                    with pytest.raises(ValueError):
                        native.reconstruct(fixture.codex.snapshot, demand, response.runtime_record, profile=fixture.old)
                finally:
                    marker.write_bytes(original_marker)
            marker.unlink()
            try:
                with pytest.raises(FileNotFoundError):
                    native.reconstruct(fixture.codex.snapshot, demand, response.runtime_record, profile=fixture.old)
            finally:
                marker.write_bytes(original_marker)
            old_request = directory / 'inputs/api-request.json'
            original_request = old_request.read_bytes()
            altered = read_json(old_request)
            altered['profile']['runtime']['endpoint'] = state.NEW_URL
            write_json(old_request, altered)
            try:
                with pytest.raises(ValueError):
                    native.reconstruct(fixture.codex.snapshot, old_demand, old_response.runtime_record, profile=fixture.old)
            finally:
                old_request.write_bytes(original_request)
        assert native.evidence_tree(directory) == original


def test_failed_https_capture_retains_charge_and_restart_evidence(fixture):
    with stage_case(fixture) as (stage, binding, deadline):
        execute(fixture, stage, binding, deadline, 'old')
        settings = read_json(fixture.codex.settings)
        settings['transport_failures'] = [{'purpose': 'source_grounded_rewrite', 'status': 504}]
        write_json(fixture.codex.settings, settings)
        with gateway.scope():
            failed_stage = gateway.live.Stage(fixture.output, binding=binding, native=FixtureNative())
            execute(fixture, failed_stage, binding, deadline, 'new-failure', expected='unknown')
            rows = failed_stage._read()['attempts']
            row = rows[1]
            retained = read_json(failed_stage._directory(row) / 'completion.json')
            assert retained['failure_class'] == 'transport_unknown'
            assert 'evidence_error' not in retained['journal']
            runtime = Path(row['runtime_directory'])
            assert read_json(runtime / 'record.json')['api_base_url'] == state.NEW_URL
            before = native.evidence_tree(runtime)
            result = failed_stage.reconcile()
            assert result['allocated_calls'] == 2
            assert native.evidence_tree(runtime) == before
            write_json(fixture.output / 'execution.json', {'status': 'nonpass', 'required': 177,
                       'attempted': 2, 'plan_identity': stage.plan['plan_identity']})
            usage = gateway.USAGE(fixture.output, require_seal=False)
            assert usage['allocated_calls'] == 2 and usage['unknown_calls'] == 1
            assert failed_stage.ledger.record['calls'][1]['usage'] is None


@pytest.mark.parametrize('field', ['model', 'effort', 'credentials', 'approval', 'client', 'url', 'retry'])
def test_rebinding_rejects_unrelated_session_changes(fixture, field):
    current = deepcopy(state.routing.binding_for(fixture.new))
    if field == 'model': current['settings']['model'] = 'foreign'
    elif field == 'effort': current['settings']['effort'] = 'low'
    elif field == 'credentials': current['credentials'] = {'changed': True}
    elif field == 'approval': current['settings']['approvals_reviewer'] = 'automatic'
    elif field == 'client': current['executable_sha256'] = digest('changed')
    elif field == 'url': current['settings']['provider']['base_url'] += '/elsewhere'
    else: current['settings']['provider']['stream_max_retries'] = 20
    with pytest.raises(ValueError, match='more than'):
        state.successor(fixture.old, current)


def test_current_config_drift_still_blocks_semantic_and_transport_bindings(fixture, monkeypatch):
    def changed(_binding):
        raise ValueError('current session changed')
    monkeypatch.setattr(gateway, 'NATIVE_VERIFY', changed)
    for profile in (fixture.old, fixture.new):
        with pytest.raises(ValueError, match='current session changed'):
            gateway.verify_binding(state.routing.binding_for(profile))


def test_gateway_scope_restores_on_exception(fixture):
    prior = [(owner, name, getattr(owner, name)) for owner, name, _ in gateway.ADAPTERS]
    verify, authorize = state.settings.verify, gateway.codex_runtime._authorize
    with pytest.raises(RuntimeError), gateway.scope():
        raise RuntimeError('test')
    assert all(getattr(owner, name) is before for owner, name, before in prior)
    assert state.settings.verify is verify and gateway.codex_runtime._authorize is authorize


def test_new_route_cannot_reuse_an_old_slot(fixture):
    stage = SimpleNamespace(output=fixture.output, plan={'profile': fixture.old,
                            'bindings': {'source': fixture.manifest['source_hash']}})
    for slot in (0, 177):
        with pytest.raises(ValueError, match='allocation'):
            gateway.live_profile(stage, {'slot': slot})


def test_native_adapters_refuse_source_drift():
    with pytest.raises(ValueError, match='one native'):
        gateway.adapt(native.Native.invoke, [('no such expression', 'True')])
