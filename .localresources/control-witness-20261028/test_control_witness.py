"""Offline storage tests; these do not establish a protected host service."""

import json
import multiprocessing
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from control_witness import Witness, WitnessError, checksum, encode

GENESIS = checksum({"genesis": "fixture"})
CONFIG = checksum({"configuration": "fixture"})
NONCE = "a" * 64


def command(request="stop-1"):
    return {"request_id": request, "action": "stop",
            "roots": ["/fixture/root"], "content": "exact\r\nbytes"}


def open_witness(path):
    return Witness(path, genesis=GENESIS, configuration=CONFIG)


@pytest.fixture
def witness(tmp_path):
    value = open_witness(tmp_path / "witness.sqlite")
    value.initialize()
    return value


def test_prepare_survives_cold_restart_and_commits_exactly_once(witness):
    initial = witness.snapshot(NONCE)
    assert initial["sequence"] == 0 and initial["pending"] is None
    prepared = witness.prepare(0, GENESIS, command())
    restarted = open_witness(witness.path)
    pending = restarted.snapshot("b" * 64)
    assert pending["pending"] == prepared["event"]
    assert pending["nonce"] != initial["nonce"]
    assert pending["pending"]["command"]["content"] == "exact\r\nbytes"
    assert restarted.prepare(0, GENESIS, command()) == prepared
    event = restarted.commit(1, prepared["event"]["identity"])
    assert restarted.commit(1, event["identity"]) == event
    assert restarted.prepare(0, GENESIS, command()) == {"status": "committed", "event": event}
    final = restarted.snapshot(NONCE)
    assert final["sequence"] == 1 and final["pending"] is None
    assert final["events"] == [event]


@pytest.mark.parametrize("kind", ["different_pending", "stale_sequence", "stale_head",
    "wrong_commit", "skip_commit", "boolean_sequence", "negative_sequence"])
def test_conflicting_transactions_cannot_advance_or_replace_pending(witness, kind):
    event = witness.prepare(0, GENESIS, command())["event"]
    before = witness.snapshot(NONCE)
    with pytest.raises(WitnessError):
        if kind == "different_pending":
            witness.prepare(0, GENESIS, command("another"))
        elif kind == "stale_sequence":
            witness.prepare(1, GENESIS, command())
        elif kind == "stale_head":
            witness.prepare(0, CONFIG, command())
        elif kind == "wrong_commit":
            witness.commit(1, CONFIG)
        elif kind == "skip_commit":
            witness.commit(2, event["identity"])
        elif kind == "boolean_sequence":
            witness.prepare(False, GENESIS, command())
        else:
            witness.prepare(-1, GENESIS, command())
    assert witness.snapshot(NONCE) == before


def test_prior_exact_retry_preserves_later_pending_transaction(witness):
    first = witness.prepare(0, GENESIS, command())["event"]
    witness.commit(1, first["identity"])
    second = witness.prepare(1, first["identity"], command("second"))["event"]
    before = witness.snapshot(NONCE)
    assert witness.commit(1, first["identity"]) == first
    assert witness.prepare(0, GENESIS, command())["status"] == "committed"
    assert witness.snapshot(NONCE) == before
    assert before["pending"] == second
    with pytest.raises(WitnessError, match="Request ID"):
        witness.prepare(1, first["identity"], command())


@pytest.mark.parametrize("bad", [None, [], {}, {"request_id": ""},
    {"request_id": "x", "bad": float("nan")},
    {"request_id": "x", "bad": (1, 2)},
    {"request_id": "x", "huge": "x" * 1_048_576}])
def test_invalid_commands_fail_before_witness_mutation(witness, bad):
    before = witness.snapshot(NONCE)
    with pytest.raises(WitnessError):
        witness.prepare(0, GENESIS, bad)
    assert witness.snapshot(NONCE) == before


@pytest.mark.parametrize("target", ["binding", "head", "event", "event_bytes", "pending"])
def test_deleted_or_altered_members_are_not_reconstructed(witness, target):
    first = witness.prepare(0, GENESIS, command())["event"]
    witness.commit(1, first["identity"])
    witness.prepare(1, first["identity"], command("second"))
    with sqlite3.connect(witness.path) as db:
        if target in {"binding", "head"}:
            db.execute("DELETE FROM " + target)
        elif target == "event":
            db.execute("DELETE FROM events")
        elif target == "event_bytes":
            db.execute("UPDATE events SET body=body || ' '")
        else:
            db.execute("UPDATE head SET pending=?", (encode({"forged": True}),))
    before = witness.path.read_bytes()
    with pytest.raises((WitnessError, KeyError)):
        witness.snapshot(NONCE)
    assert witness.path.read_bytes() == before


@pytest.mark.parametrize("kind", ["missing", "empty", "symlink", "directory", "journal_alias"])
def test_invalid_database_is_never_initialized_by_reader(witness, kind, tmp_path):
    path = witness.path
    if kind == "missing":
        path.unlink()
    elif kind == "empty":
        path.write_bytes(b"")
    elif kind == "symlink":
        saved = tmp_path / "saved.sqlite"
        path.rename(saved)
        path.symlink_to(saved)
    elif kind == "directory":
        path.unlink()
        path.mkdir()
    else:
        path.with_name(path.name + "-journal").symlink_to(tmp_path / "missing-journal")
    with pytest.raises((WitnessError, sqlite3.DatabaseError)):
        witness.snapshot(NONCE)
    if kind == "missing":
        assert not path.exists()


def test_existing_store_cannot_be_reinitialized_or_rebound(witness):
    before = witness.path.read_bytes()
    with pytest.raises(FileExistsError):
        witness.initialize()
    with pytest.raises(WitnessError, match="binding|genesis"):
        Witness(witness.path, genesis=CONFIG, configuration=CONFIG).snapshot(NONCE)
    assert witness.path.read_bytes() == before


