"""Capture the actual interactive session; no inference or service mutation."""
import json

import durable_bootstrap as bootstrap

from humanvoice.artifacts import digest, read_json
from tools.ensemble_closure_contract import save

previous = bootstrap.previous
settings = previous.rebind.settings


def main():
    old = previous.rebind.load()['active_binding']
    current = settings.capture()
    previous.rebind.compatible(old, current)
    previous.rebind.state.require(current['cli_version'] == old['cli_version']
        and current['executable_sha256'] == old['executable_sha256']
        and current['server']['executable'] == old['server']['executable'],
        'Another editor client upgrade requires a separate client check')
    path = bootstrap.HERE / 'current-session.json'
    if path.exists():
        previous.rebind.state.require(read_json(path) == current, 'Preserve prior capture')
    else:
        save(path, current)
    print(json.dumps({'changed_fields': previous.rebind.state.changes(old, current),
        'gateway': current['settings']['provider']['base_url'],
        'client': current['cli_version'], 'credentials_match': current['credentials'] == old['credentials'],
        'binding_sha256': digest(current), 'model_calls': 0}), flush=True)


if __name__ == '__main__':
    main()
