"""Apply the explicit 168-hour renewal without rewriting frozen admissions.

Only six deadline reads differ from retained functions. Exact source replacement
counts and the parent source review make an unexpected native change fatal.
All original source, grant, account, STOP, seal and attempt checks still run.
"""

import inspect
import math
import textwrap
from contextlib import ExitStack, contextmanager
from functools import wraps
from pathlib import Path
from unittest.mock import patch

import session_bootstrap  # noqa: F401  # isort: skip
import validation_program as previous

from humanvoice.artifacts import digest, read_json

HERE = Path(__file__).resolve().parent
live, base, context = previous.live, previous.base, previous.context
native, recovery = context.native_parallel, base.recovery
PATH = HERE / 'renewal.json'
RECORD = read_json(PATH)
RECORD_HASH = digest(PATH.read_bytes())


def deadline_for(output, prior):
    value = read_json(PATH)
    live.require(digest(PATH.read_bytes()) == RECORD_HASH and value == RECORD,
                 'Execution renewal changed after review')
    live.require(value['version'] == 'zlb-execution-renewal-v1'
                 and value['hours'] == 168 and value['additional_calls'] == 0
                 and value['shared_calls'] == 177 and value['workers'] == 16
                 and value['provider_seconds'] == 900 and value['attempt_seconds'] == 1050
                 and value['network_backoff_seconds'] == 900
                 and value['deadline'] == value['authorized_at'] + 168 * 3600
                 and math.isfinite(value['deadline']) and value['deadline'] > prior,
                 'Renewal changes more than the authorized execution window')
    live.require(str(Path(output).resolve()) == value['stage'] == str(live.OUTPUT)
                 and prior == value['prior_deadline']
                 and digest((live.STATE / 'admission.json').read_bytes()) == value['admission_sha256'],
                 'Renewal belongs to another stage or historical admission')
    return value['deadline']


def adapt(function, replacements):
    """Compile only enumerated substitutions against the reviewed native body."""
    original = textwrap.dedent(inspect.getsource(function))
    updated = original
    for before, after in replacements:
        live.require(updated.count(before) == 1, 'Renewal expected one native deadline expression: ' + before)
        updated = updated.replace(before, after)
    code = compile(updated, '<reviewed-renewal:' + function.__name__ + '>', 'exec')

    @wraps(function)
    def invoke(*args, **kwargs):
        # Capture current enclosing adapters, including original receipt readers.
        # A stale copy of module globals would lose those scopes after a restart.
        namespace = {**inspect.unwrap(function).__globals__, '_renewal_deadline_for': deadline_for}
        exec(code, namespace)  # noqa: S102 -- exact reviewed native body and six fixed substitutions
        return namespace[function.__name__](*args, **kwargs)

    invoke.renewal_change = {'original_sha256': digest(original), 'updated_sha256': digest(updated),
                             'replacements': replacements}
    return invoke


ADAPTERS = [
    (live, 'guard', adapt(live.guard, [("time.time() < value['deadline']",
                                     "time.time() < _renewal_deadline_for(OUTPUT, value['deadline'])")])),
    (native.Stage, 'check', adapt(native.Stage.check, [("time.time() < value['deadline']",
                                     "time.time() < _renewal_deadline_for(self.output, value['deadline'])")])),
    (native, 'reservation', adapt(native.reservation, [('deadline > time.time()',
                                     '_renewal_deadline_for(output, deadline) > time.time()')])),
    (native, 'launch_scope', adapt(native.launch_scope, [("min(context.deadline, stage.value['deadline'])",
                                     "min(context.deadline, _renewal_deadline_for(stage.output, stage.value['deadline']))")])),
    (recovery.Stage, 'attach_batch', adapt(previous.previous.attach_batch,
        [("policy['deadline'] == self.value['deadline']",
          "policy['deadline'] == _renewal_deadline_for(self.output, self.value['deadline'])")])),
    (base, 'run', adapt(base.run, [("batch_store.Policy(value['deadline'],",
                                 "batch_store.Policy(_renewal_deadline_for(live.OUTPUT, value['deadline']),")])),
]


def changes():
    return {f'{owner.__name__}.{name}': adapter.renewal_change for owner, name, adapter in ADAPTERS}


@contextmanager
def scope():
    prior_clock = base.phase_deadlines.scope

    def clock(deadline, repairs):
        return prior_clock(deadline_for(live.OUTPUT, deadline), repairs)

    with ExitStack() as stack:
        for owner, name, adapter in ADAPTERS:
            stack.enter_context(patch.object(owner, name, adapter))
        stack.enter_context(patch.object(base.phase_deadlines, 'scope', clock))
        yield
