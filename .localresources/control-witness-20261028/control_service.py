"""Read-only witness daemon primitives, requiring protected host storage.

No CLI, installation, initialization, stop or resume action is provided here.
The prospective installer must bind the fixed protected paths and release.
"""

import os
import socket
import sqlite3
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from control_transport import serve_connection
from control_witness import WitnessError, require


def protected_directory(path):
    original = str(path)
    path = Path(path)
    require(path.is_absolute() and str(path) == original and ".." not in path.parts,
            "Protected directory is not canonical")
    for part in (path, *path.parents):
        info = part.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                and info.st_uid == 0 and info.st_mode & 0o022 == 0,
                "Witness directory must be protected from workspace writers")
    return path


def protected_database(path):
    path = Path(path)
    protected_directory(path.parent)
    for selected in (path, *(path.with_name(path.name + suffix) for suffix in ("-journal", "-wal", "-shm"))):
        try:
            info = selected.lstat()
        except FileNotFoundError:
            require(selected != path, "Host witness database is missing")
            continue
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0
                and info.st_mode & 0o077 == 0 and info.st_nlink == 1,
                "Witness database must be private, regular and host owned")
    return path


def protected_projection(path, *, owner=0):
    """Require root-protected parents and, if present, a private regular leaf.

    Projection publication uses a compare-before-rename sequence; it is safe
    against untrusted writers only when those writers cannot mutate the parent
    directory or the retained leaf between the check and replacement.
    """
    original = str(path)
    path = Path(path)
    require(path.is_absolute() and str(path) == original and ".." not in path.parts,
            "Control projection path is not canonical")
    protected_directory(path.parent)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return path
    require(stat.S_ISREG(info.st_mode) and info.st_uid == owner
            and info.st_nlink == 1 and info.st_mode & 0o022 == 0,
            "Control projection must be a protected regular file")
    return path


class ReadService:
    """One root-pinned read listener; bounded clients never reach writer calls."""

    def __init__(self, path, witness):
        self.path = Path(path)
        require(str(self.path) == str(path) and self.path.is_absolute()
                and ".." not in self.path.parts, "Service endpoint must be canonical")
        self.witness = witness

    def _check(self):
        require(os.geteuid() == 0, "Witness service must run as the protected host identity")
        protected_directory(self.path.parent)
        protected_database(self.witness.path)
        return True

    def serve(self, stop):
        self._check()
        # Existence is not proof of a dead listener; never unlink an old name
        # automatically. The admitted installer owns stale endpoint recovery.
        require(not os.path.lexists(self.path), "Witness listener already exists")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(self.path))
            owned = self.path.lstat()
            try:
                os.chmod(self.path, 0o666)
                server.listen(16)
                server.settimeout(0.1)
                slots = threading.BoundedSemaphore(4)
                with ThreadPoolExecutor(max_workers=4) as workers:
                    while not stop.is_set():
                        try:
                            connection, _ = server.accept()
                        except TimeoutError:
                            continue
                        if not slots.acquire(blocking=False):
                            connection.close()
                            continue

                        def handle(connection=connection):
                            try:
                                with connection:
                                    self._check()
                                    serve_connection(connection, self.witness)
                            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
                                # The reader gets a closed connection and a veto.
                                # Malformed clients cannot terminate the service.
                                pass
                            finally:
                                slots.release()

                        try:
                            workers.submit(handle)
                        except RuntimeError:
                            connection.close()
                            slots.release()
                            raise
            finally:
                try:
                    current = self.path.lstat()
                except FileNotFoundError:
                    current = None
                if current and (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                    self.path.unlink()


def check_host_storage(witness):
    """Read-only installer check; no creation or repair fallback."""
    protected_database(witness.path)
    try:
        return witness.snapshot("0" * 64)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        raise WitnessError("Protected witness is unreadable or malformed") from error
