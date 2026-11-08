"""An explicit prospective extension of the native budget transition.

The unchanged native transition remains embedded and independently validated.
Only the execution profile and its fresh qualification may differ. Source work,
receipts, diagnostic lineage, budget and recovery consumption remain historical.
"""

from copy import deepcopy

import binding_migration as migration
import client_protocol as protocol
import migration_policy as policy

digest, require = migration.digest, migration.require
FIELD = 'current_client_migration'
ORIGIN = 'current_client_migration_origin'
VERSION = 'humanvoice-current-client-transition-v1'


def identified(value):
    body = {key: item for key, item in value.items() if key != 'identity'}
    return {**body, 'identity': digest(body)}


def protocol_evidence(candidate, evidence):
    require(evidence == identified(evidence)
        and evidence.get('version') == protocol.VERSION
        and evidence.get('status') == 'CURRENT_CLIENT_PROTOCOL_PASS'
        and evidence.get('candidate_identity') == candidate['identity']
        and evidence.get('current_binding_hash') == digest(candidate['current_binding'])
        and evidence.get('executable_sha256') == candidate['current_binding']['executable_sha256']
        and all(type(evidence.get(key)) is int and evidence[key] == 0
            for key in ('model_calls', 'external_calls', 'account_writes', 'grant_writes'))
        and evidence.get('production_admitted') is False
        and evidence.get('historical_qualification_reused') is False,
        'Client transition lacks its isolated current-client protocol evidence')
    sources = evidence.get('sources')
    require(isinstance(sources, dict) and set(sources) == {str(path) for path in protocol.SOURCES}
        and all(isinstance(value, str) and len(value) == 64
            and all(c in '0123456789abcdef' for c in value) for value in sources.values()),
        'Client protocol lost its complete source closure')
    rows = evidence.get('observations')
    require(isinstance(rows, list) and len(rows) == len(migration.routing.ORDER),
        'Client protocol omitted an authorized model')
    executable = candidate['current_binding']['server']['executable']
    for row, (model, effort) in zip(rows, migration.routing.ORDER, strict=True):
        command = [protocol.PYTHON, '-I', str(protocol.PROBE), '--executable', executable,
            '--model', model, '--effort', effort, '--deadline', '30']
        require(set(row) == {'model', 'effort', 'command_sha256', 'observation'}
            and (row['model'], row['effort']) == (model, effort)
            and row['command_sha256'] == digest(command),
            'Client protocol changed model ordering or the isolated command')
        protocol.validate_observation(row['observation'])
    return evidence


def construct(source, candidate, requirements, attestation, protocol_result):
    """Deterministic projection; callers must independently verify the source."""
    require(source.get('version') == 'inventory-budget-successor-v1'
        and FIELD not in source and ORIGIN not in source and source == identified(source),
        'Client migration requires an original native budget transition')
    expected = policy.requirements(source['profile'], candidate)
    require(expected == requirements
        and expected['qualification_mode'] == 'FRESH_NATIVE_QUALIFICATION_REQUIRED',
        'Client transition requires the exact fresh-qualification migration policy')
    profile = candidate['profiles'][expected['selected_routing_index']]
    qualification = policy.validate_fresh_evidence(attestation['qualification'], profile)
    expected_attestation = identified({
        'version': 'humanvoice-fresh-client-qualification-attestation-v1',
        'candidate_identity': candidate['identity'], 'requirements_identity': expected['identity'],
        'original_profile_hash': digest(source['profile']), 'selected_profile_hash': digest(profile),
        'qualification': qualification, 'historical_qualification_reused': False,
        'production_admitted': False})
    require(attestation == expected_attestation,
        'Client transition changed its selected-profile qualification attestation')
    protocol_evidence(candidate, protocol_result)
    extension = identified({'version': VERSION, 'source_transition': deepcopy(source),
        'candidate': deepcopy(candidate), 'requirements': deepcopy(requirements),
        'qualification': deepcopy(attestation), 'protocol': deepcopy(protocol_result)})
    return identified({**deepcopy(source), 'profile': deepcopy(profile),
        'fallback_qualification': deepcopy(qualification), FIELD: extension})


def verify(transition, *, source_verifier, qualification_verifier):
    """Recheck native history and native judgments; identity equality is insufficient."""
    marker = transition.get(FIELD, {})
    require(marker.get('version') == VERSION and marker == identified(marker),
        'Client migration extension identity changed')
    source = deepcopy(marker['source_transition'])
    require(source_verifier(source) == source, 'Native source transition verification changed')
    checked = policy.fresh_attestation(source['profile'], marker['candidate'],
        marker['requirements'], marker['qualification']['qualification'], qualification_verifier)
    require(checked == marker['qualification'], 'Native client qualification differs from its attestation')
    expected = construct(source, marker['candidate'], marker['requirements'], checked, marker['protocol'])
    require(expected == transition,
        'Client migration changed retained work, spending, recovery, routing or qualification')
    return transition


def origin(transition):
    """Later native generations retain the exact independently verified migration."""
    if FIELD in transition:
        require(ORIGIN not in transition, 'Client transition repeats its migration origin')
        return transition
    return transition.get(ORIGIN)


def profile_pair(initial, current_profile_hash):
    """Match the same model/effort across clients, including later native fallback."""
    marker = initial[FIELD]
    old = marker['source_transition']['profile']
    candidate = marker['candidate']
    index = candidate['profile_hashes'].index(current_profile_hash)
    require(index >= candidate['original_routing_index'],
        'Client migration cannot move back to an already abandoned model')
    previous = migration.routing.candidate_profile(old[migration.routing.FIELD]['base_profile'], index)
    return digest(previous), candidate['profile_hashes'][index]
