"""Reviewed ordinary-user continuation across an editor process/client reload."""
import argparse
import json
import subprocess
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import session_rebind as rebind

from humanvoice.artifacts import digest, read_json
from tools.ensemble_closure_contract import save
from tools.inventory_history_adoption import no_inference

HERE, previous = rebind.HERE, rebind.gateway
base, live, context = previous.base, previous.live, previous.context
UNIT = 'humanvoice-zlb-reloaded-20261114.service'
FILES = ('reload_bootstrap.py', 'session_rebind.py', 'session-rebind.json',
         'reload_program.py', UNIT)


def sources():
    return {str(HERE / name): digest((HERE / name).read_bytes()) for name in FILES}


def current_review():
    previous.current_review()
    rebind.load()
    value = read_json(HERE / 'review.json')
    rebind.state.require(value['status'] == 'READY' and value['sources'] == sources(),
                         'Session reload review changed')
    for path, expected in value['artifacts'].items():
        rebind.state.require(digest(Path(path).read_bytes()) == expected, 'Session reload evidence changed')
    return value


@contextmanager
def scope(*, reviewed=True):
    with rebind.scope(), previous.scope(reviewed=False), patch.object(base.recovery, 'Worker', Worker):
        if reviewed:
            with patch.object(base, 'current_review', current_review):
                yield
        else:
            yield


class Worker(previous.NATIVE_WORKER):
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
    value, before_sources = rebind.load(), sources()
    predecessor = read_json(previous.HERE / 'offline-result.json')
    for path, expected in predecessor['retained_files'].items():
        rebind.state.require(digest(Path(path).read_bytes()) == expected, 'Retained accounting changed')
    transition = rebind.state.load()
    entries = live.bank_entries()
    rebind.state.require({k: digest(v) for k, v in entries.items()} == transition['original_bank'],
                         'Retained response bank changed')
    report = read_json(read_json(previous.previous.HERE / 'rehearsal.json')['report'])
    from types import SimpleNamespace
    stage = SimpleNamespace(output=live.OUTPUT, plan=read_json(live.OUTPUT / 'plan.json'))
    commands = []
    with no_inference():
        for index, demand in enumerate(report['demands']):
            row = {'slot': transition['first_new_slot'] + index, 'demand': demand}
            before = previous.runtime.config_for(stage, row)
            request = {'profile': transition['profile'], 'timeout_seconds': before['timeout_seconds'],
                       **demand['request']}
            with previous.context.native_parallel.receipt_scope(transition['profile']):
                argv = previous.runtime.native.qualified.routing.command(request, Path('/tmp/reload-command'), Path('/tmp'))
            with scope(reviewed=False):
                after = previous.runtime.config_for(stage, row)
                current = previous.runtime.native.qualified.routing.command(request, Path('/tmp/reload-command'), Path('/tmp'))
            rebind.state.require(before == after and argv == current
                                 and argv[0] == value['request_client']['executable']
                                 and any(rebind.state.NEW_URL in arg for arg in argv)
                                 and 'approval_policy="on-request"' in argv and 'approvals_reviewer="user"' in argv,
                                 'Reload changed the qualified HTTPS request command/configuration')
            commands.append(digest(argv))
    rebind.state.require(before_sources == sources(), 'Reload sources changed during verification')
    result = {'status': 'PASS', 'sources': sources(), 'retained_responses': len(entries),
              'demands': len(commands), 'command_hashes': commands,
              'predecessor_offline': {'path': str(previous.HERE / 'offline-result.json'),
                                     'sha256': digest((previous.HERE / 'offline-result.json').read_bytes())},
              'baseline_revalidated_by_unchanged_source_and_evidence': True,
              'request_client': value['request_client'], 'model_calls': 0, 'account_writes': 0}
    save(HERE / 'offline-result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('sources', 'command_hashes')}), flush=True)


def review():
    previous.current_review()
    tests, check = read_json(HERE / 'tests-result.json'), read_json(HERE / 'offline-result.json')
    rebind.state.require(tests['sources'] == check['sources'] == sources() and check['status'] == 'PASS'
                         and tests['tests'] > 0 and tests['failures'] == tests['errors'] == tests['skipped'] == 0,
                         'Session reload checks are incomplete or stale')
    for path, expected in tests['artifacts'].items():
        rebind.state.require(digest(Path(path).read_bytes()) == expected, 'Reload regression evidence changed')
    paths = [HERE / 'tests-result.json', HERE / 'offline-result.json', *map(Path, tests['artifacts'])]
    save(HERE / 'review.json', {'status': 'READY', 'sources': sources(),
         'artifacts': {str(path): digest(path.read_bytes()) for path in paths},
         'scope': {'unit': UNIT, 'disable': [previous.UNIT], 'root_actions': 0,
                   'workers': 16, 'deadline': rebind.load()['deadline'], 'shared_slots': 177,
                   'pinned_execution_client': rebind.load()['request_client'],
                   'active_control_cli': rebind.load()['active_binding']['cli_version'],
                   'approval_policy': 'on-request', 'approvals_reviewer': 'user'}})
    print(json.dumps({'status': 'READY', 'unit': UNIT, 'root_actions': 0}), flush=True)


def environment_child():
    transition = rebind.state.load()
    with no_inference(), rebind.scope(), previous.runtime.environment_scope(transition['old_profile']):
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
    with rebind.scope(), previous.runtime.scope():
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


def install_start():
    preflight()
    subprocess.run(['/usr/bin/systemd-analyze', '--user', 'verify', str(HERE / UNIT)], check=True, timeout=30)
    target = Path('/home/ubuntu/.config/systemd/user') / UNIT
    rebind.state.require(not target.is_symlink() and (not target.exists() or target.read_bytes() == (HERE / UNIT).read_bytes()),
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
    parser.add_argument('action', choices=('prepare', 'offline', 'offline-child', 'review', 'environment-child',
                                         'preflight', 'install-start', 'run', 'run-child'))
    action = parser.parse_args().action
    base.startup_program.original.bound_file_descriptors()
    if action == 'prepare': return rebind.prepare() and 0
    if action == 'offline': return subprocess.run(namespace('offline-child'), check=False, timeout=900).returncode
    if action == 'offline-child': return offline()
    if action == 'review': return review()
    if action == 'environment-child': return environment_child()
    if action == 'preflight': return preflight()
    if action == 'install-start': return install_start()
    if action == 'run':
        preflight()
        with rebind.scope(), previous.runtime.scope():
            return base.active_environment.launch(namespace('run-child'), rebind.state.load()['old_profile'])
    try:
        current_review()
        with scope():
            return base.run()
    except BaseException as error:
        live.publish('BLOCKED_REPAIR', error=type(error).__name__ + ': ' + str(error), traceback=traceback.format_exc())
        raise


if __name__ == '__main__':
    raise SystemExit(main())
