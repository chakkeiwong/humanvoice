"""Witness-first publication: actual crash cuts and native stop-evidence checks."""

import json
import multiprocessing
import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from humanvoice.artifacts import digest
from tools.inventory_recovery_v3 import runtime_predicates, stop_authority
from tools.inventory_recovery_v3.failures import RecoveryStop

import control_files as files
import control_publication as publication
import control_semantics as semantics
from control_witness import Witness, WitnessError, encode
from test_control_service import FixtureService
from test_control_transport import FixtureReader

CUTS = ["witness-prepare", "local-intent", "local-event", "projection-0", "projection-1",
        "projection-2", "projection-3", "local-commit", "witness-commit"]


class FixturePublisher(publication.Publisher):
    """Explicit nonprivileged fixture; never a production authentication source."""

    def _authority(self):
        assert self.witness.path.is_file()
        return True

    def _clock(self):
        return 10 + self.witness.snapshot("a" * 64)["sequence"]


class FixtureSnapshots:
    def __init__(self, witness):
        self.witness = witness
        self.genesis, self.configuration = witness.genesis, witness.configuration

    def snapshot(self):
        return self.witness.snapshot(secrets.token_hex(32))


def setup(tmp_path, configuration, *, provision=True):
    host = tmp_path / "host"
    host.mkdir()
    roots = configuration["stop_bindings"]
    anchor = semantics.genesis(configuration, tmp_path / "local-control",
                               {row["root"]: None for row in roots})
    witness = Witness(host / "state.sqlite", genesis=anchor["identity"], configuration=anchor["configuration"])
    witness.initialize()
    publisher = FixturePublisher(anchor, witness)
    if provision:
        publisher.provision()
    reader = publication.EvidenceReader(anchor, FixtureSnapshots(witness))
    return SimpleNamespace(anchor=anchor, witness=witness, publisher=publisher, reader=reader,
                           configuration=configuration, root=roots[0]["root"])


@pytest.fixture
def case(tmp_path):
    roots = [tmp_path / name for name in ("old", "new")]
    for root in roots:
        root.mkdir()
    bindings = [{"root": str(root), "contract": {"root": root.name}} for root in roots]
    configuration = {"stop_bindings": bindings, "stop_floor": stop_authority.capture(bindings)}
    return setup(tmp_path, configuration)


def test_native_stop_resume_and_new_stop_invalidate_old_resume(case):
    assert stop_authority.verify(case.configuration, case.reader(case.configuration))
    assert case.publisher.publish("stop", case.root, "first")["sequence"] == 1
    with pytest.raises(RecoveryStop):
        stop_authority.verify(case.configuration, case.reader(case.configuration))
    case.publisher.publish("resume", case.root, "resume-first")
    before = files.read(Path(case.root) / "user-stop.json")
    assert stop_authority.verify(case.configuration, case.reader(case.configuration))
    case.publisher.publish("stop", case.root, "second")
    assert files.read(Path(case.root) / "resume-authorization.json") is None
    assert files.read(Path(case.root) / "user-stop.json") != before
    with pytest.raises(RecoveryStop):
        stop_authority.verify(case.configuration, case.reader(case.configuration))
    case.publisher.publish("resume", case.root, "resume-second")
    assert stop_authority.verify(case.configuration, case.reader(case.configuration))
    assert case.witness.snapshot("a" * 64)["sequence"] == 4


def test_exact_request_retries_do_not_rewrite_or_charge_again(case):
    first = case.publisher.publish("stop", case.root, "first")
    retained = case.witness.path.read_bytes()
    retry = case.publisher.publish("stop", case.root, "first")
    assert retry["events"] == first["events"] and retry["sequence"] == 1
    assert case.witness.path.read_bytes() == retained
    with pytest.raises(WitnessError, match="repurposed"):
        case.publisher.publish("resume", case.root, "first")


