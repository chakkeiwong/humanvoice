"""Validate inherited size receipts under their original destination authority."""

import shutil
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_inventory_size_recovery import native_case, run_failed
from test_qualification_capture import codex, profile_for

from humanvoice import codex_runtime
from humanvoice.artifacts import digest, write_json
from humanvoice.model import ModelAdapter
from tools import inventory_size_recovery as sizing
from tools.inventory_history_adoption import no_inference
from tools.inventory_recovery_v3 import runtime, stage
from tools.inventory_recovery_v3.requests import NativeRequests

__all__ = ["codex", "native_case"]


@pytest.fixture
def inherited_size(native_case, codex, tmp_path, monkeypatch):
    rule = run_failed(native_case, native_case.snapshot)
    sizing.enable(native_case.snapshot, [rule])
    origin = tmp_path / "original"
    write_json(origin / "plan.json", {"snapshot": str(native_case.snapshot), "profile": codex.profile})
    copied = tmp_path / "successor"
    shutil.copytree(native_case.snapshot, copied)
    profile = profile_for(SimpleNamespace(**{**vars(codex), "snapshot": copied}), monkeypatch)
    proof = {"prefix": [], "rules": [rule], "rule_predecessor": str(origin), "predecessor": str(origin)}
    plan = {"snapshot": str(copied), "profile": profile, runtime.FIELD: {"split_rules": []}}
    return SimpleNamespace(rule=rule, plan=plan, proof=proof, original=native_case.snapshot,
                           copied=copied, origin=origin, output=tmp_path / "stage")


def files(root):
    return {str(path.relative_to(root)): (digest(path.read_bytes()), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("defect", [None, "copied_record", "copied_evidence", "missing_origin",
                                    "unlisted_receipt", "foreign_profile"])
def test_native_size_history_preserves_original_rights_and_exact_receipts(inherited_size, defect):
    case = inherited_size
    owner = SimpleNamespace(check=lambda: True)
    before = files(case.original), files(case.copied)
    with no_inference(), pytest.raises(ValueError, match="inference destination"):
        NativeRequests(case.plan, case.output, None, owner)
    assert before == (files(case.original), files(case.copied))
    reference = case.rule["failure"]["runtime_record"]
    folder = case.copied / Path(reference["path"]).parent
    if defect == "copied_record":
        path = case.copied / reference["path"]
        path.write_bytes(path.read_bytes() + b" ")
    elif defect == "copied_evidence":
        (folder / "response.json").write_text("{}")
    elif defect == "missing_origin":
        (case.original / reference["path"]).unlink()
    elif defect == "unlisted_receipt":
        case.proof["rules"] = []
    elif defect == "foreign_profile":
        write_json(case.origin / "plan.json", {"snapshot": str(case.original), "profile": case.plan["profile"]})
    before = files(case.original), files(case.copied)
    native = ModelAdapter.invoke, codex_runtime.validate_codex_record, sizing.validate_codex_record
    with no_inference(), stage.receipt_replay(case.plan, case.output, case.proof,
            codex_runtime.validate_codex_record) as checked, runtime.receipt_scope(checked):
        if defect is None:
            resolver = NativeRequests(case.plan, case.output, None, owner)
            assert resolver.size_rules == [case.rule]
        else:
            with pytest.raises((ValueError, OSError)):
                NativeRequests(case.plan, case.output, None, owner)
    assert native == (ModelAdapter.invoke, codex_runtime.validate_codex_record, sizing.validate_codex_record)
    assert before == (files(case.original), files(case.copied))


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_receipt_scope_does_not_authorize_a_changed_rule(inherited_size):
    case = inherited_size
    changed = deepcopy(case.rule)
    changed["children"].reverse()
    write_json(case.copied / sizing.MARKER, sizing.policy(case.copied, [changed]))
    with no_inference(), stage.receipt_replay(case.plan, case.output, case.proof,
            codex_runtime.validate_codex_record) as checked, runtime.receipt_scope(checked), (
            pytest.raises(sizing.SplitStopped, match="partition")):
        NativeRequests(case.plan, case.output, None, SimpleNamespace(check=lambda: True))
