"""Read-only user-service and durable ZLB progress inspection."""
import json
import subprocess

import durable_program as program

from humanvoice.artifacts import read_json


def main():
    service = subprocess.run(
        ['/usr/bin/systemctl', '--user', 'show', program.UNIT,
         '--property=ActiveState,SubState,MainPID,Result,ExecMainStatus,ActiveEnterTimestamp'],
        check=False, capture_output=True, text=True, timeout=20)
    attempts = read_json(program.live.OUTPUT / 'native-attempts.json')['attempts']
    value = {'service': dict(line.split('=', 1) for line in service.stdout.splitlines() if '=' in line),
             'service_query_returncode': service.returncode,
             'status': read_json(program.live.STATE / 'status.json'),
             'coordinator': read_json(program.live.STATE / 'coordinator.json'),
             'allocated': len(attempts), 'remaining': 177 - len(attempts),
             'unfinished': [{'slot': r['slot'], 'started': r['started'], 'done': r['done']}
                            for r in attempts if not r['done']],
             'bank_responses': len(program.live.bank_entries())}
    print(json.dumps(value, indent=2), flush=True)


if __name__ == '__main__':
    main()
