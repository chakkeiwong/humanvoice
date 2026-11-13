"""Regression for the actual writer/repair endpoint-selection divergence."""

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from humanvoice import artifacts, inference_settings
from humanvoice.commands import repair_v2_command
from humanvoice.model import ModelAdapter, ModelConfig, effective_api_endpoint
from humanvoice.wp_v2_3_workflow import run_rewrite_phase

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / '.localresources/writer-session-binding-repair-20261113/session_endpoint.py'
SPEC = importlib.util.spec_from_file_location('zlb_session_endpoint', PATH)
endpoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(endpoint)


@pytest.fixture
def selected_codex(monkeypatch):
    monkeypatch.delenv('HUMANVOICE_MODEL_RUNTIME', raising=False)
    monkeypatch.delenv('ANTHROPIC_BASE_URL', raising=False)
    profile = deepcopy(inference_settings.selected_profile())
    option = profile['runtime_options']['codex']
    profile.update({key: deepcopy(option[key]) for key in ('runtime', 'model', 'sampling', 'calibration')})
    profile['runtime']['endpoint'] = 'https://gateway.invalid/v1'
    monkeypatch.setattr(inference_settings, 'selected_profile', lambda *a: deepcopy(profile))
    return profile


def test_actual_writer_session_reaches_native_repair(selected_codex, snapshot_factory, monkeypatch):
    h = snapshot_factory()
    adapter = ModelAdapter(ModelConfig.from_profile(), mock_mode=True)
    h.model.config = adapter.config
    h.model.effective_api_endpoint = adapter.effective_api_endpoint
    session = run_rewrite_phase(h.baseline, h.plan, h.snapshot, h.model, h.brief, h.policy, True)
    assert session.status == 'complete'
    saved = artifacts.load_session(h.snapshot)
    assert saved['bindings']['api_endpoint'] == 'https://gateway.invalid/v1'
    # Reproduce the production failure before applying the repair.
    with pytest.raises(ValueError, match='Session source, baseline, plan or brief changed'):
        artifacts.validated_session(h.snapshot)
    session_path = h.snapshot / '.humanvoice/rewrites' / artifacts.read_json(
        h.snapshot / '.humanvoice/rewrites/current.json')['path']
    original_bytes = session_path.read_bytes()
    calls = []
    monkeypatch.setattr(repair_v2_command, 'preflight', lambda args: calls.append(args.snapshot) or 0)
    with endpoint.scope():
        checked, _, _, _ = artifacts.validated_session(h.snapshot)
        assert checked == saved
        args = SimpleNamespace(snapshot=h.snapshot, baseline_id=h.baseline.baseline_id,
                               plan_id=h.plan.plan_id, mock=True)
        assert repair_v2_command.repair_v2_command(args) == 0
    assert calls == [h.snapshot]
    assert session_path.read_bytes() == original_bytes
    assert artifacts.read_json(h.snapshot / '.humanvoice/rewrites/repair_report.json')['actions'] == ['preflight']


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    """Keep unrelated baseline validation outside the endpoint unit cases."""
    def native(snapshot, baseline, plan, api_endpoint=None):
        config = ModelConfig.from_profile()
        return {'api_endpoint': api_endpoint if api_endpoint is not None else effective_api_endpoint(config.api_endpoint),
                'runtime_profile': artifacts.runtime_profile_hash(), 'source_hash': 'unchanged-source'}
    monkeypatch.setattr(artifacts, 'phase_bindings', native)
    return lambda **kw: artifacts.phase_bindings(tmp_path, None, None, **kw)


@pytest.mark.parametrize('selector', [None, 'anthropic', 'codex'])
@pytest.mark.parametrize('url', ['https://gateway.invalid/v1', 'https://gateway.invalid/api/v2/'])
def test_profile_selected_runtime_matches_writer_despite_environment(
        selected_codex, boundary, monkeypatch, selector, url):
    selected_codex['runtime']['endpoint'] = url
    if selector is not None:
        monkeypatch.setenv('HUMANVOICE_MODEL_RUNTIME', selector)
    monkeypatch.setenv('ANTHROPIC_BASE_URL', 'https://unrelated.invalid/v1/messages')
    writer_endpoint = ModelAdapter(ModelConfig.from_profile(), mock_mode=True).effective_api_endpoint()
    with endpoint.scope():
        assert boundary()['api_endpoint'] == writer_endpoint == url
        assert boundary(api_endpoint=url)['api_endpoint'] == url


@pytest.mark.parametrize('url', ['https://gateway.invalid', 'https://gateway.invalid/v2', 'https://other.invalid/v1'])
def test_explicit_changed_writer_destination_rejected(selected_codex, boundary, url):
    with endpoint.scope(), pytest.raises(ValueError, match='Writer endpoint differs'):
        boundary(api_endpoint=url)


def test_selected_profile_change_is_not_hidden(selected_codex, boundary):
    with endpoint.scope():
        original = boundary()
        selected_codex['model']['version_string'] = 'different-model'
        changed = boundary()
        assert original['runtime_profile'] != changed['runtime_profile']
        selected_codex['runtime']['endpoint'] = 'https://gateway.invalid/v2'
        assert boundary()['api_endpoint'] != original['api_endpoint']


def test_anthropic_endpoint_rules_preserved(boundary, monkeypatch):
    monkeypatch.delenv('HUMANVOICE_MODEL_RUNTIME', raising=False)
    monkeypatch.setenv('ANTHROPIC_BASE_URL', 'https://legacy.invalid/v1/messages')
    before = boundary()
    with endpoint.scope():
        assert boundary() == before
        assert boundary(api_endpoint='https://explicit.invalid')['api_endpoint'] == 'https://explicit.invalid'


def test_scope_restores_native_bindings_on_error(selected_codex, boundary):
    native = artifacts.phase_bindings
    with pytest.raises(RuntimeError, match='fixture failure'), endpoint.scope():
        with endpoint.scope():
            assert boundary()['api_endpoint'] == 'https://gateway.invalid/v1'
        raise RuntimeError('fixture failure')
    assert artifacts.phase_bindings is native


def test_late_consumer_import_restored(selected_codex, boundary, monkeypatch):
    native = artifacts.phase_bindings
    consumer = ModuleType('humanvoice.endpoint_scope_fixture')
    with endpoint.scope():
        monkeypatch.setitem(sys.modules, consumer.__name__, consumer)
        consumer.phase_bindings = artifacts.phase_bindings
        assert consumer.phase_bindings is not native
        assert boundary()['api_endpoint'] == 'https://gateway.invalid/v1'
    assert consumer.phase_bindings is native
