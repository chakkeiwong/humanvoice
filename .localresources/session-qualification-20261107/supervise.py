"""Own one approved qualification process and retain exact crash observations.

Native transport failures retry inside the child. A killed worker can re-enter
native receipt reconciliation only after its systemd cgroup is quiescent. An
ambiguous native allocation remains charged and cannot authorize a new call.
"""

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OWNER = ROOT / '.localresources/finalization-continuation-repair01-20261107'
sys.path[:0] = [str(HERE), str(OWNER), str(ROOT), str(ROOT / 'src')]

import execution
import namespace
import program_projection
from humanvoice_owned_descendants_20261031 import Descendants

from humanvoice.artifacts import digest, read_json
from tools import durable_program_supervisor as durable
from tools.validate_inventory_recovery_v3 import cleanup

require = execution.require
UNIT = 'humanvoice-current-client-qualification-20261107.service'
MAXIMUM_LAUNCHES = 3


def save_status(path, state):
    # Persist the operational result before updating its readable checkpoint.
    # A projection failure remains visible without discarding process cleanup.
    durable.save(path, state)
    try:
        program_projection.refresh(state)
    except (OSError, ValueError) as failure:
        state['master_refresh_error'] = type(failure).__name__ + ': ' + str(failure)
        durable.save(path, state)


def require_empty_service():
    """A restart may not outlive another process in this exact service."""
    rows = [line.split(':', 2) for line in Path('/proc/self/cgroup').read_text().splitlines()]
    current = [path for hierarchy, controllers, path in rows if hierarchy == '0' and controllers == '']
    require(len(current) == 1 and Path(current[0]).name == UNIT,
        'Qualification supervisor requires its exact systemd service cgroup')
    root = Path('/sys/fs/cgroup') / current[0].lstrip('/')
    require(root.is_dir() and not any(path.is_dir() for path in root.iterdir()),
        'Qualification service has an unexpected descendant cgroup')
    members = {int(value) for value in (root / 'cgroup.procs').read_text().split()}
    require(members == {os.getpid()}, 'Qualification service retains another owned process')
    return {'path': current[0], 'members': sorted(members)}


def inspect_progress(output):
    """Use completed ledger rows as progress; heartbeat alone cannot advance it."""
    output = Path(output)
    ledger = output / 'allocation-ledger.json'
    rows = read_json(ledger)['calls'] if ledger.exists() else []
    terminal = output / 'execution.json'
    return {'allocated': len(rows), 'completed': sum(row['status'] == 'complete' for row in rows),
        'unresolved': sum(row['status'] == 'allocated_unknown' for row in rows),
        'terminal': read_json(terminal).get('status') if terminal.exists() else None,
        'ledger_sha256': digest(ledger.read_bytes()) if ledger.exists() else None}


def disposition(previous, *, alive=durable.alive):
    if previous is None:
        return 'START'
    if alive(previous.get('child_owner')):
        return 'OBSERVE_OWNED_CHILD'
    if previous.get('status') == 'CURRENT_CLIENT_QUALIFICATION_VERIFIED':
        return 'DONE'
    if (previous.get('status') in {'STARTING', 'RUNNING', 'WORKER_CRASHED'}
            and type(previous.get('launches')) is int and 0 < previous['launches'] < MAXIMUM_LAUNCHES):
        return 'RECONCILE_NATIVE'
    return 'RECONCILE_BEFORE_RESTART'


