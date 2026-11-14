"""Fixed regression, evidence and ordinary-user continuation actions."""
import argparse
import json
import subprocess
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import interrupted_batch as interruption

from humanvoice.artifacts import digest, read_json
from tools.ensemble_closure_contract import save
from tools.inventory_history_adoption import no_inference

HERE, previous = interruption.HERE, interruption.previous
base, live, context = previous.base, previous.live, previous.context
capture, recovery = interruption.capture, interruption.recovery
UNIT = 'humanvoice-zlb-worker-recovery-20261114.service'
FILES = ('recovery_bootstrap.py', 'capture_recovery.py', 'interrupted_batch.py',
         'recovery_program.py', 'incident.json', UNIT)


def sources():
    return {str(HERE / name): digest((HERE / name).read_bytes()) for name in FILES}


def current_review():
    previous.current_review()
    value = read_json(HERE / 'review.json')
    live.require(value['status'] == 'READY' and value['sources'] == sources()
                 and value['changes'] == capture.changes(), 'Worker recovery review changed')
    for path, expected in value['artifacts'].items():
        live.require(digest(Path(path).read_bytes()) == expected, 'Worker recovery evidence changed')
    interruption.incident()
    return value


@contextmanager
def scope(*, reviewed=True):
    with previous.scope(reviewed=False), capture.scope(), \
            patch.object(recovery, 'Worker', Worker):
        if reviewed:
            with patch.object(base, 'current_review', current_review):
                yield
        else:
            yield


class Worker(previous.rebind.gateway.NATIVE_WORKER):
    def __call__(self, demand, attempt):
        with scope():
            return super().__call__(demand, attempt)

    def recover(self, database, attempts):
        with scope():
            return super().recover(database, attempts)


def namespace(action):
    command = previous.namespace('run-child')[:-4] + ['--bind', str(HERE), str(HERE)]
    if action == 'offline-child':
        command += ['--unshare-net']
    return command + [base.PYTHON, '-B', str(Path(__file__)), action]


