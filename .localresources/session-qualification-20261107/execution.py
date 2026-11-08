"""Accounted current-client qualification; no campaign admission is performed.

The native runner owns retries, their 900-second waits, receipt reconciliation
and semantic stop decisions. This boundary adds exact approval, source, window
and current-session checks. It never increases a budget on its own.
"""

import fcntl
import os
import sys
import time
from contextlib import ExitStack
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MIGRATION = ROOT / '.localresources/session-migration-20261107'
sys.path[:0] = [str(MIGRATION), str(ROOT), str(ROOT / 'src')]

import binding_migration as migration
import client_protocol
import grant_extension
import migration_policy

from humanvoice.artifacts import digest, read_json
from tools import durable_program_supervisor as durable
from tools.delayed_network_runtime import replaced_aliases
from tools.inventory_recovery_v2 import control, qualification
from tools.inventory_recovery_v3 import accounting

PYTHON = '/tmp/humanvoice-release-env-20261029/bin/python'
PREPARED = '8301e562a9712b73718fb249edf699ae51e18e2d1659e8e1b3c688ca6fb64a0c'
WINDOW_END = 1794158980
require = migration.require


def identified(value):
    body = {key: item for key, item in value.items() if key != 'identity'}
    return {**body, 'identity': digest(body)}


def approved_inputs():
    """Approval records are supplied only after an explicit host/user approval."""
    record = read_json(HERE / 'execution-authorization.json')
    require(record == identified(record)
        and record.get('version') == 'humanvoice-current-client-qualification-authorization-v1'
        and record.get('status') == 'USER_AUTHORIZED' and record.get('authorized_by') == 'user'
        and isinstance(record.get('authorization'), str) and bool(record['authorization'].strip())
        and record.get('action') == 'execute-current-client-qualification'
        and record.get('prepared_identity') == PREPARED
        and type(record.get('window_end_utc')) is int and record['window_end_utc'] == WINDOW_END
        and record.get('maximum_sessions') == 276 and type(record['maximum_sessions']) is int
        and record.get('production_admitted') is False,
        'Current-client qualification requires its exact separately approved execution')
    paths = record.get('sources')
    required = {str(HERE / 'execution.py'), str(HERE / 'supervise.py'), str(HERE / 'namespace.py'),
        str(HERE / 'program_projection.py'),
        str(HERE / 'prepared.json'), str(HERE / 'qualification-host/plan.json'),
        str(MIGRATION / 'candidate-v2.json'), str(MIGRATION / 'protocol-result.json'),
        str(HERE / 'call-authorization.json'),
        str(ROOT / '.localresources/finalization-continuation-repair01-20261107/humanvoice_owned_descendants_20261031.py'),
        *(str(ROOT / '.localresources/release-gates-20261029' / name) for name in
            ('late_archive_ssd.py', 'ssd_archive_probe.py', 'fixture_lifetime.py')),
        *(str(path) for path in MIGRATION.glob('*.py') if not path.name.startswith('test_'))}
    require(isinstance(paths, dict) and required <= set(paths),
        'Qualification approval omitted an executable or immutable input')
    native_contract = qualification.contract()
    require(record.get('qualification_contract') == native_contract,
        'Qualification native executable contract differs from approval')
    for name, checksum in paths.items():
        path = Path(name)
        require(path.is_relative_to(ROOT) and path.resolve() == path
            and path.is_file() and digest(path.read_bytes()) == checksum,
            'Approved qualification source or input changed: ' + name)
    prepared = read_json(HERE / 'prepared.json')
    require(prepared == identified(prepared) and prepared['identity'] == PREPARED,
        'Approved qualification lost its retained preparation')
    output = HERE / 'qualification-host'
    require(prepared['output'] == str(output)
        and digest((output / 'plan.json').read_bytes()) == prepared['plan_sha256'],
        'Approved qualification changed its prepared plan')
    candidate = client_protocol.candidate()
    require(candidate['identity'] == prepared['candidate_identity'],
        'Approved qualification changed its current-client candidate')
    profile = candidate['profiles'][candidate['original_routing_index']]
    plan = qualification.validate_plan(read_json(output / 'plan.json'), profile)
    require(plan['plan_identity'] == prepared['qualification_plan_identity'],
        'Approved qualification changed its native plan identity')
    from client_transition import protocol_evidence

    protocol_evidence(candidate, read_json(MIGRATION / 'protocol-result.json'))
    extension_path = HERE / 'call-authorization.json'
    extension = read_json(extension_path)
    require(extension['candidate_identity'] == candidate['identity']
        and extension['additional_calls'] == 235 and extension['total_maximum'] == 2235,
        'Qualification call extension differs from its reviewed 235-call addition')
    grant_extension.validate(extension, read_json(extension['grant']), extension['grant'])
    require(record.get('grant') == extension['grant']
        and record.get('account') == read_json(extension['grant'])['account']
        and record.get('writable_roots') == [str(HERE), str(Path(record['account']).parent),
            str(Path(record['grant']).parent), str(ROOT / 'docs/plans')],
        'Qualification changed native account or writable scope')
    return record, prepared, candidate, plan, extension


