"""The public composition has an acyclic, read-only ownership leaf."""

import fcntl
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_failure_first_native import baseline, codex, prepared
from test_inventory_recovery_v3_consumption_floors import (
    bind,
    native_floors,
    reserve_value,
    resource_lock,
    stage_value,
)
from test_inventory_recovery_v3_ownership import configured
from test_inventory_recovery_v3_runtime_closure import (
    closure_case,
    forbidden,
    installed,
)

from humanvoice.artifacts import digest, read_json, write_json
from tools.inventory_recovery_v2 import control
from tools.inventory_recovery_v3 import (
    handover,
    ownership,
    ownership_roles,
    runtime_predicates,
    stop_authority,
)
from tools.inventory_recovery_v3.failures import RecoveryStop

__all__ = ["baseline", "closure_case", "codex", "installed", "native_floors", "prepared"]


def controls_path(configuration):
    return Path(configuration["campaign_root"]).parent / "authenticated-control-fixture.json"


def controls(configuration):
    # Durable external-authority fixture. It never infers history from current
    # stop files. Production requires an independently authenticated publisher.
    value = read_json(controls_path(configuration))
    assert value["configuration"] == digest(configuration)
    return value


def initialize_controls(configuration):
    floor = configuration["stop_floor"]
    histories = {}
    for row in floor["roots"]:
        histories[row["root"]] = [] if row["stop_bytes"] is None else [stop_authority.identified(
            {"sequence": 1, "previous": None, "stop_bytes": row["stop_bytes"]})]
    write_json(controls_path(configuration), stop_authority.identified({"version": stop_authority.VERSION,
        "configuration": digest(configuration), "histories": histories,
        "resumes": {row["root"]: None for row in floor["roots"]}}))


def issue_stop(configuration, index):
    root = Path(configuration["stop_bindings"][index]["root"])
    evidence = controls(configuration)
    rows = evidence["histories"][str(root)]
    number = len(rows) + 1
    content = json.dumps({"status": "USER_STOPPED", "requested_at": number,
                          "request_id": f"fixture-{index}-{number}"})
    rows.append(stop_authority.identified({"sequence": number,
        "previous": rows[-1]["identity"] if rows else None, "stop_bytes": content}))
    evidence["resumes"][str(root)] = None
    write_json(controls_path(configuration), stop_authority.identified(evidence))
    (root / "user-stop.json").write_text(content)
    (root / "resume-authorization.json").unlink(missing_ok=True)
    return content


def issue_resume(configuration, index):
    binding = configuration["stop_bindings"][index]
    root = Path(binding["root"])
    content = json.dumps({"action": "explicit-resume", "authorized_by": "user",
        "contract": binding["contract"], "stop_sha256": digest((root / "user-stop.json").read_bytes())})
    evidence = controls(configuration)
    evidence["resumes"][str(root)] = content
    write_json(controls_path(configuration), stop_authority.identified(evidence))
    (root / "resume-authorization.json").write_text(content)
    return content


@pytest.fixture
def predicates(closure_case):
    adoption, closure = closure_case
    installed = adoption["installed"]
    root = Path(installed["account"]).parent
    configuration = {"handover": adoption, "runtime_closure": closure,
        "campaign_root": str(root / "new-campaign"), "contract": adoption["contract"],
        "execution_authority": {"program_base": str(root),
            "supervisor_root": adoption["replacement"], "account": installed["account"],
            "grant": installed["grant"], "grant_identity": "fixture-grant"}}
    configuration["stop_bindings"] = [*adoption["stop_bindings"],
        {"root": configuration["campaign_root"], "contract": configuration["contract"]}]
    for name in (configuration["campaign_root"], adoption["replacement"]):
        Path(name).mkdir()
    configuration["stop_floor"] = stop_authority.capture(configuration["stop_bindings"])
    initialize_controls(configuration)
    return configuration, runtime_predicates.RuntimeLeaf(configuration,
        require_admission=lambda: deepcopy(configuration), require_controls=controls)


