"""Client identity changes must not rewrite work or renew recovery authority."""

from copy import deepcopy

import client_transition as adapter
import pytest
import test_binding_migration
import test_migration_policy

profiles = test_binding_migration.profiles


def protocol_for(candidate):
    observation = {'status': 'pass', 'provider_calls': 0, 'real_credentials': False,
        'isolation': {'distinct_from_parent': True, 'interfaces': ['lo'],
            'remote_egress': 'blocked_by_network_namespace'},
        'process': {'status': 'complete', 'group_quiescent': True},
        'events': {'accepted': True},
        'requests': [{'kind': 'responses_post', 'request_binding_valid': True}]}
    binding = candidate['current_binding']
    rows = []
    for model, effort in adapter.migration.routing.ORDER:
        argv = [adapter.protocol.PYTHON, '-I', str(adapter.protocol.PROBE), '--executable',
            binding['server']['executable'], '--model', model, '--effort', effort, '--deadline', '30']
        rows.append({'model': model, 'effort': effort, 'command_sha256': adapter.digest(argv),
            'observation': deepcopy(observation)})
    return adapter.identified({'version': adapter.protocol.VERSION,
        'status': 'CURRENT_CLIENT_PROTOCOL_PASS', 'candidate_identity': candidate['identity'],
        'current_binding_hash': adapter.digest(binding), 'executable_sha256': binding['executable_sha256'],
        'observations': rows, 'sources': {str(path): 'a' * 64 for path in adapter.protocol.SOURCES},
        'model_calls': 0, 'external_calls': 0, 'account_writes': 0, 'grant_writes': 0,
        'production_admitted': False, 'historical_qualification_reused': False})


def upgraded(source, binding):
    candidate = adapter.migration.candidates(source['profile'], binding)
    required = adapter.policy.requirements(source['profile'], candidate)
    evidence = test_migration_policy.fixture_evidence(candidate)
    attestation = adapter.policy.fresh_attestation(source['profile'], candidate, required,
        evidence, lambda *_: deepcopy(evidence))
    value = adapter.construct(source, candidate, required, attestation, protocol_for(candidate))
    return value, evidence


@pytest.fixture
def case(profiles):
    profile, _previous, binding = profiles
    profile = adapter.migration.routing.candidate_profile(
        profile[adapter.migration.routing.FIELD]['base_profile'], 1)
    source = adapter.identified({'version': 'inventory-budget-successor-v1', 'profile': profile,
        'proof': {'prefix': ['retained-receipt'], 'remaining_calls': 470},
        'policy': {'planned_calls': 510}, 'recovery_sessions_used': 17,
        'recovery_history': {'sequences': ['retained-sequence']},
        'diagnostic_handoff': {'sequence_identity': 'unused-retry', 'incident_hash': 'failed-request'},
        'source_gate': {'profile': profile}, 'migration': {'profile_hash': adapter.digest(profile)},
        'fallback_qualification': {'profile_hash': adapter.digest(profile)}})
    value, evidence = upgraded(source, binding)
    return source, value, evidence


def check(case, *, source_reject=False, qualification_reject=False):
    source, value, evidence = case
    calls = []

    def native(item):
        calls.append('source')
        if source_reject or item != source:
            raise ValueError('native source failed')
        return deepcopy(item)

    def qualify(output, profile):
        calls.append('qualification')
        if qualification_reject or output != evidence['output'] or adapter.digest(profile) != evidence['profile_hash']:
            raise ValueError('native qualification failed')
        return deepcopy(evidence)

    result = adapter.verify(value, source_verifier=native, qualification_verifier=qualify)
    return result, calls


def test_verified_projection_keeps_every_historical_field_and_selected_fallback(case):
    source, value, _ = case
    result, calls = check(case)
    assert result == value and calls == ['source', 'qualification']
    assert {key for key in source if source[key] != value[key]} == {
        'profile', 'fallback_qualification', 'identity'}
    assert value[adapter.FIELD]['source_transition'] == source
    assert value['profile'][adapter.migration.routing.FIELD]['index'] == 1
    assert value['source_gate']['profile'] == source['profile']


@pytest.mark.parametrize('field', ['proof', 'policy', 'recovery_sessions_used', 'recovery_history',
    'diagnostic_handoff', 'source_gate', 'migration', 'fallback_qualification', 'profile', 'extra'])
def test_rehash_does_not_authorize_historical_or_budget_changes(case, field):
    source, value, evidence = case
    changed = deepcopy(value)
    changed[field] = 'unreviewed replacement'
    changed = adapter.identified(changed)
    with pytest.raises(ValueError):
        check((source, changed, evidence))


@pytest.mark.parametrize('kind', ['source', 'qualification'])
def test_source_and_semantic_replay_are_required_even_with_valid_hashes(case, kind):
    with pytest.raises(ValueError, match='native .* failed'):
        check(case, source_reject=kind == 'source', qualification_reject=kind == 'qualification')


@pytest.mark.parametrize('kind', ['old-client', 'missing-model', 'order', 'command', 'receipt',
    'source', 'boolean', 'remote', 'qualification-transfer'])
def test_rehashed_protocol_cannot_weaken_isolation_or_model_membership(case, kind):
    source, value, evidence = deepcopy(case)
    marker = value[adapter.FIELD]
    proof = marker['protocol']
    if kind == 'old-client': proof['current_binding_hash'] = adapter.digest(marker['candidate']['previous_binding'])
    elif kind == 'missing-model': proof['observations'].pop()
    elif kind == 'order': proof['observations'].reverse()
    elif kind == 'command': proof['observations'][0]['command_sha256'] = 'b' * 64
    elif kind == 'receipt': proof['observations'][0]['observation']['process']['status'] = 'timeout'
    elif kind == 'source': proof['sources'].pop(next(iter(proof['sources'])))
    elif kind == 'boolean': proof['model_calls'] = False
    elif kind == 'remote': proof['external_calls'] = 1
    else: proof['historical_qualification_reused'] = True
    marker['protocol'] = adapter.identified(proof)
    value[adapter.FIELD] = adapter.identified(marker)
    with pytest.raises(ValueError):
        check((source, adapter.identified(value), evidence))


def test_same_model_equivalence_preserves_fallback_order(case):
    source, value, _ = case
    candidate = value[adapter.FIELD]['candidate']
    for index in (1, 2):
        previous, current = adapter.profile_pair(value, candidate['profile_hashes'][index])
        assert current == candidate['profile_hashes'][index]
        assert previous == adapter.digest(adapter.migration.routing.candidate_profile(
            source['profile'][adapter.migration.routing.FIELD]['base_profile'], index))
    with pytest.raises(ValueError, match='abandoned model'):
        adapter.profile_pair(value, candidate['profile_hashes'][0])
    with pytest.raises(ValueError):
        adapter.profile_pair(value, 'unknown')
