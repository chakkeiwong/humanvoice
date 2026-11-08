"""Exercise unchanged native preparation, bootstrap and ownership with migration.

Provider/client and qualification results are synthetic fixture boundaries.
Source receipt replay, budget reconstruction, campaign initialization, journal
inheritance, native preparation and ownership checks use the real implementations.
"""

import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))

import migration_runtime as adapter
import pytest
import test_qualification_capture
from test_client_transition import upgraded
from test_inventory_recovery_v3_stage import (
    baseline,
    codex,
    configure_cold_history,
    exhausted,
    native_case,
)

from humanvoice.artifacts import digest, read_json, write_json
from tools.inventory_recovery_v3 import (
    accounting,
    ancestry,
    campaign_binding,
    campaign_initialization,
    ownership_preflight,
    runtime,
    stage,
    successor,
)

__all__ = ['baseline', 'codex', 'exhausted', 'native_case']


@pytest.fixture(autouse=True)
def complete_fixture_binding(monkeypatch):
    native = test_qualification_capture.prospective
    settings = adapter.transition.migration.settings

    def prospective(*args, **kwargs):
        profile = native(*args, **kwargs)
        binding = deepcopy(profile['runtime']['active_session']['binding'])
        binding.update(thread_id='offline-native-migration', session_path='/fixture/session.jsonl',
            credentials={'store': 'file', 'path': '/fixture/auth.json',
                'file_sha256': 'a' * 64, 'environment_sha256': 'b' * 64})
        binding['server'].update(pid=100, start_ticks='90', overrides=[])
        return settings.candidate_profile(args[0].profile, binding)

    monkeypatch.setattr(test_qualification_capture, 'prospective', prospective)


@pytest.mark.parametrize('codex', [900], indirect=True)
def test_migration_prepares_and_bootstraps_real_native_campaign_without_new_spending(
        exhausted, tmp_path, monkeypatch):
    source = exhausted.transition
    binding = deepcopy(adapter.transition.migration.routing.binding_for(source['profile']))
    binding['cli_version'] += '-upgraded-fixture'
    binding['server'].update(pid=101, start_ticks='100')
    migrated, evidence = upgraded(source, binding)
    native_qualification = adapter.qualification.verify

    def qualification(output, profile):
        if output == evidence['output']:
            assert digest(profile) == evidence['profile_hash']
            return deepcopy(evidence)
        return native_qualification(output, profile)

    monkeypatch.setattr(adapter.qualification, 'verify', qualification)
    before = {path: path.read_bytes() for path in (exhausted.account, exhausted.grant,
        exhausted.output / 'plan.json', exhausted.output / 'allocation-ledger.json')}
    root = tmp_path / 'migrated-campaign'
    native_source = successor.require_transition
    with adapter.scope():
        current = stage.Stage(root / 'generation-00', migrated)
        plan = current.prepare()
        assert current.validate() == plan
        assert current.source_gate() == migrated
        # An explicit unrelated historical reconstruction remains unchanged.
        assert successor.require_transition(source) == source
        exhausted.close_history()
        configure_cold_history(exhausted, tmp_path, monkeypatch, completed=1)
        initialized = campaign_initialization.initialize(root, check=lambda: True)
        assert campaign_initialization.initialize(root, check=lambda: True) == initialized
        # Cold low-level ancestry verification requires the same historical
        # accounting context supplied by native campaign callers.
        with accounting.document_scope(migrated):
            assert ancestry.validate(current.output, plan) == plan
        campaign_binding.create(root, check=lambda: True)
        binding_report = campaign_binding.inspect(root, check=lambda: True)
        ownership = ownership_preflight.inspect(plan, current.output, migrated,
            binding_report['binding'], lambda: True)
        assert ownership['new_reservations'] == 0 and ownership['import_idempotent']
        initial_journal = initialized['seed']['binding']['initial_journal']
        inherited = initial_journal['inherited_recovery']
        assert inherited['history_identity'] == source['recovery_history']['identity']
        assert not initial_journal['sequences']
        assert plan['profile'] == migrated['profile']
        assert plan[runtime.FIELD]['recovery_sessions_used'] == source['recovery_sessions_used']
        assert plan[runtime.FIELD]['policy'] == source['policy']
        assert plan[runtime.FIELD]['transition']['source_gate'] == source['source_gate']
        # Cold validation must detect a rehashed tamper before spending.
        wrong = deepcopy(migrated)
        wrong['recovery_sessions_used'] = 0
        wrong = adapter.transition.identified(wrong)
        write_json(current.output / 'transition.json', wrong)
        with pytest.raises((ValueError, RuntimeError)):
            current.run('validate')
    assert successor.require_transition is native_source
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert read_json(current.output / 'execution.json')['status'] == 'prepared'
