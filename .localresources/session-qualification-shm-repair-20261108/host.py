"""One authentication for actual service preflight and its conditional restart."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/home/ubuntu/workspace/humanvoice')
HERE = ROOT / '.localresources/session-qualification-shm-repair-20261108'
OUTPUT = ROOT / '.localresources/session-qualification-20261107/shm-repair-20261108'
PLAN = OUTPUT / 'plan.json'
OFFLINE = 'humanvoice-qualification-history-preflight-20261108.service'
LIVE = 'humanvoice-current-client-qualification-20261107.service'


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def show(unit):
    result = subprocess.run(['/usr/bin/systemctl', 'show', unit,
        '--property=ActiveState,MainPID,ControlPID,LoadState'], check=True,
        capture_output=True, text=True, timeout=15)
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def idle(unit):
    state = show(unit)
    return state.get('ActiveState') in {'inactive', 'failed'} and state.get('MainPID') == state.get('ControlPID') == '0'


def validate(value):
    require(value['action'] == 'preflight-and-resume-final-unspent-qualification'
        and value['additional_calls'] == 0 and value['prior_launches'] == 2
        and value['maximum_total_launches'] == 3 and value['total_call_ceiling'] == 2235
        and value['window_end'] == 1794158980 and time.time() < value['window_end'], 'Final restart scope changed')
    require(all(Path(p).is_relative_to(ROOT) and Path(p).resolve() == Path(p)
        and hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in value['sources'].items()),
        'Final repair source changed')
    for key, unit, mode in [('offline_command', OFFLINE, 'inside-preflight'), ('live_command', LIVE, 'run')]:
        cmd = value[key]
        boundary = cmd.index('--')
        require(cmd[0] == '/usr/bin/systemd-run' and '--unit=' + unit in cmd
            and {'--property=User=ubuntu', '--property=Group=ubuntu', '--property=NoNewPrivileges=yes',
                '--property=CapabilityBoundingSet=', '--property=ProtectSystem=strict',
                '--property=TemporaryFileSystem=/dev/shm:rw,nosuid,nodev,mode=1777'} <= set(cmd)
            and cmd[boundary + 1:boundary + 4] == ['/tmp/humanvoice-release-env-20261029/bin/python',
                str(HERE / 'repair.py'), mode], 'Final restart changed the fixed service command')
        require(('--property=PrivateNetwork=yes' in cmd) == (mode == 'inside-preflight'), 'Offline network changed')
    return value


def main():
    require(os.geteuid() == 0 and sys.executable == '/usr/bin/python3' and sys.flags.isolated
        and len(sys.argv) == 3 and sys.argv[1] == 'start', 'Fixed system host action only')
    raw = PLAN.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == sys.argv[2], 'Final repair packet changed')
    value = validate(json.loads(raw))
    require(idle(LIVE) and show(OFFLINE)['LoadState'] == 'not-found', 'Prior service still exists or runs')
    try:
        subprocess.run(value['offline_command'], check=True, timeout=1010)
    finally:
        if not idle(OFFLINE):
            subprocess.run(['/usr/bin/systemctl', 'stop', OFFLINE], check=True, timeout=30)
        require(idle(OFFLINE), 'Offline service cleanup incomplete')
        if show(OFFLINE).get('ActiveState') == 'failed':
            subprocess.run(['/usr/bin/systemctl', 'reset-failed', OFFLINE], check=True, timeout=15)
    proof = json.loads((OUTPUT / 'preflight.json').read_bytes())
    require(proof['status'] == 'SYSTEM_NATIVE_HISTORY_PASS' and proof['repair_identity'] == value['identity']
        and proof['model_calls'] == proof['account_writes'] == proof['grant_writes'] == 0,
        'Actual system-service preflight did not pass')
    validate(value)
    require(idle(LIVE), 'Live service acquired another owner')
    subprocess.run(['/usr/bin/systemctl', 'reset-failed', LIVE], check=True, timeout=15)
    subprocess.run(value['live_command'], check=True, timeout=30)


if __name__ == '__main__':
    main()
