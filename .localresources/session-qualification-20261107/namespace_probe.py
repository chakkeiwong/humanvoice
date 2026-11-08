"""Check the qualification mount view and installed client without remote access."""

import base64
import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MIGRATION = ROOT / '.localresources/session-migration-20261107'
sys.path[:0] = [str(HERE), str(MIGRATION), str(ROOT), str(ROOT / 'src')]

import client_protocol
import execution
import namespace
import system_probe

from humanvoice.artifacts import digest, read_json
from tools import probe_active_client_loopback as loopback
from tools import response_capture_observation as capture

require = execution.require
PROPOSAL = MIGRATION / 'budget-proposal.json'


def server_observation(binding):
    process = Path('/proc') / str(binding['server']['pid'])
    observed = {'exists': process.exists(), 'uid': os.getuid(),
        'user_namespace': os.readlink('/proc/self/ns/user')}
    for name in ('stat', 'exe'):
        try:
            observed[name] = (process.joinpath(name).read_text().split()[21]
                if name == 'stat' else os.readlink(process / name))
        except OSError as error:
            observed[name] = type(error).__name__ + ': ' + str(error)
    return observed


def diagnose_startup(binding):
    # This is called only inside the already verified loopback-only namespace.
    # Trace filenames/open modes, never request bodies or credential contents.
    directory = HERE / 'scratch'
    arguments = ['/usr/bin/strace', '-f', '-tt', '-e',
        'trace=%file,fcntl,flock,connect,poll,ppoll,epoll_wait,futex', '-o',
        str(directory / 'config-startup.trace'), binding['server']['executable'],
        *binding['server']['overrides'], 'app-server', '--stdio']
    message = {'id': 1, 'method': 'initialize', 'params': {
        'clientInfo': {'name': 'humanvoice_parity', 'version': '1'},
        'capabilities': {'experimentalApi': True}}}
    with (directory / 'config-startup.stderr').open('xb') as errors:
        child = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=errors, start_new_session=True)
        try:
            child.communicate(json.dumps(message).encode() + b'\n', timeout=20)
        except subprocess.TimeoutExpired:
            pass
        finally:
            # Reap strace and its traced client, preserving the original failure.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.communicate(timeout=5)


def inputs():
    proposal = read_json(PROPOSAL)
    extension = proposal['extension']
    grant = read_json(extension['grant'])
    value = {'grant': extension['grant'], 'account': grant['account']}
    value['writable_roots'] = [str(HERE), str(Path(value['account']).parent),
        str(Path(value['grant']).parent), str(ROOT / 'docs/plans')]
    return value


def scope(parent_network=None, environment=None, *, groups=None):
    # Preparation may run inside the command sandbox. Freeze the bound host
    # server's network identity, not the preparer's temporary network namespace.
    if parent_network is None:
        candidate = read_json(MIGRATION / 'candidate-v2.json')
        pid = candidate['current_binding']['server']['pid']
        parent_network = os.readlink('/proc/' + str(pid) + '/ns/net')
    return {'parent_network': parent_network,
        'environment': namespace.environment() if environment is None else environment,
        'properties': namespace.properties(inputs(), isolated_network=True, groups=groups),
        'helper_sha256': digest((HERE / 'system_probe.py').read_bytes())}


def command(kind, parent_network, environment, unit, *, groups=None):
    require(kind in {'environment', 'protocol', 'signal'}, 'Unknown fixed namespace probe')
    return system_probe.command(kind, scope(parent_network, environment, groups=groups), unit)


