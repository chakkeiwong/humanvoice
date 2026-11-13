"""Compare actual installed-client requests in an isolated loopback namespace."""
import argparse
import json
import os
import shutil
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]

from tools import probe_active_client_loopback as probe
from tools import response_capture_observation as capture


class Handler(probe.Handler):
    def do_POST(self):
        import io
        length = int(self.headers.get('Content-Length', '-1'))
        if not 0 < length <= probe.MAX_CAPTURE:
            self.reply(400, b'{}', 'application/json')
            return
        raw = self.rfile.read(length)
        self.server.payloads.append(json.loads(raw))
        self.rfile = io.BytesIO(raw)
        super().do_POST()


def inside(parent_network):
    import fcntl
    from http.server import ThreadingHTTPServer

    isolation = probe.require_isolation(parent_network)
    clients = json.loads((HERE / 'client-inputs.json').read_text())
    observed = {}
    for name in ('old', 'new'):
        executable = clients[name + '_executable']
        if probe.file_hash(executable) != clients[name + '_sha256']:
            raise ValueError('Installed client changed')
        directory = Path('/work/capture')
        directory.mkdir()
        home = Path(os.environ['CODEX_HOME'])
        home.mkdir(parents=True, exist_ok=True)
        (home / 'auth.json').write_text(json.dumps({'OPENAI_API_KEY': probe.DUMMY_KEY}))
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.model, server.effort, server.case = 'gpt-6-astra', 'xhigh', 'capture_success'
        server.observations, server.payloads, server.guard = [], [], threading.Lock()
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            args = probe.native_command(executable, directory,
                f'http://127.0.0.1:{server.server_port}/v1', server.model, server.effort)
            with (directory / 'owner.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = capture.launch(args, 'Return exactly the empty concept array.', directory,
                                        lock_fd=lock.fileno(), deadline=30)
            events = probe.prospective_event_summary(directory)
            observed[name] = {'process': result, 'events': events, 'requests': server.observations,
                              'payloads': server.payloads}
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
        directory.rename(Path('/work') / name)
        shutil.rmtree(Path('/work/home'))
    print(json.dumps({'isolation': isolation, 'observed': observed, 'provider_calls': 0,
                      'real_credentials': False}), flush=True)


def main():
    import subprocess

    parser = argparse.ArgumentParser()
    parser.add_argument('--inside', action='store_true')
    parser.add_argument('--parent-network')
    args = parser.parse_args()
    if args.inside:
        return inside(args.parent_network)
    clients = json.loads((HERE / 'client-inputs.json').read_text())
    command = probe.namespace_command(clients['new_executable'], os.readlink('/proc/self/ns/net'),
                                      'gpt-6-astra', 'xhigh', 30, ())
    position = command.index(sys.executable)
    command[position:position] = ['--ro-bind', str(HERE), str(HERE), '--ro-bind',
        str(Path(clients['old_executable']).parent), str(Path(clients['old_executable']).parent)]
    position = command.index(sys.executable)
    command[position:] = [sys.executable, '-I', str(Path(__file__)), '--inside',
                          '--parent-network', os.readlink('/proc/self/ns/net')]
    result = subprocess.run(command, capture_output=True, text=True, timeout=100, check=False)
    (HERE / 'wire-probe.stdout').write_text(result.stdout)
    (HERE / 'wire-probe.stderr').write_text(result.stderr)
    if result.returncode:
        raise ValueError('Local wire probe failed: ' + result.stderr[-1500:])
    value = json.loads(result.stdout)
    (HERE / 'wire-probe.json').write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({k: {'status': v['process']['status'], 'events': v['events'],
                         'request_count': len(v['payloads'])} for k, v in value['observed'].items()}), flush=True)


if __name__ == '__main__':
    main()
