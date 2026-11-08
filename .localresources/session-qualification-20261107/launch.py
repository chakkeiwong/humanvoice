"""Prepare a concrete request, then activate it only through grouped host approval."""

import fcntl
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MIGRATION = ROOT / '.localresources/session-migration-20261107'
sys.path[:0] = [str(HERE), str(MIGRATION), str(ROOT), str(ROOT / 'src')]

import execution
import namespace
import offline_host
import supervise

from humanvoice.artifacts import digest, read_json

require = execution.require
REVIEW = HERE / 'reviewed-execution.json'
REQUEST = ('Approve the exact current-client qualification: add 235 calls to the original '
    '2,000-call grant (new ceiling 2,235), retain the token allowance, and run the prepared '
    '212 native manuscript controls with at most 276 sessions using the retained Astra/xhigh '
    'routing selection. Permit the fixed system systemd supervisor running as ubuntu, '
    'with a read-only filesystem, write access only to its output/account/grant directories '
    'and docs/plans for master status refresh, and original-path read-only '
    'SSD archive mappings, with the existing gateway, on-request/user approval and the native '
    'read-only inference sandbox, '
    '900-second transport waits, 16 verification workers, at most three process launches and '
    'the fixed November 9 01:29:40 Shanghai deadline. Production inventory admission is separate.')


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def service_command(authority, *, now):
    remaining = int(execution.WINDOW_END - now)
    require(0 < remaining <= 172800, 'Qualification launch is outside its renewed execution window')
    return ['/usr/bin/pkexec', '/usr/bin/systemd-run', '--unit=' + supervise.UNIT,
        '--no-block',
        '--service-type=exec', '--property=Restart=on-failure', '--property=RestartPreventExitStatus=2',
        '--property=RestartSec=15', '--property=KillMode=control-group', '--property=TimeoutStopSec=45',
        '--property=RuntimeMaxSec=' + str(remaining), '--property=StartLimitIntervalSec=300',
        '--property=StartLimitBurst=3', '--working-directory=' + str(ROOT),
        *['--property=' + value for value in namespace.properties(authority)],
        *['--setenv=' + key + '=' + value for key, value in sorted(namespace.environment().items())],
        '--', execution.PYTHON, str(HERE / 'supervise.py'), 'run']


def reviewed_inputs():
    components, additional = offline_host.components(), offline_host.additional_components()
    native = read_json(HERE / 'offline-host-result.json')
    require(native.get('status') == 'HOST_NATIVE_MIGRATION_AND_PROTOCOL_PASS'
        and digest(Path(native['native_junit']).read_bytes()) == native['native_junit_sha256']
        and all(digest(Path(path).read_bytes()) == value for path, value in native['sources'].items()),
        'Qualification launch requires current native migration and protocol checks')
    require(read_json(HERE / 'namespace-result.json').get('status') == 'QUALIFICATION_NAMESPACE_PASS'
        and digest((HERE / 'namespace-result.json').read_bytes()) == native.get('namespace_sha256'),
        'Qualification launch requires the tested read-only client mount environment')
    continuation = read_json(offline_host.run_offline.CONTINUATION)
    require(continuation['status'] == 'offline_complete_exact_host_admission_pending',
        'Qualification must follow the completed no-call continuation')
    candidate = execution.client_protocol.candidate()
    prepared = read_json(HERE / 'prepared.json')
    require(prepared == execution.identified(prepared) and prepared['identity'] == execution.PREPARED
        and candidate['identity'] == prepared['candidate_identity'], 'Prepared qualification changed')
    proposal = read_json(MIGRATION / 'budget-proposal.json')
    require(proposal == execution.identified(proposal)
        and proposal['identity'] == prepared['budget_proposal_identity']
        and proposal['extension']['status'] == 'AWAITING_USER_APPROVAL'
        and proposal['budget']['additional_calls_required'] == 235
        and proposal['budget']['additional_tokens_required'] == 0,
        'Qualification changed its reviewed budget proposal')
    require(all(digest(Path(path).read_bytes()) == value for path, value in prepared['authority_sha256'].items()),
        'Native budget authority changed after qualification preparation')
    paths = {*components['sources'], *additional['sources'], *native['sources'],
        str(HERE / 'prepared.json'), str(HERE / 'qualification-host/plan.json'),
        str(MIGRATION / 'candidate-v2.json'), str(MIGRATION / 'protocol-result.json'),
        str(MIGRATION / 'budget-proposal.json'), str(HERE / 'offline-host-result.json'),
        str(HERE / 'namespace-result.json'),
        str(ROOT / '.localresources/finalization-continuation-repair01-20261107/humanvoice_owned_descendants_20261031.py'),
        *(str(ROOT / '.localresources/release-gates-20261029' / name)
            for name in ('late_archive_ssd.py', 'ssd_archive_probe.py', 'fixture_lifetime.py'))}
    return proposal, prepared, candidate, {path: digest(Path(path).read_bytes()) for path in sorted(paths)}


