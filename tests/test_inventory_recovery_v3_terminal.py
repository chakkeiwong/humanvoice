"""User pauses veto unrelated terminal failures before any sealed mutation."""

import pytest

from humanvoice.artifacts import digest, write_json
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.terminal import finalize_failure


@pytest.mark.parametrize("condition", ["retained_pause", "late_stop", "late_owner_loss"])
def test_user_stop_or_owner_change_preserves_terminal(tmp_path, condition):
    plan = {"calls": [{"key": "inventory:0000"}]}
    plan["plan_identity"] = digest(plan)
    write_json(tmp_path / "plan.json", plan)
    write_json(tmp_path / "allocation-ledger.json", {"plan_identity": plan["plan_identity"],
               "calls": [], "reported_tokens": 0})
    write_json(tmp_path / "execution.json", {"status": "paused_user" if condition == "retained_pause"
               else "executing", "plan_identity": plan["plan_identity"]})
    before = (tmp_path / "execution.json").read_bytes()
    settled, owner_checks, stop_checks = [], [], []

    def owner():
        owner_checks.append(True)
        return not (condition == "late_owner_loss" and len(owner_checks) > 1)

    def stop():
        stop_checks.append(True)
        if condition == "late_stop" and len(stop_checks) > 1:
            raise RecoveryStop("USER_STOPPED", "stop arrived before commit")

    with pytest.raises(RecoveryStop):
        finalize_failure(tmp_path, {"plan_identity": plan["plan_identity"]},
                         RecoveryStop("BLOCKED_BUDGET", "unrelated failure"), phase="request",
                         settle=settled.append, owner_check=owner, stop_check=stop)
    assert (tmp_path / "execution.json").read_bytes() == before
    assert settled == []
    assert not (tmp_path / "allocation-seal.json").exists()
