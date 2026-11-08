"""Run new qualification/campaign component tests after the queued component suite."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MIGRATION = ROOT / '.localresources/session-migration-20261107'
CAMPAIGN = ROOT / '.localresources/session-campaign-20261107'
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]

from humanvoice.artifacts import digest, read_json
from tools import durable_program_supervisor as durable
from tools.validate_inventory_recovery_v3 import cleanup

PYTHON = '/tmp/humanvoice-release-env-20261029/bin/python'
END = 1794158980


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def run():
    require(sys.executable == PYTHON and sys.argv[1:] == ['test'],
        'Only fixed offline qualification and campaign component tests are supported')
    status = HERE / 'additional-tests-status.json'
    state = {'status': 'WAITING_FOR_MIGRATION_COMPONENTS', 'workers': 16,
        'model_calls': 0, 'account_writes': 0, 'grant_writes': 0}
    durable.save(status, state)
    while True:
        require(time.time() < END and not (HERE / 'STOP').exists(), 'Additional offline tests stopped or expired')
        current = read_json(MIGRATION / 'offline-tests-status.json')
        if current['status'] in {'PASS', 'FAIL'}:
            require(current.get('cleanup', {}).get('complete') is True,
                'Previous test cleanup did not release its worker allocation')
            break
        time.sleep(10)
    paths = [p for folder in (HERE, CAMPAIGN, MIGRATION) for p in sorted(folder.glob('*.py'))]
    before = {str(path): digest(path.read_bytes()) for path in paths}
    evidence = ROOT / 'docs/reviews/evidence/audit-lifetime-replay-20261030/client-campaign-qualification-20261107.xml'
    log = HERE / 'additional-tests.log'
    require(not evidence.exists() and not log.exists(), 'Prior component evidence must be retained')
    tests = [str(p) for folder in (HERE, CAMPAIGN) for p in sorted(folder.glob('test_*.py'))]
    command = [PYTHON, '-m', 'pytest', '-q', '-n', '16', '--timeout=120', '--junitxml=' + str(evidence), *tests]
    state.update(status='RUNNING', sources=before, tests=tests)
    durable.save(status, state)
    child = None
    try:
        with log.open('xb') as stream:
            child = subprocess.Popen(command, cwd=ROOT, env={**os.environ,
                'HUMANVOICE_AUDIT_WORKERS': '16', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'},
                stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            code = child.wait(timeout=min(900, END - time.time()))
        require(all(digest(Path(p).read_bytes()) == value for p, value in before.items()),
            'Source changed during additional component tests')
        state.update(status='PASS' if code == 0 else 'FAIL', returncode=code,
            junit=str(evidence), junit_sha256=digest(evidence.read_bytes()))
    except BaseException as error:
        state.update(status='FAIL', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        state['cleanup'] = cleanup(child) if child is not None else {'complete': True}
        if not state['cleanup']['complete']:
            state.update(status='FAIL', error='Additional test cleanup is incomplete')
        durable.save(status, state)
    print(json.dumps({key: value for key, value in state.items() if key not in {'sources', 'tests'}}))
    return 0 if state['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(run())
