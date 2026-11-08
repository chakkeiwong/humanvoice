"""Wait for the active continuation, then run only the bounded migration tests."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT), str(ROOT / 'src')]

from humanvoice.artifacts import digest
from tools import durable_program_supervisor as durable
from tools.validate_inventory_recovery_v3 import cleanup

PYTHON = '/tmp/humanvoice-release-env-20261029/bin/python'
CONTINUATION = Path('/tmp/hv-finalization-continuation-za0i2xpf/status.json')
HOST = ROOT / '.localresources/finalization-host-20261107'
END = 1794158980  # 2026-11-08T17:29:40Z, already authorized.
EVIDENCE = ROOT / 'docs/reviews/evidence/audit-lifetime-replay-20261030'


def sources(paths=None):
    if paths is None:
        paths = [path for folder in (HERE, HOST) for path in sorted(folder.glob('*.py'))]
    return {str(path): digest(Path(path).read_bytes()) for path in paths}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run():
    try:
        return checked_run()
    except BaseException as error:
        path = HERE / 'offline-tests-status.json'
        state = json.loads(path.read_bytes()) if path.exists() else {}
        state.update(status='FAIL', error=type(error).__name__ + ': ' + str(error))
        durable.save(path, state)
        raise


def checked_run():
    require(sys.executable == PYTHON and sys.argv[1:] == ['test'],
        'Only the fixed bounded offline migration suites are supported')
    result_path = HERE / 'offline-tests-status.json'
    # Code can be repaired while waiting without invalidating existing evidence:
    # no test has started yet. Freeze its exact membership at slot acquisition.
    state = {'status': 'WAITING_FOR_CONTINUATION', 'owner': durable.identity(os.getpid()),
        'workers': 16, 'model_calls': 0, 'account_writes': 0, 'grant_writes': 0}
    durable.save(result_path, state)
    while True:
        require(time.time() < END and not (HERE / 'STOP').exists(),
            'Migration tests reached their authorization deadline or explicit stop')
        active = json.loads(CONTINUATION.read_bytes())
        if active.get('status') != 'running' and not durable.alive(active['owner']):
            require(active.get('status') == 'offline_complete_exact_host_admission_pending',
                'Continuation stopped for diagnosis; inspect cleanup before claiming its slots')
            break
        time.sleep(10)
    before = sources()
    files = [path for path in sorted(HERE.glob('test_*.py')) if path.name != 'test_migration_native.py']
    files += sorted(HOST.glob('test_*.py'))
    result = EVIDENCE / 'client-migration-host-20261107.xml'
    require(not result.exists(), 'Prior migration test evidence must be retained separately')
    argv = [PYTHON, '-m', 'pytest', '-q', '-n', '16', '--timeout=120',
        '--junitxml=' + str(result), *[str(path) for path in files]]
    log = HERE / 'offline-tests.log'
    require(not log.exists(), 'Prior test log cannot be replaced')
    state.update(status='RUNNING', sources=before, argv=argv, continuation_status=active['status'])
    durable.save(result_path, state)
    process = None
    try:
        environment = {**os.environ, 'HUMANVOICE_AUDIT_WORKERS': '16',
            'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
        with log.open('xb') as stream:
            process = subprocess.Popen(argv, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            state['test_owner'] = durable.identity(process.pid)
            durable.save(result_path, state)
            deadline = min(time.time() + 900, END)
            while process.poll() is None:
                require(time.time() < deadline and not (HERE / 'STOP').exists(),
                    'Bounded offline suite reached its deadline or explicit stop')
                time.sleep(2)
        require(before == sources(before), 'Migration sources changed during testing')
        state.update(status='PASS' if process.returncode == 0 else 'FAIL', returncode=process.returncode,
            junit=str(result), junit_sha256=digest(result.read_bytes()) if result.exists() else None)
    except BaseException as error:
        state.update(status='FAIL', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        if process is not None:
            state['cleanup'] = cleanup(process)
            if not state['cleanup']['complete']:
                state.update(status='FAIL', error='Offline worker cleanup is incomplete')
        durable.save(result_path, state)
    print(json.dumps({key: value for key, value in state.items() if key not in ('sources', 'argv')}), flush=True)
    return 0 if state['status'] == 'PASS' else 1


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Test supervisor stopped')))
    raise SystemExit(run())
