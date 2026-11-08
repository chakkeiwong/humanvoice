"""Bounded authenticated session for fixed, unprivileged offline probes.

Only the system Python standard library is imported by the privileged process.
The mount/environment scope is frozen once; workspace code runs as ubuntu.
"""

import base64
import copy
import fcntl
import hashlib
import json
import os
import re
import signal
import socket
import stat
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path('/home/ubuntu/workspace/humanvoice/.localresources/session-qualification-20261107')
ROOT = HERE.parents[1]
PYTHON = '/tmp/humanvoice-release-env-20261029/bin/python'
RUNTIME = Path('/run/humanvoice-offline-20261107')
SOCKET = RUNTIME / 'control.sock'
PACKET = HERE / 'offline-session.json'
KINDS = ('environment', 'protocol', 'signal')
MAX_BATCHES = 8
LIFETIME = 3600
EXECUTION_END = 1794158980
MAX_MESSAGE = 8 * 1024 * 1024


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_scope(value):
    require(set(value) == {'parent_network', 'environment', 'properties', 'helper_sha256'},
        'Unknown offline session scope')
    require(re.fullmatch(r'net:\[\d+\]', value['parent_network'])
        and re.fullmatch(r'[0-9a-f]{64}', value['helper_sha256']), 'Invalid session identity')
    allowed = {'HOME', 'CODEX_HOME', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
        'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
        'REQUESTS_CA_BUNDLE', 'CODEX_INTERNAL_ORIGINATOR_OVERRIDE', 'HUMANVOICE_AUDIT_WORKERS',
        'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'PYTHONDONTWRITEBYTECODE', 'TMPDIR', 'CODEX_SQLITE_HOME'}
    environment = value['environment']
    require(isinstance(environment, dict) and set(environment) <= allowed
        and all(isinstance(v, str) and not any(c in v for c in '\x00\r\n%') for v in environment.values())
        and environment.get('HOME') == '/home/ubuntu'
        and environment.get('CODEX_HOME', '/home/ubuntu/.codex') == '/home/ubuntu/.codex'
        and environment.get('TMPDIR') == str(HERE / 'scratch')
        and environment.get('CODEX_SQLITE_HOME') == str(HERE / 'scratch/client-state/sqlite'),
        'Offline session changed its credential or runtime environment')
    values = value['properties']
    require(isinstance(values, list) and all(isinstance(p, str) and '=' in p
        and not any(c in p for c in '\x00\r\n%') for p in values), 'Invalid service properties')
    properties = dict(p.split('=', 1) for p in values)
    fixed = {'User': 'ubuntu', 'Group': 'ubuntu', 'PrivateUsers': 'no', 'PrivateMounts': 'yes',
        'PrivateNetwork': 'yes', 'ProtectSystem': 'strict', 'ProtectHome': 'tmpfs',
        'NoNewPrivileges': 'yes', 'CapabilityBoundingSet': '', 'RestrictSUIDSGID': 'yes',
        'ReadOnlyPaths': str(ROOT) + ' /home/ubuntu/.codex',
        'ReadWritePaths': ' '.join(str(p) for p in (HERE, ROOT / '.localresources/automatic-program',
            ROOT / 'docs/audits/2026-10-05/master-program/automatic-execution', ROOT / 'docs/plans')),
        'BindPaths': ' '.join(str(HERE / 'scratch/client-state' / name) + ':/home/ubuntu/.codex/' + name
            for name in ('tmp', 'installation_id')),
        'TemporaryFileSystem': '/dev/shm:rw,nosuid,nodev'}
    require(len(properties) == len(values) and set(properties) == set(fixed) | {'BindReadOnlyPaths'}
        and all(properties[key] == expected for key, expected in fixed.items()),
        'Offline session broadened its user, network, mount or writable scope')
    bindings = properties['BindReadOnlyPaths'].split()
    support = [str(ROOT), '/home/ubuntu/.codex', '/home/ubuntu/.vscode', '/home/ubuntu/miniforge3']
    require(len(bindings) == 33 and bindings[:4] == [p + ':' + p + ':norbind' for p in support],
        'Offline session changed its support/archive membership')
    for binding in bindings[4:]:
        pair = binding.split(':')
        require(len(pair) == 2 and all(p.startswith('/') and '..' not in Path(p).parts
            and not any(c in p for c in '\t"\\') for p in pair), 'Invalid archive binding')
    return value


def command(kind, scope, unit):
    require(kind in KINDS, 'Unknown fixed offline probe')
    properties = list(scope['properties'])
    if kind == 'protocol':
        dummy = str(HERE / 'scratch/dummy-auth.json') + ':/home/ubuntu/.codex/auth.json'
        properties = [p + ' ' + dummy if p.startswith('BindReadOnlyPaths=') else p for p in properties]
    return ['/usr/bin/systemd-run', '--quiet', '--wait', '--pipe', '--unit=' + unit,
        '--service-type=exec', '--property=RuntimeMaxSec=75', '--property=TimeoutStopSec=10',
        '--property=KillMode=control-group', '--working-directory=' + str(ROOT),
        *['--property=' + p for p in properties],
        *['--setenv=' + key + '=' + val for key, val in sorted(scope['environment'].items())],
        '--', PYTHON, str(HERE / 'namespace_probe.py'), kind, scope['parent_network']]


def show(unit):
    result = subprocess.run(['/usr/bin/systemctl', 'show', unit,
        ('--property=LoadState,ActiveState,MainPID,ControlPID,ExecMainCode,ExecMainStatus,Result,'
        'ProtectSystem,ProtectHome,ReadOnlyPaths,ReadWritePaths,PrivateMounts,PrivateUsers,BindReadOnlyPaths,'
        'ExecStart,User,Group,CapabilityBoundingSet')],
        capture_output=True, text=True, timeout=15, check=False)
    require(result.returncode in {0, 4}, 'Cannot inspect the exact offline probe service')
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def run_probe(kind, scope):
    unit = 'humanvoice-qualification-offline-' + kind + '-' + uuid.uuid4().hex + '.service'
    require(show(unit).get('LoadState') == 'not-found', 'Offline service name already exists')
    child = subprocess.Popen(command(kind, scope, unit), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
    try:
        stdout, stderr = child.communicate(timeout=100)
    finally:
        # Reap the launcher even if systemctl inspection/cleanup itself fails.
        try:
            terminal = show(unit)
            if terminal.get('ActiveState') not in {'inactive', 'failed'} or terminal.get('MainPID') != '0':
                subprocess.run(['/usr/bin/systemctl', 'stop', unit], check=True, timeout=20,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=15)
        if show(unit).get('ActiveState') == 'failed':
            subprocess.run(['/usr/bin/systemctl', 'reset-failed', unit], check=True, timeout=15,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        observed = show(unit)
        require(observed.get('ActiveState') in {'inactive', 'failed'}
            and observed.get('MainPID') == observed.get('ControlPID') == '0',
            'Offline system probe did not clean its exact service')
    require(len(stdout) + len(stderr) <= 2 * 1024 * 1024, 'Offline probe output exceeds its bound')
    return {'returncode': child.returncode, 'terminal_service': terminal,
        'stdout': base64.b64encode(stdout).decode(), 'stderr': base64.b64encode(stderr).decode(),
        'cleanup': {'complete': True, 'service': unit, 'observed': observed}}


class Session:
    def __init__(self, scope, lifetime):
        self.scope = copy.deepcopy(validate_scope(scope))
        self.identity = identity(self.scope)
        self.deadline = time.monotonic() + min(lifetime, LIFETIME)
        self.expires_at = time.time() + min(lifetime, LIFETIME)
        self.used = 0
        self.closed = False

    def handle(self, request, uid):
        require(uid == 1000, 'Only the authenticated ubuntu user may use this session')
        require(set(request) == {'action', 'scope_sha256'} and request['scope_sha256'] == self.identity,
            'Offline session scope changed; a new reviewed session is required')
        require(not self.closed and time.monotonic() < self.deadline, 'Offline session expired or closed')
        action = request['action']
        require(action in {'check', 'status', 'close'}, 'Unknown offline session action')
        if action == 'close':
            self.closed = True
        result = {'scope_sha256': self.identity, 'expires_at': self.expires_at,
            'batches_used': self.used, 'max_batches': MAX_BATCHES, 'closed': self.closed}
        if action == 'check':
            require(self.used < MAX_BATCHES and self.deadline - time.monotonic() >= 330,
                'Offline session exhausted or too close to expiry for another batch')
            self.used += 1  # Failed attempts also consume a bounded slot.
            result['batches_used'] = self.used
            result['reports'] = {kind: run_probe(kind, self.scope) for kind in KINDS}
        return result


def receive(connection, limit):
    data = bytearray()
    while not data.endswith(b'\n'):
        part = connection.recv(min(65536, limit + 1 - len(data)))
        require(part, 'Offline session peer disconnected')
        data.extend(part)
        require(len(data) <= limit, 'Offline session message exceeds its bound')
    return json.loads(data)


def peer_uid(connection):
    return struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]


def request(action, scope):
    """Unprivileged client; never starts pkexec or silently renews a session."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(340)
        connection.connect(str(SOCKET))
        require(peer_uid(connection) == 0, 'Offline session server is not root-owned')
        connection.sendall(json.dumps({'action': action, 'scope_sha256': identity(scope)}).encode() + b'\n')
        result = receive(connection, MAX_MESSAGE)
        require(result.get('ok') is True, result.get('error', 'Invalid offline session response'))
        return result['result']


def serve(scope):
    lifetime = min(LIFETIME, EXECUTION_END - time.time())
    require(lifetime >= 330, 'Execution window is too close to expiry')
    state = Session(scope, lifetime)
    RUNTIME.mkdir(mode=0o755, exist_ok=True)
    info = RUNTIME.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and info.st_mode & 0o022 == 0,
        'Offline session runtime directory is not protected')
    fd = os.open(RUNTIME / 'owner.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as owner, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if SOCKET.exists():
            info = SOCKET.lstat()
            require(stat.S_ISSOCK(info.st_mode) and info.st_uid == 1000, 'Unexpected session socket')
            SOCKET.unlink()
        listener.bind(str(SOCKET))
        os.chown(SOCKET, 1000, 1000)
        os.chmod(SOCKET, 0o600)
        listener.listen(1)
        listener.settimeout(1)
        signal.setitimer(signal.ITIMER_REAL, lifetime)
        print(json.dumps({'status': 'OFFLINE_SESSION_READY', 'scope_sha256': state.identity,
            'expires_at': state.expires_at, 'max_batches': MAX_BATCHES}), flush=True)
        try:
            while not state.closed and time.monotonic() < state.deadline:
                try:
                    connection, _address = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    connection.settimeout(10)
                    try:
                        result = state.handle(receive(connection, 4096), peer_uid(connection))
                        response = {'ok': True, 'result': result}
                    except (ValueError, OSError, subprocess.SubprocessError) as error:
                        response = {'ok': False, 'error': type(error).__name__ + ': ' + str(error)}
                    try:
                        connection.sendall(json.dumps(response).encode() + b'\n')
                    except OSError:
                        state.closed = True
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            SOCKET.unlink(missing_ok=True)


def main():
    require(os.geteuid() == 0 and sys.executable == '/usr/bin/python3'
        and sys.flags.isolated and len(sys.argv) == 3 and sys.argv[1] == 'serve',
        'Only the isolated system-Python offline session is supported')
    fd = os.open(PACKET, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        raw = handle.read(65537)
    require(len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == sys.argv[2],
        'Reviewed offline session packet changed')
    scope = validate_scope(json.loads(raw))
    require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == scope['helper_sha256'],
        'Reviewed privileged helper changed')
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(signum, lambda *_args: sys.exit(1))
    serve(scope)


if __name__ == '__main__':
    main()
