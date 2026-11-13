"""The endpoint correction must retain native stale-session rejection."""

from copy import deepcopy

import pytest
import test_zlb_session_endpoint_binding as binding_tests

from humanvoice import artifacts
from humanvoice.model import ModelAdapter, ModelConfig
from humanvoice.wp_v2_3_workflow import run_rewrite_phase

selected_codex = binding_tests.selected_codex


def test_native_validation_keeps_all_other_binding_checks(selected_codex, snapshot_factory):
    h = snapshot_factory()
    adapter = ModelAdapter(ModelConfig.from_profile(), mock_mode=True)
    h.model.config = adapter.config
    h.model.effective_api_endpoint = adapter.effective_api_endpoint
    with binding_tests.endpoint.scope():
        session = run_rewrite_phase(h.baseline, h.plan, h.snapshot, h.model, h.brief, h.policy, True)
        assert session.status == 'complete'
        original = artifacts.load_session(h.snapshot)
        pointer = artifacts.read_json(h.snapshot / '.humanvoice/rewrites/current.json')
        path = h.snapshot / '.humanvoice/rewrites' / pointer['path']
        for key in ('source_hash', 'baseline_hash', 'canonical_inventory', 'canonical_plan',
                    'plan_hash', 'brief_hash', 'policy_hash', 'corpus_rights',
                    'implementation', 'runtime_profile', 'response_schemas', 'api_endpoint'):
            changed = deepcopy(original)
            changed['bindings'][key] = 'changed-fixture-binding'
            artifacts.write_json(path, changed)
            with pytest.raises(ValueError, match='Session source, baseline, plan or brief changed'):
                artifacts.validated_session(h.snapshot)
        artifacts.write_json(path, original)
        assert artifacts.validated_session(h.snapshot)[0] == original
        selected_codex['model']['version_string'] = 'changed-fixture-model'
        with pytest.raises(ValueError, match='Session source, baseline, plan or brief changed'):
            artifacts.validated_session(h.snapshot)
