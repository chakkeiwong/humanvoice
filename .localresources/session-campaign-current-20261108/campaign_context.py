"""Carry the proved receipt mapping and sealed-plan grant reader into campaigns."""

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / '.localresources/session-qualification-resume-20261108/repair.py'
GRANT = ROOT / '.localresources/session-qualification-shm-repair-20261108/grant_dispatch.py'
sys.path.insert(0, str(GRANT.parent))

import grant_dispatch

SPEC = importlib.util.spec_from_file_location('qualification_receipt_repair', RECEIPT)
receipt = sys.modules.get(SPEC.name)
if receipt is None:
    receipt = importlib.util.module_from_spec(SPEC)
    sys.modules[SPEC.name] = receipt
    SPEC.loader.exec_module(receipt)


def sources():
    packet = receipt.plan()
    return [Path(__file__), GRANT, receipt.PLAN, receipt.RECEIPT,
        *(Path(path) for path in packet['sources'])]


@contextmanager
def scope():
    receipt.plan()
    with receipt.receipt_scope(), grant_dispatch.scope():
        yield
