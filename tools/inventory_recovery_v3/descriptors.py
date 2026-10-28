"""Prove existing exclusive Linux flock ownership without changing any lock."""

import os
import re
import stat
from pathlib import Path

from tools.inventory_recovery_v3.installed_authority import canonical_path
from tools.inventory_recovery_v3.reservations import regular_path


def identity(value):
    if not stat.S_ISREG(value.st_mode):
        raise ValueError("Inherited ownership requires a regular lock file")
    return value.st_dev, value.st_ino


def lock_record(descriptor, expected):
    with Path(f"/proc/self/fdinfo/{descriptor}").open("rb") as source:
        content = source.read(65537)
    if len(content) > 65536:
        raise ValueError("Inherited descriptor has ambiguous lock metadata")
    rows = [line.split() for line in content.decode("ascii").splitlines()
            if line.startswith("lock:")]
    if len(rows) != 1:
        raise ValueError("Descriptor lacks its own exclusive lock")
    row = rows[0]
    if (len(row) != 9 or not re.fullmatch(r"[0-9]+:", row[1])
            or row[2:5] != ["FLOCK", "ADVISORY", "WRITE"]
            or not re.fullmatch(r"-?[0-9]+", row[5]) or row[7:] != ["0", "EOF"]):
        raise ValueError("Descriptor is not an exclusive whole-file advisory flock")
    match = re.fullmatch(r"([0-9a-fA-F]+):([0-9a-fA-F]+):([0-9]+)", row[6])
    if match is None or (int(match[1], 16), int(match[2], 16), int(match[3])) != (
            os.major(expected[0]), os.minor(expected[0]), expected[1]):
        raise ValueError("Descriptor lock metadata names a different inode")
    # The creator PID may have exited while descendants retain the same OFD.
    return tuple(row[2:])


def exclusive_descriptor(path, descriptor):
    """Borrow an FD; never acquire, upgrade, release, duplicate or close it."""
    if type(descriptor) is not int or descriptor < 3:
        raise ValueError("Inherited ownership requires a non-stdio integer descriptor")
    path = regular_path(canonical_path(path))
    try:
        expected = identity(os.fstat(descriptor))
        if identity(path.stat()) != expected:
            raise ValueError("Inherited descriptor differs from its canonical lock inode")
        first = lock_record(descriptor, expected)
        second = lock_record(descriptor, expected)
        if (second != first or identity(os.fstat(descriptor)) != expected
                or identity(regular_path(path).stat()) != expected):
            raise ValueError("Inherited descriptor changed during ownership observation")
    except (OSError, UnicodeError) as error:
        raise ValueError("Cannot prove inherited descriptor ownership") from error
    return True
