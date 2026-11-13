"""Keep semantic allocations stable while new transport uses the active HTTPS URL.

The old 135 attempts remain immutable. New receipts carry their actual selected
profile and an explicit transition marker. Every original native check remains;
the enumerated profile comparisons admit only that verified successor.
"""
import inspect
import textwrap
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import asdict
from functools import wraps
from pathlib import Path
from unittest.mock import patch

import gateway_state as state

from humanvoice import automatic_settlement, codex_runtime
from humanvoice.artifacts import digest, read_json, validate_snapshot
from humanvoice.model import ModelConfig
from tools import active_session_settings as settings
from tools import model_routing_policy as routing
from tools.delayed_network_runtime import replaced_aliases
from tools.ensemble_closure_contract import save

previous, live, context = state.previous, state.live, state.context
base = previous.base
native = context.native_parallel
completion = base.recovery.native_completion
NATIVE_VALIDATE = native._capture.validate_record
NATIVE_AUTHORIZE = codex_runtime._authorize
NATIVE_USAGE = automatic_settlement.completed_usage
NATIVE_ENV_SCOPE = base.active_environment.scope
NATIVE_VERIFY = settings.verify


def trusted(profile):
    value = state.load()
    return (value['old_profile'], value['profile']) if profile in (value['old_profile'], value['profile']) else (profile,)


def live_profile(stage, row):
    value = state.load()
    state.require(str(stage.output) == value['stage'] and stage.plan['profile'] == value['old_profile']
                  and stage.plan['bindings']['source'] == value['source_hash']
                  and value['first_new_slot'] <= row['slot'] < value['maximum_slots'],
                  'Gateway launch belongs to another stage/old allocation')
    return deepcopy(value['profile'])


def config_for(stage, row):
    profile = live_profile(stage, row)
    before = row['demand']['config']
    with native.qualified.active.selected(profile):
        after = asdict(ModelConfig.from_profile())
    state.require(after == {**before, 'api_endpoint': profile['runtime']['endpoint']},
                  'Migration changed model request configuration beyond its gateway')
    return after


def write_marker(stage, row, directory):
    value = state.load()
    live_profile(stage, row)
    path = directory / 'gateway-transition.json'
    state.require(not path.exists(), 'Transport capture cannot replace an existing marker')
    save(path, state.marker(value, row, directory))


def profile_matches(actual, expected, directory):
    value = state.load()
    if actual == expected and actual != value['profile']:
        return True
    if expected not in (value['old_profile'], value['profile']) or actual != value['profile']:
        return False
    directory = Path(directory)
    record = read_json(directory / 'record.json')
    # Both original and settlement/consumer copies have the native layout.
    snapshot = directory.parents[1]
    reference = {'path': str((directory / 'record.json').relative_to(snapshot)), 'hash': digest(record)}
    return state.recorded_profile(snapshot, reference, expected) == actual


def validate_record(snapshot, reference, *, calibration_profile=None):
    expected = calibration_profile or codex_runtime.selected_profile()
    actual = state.recorded_profile(snapshot, reference, expected)
    with native.receipt_scope(actual):
        return NATIVE_VALIDATE(snapshot, reference, calibration_profile=actual)


def authorize(snapshot, profile):
    value = state.load()
    if profile != value['profile']:
        return NATIVE_AUTHORIZE(snapshot, profile)
    state.require(validate_snapshot(snapshot)['source_hash'] == value['source_hash'],
                  'Gateway authorization belongs to another manuscript')
    # Native verification still checks source, attribution, expiry, withdrawal,
    # brief/provider and policy against the original retained permission.
    original = NATIVE_AUTHORIZE(snapshot, value['old_profile'])
    return {**original, 'destination': profile['runtime']['responses_url'],
            'gateway_transition': {'path': str(state.PATH), 'sha256': digest(state.PATH.read_bytes()),
                                   'authorization': value['authorization']}}


def verify_binding(binding):
    value = state.load()
    old, current = (routing.binding_for(value[k]) for k in ('old_profile', 'profile'))
    if binding not in (old, current):
        return NATIVE_VERIFY(binding)
    state.require(NATIVE_VERIFY(current) == digest(current), 'Current gateway session did not verify')
    # A semantic/accounting binding can remain historical only through this
    # explicit successor. The actual launch uses current, never old, transport.
    return digest(binding)


@contextmanager
def environment_scope(profile):
    value = state.load()
    old, current = (routing.binding_for(value[k]) for k in ('old_profile', 'profile'))
    state.require(profile == value['old_profile'], 'Gateway child requested a foreign logical profile')
    with NATIVE_ENV_SCOPE(profile):
        native_check = settings.verify
        def checked(binding):
            state.require(binding in (old, current), 'Gateway child requested an unadmitted session')
            state.require(native_check(old) == digest(old), 'Host did not verify the transport successor')
            return digest(binding)
        with patch.object(settings, 'verify', checked):
            yield


