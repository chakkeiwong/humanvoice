"""Refresh only the current qualification checkpoint in both master documents."""

import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MASTERS = tuple(ROOT / 'docs/plans' / name for name in
    ('humanvoice_master_program_v2.md', 'ENSEMBLE_MASTER_PROGRAM_2026-09-30.md'))
START = '<!-- current-client-qualification-20261107 -->'
END = '<!-- end-current-client-qualification-20261107 -->'


def refresh(state):
    progress = state.get('progress') or {}
    status = state['status']
    result = (START + '\nCurrent-client qualification: ' + status + '.\n'
        + 'Native completed calls: ' + str(progress.get('completed', 'unknown'))
        + '; unresolved allocations: ' + str(progress.get('unresolved', 'unknown')) + '.\n'
        + 'Process launches: ' + str(state.get('launches', 'unknown')) + ' of at most 3.\n'
        + 'Status: .localresources/session-qualification-20261107/supervisor-status.json.\n'
        + 'Execution window ends 2026-11-09 01:29:40 Asia/Shanghai.\n'
        + 'Next: ' + ('publish verified migration activation and prepare the campaign' if
            status == 'CURRENT_CLIENT_QUALIFICATION_VERIFIED' else
            'inspect retained native evidence and repair/test/review/refresh before continuation' if
            status in {'QUALIFICATION_BLOCKED', 'WORKER_CRASHED'} else
            'continue native qualification and preserve receipts across transport recovery') + '.\n'
        + 'Production inventory is not admitted; full ZLB and final human output acceptance remain pending.\n'
        + END)
    for path in MASTERS:
        before = path.read_text()
        if START in before or END in before:
            if before.count(START) != 1 or before.count(END) != 1:
                raise ValueError('Qualification checkpoint marker membership changed')
            left, tail = before.split(START, 1)
            _, right = tail.split(END, 1)
            after = left + result + right
        else:
            after = result + '\n\n' + before
        if after == before:
            continue
        fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(after)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, path.stat().st_mode & 0o777)
            if path.read_text() != before:
                raise ValueError('Master document changed during qualification refresh')
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