def crash_writer(anchor, database, cut, action, root):
    class CrashingPublisher(FixturePublisher):
        def _cut(self, name):
            if name == cut:
                os._exit(91)
    witness = Witness(database, genesis=anchor["identity"], configuration=anchor["configuration"])
    CrashingPublisher(anchor, witness).publish(action, root, "crash-request")


@pytest.mark.parametrize("action", ["stop", "resume"])
@pytest.mark.parametrize("cut", CUTS)
def test_process_death_at_each_publication_cut_converges_once(case, action, cut):
    if action == "resume":
        case.publisher.publish("stop", case.root, "original-stop")
    initial = case.witness.snapshot("a" * 64)["sequence"]
    process = multiprocessing.get_context("spawn").Process(target=crash_writer,
        args=(case.anchor, case.witness.path, cut, action, case.root))
    process.start()
    process.join(15)
    if process.is_alive():
        process.kill()
        process.join(5)
        pytest.fail("Crash writer did not finish")
    assert process.exitcode == 91
    if cut != "witness-commit":
        with pytest.raises(WitnessError, match="pending"):
            case.reader(case.configuration)
    cold = FixturePublisher(case.anchor, Witness(case.witness.path, genesis=case.anchor["identity"],
                                                configuration=case.anchor["configuration"]))
    result = cold.repair()
    assert result["sequence"] == initial + 1 and result["pending"] is None
    assert cold.repair()["events"] == result["events"]
    assert cold.publish(action, case.root, "crash-request")["events"] == result["events"]
    if action == "stop":
        with pytest.raises(RecoveryStop):
            stop_authority.verify(case.configuration, case.reader(case.configuration))
    else:
        assert stop_authority.verify(case.configuration, case.reader(case.configuration))


@pytest.mark.parametrize("cut", CUTS)
def test_repeated_storage_failures_preserve_one_pending_command(case, monkeypatch, cut):
    def fail(name):
        if name == cut:
            raise OSError("injected storage outage")
    monkeypatch.setattr(case.publisher, "_cut", fail)
    for _ in range(3):
        if cut == "witness-prepare" and case.witness.snapshot("a" * 64)["pending"] is not None:
            break  # Reopening repairs the retained event; it never prepares it again.
        if cut == "witness-commit" and case.witness.snapshot("a" * 64)["sequence"] == 1:
            break
        with pytest.raises(OSError, match="storage outage"):
            case.publisher.publish("stop", case.root, "one-request")
    monkeypatch.setattr(case.publisher, "_cut", lambda _: None)
    result = case.publisher.repair()
    assert result["sequence"] == 1 and len(result["events"]) == 1


def test_native_runtime_leaf_uses_publication_evidence(predicates, tmp_path):
    configuration, _ = predicates
    case = setup(tmp_path, configuration)
    leaf = runtime_predicates.RuntimeLeaf(configuration,
        require_admission=lambda: deepcopy(configuration), require_controls=case.reader)
    assert leaf() is True
    case.publisher.publish("stop", case.root, "native-stop")
    with pytest.raises(RecoveryStop):
        leaf()
    case.publisher.publish("resume", case.root, "native-resume")
    assert leaf() is True


@pytest.mark.parametrize("target", ["head", "genesis", "event", "stop", "resume", "extra", "whole-tree"])
def test_rollback_or_missing_committed_evidence_is_not_reconstructed(case, target):
    case.publisher.publish("stop", case.root, "first")
    case.publisher.publish("resume", case.root, "resume")
    root = Path(case.anchor["directory"])
    if target in {"head", "genesis"}:
        (root / (target + ".json")).unlink()
    elif target == "event":
        next((root / "events").iterdir()).unlink()
    elif target in {"stop", "resume"}:
        name = "user-stop.json" if target == "stop" else "resume-authorization.json"
        (Path(case.root) / name).unlink()
    elif target == "extra":
        (root / "unknown.json").write_text("{}")
    else:
        for p in (root / "events").iterdir():
            p.unlink()
        (root / "head.json").write_bytes(publication.encoded(publication.head(case.anchor, 0, case.anchor["identity"])))
        (Path(case.root) / "user-stop.json").unlink()
        (Path(case.root) / "resume-authorization.json").unlink()
    before = case.witness.path.read_bytes()
    for action in (lambda: case.reader(case.configuration), case.publisher.repair):
        with pytest.raises((OSError, WitnessError)):
            action()
    assert case.witness.path.read_bytes() == before


