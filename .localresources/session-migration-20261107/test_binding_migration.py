"""Client migration preserves receipt identity and rejects effective drift."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('binding_migration_tested',
    Path(__file__).with_name('binding_migration.py'))
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.fixture
def profiles():
    from humanvoice.inference_settings import selected_profile

    base = selected_profile()
    base.update(deepcopy(base['runtime_options']['codex']))
    client = base['runtime']['codex']
    previous = {'version': migration.settings.VERSION, 'authorization': migration.settings.AUTHORIZATION,
        'thread_id': 'historical-fixture', 'session_path': '/fixture/historical.jsonl',
        'server': {'pid': 100, 'start_ticks': '90', 'executable': '/fixture/old/codex', 'overrides': []},
        'executable_sha256': 'a' * 64, 'cli_version': client['cli_version'],
        'credentials': {'store': 'file', 'path': '/fixture/auth.json', 'file_sha256': 'b' * 64,
            'environment_sha256': 'b' * 64},
        'settings': {'model': 'gpt-6-astra', 'effort': 'max', 'provider_id': 'fixture-provider',
            'approval_policy': 'on-request', 'approvals_reviewer': 'user',
            'provider': {'name': 'Fixture', 'base_url': 'https://fixture.invalid/v1',
                'wire_api': 'responses', 'requires_openai_auth': True},
            'model_settings': {}, 'transport_features': {}, 'layers': []}}
    base = migration.settings.candidate_profile(base, previous)
    base = migration.stream.candidate_profile(base)
    original = migration.routing.candidate_profile(base)
    previous = migration.routing.binding_for(original)
    current = deepcopy(previous)
    current['server'].update(pid=123, start_ticks='100', executable='/fixture/new/codex')
    current['cli_version'] = 'current-fixture'
    current['executable_sha256'] = 'c' * 64
    current['settings']['layers'] = [{'fixture': 'new-layer-metadata'}]
    return original, previous, current


def test_new_profiles_use_current_client_and_preserve_historical_source(profiles):
    original, previous, current = profiles
    before = deepcopy(original)
    result = migration.candidates(original, current)
    assert original == before
    assert result['previous_binding'] == previous
    assert result['current_binding'] == current
    assert result['production_admitted'] is False
    assert result['historical_qualification_reused'] is False
    assert result['comparison']['client_changed'] is True
    for index, profile in enumerate(result['profiles']):
        assert profile['runtime']['codex']['executable'] == '/fixture/new/codex'
        assert profile['runtime']['codex']['cli_version'] == 'current-fixture'
        assert profile['budget'] == original['budget']
        assert profile['prompt_templates'] == original['prompt_templates']
        assert (profile['model']['version_string'], profile['sampling']['reasoning_effort']) == migration.routing.ORDER[index]
        assert profile['runtime_options']['codex']['runtime'] == profile['runtime']
        assert migration.routing.binding_for(profile) == current
    assert original['runtime']['codex']['executable'] == previous['server']['executable']


@pytest.mark.parametrize('index', [0, 1, 2])
def test_migration_preserves_selected_model_without_resetting_fallback_history(profiles, index):
    original, _previous, current = profiles
    original = migration.routing.candidate_profile(original[migration.routing.FIELD]['base_profile'], index)
    result = migration.candidates(original, current)
    assert result['original_routing_index'] == index
    assert result['selected_profile_hash'] == migration.digest(result['profiles'][index])
    selected = result['profiles'][index]
    assert (selected['model'], selected['sampling']) == (original['model'], original['sampling'])


@pytest.mark.parametrize('field', ['endpoint', 'credential', 'proxy', 'model', 'effort',
    'approval', 'reviewer', 'transport', 'context', 'unknown'])
def test_changed_effective_settings_cannot_use_client_only_migration(profiles, field):
    original, _previous, current = profiles
    if field == 'endpoint': current['settings']['provider']['base_url'] = 'https://other.invalid/v1'
    elif field == 'credential': current['credentials']['file_sha256'] = 'd' * 64
    elif field == 'proxy': current['credentials']['environment_sha256'] = 'd' * 64
    elif field == 'model': current['settings']['model'] = 'another-model'
    elif field == 'effort': current['settings']['effort'] = 'low'
    elif field == 'approval': current['settings']['approval_policy'] = 'never'
    elif field == 'reviewer': current['settings']['approvals_reviewer'] = 'guardian'
    elif field == 'transport': current['settings']['transport_features']['unreviewed_http'] = True
    elif field == 'context': current['settings']['model_settings']['model_context_window'] = 1234
    else: current['new_field'] = 'unreviewed'
    with pytest.raises(ValueError):
        migration.candidates(original, current)


@pytest.mark.parametrize('failure_at', [1, 2])
def test_live_verification_is_required_on_both_sides_of_construction(profiles, monkeypatch, failure_at):
    original, _previous, current = profiles
    seen = []
    def verify(binding):
        seen.append(deepcopy(binding))
        if len(seen) == failure_at:
            raise ValueError('Current session changed or exited')
    monkeypatch.setattr(migration.settings, 'verify', verify)
    with pytest.raises(ValueError, match='changed or exited'):
        migration.checked_candidates(original, current)
    assert seen == [current] * failure_at


def test_native_command_names_actual_client_and_human_approval(profiles, tmp_path):
    original, _previous, current = profiles
    value = migration.candidates(original, current)
    for profile in value['profiles']:
        request = {'profile': profile, 'timeout_seconds': 900}
        arguments = migration.routing.command(request, tmp_path / 'runtime', tmp_path / 'working')
        assert arguments[0] == current['server']['executable']
        assert '--ignore-user-config' in arguments and '--strict-config' in arguments
        assert '--approve-for-me' not in arguments
        assert arguments[arguments.index('--model') + 1] == profile['model']['version_string']
        overrides = [arguments[i + 1] for i, item in enumerate(arguments[:-1]) if item == '-c']
        assert 'approval_policy="on-request"' in overrides
        assert 'approvals_reviewer="user"' in overrides
        assert arguments[arguments.index('--sandbox') + 1] == 'read-only'


@pytest.mark.parametrize('defect', [None, 'existing', 'symlink', 'publication'])
def test_candidate_publication_never_overwrites_prior_or_partial_work(tmp_path, monkeypatch, defect):
    path = tmp_path / 'candidate.json'
    if defect == 'existing': path.write_bytes(b'prior')
    elif defect == 'symlink': path.symlink_to(tmp_path / 'absent')
    elif defect == 'publication':
        monkeypatch.setattr(migration.os, 'link', lambda *a, **kw:
            (_ for _ in ()).throw(OSError('injected crash before commit')))
    if defect:
        with pytest.raises(OSError):
            migration.save_new(path, {'new': 'candidate'})
        if defect == 'existing': assert path.read_bytes() == b'prior'
        if defect == 'symlink': assert path.is_symlink() and not path.exists()
        if defect == 'publication': assert not path.exists()
    else:
        migration.save_new(path, {'new': 'candidate'})
        assert json.loads(path.read_bytes()) == {'new': 'candidate'}
    assert not list(tmp_path.glob('.*.pending-*'))


@pytest.mark.parametrize('thread', [None, 'another-thread', 'current-thread'])
def test_explicit_anchor_requires_current_thread_and_native_capture(monkeypatch, thread):
    anchor = {'thread_id': 'current-thread', 'server': {'pid': 123}}
    seen = []
    monkeypatch.setattr(migration.settings, 'capture', lambda value: seen.append(value) or {'captured': True})
    if thread is None:
        monkeypatch.delenv('CODEX_THREAD_ID', raising=False)
    else:
        monkeypatch.setenv('CODEX_THREAD_ID', thread)
    if thread == anchor['thread_id']:
        assert migration.capture_current(anchor) == {'captured': True}
        assert seen == [anchor]
    else:
        with pytest.raises(ValueError, match='another interactive thread'):
            migration.capture_current(anchor)
        assert seen == []