def test_leaf_never_calls_lease_floor_transfer_or_lock(predicates, monkeypatch):
    _configuration, leaf = predicates
    monkeypatch.setattr(handover, "validate", forbidden)
    monkeypatch.setattr(ownership.Lease, "check", forbidden)
    monkeypatch.setattr(fcntl, "flock", forbidden)
    assert leaf() is True


@pytest.mark.parametrize("index", [0, 1])
def test_inherited_and_current_stop_veto(predicates, index):
    configuration, leaf = predicates
    root = Path(configuration["stop_bindings"][index]["root"])
    root.mkdir(parents=True, exist_ok=True)
    control.stop(root)
    with pytest.raises(RuntimeError) as caught:
        leaf()
    assert caught.value.category == "USER_STOPPED"


def test_external_admission_rejects_rehashed_closure(predicates):
    configuration, _leaf = predicates
    changed = deepcopy(configuration)
    changed["runtime_closure"]["predecessors"] = {}
    from tools.inventory_recovery_v3.runtime_closure import identified

    changed["runtime_closure"] = identified(changed["runtime_closure"])
    leaf = runtime_predicates.RuntimeLeaf(changed, require_admission=lambda: configuration, require_controls=controls)
    with pytest.raises(RecoveryStop, match="External admission"):
        leaf()


def test_leaf_rejects_recursive_admission_and_recovers(predicates):
    configuration, _leaf = predicates
    recursive = [True]
    leaf = runtime_predicates.RuntimeLeaf(configuration, require_admission=lambda:
        leaf() if recursive[0] else deepcopy(configuration), require_controls=controls)
    with pytest.raises(RecoveryStop, match="recursively"):
        leaf()
    recursive[0] = False
    assert leaf()


def test_leaf_checks_predecessor_process_identity(predicates, monkeypatch):
    configuration, leaf = predicates
    monkeypatch.setattr(runtime_predicates.durable, "alive", lambda owner: True)
    # A retained owner must be bound into a newly admitted configuration.
    changed = deepcopy(configuration)
    changed["handover"]["records"][0]["predecessor"]["owners"].append({"pid": 1})
    from tools.inventory_recovery_v3.runtime_closure import identified

    changed["handover"] = identified(changed["handover"])
    changed["runtime_closure"]["adoption_identity"] = changed["handover"]["identity"]
    changed["runtime_closure"] = identified(changed["runtime_closure"])
    initialize_controls(changed)
    leaf = runtime_predicates.RuntimeLeaf(changed, require_admission=lambda: changed, require_controls=controls)
    with pytest.raises(RecoveryStop, match="still alive"):
        leaf()


def test_complete_lease_and_native_write_guard_are_acyclic(predicates, monkeypatch):
    configuration, leaf = predicates
    derive = lambda: ownership_roles.expected(configuration, "monitor")
    with ownership.acquire(derive, leaf=leaf) as held:
        guards = runtime_predicates.OwnedPredicates(leaf, held)
        monkeypatch.setattr(fcntl, "flock", forbidden)
        assert guards.check() is True
        assert held.check() is True


@pytest.mark.parametrize("status", ["READY", "EXTENDED", "PENDING_BEFORE",
    "PENDING_AFTER", "PENDING_EXTENDED", "PUBLICATION_IN_PROGRESS", "foreign"])
def test_dispatch_checks_read_only_floors_then_rechecks_leaf(predicates, status):
    configuration, leaf = predicates
    observations = []
    scope = configuration["execution_authority"]
    floors = SimpleNamespace(seed={"configuration": digest(configuration),
        "grant": scope["grant"], "grant_identity": scope["grant_identity"]},
        path=lambda resource: Path(scope["account"]),
        status=lambda resource: observations.append(resource) or {"status": status})
    with ownership.acquire(lambda: ownership_roles.expected(configuration, "monitor"), leaf=leaf) as held:
        guards = runtime_predicates.OwnedPredicates(leaf, held)
        if status in {"READY", "EXTENDED"}:
            assert guards.dispatch(floors)
            assert observations == ["account", "stages"]
        else:
            with pytest.raises(RecoveryStop, match="Reconcile"):
                guards.dispatch(floors)