@pytest.mark.parametrize("clock", [1, 10, False, float("nan"), float("inf")])
def test_host_clock_regression_or_invalid_time_cannot_publish(case, monkeypatch, clock):
    case.publisher.publish("stop", case.root, "first")
    before = case.witness.path.read_bytes()
    monkeypatch.setattr(case.publisher, "_clock", lambda: clock)
    with pytest.raises(ValueError):
        case.publisher.publish("stop", case.root, "later")
    assert case.witness.path.read_bytes() == before


def test_stable_reader_is_readonly_and_rejects_concurrent_control_change(case, monkeypatch):
    root = Path(case.anchor["directory"])
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    assert case.reader(case.configuration)
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    original = case.reader.reader.snapshot
    calls = []

    def changed():
        calls.append(True)
        if len(calls) == 2:
            case.publisher.publish("stop", case.root, "concurrent")
        return original()

    monkeypatch.setattr(case.reader.reader, "snapshot", changed)
    with pytest.raises(WitnessError, match="advanced"):
        case.reader(case.configuration)


@pytest.mark.parametrize("target", ["root", "stop", "head", "event-directory"])
def test_symlinks_never_become_privileged_projection_targets(case, target, tmp_path):
    local = Path(case.anchor["directory"])
    if target == "root":
        original = Path(case.root)
        original.rename(tmp_path / "moved")
        original.symlink_to(tmp_path / "moved", target_is_directory=True)
    elif target == "stop":
        (Path(case.root) / "user-stop.json").symlink_to(tmp_path / "victim")
    elif target == "head":
        (local / "head.json").rename(tmp_path / "head.saved")
        (local / "head.json").symlink_to(tmp_path / "head.saved")
    else:
        (local / "events").rename(tmp_path / "events.saved")
        (local / "events").symlink_to(tmp_path / "events.saved", target_is_directory=True)
    (tmp_path / "victim").write_text("unchanged")
    before = case.witness.path.read_bytes()
    with pytest.raises((OSError, WitnessError)):
        case.publisher.publish("stop", case.root, "first")
    assert case.witness.path.read_bytes() == before
    assert (tmp_path / "victim").read_text() == "unchanged"


def test_unprivileged_production_publisher_refuses_before_mutation(case):
    before = case.witness.path.read_bytes()
    with pytest.raises(WitnessError, match="protected|host"):
        publication.Publisher(case.anchor, case.witness).publish("stop", case.root, "forbidden")
    assert case.witness.path.read_bytes() == before


def test_native_digest_and_unicode_floor_compatibility(case):
    for value in ({"text": "résumé 中文", "nested": [1, None, True]}, "exact\r\n", b"exact\r\n"):
        assert semantics.native_digest(value) == digest(value)
    assert semantics.evidence(case.anchor, case.anchor["initial"])["identity"] == stop_authority.identified(
        semantics.evidence(case.anchor, case.anchor["initial"]))["identity"]


@pytest.mark.parametrize("mutation", ["stop_hash", "root", "contract", "request_id"])
def test_forged_resume_in_witness_is_vetoed_before_local_writes(case, mutation):
    observed = case.publisher.publish("stop", case.root, "first")
    state, _ = semantics.replay(case.anchor, observed)
    command = semantics.command(case.anchor, state, "resume", case.root, "forged", now=20)
    content = json.loads(command["content"])
    if mutation == "root":
        command["root"] = "/foreign"
    else:
        content[{"stop_hash": "stop_sha256", "contract": "contract", "request_id": "request_id"}[mutation]] = "foreign"
        command["content"] = encode(content)
    case.witness.prepare(observed["sequence"], observed["committed_head"], command)
    before = files.read(Path(case.anchor["directory"]) / "head.json")
    with pytest.raises(WitnessError):
        case.publisher.repair()
    assert files.read(Path(case.anchor["directory"]) / "head.json") == before


