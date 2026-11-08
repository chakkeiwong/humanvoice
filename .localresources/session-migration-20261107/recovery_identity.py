"""Preserve recovery limits across a verified same-model client migration.

This prospective reservation adapter keeps old receipts/profile hashes intact.
The old/current profile equivalence affects eligibility only. The new sequence
stores the actual current profile and reserves a fresh canary and retry.
"""

from copy import deepcopy

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.lineage import validate_lineage


def reserve(journal, *, original_profile_hash, current_profile_hash, check_migration,
            lineage, incident, request_hash, inherited_diagnostic=None, check_only=False):
    """Called only for the exact migrated profile under a checked transition."""
    if (type(check_only) is not bool or original_profile_hash == current_profile_hash
            or not callable(check_migration)):
        raise ValueError('Client migration requires distinct bound profiles and its native verifier')
    for value in (original_profile_hash, current_profile_hash):
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Client migration profile identities must be SHA256')
    fields = {'lineage': lineage, 'incident': incident,
        'request_hash': request_hash, 'profile_hash': current_profile_hash}
    if inherited_diagnostic is not None:
        fields['inherited_diagnostic'] = inherited_diagnostic
    if any(not isinstance(value, str) or not value for value in fields.values()):
        raise ValueError('Recovery sequence requires exact nonempty identities')

    def equivalent(profile_hash):
        return profile_hash in {original_profile_hash, current_profile_hash}

    def guard():
        if check_migration() is not True:
            raise RecoveryStop('BLOCKED_ACCOUNTING', 'Client migration proof changed before reservation')

    key = digest(fields)
    guard()
    with journal.locked():
        guard()
        record = journal.read()
        selected = record['lineages'].get(lineage)
        if selected is None:
            raise RecoveryStop('BLOCKED_ACCOUNTING', 'Recovery requires a registered source lineage')
        validate_lineage(selected, ancestors=record['lineages'])
        if lineage in record['splits']:
            raise RecoveryStop('BLOCKED_DECOMPOSITION', 'Split parent cannot renew its exact retry')
        sequences = record['sequences']
        if key in sequences:
            return deepcopy(sequences[key])
        for sequence in sequences.values():
            if any(slot['state'] == 'dispatching' for slot in sequence['slots'].values()):
                raise RecoveryStop('BLOCKED_ACCOUNTING', 'Unresolved dispatch retains its reservation')
            if sequence['incident'] == incident:
                raise RecoveryStop('BLOCKED_ACCOUNTING', 'Incident was already bound to another recovery')
        lineage_rows = [row for row in sequences.values() if row['lineage'] == lineage]
        root_rows = [row for row in sequences.values() if row['root'] == selected['root']]
        inherited = record.get('inherited_recovery', {})
        legacy = inherited.get('sequences', {})
        legacy_lineage = [row for row in legacy.values() if row['lineage'] == lineage]
        legacy_root = [row for row in legacy.values() if row['root'] == selected['root']]
        consumed = {row.get('inherited_diagnostic') for row in sequences.values()}
        if inherited_diagnostic is not None:
            previous = legacy.get(inherited_diagnostic)
            if (previous is None or not previous['diagnostic_only'] or previous['retry_allocated']
                    or inherited.get('handoff') != {'sequence_identity': inherited_diagnostic,
                        'incident_hash': incident}
                    or previous['lineage'] != lineage or previous['request_hash'] != request_hash
                    or not equivalent(previous['profile_hash']) or inherited_diagnostic in consumed):
                raise RecoveryStop('BLOCKED_ACCOUNTING', 'Migrated diagnostic handoff changed or was already consumed')
        elif any(row['diagnostic_only'] and row['evidence_identity'] not in consumed
                 and row['request_hash'] == request_hash and equivalent(row['profile_hash'])
                 for row in legacy_lineage):
            raise RecoveryStop('BLOCKED_ACCOUNTING', 'Unused historical retry requires its exact diagnostic handoff')
        if (len(lineage_rows) + len(legacy_lineage) >= journal.policy['lineage_sequences']
                or len(root_rows) + len(legacy_root) >= journal.policy['root_sequences']
                or any(row['retry_allocated'] and equivalent(row['profile_hash']) for row in legacy_lineage)
                or any(equivalent(row['profile_hash']) and not row.get('cancelled') for row in lineage_rows)):
            raise RecoveryStop('BLOCKED_DECOMPOSITION', 'Client migration cannot renew model or lineage retries')
        if len(sequences) >= journal.policy['incident_allowance']:
            raise RecoveryStop('BLOCKED_BUDGET', 'Cannot reserve a complete canary and retry sequence')
        sequence = {**fields, 'root': selected['root'], 'identity': key, 'slots': {
            role: {'state': 'reserved', 'tokens': journal.policy['token_reservation_per_call']}
            for role in ('canary', 'retry')}}
        guard()
        if check_only:
            return deepcopy(sequence)
        sequences[key] = sequence
        journal.save(record)
        return deepcopy(sequence)