def execute():
    record, prepared, candidate, plan, extension = approved_inputs()
    output, profile = Path(prepared['output']), plan['profile']
    authorization_bytes = (HERE / 'execution-authorization.json').read_bytes()
    original_stop = control.require_running

    def guard(directory=None, *, contract=None):
        require(time.time() < record['window_end_utc'] and not (HERE / 'STOP').exists(),
            'Current-client qualification reached its authorized end or explicit stop')
        require((HERE / 'execution-authorization.json').read_bytes() == authorization_bytes
            and all(digest(Path(name).read_bytes()) == value for name, value in record['sources'].items()),
            'Qualification authority or immutable source changed before dispatch')
        require(qualification.contract() == record['qualification_contract'],
            'Native qualification contract changed during execution')
        original_stop(directory, contract=contract)

    def publish(state):
        durable.save(HERE / 'execution-status.json', {
            **state, 'owner': durable.identity(os.getpid()), 'observed_at_utc': time.time(),
            'plan_identity': plan['plan_identity'], 'production_admitted': False})

    guard()
    grant = Path(extension['grant'])
    with ExitStack() as stack:
        # The same installed master lock prevents competing account allocation.
        lock_path = grant.parent / 'active-session-program.lock'
        handle = stack.enter_context(lock_path.open('a'))
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stack.enter_context(grant_extension.scope(HERE / 'call-authorization.json',
            expected_sha256=record['sources'][str(HERE / 'call-authorization.json')]))
        stack.enter_context(replaced_aliases(original_stop, guard))
        publish({'status': 'QUALIFICATION_RECONCILING'})
        stack.enter_context(accounting.history_scope())
        guard()
        migration.settings.verify(candidate['current_binding'])
        result = qualification.execute(output, profile, grant, publish=publish)
        if result.get('status') not in {'pass', 'QUALIFICATION_VERIFIED'}:
            publish({'status': 'QUALIFICATION_NONPASS', 'native_result': result,
                'automatic_semantic_reroll': False})
            return 2
        # Refresh native history after settlement; qualification.verify checks
        # exactly one account settlement and every frozen semantic judgment.
        with accounting.history_scope():
            evidence = qualification.verify(output, profile)
        migration_policy.validate_fresh_evidence(evidence, profile)
        guard()
        target = HERE / 'qualification-verified.json'
        if target.exists():
            require(read_json(target) == evidence, 'Prior verified qualification changed')
        else:
            migration.save_new(target, evidence)
        publish({'status': 'CURRENT_CLIENT_QUALIFICATION_VERIFIED', 'evidence': evidence})
    return 0


def main():
    require(sys.executable == PYTHON and sys.argv[1:] == ['execute'],
        'Only the exact approved current-client qualification is supported')
    try:
        return execute()
    except BaseException as error:
        durable.save(HERE / 'execution-failure.json', {
            'status': 'QUALIFICATION_BLOCKED', 'error': type(error).__name__ + ': ' + str(error),
            'observed_at_utc': time.time(), 'model_calls': None,
            'usage_status': 'REQUIRES_NATIVE_RECONCILIATION', 'production_admitted': False})
        raise


if __name__ == '__main__':
    raise SystemExit(main())
