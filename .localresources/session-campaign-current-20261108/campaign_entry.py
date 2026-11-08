"""Public current-client entry; each child installs the same reviewed adapters."""

import argparse
import json
import sys
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MIGRATION = ROOT / '.localresources/session-migration-20261107'
sys.path[:0] = [str(HERE), str(MIGRATION), str(ROOT), str(ROOT / 'src')]

import binding_migration
import campaign_context
import grant_extension
import migration_runtime
import preparation_adapter

from humanvoice.artifacts import digest, read_json
from tools import finalization_cache, finalization_configuration
from tools.inventory_recovery_v3 import configuration, public

VERSION = 'humanvoice-current-client-public-adapter-v1'
ACTIVATION = HERE / 'activation.json'
require = binding_migration.require


def activation():
    value = read_json(ACTIVATION)
    require(value.get('version') == VERSION
        and value.get('identity') == digest({key: item for key, item in value.items() if key != 'identity'})
        and value.get('status') == 'QUALIFIED_PENDING_HOST_ADMISSION'
        and value.get('production_admitted') is False,
        'Current-client public entry requires explicit qualified activation')
    references = value.get('inputs')
    require(isinstance(references, dict) and set(references) == {
        'candidate', 'qualification', 'protocol', 'call_authorization'},
        'Current-client activation changed immutable input membership')
    objects = {}
    for key, reference in references.items():
        path = Path(reference['path'])
        require(path.is_absolute() and path.is_relative_to(ROOT) and path.resolve() == path
            and path.is_file() and digest(path.read_bytes()) == reference['sha256'],
            'Current-client activation input changed: ' + key)
        objects[key] = read_json(path)
    candidate, qualification = objects['candidate'], objects['qualification']
    require(candidate['identity'] == value['candidate_identity']
        and candidate['profile_hashes'][candidate['original_routing_index']] == qualification['profile_hash'],
        'Current-client public entry reset its selected model')
    extension = objects['call_authorization']
    grant_extension.validate(extension, read_json(extension['grant']), extension['grant'])
    require(extension.get('candidate_identity') == candidate['identity'],
        'Call extension belongs to another client migration')
    return value, objects


def project(native, active):
    require(native.get('identity') == digest({key: item for key, item in native.items() if key != 'identity'})
        and 'current_client_adapter' not in native,
        'Client command projection requires an intact finalization configuration')
    previous = [configuration.PYTHON, '-I', str(ROOT / 'tools/finalization_public.py')]
    command = [configuration.PYTHON, '-I', str(Path(__file__))]
    value = deepcopy(native)
    for key, action in finalization_configuration.ACTIONS.items():
        require(native.get(key) == previous + [action], 'Client projection encountered an unknown command')
        value[key] = command + [action]
    value['current_client_adapter'] = {'version': VERSION,
        'native_configuration_identity': native['identity'],
        'activation_identity': active['identity'], 'candidate_identity': active['candidate_identity']}
    value.pop('identity')
    return {**value, 'identity': digest(value)}


@contextmanager
def scope():
    active, objects = activation()
    reference = active['inputs']['call_authorization']
    extra = (ACTIVATION, Path(__file__), *(Path(row['path']) for row in active['inputs'].values()))
    with ExitStack() as stack:
        stack.enter_context(campaign_context.scope())
        stack.enter_context(grant_extension.scope(reference['path'], expected_sha256=reference['sha256']))
        stack.enter_context(migration_runtime.scope())
        stack.enter_context(preparation_adapter.source_scope(extra))
        stack.enter_context(finalization_cache.scope())
        yield active, objects


def derive():
    with scope() as (active, objects):
        native = finalization_configuration.derive()
        candidate = objects['candidate']
        require(native['initial_profile'] == candidate['profiles'][candidate['original_routing_index']],
            'Prepared campaign did not adopt the exact qualified current profile')
        transition = read_json(Path(native['campaign_root']) / 'generation-00/transition.json')
        marker = transition[migration_runtime.transition.FIELD]
        require(marker['candidate'] == candidate and marker['protocol'] == objects['protocol']
            and marker['qualification']['qualification'] == objects['qualification'],
            'Prepared campaign lost its qualified current-client transition')
        return project(native, active)


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('configuration', 'status', 'monitor', 'worker',
        'campaign-execute', 'campaign-verify', 'campaign-repair'))
    parser.add_argument('--job')
    args = parser.parse_args(arguments)
    if args.action in {'configuration', 'status'}:
        require(args.job is None, 'Read-only configuration cannot select an execution job')
        print(json.dumps({'status': 'OFFLINE_CONFIGURATION_READY', 'configuration': derive(),
            'model_calls': 0, 'account_writes': 0, 'grant_writes': 0,
            'live_execution_enabled': False, 'dispatch_allowed': False}, sort_keys=True))
        return 0
    # Native public entry retains protected admission, explicit job ownership,
    # controls, budget validation, recovery and failure accounting in every child.
    with scope():
        return public.main(arguments)


if __name__ == '__main__':
    raise SystemExit(main())
