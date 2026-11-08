"""A restarted qualification service must have no competing cgroup members."""

import os
from pathlib import Path

import pytest
import supervise


@pytest.mark.parametrize('defect', [None, 'another-unit', 'another-process', 'nested-cgroup', 'legacy-cgroup'])
def test_service_ownership_checks_members_and_unit_before_launch(tmp_path, monkeypatch, defect):
    path = '/user.slice/' + supervise.UNIT
    tree = tmp_path / 'cgroup'
    tree.mkdir()
    members = [os.getpid()]
    if defect == 'another-process': members.append(os.getpid() + 1000)
    (tree / 'cgroup.procs').write_text('\n'.join(map(str, members)) + '\n')
    if defect == 'nested-cgroup': (tree / 'competing-worker').mkdir()
    record = tmp_path / 'self-cgroup'
    record.write_text('0::' + path + '\n')
    if defect == 'another-unit': record.write_text('0::/user.slice/unrelated.service\n')
    if defect == 'legacy-cgroup': record.write_text('1:cpu:/legacy\n')

    def selected(value):
        if value == '/proc/self/cgroup': return record
        if value == '/sys/fs/cgroup':
            class Root:
                def __truediv__(self, relative):
                    assert relative == path.lstrip('/')
                    return tree
            return Root()
        return Path(value)

    monkeypatch.setattr(supervise, 'Path', selected)
    if defect:
        with pytest.raises(ValueError):
            supervise.require_empty_service()
    else:
        assert supervise.require_empty_service() == {'path': path, 'members': [os.getpid()]}
