"""Fixed grouped publication/start and progress-checkpoint actions."""
import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import reload_program as program

from humanvoice.artifacts import digest, read_json
from tools.ensemble_closure_contract import save

ROOT = program.HERE.parents[1]
MASTERS = [ROOT / 'docs/plans' / name for name in
           ('ENSEMBLE_MASTER_PROGRAM_2026-09-30.md', 'humanvoice_master_program_v2.md')]
MANIFEST_SHA256 = 'b6dfddc7026e5f5b637fea54349fe75d2e5e7f084eb0e70572b2b706cb6cf336'


def git(*args):
    return subprocess.run(['/usr/bin/git', *args], cwd=ROOT, check=True,
                          capture_output=True, text=True, timeout=120).stdout.strip()


def commit(files, message):
    program.rebind.state.require(not git('diff', '--cached', '--name-only'),
                                 'Preserve unrelated staged changes')
    git('add', '-f', '--', *files)
    actual = set(git('diff', '--cached', '--name-only').splitlines())
    program.rebind.state.require(actual <= set(files), 'Commit includes an unrelated path')
    git('diff', '--cached', '--check')
    if actual:
        print(git('commit', '-m', message), flush=True)
    return git('rev-parse', 'HEAD')


def master_hash(path):
    text = path.read_text()
    opening, closing = '<!-- writing-live-20261112 -->', '<!-- end-writing-live-20261112 -->'
    if opening in text:
        first, last = text.index(opening), text.index(closing) + len(closing)
        text = text[:first] + opening + closing + text[last:]
    return digest(text)


def checkpoint():
    program.current_review()
    published = read_json(program.HERE / 'publication.json')
    for path, expected in published['masters'].items():
        program.rebind.state.require(master_hash(Path(path)) == expected,
                                     'Master changed outside this publication; preserve it')
    result = subprocess.run(['/usr/bin/systemctl', '--user', 'show', program.UNIT,
        '--property=ActiveState,SubState,MainPID,Result'], capture_output=True, text=True, check=True, timeout=20)
    service = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    status = read_json(program.live.STATE / 'status.json')
    attempts = read_json(program.live.OUTPUT / 'native-attempts.json')['attempts']
    count = len(program.live.bank_entries())
    now = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    label = status['status'] if service['ActiveState'] == 'active' else 'STOPPED_' + status['status']
    block = f"""<!-- renewed-session-execution-20261113 -->
Current checkpoint, {now}: **{label}**.
User service: {service['ActiveState']}/{service['SubState']}; PID {service['MainPID']}.
Durable manuscript state: {count} saved responses, {len(attempts)} allocated slots,
{177-len(attempts)} slots remaining in the original 177-call pool.
Execution is authorized through November 20, 17:03:49 Shanghai.

The editor reload upgraded its control client from 0.164 to 0.169. The
continuation explicitly binds the actual current control process while pinning
manuscript execution to the qualified 0.164 client and its exact bytes. The
current gateway is https://cn.origincoder.com/v1; model routing remains
Astra/xhigh. The upgrade changes built-in instructions, so no equivalence or
new-client qualification is claimed. Credentials and all effective settings
are checked before launch. New receipts carry the actual executed profile
and a separate exact control-session transition marker.

The reviewed repair passed 18 regressions, unchanged-command checks for all five
prepared repairs, retained-bank/account verification, sixteen-client host/sandbox
parity, and isolated startup of the pinned client. The earlier full baseline
and receipt gate remains source/evidence-bound (826.45 seconds, zero calls).
The ordinary-user continuation needs no sudo. Preserve sixteen workers,
900-second provider bounds, 1050-second scheduler bounds, fifteen-minute network
retry, every retained judgment, and charges for failed or unknown calls.

Next document work: five unit repairs (002, 009, 012, 018, 020) and their automatic
independent reviews; assembled relationships/build/release; benchmark/regression;
separately budgeted reproduction; final human review of the actual output.
Automatic recovery after assembled semantic rejection remains open in the
preceding repair plan. No final ZLB acceptance exists.
See docs/plans/ZLB_CLIENT_RELOAD_CONTINUATION_2026-11-14.md.
<!-- end-renewed-session-execution-20261113 -->"""
    for path in MASTERS:
        text = path.read_text()
        first = text.index('<!-- renewed-session-execution-20261113 -->')
        last = text.index('<!-- end-renewed-session-execution-20261113 -->') + len('<!-- end-renewed-session-execution-20261113 -->')
        path.write_text(text[:first] + block + text[last:])
    evidence = program.HERE / 'progress-checkpoint.json'
    save(evidence, {'at': now, 'service': service, 'status': status,
         'allocated': len(attempts), 'retained': count, 'review_sha256': digest((program.HERE / 'review.json').read_bytes())})
    revision = commit([str(p.relative_to(ROOT)) for p in [*MASTERS, evidence]],
                      'Refresh ZLB continuation progress after session recovery')
    published.update(checkpoint_commit=revision, masters={str(p): master_hash(p) for p in MASTERS})
    save(program.HERE / 'publication.json', published)
    print(json.dumps({'commit': revision, 'service': service, 'phase': status['status'],
                       'allocated': len(attempts), 'retained': count}), flush=True)


def publish_start():
    manifest = program.HERE / 'publish-inputs.json'
    program.rebind.state.require(digest(manifest.read_bytes()) == MANIFEST_SHA256,
                                 'Reviewed publication manifest changed')
    files = read_json(manifest)
    for relative, expected in files.items():
        path = ROOT / relative
        program.rebind.state.require(not path.is_symlink() and digest(path.read_bytes()) == expected,
                                     'Reviewed publication input changed: ' + relative)
    program.current_review()
    revision = commit([*files, str(manifest.relative_to(ROOT)), str(Path(__file__).relative_to(ROOT))],
                      'Resume qualified ZLB execution after editor session upgrade')
    save(program.HERE / 'publication.json', {'commit': revision,
         'masters': {str(p): master_hash(p) for p in MASTERS}})
    program.install_start()
    print(json.dumps({'commit': revision, 'unit': program.UNIT, 'installed': True}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('publish-start', 'checkpoint'))
    action = parser.parse_args().action
    publish_start() if action == 'publish-start' else checkpoint()
