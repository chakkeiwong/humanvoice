"""Prepare an exact call-budget proposal from the derived configuration.

This creates a native qualification prototype and an unapproved extension;
it neither claims spending authority nor executes a provider request.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT), str(ROOT / 'src')]

import binding_migration as migration
import grant_extension
import migration_policy
import qualification_budget

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v2 import qualification

CONFIGURATION = Path('/tmp/hvactualconfig-1i76q_du/configuration.json')
CANDIDATE = 'c3f1d77bc829d820b7870da0183a04cea2f6126d95295de284cf4d52aad7fa2c'
require = migration.require


def prepare():
    configuration_raw = CONFIGURATION.read_bytes()
    cfg = json.loads(configuration_raw)
    candidate = read_json(HERE / 'candidate-v2.json')
    require(candidate['identity'] == CANDIDATE
        and migration.candidates(cfg['initial_profile'], candidate['current_binding']) == candidate,
        'Budget proposal differs from the exact current-client candidate')
    requirements = migration_policy.requirements(cfg['initial_profile'], candidate)
    authority = cfg['execution_authority']
    account_path, grant_path = Path(authority['account']), Path(authority['grant'])
    observed = {path: path.read_bytes() for path in
        (account_path, grant_path, grant_path.with_suffix('.stages.json'), grant_path.with_suffix('.usage.json'))}
    account, grant = json.loads(observed[account_path]), json.loads(observed[grant_path])
    usage = json.loads(observed[grant_path.with_suffix('.usage.json')])
    anchor = read_json(Path(cfg['campaign_root']) / 'generation-00/prepared-authority.json')
    require(digest(account) == anchor['account_hash']
        and usage['identity'] == grant['identity'] == authority['grant_identity']
        and usage['available'] == cfg['policy']['available_calls']
        and account['allowance'] - account['reservation_ceiling'] == cfg['policy']['available_tokens'],
        'Budget proposal authority differs from the completed native derivation')
    profile = candidate['profiles'][requirements['selected_routing_index']]
    lineage = {'version': 'humanvoice-client-migration-qualification-v1',
        'candidate_identity': candidate['identity'], 'configuration_identity': cfg['identity']}
    seed = 'inventory-fallback-' + digest({'profile': profile, 'lineage': lineage})[:24]
    corpus = qualification.qualification.generate_corpus(seed, 1, 'manuscript-controls')
    with qualification.runtime(profile):
        prototype = qualification.qualification_plan(corpus, profile, None, digest({}),
            account['reservation_ceiling'], recovery=True, resumable=True,
            account_allowance=account['allowance'])
    _baseline, epoch, _position = qualification.epoch.baseline_for(account)
    plan = qualification.bind_plan(prototype, epoch['identity'], lineage)
    report = qualification_budget.assess(requirements, plan, cfg['policy'], account, usage)
    amendment = {'version': grant_extension.VERSION, 'status': 'AWAITING_USER_APPROVAL',
        'grant': str(grant_path), 'grant_identity': grant['identity'],
        'original_maximum': grant['maximum_new_calls'],
        'additional_calls': report['additional_calls_required'],
        'total_maximum': grant['maximum_new_calls'] + report['additional_calls_required'],
        'no_replenishment_on_reload': True, 'budget_proposal_identity': report['identity'],
        'candidate_identity': candidate['identity']}
    amendment['identity'] = digest(amendment)
    require(CONFIGURATION.read_bytes() == configuration_raw
        and all(path.read_bytes() == raw for path, raw in observed.items()),
        'Budget proposal inputs changed during construction')
    value = {'status': 'PROPOSED_NOT_ADMITTED', 'budget': report, 'extension': amendment,
        'qualification_prototype': plan, 'requirements': requirements,
        'configuration_sha256': digest(configuration_raw),
        'authority_sha256': {str(path): digest(raw) for path, raw in observed.items()},
        'model_calls': 0, 'account_writes': 0, 'grant_writes': 0, 'production_admitted': False}
    value['identity'] = digest(value)
    migration.save_new(HERE / 'budget-proposal.json', value)
    print(json.dumps({'status': value['status'], 'identity': value['identity'], 'budget': report,
        'additional_calls_not_yet_authorized': report['additional_calls_required']}), flush=True)


if __name__ == '__main__':
    require(sys.argv[1:] == ['prepare'], 'Only the fixed no-call budget proposal is supported')
    prepare()