def test_late_stop_after_floor_read_prevents_dispatch(predicates):
    configuration, leaf = predicates
    scope = configuration["execution_authority"]

    def status(resource):
        if resource == "stages":
            write_json(Path(configuration["campaign_root"]) / "user-stop.json",
                       {"status": "USER_STOPPED"})
        return {"status": "READY"}

    floors = SimpleNamespace(seed={"configuration": digest(configuration),
        "grant": scope["grant"], "grant_identity": scope["grant_identity"]},
        path=lambda resource: Path(scope["account"]), status=status)
    with ownership.acquire(lambda: ownership_roles.expected(configuration, "monitor"), leaf=leaf) as held:
        with pytest.raises(RuntimeError) as caught:
            runtime_predicates.OwnedPredicates(leaf, held).dispatch(floors)
        assert caught.value.category == "USER_STOPPED"


@pytest.mark.parametrize("resource", ["account", "stages"])
def test_real_native_floors_write_guard_and_cold_rollback(native_floors, tmp_path, resource):
    original, account, grant, plan, output, _control = native_floors
    configuration = configured(tmp_path / "complete-lease")
    configuration["execution_authority"].update(account=str(account), grant=str(grant),
        grant_identity=original.seed["grant_identity"])
    # This test composes the real lease with real native floors. The independent
    # RuntimeLeaf/closure integration is exercised by the tests above.
    class Admission:
        def __init__(self):
            self.configuration = configuration

        def __call__(self):
            return True

    leaf = Admission()
    guard = bind(configuration, lambda: True)
    with ownership.acquire(lambda: ownership_roles.expected(configuration, "monitor"), leaf=leaf) as held:
        checks = runtime_predicates.OwnedPredicates(leaf, held)
        guard.check = checks.check
        guard.initialize()
        before = guard.path(resource).read_bytes() if guard.path(resource).exists() else None
        value = reserve_value(account, plan, output) if resource == "account" else stage_value(guard, plan, output)
        with resource_lock(guard, resource):
            # This callback runs while the native spending lock is already held.
            guard.write(resource, value, operation="reserve" if resource == "account" else "hold",
                        writer=write_json)
        assert checks.dispatch(guard)
        from tools.inventory_recovery_v3.consumption_floors import ConsumptionFloors

        cold = ConsumptionFloors.__new__(ConsumptionFloors)
        cold.seed, cold.root, cold.check = deepcopy(guard.seed), guard.root, checks.check
        retained = {path: path.read_bytes() for path in guard.root.iterdir()}
        assert checks.dispatch(cold)
        assert retained == {path: path.read_bytes() for path in guard.root.iterdir()}
        if before is None:
            guard.path(resource).unlink()
        else:
            guard.path(resource).write_bytes(before)
        with pytest.raises((RecoveryStop, ValueError, OSError)):
            checks.dispatch(cold)


def cold_leaf(configuration):
    return runtime_predicates.RuntimeLeaf(configuration, require_admission=lambda: deepcopy(configuration),
                                          require_controls=controls)


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("at_transfer", [False, True])
@pytest.mark.parametrize("defect", ["delete", "rollback", "resume-replay", "history-missing"])
def test_stop_history_survives_deletion_rollback_and_cold_reopen(predicates, index, at_transfer, defect):
    configuration, leaf = predicates
    root = Path(configuration["stop_bindings"][index]["root"])
    old = issue_stop(configuration, index)
    if at_transfer:
        configuration["stop_floor"] = stop_authority.capture(configuration["stop_bindings"])
        initialize_controls(configuration)
        leaf = cold_leaf(configuration)
    old_resume = issue_resume(configuration, index)
    assert leaf()
    latest = issue_stop(configuration, index)
    with pytest.raises(RecoveryStop) as caught:
        leaf()
    assert caught.value.category == "USER_STOPPED"
    if defect == "delete":
        (root / "user-stop.json").unlink()
    elif defect == "rollback":
        (root / "user-stop.json").write_text(old)
        (root / "resume-authorization.json").write_text(old_resume)
    elif defect == "resume-replay":
        (root / "resume-authorization.json").write_text(old_resume)
    else:
        controls_path(configuration).unlink()
    for selected in (leaf, cold_leaf(configuration)):
        with pytest.raises(RecoveryStop) as caught:
            selected()
        assert caught.value.category == "USER_STOPPED"
    if defect != "history-missing":
        (root / "user-stop.json").write_text(latest)
        issue_resume(configuration, index)
        assert cold_leaf(configuration)()


