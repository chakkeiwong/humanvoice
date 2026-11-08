"""Fixed offline activation, native preparation and configuration after qualification."""

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
QUALIFICATION = ROOT / '.localresources/session-qualification-20261107'
BUILDER = ROOT / '.localresources/release-gates-20261029'
sys.path[:0] = [str(HERE), str(QUALIFICATION), str(BUILDER), str(ROOT), str(ROOT / 'src')]

import campaign_entry as entry
import execution
import namespace
import run_production_preparation as monitored

from humanvoice.artifacts import digest, read_json
from tools import durable_program_supervisor as durable
from tools.inventory_history_adoption import no_inference
from tools.validate_inventory_recovery_v3 import cleanup

OUTPUT = HERE / 'offline-20261108'
MANIFEST = OUTPUT / 'manifest.json'
WINDOW_END = execution.WINDOW_END
require = execution.require
MASTERS = tuple(ROOT / 'docs/plans' / name for name in
    ('humanvoice_master_program_v2.md', 'ENSEMBLE_MASTER_PROGRAM_2026-09-30.md'))


def inputs():
    return {'candidate': execution.MIGRATION / 'candidate-v2.json',
        'qualification': QUALIFICATION / 'qualification-verified.json',
        'protocol': execution.MIGRATION / 'protocol-result.json',
        'call_authorization': QUALIFICATION / 'call-authorization.json'}


def stable():
    value = read_json(MANIFEST)
    require(time.time() < WINDOW_END and not (OUTPUT / 'STOP').exists(), 'Offline campaign stopped or expired')
    require(all(digest(Path(path).read_bytes()) == checksum
        for path, checksum in value['immutable'].items()), 'Offline campaign source or input changed')
    require(monitored.authority() == value['authority'], 'Offline campaign changed spending or production cursor')
    return value['bindings']


def activation_record(candidate, evidence, protocol, references):
    state = read_json(QUALIFICATION / 'supervisor-status.json')
    require(state['status'] == 'CURRENT_CLIENT_QUALIFICATION_VERIFIED'
        and state['progress']['completed'] == state['progress']['allocated'] == 212
        and state['progress']['unresolved'] == 0 and state['progress']['terminal'] == 'pass'
        and state['cleanup']['complete'] and state['descendant_cleanup']['descendants_quiescent']
        and state['evidence'] == evidence, 'Campaign requires completed and cleaned-up qualification')
    profile = candidate['profiles'][candidate['original_routing_index']]
    execution.migration_policy.validate_fresh_evidence(evidence, profile)
    entry.migration_runtime.transition.protocol_evidence(candidate, protocol)
    return execution.identified({'version': entry.VERSION, 'status': 'QUALIFIED_PENDING_HOST_ADMISSION',
        'production_admitted': False, 'candidate_identity': candidate['identity'], 'inputs': references})


def activate():
    objects = {key: read_json(path) for key, path in inputs().items()}
    references = {key: {'path': str(path), 'sha256': digest(path.read_bytes())}
        for key, path in inputs().items()}
    candidate, evidence = objects['candidate'], objects['qualification']
    value = activation_record(candidate, evidence, objects['protocol'], references)
    profile = candidate['profiles'][candidate['original_routing_index']]
    with no_inference(), entry.campaign_context.scope(), execution.accounting.history_scope():
        require(execution.qualification.verify(evidence['output'], profile) == evidence,
            'Native qualification changed before campaign activation')
    stable()
    if entry.ACTIVATION.exists():
        require(read_json(entry.ACTIVATION) == value, 'Existing campaign activation differs')
    else:
        execution.migration.save_new(entry.ACTIVATION, value)
    entry.activation()
    return {'status': 'QUALIFIED_PENDING_HOST_ADMISSION', 'activation_identity': value['identity']}


