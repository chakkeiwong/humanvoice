"""
Canonical path resolution for humanvoice run records.

Single source of truth for where run records live. Before this module,
plan/draft wrote to Path.cwd()/.humanvoice/runs/ while every release gate read
snapshot_dir/.humanvoice/runs/ — the two never coincided unless cwd happened to
be the snapshot directory, so release gates saw no records and passed.

The snapshot is the authoritative artifact, so records live under it. A snapshot
directory is self-contained: everything needed to audit a release is inside it.
"""
from datetime import datetime, timezone
from pathlib import Path


def runs_dir(snapshot_dir: Path) -> Path:
    """
    Canonical runs directory for a snapshot.

    All commands that write run records, and all release gates that read them,
    must resolve through this function.
    """
    return Path(snapshot_dir).resolve() / ".humanvoice" / "runs"


def new_run_dir(snapshot_dir: Path, run_id: str = None) -> Path:
    """
    Create and return a fresh run directory under the snapshot.

    Passing run_id reuses an existing identifier; otherwise one is minted from
    the current UTC time.
    """
    if run_id is None:
        run_id = mint_run_id()
    d = runs_dir(snapshot_dir) / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def mint_run_id() -> str:
    """Timestamp-based run identifier."""
    return f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


def snapshot_dir_for_run(run_dir: Path) -> Path:
    """
    Recover the snapshot directory that owns a run directory.

    Inverse of new_run_dir. Needed by repair, which receives a draft path rather
    than a snapshot path and must find the snapshot to write records into.

    Layout: <snapshot>/.humanvoice/runs/<run_id>/, so the snapshot is three
    levels up. Returns None when run_dir is not inside a recognisable layout.
    """
    run_dir = Path(run_dir).resolve()
    for parent in [run_dir] + list(run_dir.parents):
        if parent.name == "runs" and parent.parent.name == ".humanvoice":
            return parent.parent.parent
    return None
