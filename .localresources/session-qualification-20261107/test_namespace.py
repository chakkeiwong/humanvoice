"""Live namespace scope is explicit; historical mounts remain read-only."""

import namespace
import pytest


@pytest.fixture
def inputs(monkeypatch):
    groups = [(i, 'humanvoice/docs/audits/frozen-' + str(i)) for i in range(27)]
    authority = {'grant': str(namespace.ROOT / 'docs/audits/grant.json'),
        'account': str(namespace.ROOT / '.localresources/account/account.json')}
    authority['writable_roots'] = [str(namespace.HERE), str(namespace.ROOT / '.localresources/account'),
        str(namespace.ROOT / 'docs/audits'), str(namespace.ROOT / 'docs/plans')]
    return groups, authority


def test_approved_command_keeps_child_sandbox_and_readonly_history(inputs):
    groups, authority = inputs
    properties = namespace.properties(authority, groups=groups)
    assert {'PrivateUsers=no', 'PrivateMounts=yes', 'PrivateNetwork=no',
        'User=ubuntu', 'Group=ubuntu', 'ProtectSystem=strict', 'ProtectHome=tmpfs',
        'NoNewPrivileges=yes', 'CapabilityBoundingSet='} <= set(properties)
    bindings = next(value for value in properties if value.startswith('BindReadOnlyPaths=')).split('=', 1)[1].split()
    assert len(bindings) == 33
    assert bindings[:4] == [path + ':' + path + ':norbind' for path in
        (str(namespace.ROOT), '/home/ubuntu/.codex', '/home/ubuntu/.vscode',
            '/home/ubuntu/miniforge3')]
    assert 'ReadWritePaths=' + ' '.join(authority['writable_roots']) in properties
    private = next(value for value in properties if value.startswith('BindPaths=')).split('=', 1)[1].split()
    assert private == [str(a) + ':' + str(b) for a, b in namespace.client_state_bindings()]
    assert all(str(namespace.HERE / 'scratch') in path.split(':')[0] for path in private)
    offline = namespace.properties(authority, groups=groups, isolated_network=True)
    assert [x for x in properties if not x.startswith('PrivateNetwork=')] == [
        x for x in offline if not x.startswith('PrivateNetwork=')]
    assert 'PrivateNetwork=yes' in offline


def test_namespace_rejects_broader_write_scope_or_missing_archive(inputs):
    groups, authority = inputs
    with pytest.raises(ValueError, match='membership'):
        namespace.properties(authority, groups=groups[:-1])
    authority['writable_roots'].append('/home/ubuntu')
    with pytest.raises(ValueError, match='writable roots'):
        namespace.properties(authority, groups=groups)


def test_worker_refuses_to_run_outside_the_reviewed_namespace(inputs, monkeypatch):
    _groups, authority = inputs
    monkeypatch.setattr(namespace.os, 'geteuid', lambda: 0)
    with pytest.raises(ValueError, match='unprivileged'):
        namespace.command(authority)


@pytest.fixture
def runtime(inputs, monkeypatch):
    from types import SimpleNamespace

    groups, authority = inputs
    pairs = namespace.mounts(groups=groups)
    flags = {str(path): namespace.os.ST_RDONLY for path in
        [namespace.ROOT, '/home/ubuntu/.codex', *(target for _source, target in pairs)]}
    flags.update({path: 0 for path in authority['writable_roots']})
    monkeypatch.setattr(namespace.os, 'geteuid', lambda: 1000)
    monkeypatch.setattr(namespace.os, 'statvfs', lambda p: SimpleNamespace(f_flag=flags[str(p)]))
    monkeypatch.setattr(namespace.os.path, 'samefile', lambda _a, _b: True)
    monkeypatch.setattr(namespace.os, 'readlink', lambda _p: 'user:[1]')
    monkeypatch.setattr(namespace.execution.client_protocol, 'candidate',
        lambda: {'current_binding': {'server': {'pid': 123}}})
    monkeypatch.setattr(namespace, 'validate_client_state', lambda: None)
    return groups, authority, pairs, flags


def test_actual_mount_view_is_required_even_when_service_properties_match(runtime):
    groups, authority, _pairs, flags = runtime
    namespace.validate_environment(authority, groups=groups)
    flags[str(namespace.ROOT)] = 0
    with pytest.raises(ValueError, match='read-only'):
        namespace.validate_environment(authority, groups=groups)


def test_runtime_rejects_writable_credentials_and_archives(runtime):
    groups, authority, pairs, flags = runtime
    for path in ['/home/ubuntu/.codex', *(target for _source, target in pairs)]:
        flags[path] = 0
        with pytest.raises(ValueError, match='read-only|missing or writable'):
            namespace.validate_environment(authority, groups=groups)
        flags[path] = namespace.os.ST_RDONLY


