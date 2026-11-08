"""Resume the exact unspent qualification after a missing archive receipt.

The approved launcher and historical evidence remain immutable. The only
runtime substitution reads the same pinned receipt bytes inside the existing
output mount. Native image, alias, settlement and budget validation still run.
"""

import atexit
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from functools import partial
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = ROOT / '.localresources/session-qualification-20261107'
OUTPUT = PREVIOUS / 'repair-20261108'
sys.path[:0] = [str(PREVIOUS), str(ROOT), str(ROOT / 'src')]

import execution
import namespace
import supervise

from humanvoice.artifacts import digest, read_json
from tools import archive_evidence as archive
from tools import durable_program_supervisor as durable
from tools import probe_active_client_loopback as loopback
from tools.delayed_network_runtime import replaced_aliases
from tools.validate_inventory_recovery_v3 import cleanup

require = execution.require
PLAN = OUTPUT / 'repair-plan.json'
RECEIPT = OUTPUT / 'archive-receipt.json'
EXPECTED_ERROR = "FileNotFoundError: [Errno 2] No such file or directory: '" + str(archive.RECEIPT) + "'"
NATIVE_INITIALIZE_WORKER = archive.initialize_worker


def check_unspent(state, failure, progress, *, alive=durable.alive):
    require(state.get('status') == failure.get('status') == 'QUALIFICATION_BLOCKED'
        and failure.get('error') == EXPECTED_ERROR
        and state.get('launches') == 1 and type(state['launches']) is int
        and state.get('cleanup', {}).get('complete') is True
        and state.get('descendant_cleanup', {}).get('descendants_quiescent') is True
        and not alive(state.get('owner')) and not alive(state.get('child_owner')),
        'Restart requires the exact stopped missing-receipt failure and complete cleanup')
    expected = {'allocated': 0, 'completed': 0, 'unresolved': 0,
        'terminal': 'prepared', 'ledger_sha256': None}
    require(state.get('progress') == progress == expected,
        'Qualification allocated or settled work; native reconciliation is required')


def plan():
    value = read_json(PLAN)
    require(value == execution.identified(value) and value['action'] == 'resume-unspent-qualification',
        'Repair proposal identity changed')
    require(all(digest(Path(path).read_bytes()) == checksum for path, checksum in value['sources'].items()),
        'Reviewed repair source changed')
    require(digest(RECEIPT.read_bytes()) == archive.RECEIPT_SHA256,
        'Private archive receipt differs from the pinned historical bytes')
    return value


@contextmanager
def receipt_scope(path=RECEIPT):
    require(path.resolve() == path and not path.is_symlink()
        and digest(path.read_bytes()) == archive.RECEIPT_SHA256,
        'Repair requires an ordinary exact-byte archive receipt')
    original, initializer = archive.RECEIPT, archive.initialize_worker
    archive.RECEIPT = path
    archive.initialize_worker = partial(initialize_worker, path)
    try:
        yield
    finally:
        archive.RECEIPT, archive.initialize_worker = original, initializer


def initialize_worker(path):
    # Spawn/forkserver workers import fresh modules. Bind the pinned receipt in
    # each worker before the native initializer verifies its image and aliases.
    context = receipt_scope(path)
    context.__enter__()
    atexit.register(context.__exit__, None, None, None)
    NATIVE_INITIALIZE_WORKER()


def prepare():
    record, prepared, _candidate, _native, _extension = execution.approved_inputs()
    state = read_json(PREVIOUS / 'supervisor-status.json')
    failure = read_json(PREVIOUS / 'execution-failure.json')
    check_unspent(state, failure, supervise.inspect_progress(prepared['output']))
    OUTPUT.mkdir(exist_ok=True)
    require(digest(archive.RECEIPT.read_bytes()) == archive.RECEIPT_SHA256, 'Historical receipt changed')
    if not RECEIPT.exists():
        with RECEIPT.open('xb') as handle:
            handle.write(archive.RECEIPT.read_bytes())
    require(digest(RECEIPT.read_bytes()) == archive.RECEIPT_SHA256, 'Copied receipt changed')
    sources = {str(path): digest(path.read_bytes()) for path in sorted(HERE.glob('*.py'))}
    value = execution.identified({'action': 'resume-unspent-qualification',
        'original_authorization': record['identity'], 'prior_status': state, 'prior_failure': failure,
        'sources': sources, 'receipt_sha256': archive.RECEIPT_SHA256,
        'budget_addition': 0, 'new_budget_authorization': False,
        'maximum_total_launches': 3, 'window_end_utc': execution.WINDOW_END})
    execution.migration.save_new(PLAN, value)
    print(json.dumps({'status': 'REPAIR_PREPARED', 'identity': value['identity'], 'extra_calls': 0}))