def run():
    record, prepared, _candidate, plan, _extension = execution.approved_inputs()
    output = Path(prepared['output'])
    path = HERE / 'supervisor-status.json'
    with (HERE / 'supervisor.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = read_json(path) if path.exists() else None
        mode = disposition(previous)
        require(mode in {'START', 'RECONCILE_NATIVE', 'DONE'},
            'Qualification already has durable ownership: ' + mode)
        if previous is not None:
            require(previous.get('plan_identity') == plan['plan_identity']
                and previous.get('authorization_identity') == record['identity'],
                'Qualification restart changed its original plan or authority')
        if mode == 'DONE':
            require(read_json(HERE / 'qualification-verified.json') == previous['evidence'],
                'Completed qualification evidence changed before supervisor reentry')
            return 0
        cgroup = require_empty_service()
        require(time.time() < record['window_end_utc'] and not (HERE / 'STOP').exists(),
            'Qualification cannot start after its authorized deadline or explicit stop')
        state = {'status': 'STARTING', 'plan_identity': plan['plan_identity'],
            'authorization_identity': record['identity'], 'owner': durable.identity(os.getpid()),
            'window_end_utc': record['window_end_utc'], 'production_admitted': False,
            'started_at_utc': previous['started_at_utc'] if previous else time.time(),
            'last_progress_at_utc': time.time(), 'cgroup': cgroup,
            'launches': (previous['launches'] if previous else 0) + 1,
            'restart_mode': mode, 'prior_progress': previous.get('progress') if previous else None}
        # Persist launch intent first. Reload requires an empty service cgroup
        # and native receipt reconciliation before any further allocation.
        save_status(path, state)
        owned = Descendants()
        child = None
        error = None
        try:
            with (HERE / 'execution.log').open('ab') as log:
                (HERE / 'scratch').mkdir(exist_ok=True)
                command = namespace.command(record)
                child = subprocess.Popen(command,
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True, env={**os.environ, 'HUMANVOICE_AUDIT_WORKERS': '16',
                        'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'})
                owned.attach(child.pid)
                state.update(status='RUNNING', child_owner=durable.identity(child.pid))
                save_status(path, state)
                previous_progress = None
                while child.poll() is None:
                    require(time.time() < record['window_end_utc'] and not (HERE / 'STOP').exists(),
                        'Qualification reached its authorized deadline or explicit stop')
                    owned.scan()
                    progress = inspect_progress(output)
                    if progress != previous_progress:
                        state['last_progress_at_utc'] = time.time()
                        previous_progress = progress
                    state.update(progress=progress, observed_at_utc=time.time(),
                        stalled_seconds=time.time() - state['last_progress_at_utc'])
                    state['attention_required'] = state['stalled_seconds'] > 1920
                    save_status(path, state)
                    time.sleep(5)
                state['returncode'] = child.returncode
                verified = HERE / 'qualification-verified.json'
                # Bubblewrap can encode a killed inner worker as 128 + signal.
                # Both forms re-enter native receipt reconciliation; neither
                # form clears an allocation or retries a semantic result.
                if child.returncode in {-signal.SIGKILL, 128 + signal.SIGKILL}:
                    state.update(status='WORKER_CRASHED',
                        next='Re-enter native receipt reconciliation after complete owned cleanup')
                else:
                    require(child.returncode == 0 and verified.exists(),
                        'Qualification worker did not return verified native evidence')
                    evidence = read_json(verified)
                    execution.migration_policy.validate_fresh_evidence(evidence, plan['profile'])
                    require(evidence['output'] == str(output) and evidence['plan_identity'] == plan['plan_identity'],
                        'Qualification worker returned another plan or output')
                    state.update(status='CURRENT_CLIENT_QUALIFICATION_VERIFIED', evidence=evidence)
        except BaseException as failure:  # noqa: BLE001 -- persist failure after owned cleanup
            error = failure
            state.update(status='QUALIFICATION_BLOCKED', error=type(failure).__name__ + ': ' + str(failure))
        finally:
            try:
                state['cleanup'] = cleanup(child, grace_seconds=10) if child is not None else {'complete': True}
            except BaseException as failure:  # noqa: BLE001 -- always continue descendant cleanup
                state['cleanup'] = {'complete': False, 'error': type(failure).__name__ + ': ' + str(failure)}
            try:
                state['descendant_cleanup'] = owned.finish()
            except BaseException as failure:  # noqa: BLE001 -- publish incomplete ownership cleanup
                state['descendant_cleanup'] = {'descendants_quiescent': False,
                    'error': type(failure).__name__ + ': ' + str(failure)}
            if not state['cleanup']['complete'] or not state['descendant_cleanup']['descendants_quiescent']:
                state.update(status='QUALIFICATION_BLOCKED', error='Owned qualification process cleanup incomplete')
            try:
                state['progress'] = inspect_progress(output)
            except (OSError, ValueError, KeyError, TypeError) as failure:
                state.update(status='QUALIFICATION_BLOCKED',
                    error='Native progress unavailable: ' + type(failure).__name__ + ': ' + str(failure))
            state.setdefault('progress', None)
            state['observed_at_utc'] = time.time()
            save_status(path, state)
        print(json.dumps({key: state[key] for key in ('status', 'observed_at_utc', 'progress', 'production_admitted')}))
        if error is not None:
            return 2
        if state['status'] == 'WORKER_CRASHED' and state['launches'] < MAXIMUM_LAUNCHES:
            return 75
        return 0 if state['status'] == 'CURRENT_CLIENT_QUALIFICATION_VERIFIED' else 2


if __name__ == '__main__':
    require(sys.executable == execution.PYTHON and sys.argv[1:] == ['run'],
        'Only the exact approved qualification supervisor action is supported')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Supervisor stopped')))
    try:
        code = run()
    except Exception as error:  # noqa: BLE001 -- persist a visible terminal service failure
        save_status(HERE / 'supervisor-failure.json', {
            'status': 'QUALIFICATION_BLOCKED', 'observed_at_utc': time.time(),
            'error': type(error).__name__ + ': ' + str(error), 'production_admitted': False})
        code = 2
    raise SystemExit(code)
