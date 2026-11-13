"""Fixed offline checks and ordinary-user HTTPS continuation for the same stage."""
import argparse
import json
import subprocess
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import gateway_runtime as runtime
import gateway_state as state

from humanvoice.artifacts import digest, read_json
from tools.ensemble_closure_contract import save
from tools.inventory_history_adoption import no_inference

HERE, previous = state.HERE, state.previous
base, live, context = previous.base, previous.live, previous.context
UNIT = 'humanvoice-zlb-https-20261113.service'
NATIVE_WORKER = previous.NATIVE_WORKER


def sources():
    return {str(HERE / name): digest((HERE / name).read_bytes()) for name in
            ('gateway_bootstrap.py', 'gateway_state.py', 'gateway_runtime.py', 'gateway_program.py',
             'transition.json', UNIT)}


LOADED = sources()


def current_review():
    previous.current_review()
    state.load()
    value = read_json(HERE / 'review.json')
    state.require(value['status'] == 'READY' and value['sources'] == sources() == LOADED,
                  'Gateway continuation source/review changed')
    for path, expected in value['artifacts'].items():
        state.require(digest(Path(path).read_bytes()) == expected, 'Gateway test/rehearsal evidence changed')
    return value


@contextmanager
def scope(*, reviewed=True):
    with previous.runtime_scope(reviewed=False), runtime.scope(), patch.object(base.recovery, 'Worker', Worker):
        if reviewed:
            with patch.object(base, 'current_review', current_review):
                yield
        else:
            yield


class Worker(NATIVE_WORKER):
    def __call__(self, demand, attempt):
        with scope():
            return super().__call__(demand, attempt)

    def recover(self, database, attempts):
        with scope():
            return super().recover(database, attempts)


def namespace(action):
    if action == 'offline-child':
        return ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--ro-bind', '/', '/',
                '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp', '--unshare-net',
                '--bind', str(HERE), str(HERE),
                '--ro-bind', str(context.QUALIFICATION), str(context.QUALIFICATION),
                base.PYTHON, '-B', str(Path(__file__)), action]
    command = previous.namespace('run-child')[:-4] + ['--bind', str(HERE), str(HERE)]
    if action == 'environment-child':
        command += ['--unshare-net']
    return command + [base.PYTHON, '-B', str(Path(__file__)), action]