def preflight_inside(parent_network):
    loopback.require_isolation(parent_network)
    require(os.statvfs(ROOT).f_flag & os.ST_RDONLY, 'Preflight workspace is not read-only')
    value = plan()
    authority = read_json(PREVIOUS / 'execution-authorization.json')
    before = {path: digest(Path(path).read_bytes()) for path in (authority['account'], authority['grant'])}
    # Enter the complete native history stack that failed before allocation.
    # Block actual qualification/transport dispatch in addition to network isolation.
    def no_calls(*_args, **_kwargs):
        raise AssertionError('No-call repair preflight attempted inference')

    with receipt_scope(), replaced_aliases(execution.qualification.execute, no_calls), (
            execution.accounting.history_scope()):
        require(archive.current() is not None, 'Native archive validation did not run')
    require(before == {path: digest(Path(path).read_bytes()) for path in before},
        'Offline history preflight changed spending authority')
    result = {'status': 'NATIVE_HISTORY_PREFLIGHT_PASS', 'repair_identity': value['identity'],
        'sources': value['sources'], 'model_calls': 0, 'account_writes': 0, 'grant_writes': 0}
    execution.migration.save_new(OUTPUT / 'preflight.json', result)
    print(json.dumps(result))


def preflight_command():
    authority = read_json(PREVIOUS / 'execution-authorization.json')
    command = ['/usr/bin/bwrap', '--unshare-user', '--unshare-net', '--die-with-parent', '--new-session',
        '--ro-bind', '/', '/', '--tmpfs', '/home', '--tmpfs', '/dev/shm']
    for path in (str(ROOT), '/home/ubuntu/.codex', '/home/ubuntu/.vscode', '/home/ubuntu/miniforge3'):
        command += ['--ro-bind', path, path]
    for path in namespace.writable_roots(authority):
        command += ['--bind', path, path]
    for source, target in namespace.mounts():
        command += ['--ro-bind', source, target]
    return [*command, '--chdir', str(ROOT), '--', execution.PYTHON, str(HERE / 'repair.py'),
        'inside-preflight', os.readlink('/proc/self/ns/net')]


def preflight():
    plan()
    require(not (OUTPUT / 'preflight.log').exists(), 'Retain earlier preflight results before retry')
    child = None
    try:
        with (OUTPUT / 'preflight.log').open('xb') as handle:
            child = subprocess.Popen(preflight_command(), stdin=subprocess.DEVNULL,
                stdout=handle, stderr=subprocess.STDOUT, start_new_session=True,
                env={**os.environ, 'HUMANVOICE_AUDIT_WORKERS': '16',
                    'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
            code = child.wait(timeout=min(900, execution.WINDOW_END - time.time()))
    finally:
        result = cleanup(child) if child is not None else {'complete': True}
        durable.save(OUTPUT / 'preflight-cleanup.json', result)
    require(code == 0 and result['complete'], 'Native history preflight failed; inspect preflight.log')
    print(json.dumps(read_json(OUTPUT / 'preflight.json')))


def disposition(previous, native, value):
    if previous == value['prior_status']:
        check_unspent(previous, value['prior_failure'], supervise.inspect_progress(PREVIOUS / 'qualification-host'))
        return 'RECONCILE_NATIVE'
    return native(previous)


def run():
    value = plan()
    record, _prepared, _candidate, _native, _extension = execution.approved_inputs()
    require(record['identity'] == value['original_authorization'], 'Original execution authority changed')
    native_command, native_disposition = namespace.command, supervise.disposition

    def command(authority):
        native_command(authority)
        return [execution.PYTHON, str(HERE / 'repair.py'), 'worker']

    namespace.command = command
    supervise.disposition = lambda previous: disposition(previous, native_disposition, value)
    try:
        with receipt_scope():
            return supervise.run()
    finally:
        namespace.command, supervise.disposition = native_command, native_disposition


def worker():
    value = plan()
    original = execution.control.require_running

    def guard(*args, **kwargs):
        require(plan()['identity'] == value['identity'], 'Repair changed before provider dispatch')
        return original(*args, **kwargs)

    with receipt_scope(), replaced_aliases(original, guard):
        previous_arguments = sys.argv
        sys.argv = [execution.__file__, 'execute']
        try:
            return execution.main()
        finally:
            sys.argv = previous_arguments


if __name__ == '__main__':
    require(sys.executable == execution.PYTHON and len(sys.argv) in {2, 3}, 'Fixed repair actions only')
    action = sys.argv[1]
    if action == 'inside-preflight' and len(sys.argv) == 3:
        preflight_inside(sys.argv[2])
    else:
        require(len(sys.argv) == 2 and action in {'prepare', 'preflight', 'run', 'worker'}, 'Unknown repair action')
        if action == 'run':
            signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Supervisor stopped')))
        if action in {'prepare', 'preflight'}:
            with (HERE / 'offline.lock').open('a') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                (prepare if action == 'prepare' else preflight)()
        else:
            raise SystemExit(run() if action == 'run' else worker())
