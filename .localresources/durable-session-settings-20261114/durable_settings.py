"""Verify live settings and credentials without an editor-process lifetime gate."""
import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import durable_bootstrap as bootstrap

from humanvoice.artifacts import confined_path, digest, read_json
from tools.ensemble_closure_contract import save

HERE, previous = bootstrap.HERE, bootstrap.previous
rebind, state, base = previous.rebind, previous.rebind.state, previous.base
settings, routing = rebind.settings, rebind.routing
PATH = HERE / 'current-session.json'
VERSION = 'zlb-durable-settings-v1'
NATIVE_MARKER = rebind.write_marker
NATIVE_RECORDED = rebind.recorded_profile


def stable(binding):
    value = deepcopy(binding)
    value['server'].pop('pid')
    value['server'].pop('start_ticks')
    return value


def load():
    value = read_json(PATH)
    reference = rebind.load()['active_binding']
    state.require(stable(value) == stable(reference),
                  'Durable settings changed beyond editor PID/start time')
    return value


def checked_configuration(expected, effective, context, *, environment_hash, credential_hash):
    actual = settings.select_settings(context, effective)
    state.require(actual == expected['settings'], 'Active model/provider/permissions/settings changed')
    state.require(effective['config'].get('cli_auth_credentials_store', 'file') == 'file',
                  'Credential store changed')
    state.require(environment_hash == expected['credentials']['environment_sha256'],
                  'Execution credential/proxy environment changed')
    state.require(credential_hash == expected['credentials']['file_sha256'], 'Credential file changed')


def verify(binding):
    expected = load()
    # Only process identity is excluded. Client, thread, config, credentials and
    # all execution settings remain exact. The original native receipt binding
    # is preserved rather than relabelled as the current editor process.
    state.require(stable(binding) == stable(expected), 'Unadmitted durable settings binding')
    executable = Path(expected['server']['executable'])
    state.require(digest(executable.read_bytes()) == expected['executable_sha256'],
                  'Control configuration reader executable changed')
    context = settings.session_context(expected['session_path'], expected['thread_id'])
    effective = settings.native_config(str(executable), expected['server']['overrides'])
    credential_home = Path(os.environ.get('CODEX_HOME', str(Path(os.environ['HOME']) / '.codex'))).resolve()
    state.require(credential_home == settings.HOME.resolve(), 'Credential home changed')
    credential = credential_home / 'auth.json'
    state.require(str(credential) == expected['credentials']['path'], 'Credential path changed')
    checked_configuration(expected, effective, context,
        environment_hash=base.active_environment.environment_hash(expected),
        credential_hash=digest(credential.read_bytes()) if credential.is_file() else None)
    # Read again to reject edits during the configuration lookup.
    state.require(settings.session_context(expected['session_path'], expected['thread_id']) == context
                  and base.active_environment.environment_hash(expected) == expected['credentials']['environment_sha256']
                  and (digest(credential.read_bytes()) if credential.is_file() else None) == expected['credentials']['file_sha256'],
                  'Settings or credentials changed during verification')
    return digest(binding)


def adopt(profile):
    binding = routing.binding_for(profile)
    verify(binding)
    return {'status': 'EXACT_DURABLE_SETTINGS_VERIFIED',
            'environment_sha256': binding['credentials']['environment_sha256']}


def marker():
    expected = load()
    return {'version': VERSION, 'configuration': str(PATH),
            'configuration_sha256': digest(PATH.read_bytes()),
            'settings_sha256': digest(stable(expected)),
            'qualified_request_client': rebind.load()['request_client'],
            'editor_process_lifetime_required': False}


def write_marker(stage, row, directory):
    NATIVE_MARKER(stage, row, directory)
    path = directory / 'durable-settings.json'
    state.require(not path.exists(), 'Durable settings marker already exists')
    save(path, {**marker(), 'session_marker_sha256': digest((directory / 'session-rebind.json').read_bytes())})


def recorded_profile(snapshot, reference, expected):
    actual = NATIVE_RECORDED(snapshot, reference, expected)
    if actual == state.load()['profile']:
        directory = confined_path(Path(snapshot), reference['path']).parent
        state.require(read_json(directory / 'durable-settings.json') == {
            **marker(), 'session_marker_sha256': digest((directory / 'session-rebind.json').read_bytes())},
            'Receipt lacks its durable live-settings verification contract')
    return actual


@contextmanager
def scope():
    load()
    with patch.object(rebind, 'NATIVE_VERIFY', verify), patch.object(rebind, 'NATIVE_ADOPT', adopt), \
            patch.object(rebind, 'write_marker', write_marker), patch.object(rebind, 'recorded_profile', recorded_profile):
        yield
