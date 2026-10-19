import fcntl
import hashlib
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from humanvoice.artifacts import digest
from tools import archive_evidence as archive
from tools.inventory_transport_continuation import tree_hashes
from tools.settlement_replay_cache import EvidenceTree, SettlementReplayCache


@pytest.fixture
def relocated(tmp_path):
    target = tmp_path / "archive/stage"
    target.mkdir(parents=True)
    logical = tmp_path / "work/stage"
    logical.parent.mkdir()
    (target / "calls/0000").mkdir(parents=True)
    (target / "calls/0000/result.json").write_text('{"status":"pass"}')
    (target / "allocation-seal.json").write_text('{"sealed":true}')
    (target / "execution.lock").touch()
    logical.symlink_to(target, target_is_directory=True)
    return logical, target, archive.Archive({logical: target}, {"test": True})


def spawned_read(mapping, logical):
    with archive.access(mapping):
        return str(logical.resolve()), tree_hashes(logical), (logical / "execution.lock").open("a").writable()


def test_archive_logical_identity_content_and_scope_restoration(relocated):
    logical, target, mapping = relocated
    expected = tree_hashes(target)
    native_methods = Path.resolve, Path.is_symlink, Path.open, Path.glob
    with archive.access(mapping):
        assert logical.resolve() == logical
        assert (logical / "calls/0000/result.json").resolve() == logical / "calls/0000/result.json"
        assert tree_hashes(logical) == expected
        assert tree_hashes(logical.parent) == {"stage/" + key: value for key, value in expected.items()}
        assert list(logical.parent.glob("stage/calls/*/result.json")) == [logical / "calls/0000/result.json"]
        with archive.access() as nested:
            assert nested is mapping
    assert (Path.resolve, Path.is_symlink, Path.open, Path.glob) == native_methods
    assert logical.is_symlink() and logical.resolve() == target


def test_archive_scope_restores_after_failure(relocated):
    logical, target, mapping = relocated
    with pytest.raises(RuntimeError):
        with archive.access(mapping):
            raise RuntimeError("stop")
    assert logical.resolve() == target
    assert EvidenceTree is __import__("tools.settlement_replay_cache", fromlist=["EvidenceTree"]).EvidenceTree


def test_archive_settlement_cache_rechecks_original_bytes(relocated):
    logical, target, mapping = relocated
    report = {"output": str(logical), "evidence_hashes": tree_hashes(target)}
    cache, reads = SettlementReplayCache(), []

    def reader(output):
        reads.append(output)
        assert tree_hashes(output) == report["evidence_hashes"]
        return report

    with archive.access(mapping):
        assert cache.read(logical, reader) == report
        assert cache.read(logical, reader) == report
        assert reads == [logical]
        (target / "calls/0000/result.json").write_text('{"status":"tampered"}')
        with pytest.raises(AssertionError):
            cache.read(logical, reader)


def test_archive_preserves_native_account_reservation_identity(relocated):
    from humanvoice.automatic_settlement import BASE_ACCOUNT_ALLOWANCE, RESERVATION, bound_account_allowance

    logical, target, mapping = relocated
    plan = {"plan_identity": "frozen-plan", "calls": [{}], "prior_reservation_ceiling": RESERVATION}
    entry = {"plan_identity": "frozen-plan", "output": str(logical), "calls": 1,
             "reserved_tokens": RESERVATION, "prior_reservation_ceiling": RESERVATION}
    receipt = {"entry": entry, "entry_hash": digest(entry), "unknown_tokens_released": False}
    with pytest.raises(ValueError, match="differs"):
        bound_account_allowance(logical, plan, receipt=receipt)
    before = json.dumps(receipt)
    with archive.access(mapping):
        assert bound_account_allowance(logical, plan, receipt=receipt) == BASE_ACCOUNT_ALLOWANCE
    assert json.dumps(receipt) == before


def test_archive_descriptor_readers_keep_native_validation(relocated):
    from humanvoice import policy
    from tools import baseline_replay_cache

    logical, target, mapping = relocated
    expected = baseline_replay_cache.tree_state(target, ["calls", "allocation-seal.json"])
    native_read = policy._read_regular_file
    with archive.access(mapping):
        assert policy._read_regular_file(logical / "allocation-seal.json") == b'{"sealed":true}'
        assert baseline_replay_cache.tree_state(logical, ["calls", "allocation-seal.json"]) == expected
        (target / "unsafe.json").symlink_to(target / "allocation-seal.json")
        with pytest.raises(ValueError, match="unexpected alias"):
            policy._read_regular_file(logical / "unsafe.json")
    assert policy._read_regular_file is native_read


def test_archive_read_only_locks_and_writes(relocated):
    logical, target, mapping = relocated
    with archive.access(mapping):
        with (logical / "execution.lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            assert not handle.writable()
        for name, mode in (("allocation-seal.json", "w"), ("new.json", "w"),
                           ("execution.lock", "a+"), ("new.lock", "a")):
            with pytest.raises(ValueError, match="read-only"):
                (logical / name).open(mode)
    assert (target / "execution.lock").stat().st_size == 0


@pytest.mark.parametrize("mutation", ["retarget", "missing", "nested"])
def test_archive_rejects_changed_aliases(relocated, mutation):
    logical, target, mapping = relocated
    if mutation == "retarget":
        logical.unlink()
        logical.symlink_to(logical.parent, target_is_directory=True)
    elif mutation == "missing":
        logical.unlink()
    else:
        (target / "unexpected").symlink_to(logical.parent, target_is_directory=True)
    with archive.access(mapping), pytest.raises(ValueError, match="alias"):
        (logical / "unexpected" if mutation == "nested" else logical).resolve()


def test_archive_rejects_unapproved_symlinks(relocated):
    logical, target, mapping = relocated
    (logical.parent / "unapproved").symlink_to(target, target_is_directory=True)
    with archive.access(mapping), pytest.raises(ValueError, match="symbolic links"):
        tree_hashes(logical.parent)


def test_archive_individual_file_and_child_process(relocated):
    logical, target, mapping = relocated
    original_file = logical.parent / "retained.json"
    original_file.symlink_to(target / "allocation-seal.json")
    mapping.mappings[original_file] = target / "allocation-seal.json"
    with archive.access(mapping):
        assert not original_file.is_symlink()
        assert original_file.resolve() == original_file
        assert json.loads(original_file.read_text()) == {"sealed": True}
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
        identity, hashes, writable = pool.submit(spawned_read, mapping, logical).result(timeout=30)
    assert identity == str(logical) and hashes == tree_hashes(target) and not writable


def test_archive_rejects_changed_receipt(tmp_path, monkeypatch):
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}")
    monkeypatch.setattr(archive, "RECEIPT", receipt)
    with pytest.raises(ValueError, match="receipt changed"):
        archive.load()


def test_archive_image_checksum_detects_content_change(tmp_path):
    image = tmp_path / "image"
    image.write_bytes(b"original")
    assert archive.image_hash(image) == hashlib.sha256(b"original").hexdigest()
    image.write_bytes(b"modified")
    assert archive.image_hash(image) == hashlib.sha256(b"modified").hexdigest()
