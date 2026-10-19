"""Read verified archive aliases without changing frozen evidence identities."""

import atexit
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT.parent / "storage-cleanup-20261019"
RECEIPT = PACKET / "humanvoice/receipt.json"
MOUNT = PACKET / "mounts/humanvoice"
RECEIPT_SHA256 = "93fb81d5504fc4adc29bd0cdd0f3713e70e8762aa044487fe72343b0e992b272"
IMAGE_SHA256 = "278400fb21fa91ab0c0dd03efbe15a4bbe15cecca252172d45f5e6b31896c642"
VERSION = "verified-archive-aliases-v1"
NATIVE_RESOLVE, NATIVE_LINK = Path.resolve, Path.is_symlink
NATIVE_OPEN, NATIVE_GLOB = Path.open, Path.glob
_active = None


def file_identity(path):
    status = path.stat()
    return tuple(getattr(status, name) for name in
                 ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"))


def image_hash(path):
    before = file_identity(path)
    with NATIVE_OPEN(path, "rb") as stream:
        result = hashlib.file_digest(stream, "sha256").hexdigest()
    if file_identity(path) != before:
        raise ValueError("Archive image changed while verifying its checksum")
    return result


class Archive:
    def __init__(self, mappings, identity):
        self.mappings = dict(mappings)
        self.identity = identity

    def physical(self, path, *, strict=False):
        absolute = Path(os.path.abspath(path))
        for original in (absolute, *absolute.parents):
            target = self.mappings.get(original)
            if target is None:
                continue
            if not NATIVE_LINK(original) or os.readlink(original) != str(target):
                raise ValueError("Verified archive alias changed: " + str(original))
            expected = target / absolute.relative_to(original)
            actual = NATIVE_RESOLVE(path, strict=strict)
            if actual != expected or NATIVE_RESOLVE(target, strict=True) != target:
                raise ValueError("Archive evidence traverses an unexpected alias: " + str(absolute))
            return expected
        return None

    def resolve(self, path, strict=False):
        physical = self.physical(path, strict=strict)
        return Path(os.path.abspath(path)) if physical is not None else NATIVE_RESOLVE(path, strict=strict)

    def is_symlink(self, path):
        if Path(os.path.abspath(path)) in self.mappings:
            self.physical(path, strict=True)
            return False
        return NATIVE_LINK(path)

    def open(self, path, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        physical = self.physical(path)
        if physical is not None and any(flag in mode for flag in "wax+"):
            if mode == "a" and path.name.endswith(".lock") and physical.is_file() and physical.stat().st_size == 0:
                return NATIVE_OPEN(physical, "rb")
            raise ValueError("Archived evidence is read-only: " + str(path))
        return NATIVE_OPEN(path, mode, buffering, encoding, errors, newline)

    def glob(self, path, pattern, *, case_sensitive=None, recurse_symlinks=False):
        absolute = Path(os.path.abspath(path))
        descendants = [(original, target) for original, target in self.mappings.items()
                       if original != absolute and original.is_relative_to(absolute)]
        seen = set()
        for member in NATIVE_GLOB(path, pattern, case_sensitive=case_sensitive, recurse_symlinks=recurse_symlinks):
            seen.add(member)
            yield member
        for original, target in descendants:
            self.physical(original, strict=True)
            if target.is_dir():
                for member in NATIVE_GLOB(target, "**/*", case_sensitive=case_sensitive):
                    logical = original / member.relative_to(target)
                    if logical.relative_to(absolute).full_match(pattern, case_sensitive=case_sensitive):
                        member = path / logical.relative_to(absolute)
                        if member not in seen:
                            seen.add(member)
                            yield member


def load():
    raw = RECEIPT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise ValueError("Archive relocation receipt changed")
    receipt = json.loads(raw)
    image = Path(receipt["image"])
    if (receipt["status"] != "COMPLETE" or receipt["name"] != ROOT.name
            or receipt["all_members_sha256_verified"] is not True
            or receipt["image_sha256"] != IMAGE_SHA256 or image.stat().st_size != receipt["image_bytes"]
            or image_hash(image) != IMAGE_SHA256):
        raise ValueError("Archive image differs from its verified relocation receipt")
    if not MOUNT.is_mount() or not os.statvfs(MOUNT).f_flag & os.ST_RDONLY:
        raise ValueError("Verified archive must be mounted read-only")
    mappings = {}
    for entry in receipt["entries"]:
        if entry["status"] != "COMPLETE":
            continue
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.parts[:3] != (ROOT.name, "docs", "audits"):
            raise ValueError("Archive mapping is outside historical evidence")
        original, target = ROOT.parent / relative, MOUNT / relative
        if original in mappings or any(original.is_relative_to(prior) or prior.is_relative_to(original) for prior in mappings):
            raise ValueError("Archive mappings overlap")
        mappings[original] = target
    archive = Archive(mappings, {"version": VERSION, "receipt_sha256": RECEIPT_SHA256,
                                "image_sha256": IMAGE_SHA256, "aliases": len(mappings)})
    for original in mappings:
        archive.physical(original, strict=True)
    return archive


def initialize_worker():
    context = access()
    context.__enter__()
    atexit.register(context.__exit__, None, None, None)


def identity():
    with access() as archive:
        return archive.identity


def replace_aliases(original, replacement):
    for name, module in list(sys.modules.items()):
        if module is None or name == __name__ or not name.startswith(("humanvoice.", "tools.")):
            continue
        for attribute, value in list(vars(module).items()):
            if value is original:
                setattr(module, attribute, replacement)


@contextmanager
def access(archive=None):
    global _active
    if _active is not None:
        if archive is not None and archive is not _active:
            raise ValueError("Cannot replace an active archive mapping")
        yield _active
        return
    from tools import parallel_verification_replay, settlement_replay_cache
    from humanvoice import policy

    archive = load() if archive is None else archive
    native_tree = settlement_replay_cache.EvidenceTree
    native_pool = parallel_verification_replay.ProcessPoolExecutor
    native_read = policy._read_regular_file

    class ArchivedEvidenceTree(native_tree):
        def __init__(self, root):
            super().__init__(archive.physical(root, strict=True) or root)

    def pool(*arguments, **keywords):
        if "initializer" in keywords:
            raise ValueError("Archive verification cannot replace another process initializer")
        return native_pool(*arguments, initializer=initialize_worker, **keywords)

    def read_regular_file(path):
        return native_read(archive.physical(path, strict=True) or path)

    Path.resolve = lambda path, strict=False: archive.resolve(path, strict)
    Path.is_symlink = lambda path: archive.is_symlink(path)
    Path.open = lambda path, *args, **kwargs: archive.open(path, *args, **kwargs)
    Path.glob = lambda path, *args, **kwargs: archive.glob(path, *args, **kwargs)
    replace_aliases(native_tree, ArchivedEvidenceTree)
    replace_aliases(native_read, read_regular_file)
    parallel_verification_replay.ProcessPoolExecutor = pool
    _active = archive
    try:
        yield archive
    finally:
        _active = None
        Path.resolve, Path.is_symlink = NATIVE_RESOLVE, NATIVE_LINK
        Path.open, Path.glob = NATIVE_OPEN, NATIVE_GLOB
        replace_aliases(ArchivedEvidenceTree, native_tree)
        replace_aliases(read_regular_file, native_read)
        parallel_verification_replay.ProcessPoolExecutor = native_pool
