"""Prepare and submit the exact already-authorized, unspent qualification repair."""

import json
import subprocess
import sys
import time
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPAIR = ROOT / '.localresources/session-qualification-resume-20261108'
PREVIOUS = ROOT / '.localresources/session-qualification-20261107'
sys.path[:0] = [str(REPAIR), str(PREVIOUS), str(ROOT), str(ROOT / 'src')]

import execution
import launch
import repair
import supervise

from humanvoice.artifacts import digest, read_json

PACKET = repair.OUTPUT / 'resume-host.json'
require = execution.require


def inputs():
    value = repair.plan()
    proof = read_json(repair.OUTPUT / 'preflight.json')
    require(proof['status'] == 'NATIVE_HISTORY_PREFLIGHT_PASS'
        and proof['repair_identity'] == value['identity'] and proof['sources'] == value['sources']
        and proof['model_calls'] == proof['account_writes'] == proof['grant_writes'] == 0
        and read_json(repair.OUTPUT / 'preflight-cleanup.json')['complete'],
        'Resume requires the completed full native-history preflight')
    cases = list(ElementTree.parse(REPAIR / 'tests-workers.xml').getroot().iter('testcase'))
    require(len(cases) == 16 and not any(item.tag in {'failure', 'error', 'skipped'}
        for case in cases for item in case), 'Repair regression evidence is incomplete')
    authority, prepared, _candidate, _plan, _addition = execution.approved_inputs()
    require(authority['identity'] == value['original_authorization'], 'Original approval changed')
    state, failure = (read_json(PREVIOUS / name) for name in ('supervisor-status.json', 'execution-failure.json'))
    require(state == value['prior_status'] and failure == value['prior_failure'], 'Stopped evidence changed')
    repair.check_unspent(state, failure, supervise.inspect_progress(prepared['output']))
    return value, authority


def command(authority):
    # Preserve the already approved mount, network, budget and supervisor unit.
    result = launch.service_command(authority, now=time.time())[1:]
    require(result[-3:] == [execution.PYTHON, str(PREVIOUS / 'supervise.py'), 'run'],
        'Original service command changed')
    return [*result[:-3], execution.PYTHON, str(REPAIR / 'repair.py'), 'run']


def prepare():
    value, authority = inputs()
    files = [*HERE.glob('*.py'), REPAIR / 'tests-workers.xml', repair.PLAN,
        repair.OUTPUT / 'preflight.json', repair.OUTPUT / 'preflight-cleanup.json',
        PREVIOUS / 'supervisor-status.json', PREVIOUS / 'execution-failure.json']
    packet = {'action': 'resume-exact-unspent-qualification', 'repair_identity': value['identity'],
        'original_authorization': authority['identity'], 'unit': supervise.UNIT,
        'command': command(authority), 'window_end': execution.WINDOW_END,
        'sources': {str(p): digest(p.read_bytes()) for p in sorted(files)},
        'additional_calls': 0, 'total_call_ceiling': 2235,
        'prior_launches': 1, 'maximum_total_launches': 3}
    execution.migration.save_new(PACKET, packet)
    print(json.dumps({'status': 'RESUME_REVIEW_PREPARED', 'repair_identity': value['identity'],
        'packet_sha256': digest(PACKET.read_bytes()), 'extra_calls': 0}))


def start():
    value, authority = inputs()
    packet = read_json(PACKET)
    require(packet['repair_identity'] == value['identity']
        and packet['original_authorization'] == authority['identity']
        and all(digest(Path(path).read_bytes()) == checksum for path, checksum in packet['sources'].items()),
        'Prepared restart lost its reviewed evidence')
    require(time.time() < packet['window_end'], 'Approved execution window expired')
    subprocess.run(['/usr/bin/pkexec', '/usr/bin/python3', '-I', '-B', str(HERE / 'host.py'),
        'start', digest(PACKET.read_bytes())], check=True, timeout=180)
    print(json.dumps({'status': 'REPAIRED_QUALIFICATION_SUBMITTED', 'extra_calls': 0, 'unit': supervise.UNIT}))


if __name__ == '__main__':
    require(sys.executable == execution.PYTHON and len(sys.argv) == 2
        and sys.argv[1] in {'prepare', 'start'}, 'Only fixed reviewed restart actions are supported')
    (prepare if sys.argv[1] == 'prepare' else start)()
