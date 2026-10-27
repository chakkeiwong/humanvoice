"""Native seal/account commits remain idempotent after interrupted finalization."""

from pathlib import Path

import pytest
from test_failure_first_native import baseline, codex, prepared

from humanvoice.artifacts import digest, read_json
from humanvoice.model import ModelAdapter, ModelConfig
from tools import sol_inventory_program as original
from tools.inventory_recovery_v2 import execution
from tools.inventory_recovery_v2 import runtime as adapter
from tools.inventory_recovery_v3.terminal import finalize_failure

__all__ = ["baseline", "codex", "prepared"]


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("cut", ["seal", "account"])
def test_native_settlement_commit_replays_without_duplicate_charge(prepared, monkeypatch, cut):
    codex, account_path, plan, output, request = prepared
    with original.epoch.accounting_scope(), adapter.settlement_scope(), (
            adapter.implementation.qualified.accounting.accounting_scope()):
        original.epoch.claim(plan, output, account_path=account_path)
        ledger = original.epoch.EpochLedger(output / "allocation-ledger.json", plan)
        with adapter.implementation.automatic_recovery.exclusive_execution(output), adapter.runtime(
                plan, output, live=True, lock_fd=adapter.implementation.automatic_recovery.execution_fds()[0]):
            model = ModelAdapter(ModelConfig.from_profile(), snapshot_dir=codex.snapshot)
            with execution.accounted_model(output, plan, ledger):
                model.invoke(**request)
            native_save, native_write = original.account.save, original.account.write_json
            interrupted = []

            def save(path, record):
                native_save(path, record)
                if cut == "seal" and Path(path).name == "allocation-seal.json" and not interrupted:
                    interrupted.append(True)
                    raise OSError("crash after seal")

            def write(path, record):
                native_write(path, record)
                if cut == "account" and Path(path) == account_path and not interrupted:
                    interrupted.append(True)
                    raise OSError("crash after account event")

            monkeypatch.setattr(original.account, "save", save)
            monkeypatch.setattr(original.account, "write_json", write)
            arguments = {"phase": "request", "owner_check": lambda: True,
                         "stop_check": lambda: None,
                         "settle": lambda root: original.account.settle(root, account=account_path)}
            summary = {"plan_identity": plan["plan_identity"]}
            error = execution.RecoveryBlocked("BLOCKED_BUDGET", "fixture limit")
            with pytest.raises(OSError, match="crash after"):
                finalize_failure(output, summary, error, **arguments)
            assert interrupted == [True]
            terminal = read_json(output / "execution.json")
            sealed = (output / "allocation-seal.json").read_bytes()
            assert read_json(output / "allocation-seal.json")["terminal_hash"] == digest(terminal)
            finalize_failure(output, summary, error, **arguments)
            retained = account_path.read_bytes()
            finalize_failure(output, summary, error, **arguments)
            assert account_path.read_bytes() == retained
            assert (output / "allocation-seal.json").read_bytes() == sealed
            events = [event for event in read_json(account_path)["events"] if event["kind"] == "settle"
                      and event["usage"]["plan_identity"] == plan["plan_identity"]]
            assert len(events) == 1
            assert events[0]["usage"]["allocated_calls"] == 2
            assert events[0]["usage"]["retained_tokens"] == 1088000