def prepare():
    previous.current_review()
    data = read_json(live.OUTPUT / 'native-attempts.json')
    calls = read_json(live.OUTPUT / 'allocation-ledger.json')['calls']
    status = read_json(live.STATE / 'status.json')
    database = str(live.STATE / 'wave-003/batch.sqlite')
    rows = [r for r in data['attempts'] if r['database'] == database]
    live.require(status['error'] == 'Blocked: Captured launch evidence changed'
                 and len(data['attempts']) == len(calls) == 140 and len(rows) == 5,
                 'Expected the retained five-attempt recovery-check incident')
    files, known, interrupted = {}, [], []
    for row in rows:
        completion = read_json(live.OUTPUT / f"calls/{row['slot']:04d}/completion.json")
        (known if completion['kind'] in {'success', 'negative'} else interrupted).append(row['task'])
        for root in (Path(row['runtime_directory']), live.OUTPUT / f"calls/{row['slot']:04d}"):
            files.update({str(root / name): value for name, value in capture.native.evidence_tree(root).items()})
    import sqlite3
    with sqlite3.connect(Path(database).as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        scheduler_attempts = [dict(r) for r in db.execute(
            'SELECT id,task,token,state,charged_tokens FROM attempts ORDER BY id')]
    value = {'version': interruption.VERSION, 'cause': status['error'], 'status_at_failure': status,
             'database': database, 'attempts': data['attempts'], 'allocations': calls, 'rows': rows,
             'files': files, 'scheduler_attempts': scheduler_attempts, 'known_tasks': known, 'interrupted_tasks': interrupted,
             'charges_released': 0, 'counters_reset': 0}
    recovery.immutable(interruption.PATH, value)
    print(json.dumps({'retained': len(known), 'interrupted': len(interrupted), 'allocated': len(calls)}))


def offline():
    previous.current_review()
    started, before_sources = time.monotonic(), sources()
    value = interruption.incident()
    admission = read_json(live.STATE / 'admission.json')
    files = [live.OUTPUT / 'native-attempts.json', live.OUTPUT / 'allocation-ledger.json',
             Path(admission['account']), Path(admission['grant']), Path(value['database']),
             live.STATE / 'coordinator.json']
    before = {str(p): digest(p.read_bytes()) for p in files}
    bank_before = {k: digest(v) for k, v in live.bank_entries().items()}
    with no_inference(), scope(reviewed=False):
        for row in value['rows']:
            for owner in (row['worker_owner'], row['capture_owner']['owner']):
                live.require(interruption.process_identity(owner['pid']) != owner,
                             'Offline audit refuses a live worker/client')
        stage = recovery.Stage(live.OUTPUT, binding=admission['binding'])
        interruption.eligible(stage, value['database'])
    live.require(before == {str(p): digest(p.read_bytes()) for p in files}
                 and bank_before == {k: digest(v) for k, v in live.bank_entries().items()}
                 and sources() == before_sources, 'Offline audit changed production state')
    save(HERE / 'offline-result.json', {'status': 'PASS', 'sources': before_sources,
         'elapsed_seconds': time.monotonic() - started, 'retained_bank': len(bank_before),
         'new_known': len(value['known_tasks']), 'interrupted': len(value['interrupted_tasks']),
         'allocated': len(value['attempts']), 'remaining': 177-len(value['attempts']),
         'model_calls': 0, 'account_writes': 0, 'retained_files': before})
    print(json.dumps({k:v for k,v in read_json(HERE / 'offline-result.json').items()
                      if k not in ('sources', 'retained_files')}), flush=True)


def review():
    previous.current_review()
    tests, check = read_json(HERE / 'tests-result.json'), read_json(HERE / 'offline-result.json')
    live.require(tests['sources'] == check['sources'] == sources() and check['status'] == 'PASS'
                 and tests['tests'] > 0 and tests['failures'] == tests['errors'] == tests['skipped'] == 0,
                 'Worker recovery checks are incomplete/stale')
    paths = [HERE / 'tests-result.json', HERE / 'offline-result.json', *map(Path, tests['artifacts'])]
    for path, expected in tests['artifacts'].items():
        live.require(digest(Path(path).read_bytes()) == expected, 'Regression evidence changed')
    save(HERE / 'review.json', {'status': 'READY', 'sources': sources(), 'changes': capture.changes(),
         'artifacts': {str(p): digest(p.read_bytes()) for p in paths},
         'scope': {'unit': UNIT, 'disable': previous.UNIT, 'root_actions': 0,
                   'workers': 16, 'shared_calls': 177, 'deadline': previous.rebind.load()['deadline'],
                   'approval_policy': 'on-request', 'approvals_reviewer': 'user',
                   'final_zlb_acceptance': False}})
    print('Worker recovery review READY', flush=True)


def install_start():
    current_review()
    # Previous service preflight is unchanged and uses the actual user manager.
    previous.service_preflight()
    subprocess.run(['/usr/bin/systemd-analyze', '--user', 'verify', str(HERE / UNIT)], check=True, timeout=30)
    target = Path('/home/ubuntu/.config/systemd/user') / UNIT
    live.require(not target.is_symlink() and (not target.exists() or target.read_bytes() == (HERE / UNIT).read_bytes()),
                 'Service destination belongs to another payload')
    subprocess.run(['/usr/bin/systemctl', '--user', 'disable', '--now', previous.UNIT], check=True, timeout=30)
    temporary = target.with_suffix('.service.next')
    temporary.write_bytes((HERE / UNIT).read_bytes())
    temporary.replace(target)
    subprocess.run(['/usr/bin/systemctl', '--user', 'daemon-reload'], check=True, timeout=30)
    subprocess.run(['/usr/bin/systemctl', '--user', 'enable', '--now', base.startup_program.original.OBSERVER, UNIT],
                   check=True, timeout=30)
    save(HERE / 'installation.json', {'installed_at': time.time(), 'review_sha256': digest(current_review())})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'offline', 'offline-child', 'review',
                                         'install-start', 'run', 'run-child'))
    action = parser.parse_args().action
    base.startup_program.original.bound_file_descriptors()
    if action == 'prepare': return prepare()
    if action == 'offline': return subprocess.run(namespace('offline-child'), check=False, timeout=900).returncode
    if action == 'offline-child': return offline()
    if action == 'review': return review()
    if action == 'install-start': return install_start()
    try:
        current_review()
        if action == 'run':
            live.publish('VERIFYING_CURRENT_SETTINGS', repair='gateway_worker_recovery')
            previous.preflight()
            with previous.durable.scope(), previous.rebind.scope(), previous.rebind.gateway.runtime.scope():
                return base.active_environment.launch(namespace('run-child'), previous.rebind.state.load()['old_profile'])
        with scope():
            with no_inference():
                live.publish('RECOVERING_INTERRUPTED_BATCH', repair='gateway_worker_recovery')
                detail = interruption.transition()
                save(HERE / 'transition-result.json', detail)
            return base.run()
    except BaseException as error:
        live.publish('BLOCKED_REPAIR', error=type(error).__name__ + ': ' + str(error), traceback=traceback.format_exc())
        raise


if __name__ == '__main__':
    raise SystemExit(main())