@pytest.mark.parametrize("index", [0, 1])
def test_owned_guard_and_fresh_process_reject_stop_deletion(predicates, index, monkeypatch):
    configuration, leaf = predicates
    with ownership.acquire(lambda: ownership_roles.expected(configuration, "monitor"), leaf=leaf) as held:
        checks = runtime_predicates.OwnedPredicates(leaf, held)
        issue_stop(configuration, index)
        root = Path(configuration["stop_bindings"][index]["root"])
        (root / "user-stop.json").unlink()
        with pytest.raises(RecoveryStop) as caught:
            checks.check()
        assert caught.value.category == "USER_STOPPED"
    record = Path(configuration["campaign_root"]).parent / "configuration-test.json"
    write_json(record, configuration)
    source = ("import sys; sys.path[:0]=[sys.argv[1],sys.argv[1]+'/src']; "
        "from pathlib import Path; from humanvoice.artifacts import read_json; "
        "from tools.inventory_recovery_v3 import installed_authority,runtime_predicates; "
        "installed_authority.require_environment=lambda value:None; "
        "c=read_json(Path(sys.argv[2])); "
        "leaf=runtime_predicates.RuntimeLeaf(c,require_admission=lambda:c,"
        "require_controls=lambda value:read_json(Path(sys.argv[3]))); "
        "leaf()")
    result = subprocess.run([sys.executable, "-I", "-c", source,
        str(Path(__file__).resolve().parents[1]), str(record), str(controls_path(configuration))],
        capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode != 0 and "deleted, rolled back" in result.stderr


def test_leaf_cannot_omit_explicit_monotonic_control_authority(predicates):
    configuration, _leaf = predicates
    with pytest.raises(TypeError):
        runtime_predicates.RuntimeLeaf(configuration, require_admission=lambda: configuration)
    leaf = runtime_predicates.RuntimeLeaf(configuration, require_admission=lambda: configuration,
        require_controls=lambda value: None)
    with pytest.raises(RecoveryStop, match="authenticated"):
        leaf()


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("target", ["user-stop.json", "resume-authorization.json"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_control_byte_identity_rejects_newline_conversion(predicates, index, target, newline):
    configuration, leaf = predicates
    root = Path(configuration["stop_bindings"][index]["root"])
    issued = issue_stop(configuration, index)
    content = (json.dumps(json.loads(issued), indent=2) + "\n").replace("\n", newline)
    evidence = controls(configuration)
    evidence["histories"][str(root)][0] = stop_authority.identified(
        {"sequence": 1, "previous": None, "stop_bytes": content})
    write_json(controls_path(configuration), stop_authority.identified(evidence))
    (root / "user-stop.json").write_bytes(content.encode())
    authorized = issue_resume(configuration, index)
    resume = (json.dumps(json.loads(authorized), indent=2) + "\n").replace("\n", newline)
    evidence = controls(configuration)
    evidence["resumes"][str(root)] = resume
    write_json(controls_path(configuration), stop_authority.identified(evidence))
    (root / "resume-authorization.json").write_bytes(resume.encode())
    assert leaf() and cold_leaf(configuration)()
    path = root / target
    original = path.read_bytes()
    changed = original.replace(b"\r\n", b"\n") if newline == "\r\n" else original.replace(b"\n", b"\r\n")
    assert changed != original
    path.write_bytes(changed)
    for selected in (leaf, cold_leaf(configuration)):
        with pytest.raises(RecoveryStop) as caught:
            selected()
        assert caught.value.category == "USER_STOPPED"
