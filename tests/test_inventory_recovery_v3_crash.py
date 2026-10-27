"""Exercise native claim persistence after abrupt worker process death."""

import multiprocessing
import os
from pathlib import Path

import pytest
from test_failure_first_native import baseline, codex, prepared

from humanvoice.artifacts import read_json, write_json
from tools import sol_inventory_program as original
from tools.inventory_recovery_v2 import runtime as adapter
from tools.inventory_recovery_v3.claim import claim

__all__ = ["baseline", "codex", "prepared"]


def crash_claim(plan, output, account_path, boundary):
    native_write = original.epoch.write_json

    def write(path, value):
        native_write(path, value)
        selected = "account" if Path(path) == account_path else Path(path).name
        if selected == boundary:
            os._exit(73)

    original.epoch.write_json = write
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        claim(plan, output, account_path=account_path,
              owner_check=lambda: True, stop_check=lambda: None)
    os._exit(74)


@pytest.mark.parametrize("boundary", ["account", "account-reservation.json", "allocation-ledger.json"])
def test_process_death_replays_claim_once(prepared, boundary):
    _codex, account_path, plan, output, _request = prepared
    write_json(output / "execution.json", {"status": "prepared", "plan_identity": plan["plan_identity"],
               "model_calls": 0, "required": len(plan["calls"]), "human_evidence": False})
    marker = (output / "execution.json").read_bytes()
    process = multiprocessing.get_context("fork").Process(
        target=crash_claim, args=(plan, output, account_path, boundary))
    process.start()
    process.join(15)
    if process.is_alive():
        process.kill()
        process.join(5)
        pytest.fail("Crash fixture failed to reach native boundary")
    assert process.exitcode == 73
    before = account_path.read_bytes()
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        receipt = claim(plan, output, account_path=account_path,
                        owner_check=lambda: True, stop_check=lambda: None)
        assert account_path.read_bytes() == before
        events = [event for event in read_json(account_path)["events"] if event["kind"] == "reserve"
                  and event["entry"]["plan_identity"] == plan["plan_identity"]]
        assert events == [{"kind": "reserve", "entry": receipt["entry"]}]
        assert read_json(output / "allocation-ledger.json")["calls"] == []
        assert (output / "execution.json").read_bytes() == marker
