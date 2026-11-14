"""Bounded offline regression runner, with retained source/evidence hashes."""
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import recovery_program as program

from humanvoice.artifacts import digest
from tools.ensemble_closure_contract import save


def main():
    sources, started = program.sources(), time.monotonic()
    tests = [program.HERE / 'test_recovery.py']
    before = {str(p): digest(p.read_bytes()) for p in tests}
    xml = program.HERE / 'tests.xml'
    result = subprocess.run([program.base.PYTHON, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        '--tb=short', '--basetemp=/tmp/hv-worker-recovery-' + str(time.time_ns()), '--junitxml=' + str(xml),
        *map(str, tests)], capture_output=True, text=True, timeout=600, check=False)
    log = program.HERE / 'tests.log'
    log.write_text(result.stdout + result.stderr)
    print(result.stdout + result.stderr, flush=True)
    program.live.require(result.returncode == 0 and sources == program.sources()
        and before == {p: digest(Path(p).read_bytes()) for p in before}, 'Worker recovery regressions failed or changed')
    totals = {key: sum(int(s.attrib[key]) for s in ET.parse(xml).getroot())
              for key in ('tests', 'failures', 'errors', 'skipped')}
    paths = [*tests, program.HERE / 'check_recovery.py', xml, log,
             program.previous.HERE / 'test_durable.py', program.capture.state.HERE / 'test_gateway.py']
    save(program.HERE / 'tests-result.json', {**totals, 'sources': program.sources(),
         'elapsed_seconds': time.monotonic() - started,
         'artifacts': {str(p): digest(p.read_bytes()) for p in paths}, 'model_calls': 0})


if __name__ == '__main__':
    main()