def prepare():
    proposal, prepared, candidate, sources = reviewed_inputs()
    result = execution.identified({'version': 'humanvoice-current-client-execution-review-v1',
        'status': 'REVIEWED_AWAITING_USER_APPROVAL', 'request': REQUEST,
        'prepared_identity': prepared['identity'], 'candidate_identity': candidate['identity'],
        'budget_proposal_identity': proposal['identity'], 'additional_calls': 235,
        'total_maximum_calls': 2235, 'qualification_maximum_sessions': 276,
        'sources': sources, 'qualification_contract': execution.qualification.contract(),
        'window_end_utc': execution.WINDOW_END, 'unit': supervise.UNIT,
        'production_admitted': False, 'model_calls': 0})
    execution.migration.save_new(REVIEW, result)
    (HERE / 'EXECUTION_REQUEST.md').write_text(REQUEST + '\n\n'
        'Exact host action:\n\n```text\n' + execution.PYTHON + ' '
        + str(HERE / 'launch.py') + ' approve-and-start\n```\n\n'
        'Review identity: `' + result['identity'] + '`.\n'
        'This review file grants no spending or execution authority.\n')
    print(json.dumps({'status': result['status'], 'review_identity': result['identity'],
        'additional_calls': 235, 'model_calls': 0}))


def activate():
    """Invoke only after host/user approval of this exact action and scope."""
    value = read_json(REVIEW)
    require(value == execution.identified(value) and value['status'] == 'REVIEWED_AWAITING_USER_APPROVAL'
        and value['request'] == REQUEST, 'Exact grouped qualification request changed')
    proposal, prepared, _candidate, sources = reviewed_inputs()
    require(value['sources'] == sources and value['qualification_contract'] == execution.qualification.contract()
        and value['prepared_identity'] == prepared['identity']
        and value['budget_proposal_identity'] == proposal['identity'],
        'Grouped qualification approval lost its reviewed evidence')
    observed = subprocess.run(['/usr/bin/systemctl', 'show', supervise.UNIT,
        '--property=ActiveState,MainPID,ControlPID'], capture_output=True, text=True, check=True, timeout=30)
    unit = dict(line.split('=', 1) for line in observed.stdout.splitlines() if '=' in line)
    require(unit.get('ActiveState') in {'inactive', 'failed'}
        and unit.get('MainPID') == unit.get('ControlPID') == '0',
        'Qualification service is already active or has an owned control process')
    require(not (HERE / 'supervisor-status.json').exists(),
        'Retained qualification supervisor requires native restart/reconciliation, not a second launch')
    addition = execution.identified({**proposal['extension'], 'status': 'USER_AUTHORIZED',
        'authorized_by': 'user', 'authorization': REQUEST, 'review_identity': value['identity']})
    extension_path = HERE / 'call-authorization.json'
    grant = read_json(addition['grant'])
    require(addition['additional_calls'] == 235 and addition['total_maximum'] == 2235,
        'Host approval changed the exact call addition')
    execution.grant_extension.validate(addition, grant, addition['grant'])
    approved = execution.identified({'version': 'humanvoice-current-client-qualification-authorization-v1',
        'status': 'USER_AUTHORIZED', 'authorized_by': 'user', 'authorization': REQUEST,
        'action': 'execute-current-client-qualification', 'review_identity': value['identity'],
        'prepared_identity': prepared['identity'], 'window_end_utc': execution.WINDOW_END,
        'maximum_sessions': 276, 'production_admitted': False,
        'grant': addition['grant'], 'account': grant['account'],
        'writable_roots': [str(HERE), str(Path(grant['account']).parent),
            str(Path(addition['grant']).parent), str(ROOT / 'docs/plans')],
        'sources': {**sources, str(extension_path): digest(encoded(addition))},
        'qualification_contract': value['qualification_contract']})
    command = service_command(approved, now=time.time())
    for path, record in ((extension_path, addition), (HERE / 'execution-authorization.json', approved)):
        if path.exists():
            require(path.read_bytes() == encoded(record), 'Prior approved qualification record differs')
        else:
            execution.migration.save_new(path, record)
    execution.approved_inputs()
    # Authentication must not share a 30-second budget with namespace startup.
    # Submit the exact service once; systemd then owns startup and supervision.
    subprocess.run(command, check=True, timeout=180)
    print(json.dumps({'status': 'APPROVED_QUALIFICATION_SERVICE_SUBMITTED', 'unit': supervise.UNIT,
        'additional_calls': 235, 'total_maximum_calls': 2235, 'production_admitted': False}))


if __name__ == '__main__':
    require(sys.executable == execution.PYTHON and len(sys.argv) == 2
        and sys.argv[1] in {'prepare', 'approve-and-start'}, 'Only fixed reviewed qualification actions are supported')
    with (HERE / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (prepare if sys.argv[1] == 'prepare' else activate)()
