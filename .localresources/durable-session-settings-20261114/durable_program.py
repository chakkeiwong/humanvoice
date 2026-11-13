"""Reviewed ordinary-user continuation across an editor process/client reload."""
import argparse
import json
import subprocess
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import durable_settings as durable

from humanvoice.artifacts import digest, read_json
from tools.ensemble_closure_contract import save
from tools.inventory_history_adoption import no_inference

rebind = durable.rebind
HERE, previous = durable.HERE, durable.previous
base, live, context = previous.base, previous.live, previous.context
UNIT = 'humanvoice-zlb-durable-settings-20261114.service'
FILES = ('durable_bootstrap.py', 'durable_settings.py', 'current-session.json',
         'durable_program.py', 'environment-repair.json', UNIT)


def sources():
    return {str(HERE / name): digest((HERE / name).read_bytes()) for name in FILES}


def current_review():
    previous.current_review()
    durable.load()
    value = read_json(HERE / 'review.json')
    rebind.state.require(value['status'] == 'READY' and value['sources'] == sources(),
                         'Durable settings review changed')
    for path, expected in value['artifacts'].items():
        rebind.state.require(digest(Path(path).read_bytes()) == expected, 'Durable settings evidence changed')
    return value


@contextmanager
def scope(*, reviewed=True):
    with durable.scope(), previous.scope(reviewed=False), patch.object(base.recovery, 'Worker', Worker):
        if reviewed:
            with patch.object(base, 'current_review', current_review):
                yield
        else:
            yield


class Worker(previous.previous.NATIVE_WORKER):
    def __call__(self, demand, attempt):
        with scope():
            return super().__call__(demand, attempt)

    def recover(self, database, attempts):
        with scope():
            return super().recover(database, attempts)


def namespace(action):
    command = previous.namespace('run-child')[:-4] + ['--bind', str(HERE), str(HERE)]
    if action in ('offline-child', 'environment-child'):
        command += ['--unshare-net']
    return command + [base.PYTHON, '-B', str(Path(__file__)), action]


def offline():
    previous.current_review()
    durable.load()
    started = time.monotonic()
    value = rebind.state.load()
    check = read_json(previous.HERE / 'offline-result.json')
    rebind.state.require(check['status'] == 'PASS' and check['sources'] == previous.sources(),
                         'Predecessor continuation proof changed')
    with no_inference(), scope(reviewed=False):
        entries = live.bank_entries()
        rebind.state.require({k: digest(v) for k, v in entries.items()} == value['original_bank'],
                             'Retained bank changed')
        before = read_json(rebind.gateway.HERE / 'offline-result.json')['retained_files']
        for path, expected in before.items():
            rebind.state.require(digest(Path(path).read_bytes()) == expected, 'Retained accounting changed')
    result = {'status': 'PASS', 'sources': sources(), 'retained_responses': len(entries),
              'predecessor': {'path': str(previous.HERE / 'offline-result.json'),
                              'sha256': digest((previous.HERE / 'offline-result.json').read_bytes())},
              'elapsed_seconds': time.monotonic() - started, 'model_calls': 0, 'account_writes': 0}
    save(HERE / 'offline-result.json', result)
    print(json.dumps({k:v for k,v in result.items() if k != 'sources'}), flush=True)


def review():
    previous.current_review()
    tests, check = read_json(HERE / 'tests-result.json'), read_json(HERE / 'offline-result.json')
    rebind.state.require(tests['sources'] == check['sources'] == sources() and check['status'] == 'PASS'
                         and tests['tests'] > 0 and tests['failures'] == tests['errors'] == tests['skipped'] == 0,
                         'Durable settings checks are incomplete or stale')
    for path, expected in tests['artifacts'].items():
        rebind.state.require(digest(Path(path).read_bytes()) == expected, 'Durable settings regression evidence changed')
    paths = [HERE / 'tests-result.json', HERE / 'offline-result.json', *map(Path, tests['artifacts'])]
    save(HERE / 'review.json', {'status': 'READY', 'sources': sources(),
         'artifacts': {str(path): digest(path.read_bytes()) for path in paths},
         'scope': {'unit': UNIT, 'disable': [previous.UNIT], 'root_actions': 0,
                   'workers': 16, 'deadline': rebind.load()['deadline'], 'shared_slots': 177,
                   'pinned_execution_client': rebind.load()['request_client'],
                   'configuration_reader_cli': durable.load()['cli_version'],
                   'editor_process_lifetime_required': False,
                   'approval_policy': 'on-request', 'approvals_reviewer': 'user'}})
    print(json.dumps({'status': 'READY', 'unit': UNIT, 'root_actions': 0}), flush=True)


