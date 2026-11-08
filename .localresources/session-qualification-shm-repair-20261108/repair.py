"""Final unspent restart: exercise native history in the actual system service."""

import importlib.util
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = ROOT / '.localresources/session-qualification-20261107'
RECEIPT_REPAIR = ROOT / '.localresources/session-qualification-resume-20261108'
sys.path[:0] = [str(PREVIOUS), str(ROOT), str(ROOT / 'src')]

import execution
import grant_dispatch
import launch
import namespace
import supervise

from humanvoice.artifacts import digest, read_json
from tools import automatic_call_grant as grants
from tools import durable_program_supervisor as durable
from tools import probe_active_client_loopback as loopback
from tools.delayed_network_runtime import replaced_aliases

# The receipt adapter is already reviewed; import it under an unambiguous name
# usable by spawn workers without changing any of its approved source files.
SPEC = importlib.util.spec_from_file_location('qualification_receipt_repair', RECEIPT_REPAIR / 'repair.py')
receipt = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = receipt
SPEC.loader.exec_module(receipt)

OUTPUT = PREVIOUS / 'shm-repair-20261108'
PLAN = OUTPUT / 'plan.json'
PREFLIGHT_UNIT = 'humanvoice-qualification-history-preflight-20261108.service'
require = execution.require
ERROR = 'PermissionError: [Errno 13] Permission denied'


def unspent(state, failure, progress, *, alive=durable.alive):
    expected = {'allocated': 0, 'completed': 0, 'unresolved': 0,
        'terminal': 'prepared', 'ledger_sha256': None}
    require(state['status'] == failure['status'] == 'QUALIFICATION_BLOCKED'
        and failure['error'] == ERROR and type(state['launches']) is int and state['launches'] == 2
        and state['cleanup']['complete'] and state['descendant_cleanup']['descendants_quiescent']
        and state['progress'] == progress == expected
        and not alive(state['owner']) and not alive(state['child_owner']),
        'Final restart requires the exact zero-call semaphore failure and complete cleanup')


def properties(authority, *, offline):
    values = namespace.properties(authority, isolated_network=offline)
    old = 'TemporaryFileSystem=/dev/shm:rw,nosuid,nodev'
    require(values.count(old) == 1, 'Original shared-memory scope changed')
    return [p if p != old else old + ',mode=1777' for p in values]


def commands(authority):
    remaining = int(execution.WINDOW_END - time.time())
    require(remaining > 1200, 'Not enough authorized time for the grouped preflight and restart')
    offline = ['/usr/bin/systemd-run', '--quiet', '--wait', '--pipe', '--unit=' + PREFLIGHT_UNIT,
        '--service-type=exec', '--property=RuntimeMaxSec=900', '--property=TimeoutStopSec=15',
        '--property=KillMode=control-group', '--working-directory=' + str(ROOT),
        *['--property=' + p for p in properties(authority, offline=True)],
        *['--setenv=' + key + '=' + value for key, value in sorted(namespace.environment().items())],
        '--', execution.PYTHON, str(HERE / 'repair.py'), 'inside-preflight', os.readlink('/proc/self/ns/net')]
    live = launch.service_command(authority, now=time.time())[1:]
    old = '--property=TemporaryFileSystem=/dev/shm:rw,nosuid,nodev'
    require(live.count(old) == 1, 'Original live shared-memory scope changed')
    live = [p if p != old else old + ',mode=1777' for p in live]
    live[-3:] = [execution.PYTHON, str(HERE / 'repair.py'), 'run']
    return offline, live


def plan():
    value = read_json(PLAN)
    require(value == execution.identified(value)
        and all(digest(Path(p).read_bytes()) == h for p, h in value['sources'].items()),
        'Reviewed final repair source changed')
    receipt.plan()  # Preserves the prior receipt adapter and exact-byte copy.
    return value


def prepare():
    authority, prepared, _candidate, _native, _addition = execution.approved_inputs()
    state, failure = (read_json(PREVIOUS / name) for name in ('supervisor-status.json', 'execution-failure.json'))
    unspent(state, failure, supervise.inspect_progress(prepared['output']))
    offline, live = commands(authority)
    OUTPUT.mkdir(exist_ok=True)
    value = execution.identified({'action': 'preflight-and-resume-final-unspent-qualification',
        'original_authorization': authority['identity'], 'prior_status': state, 'prior_failure': failure,
        'sources': {str(p): digest(p.read_bytes()) for p in sorted(HERE.glob('*.py'))},
        'offline_command': offline, 'live_command': live,
        'window_end': execution.WINDOW_END, 'additional_calls': 0,
        'total_call_ceiling': 2235, 'prior_launches': 2, 'maximum_total_launches': 3})
    execution.migration.save_new(PLAN, value)
    print(json.dumps({'status': 'FINAL_REPAIR_PREPARED', 'identity': value['identity'], 'extra_calls': 0}))