def adapt(function, replacements):
    original = textwrap.dedent(inspect.getsource(function))
    updated = original.removeprefix('@staticmethod\n')
    for before, after in replacements:
        state.require(updated.count(before) == 1, 'Gateway adapter expected one native expression: ' + before)
        updated = updated.replace(before, after)
    code = compile(updated, '<reviewed-gateway:' + function.__name__ + '>', 'exec')
    @wraps(function)
    def invoke(*args, **kwargs):
        namespace = {**inspect.unwrap(function).__globals__,
                     '_gateway_profile': live_profile, '_gateway_config': config_for,
                     '_gateway_marker': write_marker, '_gateway_matches': profile_matches,
                     '_gateway_trusted': trusted, '_renewal_deadline_for': previous.renewal.deadline_for}
        exec(code, namespace)  # noqa: S102 -- exact native bodies and enumerated transport substitutions
        return namespace[function.__name__](*args, **kwargs)
    invoke.gateway_change = {'original_sha256': digest(original), 'updated_sha256': digest(updated),
                             'replacements': replacements}
    return invoke


ADAPTERS = [
    (native, 'receipt_scope', adapt(native.receipt_scope, [
        ('qualified.stream.grammar_scope((profile,))', 'qualified.stream.grammar_scope(_gateway_trusted(profile))'),
        ('qualified.active.runtime(profile)',
         'qualified.active.runtime(profile, historical_profiles=_gateway_trusted(profile))')])),
    (native.Native, 'invoke', adapt(native.Native.invoke, [
        ("ModelConfig(**demand['config'])", 'ModelConfig(**_gateway_config(stage, row))')])),
    (native, 'launch_scope', adapt(native.launch_scope, [
        ("profile = stage.plan['profile']", 'profile = _gateway_profile(stage, row)'),
        ("min(context.deadline, stage.value['deadline'])",
         "min(context.deadline, _renewal_deadline_for(stage.output, stage.value['deadline']))"),
        ("save(directory / 'qualification-capture.json', {**check, 'status': 'verified'})",
         "_gateway_marker(stage, row, directory)\n                save(directory / 'qualification-capture.json', {**check, 'status': 'verified'})")])),
    (native.Stage, '_verify_response', adapt(native.Stage._verify_response, [
        ("request['profile'] == self.plan['profile']",
         "_gateway_matches(request['profile'], self.plan['profile'], directory)")])),
    (live.Stage, '_unknown', adapt(live.Stage._unknown, [
        ("request['profile'] == self.plan['profile']",
         "_gateway_matches(request['profile'], self.plan['profile'], runtime)")])),
    (native, 'reconstruct', adapt(native.reconstruct, [
        ("api['profile'] == profile", "_gateway_matches(api['profile'], profile, directory)")])),
    (completion, 'allocation_evidence', adapt(completion.allocation_evidence, [
        ("request['profile'] == stage.plan['profile']",
         "_gateway_matches(request['profile'], stage.plan['profile'], original)")])),
]
USAGE_BODY = adapt(NATIVE_USAGE, [("request.get(\"profile\") != plan[\"profile\"]",
                            "not _gateway_matches(request.get(\"profile\"), plan[\"profile\"], output / folder)")])


@wraps(USAGE_BODY)
def USAGE(output, **keywords):
    if Path(output).resolve() != live.OUTPUT:
        return NATIVE_USAGE(output, **keywords)
    value = state.load()
    with native.qualified.stream.grammar_scope((value['old_profile'], value['profile'])):
        return USAGE_BODY(output, **keywords)


USAGE.gateway_change = USAGE_BODY.gateway_change


def changes():
    return {**{f'{owner.__name__}.{name}': fn.gateway_change for owner, name, fn in ADAPTERS},
            'automatic_settlement.completed_usage': USAGE.gateway_change}


@contextmanager
def scope():
    state.load()
    with ExitStack() as stack:
        for owner, name, adapter in ADAPTERS:
            if owner is native.Native:
                adapter = staticmethod(adapter)
            stack.enter_context(patch.object(owner, name, adapter))
        stack.enter_context(patch.object(native._capture, 'validate_record', validate_record))
        stack.enter_context(patch.object(codex_runtime, '_authorize', authorize))
        stack.enter_context(patch.object(settings, 'verify', verify_binding))
        stack.enter_context(patch.object(base.active_environment, 'scope', environment_scope))
        stack.enter_context(replaced_aliases(NATIVE_USAGE, USAGE))
        yield