def test_existing_inherited_stop_needs_exact_explicit_resume(tmp_path):
    root = tmp_path / "inherited"
    root.mkdir()
    original = '{"status":"USER_STOPPED","request_id":"inherited","requested_at":1}\r\n'
    (root / "user-stop.json").write_bytes(original.encode())
    bindings = [{"root": str(root), "contract": {"unicode": "原始"}}]
    configuration = {"stop_bindings": bindings, "stop_floor": stop_authority.capture(bindings)}
    case = setup(tmp_path, configuration)
    with pytest.raises(RecoveryStop):
        stop_authority.verify(configuration, case.reader(configuration))
    case.publisher.publish("resume", case.root, "explicit")
    assert files.read(root / "user-stop.json") == original.encode()
    assert stop_authority.verify(configuration, case.reader(configuration))


def test_existing_resume_file_cannot_manufacture_genesis_authorization(tmp_path):
    root = tmp_path / "inherited"
    root.mkdir()
    (root / "user-stop.json").write_text(encode({"status": "USER_STOPPED", "request_id": "old", "requested_at": 1}))
    (root / "resume-authorization.json").write_text('{"authorized_by":"user"}')
    bindings = [{"root": str(root), "contract": {"original": True}}]
    configuration = {"stop_bindings": bindings, "stop_floor": stop_authority.capture(bindings)}
    with pytest.raises(WitnessError, match="projection"):
        setup(tmp_path, configuration)
    assert not (tmp_path / "local-control").exists()


def test_real_socket_service_supplies_native_control_reader(case, tmp_path):
    path = tmp_path / "witness.sock"
    stop, errors = threading.Event(), []

    def serve():
        try:
            FixtureService(path, case.witness).serve(stop)
        except (OSError, ValueError) as error:
            errors.append(error)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        transport = FixtureReader(path, genesis=case.anchor["identity"], configuration=case.anchor["configuration"])
        reader = publication.EvidenceReader(case.anchor, transport)
        assert stop_authority.verify(case.configuration, reader(case.configuration))
        case.publisher.publish("stop", case.root, "real-socket-stop")
        with pytest.raises(RecoveryStop):
            stop_authority.verify(case.configuration, reader(case.configuration))
        case.publisher.publish("resume", case.root, "real-socket-resume")
        assert stop_authority.verify(case.configuration, reader(case.configuration))
    finally:
        stop.set()
        thread.join(8)
    assert not thread.is_alive() and not errors


def test_concurrent_stop_resume_cannot_overlap_host_publication(case, monkeypatch):
    case.publisher.publish("stop", case.root, "initial")
    entered, release = threading.Event(), threading.Event()

    def hold(name):
        if name == "witness-prepare":
            entered.set()
            assert release.wait(5)

    monkeypatch.setattr(case.publisher, "_cut", hold)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(case.publisher.publish, "resume", case.root, "resume")
        try:
            assert entered.wait(5)
            with pytest.raises(BlockingIOError):
                FixturePublisher(case.anchor, case.witness).publish("stop", case.root, "later")
        finally:
            release.set()
        assert future.result(timeout=5)["sequence"] == 2
    result = case.publisher.publish("stop", case.root, "later")
    assert result["sequence"] == 3
    with pytest.raises(RecoveryStop):
        stop_authority.verify(case.configuration, case.reader(case.configuration))


