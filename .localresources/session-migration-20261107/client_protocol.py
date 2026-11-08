"""Check the installed client against synthetic responses with no remote route.

This is a transport and receipt compatibility check. It never transfers model
qualification or admits manuscript execution.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT), str(ROOT / 'src')]

import binding_migration as migration

from humanvoice.artifacts import digest

# The isolated probe masks /tmp. Its interpreter must live in the base prefix
# mounted by the existing namespace builder, not in the release virtualenv.
PYTHON = '/home/ubuntu/miniforge3/bin/python'
DIAGNOSTICS = HERE / 'protocol-attempts'
PROBE = ROOT / 'tools/probe_response_capture_loopback.py'
VERSION = 'humanvoice-current-client-protocol-v1'
SOURCES = (Path(__file__), HERE / 'binding_migration.py', PROBE,
    ROOT / 'tools/probe_active_client_loopback.py', ROOT / 'tools/response_capture_observation.py',
    ROOT / 'tools/active_session_stream_recovery.py', ROOT / 'src/humanvoice/codex_runtime.py')
require = migration.require


def source_hashes():
    return {str(path): digest(path.read_bytes()) for path in SOURCES}


def candidate():
    value = json.loads((HERE / 'candidate-v2.json').read_bytes())
    require(value.get('version') == migration.VERSION
        and value.get('identity') == digest({k: v for k, v in value.items() if k != 'identity'})
        and value.get('production_admitted') is False
        and value.get('historical_qualification_reused') is False
        and value.get('profile_hashes') == [digest(p) for p in value['profiles']],
        'Current-client candidate identity or admission boundary changed')
    require(len(value['profiles']) == len(migration.routing.ORDER),
        'Current-client candidate changed model membership')
    index = value.get('original_routing_index')
    require(type(index) is int and 0 <= index < len(migration.routing.ORDER)
        and value.get('selected_profile_hash') == value['profile_hashes'][index],
        'Current-client candidate reset the retained model selection')
    for index, profile in enumerate(value['profiles']):
        require(migration.routing.binding_for(profile) == value['current_binding']
            and profile[migration.routing.FIELD]['index'] == index,
            'Current-client candidate differs from ordered native profile construction')
    require(value['comparison'] == migration.compare(value['previous_binding'], value['current_binding']),
        'Current-client candidate changed its effective-setting comparison')
    migration.settings.verify(value['current_binding'])
    return value


def validate_observation(value):
    require(value.get('status') == 'pass' and value.get('provider_calls') == 0
        and type(value.get('provider_calls')) is int and value.get('real_credentials') is False,
        'Synthetic client protocol check failed or changed its isolation claim')
    isolation, process = value.get('isolation', {}), value.get('process', {})
    require(isolation.get('distinct_from_parent') is True and isolation.get('interfaces') == ['lo']
        and isolation.get('remote_egress') == 'blocked_by_network_namespace'
        and process.get('status') == 'complete' and process.get('group_quiescent') is True
        and value.get('events', {}).get('accepted') is True
        and value.get('requests') == [{'kind': 'responses_post', 'request_binding_valid': True}],
        'Synthetic client protocol lost receipt completion, cleanup or exact request membership')
    return value


def inspect(value):
    binding = value['current_binding']
    before = source_hashes()
    executable = binding['server']['executable']
    migration.settings.verify(binding)
    require(digest(Path(executable).read_bytes()) == binding['executable_sha256'],
        'Current-client executable changed before protocol observation')
    DIAGNOSTICS.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='attempt-', dir=DIAGNOSTICS))
    observations = []
    for model, effort in migration.routing.ORDER:
        migration.settings.verify(binding)
        command = [PYTHON, '-I', str(PROBE), '--executable', executable,
            '--model', model, '--effort', effort, '--deadline', '30']
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        prefix = directory / f'{len(observations):02d}'
        prefix.with_suffix('.stdout').write_text(completed.stdout)
        prefix.with_suffix('.stderr').write_text(completed.stderr)
        migration.save_new(prefix.with_suffix('.json'), {'command': command,
            'returncode': completed.returncode, 'stdout_sha256': digest(completed.stdout.encode()),
            'stderr_sha256': digest(completed.stderr.encode())})
        require(completed.returncode == 0,
            'Isolated client protocol process failed: ' + str(completed.returncode)
            + '; diagnostics=' + str(prefix.with_suffix('.json')))
        observed = validate_observation(json.loads(completed.stdout))
        observations.append({'model': model, 'effort': effort, 'command_sha256': digest(command),
            'observation': observed})
    migration.settings.verify(binding)
    require(source_hashes() == before
        and digest(Path(executable).read_bytes()) == binding['executable_sha256'],
        'Current-client protocol inputs changed during observation')
    result = {'version': VERSION, 'status': 'CURRENT_CLIENT_PROTOCOL_PASS',
        'candidate_identity': value['identity'], 'current_binding_hash': digest(binding),
        'executable_sha256': binding['executable_sha256'], 'sources': before,
        'observations': observations, 'model_calls': 0, 'external_calls': 0,
        'account_writes': 0, 'grant_writes': 0, 'production_admitted': False,
        'historical_qualification_reused': False}
    return {**result, 'identity': digest(result)}


def main():
    require(sys.executable == PYTHON and sys.argv[1:] == ['probe'],
        'Only the fixed isolated current-client probe is supported')
    value = candidate()
    result = inspect(value)
    destination = HERE / 'protocol-result.json'
    migration.save_new(destination, result)
    print(json.dumps({k: result[k] for k in ('status', 'identity', 'candidate_identity',
        'model_calls', 'external_calls', 'production_admitted', 'historical_qualification_reused')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
