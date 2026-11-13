"""Follow active provider settings while retaining the qualified request client.

An editor reload is a new control process, not permission to replace the tested
request executable. The explicit record separates these two identities. No
new-client qualification or wire-equivalence credit is asserted.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import reload_bootstrap as bootstrap

from humanvoice.artifacts import confined_path, digest, read_json
from tools.ensemble_closure_contract import save

HERE, gateway = bootstrap.HERE, bootstrap.previous
state, transport, base = gateway.state, gateway.runtime, gateway.base
settings, routing = state.settings, state.routing
PATH = HERE / 'session-rebind.json'
NATIVE_VERIFY = transport.NATIVE_VERIFY
NATIVE_ADOPT = base.hv_service_env.adopt
NATIVE_MARKER = transport.write_marker
NATIVE_RECORDED = state.recorded_profile
VERSION = 'zlb-active-control-session-pinned-client-v1'


def compatible(old, current):
    """Only the control process/client may differ; effective settings may not."""
    expected = deepcopy(old)
    for key in ('cli_version', 'executable_sha256'):
        expected[key] = current[key]
    for key in ('pid', 'start_ticks', 'executable'):
        expected['server'][key] = current['server'][key]
    state.require(expected == current,
                  'Reload changed model/gateway/credentials/permissions/thread or effective settings')
    state.require(current['settings']['approval_policy'] == 'on-request'
                  and current['settings']['approvals_reviewer'] == 'user',
                  'Reload lacks human approval settings')


def active_profile(value):
    # Used ONLY to read/verify the current control process environment. It is
    # never selected for a manuscript request or given qualification credit.
    profile = state.load()['profile']
    candidate = settings.candidate_profile(profile[routing.FIELD]['base_profile'], value['active_binding'])
    return routing.candidate_profile(state.stream.candidate_profile(candidate), profile[routing.FIELD]['index'])


def prepare():
    gateway.current_review()
    transition = state.load()
    binding = read_json(gateway.HERE / 'reloaded-session-capture.json')
    compatible(routing.binding_for(transition['profile']), binding)
    state.require(len(read_json(state.live.OUTPUT / 'native-attempts.json')['attempts']) == 135
                  and read_json(state.live.STATE / 'coordinator.json')['pending'] is None,
                  'Session rebind requires the drained 135-attempt boundary')
    value = {'version': VERSION, 'gateway_transition': str(state.PATH),
             'gateway_sha256': digest(state.PATH.read_bytes()),
             'active_binding': binding, 'request_client': transition['profile']['runtime']['codex'],
             'deadline': transition['deadline'], 'first_new_slot': transition['first_new_slot'],
             'authorization': transition['authorization'],
             'continuation_authorization': transition['continuation_authorization'],
             'qualification': 'Retain the exact qualified request client; no credit for the upgraded editor client.'}
    if PATH.exists():
        state.require(read_json(PATH) == value, 'Preserve the existing session rebind')
    else:
        save(PATH, value)
    return load()


def load():
    value, transition = read_json(PATH), state.load()
    state.require(value['version'] == VERSION
                  and value['gateway_transition'] == str(state.PATH)
                  and value['gateway_sha256'] == digest(state.PATH.read_bytes())
                  and value['request_client'] == transition['profile']['runtime']['codex']
                  and value['deadline'] == transition['deadline']
                  and value['first_new_slot'] == transition['first_new_slot']
                  and value['authorization'] == transition['authorization']
                  and value['continuation_authorization'] == transition['continuation_authorization'],
                  'Session rebind differs from its immutable execution/authorization binding')
    compatible(routing.binding_for(transition['profile']), value['active_binding'])
    client = value['request_client']
    state.require(digest(Path(client['executable']).read_bytes()) == client['executable_sha256'],
                  'Pinned qualified request client changed or disappeared')
    return value


def verify(binding):
    value, transition = load(), state.load()
    allowed = [routing.binding_for(transition[k]) for k in ('old_profile', 'profile')]
    allowed.append(value['active_binding'])
    if binding not in allowed:
        return NATIVE_VERIFY(binding)
    state.require(NATIVE_VERIFY(value['active_binding']) == digest(value['active_binding']),
                  'Current control session verification failed')
    return digest(binding)


def adopt(profile):
    value, transition = load(), state.load()
    state.require(profile in (transition['old_profile'], transition['profile']),
                  'Session rebind cannot adopt a foreign request profile')
    return NATIVE_ADOPT(active_profile(value))


def marker(value, gateway_marker):
    return {'version': VERSION, 'rebind': str(PATH), 'rebind_sha256': digest(PATH.read_bytes()),
            'active_binding_hash': digest(value['active_binding']),
            'request_client': value['request_client'], 'gateway_marker_hash': digest(gateway_marker)}


def write_marker(stage, row, directory):
    value = load()
    NATIVE_MARKER(stage, row, directory)
    path = directory / 'session-rebind.json'
    state.require(not path.exists(), 'Session rebind marker already exists')
    save(path, marker(value, read_json(directory / 'gateway-transition.json')))


def recorded_profile(snapshot, reference, expected):
    actual = NATIVE_RECORDED(snapshot, reference, expected)
    transition = state.load()
    if actual == transition['profile']:
        directory = confined_path(Path(snapshot), reference['path']).parent
        state.require(read_json(directory / 'session-rebind.json') == marker(
            load(), read_json(directory / 'gateway-transition.json')),
            'Receipt lacks its exact active-session/pinned-client transition')
    return actual


@contextmanager
def scope():
    load()
    with patch.object(transport, 'NATIVE_VERIFY', verify), \
            patch.object(base.hv_service_env, 'adopt', adopt), \
            patch.object(transport, 'write_marker', write_marker), \
            patch.object(state, 'recorded_profile', recorded_profile):
        yield
