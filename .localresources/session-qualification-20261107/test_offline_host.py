"""Reuse an observed native pass only with intact results, inputs and cleanup."""

from copy import deepcopy

import offline_host as host
import pytest


@pytest.fixture
def native(tmp_path, monkeypatch):
    evidence = tmp_path / 'native.xml'
    evidence.write_text('<testsuites><testsuite><testcase name="native"/></testsuite></testsuites>')
    monkeypatch.setattr(host, 'EVIDENCE', evidence)
    sources = {'native-test.py': 'a' * 64}
    return {'status': 'NATIVE_MIGRATION_PASS', 'sources': sources,
        'native_junit': str(evidence), 'native_junit_sha256': host.digest(evidence.read_bytes()),
        'cleanup': {'complete': True}}


def test_unchanged_native_pass_can_be_reused_without_running_again(native, monkeypatch, tmp_path):
    monkeypatch.setattr(host, 'HERE', tmp_path)
    host.binding.save_new(tmp_path / 'native-pass.json', native)
    monkeypatch.setattr(host.run_offline, 'sources', lambda paths: deepcopy(paths))
    monkeypatch.setattr(host.subprocess, 'Popen', lambda *_args, **_kwargs: pytest.fail('repeated native test'))
    assert host.native_integration({'sources': native['sources']}) == native


@pytest.mark.parametrize('defect', ['source', 'cleanup', 'bytes', 'failure', 'skip', 'missing'])
def test_native_reuse_never_accepts_drift_or_incomplete_evidence(native, defect):
    sources = deepcopy(native['sources'])
    if defect == 'source': sources['native-test.py'] = 'b' * 64
    elif defect == 'cleanup': native['cleanup']['complete'] = False
    elif defect == 'bytes': host.EVIDENCE.write_text('changed')
    else:
        node = {'failure': '<failure/>', 'skip': '<skipped/>', 'missing': ''}[defect]
        case = '<testcase>' + node + '</testcase>' if defect != 'missing' else ''
        host.EVIDENCE.write_text('<testsuites><testsuite>' + case + '</testsuite></testsuites>')
        native['native_junit_sha256'] = host.digest(host.EVIDENCE.read_bytes())
    with pytest.raises(ValueError):
        host.validate_native(native, sources)
