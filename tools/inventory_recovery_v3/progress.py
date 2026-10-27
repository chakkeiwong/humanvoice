"""Watch all admitted stages without treating a heartbeat as business progress."""

from pathlib import Path

from tools.inventory_recovery_v3.policy import validate_policy


def watch_config(configuration, campaign_root, policy):
    validate_policy(policy)
    root = Path(campaign_root)
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("Progress requires a canonical absolute campaign directory")
    paths = list(configuration["progress_files"])
    for generation in range(policy["maximum_generations"]):
        stage = root / f"generation-{generation:02d}"
        paths.extend(str(stage / name) for name in
                     ("execution.json", "progress.json", "allocation-ledger.json"))
    return {**configuration, "progress_files": list(dict.fromkeys(paths)),
            "recovery_policy_identity": policy["identity"]}