def prepare(directory):
    active, objects = entry.activation()
    call = active['inputs']['call_authorization']
    extra = (entry.ACTIVATION, Path(entry.__file__),
        *(Path(row['path']) for key, row in active['inputs'].items() if key != 'call_authorization'))
    observer = monitored.Observer(directory, stable(), reader=stable)
    try:
        code = entry.preparation_adapter.prepare(objects['candidate'], objects['qualification'], objects['protocol'],
            authorization_path=Path(call['path']), authorization_sha256=call['sha256'],
            additional_sources=extra, progress=observer.completed_native)
        require(code == 0, 'Native migrated campaign preparation failed')
        observer.finish()
    finally:
        observer.chain.close()
    with entry.scope():
        sources = entry.preparation_adapter.review.sources()
    output = entry.preparation_adapter.review.OUTPUT / 'preparation' / digest(sources)[:20]
    record = read_json(output / 'preparation.json')
    require(record['status'] == 'OFFLINE_PREPARATION_PASS' and record['sources'] == sources,
        'Native preparation proof differs from projected sources')
    return {'status': 'OFFLINE_PREPARATION_PASS', 'output': str(output),
        'plan_identity': record['plan_identity'], 'transition_identity': record['transition_identity']}


def child(action, parent_network):
    require(os.geteuid() == 1000 and os.readlink('/proc/self/ns/net') != parent_network
        and os.statvfs(ROOT).f_flag & os.ST_RDONLY, 'Offline campaign lost read-only network isolation')
    stable()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('Native operation exceeded 880 seconds')))
    directory = OUTPUT / action
    # Native preparation resets this bound only after completed operations.
    signal.setitimer(signal.ITIMER_REAL, 880)
    try:
        with no_inference():
            result = activate() if action == 'activate' else prepare(directory) if action == 'prepare' else entry.derive()
        stable()
        execution.migration.save_new(directory / 'result.json', result)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def command(action, authority):
    args = ['/usr/bin/bwrap', '--unshare-user', '--unshare-net', '--die-with-parent', '--new-session',
        '--ro-bind', '/', '/', '--tmpfs', '/home', '--tmpfs', '/dev/shm']
    for path in (str(ROOT), '/home/ubuntu/.codex', '/home/ubuntu/.vscode', '/home/ubuntu/miniforge3'):
        args += ['--ro-bind', path, path]
    for path in [*namespace.writable_roots(authority), str(HERE)]:
        args += ['--bind', path, path]
    for source, target in namespace.mounts():
        args += ['--ro-bind', source, target]
    return [*args, '--chdir', str(ROOT), '--', execution.PYTHON, str(Path(__file__)),
        'inside-' + action, os.readlink('/proc/self/ns/net')]


def refresh(state):
    start, end = '<!-- qualified-campaign-20261108 -->', '<!-- end-qualified-campaign-20261108 -->'
    block = (start + '\nCurrent-client qualification PASS: 212 completed calls; no unresolved usage.\n'
        + 'Campaign continuation: ' + state['status'] + '; phase: ' + state['phase'] + '.\n'
        + 'Completed native preparation operations: ' + str(state.get('completed', [])) + '.\n'
        + ('Failure: ' + state['error'] + '.\n' if state.get('error') else '')
        + 'State: .localresources/session-campaign-current-20261108/offline-20261108/status.json.\n'
        + '16 workers; no provider calls; host admission and full ZLB remain pending.\n' + end)
    for path in MASTERS:
        original = path.read_text()
        require(original.count(start) == original.count(end) <= 1, 'Ambiguous campaign master checkpoint')
        if start in original:
            before, rest = original.split(start, 1)
            _, after = rest.split(end, 1)
            updated = before + block + after
        else:
            updated = block + '\n\n' + original
        temporary = path.with_name('.' + path.name + '.campaign-' + str(os.getpid()))
        with temporary.open('x') as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        require(path.read_text() == original, 'Master changed during campaign refresh')
        os.replace(temporary, path)