def environment_child():
    transition = rebind.state.load()
    with no_inference(), durable.scope(), rebind.scope(), rebind.gateway.runtime.environment_scope(transition['old_profile']):
        for key in ('old_profile', 'profile'):
            binding = rebind.routing.binding_for(transition[key])
            rebind.state.require(rebind.settings.verify(binding) == digest(binding), 'Child binding verification failed')
        checks = base.active_environment.concurrent_preflight(transition['old_profile'])
    save(HERE / 'environment-check.json', {'status': 'PASS', 'sources': sources(),
         'concurrent_verification': checks, 'model_calls': 0})


def preflight():
    current_review()
    rebind.state.require(time.time() < rebind.load()['deadline'] and not (live.OUTPUT / 'STOP').exists(),
                         'Execution renewal expired or explicit STOP present')
    with durable.scope(), rebind.scope(), rebind.gateway.runtime.scope():
        rebind.adopt(rebind.state.load()['old_profile'])
        rebind.state.require(base.active_environment.launch(namespace('environment-child'),
                             rebind.state.load()['old_profile']) == 0, 'Actual host/sandbox verification failed')
    probe = base.startup_program.preflight()
    checked = read_json(probe)
    rebind.state.require(checked['status'] == 'PASS' and checked['network_isolated']
                         and checked['client_sha256'] == rebind.load()['request_client']['executable_sha256'],
                         'Startup check did not use the pinned qualified client')
    save(HERE / 'startup-check.json', {'status': 'PASS', 'sources': sources(),
         'probe': str(probe), 'sha256': digest(probe.read_bytes()), 'model_calls': 0})


def service_preflight():
    # Exercise the actual systemd environment, not just the interactive shell.
    # The only explicitly injected value is non-secret client identification.
    subprocess.run(['/usr/bin/systemd-run', '--user', '--wait', '--collect', '--quiet',
        '--unit=humanvoice-zlb-durable-preflight-' + str(time.time_ns()),
        '--property=NoNewPrivileges=yes',
        '--setenv=CODEX_INTERNAL_ORIGINATOR_OVERRIDE=codex_vscode',
        base.PYTHON, '-B', str(Path(__file__)), 'preflight'], check=True, timeout=240)


def install_start():
    service_preflight()
    subprocess.run(['/usr/bin/systemd-analyze', '--user', 'verify', str(HERE / UNIT)], check=True, timeout=30)
    target = Path('/home/ubuntu/.config/systemd/user') / UNIT
    predecessor = read_json(HERE / 'environment-repair.json')
    rebind.state.require(predecessor == {
        'previous_unit_sha256': '0c98cabfa70ba2c1352dd5651e72b3f71e5db5ae9221b69620b2a1e8b51bed2c',
        'environment_key': 'CODEX_INTERNAL_ORIGINATOR_OVERRIDE', 'environment_value': 'codex_vscode',
        'reason': 'Only required environment key missing from the user service manager.',
        'before_attempts': 135, 'paid_calls_before_repair': 0}, 'Service environment repair scope changed')
    rebind.state.require(not target.is_symlink() and (not target.exists()
        or target.read_bytes() == (HERE / UNIT).read_bytes()
        or digest(target.read_bytes()) == predecessor['previous_unit_sha256']),
        'User service destination belongs to another payload')
    subprocess.run(['/usr/bin/systemctl', '--user', 'disable', '--now', previous.UNIT], check=True, timeout=30)
    temporary = target.with_suffix('.service.next')
    temporary.write_bytes((HERE / UNIT).read_bytes())
    temporary.replace(target)
    subprocess.run(['/usr/bin/systemctl', '--user', 'daemon-reload'], check=True, timeout=30)
    subprocess.run(['/usr/bin/systemctl', '--user', 'enable', '--now', base.startup_program.original.OBSERVER, UNIT],
                   check=True, timeout=30)
    save(HERE / 'installation.json', {'installed_at': time.time(), 'review': digest(current_review())})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('offline', 'offline-child', 'review', 'environment-child',
                                         'preflight', 'install-start', 'run', 'run-child'))
    action = parser.parse_args().action
    base.startup_program.original.bound_file_descriptors()
    if action == 'offline': return subprocess.run(namespace('offline-child'), check=False, timeout=900).returncode
    if action == 'offline-child': return offline()
    if action == 'review': return review()
    if action == 'environment-child': return environment_child()
    if action == 'preflight': return preflight()
    if action == 'install-start': return install_start()
    try:
        if action == 'run':
            live.publish('VERIFYING_CURRENT_SETTINGS', repair='durable_settings_after_editor_reload')
            preflight()
            with durable.scope(), rebind.scope(), rebind.gateway.runtime.scope():
                return base.active_environment.launch(namespace('run-child'), rebind.state.load()['old_profile'])
        current_review()
        with scope():
            return base.run()
    except BaseException as error:
        live.publish('BLOCKED_REPAIR', error=type(error).__name__ + ': ' + str(error), traceback=traceback.format_exc())
        raise


if __name__ == '__main__':
    raise SystemExit(main())
