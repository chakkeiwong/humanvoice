"""Fixed offline test action for the concrete session-repair continuation."""
import subprocess
import time
import xml.etree.ElementTree as ET

import session_program as program

from humanvoice.artifacts import digest
from tools.ensemble_closure_contract import save


def main():
    sources, started = program.sources(), time.monotonic()
    tests = [program.HERE / 'test_session_program.py']
    test_sources = {str(path): digest(path.read_bytes()) for path in tests}
    xml = program.HERE / 'execution-tests.xml'
    result = subprocess.run([program.base.PYTHON, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        '--tb=short', '--basetemp=/tmp/hv-execution-renewal-' + str(time.time_ns()), '--junitxml=' + str(xml),
        *map(str, tests)], capture_output=True, text=True, timeout=300, check=False)
    log = program.HERE / 'execution-tests.log'
    log.write_text(result.stdout + result.stderr)
    print(result.stdout + result.stderr, flush=True)
    program.live.require(result.returncode == 0 and sources == program.sources()
        and test_sources == {path: digest(program.Path(path).read_bytes()) for path in test_sources},
        'Execution regression failed or changed')
    totals = {key: sum(int(s.attrib[key]) for s in ET.parse(xml).getroot())
              for key in ('tests', 'failures', 'errors', 'skipped')}
    paths = [*tests, program.HERE / 'check_execution.py', xml, log]
    save(program.HERE / 'execution-tests.json', {**totals, 'sources': sources,
         'elapsed_seconds': time.monotonic() - started,
         'artifacts': {str(path): digest(path.read_bytes()) for path in paths}, 'model_calls': 0})


if __name__ == '__main__':
    main()
