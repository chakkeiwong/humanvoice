"""Bounded offline regression runner for the explicit process rebind."""
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import durable_program as program

from humanvoice.artifacts import digest
from tools.ensemble_closure_contract import save


def main():
    sources, started = program.sources(), time.monotonic()
    tests = [program.HERE / 'test_durable.py']
    before = {str(p): digest(p.read_bytes()) for p in tests}
    xml = program.HERE / 'tests.xml'
    result = subprocess.run([program.base.PYTHON, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        '--tb=short', '--basetemp=/tmp/hv-durable-' + str(time.time_ns()), '--junitxml=' + str(xml),
        *map(str, tests)], capture_output=True, text=True, timeout=600, check=False)
    log = program.HERE / 'tests.log'
    log.write_text(result.stdout + result.stderr)
    print(result.stdout + result.stderr, flush=True)
    program.rebind.state.require(result.returncode == 0 and sources == program.sources()
        and before == {p: digest(Path(p).read_bytes()) for p in before}, 'Reload regressions failed or changed')
    totals = {key: sum(int(s.attrib[key]) for s in ET.parse(xml).getroot())
              for key in ('tests', 'failures', 'errors', 'skipped')}
    paths = [*tests, program.HERE / 'check_durable.py', xml, log,
             program.rebind.gateway.HERE / 'test_gateway.py']
    save(program.HERE / 'tests-result.json', {**totals, 'sources': sources,
        'elapsed_seconds': time.monotonic() - started,
        'artifacts': {str(p): digest(p.read_bytes()) for p in paths}, 'model_calls': 0})


if __name__ == '__main__':
    main()
