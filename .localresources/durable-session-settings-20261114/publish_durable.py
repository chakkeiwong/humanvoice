"""Fixed grouped publication/start and progress-checkpoint actions."""
import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import durable_program as program

from humanvoice.artifacts import digest, read_json
from tools.ensemble_closure_contract import save

ROOT = program.HERE.parents[1]
MASTERS = [ROOT / 'docs/plans' / name for name in
           ('ENSEMBLE_MASTER_PROGRAM_2026-09-30.md', 'humanvoice_master_program_v2.md')]
MANIFEST_SHA256 = 'f7f5ab6b70565f0ce44f2023b48e5ce945e7fafe03880dc902026850d201e9c1'


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
    block = f"""<!-- durable-settings-recovery-20261114 -->
Current checkpoint, {now}: **{label}**.
User service: {service['ActiveState']}/{service['SubState']}; PID {service['MainPID']}.
Retained manuscript responses: {count}; allocated slots: {len(attempts)};
remaining slots: {177-len(attempts)} in the original 177-call pool.

Execution now verifies current thread/native configuration and credential/
environment hashes directly; it does not depend on an editor process remaining
alive. Only PID/start time are excluded from stable settings identity. Changed
model, effort, gateway, approval, credentials, thread or pinned executable still
blocks before a request. New receipts retain actual qualified-client profiles
and exact gateway/session/durable-settings markers.

The repair passes 20 regressions, including actual verification after editor
exit, native success/failure accounting, restart, tamper rejection and worker
scope restoration. Retained-bank/account checks pass with zero provider calls
or account writes. Host/sandbox parity uses sixteen clients; the exact qualified
executable is checked in the production namespace with networking denied.
Ordinary-user service deployment requires no sudo.

The active gateway is https://cn.origincoder.com/v1 and manuscript routing remains
Astra/xhigh with the qualified pinned client. Sixteen workers, 900-second provider
bounds, 1050-second scheduler attempts, 15-minute network backoff and the
November 20, 17:03:49 Shanghai deadline remain.

Remaining document work: five unit repairs and automatic independent reviews;
assembled relationships/build/release; benchmark/regression; separately budgeted
reproduction; final human review. Automatic recovery from assembled semantic
rejection remains open in the preceding repair plan. No final acceptance exists.
See docs/plans/ZLB_DURABLE_SETTINGS_RECOVERY_2026-11-14.md.
<!-- end-durable-settings-recovery-20261114 -->"""
    for path in MASTERS:
        text = path.read_text()
        first = text.index('<!-- durable-settings-recovery-20261114 -->')
        last = text.index('<!-- end-durable-settings-recovery-20261114 -->') + len('<!-- end-durable-settings-recovery-20261114 -->')
        path.write_text(text[:first] + block + text[last:])
    evidence = program.HERE / 'progress-checkpoint.json'
    save(evidence, {'at': now, 'service': service, 'status': status,
         'allocated': len(attempts), 'retained': count, 'review_sha256': digest((program.HERE / 'review.json').read_bytes())})
    revision = commit([str(p.relative_to(ROOT)) for p in [*MASTERS, evidence]],
                      'Refresh durable ZLB execution progress')
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
                      'Keep verified ZLB execution independent of editor process lifetime')
    save(program.HERE / 'publication.json', {'commit': revision,
         'masters': {str(p): master_hash(p) for p in MASTERS}})
    program.install_start()
    print(json.dumps({'commit': revision, 'unit': program.UNIT, 'installed': True}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('publish-start', 'checkpoint'))
    action = parser.parse_args().action
    publish_start() if action == 'publish-start' else checkpoint()
