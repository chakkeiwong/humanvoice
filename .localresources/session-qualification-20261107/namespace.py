"""System-service mount isolation retaining native host session verification."""

import os
import sqlite3
import stat
import sys
import time
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILDER = ROOT / '.localresources/release-gates-20261029'
sys.path[:0] = [str(HERE), str(BUILDER)]

import execution
import late_archive_ssd as archive

require = execution.require


def client_state():
    return HERE / 'scratch/client-state'


def client_state_bindings():
    root = client_state()
    return [(root / 'tmp', Path('/home/ubuntu/.codex/tmp')),
        (root / 'installation_id', Path('/home/ubuntu/.codex/installation_id'))]


def snapshot_client_index(source, target):
    """Copy a consistent native index, including its already-completed backfill.

    A fresh index tries to rebuild the entire read-only session history and
    waits behind the desktop's backfill owner. Use SQLite's online backup API;
    never invent a completion marker or modify the desktop database.
    """
    require(source.resolve() == source and stat.S_ISREG(source.lstat().st_mode),
        'Client index source must be an ordinary file')
    if target.exists():
        require(target.resolve() == target and stat.S_ISREG(target.lstat().st_mode),
            'Private client index is not an ordinary file')
        return
    temporary = target.with_suffix('.pending')
    deadline = time.monotonic() + 20

    def progress(_status, _remaining, _pages):
        require(time.monotonic() < deadline, 'Native index snapshot exceeded twenty seconds')

    with temporary.open('xb'):
        pass
    try:
        with (closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)) as original,
                closing(sqlite3.connect(temporary, timeout=5)) as private):
            original.backup(private, pages=256, progress=progress, sleep=0.05)
            require(private.execute('select status from backfill_state where id=1').fetchone()
                == ('complete',), 'Native session index backfill is not complete')
        temporary.chmod(0o600)
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_client_state():
    """Keep writable client state under the existing output grant, never in the host home."""
    root = client_state()
    require(root.resolve() == root, 'Client state path contains a symlink')
    for path in (root, root / 'tmp', root / 'sqlite'):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        require(stat.S_ISDIR(path.lstat().st_mode) and path.resolve() == path,
            'Client state directory is not an ordinary output directory')
    source = Path('/home/ubuntu/.codex/installation_id')
    require(stat.S_ISREG(source.lstat().st_mode), 'Host installation identity is not a regular file')
    target = root / 'installation_id'
    if not target.exists():
        with target.open('xb') as handle:
            handle.write(source.read_bytes())
        target.chmod(0o600)
    require(stat.S_ISREG(target.lstat().st_mode) and target.read_bytes() == source.read_bytes(),
        'Private client installation identity changed')
    snapshot_client_index(Path('/home/ubuntu/.codex/state_5.sqlite'), root / 'sqlite/state_5.sqlite')


def validate_client_state():
    require(os.environ.get('CODEX_SQLITE_HOME') == str(client_state() / 'sqlite'),
        'Qualification client database path escaped its output directory')
    require(not os.statvfs(client_state() / 'sqlite').f_flag & os.ST_RDONLY,
        'Qualification client databases are not writable')
    for source, target in client_state_bindings():
        require(os.path.samefile(source, target) and not os.statvfs(target).f_flag & os.ST_RDONLY,
            'Qualification private client state mapping is missing or read-only')
    for name in ('auth.json', 'config.toml'):
        require(os.statvfs('/home/ubuntu/.codex/' + name).f_flag & os.ST_RDONLY,
            'Qualification client credentials and configuration must remain read-only')


def writable_roots(authority):
    roots = [str(HERE), str(Path(authority['account']).parent),
        str(Path(authority['grant']).parent), str(ROOT / 'docs/plans')]
    require(authority['writable_roots'] == roots
        and all(Path(path).is_relative_to(ROOT) for path in roots),
        'Qualification changed its exact writable roots')
    return roots


def archive_receipt():
    # ProtectHome hides the cleanup workspace. Its pinned public receipt may
    # be read from an exact-byte local copy, without exposing another home tree.
    path = archive.RECEIPT if archive.RECEIPT.exists() else HERE / 'archive-inputs/historical-receipt.json'
    require(archive.checksum(path) == archive.RECEIPT_SHA256,
        'Qualification archive receipt changed')
    return execution.read_json(path)


def prepare_archive_receipt():
    require(archive.checksum(archive.RECEIPT) == archive.RECEIPT_SHA256,
        'Qualification archive receipt changed before copying')
    target = HERE / 'archive-inputs/historical-receipt.json'
    require(target.parent.resolve() == target.parent, 'Archive receipt directory contains an alias')
    target.parent.mkdir(exist_ok=True)
    if not target.exists():
        with target.open('xb') as handle:
            handle.write(archive.RECEIPT.read_bytes())
    require(archive.checksum(target) == archive.RECEIPT_SHA256,
        'Local archive receipt differs from pinned original')


