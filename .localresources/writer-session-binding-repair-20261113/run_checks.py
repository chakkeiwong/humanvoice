"""Fixed offline regression check for the session endpoint correction."""

import hashlib
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TESTS = [ROOT / 'tests/test_zlb_session_endpoint_binding.py',
         ROOT / 'tests/test_zlb_session_endpoint_integrity.py']
SOURCES = [HERE / 'session_endpoint.py', HERE / 'diagnose.py', Path(__file__), *TESTS]


def hashes():
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in SOURCES}


def main():
    before, started = hashes(), time.monotonic()
    xml = HERE / 'regression-tests.xml'
    result = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                             '--tb=short', '--basetemp=/tmp/hv-session-check-' + str(time.time_ns()),
                             '--junitxml=' + str(xml), *map(str, TESTS)],
                            cwd=ROOT, capture_output=True, text=True, timeout=300, check=False)
    log = HERE / 'regression-tests.log'
    log.write_text(result.stdout + result.stderr)
    print(result.stdout + result.stderr, flush=True)
    if result.returncode or hashes() != before:
        raise ValueError('Endpoint regression failed or its sources changed')
    suites = ET.parse(xml).getroot()
    totals = {key: sum(int(suite.attrib[key]) for suite in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    if not totals['tests'] or any(totals[key] for key in ('failures', 'errors', 'skipped')):
        raise ValueError('Endpoint regression incomplete')
    value = {**totals, 'sources': before, 'elapsed_seconds': time.monotonic() - started,
             'artifacts': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (xml, log)},
             'model_calls': 0}
    (HERE / 'tests-result.json').write_text(json.dumps(value, indent=2) + '\n')


if __name__ == '__main__':
    main()
