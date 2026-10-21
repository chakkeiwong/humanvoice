"""Materialize an archived ZLB snapshot on SSD without rewriting its evidence."""

import os
import shutil
from pathlib import Path

from humanvoice.artifacts import digest, read_json, validate_snapshot
from tools import archive_evidence as archive
from tools.inventory_transport_continuation import immutable, tree_hashes

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/audits/2026-10-05/master-program/automatic-execution"
SOURCE = BASE / "zlb-live/snapshot-20261012-manuscript-recovery-02"
WORK = BASE / "zlb-ssd-20261021-snapshot"
STAGE = BASE / "zlb-inventory-20261012-writer-policy-repaired-01"
EVIDENCE = BASE / "zlb-ssd-recovery-20261021"
ORIGIN = EVIDENCE / "workspace-origin.json"
VERSION = "zlb-ssd-workspace-v1"


def workspace(source, destination, receipt, *, archive_identity, allow_progress=False):
    source, destination, receipt = Path(source), Path(destination), Path(receipt)
    if (destination.resolve() == source.resolve() or destination.is_relative_to(source)
            or source.is_relative_to(destination) or archive.NATIVE_RESOLVE(destination) != destination.absolute()):
        raise ValueError("SSD workspace must be separate and must not traverse archive aliases")
    manifest, hashes = validate_snapshot(source), tree_hashes(source)
    expected = {"version": VERSION, "source": str(source), "destination": str(destination),
                "archive": archive_identity, "source_files": hashes, "manifest_hash": digest(manifest),
                "source_hash": manifest["source_hash"], "model_calls": 0}
    expected["identity"] = digest(expected)
    existed = receipt.exists()
    if destination.exists() and not existed:
        raise ValueError("Existing workspace lacks its frozen origin receipt")
    immutable(receipt, expected)
    if not destination.exists():
        pending = destination.with_name(destination.name + ".copying")
        if not pending.exists():
            shutil.copytree(source, pending)
        if tree_hashes(pending) != hashes:
            raise ValueError("Incomplete SSD copy must be reconciled before execution")
        pending.rename(destination)
    current = tree_hashes(destination)
    if (any(current.get(name) != value for name, value in hashes.items())
            or not allow_progress and current != hashes or validate_snapshot(destination) != manifest):
        raise ValueError("SSD workspace changed inherited source or evidence")
    if os.statvfs(destination).f_flag & os.ST_RDONLY:
        raise ValueError("SSD workspace is not writable")
    if tree_hashes(source) != hashes:
        raise ValueError("Archive source changed while materializing its workspace")
    return expected


def ensure(*, allow_progress=False):
    with archive.access() as mapping:
        if mapping.physical(SOURCE, strict=True) is None or mapping.physical(WORK) is not None:
            raise ValueError("ZLB recovery requires an archived source and separate SSD destination")
        return workspace(SOURCE, WORK, ORIGIN, archive_identity=mapping.identity, allow_progress=allow_progress)


def route(name, row):
    if name != "zlb":
        return row
    if BASE / row["snapshot"] != SOURCE:
        raise ValueError("ZLB workspace routing changed the frozen source selection")
    ensure(allow_progress=True)
    if (STAGE / "plan.json").exists() and read_json(STAGE / "plan.json")["snapshot"] != str(WORK):
        raise ValueError("Retained ZLB stage uses another working snapshot")
    return {**row, "snapshot": str(WORK.relative_to(BASE))}