def mounts(*, groups=None):
    if groups is None:
        receipt = archive_receipt()
        selected = [(index, str(Path(row['repo']) / row['scope']))
            for index, row in enumerate(receipt['groups'])
            if row['repo'] == 'humanvoice' and row['status'] == 'COMPLETE']
    else:
        selected = groups
    require(len(selected) == 27 and len({path for _group, path in selected}) == 27,
        'Qualification archive mapping membership changed')
    require(all(not Path(path).is_absolute() and '..' not in Path(path).parts
        and Path(path).parts[:3] == ('humanvoice', 'docs', 'audits') for _group, path in selected),
        'Qualification archive mapping escaped historical evidence')
    pairs = [(archive.original.EXTRACTED, archive.original.MOUNT),
        (archive.original.IMAGE, archive.original.ORIGINAL_IMAGE)]
    pairs.extend((archive.EXTRACTED / relative, ROOT.parent / relative)
        for _group, relative in selected)
    return [(str(source), str(target)) for source, target in pairs]


def literal(path):
    require(isinstance(path, str) and path.startswith('/') and '..' not in Path(path).parts
        and not any(c in path for c in ':\n\r\t %"\\'),
        'Qualification service path must be literal and absolute')
    return path


def properties(authority, *, isolated_network=False, groups=None):
    roots = writable_roots(authority)
    pairs = mounts(groups=groups)
    # Ubuntu's systemd 249 silently ignores EACCES/EPERM during namespace
    # construction. Root cannot traverse the user's FUSE archives. Hide those
    # inherited mounts before exposing the required SSD trees without submounts;
    # then install the 29 reviewed archive substitutions at their original paths.
    # The empty home view also prevents recursive remounts of unrelated FUSE
    # mounts, including the desktop mounts under /run/user.
    support = [str(ROOT), '/home/ubuntu/.codex', '/home/ubuntu/.vscode',
        '/home/ubuntu/miniforge3']
    bindings = [literal(path) + ':' + literal(path) + ':norbind' for path in support]
    bindings.extend(literal(a) + ':' + literal(b) for a, b in pairs)
    return ['User=ubuntu', 'Group=ubuntu', 'PrivateUsers=no', 'PrivateMounts=yes',
        'PrivateNetwork=' + ('yes' if isolated_network else 'no'),
        'ProtectSystem=strict', 'ProtectHome=tmpfs', 'NoNewPrivileges=yes',
        'CapabilityBoundingSet=', 'RestrictSUIDSGID=yes',
        'ReadOnlyPaths=' + str(ROOT) + ' /home/ubuntu/.codex',
        'ReadWritePaths=' + ' '.join(literal(path) for path in roots),
        'BindPaths=' + ' '.join(literal(str(a)) + ':' + literal(str(b))
            for a, b in client_state_bindings()),
        'BindReadOnlyPaths=' + ' '.join(bindings),
        'TemporaryFileSystem=/dev/shm:rw,nosuid,nodev']


def environment():
    # Copy only the native parity keys; never copy arbitrary provider overrides.
    values = {key: os.environ[key] for key in execution.migration.settings.ENVIRONMENT_KEYS
        if key in os.environ}
    require(values.get('HOME') == '/home/ubuntu'
        and values.get('CODEX_HOME', '/home/ubuntu/.codex') == '/home/ubuntu/.codex',
        'Qualification must retain the interactive credential home')
    values.update(CODEX_INTERNAL_ORIGINATOR_OVERRIDE='codex_vscode',
        HUMANVOICE_AUDIT_WORKERS='16', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
        PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(HERE / 'scratch'))
    values['CODEX_SQLITE_HOME'] = str(client_state() / 'sqlite')
    return values


def validate_environment(authority, *, groups=None):
    require(os.geteuid() == 1000 and os.statvfs(ROOT).f_flag & os.ST_RDONLY,
        'Qualification requires its unprivileged read-only system-service environment')
    require(all(not os.statvfs(path).f_flag & os.ST_RDONLY for path in writable_roots(authority)),
        'Qualification service lost its reviewed writable roots')
    require(os.statvfs('/home/ubuntu/.codex').f_flag & os.ST_RDONLY,
        'Qualification credential home must remain read-only')
    validate_client_state()
    for source, target in mounts(groups=groups):
        require(os.path.samefile(source, target) and os.statvfs(target).f_flag & os.ST_RDONLY,
            'Qualification archive mapping is missing or writable')
    candidate = execution.client_protocol.candidate()
    require(os.readlink('/proc/self/ns/user') == os.readlink(
        '/proc/' + str(candidate['current_binding']['server']['pid']) + '/ns/user'),
        'Qualification must retain the bound server user namespace')


def command(authority):
    validate_environment(authority)
    return [execution.PYTHON, str(HERE / 'execution.py'), 'execute']