def preflight(parent_network):
    loopback.require_isolation(parent_network)
    value = plan()
    authority, _prepared, _candidate, _native, _addition = execution.approved_inputs()
    namespace.validate_environment(authority)
    require(os.stat('/dev/shm').st_mode & 0o1777 == 0o1777 and os.access('/dev/shm', os.W_OK),
        'Private shared memory must support unprivileged worker locks')
    lock = multiprocessing.get_context('spawn').Lock()
    with lock:
        pass
    report = check_accounting(authority)
    result = {'status': 'SYSTEM_NATIVE_HISTORY_PASS', 'repair_identity': value['identity'],
        'model_calls': 0, 'account_writes': 0, 'grant_writes': 0, 'workers': 16,
        'grant_status': report}
    execution.migration.save_new(OUTPUT / 'preflight.json', result)
    print(json.dumps(result))


def check_accounting(authority):
    """Exercise the same extended grant reader as execution, with no inference."""
    before = {p: digest(Path(p).read_bytes()) for p in (authority['account'], authority['grant'])}

    def no_calls(*_args, **_kwargs):
        raise AssertionError('Offline preflight attempted model execution')

    with receipt.receipt_scope(), grant_dispatch.scope(), replaced_aliases(execution.qualification.execute, no_calls), (
            execution.grant_extension.scope(PREVIOUS / 'call-authorization.json',
                expected_sha256=authority['sources'][str(PREVIOUS / 'call-authorization.json')])), (
            execution.accounting.history_scope()):
        report = grants.status(authority['grant'])
    require(before == {p: digest(Path(p).read_bytes()) for p in before}, 'Preflight changed spending authority')
    return report


def run():
    value = plan()
    authority, _prepared, _candidate, _native, _addition = execution.approved_inputs()
    require(authority['identity'] == value['original_authorization'], 'Original authority changed')
    require(read_json(OUTPUT / 'preflight.json')['repair_identity'] == value['identity'], 'Actual preflight missing')
    native_command, native_disposition = namespace.command, supervise.disposition

    def command(record):
        native_command(record)
        return [execution.PYTHON, str(HERE / 'repair.py'), 'worker']

    def disposition(previous):
        if previous == value['prior_status']:
            unspent(previous, value['prior_failure'], supervise.inspect_progress(PREVIOUS / 'qualification-host'))
            return 'RECONCILE_NATIVE'
        return native_disposition(previous)

    namespace.command, supervise.disposition = command, disposition
    try:
        with receipt.receipt_scope():
            return supervise.run()
    finally:
        namespace.command, supervise.disposition = native_command, native_disposition


def worker():
    value = plan()
    original = execution.control.require_running

    def guard(*args, **kwargs):
        require(plan()['identity'] == value['identity'], 'Repair changed before dispatch')
        return original(*args, **kwargs)

    previous_arguments = sys.argv
    sys.argv = [execution.__file__, 'execute']
    try:
        with receipt.receipt_scope(), grant_dispatch.scope(), replaced_aliases(original, guard):
            return execution.main()
    finally:
        sys.argv = previous_arguments


def start():
    value = plan()
    authority, prepared, _candidate, _native, _addition = execution.approved_inputs()
    state, failure = (read_json(PREVIOUS / name) for name in ('supervisor-status.json', 'execution-failure.json'))
    unspent(state, failure, supervise.inspect_progress(prepared['output']))
    require(state == value['prior_status'] and failure == value['prior_failure']
        and authority['identity'] == value['original_authorization'], 'Reviewed restart state changed')
    subprocess.run(['/usr/bin/pkexec', '/usr/bin/python3', '-I', '-B', str(HERE / 'host.py'),
        'start', digest(PLAN.read_bytes())], check=True, timeout=1200)
    print(json.dumps({'status': 'PREFLIGHT_PASSED_FINAL_RESTART_SUBMITTED', 'extra_calls': 0}))


if __name__ == '__main__':
    require(sys.executable == execution.PYTHON and len(sys.argv) in {2, 3}, 'Fixed final repair actions only')
    action = sys.argv[1]
    if action == 'inside-preflight' and len(sys.argv) == 3:
        preflight(sys.argv[2])
    else:
        require(len(sys.argv) == 2 and action in {'prepare', 'start', 'run', 'worker'}, 'Unknown final repair action')
        if action == 'run':
            signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Supervisor stopped')))
        if action in {'prepare', 'start'}:
            (prepare if action == 'prepare' else start)()
        else:
            raise SystemExit(run() if action == 'run' else worker())
