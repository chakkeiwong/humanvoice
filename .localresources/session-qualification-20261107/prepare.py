"""Prepare native qualification for review without activating its proposed budget."""

import json
import sys
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MIGRATION = ROOT / '.localresources/session-migration-20261107'
sys.path[:0] = [str(MIGRATION), str(ROOT), str(ROOT / 'src')]

import binding_migration as migration
import budget_proposal

from humanvoice.artifacts import digest, read_json
from tools.inventory_history_adoption import no_inference
from tools.inventory_recovery_v2 import qualification

PROPOSAL = '40b2987ba5f6362f3fa5f4089cdd1ff492debe9ae911c1dc29ce939fb5fe8fa4'
require = migration.require


def prepare():
    value = read_json(MIGRATION / 'budget-proposal.json')
    require(value.get('identity') == PROPOSAL
        and digest({key: item for key, item in value.items() if key != 'identity'}) == PROPOSAL
        and value.get('status') == 'PROPOSED_NOT_ADMITTED'
        and value['extension']['status'] == 'AWAITING_USER_APPROVAL',
        'Qualification preparation lost the exact unapproved capacity proposal')
    require(all(digest(Path(path).read_bytes()) == expected
        for path, expected in value['authority_sha256'].items()),
        'Qualification preparation authority changed since native capacity derivation')
    configuration = read_json(budget_proposal.CONFIGURATION)
    require(digest(budget_proposal.CONFIGURATION.read_bytes()) == value['configuration_sha256'],
        'Qualification preparation changed its retained campaign')
    account = read_json(configuration['execution_authority']['account'])
    expected = value['qualification_prototype']
    profile = expected['profile']
    # Retain the failed nested-sandbox snapshot as evidence. The host preparation
    # uses the native parser's own sandbox and a fresh, fixed destination.
    output = HERE / 'qualification-host'
    # This is a proposed future limit, never an allocation. The real grant is
    # untouched; execution must independently require the authorized extension.
    proposed_authority = {'available': value['budget']['total_required_calls']}
    with no_inference():
        plan = qualification.prepare(output, profile, account, proposed_authority,
            expected[qualification.FIELD]['lineage'], production_sessions=value['budget']['campaign_calls'])
        qualification.validate_plan(plan, profile)
        with qualification.runtime(profile):
            qualification.qualification.validate_execution_inputs(output, plan)
    # The budget prototype uses an empty policy hash before the real snapshot
    # exists. Only that binding and its identity may change during preparation.
    bound_expected = deepcopy(expected)
    bound_expected['bindings']['policy'] = plan['bindings']['policy']
    bound_expected['plan_identity'] = digest({
        key: item for key, item in bound_expected.items() if key != 'plan_identity'})
    require(plan == bound_expected, 'Native prepared qualification differs from the reviewed prototype')
    require(all(digest(Path(path).read_bytes()) == checksum
        for path, checksum in value['authority_sha256'].items()),
        'Offline qualification preparation changed account or grant authority')
    result = {'version': 'humanvoice-current-client-prepared-qualification-v1',
        'status': 'PREPARED_PENDING_BUDGET_AND_EXECUTION_APPROVAL',
        'budget_proposal_identity': PROPOSAL, 'candidate_identity': budget_proposal.CANDIDATE,
        'qualification_plan_identity': plan['plan_identity'], 'output': str(output),
        'plan_sha256': digest((output / 'plan.json').read_bytes()),
        'execution_sha256': digest((output / 'execution.json').read_bytes()),
        'authority_sha256': value['authority_sha256'],
        'model_calls': 0, 'account_writes': 0, 'grant_writes': 0,
        'execution_admitted': False, 'additional_calls_authorized': False}
    result['identity'] = digest(result)
    migration.save_new(HERE / 'prepared.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    require(sys.argv[1:] == ['prepare'], 'Only the fixed no-call qualification preparation is supported')
    prepare()