def inside(kind, parent_network):
    isolation = loopback.require_isolation(parent_network)
    if kind == 'signal':
        os.kill(os.getpid(), signal.SIGKILL)
        raise AssertionError('SIGKILL returned')
    candidate = read_json(MIGRATION / 'candidate-v2.json')
    binding = candidate['current_binding']
    print(json.dumps({'mount_readonly': {str(path): bool(os.statvfs(path).f_flag & os.ST_RDONLY)
        for path in (ROOT, Path(binding['credentials']['path']).parent)},
        'uid': os.getuid(), 'pid': os.getpid(),
        'mountinfo': [line for line in Path('/proc/self/mountinfo').read_text().splitlines()
            if line.split()[4] in {'/', '/home', str(ROOT), '/home/ubuntu/.codex',
                '/run/systemd/unit-root', '/run/systemd/unit-root' + str(ROOT)}],
        'namespaces': {name: os.readlink('/proc/self/ns/' + name) for name in ('mnt', 'user', 'pid')},
        'capabilities': [line for line in Path('/proc/self/status').read_text().splitlines()
            if line.startswith(('Cap', 'NoNewPrivs'))]}), file=sys.stderr)
    require(digest(Path(binding['server']['executable']).read_bytes()) == binding['executable_sha256'],
        'Namespace probe client changed')
    require(os.statvfs(ROOT).f_flag & os.ST_RDONLY
        and os.statvfs(Path(binding['credentials']['path']).parent).f_flag & os.ST_RDONLY,
        'Qualification probe lost the read-only workspace or client home')
    authority = inputs()
    require(all(not os.statvfs(path).f_flag & os.ST_RDONLY for path in authority['writable_roots']),
        'Qualification namespace lost its reviewed write roots')
    namespace.validate_client_state()
    if kind == 'environment':
        # Native config/read has no inference request and must function with
        # the exact current credentials/environment and a read-only client home.
        try:
            execution.migration.settings.verify(binding)
        except (OSError, ValueError):
            print(json.dumps({'bound_server_observation': server_observation(binding)}), file=sys.stderr)
            try:
                diagnose_startup(binding)
            except (OSError, subprocess.SubprocessError) as error:
                print('Startup diagnostic failed: ' + str(error), file=sys.stderr)
            raise
        namespace.validate_environment(authority)
        prepared = read_json(HERE / 'prepared.json')
        plan = read_json(Path(prepared['output']) / 'plan.json')
        execution.qualification.validate_plan(plan, plan['profile'])
        execution.control.require_running()
        return {'status': 'NAMESPACE_ENVIRONMENT_PASS', 'isolation': isolation,
            'candidate_identity': candidate['identity'], 'model_calls': 0, 'account_writes': 0}
    require(read_json(binding['credentials']['path']) == {'OPENAI_API_KEY': loopback.DUMMY_KEY},
        'Read-only client probe must see only synthetic credentials')
    profile = candidate['profiles'][candidate['original_routing_index']]
    model, effort = profile['model']['version_string'], profile['sampling']['reasoning_effort']
    directory = HERE / 'scratch/readonly-client'
    directory.mkdir()
    server = loopback.Gateway('retry_then_success', model, effort)
    server.case = 'capture_success'
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        arguments = loopback.native_command(binding['server']['executable'], directory,
            'http://127.0.0.1:' + str(server.server_port) + '/v1', model, effort)
        with (directory / 'owner.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = capture.launch(arguments, 'Return exactly the empty concept array.',
                directory, lock_fd=lock.fileno(), deadline=30)
        observed = {'status': 'pass', 'isolation': isolation, 'process': result,
            'events': loopback.prospective_event_summary(directory), 'requests': server.observations,
            'provider_calls': 0, 'real_credentials': False}
        client_protocol.validate_observation(observed)
        require(read_json(directory / 'response-envelope.json') == {'result': []},
            'Read-only client probe changed the exact synthetic response')
        return {'status': 'NAMESPACE_READONLY_CLIENT_PASS', 'observation': observed,
            'model_calls': 0, 'account_writes': 0}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def inspect():
    candidate = client_protocol.candidate()
    proposal = read_json(PROPOSAL)
    before = {path: digest(Path(path).read_bytes()) for path in proposal['authority_sha256']}
    parent_network = os.readlink('/proc/self/ns/net')
    scratch = HERE / 'scratch'
    scratch.mkdir(exist_ok=True)
    namespace.prepare_archive_receipt()
    namespace.prepare_client_state()
    dummy = scratch / 'dummy-auth.json'
    with dummy.open('x') as stream:
        json.dump({'OPENAI_API_KEY': loopback.DUMMY_KEY}, stream)
    packet = {'parent_network': parent_network, 'environment': namespace.environment(),
        'sources': {str(path): digest(path.read_bytes()) for path in sorted(HERE.glob('*.py'))}}
    path = scratch / 'system-probe-input.json'
    execution.migration.save_new(path, packet)
    # This path never authenticates or renews; scope drift fails before launch.
    result = system_probe.request('check', scope(parent_network, packet['environment']))
    execution.migration.save_new(scratch / 'system-session-result.json', result)
    require(packet['sources'] == {str(p): digest(p.read_bytes()) for p in sorted(HERE.glob('*.py'))},
        'Offline probe sources changed during execution')
    records = result['reports']
    require(set(records) == {'environment', 'protocol', 'signal'}, 'System probe lost its exact case membership')
    observations = {}
    for kind in ('environment', 'protocol', 'signal'):
        record = records[kind]
        stdout, stderr = (base64.b64decode(record[name], validate=True) for name in ('stdout', 'stderr'))
        cleaned = record['cleanup']
        execution.migration.save_new(scratch / (kind + '-cleanup.json'), cleaned)
        require(cleaned['complete'], 'Qualification namespace probe left an active service')
        for name, raw in (('stdout', stdout), ('stderr', stderr)):
            with (scratch / (kind + '.' + name)).open('xb') as stream:
                stream.write(raw)
        if kind == 'signal':
            observed = record['terminal_service']
            require(record['returncode'] == 255 and observed.get('ExecMainCode') == '2'
                and observed.get('ExecMainStatus') == str(signal.SIGKILL),
                'Qualification service did not report the exact killed-child status')
            observations[kind] = {'returncode': record['returncode'],
                'terminal_service': observed, 'cleanup': cleaned}
        else:
            require(record['returncode'] == 0,
                'Qualification namespace ' + kind + ' probe failed; stderr_sha256=' + digest(stderr))
            observations[kind] = json.loads(stdout)
    require(before == {path: digest(Path(path).read_bytes()) for path in before},
        'No-call namespace probe changed account authority')
    execution.migration.settings.verify(candidate['current_binding'])
    return {'status': 'QUALIFICATION_NAMESPACE_PASS', 'observations': observations,
        'candidate_identity': candidate['identity'], 'model_calls': 0,
        'external_calls': 0, 'account_writes': 0, 'grant_writes': 0}


if __name__ == '__main__':
    require(sys.executable == execution.PYTHON and len(sys.argv) == 3
        and sys.argv[1] in {'environment', 'protocol', 'signal'}, 'Only fixed internal namespace probes are supported')
    print(json.dumps(inside(sys.argv[1], sys.argv[2])))