def test_runtime_requires_all_write_roots_and_exact_archive_identity(runtime, monkeypatch):
    groups, authority, _pairs, flags = runtime
    for path in authority['writable_roots']:
        flags[path] = namespace.os.ST_RDONLY
        with pytest.raises(ValueError, match='writable roots'):
            namespace.validate_environment(authority, groups=groups)
        flags[path] = 0
    monkeypatch.setattr(namespace.os.path, 'samefile', lambda _a, _b: False)
    with pytest.raises(ValueError, match='archive mapping'):
        namespace.validate_environment(authority, groups=groups)


def test_private_client_state_keeps_real_credentials_readonly(monkeypatch):
    from types import SimpleNamespace

    root = namespace.client_state()
    flags = {str(root / 'sqlite'): 0,
        **{str(target): 0 for _source, target in namespace.client_state_bindings()},
        '/home/ubuntu/.codex/auth.json': namespace.os.ST_RDONLY,
        '/home/ubuntu/.codex/config.toml': namespace.os.ST_RDONLY}
    monkeypatch.setenv('CODEX_SQLITE_HOME', str(root / 'sqlite'))
    monkeypatch.setattr(namespace.os, 'statvfs', lambda p: SimpleNamespace(f_flag=flags[str(p)]))
    monkeypatch.setattr(namespace.os.path, 'samefile', lambda _a, _b: True)
    namespace.validate_client_state()
    for path in ('/home/ubuntu/.codex/auth.json', '/home/ubuntu/.codex/config.toml'):
        flags[path] = 0
        with pytest.raises(ValueError, match='credentials and configuration'):
            namespace.validate_client_state()
        flags[path] = namespace.os.ST_RDONLY
    monkeypatch.setenv('CODEX_SQLITE_HOME', '/home/ubuntu/.codex')
    with pytest.raises(ValueError, match='escaped'):
        namespace.validate_client_state()


def test_client_state_preparation_refuses_a_symlink_into_host_home(tmp_path, monkeypatch):
    monkeypatch.setattr(namespace, 'HERE', tmp_path)
    (tmp_path / 'scratch').mkdir()
    (tmp_path / 'scratch/client-state').symlink_to('/home/ubuntu/.codex', target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        namespace.prepare_client_state()


def test_private_index_snapshot_includes_committed_wal_without_changing_source(tmp_path):
    import sqlite3

    source, target = tmp_path / 'desktop.sqlite', tmp_path / 'private.sqlite'
    with sqlite3.connect(source) as connection:
        connection.execute('pragma journal_mode=wal')
        connection.execute('create table backfill_state(id integer primary key, status text)')
        connection.execute("insert into backfill_state values(1, 'complete')")
        connection.commit()
        before = {p.name: p.read_bytes() for p in (source, source.with_name(source.name + '-wal'))}
        namespace.snapshot_client_index(source, target)
        with sqlite3.connect(target) as private:
            assert private.execute('select * from backfill_state').fetchall() == [(1, 'complete')]
            private.execute("update backfill_state set status='private-change'")
        assert connection.execute('select * from backfill_state').fetchall() == [(1, 'complete')]
        assert before == {p.name: p.read_bytes() for p in (source, source.with_name(source.name + '-wal'))}
        namespace.snapshot_client_index(source, target)
        with sqlite3.connect(target) as private:
            assert private.execute('select status from backfill_state').fetchone() == ('private-change',)


def test_snapshot_rejects_incomplete_native_index_and_leaves_no_partial_copy(tmp_path):
    import sqlite3

    source, target = tmp_path / 'desktop.sqlite', tmp_path / 'private.sqlite'
    with sqlite3.connect(source) as connection:
        connection.execute('create table backfill_state(id integer primary key, status text)')
        connection.execute("insert into backfill_state values(1, 'running')")
    with pytest.raises(ValueError, match='not complete'):
        namespace.snapshot_client_index(source, target)
    assert not target.exists() and not target.with_suffix('.pending').exists()
    linked = tmp_path / 'linked.sqlite'
    linked.symlink_to(source)
    with pytest.raises(ValueError, match='ordinary file'):
        namespace.snapshot_client_index(linked, target)


def test_hidden_archive_receipt_uses_same_pinned_bytes_and_rejects_tampering(tmp_path, monkeypatch):
    from humanvoice.artifacts import digest

    original = tmp_path / 'external-receipt.json'
    original.write_text('{"status": "COMPLETE"}')
    monkeypatch.setattr(namespace, 'HERE', tmp_path)
    monkeypatch.setattr(namespace.archive, 'RECEIPT', original)
    monkeypatch.setattr(namespace.archive, 'RECEIPT_SHA256', digest(original.read_bytes()))
    namespace.prepare_archive_receipt()
    expected = namespace.archive_receipt()
    original.rename(tmp_path / 'hidden-receipt.json')
    assert namespace.archive_receipt() == expected
    (tmp_path / 'archive-inputs/historical-receipt.json').write_text('{"status": "OTHER"}')
    with pytest.raises(ValueError, match='receipt changed'):
        namespace.archive_receipt()
