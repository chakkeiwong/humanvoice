"""Fixed renewal, offline replay and ordinary-user continuation actions."""

import argparse
import json
import signal
import subprocess
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import session_bootstrap as bootstrap  # isort: skip -- initialize retained dependencies
import renewal_runtime as renewal
import session_endpoint
import validation_program as previous

from humanvoice.artifacts import digest, read_json
from tools.ensemble_closure_contract import save
from tools.inventory_history_adoption import no_inference

HERE = bootstrap.HERE
base, live, context = previous.base, previous.live, previous.context
UNIT = 'humanvoice-zlb-session-repair-20261113.service'
NATIVE_DISCOVER = previous.NATIVE_DISCOVER
NATIVE_WORKER = base.recovery.Worker


def sources():
    paths = [HERE / name for name in ('session_bootstrap.py', 'session_program.py',
              'renewal_runtime.py', 'renewal.json', 'session_endpoint.py', UNIT)]
    return {str(path): digest(path.read_bytes()) for path in paths}


LOADED = sources()


def discover(parent, binding, entries, failures, old=None):
    live.require(sources() == LOADED, 'Session repair implementation changed')
    prepared = HERE / 'rehearsal.json'
    if prepared.exists():
        value = read_json(prepared)
        if (value['sources'] == sources() and value['bank'] == {k: digest(v) for k, v in entries.items()}
                and value['failures_sha256'] == digest(failures)):
            path = Path(value['report'])
            live.require(digest(path.read_bytes()) == value['report_sha256'], 'Prepared session replay changed')
            report = read_json(path)
            live.require(report['binding'] == binding and report['bank'] == value['bank']
                         and report['session_repair_sources'] == sources(), 'Prepared replay binding changed')
            with live.offline_deadline(), context.plain_plan.scope(snapshots=[live.TRANSMISSION]):
                live.bound_sources(binding)
                current = context.demand_probe.seed_binding(context.SEED, parent.profile, parent.reference,
                    protocols=binding['protocols'], native_processes=True)
                live.require(current == binding, 'Prepared replay source or policy changed')
                verifier = context.native_parallel.ReceiptVerifier(binding, entries,
                    verify_qualification=parent.qualification)
                for entry in entries.values():
                    verifier.bank(entry['origin'], entry['request'], entry)
            base.retained_extension(old, report, entries, failures)
            return path, report, path, report
    with session_endpoint.scope(), previous.operation_reuse.scope() as reuse:
        result = NATIVE_DISCOVER(parent, binding, entries, failures, old)
    path, report, _, _ = result
    report.update(session_repair_sources=sources(), comparison_reuse={'launches': reuse.launches, 'hits': reuse.hits})
    save(path, report)
    return result


def current_review():
    previous.current_review()
    value = read_json(HERE / 'execution-review.json')
    live.require(value['status'] == 'READY' and value['sources'] == sources() == LOADED,
                 'Session repair review changed')
    for path, expected in value['artifacts'].items():
        live.require(digest(Path(path).read_bytes()) == expected, 'Session repair evidence changed')
    renewal.deadline_for(live.OUTPUT, read_json(live.STATE / 'admission.json')['deadline'])
    return value


@contextmanager
def runtime_scope(*, reviewed=True):
    with previous.previous.scope(), previous.offline_scope(), renewal.scope(), \
            patch.object(base, 'discover', discover), patch.object(base.recovery, 'Worker', Worker):
        if reviewed:
            with patch.object(base, 'current_review', current_review):
                yield
        else:
            yield


class Worker(NATIVE_WORKER):
    def __call__(self, demand, attempt):
        with runtime_scope():
            return super().__call__(demand, attempt)

    def recover(self, database, attempts):
        with runtime_scope():
            return super().recover(database, attempts)


def namespace(action):
    if action == 'rehearse-child':
        return ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--ro-bind', '/', '/',
                '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp', '--unshare-net',
                '--bind', str(HERE), str(HERE), '--bind', str(context.MANUSCRIPT), str(context.MANUSCRIPT),
                '--ro-bind', str(context.QUALIFICATION), str(context.QUALIFICATION),
                base.PYTHON, '-B', str(Path(__file__)), action]
    return previous.namespace('run-child')[:-4] + ['--bind', str(HERE), str(HERE),
             base.PYTHON, '-B', str(Path(__file__)), action]


