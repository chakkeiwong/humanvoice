"""
Transmission tracking for the "unauthorized external transmission" never-except condition.

Per contract 1.1.0, "unauthorized external transmission" is a never-except condition.
This module logs every outbound API call so the release gate can verify that only
authorized transmissions occurred during authoring.

Authorized transmissions (internal evaluation):
- API calls to Anthropic during plan/draft/repair (operator-initiated, logged)
- Writing to local filesystem

Unauthorized (blocks release):
- Transmissions without operator authorization
- Future commands like `hv publish` or `hv upload` require explicit `--authorize` flag
"""

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Optional, Dict, Any


def log_transmission(
    snapshot_dir: Path,
    action: str,
    destination: str,
    purpose: str,
    content_summary: str,
    authorized_by: str = "operator",
) -> None:
    """
    Append a transmission record to the snapshot's transmission log.

    Called by model.py after each API invocation. The log lives in the snapshot
    manifest so release gates can read it.

    Args:
        snapshot_dir: Path to the snapshot directory
        action: "api_invocation", "file_write", "network_copy", etc.
        destination: Where the data went (e.g., "api.anthropic.com")
        purpose: Why ("plan_generation", "draft_generation", "repair_validation")
        content_summary: Brief description or hash (not the content itself)
        authorized_by: Who authorized ("operator", "release-gate", "unauthorized")
    """
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        # Snapshot not initialized; nothing to log to
        return

    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception:
        # Corrupt manifest; don't break the command
        return

    if "transmission_log" not in manifest:
        manifest["transmission_log"] = []

    manifest["transmission_log"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "destination": destination,
        "purpose": purpose,
        "content_summary": content_summary,
        "authorized_by": authorized_by,
    })

    try:
        manifest_path.write_text(json.dumps(manifest, indent=2))
    except Exception:
        # Write failed; don't break the command
        pass


def get_transmission_log(snapshot_dir: Path) -> list:
    """
    Read the transmission log from the snapshot manifest.

    Returns an empty list if no manifest or no log exists.
    """
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        return []

    try:
        manifest = json.loads(manifest_path.read_text())
        return manifest.get("transmission_log", [])
    except Exception:
        return []
