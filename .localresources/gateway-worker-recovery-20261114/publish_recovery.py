"""Fixed, focused commit/service start and progress checkpoint actions."""
import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import recovery_program as program  # isort: skip -- initializes retained sibling paths
import publish_durable as prior

from humanvoice.artifacts import digest, read_json
from tools.ensemble_closure_contract import save

ROOT = program.HERE.parents[1]
MANIFEST_SHA256 = 'd5bbcf67e1f17fe923e30c48a9b0e337f2ce8b558e0059d7358229e33abe51df'
MASTERS = prior.MASTERS
OPEN = '<!-- gateway-worker-recovery-20261114 -->'
CLOSE = '<!-- end-gateway-worker-recovery-20261114 -->'


def status():
    result = subprocess.run(['/usr/bin/systemctl', '--user', 'show', program.UNIT,
        '--property=ActiveState,SubState,MainPID,Result'], capture_output=True, text=True, check=True, timeout=20)
    service = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    attempts = read_json(program.live.OUTPUT / 'native-attempts.json')['attempts']
    known = sum(read_json(program.live.OUTPUT / f"calls/{r['slot']:04d}/completion.json")['response'] is not None
                for r in attempts if r['done'])
    return {'at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
            'service': service, 'status': read_json(program.live.STATE / 'status.json'),
            'allocated': len(attempts), 'remaining': 177-len(attempts),
            'bank': len(program.live.bank_entries()), 'known_native_responses': known,
            'review_sha256': digest((program.HERE / 'review.json').read_bytes())}


def refresh():
    program.current_review()
    value = status()
    phase = value['status']['status'] if (program.HERE / 'installation.json').exists() else 'READY_TO_RESUME'
    service = value['service']
    block = f"""{OPEN}
Current checkpoint, {value['at']}: **{phase}**.
Successor user service: {service['ActiveState']}/{service['SubState']}; PID {service['MainPID']}.
Allocated calls: {value['allocated']}; remaining: {value['remaining']} of 177.
Known native responses: {value['known_native_responses']}; imported bank entries: {value['bank']}.

The previous run survived editor reload and started five HTTPS requests. One
completed; worker cleanup then compared its new gateway profile against the
old plan and failed, cancelling the other four. The repair verifies actual
admitted transport/session evidence in the worker ownership check. Sixteen
regressions pass, including real worker exit and interrupted native retry.
The actual five-capture offline check passes in 25.92 seconds with no model
calls or accounting writes.

Only the four verified interrupted tasks are reopened in the same batch.
Original failed outcomes/charges, known answers, attempt counters and limits
remain. No sudo is needed. The gateway is https://cn.origincoder.com/v1 with
the qualified pinned client and Astra/xhigh manuscript routing. Sixteen workers,
900-second provider limits, 1050-second scheduler limits, 15-minute network
retry and the November 20, 17:03:49 Shanghai execution window remain.

Next: finish unit repairs and automatic independent reviews; assembled
relationships/build/release; benchmark/regression; separately budgeted
reproduction; final human review. Assembled semantic-rejection recovery is
still an implementation gap. No final ZLB acceptance is claimed.
See docs/plans/ZLB_GATEWAY_WORKER_RECOVERY_2026-11-14.md.
{CLOSE}"""
    for path in MASTERS:
        text = path.read_text()
        opening, closing = (OPEN, CLOSE) if OPEN in text else (
            '<!-- durable-settings-recovery-20261114 -->', '<!-- end-durable-settings-recovery-20261114 -->')
        start, end = text.index(opening), text.index(closing) + len(closing)
        path.write_text(text[:start] + block + text[end:])
    save(program.HERE / 'progress-checkpoint.json', value)
    return value


def publish_start():
    manifest = program.HERE / 'publish-inputs.json'
    program.live.require(digest(manifest.read_bytes()) == MANIFEST_SHA256, 'Reviewed publication manifest changed')
    files = read_json(manifest)
    for relative, expected in files.items():
        path = ROOT / relative
        program.live.require(not path.is_symlink() and digest(path.read_bytes()) == expected,
                             'Reviewed publication changed: ' + relative)
    program.current_review()
    revision = prior.commit([*files, str(manifest.relative_to(ROOT)), str(Path(__file__).relative_to(ROOT))],
                            'Repair gateway worker recovery and retain interrupted ZLB attempts')
    save(program.HERE / 'publication.json', {'commit': revision,
         'masters': {str(p): prior.master_hash(p) for p in MASTERS}})
    program.install_start()
    print(json.dumps({'commit': revision, 'unit': program.UNIT, 'installed': True}), flush=True)


def checkpoint():
    program.current_review()
    published = read_json(program.HERE / 'publication.json')
    for path, expected in published['masters'].items():
        program.live.require(prior.master_hash(Path(path)) == expected, 'Master changed outside this publication')
    value = refresh()
    evidence = program.HERE / 'progress-checkpoint.json'
    revision = prior.commit([str(p.relative_to(ROOT)) for p in [*MASTERS, evidence]],
                            'Refresh recovered ZLB worker execution progress')
    published.update(checkpoint_commit=revision, masters={str(p): prior.master_hash(p) for p in MASTERS})
    save(program.HERE / 'publication.json', published)
    print(json.dumps({'commit': revision, 'service': value['service'], 'phase': value['status']['status'],
                      'allocated': value['allocated'], 'bank': value['bank']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('refresh', 'publish-start', 'checkpoint', 'status'))
    action = parser.parse_args().action
    if action == 'refresh': refresh()
    elif action == 'publish-start': publish_start()
    elif action == 'checkpoint': checkpoint()
    else: print(json.dumps(status(), indent=2), flush=True)
