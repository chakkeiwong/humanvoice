"""Construct current-client candidates while preserving historical profiles.

This module grants neither qualification credit nor live execution. Candidate
profiles use the native builders so future receipts name the client actually
invoked. Historical receipts continue to validate against their own profiles.
"""

import json
import os
import sys
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]

from humanvoice.artifacts import digest
from tools import active_session_settings as settings
from tools import active_session_stream_recovery as stream
from tools import model_routing_policy as routing

VERSION = 'humanvoice-current-client-migration-candidate-v2'
PREVIOUS_CANDIDATE = '2e2d5cb59ef971536e68da1fdae47bcf6430317d949a7ea8dc4e377c192ebc56'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stable_settings(binding):
    """Process and layer metadata are not model/gateway/credential settings."""
    value = deepcopy(binding)
    require(set(value) == {'version', 'thread_id', 'session_path', 'server', 'settings',
        'cli_version', 'executable_sha256', 'authorization', 'credentials'},
        'Session migration requires a known complete binding schema')
    for name in ('thread_id', 'session_path', 'server', 'cli_version', 'executable_sha256'):
        value.pop(name)
    value['settings'].pop('layers')
    return value


def compare(previous, current):
    require(previous['version'] == current['version'] == settings.VERSION
        and previous['authorization'] == current['authorization'] == settings.AUTHORIZATION,
        'Session migration lacks the original user authority')
    require(stable_settings(previous) == stable_settings(current),
        'Model, gateway, credentials or effective settings changed; client-only migration is insufficient')
    changed = sorted(key for key in previous if previous[key] != current[key])
    client_changed = any(previous[key] != current[key] for key in ('cli_version', 'executable_sha256'))
    return {'changed_fields': changed, 'client_changed': client_changed,
        'previous_binding_hash': digest(previous), 'current_binding_hash': digest(current),
        'effective_settings_unchanged': True, 'historical_qualification_reused': False,
        'required_checks': ['native-command-configuration', 'new-client-event-receipt-contract',
            'accounted-current-client-canaries', 'explicit-qualification-transfer-or-fresh-qualification',
            'native-prepared-successor-with-inherited-receipts', 'cold-configuration-and-admission']}


def candidates(original, current):
    previous = routing.binding_for(original)
    comparison = compare(previous, current)
    marker = original.get(routing.FIELD)
    require(marker is not None, 'Migration requires the explicitly ordered routing profile')
    base = marker['base_profile']
    # candidate_profile resets active_session rather than altering a historical
    # object. Reapply its native stream extension and each authorized model.
    rebuilt = settings.candidate_profile(base, current)
    rebuilt = stream.candidate_profile(rebuilt)
    profiles = [routing.candidate_profile(rebuilt, index) for index in range(len(routing.ORDER))]
    for index, profile in enumerate(profiles):
        require(routing.binding_for(profile) == current
            and profile['model']['version_string'] == routing.ORDER[index][0]
            and profile['sampling']['reasoning_effort'] == routing.ORDER[index][1],
            'Candidate changed the current client or authorized model ordering')
        with routing.binding_scope():
            stream.validate_profile(profile)
    value = {'version': VERSION, 'status': 'CURRENT_CLIENT_CANDIDATES_ONLY',
        'original_profile_hash': digest(original), 'previous_binding': deepcopy(previous),
        'current_binding': deepcopy(current), 'comparison': comparison, 'profiles': profiles,
        'profile_hashes': [digest(profile) for profile in profiles],
        'original_routing_index': marker['index'],
        'selected_profile_hash': digest(profiles[marker['index']]),
        'model_calls': 0, 'account_writes': 0, 'grant_writes': 0,
        'production_admitted': False, 'historical_qualification_reused': False}
    return {**value, 'identity': digest(value)}


def checked_candidates(original, current):
    before = digest(original)
    settings.verify(current)
    value = candidates(original, current)
    settings.verify(current)
    require(digest(original) == before, 'Historical profile changed during migration construction')
    return value


def save_new(path, value):
    """Commit once; a failed or interrupted proposal never replaces prior evidence."""
    path = Path(path)
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    temporary = path.with_name('.' + path.name + '.pending-' + str(os.getpid()))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream_out:
            stream_out.write(raw)
            stream_out.flush()
            os.fsync(stream_out.fileno())
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink()
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def prepare():
    source = Path('/tmp/hvactualconfig-ifop3bds/configuration.json')
    original = json.loads(source.read_bytes())['initial_profile']
    previous = json.loads((HERE / 'candidate.json').read_bytes())
    require(previous.get('identity') == PREVIOUS_CANDIDATE
        and previous['identity'] == digest({k: v for k, v in previous.items() if k != 'identity'})
        and previous['original_profile_hash'] == digest(original),
        'Retained session candidate or original profile changed')
    current = capture_current(previous['current_binding'])
    value = checked_candidates(original, current)
    destination = HERE / 'candidate-v2.json'
    save_new(destination, value)
    print(json.dumps({'status': value['status'], 'path': str(destination),
        'identity': value['identity'], 'comparison': value['comparison'],
        'models': [list(pair) for pair in routing.ORDER], 'production_admitted': False,
        'model_calls': 0}))
    return 0


def capture_current(anchor):
    # The command sandbox does not always retain the app-server in its parent
    # chain. Use the already captured current-session anchor, after checking the
    # actual thread. Native capture still verifies PID/start ticks/executable,
    # current configuration, credential hashes and the latest session context.
    require(os.environ.get('CODEX_THREAD_ID') == anchor['thread_id'],
        'Retained current-client anchor belongs to another interactive thread')
    return settings.capture(anchor)


if __name__ == '__main__':
    require(sys.argv[1:] == ['prepare'], 'Only the fixed offline candidate preparation is supported')
    raise SystemExit(prepare())