def test_concurrent_prepares_have_one_durable_winner(witness):
    def attempt(index):
        try:
            return open_witness(witness.path).prepare(0, GENESIS, command(str(index)))
        except WitnessError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    winners = [result for result in results if result]
    assert len(winners) == 1
    assert witness.snapshot(NONCE)["pending"] == winners[0]["event"]


def crash_at(path, cut, event):
    witness = open_witness(path)
    if cut == "prepare_uncommitted":
        with witness._connect(write=True) as db:
            db.execute("UPDATE head SET pending=?", (encode(event),))
            os._exit(81)
    elif cut == "prepare_committed":
        witness.prepare(0, GENESIS, command())
        os._exit(82)
    elif cut == "commit_uncommitted":
        with witness._connect(write=True) as db:
            db.execute("INSERT INTO events VALUES (?,?,?,?)",
                       (1, event["identity"], event["command"]["request_id"], encode(event)))
            db.execute("UPDATE head SET sequence=1,identity=?,pending=NULL", (event["identity"],))
            os._exit(83)
    else:
        witness.commit(1, event["identity"])
        os._exit(84)


@pytest.mark.parametrize("cut", ["prepare_uncommitted", "prepare_committed",
                                     "commit_uncommitted", "commit_committed"])
def test_real_process_death_preserves_atomic_witness_transactions(witness, cut):
    event = witness.event(1, GENESIS, command())
    if cut.startswith("commit_"):
        witness.prepare(0, GENESIS, command())
    child = multiprocessing.get_context("spawn").Process(target=crash_at, args=(witness.path, cut, event))
    child.start()
    child.join(10)
    if child.is_alive():
        child.kill()
        child.join(5)
        pytest.fail("Crash test child did not exit")
    assert child.exitcode in {81, 82, 83, 84}
    reopened = open_witness(witness.path)
    state = reopened.snapshot(NONCE)
    assert state["sequence"] == int(cut == "commit_committed")
    assert (state["pending"] is not None) == (cut in {"prepare_committed", "commit_uncommitted"})
    prepared = reopened.prepare(0, GENESIS, command())
    assert prepared["event"] == event
    reopened.commit(1, event["identity"])
    assert reopened.snapshot(NONCE)["events"] == [event]


def test_reader_does_not_modify_database_or_create_sidecars(witness):
    witness.prepare(0, GENESIS, command())
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in witness.path.parent.iterdir()}
    for nonce in ("b" * 64, "c" * 64):
        assert witness.snapshot(nonce)["nonce"] == nonce
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in witness.path.parent.iterdir()}


def test_stale_nonce_cannot_match_current_challenge(witness):
    old = witness.snapshot(NONCE)
    fresh = witness.snapshot("b" * 64)
    assert old["nonce"] != fresh["nonce"]
    assert old["identity"] != fresh["identity"]
    assert json.loads(encode(fresh)) == fresh


@pytest.mark.parametrize("operation", ["prepare", "commit"])
def test_storage_failure_rolls_back_without_losing_pending_intent(witness, operation):
    if operation == "commit":
        event = witness.prepare(0, GENESIS, command())["event"]
    before = witness.snapshot(NONCE)
    with sqlite3.connect(witness.path) as db:
        db.execute("CREATE TRIGGER fail_head BEFORE UPDATE ON head "
                   "BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="injected storage failure"):
        if operation == "prepare":
            witness.prepare(0, GENESIS, command())
        else:
            witness.commit(1, event["identity"])
    assert witness.snapshot(NONCE) == before
    with sqlite3.connect(witness.path) as db:
        db.execute("DROP TRIGGER fail_head")
    event = witness.prepare(0, GENESIS, command())["event"]
    witness.commit(1, event["identity"])
    assert witness.snapshot(NONCE)["events"] == [event]


def test_concurrent_identical_commits_charge_once(witness):
    event = witness.prepare(0, GENESIS, command())["event"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: open_witness(witness.path).commit(1, event["identity"]), range(8)))
    assert results == [event] * 8
    assert witness.snapshot(NONCE)["sequence"] == 1


def test_writer_lock_contention_is_bounded_and_does_not_mutate(witness):
    import time

    with sqlite3.connect(witness.path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            witness.prepare(0, GENESIS, command())
        assert time.monotonic() - started < 3
        assert witness.snapshot(NONCE)["pending"] is None


def test_json_null_cannot_erase_a_pending_command(witness):
    witness.prepare(0, GENESIS, command())
    with sqlite3.connect(witness.path) as connection:
        connection.execute("UPDATE head SET pending='null'")
    with pytest.raises(WitnessError, match="pending"):
        witness.snapshot(NONCE)


def test_publication_initialization_is_monotonic_and_never_reissued(witness):
    assert witness.snapshot(NONCE)["publication"] == "absent"
    with pytest.raises(WitnessError, match="intent"):
        witness.finish_publication()
    witness.begin_publication()
    witness.begin_publication()
    assert open_witness(witness.path).snapshot(NONCE)["publication"] == "pending"
    witness.finish_publication()
    witness.finish_publication()
    assert witness.snapshot(NONCE)["publication"] == "ready"
    with pytest.raises(WitnessError, match="already initialized"):
        witness.begin_publication()


def test_missing_initialization_state_is_corruption_not_a_fresh_store(witness):
    witness.begin_publication()
    with sqlite3.connect(witness.path) as connection:
        connection.execute("DELETE FROM publication")
    for operation in (lambda: witness.snapshot(NONCE), witness.begin_publication, witness.finish_publication):
        with pytest.raises(WitnessError, match="initialization state"):
            operation()