def offline():
    """Verify actual retained bank and each new transport config without inference."""
    previous.current_review()
    value = state.load()
    before_sources = sources()
    admission = read_json(live.STATE / 'admission.json')
    files = [live.OUTPUT / 'native-attempts.json', live.OUTPUT / 'allocation-ledger.json',
             Path(admission['account']), Path(admission['grant'])]
    before = {str(path): digest(path.read_bytes()) for path in files}
    started = time.monotonic()
    with no_inference(), scope(reviewed=False), live.offline_deadline(), context.parent() as parent:
        entries = live.bank_entries()
        state.require({k: digest(v) for k, v in entries.items()} == value['original_bank'],
                      'Retained response bank changed during migration')
        binding = admission['binding']
        with context.plain_plan.scope(snapshots=[live.TRANSMISSION]):
            verifier = context.native_parallel.ReceiptVerifier(binding, entries, verify_qualification=parent.qualification)
            for entry in entries.values():
                verifier.bank(entry['origin'], entry['request'], entry)
        replay = read_json(previous.HERE / 'rehearsal.json')
        report = read_json(replay['report'])
        state.require(digest(Path(replay['report']).read_bytes()) == replay['report_sha256']
                      and report['binding'] == binding and report['bank'] == value['original_bank'],
                      'Verified semantic frontier changed')
        from types import SimpleNamespace
        stage = SimpleNamespace(output=live.OUTPUT, plan=read_json(live.OUTPUT / 'plan.json'))
        for i, demand in enumerate(report['demands']):
            config = runtime.config_for(stage, {'slot': value['first_new_slot'] + i, 'demand': demand})
            request = {'profile': value['profile'], 'timeout_seconds': config['timeout_seconds'], **demand['request']}
            # Construct the exact native command independently of live dispatch.
            with context.native_parallel.receipt_scope(value['profile']):
                args = runtime.native.qualified.routing.command(request, Path('/tmp/gateway-command-check'), Path('/tmp'))
            state.require(any(state.NEW_URL in arg for arg in args) and not any(state.OLD_URL in arg for arg in args)
                          and 'approval_policy="on-request"' in args and 'approvals_reviewer="user"' in args,
                          'New transport command differs from HTTPS/human approval settings')
        authorization = runtime.authorize(live.TRANSMISSION, value['profile'])
        state.require(authorization['destination'] == state.NEW_URL + '/responses', 'Wrong permission destination')
    state.require(sources() == before_sources and before == {p: digest(Path(p).read_bytes()) for p in before},
                  'Offline gateway check changed source/accounting')
    result = {'status': 'PASS', 'sources': sources(), 'retained_responses': len(entries),
              'demands': len(report['demands']), 'frontier_sha256': replay['report_sha256'],
              'endpoint': state.NEW_URL, 'elapsed_seconds': time.monotonic() - started,
              'model_calls': 0, 'account_writes': 0, 'retained_files': before}
    save(HERE / 'offline-result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('sources', 'retained_files')}), flush=True)


def review():
    previous.current_review()
    tests, check = read_json(HERE / 'tests-result.json'), read_json(HERE / 'offline-result.json')
    state.require(tests['sources'] == check['sources'] == sources() == LOADED
                  and tests['tests'] > 0 and tests['failures'] == tests['errors'] == tests['skipped'] == 0
                  and check['status'] == 'PASS', 'Gateway verification is incomplete or stale')
    for path, expected in tests['artifacts'].items():
        state.require(digest(Path(path).read_bytes()) == expected, 'Gateway test evidence changed')
    paths = [HERE / 'tests-result.json', HERE / 'offline-result.json', *map(Path, tests['artifacts'])]
    value = {'status': 'READY', 'sources': sources(), 'transport_adapters': runtime.changes(),
             'artifacts': {str(path): digest(path.read_bytes()) for path in paths},
             'scope': {'unit': UNIT, 'disable': [previous.previous.UNIT],
                       'root_actions': 0, 'endpoint': state.NEW_URL, 'workers': 16,
                       'deadline': previous.renewal.RECORD['deadline'], 'shared_calls': 177,
                       'approval_policy': 'on-request', 'approvals_reviewer': 'user'}}
    save(HERE / 'review.json', value)
    print(json.dumps({'status': 'READY', 'scope': value['scope']}), flush=True)


def install_start():
    reviewed = current_review()
    state.require(time.time() < previous.renewal.RECORD['deadline'] and not (live.OUTPUT / 'STOP').exists(),
                  'Renewed execution window expired or explicit STOP present')
    with runtime.scope():
        base.hv_service_env.adopt(state.load()['old_profile'])
        state.require(base.active_environment.launch(namespace('environment-child'),
                      state.load()['old_profile']) == 0, 'Actual sandbox gateway verification failed')
    base.startup_program.preflight()
    subprocess.run(['/usr/bin/systemd-analyze', '--user', 'verify', str(HERE / UNIT)], check=True, timeout=30)
    target = Path('/home/ubuntu/.config/systemd/user') / UNIT
    state.require(not target.is_symlink() and (not target.exists() or target.read_bytes() == (HERE / UNIT).read_bytes()),
                  'Gateway service destination belongs to another payload')
    subprocess.run(['/usr/bin/systemctl', '--user', 'disable', '--now', previous.previous.UNIT], check=True, timeout=30)
    temporary = target.with_suffix('.service.next')
    temporary.write_bytes((HERE / UNIT).read_bytes())
    temporary.replace(target)
    subprocess.run(['/usr/bin/systemctl', '--user', 'daemon-reload'], check=True, timeout=30)
    subprocess.run(['/usr/bin/systemctl', '--user', 'enable', '--now',
                    base.startup_program.original.OBSERVER, UNIT], check=True, timeout=30)
    save(HERE / 'installation.json', {'installed_at': time.time(), 'review': digest(reviewed)})


def environment_child():
    value = state.load()
    with no_inference(), runtime.environment_scope(value['old_profile']):
        for key in ('old_profile', 'profile'):
            binding = state.routing.binding_for(value[key])
            state.require(state.settings.verify(binding) == digest(binding), 'Sandbox binding differs from host')
        checks = base.active_environment.concurrent_preflight(value['old_profile'])
    save(HERE / 'environment-check.json', {'status': 'PASS', 'endpoint': state.NEW_URL,
         'sources': sources(), 'concurrent_verification': checks, 'model_calls': 0})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('offline', 'offline-child', 'environment-child', 'review', 'install-start', 'run', 'run-child'))
    action = parser.parse_args().action
    base.startup_program.original.bound_file_descriptors()
    if action == 'offline':
        return subprocess.run(namespace('offline-child'), check=False, timeout=1050).returncode
    if action == 'offline-child': return offline()
    if action == 'environment-child': return environment_child()
    if action == 'review': return review()
    if action == 'install-start': return install_start()
    if action == 'run':
        current_review()
        base.startup_program.preflight()
        with runtime.scope():
            return base.active_environment.launch(namespace('run-child'), state.load()['old_profile'])
    try:
        current_review()
        with scope():
            return base.run()
    except BaseException as error:
        live.publish('BLOCKED_REPAIR', error=type(error).__name__ + ': ' + str(error), traceback=traceback.format_exc())
        raise


if __name__ == '__main__':
    raise SystemExit(main())
