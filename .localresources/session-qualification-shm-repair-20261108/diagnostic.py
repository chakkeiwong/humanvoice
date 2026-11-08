"""Unprivileged, network-isolated full grant replay before OS authentication."""

import json
import os
import subprocess
import sys

import repair

from tools.validate_inventory_recovery_v3 import cleanup


def inside(parent_network):
    repair.loopback.require_isolation(parent_network)
    repair.require(os.geteuid() == 1000 and os.statvfs(repair.ROOT).f_flag & os.ST_RDONLY,
        'Offline diagnostic requires unprivileged read-only inputs')
    value = repair.plan()
    authority = repair.read_json(repair.PREVIOUS / 'execution-authorization.json')
    repair.require(authority == repair.execution.identified(authority)
        and authority['identity'] == value['original_authorization'], 'Original authority changed')
    report = repair.check_accounting(authority)
    result = {'status': 'ISOLATED_GRANT_REPLAY_PASS', 'repair_identity': value['identity'],
        'model_calls': 0, 'account_writes': 0, 'grant_writes': 0, 'grant_status': report}
    repair.execution.migration.save_new(repair.OUTPUT / 'diagnostic.json', result)
    print(json.dumps(result))


def run():
    repair.plan()
    command = repair.receipt.preflight_command()
    command[-3:] = [str(repair.HERE / 'diagnostic.py'), 'inside', os.readlink('/proc/self/ns/net')]
    child = None
    code = None
    try:
        with (repair.OUTPUT / 'diagnostic.log').open('xb') as handle:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                stdout=handle, stderr=subprocess.STDOUT, start_new_session=True,
                env={**os.environ, 'HUMANVOICE_AUDIT_WORKERS': '16',
                    'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
            code = child.wait(timeout=900)
    finally:
        result = cleanup(child) if child is not None else {'complete': True}
        repair.durable.save(repair.OUTPUT / 'diagnostic-cleanup.json', result)
    repair.require(code == 0 and result['complete'], 'Grant diagnostic failed; inspect diagnostic.log')
    print(json.dumps(repair.read_json(repair.OUTPUT / 'diagnostic.json')))


if __name__ == '__main__':
    repair.require(sys.executable == repair.execution.PYTHON, 'Fixed diagnostic Python required')
    if sys.argv[1:] == ['run']:
        run()
    else:
        repair.require(len(sys.argv) == 3 and sys.argv[1] == 'inside', 'Fixed offline diagnostic actions only')
        inside(sys.argv[2])
