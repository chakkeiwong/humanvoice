"""Fixed host-only native migration test followed by the isolated client probe."""

import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MIGRATION = ROOT / '.localresources/session-migration-20261107'
sys.path[:0] = [str(MIGRATION), str(ROOT), str(ROOT / 'src')]

import binding_migration as binding
import client_protocol
import namespace_probe
import run_offline
import system_probe
from client_transition import protocol_evidence

from humanvoice.artifacts import digest, read_json
from tools import durable_program_supervisor as durable
from tools.validate_inventory_recovery_v3 import cleanup

PYTHON = run_offline.PYTHON
EVIDENCE = run_offline.EVIDENCE / 'client-migration-native-20261107.xml'
require = binding.require


def components():
    status = read_json(MIGRATION / 'offline-tests-status.json')
    require(status.get('status') == 'PASS' and status['cleanup']['complete'] is True
        and status['sources'] == run_offline.sources(status['sources'])
        and digest(Path(status['junit']).read_bytes()) == status['junit_sha256'],
        'Host migration checks require current passing component tests and cleanup')
    report = ElementTree.parse(status['junit']).getroot()
    cases = list(report.iter('testcase'))
    require(len(cases) >= 100 and not any(item.tag in {'failure', 'error', 'skipped'}
        for case in cases for item in case),
        'Migration component evidence contains a failed or missing test')
    return status


def additional_components():
    status = read_json(HERE / 'additional-tests-status.json')
    require(status.get('status') == 'PASS' and status.get('cleanup', {}).get('complete') is True
        and all(digest(Path(path).read_bytes()) == value for path, value in status['sources'].items())
        and digest(Path(status['junit']).read_bytes()) == status['junit_sha256'],
        'Host checks require completed current qualification/campaign tests and free workers')
    cases = list(ElementTree.parse(status['junit']).getroot().iter('testcase'))
    require(len(cases) >= 17 and not any(item.tag in {'failure', 'error', 'skipped'}
        for case in cases for item in case), 'Qualification/campaign tests are incomplete')
    return status


def validate_native(record, sources):
    require(record.get('status') == 'NATIVE_MIGRATION_PASS'
        and record.get('sources') == sources
        and record.get('cleanup', {}).get('complete') is True
        and record.get('native_junit') == str(EVIDENCE)
        and digest(EVIDENCE.read_bytes()) == record.get('native_junit_sha256'),
        'Retained native integration lost its exact source, result or cleanup')
    cases = list(ElementTree.parse(EVIDENCE).getroot().iter('testcase'))
    require(len(cases) == 1 and not any(item.tag in {'failure', 'error', 'skipped'}
        for case in cases for item in case), 'Retained native integration did not pass')
    return record


def native_integration(tested):
    before = run_offline.sources(tested['sources'])
    checkpoint = HERE / 'native-pass.json'
    if checkpoint.exists():
        return validate_native(read_json(checkpoint), before)
    require(not EVIDENCE.exists(), 'Retain previous native test results before a new attempt')
    environment = {**os.environ, 'HUMANVOICE_AUDIT_WORKERS': '16',
        'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
    command = [PYTHON, '-m', 'pytest', '-q', '--timeout=900', '--junitxml=' + str(EVIDENCE),
        str(MIGRATION / 'test_migration_native.py')]
    process = subprocess.Popen(command, cwd=ROOT, env=environment, start_new_session=True)
    try:
        code = process.wait(timeout=920)
    finally:
        cleaned = cleanup(process)
        durable.save(HERE / 'native-cleanup.json', cleaned)
        require(cleaned['complete'], 'Native migration integration left owned processes')
    require(code == 0, 'Native migration integration failed')
    require(before == run_offline.sources(before), 'Migration sources changed during native integration')
    record = {'status': 'NATIVE_MIGRATION_PASS', 'sources': before,
        'native_junit': str(EVIDENCE), 'native_junit_sha256': digest(EVIDENCE.read_bytes()),
        'cleanup': cleaned}
    validate_native(record, before)
    binding.save_new(checkpoint, record)
    return record


def checked_protocol(candidate):
    path = MIGRATION / 'protocol-result.json'
    if path.exists():
        observation = protocol_evidence(candidate, read_json(path))
        require(observation['sources'] == client_protocol.source_hashes(),
            'Retained client protocol sources changed')
        return observation
    observation = client_protocol.inspect(candidate)
    protocol_evidence(candidate, observation)
    binding.save_new(path, observation)
    return observation


def main():
    require(sys.executable == PYTHON and len(sys.argv) == 2 and sys.argv[1] in {
        'prepare-system', 'open-system', 'check-system', 'session-status', 'close-system'},
        'Only the fixed offline session actions are supported')
    action = sys.argv[1]
    if action in {'session-status', 'close-system'}:
        frozen = read_json(system_probe.PACKET)
        print(json.dumps(system_probe.request('status' if action == 'session-status' else 'close', frozen)))
        return
    tested = components()
    additional_components()
    continuation = read_json(run_offline.CONTINUATION)
    require(continuation['status'] == 'offline_complete_exact_host_admission_pending'
        and not durable.alive(continuation['owner']),
        'Host checks require the completed continuation and free worker allocation')
    if action in {'prepare-system', 'open-system'}:
        scope = system_probe.validate_scope(namespace_probe.scope())
        if action == 'prepare-system':
            binding.save_new(system_probe.PACKET, scope)
            print(json.dumps({'status': 'OFFLINE_SESSION_PREPARED', 'scope_sha256': system_probe.identity(scope),
                'lifetime_seconds': 3600, 'max_batches': 8, 'model_calls': 0}))
            return
        require(read_json(system_probe.PACKET) == scope, 'Reviewed offline session scope changed')
        result = subprocess.run(['/usr/bin/pkexec', '/usr/bin/python3', '-I', '-B',
            str(HERE / 'system_probe.py'), 'serve', digest(system_probe.PACKET.read_bytes())], check=False)
        require(result.returncode == 0, 'Offline session helper exited unsuccessfully')
        return
    native = native_integration(tested)
    candidate = client_protocol.candidate()
    observation = checked_protocol(candidate)
    environment = namespace_probe.inspect()
    binding.save_new(HERE / 'namespace-result.json', environment)
    final = {'status': 'HOST_NATIVE_MIGRATION_AND_PROTOCOL_PASS',
        'sources': native['sources'], 'native_junit': native['native_junit'],
        'native_junit_sha256': native['native_junit_sha256'],
        'protocol_identity': observation['identity'],
        'namespace_sha256': digest((HERE / 'namespace-result.json').read_bytes()),
        'model_calls': 0, 'external_calls': 0, 'account_writes': 0, 'grant_writes': 0,
        'production_admitted': False}
    binding.save_new(HERE / 'offline-host-result.json', final)
    print(json.dumps({key: value for key, value in final.items() if key != 'sources'}))


if __name__ == '__main__':
    main()
