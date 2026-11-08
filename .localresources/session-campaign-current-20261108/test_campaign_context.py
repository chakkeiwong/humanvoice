"""Every public child retains proved grant-reader ordering and restores context."""

import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import campaign_context
import campaign_entry
import preparation_adapter
import pytest

from tools import automatic_call_grant as grants
from tools.inventory_recovery_v3 import accounting, runtime


def test_context_binds_receipt_and_grant_without_replacing_dispatch(monkeypatch):
    original_receipt = campaign_context.receipt.archive.RECEIPT
    original_reader = grants.settled_usage
    dispatcher = accounting.completed_usage
    monkeypatch.setattr(accounting, 'verify_settlement', lambda output: {'report': {'output': output}})
    with pytest.raises(RuntimeError, match='stop'), campaign_context.scope(), runtime.settlement_scope():
        assert campaign_context.receipt.archive.RECEIPT == campaign_context.receipt.RECEIPT
        assert accounting.completed_usage is dispatcher
        assert grants.settled_usage('historical') == {'output': 'historical'}
        raise RuntimeError('stop')
    assert campaign_context.receipt.archive.RECEIPT == original_receipt
    assert grants.settled_usage is original_reader


def test_public_and_preparation_install_context_before_copying_grant(monkeypatch):
    order = []

    @contextmanager
    def context():
        order.append('context')
        yield
        order.append('restored')

    @contextmanager
    def grant(*args, **kwargs):
        assert order[-1] == 'context'
        order.append('grant')
        yield

    @contextmanager
    def empty(*args, **kwargs):
        yield {}

    monkeypatch.setattr(campaign_context, 'scope', context)
    monkeypatch.setattr(campaign_entry.grant_extension, 'scope', grant)
    monkeypatch.setattr(campaign_entry.migration_runtime, 'scope', empty)
    monkeypatch.setattr(campaign_entry.finalization_cache, 'scope', empty)
    monkeypatch.setattr(preparation_adapter, 'source_scope', empty)
    active = {'inputs': {'call_authorization': {'path': '/fixture/grant', 'sha256': 'fixture'}}}
    monkeypatch.setattr(campaign_entry, 'activation', lambda: (active, {}))
    with campaign_entry.scope():
        assert order == ['context', 'grant']
    assert order == ['context', 'grant', 'restored']
    order.clear()
    monkeypatch.setattr(preparation_adapter, 'projected_prepare', lambda *_: lambda **_: 'prepared')
    assert preparation_adapter.prepare({}, {}, {}, authorization_path='/fixture/grant',
        authorization_sha256='fixture') == 'prepared'
    assert order == ['context', 'grant', 'restored']
