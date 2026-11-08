"""A client update preserves native journal consumption and fresh-canary rules."""

from copy import deepcopy

import pytest
import recovery_identity as migration

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3 import inheritance, policy
from tools.inventory_recovery_v3.reservations import RecoveryReservations

OLD, CURRENT = 'a' * 64, 'b' * 64


@pytest.fixture
def journal(tmp_path):
    budget = policy.proposal(remaining_requests=2, inherited_recovery=1,
        incident_allowance=4, split_allowance=0, qualification_calls=0,
        available_calls=50, available_tokens=50 * 544000, root_sequences=4)
    journal = RecoveryReservations(tmp_path / 'journal', budget,
        {'document': 'doc', 'migration': 'source', 'authority': 'authority'})
    journal.initialize()
    root = journal.register_root(purpose='concept_extraction', owned=['span1', 'span2'])
    request = {'purpose': 'concept_extraction', 'prompt': 'preserved request'}
    row = inheritance.identified({'request': request, 'request_hash': digest(request),
        'profile_hash': OLD, 'canary': {'status': 'complete'}, 'retry': None,
        'diagnostic_only': True})
    history = inheritance.identified({'version': 'inherited-reconnect-sequences-v1',
        'source': 'doc', 'new_reserved_calls': 0, 'sequences': [row],
        'stages': [{'sequences': [row['identity']]}]})
    handoff = {'sequence_identity': row['identity'], 'incident_hash': 'incident'}
    journal.inherit_history(history, {row['identity']: root['identity']}, handoff)
    arguments = {'original_profile_hash': OLD, 'current_profile_hash': CURRENT,
        'lineage': root['identity'], 'incident': 'incident', 'request_hash': digest(request),
        'inherited_diagnostic': row['identity'], 'check_migration': lambda: True}
    return journal, arguments


def test_migrated_pair_retains_old_history_and_requires_fresh_current_canary(journal):
    native, arguments = journal
    history = deepcopy(native.read()['inherited_recovery'])
    result = migration.reserve(native, **arguments)
    assert result['profile_hash'] == CURRENT
    assert result['inherited_diagnostic'] == arguments['inherited_diagnostic']
    assert result['slots'] == {role: {'state': 'reserved', 'tokens': 544000}
        for role in ('canary', 'retry')}
    assert native.read()['inherited_recovery'] == history
    before = native.path.read_bytes()
    assert migration.reserve(native, **arguments) == result
    assert native.path.read_bytes() == before
    with pytest.raises(migration.RecoveryStop, match='completed canary'):
        native.dispatch(result['identity'], 'retry', 'invocation', owner_check=lambda: True,
            stop_check=lambda: None)


def test_no_call_preflight_is_read_only(journal):
    native, arguments = journal
    before = native.path.read_bytes()
    result = migration.reserve(native, **arguments, check_only=True)
    assert result['slots']['canary']['state'] == 'reserved'
    assert native.path.read_bytes() == before


@pytest.mark.parametrize('defect', ['wrong-incident', 'wrong-request', 'unknown-profile',
    'missing-handoff', 'missing-proof', 'split-parent', 'old-spent', 'old-pending',
    'duplicate-incident', 'consumed-handoff', 'lineage-full', 'publication-failure'])
def test_migration_does_not_renew_or_ignore_native_recovery_failures(journal, defect, monkeypatch):
    native, arguments = journal
    record = native.read()
    if defect == 'wrong-incident': arguments['incident'] = 'another'
    elif defect == 'wrong-request': arguments['request_hash'] = 'another'
    elif defect == 'unknown-profile': arguments['original_profile_hash'] = 'c' * 64
    elif defect == 'missing-handoff': arguments['inherited_diagnostic'] = None
    elif defect == 'missing-proof': arguments['check_migration'] = lambda: False
    elif defect == 'split-parent':
        native.inherit_split(arguments['lineage'], [['span1'], ['span2']], evidence='split')
    elif defect in {'old-spent', 'old-pending', 'duplicate-incident', 'consumed-handoff', 'lineage-full'}:
        # Use native publication for prospective history. Never mutate the
        # immutable inherited rows to make a test pass.
        entries = 2 if defect == 'lineage-full' else 1
        for index in range(entries):
            sequence = {'identity': 'sequence-' + str(index), 'lineage': arguments['lineage'],
                'root': arguments['lineage'], 'incident': 'previous-' + str(index),
                'profile_hash': OLD if defect in {'old-spent', 'old-pending'} else 'c' * 64,
                'request_hash': arguments['request_hash'], 'slots': {
                    role: {'state': 'dispatching' if defect == 'old-pending' else 'incomplete',
                        'tokens': 544000} for role in ('canary', 'retry')}}
            if defect == 'duplicate-incident': sequence['incident'] = arguments['incident']
            if defect == 'consumed-handoff': sequence['inherited_diagnostic'] = arguments['inherited_diagnostic']
            record['sequences'][sequence['identity']] = sequence
        with native.locked(): native.save(record)
    else:
        monkeypatch.setattr(native, 'save', lambda value:
            (_ for _ in ()).throw(OSError('publication failed')))
    before = native.path.read_bytes()
    with pytest.raises((migration.RecoveryStop, ValueError, OSError)):
        migration.reserve(native, **arguments)
    assert native.path.read_bytes() == before


def test_proof_is_rechecked_before_publication(journal):
    native, arguments = journal
    calls = []
    def proof():
        calls.append(True)
        return len(calls) < 3
    arguments['check_migration'] = proof
    before = native.path.read_bytes()
    with pytest.raises(migration.RecoveryStop, match='proof changed'):
        migration.reserve(native, **arguments)
    assert len(calls) == 3
    assert native.path.read_bytes() == before