@pytest.mark.parametrize("failure", range(1, 6))
def test_file_fsync_failures_keep_pending_witness_until_repaired(case, monkeypatch, failure):
    original = files.os.fsync
    calls = []

    def fail(descriptor):
        calls.append(descriptor)
        if len(calls) == failure:
            raise OSError("injected fsync failure")
        return original(descriptor)

    monkeypatch.setattr(files.os, "fsync", fail)
    with pytest.raises(OSError, match="fsync failure"):
        case.publisher.publish("stop", case.root, "durable")
    assert case.witness.snapshot("a" * 64)["pending"] is not None
    monkeypatch.setattr(files.os, "fsync", original)
    assert case.publisher.repair()["sequence"] == 1
    assert case.publisher.repair()["sequence"] == 1


def test_identical_file_replay_retries_failed_directory_fsync(case, monkeypatch):
    case.publisher.publish("stop", case.root, "first")
    target = Path(case.root) / "user-stop.json"
    content = files.read(target)
    original = files.os.fsync
    calls = []

    def fail(descriptor):
        calls.append(descriptor)
        if len(calls) == 2:
            raise OSError("directory sync failed")
        return original(descriptor)

    monkeypatch.setattr(files.os, "fsync", fail)
    with pytest.raises(OSError, match="directory sync"):
        files.write(target, content, expected=[content])
    files.write(target, content, expected=[content])
    assert len(calls) == 4


def unprovisioned(tmp_path):
    root = tmp_path / "stop-root"
    root.mkdir()
    bindings = [{"root": str(root), "contract": {"initialization": True}}]
    configuration = {"stop_bindings": bindings, "stop_floor": stop_authority.capture(bindings)}
    return setup(tmp_path, configuration, provision=False)


def crash_initialization(anchor, database, cut):
    class CrashingInitializer(FixturePublisher):
        def _cut(self, name):
            if name == cut:
                os._exit(92)
    witness = Witness(database, genesis=anchor["identity"], configuration=anchor["configuration"])
    CrashingInitializer(anchor, witness).provision()


@pytest.mark.parametrize("cut", ["initialize-witness", "initialize-directories",
    "initialize-genesis", "initialize-head", "initialize-complete"])
def test_initialization_crash_repairs_only_retained_host_intent(tmp_path, cut):
    case = unprovisioned(tmp_path)
    with pytest.raises(WitnessError, match="initialization"):
        case.publisher.repair()
    with pytest.raises(WitnessError, match="initialization"):
        case.reader(case.configuration)
    process = multiprocessing.get_context("spawn").Process(target=crash_initialization,
        args=(case.anchor, case.witness.path, cut))
    process.start()
    process.join(15)
    if process.is_alive():
        process.kill()
        process.join(5)
        pytest.fail("Initialization child did not stop")
    assert process.exitcode == 92
    if cut != "initialize-complete":
        with pytest.raises(WitnessError, match="initialization"):
            case.reader(case.configuration)
    final = case.publisher.repair()
    assert final["publication"] == "ready" and final["sequence"] == 0
    assert case.publisher.repair()["events"] == []
    assert stop_authority.verify(case.configuration, case.reader(case.configuration))


@pytest.mark.parametrize("target", ["head", "whole-tree"])
def test_provision_cannot_recreate_completed_zero_sequence_state(case, target):
    root = Path(case.anchor["directory"])
    if target == "head":
        (root / "head.json").unlink()
    else:
        root.rename(root.with_name("lost-control"))
    before = case.witness.path.read_bytes()
    for action in (case.publisher.provision, case.publisher.repair):
        with pytest.raises((OSError, WitnessError)):
            action()
    assert case.witness.path.read_bytes() == before
    assert not (root / "head.json").exists()


def test_pending_initialization_rejects_foreign_local_bytes(tmp_path, monkeypatch):
    case = unprovisioned(tmp_path)

    def fail(name):
        if name == "initialize-genesis":
            raise OSError("initialization outage")

    monkeypatch.setattr(case.publisher, "_cut", fail)
    with pytest.raises(OSError):
        case.publisher.provision()
    root = Path(case.anchor["directory"])
    (root / "genesis.json").write_text('{"foreign":true}')
    with pytest.raises(WitnessError, match="conflicts"):
        case.publisher.repair()
    assert case.witness.snapshot("a" * 64)["publication"] == "pending"
