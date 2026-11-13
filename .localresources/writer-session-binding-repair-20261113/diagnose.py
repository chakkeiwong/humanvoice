"""Fixed offline check of the actual stopped ZLB session; no launch action."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'writer-validation-repair-20261113'))
sys.dont_write_bytecode = True

import validation_program as previous  # isort: skip -- initialize retained dependency paths
import session_endpoint

from humanvoice import artifacts
from humanvoice.model import ModelConfig, effective_api_endpoint
from tools.inventory_history_adoption import no_inference

context, live = previous.context, previous.live
FAILED = HERE.parent / 'parallel-manuscript-20261112/execution-frontier-1794512046911131230'


def sources():
    paths = [Path(__file__), HERE / 'session_endpoint.py',
             HERE.parents[1] / 'tests/test_zlb_session_endpoint_binding.py']
    return {str(path): artifacts.digest(path.read_bytes()) for path in paths}


def namespace():
    # Accounting, responses, qualification and the stopped clone are read-only.
    # Only this diagnostic directory and a private temporary filesystem can be
    # written. The OS network namespace has no external interface.
    return ['/usr/bin/bwrap', '--die-with-parent', '--new-session',
            '--ro-bind', '/', '/', '--dev', '/dev', '--proc', '/proc',
            '--tmpfs', '/tmp', '--unshare-net', '--bind', str(HERE), str(HERE),
            '--ro-bind', str(context.QUALIFICATION), str(context.QUALIFICATION),
            previous.base.PYTHON, '-B', str(Path(__file__)), 'check-child']


def check():
    started = time.monotonic()
    previous.current_review()
    before_sources = sources()
    snapshot = FAILED / 'snapshot'
    admission = artifacts.read_json(live.STATE / 'admission.json')
    immutable = [FAILED / 'report.json', live.STATE / 'admission.json',
                 live.OUTPUT / 'native-attempts.json', live.OUTPUT / 'allocation-ledger.json',
                 Path(admission['account']), Path(admission['grant'])]
    before = {str(path): artifacts.digest(path.read_bytes()) for path in immutable}
    rewrites = context.demand_probe.tree(snapshot / '.humanvoice/rewrites')
    print('Checking historical qualification and the actual stopped session offline.', flush=True)
    with no_inference(), live.offline_deadline(), context.parent() as parent:
        print('Historical qualification passed; checking the native session once.', flush=True)
        with parent.consumer(snapshot):
            session = artifacts.load_session(snapshot)
            retained_failure = artifacts.read_json(snapshot / '.humanvoice/rewrites/repair_report.json')
            before_error = retained_failure.get('error')
            if (before_error != 'Session source, baseline, plan or brief changed'
                    or retained_failure['actions'] or retained_failure['status'] != 'blocked'):
                raise ValueError('Stopped repair evidence changed')
            expected = {}
            native = artifacts.phase_bindings

            def observe(*args, **kwargs):
                value = native(*args, **kwargs)
                expected.update(value)
                return value

            # One full native check. Only endpoint calculation differs between
            # the two paths; collect its actual result without replaying inventory
            # and historical receipts three times inside one audit allowance.
            with patch.object(artifacts, 'phase_bindings', observe), session_endpoint.scope():
                checked, _, plan, _ = artifacts.validated_session(snapshot, require_complete=False)
                if checked != session:
                    raise ValueError('Endpoint correction changed the retained session')
            legacy = dict(expected)
            legacy['api_endpoint'] = effective_api_endpoint(ModelConfig.from_profile().api_endpoint)
            different = sorted(key for key, value in legacy.items() if session['bindings'].get(key) != value)
            if different != ['api_endpoint']:
                raise ValueError('Unexpected native binding differences: ' + ', '.join(different))
            failures, accepted = [], []
            for unit in plan.units:
                result = artifacts.load_unit_result(snapshot, session, unit.unit_id)
                (accepted if result['is_acceptable'] else failures).append(unit.unit_id)
    if before != {str(path): artifacts.digest(path.read_bytes()) for path in immutable}:
        raise ValueError('Offline diagnostic changed accounting or stopped evidence')
    if rewrites != context.demand_probe.tree(snapshot / '.humanvoice/rewrites') or sources() != before_sources:
        raise ValueError('Saved sessions or diagnostic implementation changed')
    report = {'status': 'PASS', 'checked_at': time.time(), 'sources': before_sources,
              'elapsed_seconds': time.monotonic() - started,
              'baseline': {'native_replays': parent.baseline.replays, 'reuse_hits': parent.baseline.hits,
                           **parent.baseline.last_guard},
              'original_error': before_error, 'differing_keys': different,
              'session_path': str(snapshot), 'retained_files': before,
              'retained_rewrites_sha256': artifacts.digest(rewrites),
              'accepted_units': accepted, 'failed_units': failures,
              'model_calls': 0, 'account_writes': 0, 'service_started': False,
              'execution_deadline': admission['deadline'], 'final_zlb_acceptance': False}
    artifacts.write_json(HERE / 'actual-session-check.json', report)
    print(json.dumps({key: value for key, value in report.items()
                      if key not in {'sources', 'retained_files'}}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('check', 'check-child'))
    action = parser.parse_args().action
    previous.base.startup_program.original.bound_file_descriptors()
    if action == 'check-child':
        return check()
    return subprocess.run(namespace(), check=False, timeout=1050).returncode


if __name__ == '__main__':
    raise SystemExit(main())
