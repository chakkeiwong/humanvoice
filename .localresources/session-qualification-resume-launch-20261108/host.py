"""Reset one stopped transient service and submit its reviewed repair command."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/home/ubuntu/workspace/humanvoice')
PACKET = ROOT / '.localresources/session-qualification-20261107/repair-20261108/resume-host.json'
UNIT = 'humanvoice-current-client-qualification-20261107.service'
PYTHON = '/tmp/humanvoice-release-env-20261029/bin/python'
SCRIPT = ROOT / '.localresources/session-qualification-resume-20261108/repair.py'


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def validate(packet):
    require(packet['action'] == 'resume-exact-unspent-qualification' and packet['unit'] == UNIT
        and packet['additional_calls'] == 0 and packet['total_call_ceiling'] == 2235
        and packet['prior_launches'] == 1 and packet['maximum_total_launches'] == 3
        and packet['window_end'] == 1794158980 and time.time() < packet['window_end'],
        'Restart scope or execution window changed')
    command = packet['command']
    require(command[:2] == ['/usr/bin/systemd-run', '--unit=' + UNIT]
        and command[-4:] == ['--', PYTHON, str(SCRIPT), 'run']
        and {'--no-block', '--property=User=ubuntu', '--property=Group=ubuntu',
            '--property=NoNewPrivileges=yes', '--property=CapabilityBoundingSet=',
            '--property=ProtectSystem=strict', '--property=ProtectHome=tmpfs',
            '--property=KillMode=control-group', '--property=RestartPreventExitStatus=2'} <= set(command),
        'Restart changed the exact unprivileged service')
    require(all(Path(path).is_relative_to(ROOT) and Path(path).resolve() == Path(path)
        and hashlib.sha256(Path(path).read_bytes()).hexdigest() == checksum
        for path, checksum in packet['sources'].items()), 'Reviewed restart source changed')
    return command


def main():
    require(os.geteuid() == 0 and sys.executable == '/usr/bin/python3' and sys.flags.isolated
        and len(sys.argv) == 3 and sys.argv[1] == 'start', 'Fixed isolated host restart only')
    raw = PACKET.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == sys.argv[2], 'Reviewed restart packet changed')
    command = validate(json.loads(raw))
    result = subprocess.run(['/usr/bin/systemctl', 'show', UNIT,
        '--property=ActiveState,MainPID,ControlPID'], capture_output=True, text=True, check=True, timeout=15)
    observed = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    require(observed.get('ActiveState') in {'failed', 'inactive'}
        and observed.get('MainPID') == observed.get('ControlPID') == '0', 'Prior service is still owned')
    subprocess.run(['/usr/bin/systemctl', 'reset-failed', UNIT], check=True, timeout=15)
    subprocess.run(command, check=True, timeout=30)


if __name__ == '__main__':
    main()
