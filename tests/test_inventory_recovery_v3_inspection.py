"""Native warmup inspection keeps validation but suppresses publication."""

import pytest
from test_inventory_recovery_v3_policy import reservations

from tools import parallel_verification_replay as verification
from tools.inventory_recovery_v3 import inspection
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.ownership_preflight import RetainedJournal


@pytest.mark.parametrize("invalid", [False, True])
def test_nonpublishing_native_warmup_restores_aliases_on_error(tmp_path, monkeypatch, invalid):
    destination = tmp_path / "warmup.json"
    destination.write_text("retained report")
    before = destination.read_bytes(), destination.stat().st_mtime_ns
    native = verification.warm_settlements
    writes = []

    def forbidden(*arguments, **keywords):
        writes.append(arguments)
        raise AssertionError("Read-only replay attempted diagnostic publication")

    monkeypatch.setattr(verification, "write_json", forbidden)
    with inspection.nonpublishing():
        if invalid:
            with pytest.raises(ValueError, match="workers"):
                verification.warm_settlements({"events": []}, workers=0, progress=destination)
        else:
            _cache, report = verification.warm_settlements({"events": []}, workers=16, progress=destination)
            assert report["status"] == "pass" and report["completed"] == 0
    assert verification.warm_settlements is native
    assert not writes and before == (destination.read_bytes(), destination.stat().st_mtime_ns)


def test_nonpublishing_native_worker_failure_is_not_suppressed(tmp_path, monkeypatch):
    destination = tmp_path / "warmup.json"
    native = verification.warm_settlements
    observed = []

    def fail_pool(**keywords):
        observed.append(keywords["max_workers"])
        raise OSError("fixture native worker failure")

    monkeypatch.setattr(verification, "ProcessPoolExecutor", fail_pool)
    record = {"events": [{"kind": "settle", "usage": {"output": str(tmp_path / "settled")}}]}
    with pytest.raises(OSError, match="native worker failure"), inspection.nonpublishing():
        verification.warm_settlements(record, workers=16, progress=destination)
    assert observed == [1] and not destination.exists()
    assert verification.warm_settlements is native


def test_retained_journal_rejects_missing_membership_without_repair(tmp_path):
    native = reservations(tmp_path / "journal")
    root = native.register_root(purpose="concept_extraction", owned=["existing"])
    record = native.read()
    retained = RetainedJournal(native.root, native.policy, native.binding, record, lambda: True)
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns)
              for path in native.root.iterdir() if path.is_file()}
    assert retained.register_root(purpose="concept_extraction", owned=["existing"]) == root
    with pytest.raises(RecoveryStop, match="missing journal membership"):
        retained.register_root(purpose="concept_extraction", owned=["missing"])
    value = retained.reserve(lineage=root["identity"], incident="incident", request_hash="request",
                             profile_hash="profile", check_only=True)
    assert value["lineage"] == root["identity"] and retained.read() == record
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns)
                      for path in native.root.iterdir() if path.is_file()}


def test_retained_journal_checks_owner_even_for_idempotent_reads(tmp_path):
    native = reservations(tmp_path / "journal")
    retained = RetainedJournal(native.root, native.policy, native.binding, native.read(), lambda: False)
    with pytest.raises(RecoveryStop, match="ownership"):
        retained.read()
