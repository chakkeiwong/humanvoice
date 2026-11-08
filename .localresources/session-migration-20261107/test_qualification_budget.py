"""Fund qualification and the complete campaign before spending either budget."""

from copy import deepcopy

import migration_policy
import pytest
import qualification_budget as budget
import test_binding_migration

from tools.inventory_recovery_v2 import qualification
from tools.inventory_recovery_v3 import policy

profiles = test_binding_migration.profiles


@pytest.fixture
def capacity(profiles):
    original, _before, current = profiles
    original = migration_policy.migration.routing.candidate_profile(
        original[migration_policy.migration.routing.FIELD]['base_profile'], 1)
    candidate = migration_policy.migration.candidates(original, current)
    requirements = migration_policy.requirements(original, candidate)
    profile = candidate['profiles'][1]
    corpus = qualification.qualification.generate_corpus('native-capacity-fixture', 1, 'manuscript-controls')
    account = {'allowance': 1100000000, 'reservation_ceiling': 577580867}
    with qualification.runtime(profile):
        plan = qualification.qualification_plan(corpus, profile, None, budget.digest({}),
            account['reservation_ceiling'], recovery=True, resumable=True,
            account_allowance=account['allowance'])
    document = policy.proposal(remaining_requests=439, inherited_recovery=17,
        incident_allowance=32, split_allowance=32, qualification_calls=0,
        root_sequences=12, available_calls=576, available_tokens=522419133)
    grant = {'identity': 'retained-grant', 'maximum': 2000, 'used': 1424,
        'remaining': 576, 'reserved_remaining': 0, 'available': 576}
    return requirements, plan, document, account, grant


def test_actual_native_qualification_cannot_consume_the_campaigns_remaining_authority(capacity):
    before = deepcopy(capacity)
    result = budget.assess(*capacity)
    assert result['status'] == 'CAPACITY_SHORTFALL'
    assert result['qualification_calls'] == 276 and result['campaign_calls'] == 535
    assert result['additional_calls_required'] == 235 and result['additional_tokens_required'] == 0
    assert result['required_tokens'] == 441184000
    assert not result['automatic_budget_increase'] and not result['production_admitted']
    assert capacity == before


def test_exact_extension_covers_campaign_and_qualification_without_double_charging(capacity):
    requirements, plan, document, account, grant = capacity
    grant.update(maximum=2235, remaining=811, available=811)
    result = budget.assess(requirements, plan, document, account, grant)
    assert result['status'] == 'CAPACITY_SUFFICIENT'
    assert result['total_required_calls'] == 811
    assert document['qualification_calls'] == 0
    account['reservation_ceiling'] = account['allowance'] - result['required_tokens'] + 1
    result = budget.assess(requirements, plan, document, account, grant)
    assert result['status'] == 'CAPACITY_SHORTFALL' and result['additional_tokens_required'] == 1


@pytest.mark.parametrize('defect', ['boolean', 'arithmetic', 'profile', 'membership', 'limit', 'mode'])
def test_inconsistent_native_authority_or_qualification_plan_is_rejected(capacity, defect):
    requirements, plan, document, account, grant = capacity
    if defect == 'boolean': grant['used'] = False
    elif defect == 'arithmetic': grant['available'] += 1
    elif defect == 'profile': requirements['selected_profile_hash'] = 'a' * 64
    elif defect == 'membership': plan['calls'].pop()
    elif defect == 'limit': requirements['qualification_maximum_sessions'] -= 1
    else: requirements['qualification_mode'] = 'REVALIDATE_RETAINED_QUALIFICATION'
    with pytest.raises(ValueError):
        budget.assess(requirements, plan, document, account, grant)