def run():
    authority, _prepared, _candidate, _plan, _extension = execution.approved_inputs()
    require(time.time() < WINDOW_END, 'Authorized execution window expired')
    with (HERE / 'offline.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not OUTPUT.exists(), 'Retain and diagnose prior offline campaign before retry')
        require(monitored.stopped_services()['production_stopped'], 'Production must be stopped for preparation')
        OUTPUT.mkdir()
        immutable = {str(p): digest(p.read_bytes()) for p in
            [*HERE.glob('*.py'), *inputs().values(), QUALIFICATION / 'supervisor-status.json']}
        immutable.update({str(ROOT / p): h for p, h in entry.preparation_adapter.dependencies().items()})
        immutable.update({str(ROOT / p): h for p, h in entry.preparation_adapter.review.sources().items()})
        observed = monitored.authority()
        bound = {'sources': immutable, 'authority': observed}
        execution.migration.save_new(MANIFEST, {'immutable': immutable, 'authority': observed,
            'bindings': bound, 'window_end': WINDOW_END, 'model_calls': 0, 'production_admitted': False})
        state = {'status': 'RUNNING', 'phase': 'activate', 'completed': [], 'model_calls': 0}
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Campaign continuation stopped')))
        try:
            for action in ('activate', 'prepare', 'configure'):
                stable()
                directory = OUTPUT / action
                directory.mkdir()
                started = time.monotonic()
                monitor = monitored.Monitor(directory, bound, started) if action == 'prepare' else None
                state.update(phase=action, completed=[], owner=durable.identity(os.getpid()))
                durable.save(OUTPUT / 'status.json', state)
                refresh(state)
                process = None
                try:
                    with (directory / 'execution.log').open('xb') as log:
                        process = subprocess.Popen(command(action, authority), cwd=ROOT, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                            env={**os.environ, 'HUMANVOICE_AUDIT_WORKERS': '16', 'OMP_NUM_THREADS': '1',
                                'OPENBLAS_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
                        state['child_owner'] = durable.identity(process.pid)
                        previous = []
                        while process.poll() is None:
                            stable()
                            if monitor:
                                monitor.read(time.monotonic())
                                completed = [r['label'] for r in monitor.rows]
                                if completed != previous:
                                    state['completed'] = previous = completed
                                    refresh(state)
                            else:
                                require(time.monotonic() - started < 890, 'Offline campaign phase exceeded deadline')
                            state['observed_at_utc'] = time.time()
                            durable.save(OUTPUT / 'status.json', state)
                            time.sleep(2)
                        require(process.returncode == 0, action + ' child failed; inspect execution.log')
                        require((directory / 'result.json').is_file(), 'Offline campaign lacks native result')
                        if monitor:
                            monitor.read(time.monotonic())
                            require(len(monitor.rows) == len(monitored.preparation.PHASES), 'Preparation omitted native phases')
                finally:
                    proof = cleanup(process) if process else {'complete': True}
                    durable.save(directory / 'cleanup.json', proof)
                    require(proof['complete'], 'Offline campaign process cleanup incomplete')
            stable()
            state.update(status='CAMPAIGN_PREPARED_CONFIGURATION_READY', phase='complete')
        except BaseException as error:  # noqa: BLE001 -- retain failure before returning
            state.update(status='STOPPED_FOR_DIAGNOSIS', error=type(error).__name__ + ': ' + str(error))
        state['observed_at_utc'] = time.time()
        durable.save(OUTPUT / 'status.json', state)
        refresh(state)
        print(json.dumps(state), flush=True)
        return 0 if state['status'] == 'CAMPAIGN_PREPARED_CONFIGURATION_READY' else 1


if __name__ == '__main__':
    require(sys.executable == execution.PYTHON, 'Fixed offline campaign interpreter required')
    if sys.argv[1:] == ['run']:
        raise SystemExit(run())
    require(len(sys.argv) == 3 and sys.argv[1] in {'inside-activate', 'inside-prepare', 'inside-configure'},
        'Fixed offline campaign actions only')
    child(sys.argv[1].removeprefix('inside-'), sys.argv[2])
