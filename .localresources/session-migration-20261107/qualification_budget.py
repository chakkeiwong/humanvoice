"""Quantify migration qualification and campaign capacity without new authority."""

import migration_policy

from humanvoice.automatic_recovery import call_limit
from tools.inventory_recovery_v3.policy import require_capacity

digest, require = migration_policy.digest, migration_policy.require


def assess(requirements, native_qualification_plan, campaign_policy, account, grant):
    document = require_capacity(campaign_policy)
    require(requirements.get('qualification_mode') == 'FRESH_NATIVE_QUALIFICATION_REQUIRED'
        and native_qualification_plan.get('plan_identity') == digest({
            key: value for key, value in native_qualification_plan.items() if key != 'plan_identity'})
        and digest(native_qualification_plan['profile']) == requirements['selected_profile_hash']
        and len(native_qualification_plan['calls']) == requirements['native_logical_cases']
        and call_limit(native_qualification_plan) == requirements['qualification_maximum_sessions'],
        'Migration capacity requires the actual native selected-profile qualification plan')
    for mapping, keys in ((account, ('allowance', 'reservation_ceiling')),
            (grant, ('maximum', 'used', 'remaining', 'reserved_remaining', 'available'))):
        require(all(type(mapping.get(key)) is int and mapping[key] >= 0 for key in keys),
            'Migration capacity requires native nonnegative integer authority')
    require(grant['maximum'] - grant['used'] == grant['remaining']
        and grant['remaining'] - grant['reserved_remaining'] == grant['available']
        and account['reservation_ceiling'] <= account['allowance'],
        'Migration capacity changed native cumulative authority arithmetic')
    qualification_calls = call_limit(native_qualification_plan)
    # Qualification happens before the prospective campaign. The campaign policy
    # continues to reserve any future fallback qualifications it already includes.
    campaign_calls = document['planned_calls']
    total = qualification_calls + campaign_calls
    tokens = total * document['token_reservation_per_call']
    token_headroom = account['allowance'] - account['reservation_ceiling']
    call_shortfall = max(0, total - grant['available'])
    token_shortfall = max(0, tokens - token_headroom)
    value = {'version': 'humanvoice-client-migration-budget-v1',
        'status': 'CAPACITY_SUFFICIENT' if call_shortfall == token_shortfall == 0 else 'CAPACITY_SHORTFALL',
        'requirements_identity': requirements['identity'],
        'qualification_plan_identity': native_qualification_plan['plan_identity'],
        'campaign_policy_identity': document['identity'], 'grant_identity': grant['identity'],
        'account_identity': digest(account), 'qualification_calls': qualification_calls,
        'campaign_calls': campaign_calls, 'total_required_calls': total,
        'available_calls': grant['available'], 'additional_calls_required': call_shortfall,
        'required_tokens': tokens, 'available_tokens': token_headroom,
        'additional_tokens_required': token_shortfall,
        'preserves_recovery_allowance': True, 'automatic_budget_increase': False,
        'model_calls': 0, 'account_writes': 0, 'grant_writes': 0,
        'production_admitted': False}
    return {**value, 'identity': digest(value)}
