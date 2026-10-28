"""Descriptor-relative control projections with bounded reads and durable writes."""

import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path

from control_semantics import path
from control_witness import require

TEMP_PREFIX = ".control-tmp-"
MAX_FILE_BYTES = 8_388_608


@contextmanager
def directory(value):
    selected = path(str(value))
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in selected.parts[1:]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        yield descriptor
    finally:
        os.close(descriptor)


def _read(parent, name, *, durable=False):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_FILE_BYTES,
                "Control projection is not a bounded regular file")
        raw = handle.read(MAX_FILE_BYTES + 1)
        require(len(raw) <= MAX_FILE_BYTES, "Control projection grew beyond its bound")
        if durable:
            os.fsync(handle.fileno())
        return raw


def read(value):
    selected = path(str(value))
    with directory(selected.parent) as parent:
        return _read(parent, selected.name)


def write(value, content, *, expected):
    """Replace only an exact retained before/after image; every replay fsyncs."""
    selected = path(str(value))
    require(content is None or isinstance(content, bytes) and len(content) <= MAX_FILE_BYTES,
            "Control write requires bounded exact bytes")
    with directory(selected.parent) as parent:
        actual = _read(parent, selected.name, durable=True)
        require(actual in expected, "Control projection conflicts with retained before/after bytes")
        if actual == content:
            os.fsync(parent)
            return
        if content is None:
            os.unlink(selected.name, dir_fd=parent)
            os.fsync(parent)
            return
        temporary = TEMP_PREFIX + secrets.token_hex(16)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            require(_read(parent, selected.name) in expected,
                    "Control projection changed during publication")
            os.replace(temporary, selected.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass


def members(value):
    with directory(value) as descriptor:
        result = []
        for name in os.listdir(descriptor):
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode), "Control directory contains a symlink")
            if name.startswith(TEMP_PREFIX):
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                        "Interrupted control temporary file is not regular")
                continue
            result.append(name)
        return sorted(result)


def mkdir(value):
    selected = Path(value)
    with directory(selected.parent) as descriptor:
        os.mkdir(selected.name, 0o700, dir_fd=descriptor)
        os.fsync(descriptor)
