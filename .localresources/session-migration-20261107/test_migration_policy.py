"""Client upgrades cannot use a canary to erase semantic or recovery history."""

from copy import deepcopy

import migration_policy as policy
import pytest
import test_binding_migration

profiles = test_binding_migration.profiles


@pytest.mark.parametrize('index', [0, 1, 2])
@pytest.mark.parametrize('client_changed', [False, True])
def test_upgrade_checks_only_selected_model_without_resetting_fallback(profiles, index, client_changed):
    original, previous, current = profiles
    original = policy.migration.routing.candidate_profile(
        original[policy.migration.routing.FIELD]['base_profile'], index)
    if not client_changed:
        for key in ('cli_version', 'executable_sha256'):
            current[key] = previous[key]
    candidate = policy.migration.candidates(original, current)
    result = policy.requirements(original, candidate)
    assert result['selected_routing_index'] == index
    assert (result['model'], result['effort']) == policy.migration.routing.ORDER[index]
    assert result['native_logical_cases'] == (212 if client_changed else 0)
    assert result['qualification_maximum_sessions'] == (276 if client_changed else 0)
    assert not any(result[key] for key in ('reset_model_order', 'reset_request_lineage',
        'reset_recovery_usage', 'rewrite_historical_receipts', 'human_intermediate_review',
        'production_admitted', 'canary_is_qualification'))


def fixture_evidence(candidate):
    profile = candidate['profiles'][candidate['original_routing_index']]
    return {'status': 'QUALIFICATION_VERIFIED', 'profile_hash': policy.digest(profile),
        'purposes': policy.PURPOSES, 'settled': True, 'canary_only': False,
        'evaluation_hash': 'a' * 64, 'plan_identity': 'b' * 64, 'output': '/fixture/qualification'}


def test_fresh_native_qualification_is_verified_before_attestation(profiles):
    original, _previous, current = profiles
    candidate = policy.migration.candidates(original, current)
    requirements = policy.requirements(original, candidate)
    evidence = fixture_evidence(candidate)
    calls = []
    def verify(output, profile):
        calls.append((output, profile))
        return deepcopy(evidence)
    result = policy.fresh_attestation(original, candidate, requirements, evidence, verify)
    assert calls == [(evidence['output'], candidate['profiles'][candidate['original_routing_index']])]
    assert result['qualification'] == evidence
    assert result['historical_qualification_reused'] is result['production_admitted'] is False


@pytest.mark.parametrize('defect', ['profile', 'canary', 'unsettled', 'nonpass', 'purposes',
    'missing-plan', 'verifier-reject', 'verifier-mismatch', 'candidate-reset'])
def test_failed_or_stale_qualification_cannot_attest_migration(profiles, defect):
    original, _previous, current = profiles
    candidate = policy.migration.candidates(original, current)
    requirements = policy.requirements(original, candidate)
    evidence = fixture_evidence(candidate)
    if defect == 'profile': evidence['profile_hash'] = policy.digest(original)
    elif defect == 'canary': evidence['canary_only'] = True
    elif defect == 'unsettled': evidence['settled'] = False
    elif defect == 'nonpass': evidence['status'] = 'QUALIFICATION_REJECTED'
    elif defect == 'purposes': evidence['purposes'] = ['concept_extraction']
    elif defect == 'missing-plan': evidence.pop('plan_identity')
    elif defect == 'candidate-reset':
        candidate['original_routing_index'] = 1
        candidate['selected_profile_hash'] = candidate['profile_hashes'][1]
        candidate['identity'] = policy.digest({k: v for k, v in candidate.items() if k != 'identity'})

    def verify(output, profile):
        if defect == 'verifier-reject': raise ValueError('native evaluation failed')
        if defect == 'verifier-mismatch': return {**evidence, 'evaluation_hash': 'c' * 64}
        pytest.fail('Invalid metadata must be rejected before native verification')

    with pytest.raises(ValueError):
        policy.fresh_attestation(original, candidate, requirements, evidence, verify)
