"""Choose automatic client migration checks without resetting model recovery.

Candidate equality is not qualification. A changed executable needs fresh
native manuscript controls unless an independently checked wire-equivalence
mechanism is implemented. This module does not offer such a mechanism.
"""

from copy import deepcopy

import binding_migration as migration

digest, require = migration.digest, migration.require
VERSION = 'humanvoice-client-migration-requirements-v1'
PURPOSES = ['concept_extraction', 'coverage_verification', 'reconstruction_verification']


def requirements(original, candidate):
    # Reconstruct every field, including the selected routing index. An edited
    # candidate cannot acquire qualification credit by rehashing itself.
    require(migration.candidates(original, candidate['current_binding']) == candidate,
        'Migration candidate differs from its retained source profile')
    index = original[migration.routing.FIELD]['index']
    current = candidate['profiles'][index]
    changed = candidate['comparison']['client_changed']
    mode = 'FRESH_NATIVE_QUALIFICATION_REQUIRED' if changed else 'REVALIDATE_RETAINED_QUALIFICATION'
    result = {'version': VERSION, 'candidate_identity': candidate['identity'],
        'original_profile_hash': digest(original), 'selected_profile_hash': digest(current),
        'selected_routing_index': index, 'model': current['model']['version_string'],
        'effort': current['sampling']['reasoning_effort'], 'qualification_mode': mode,
        'purposes': PURPOSES, 'native_logical_cases': 212 if changed else 0,
        'qualification_maximum_sessions': 276 if changed else 0,
        'protocol_matrix': [list(pair) for pair in migration.routing.ORDER],
        'canary_is_qualification': False, 'reset_model_order': False,
        'reset_request_lineage': False, 'reset_recovery_usage': False,
        'rewrite_historical_receipts': False, 'human_intermediate_review': False,
        'production_admitted': False}
    return {**result, 'identity': digest(result)}


def validate_fresh_evidence(evidence, profile):
    """Only the native verifier's exact selected-profile result is usable."""
    require(evidence.get('status') == 'QUALIFICATION_VERIFIED'
        and evidence.get('profile_hash') == digest(profile)
        and evidence.get('purposes') == PURPOSES
        and evidence.get('settled') is True and evidence.get('canary_only') is False
        and all(isinstance(evidence.get(key), str) and evidence[key]
            for key in ('evaluation_hash', 'plan_identity', 'output')),
        'Current-client migration lacks native selected-profile qualification')
    return evidence


def fresh_attestation(original, candidate, requirements_record, evidence, verify):
    expected = requirements(original, candidate)
    require(requirements_record == expected
        and expected['qualification_mode'] == 'FRESH_NATIVE_QUALIFICATION_REQUIRED',
        'Fresh qualification evidence cannot change migration requirements')
    profile = candidate['profiles'][expected['selected_routing_index']]
    validate_fresh_evidence(evidence, profile)
    before = deepcopy(evidence)
    checked = verify(evidence['output'], deepcopy(profile))
    require(checked == before == evidence, 'Native qualification changed during migration verification')
    result = {'version': 'humanvoice-fresh-client-qualification-attestation-v1',
        'candidate_identity': candidate['identity'], 'requirements_identity': expected['identity'],
        'original_profile_hash': digest(original), 'selected_profile_hash': digest(profile),
        'qualification': deepcopy(checked), 'historical_qualification_reused': False,
        'production_admitted': False}
    return {**result, 'identity': digest(result)}