def rehearse():
    previous.current_review()
    admission = read_json(live.STATE / 'admission.json')
    binding = admission['binding']
    files = [live.OUTPUT / 'native-attempts.json', live.OUTPUT / 'allocation-ledger.json',
             Path(admission['account']), Path(admission['grant'])]
    before = {str(path): digest(path.read_bytes()) for path in files}
    with no_inference(), runtime_scope(reviewed=False), live.offline_deadline(), context.parent() as parent:
        baseline = parent.prime_baseline()
        signal.alarm(0)
        live.guard()
        entries = live.bank_entries()
        failures = read_json(base.recovery.FAILURES)
        checkpoint = read_json(live.STATE / 'coordinator.json')
        old = read_json(checkpoint['previous']) if checkpoint['previous'] else None
        print(json.dumps({'baseline': baseline, 'retained_responses': len(entries),
                          'next': 'native replay with bounded semantic repair'}), flush=True)
        started = time.monotonic()
        path, report, _, _ = discover(parent, binding, entries, failures, old)
        live.require(before == {str(path): digest(path.read_bytes()) for path in files},
                     'Offline replay changed accounting')
        result = {'status': report['status'], 'frontier_complete': report['frontier_complete'],
                  'demands': len(report['demands']), 'report': str(path), 'report_sha256': digest(path.read_bytes()),
                  'sources': sources(), 'bank': {k: digest(v) for k, v in entries.items()},
                  'failures_sha256': digest(failures), 'elapsed_seconds': time.monotonic() - started,
                  'baseline': baseline, 'slots_remaining': 177 - len(read_json(files[0])['attempts']),
                  'model_calls': 0, 'account_writes': 0}
        save(HERE / 'rehearsal.json', result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('bank', 'sources')}), flush=True)
        live.require(previous.replay_usable(result), 'Native repair replay did not produce a usable frontier')


def review():
    previous.current_review()
    tests = read_json(HERE / 'execution-tests.json')
    replay = read_json(HERE / 'rehearsal.json')
    live.require(tests['sources'] == sources() and tests['tests'] > 0
                 and tests['failures'] == tests['errors'] == tests['skipped'] == 0, 'Execution tests stale')
    live.require(replay['sources'] == sources() and previous.replay_usable(replay), 'Actual repair replay incomplete')
    paths = [HERE / 'execution-tests.json', HERE / 'rehearsal.json', Path(replay['report']),
             HERE / 'tests-result.json', HERE / 'actual-session-check.json', *map(Path, tests['artifacts'])]
    value = {'status': 'READY', 'sources': sources(), 'deadline_changes': renewal.changes(),
             'artifacts': {str(path): digest(path.read_bytes()) for path in paths},
             'scope': {'unit': UNIT, 'disable': previous.UNIT, 'root_actions': 0, 'workers': 16,
                       'shared_calls': 177, 'deadline': renewal.RECORD['deadline'],
                       'approval_policy': 'on-request', 'approvals_reviewer': 'user'}}
    save(HERE / 'execution-review.json', value)
    print(json.dumps({'status': 'READY', 'scope': value['scope']}), flush=True)


def install_start():
    current_review()
    live.require(time.time() < renewal.RECORD['deadline'] and not (live.OUTPUT / 'STOP').exists(),
                 'Renewed execution expired or stopped')
    base.hv_service_env.adopt(read_json(live.STATE / 'admission.json')['binding']['profile'])
    base.startup_program.preflight()
    subprocess.run(['/usr/bin/systemd-analyze', '--user', 'verify', str(HERE / UNIT)], check=True, timeout=30)
    target = Path('/home/ubuntu/.config/systemd/user') / UNIT
    live.require(not target.is_symlink() and (not target.exists() or target.read_bytes() == (HERE / UNIT).read_bytes()),
                 'Service destination belongs to another payload')
    subprocess.run(['/usr/bin/systemctl', '--user', 'disable', '--now', previous.UNIT], check=True, timeout=30)
    temporary = target.with_suffix('.service.next')
    temporary.write_bytes((HERE / UNIT).read_bytes())
    temporary.replace(target)
    subprocess.run(['/usr/bin/systemctl', '--user', 'daemon-reload'], check=True, timeout=30)
    subprocess.run(['/usr/bin/systemctl', '--user', 'enable', '--now',
                    base.startup_program.original.OBSERVER, UNIT], check=True, timeout=30)
    save(HERE / 'installation.json', {'installed_at': time.time(), 'review': digest(current_review())})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('rehearse', 'rehearse-child', 'review', 'install-start', 'run', 'run-child'))
    action = parser.parse_args().action
    base.startup_program.original.bound_file_descriptors()
    if action == 'rehearse':
        return subprocess.run(namespace('rehearse-child'), check=False).returncode
    if action == 'rehearse-child':
        return rehearse()
    if action == 'review':
        return review()
    if action == 'install-start':
        return install_start()
    if action == 'run':
        current_review()
        base.startup_program.preflight()
        return base.active_environment.launch(namespace('run-child'), context.policy()['profile'])
    try:
        current_review()
        with runtime_scope():
            return base.run()
    except BaseException as error:
        live.publish('BLOCKED_REPAIR', error=type(error).__name__ + ': ' + str(error), traceback=traceback.format_exc())
        raise


if __name__ == '__main__':
    raise SystemExit(main())
