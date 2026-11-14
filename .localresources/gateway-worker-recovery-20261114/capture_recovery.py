"""Use the actual admitted transport when reclaiming a captured worker."""
import inspect
import textwrap
from contextlib import contextmanager
from unittest.mock import patch

import recovery_bootstrap as bootstrap

from humanvoice.artifacts import digest, read_json

previous = bootstrap.previous
gateway = previous.rebind.transport
native, state = gateway.native, gateway.state
ORIGINAL = native.Stage.recover_workers
BEFORE = "row['capture_binding']['profile_hash'] == digest(self.plan['profile'])"
AFTER = "row['capture_binding']['profile_hash'] == _captured_profile_hash(self, row, directory)"
SOURCE = textwrap.dedent(inspect.getsource(ORIGINAL))
state.require(SOURCE.count(BEFORE) == 1, 'Worker recovery source changed')
UPDATED = SOURCE.replace(BEFORE, AFTER)
CODE = compile(UPDATED, '<reviewed-capture-recovery>', 'exec')
ORIGINAL_EXECUTE = native.Stage.execute
EXEC_SOURCE = textwrap.dedent(inspect.getsource(ORIGINAL_EXECUTE))
EXEC_BEFORE = "if outcome.kind != 'unknown':"
EXEC_AFTER = "if outcome.kind != 'unknown' and not _interrupted_retry(self, previous, outcome, context):"
state.require(EXEC_SOURCE.count(EXEC_BEFORE) == 1, 'Worker dispatch source changed')
EXEC_UPDATED = EXEC_SOURCE.replace(EXEC_BEFORE, EXEC_AFTER)
EXEC_CODE = compile(EXEC_UPDATED, '<reviewed-interrupted-dispatch>', 'exec')


def captured_profile_hash(stage, row, directory):
    # No record.json is needed: an orphan may still be writing it. Admission,
    # all three transport/session markers and argv precede process launch.
    snapshot = stage.plan['snapshot']
    reference = {'path': str((directory / 'record.json').relative_to(snapshot))}
    actual = state.recorded_profile(snapshot, reference, stage.plan['profile'])
    request = read_json(directory / 'inputs/api-request.json')
    expected = stage._demand(row)['request']
    state.require(request['profile'] == actual
        and request['source_hash'] == stage.plan['bindings']['source']
        and request['implementation'] == stage.plan['bindings']['implementation']
        and request['prompt_hash'] == digest(expected['prompt'])
        and (directory / 'inputs/prompt.txt').read_text() == expected['prompt']
        and all(request[k] == expected[k] for k in ('purpose', 'response_schema', 'system_prompt'))
        and row['capture_binding']['binding_hash'] == digest(state.routing.binding_for(actual)),
        'Captured request differs from its admitted source/profile/slot')
    return digest(actual)


def recover_workers(self, database, attempts):
    namespace = {**ORIGINAL.__globals__, '_captured_profile_hash': captured_profile_hash}
    exec(CODE, namespace)  # noqa: S102 -- one checked expression in unchanged native ownership logic
    return namespace['recover_workers'](self, database, attempts)


def execute(self, demand, context, *, before_start, classify):
    from interrupted_batch import may_retry
    namespace = {**ORIGINAL_EXECUTE.__globals__, '_interrupted_retry': may_retry}
    exec(EXEC_CODE, namespace)  # noqa: S102 -- one checked retry expression, original counters and accounting
    return namespace['execute'](self, demand, context, before_start=before_start, classify=classify)


def changes():
    return {'original_sha256': digest(SOURCE), 'updated_sha256': digest(UPDATED),
            'replacements': [[BEFORE, AFTER]],
            'dispatch_original_sha256': digest(EXEC_SOURCE), 'dispatch_updated_sha256': digest(EXEC_UPDATED),
            'dispatch_replacements': [[EXEC_BEFORE, EXEC_AFTER]]}


@contextmanager
def scope():
    with patch.object(native.Stage, 'recover_workers', recover_workers), patch.object(native.Stage, 'execute', execute):
        yield
