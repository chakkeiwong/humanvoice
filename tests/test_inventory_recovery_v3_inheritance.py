"""Preserve historical root consumption separately from newly funded pairs."""

import multiprocessing
import os
from copy import deepcopy

import pytest
from test_inventory_recovery_v3_policy import reservations
from test_inventory_recovery_v3_stage import baseline, codex, exhausted, native_case

from humanvoice.artifacts import digest, read_json, write_json
from tools.inventory_recovery_v3 import inheritance, stage, successor

__all__ = ["baseline", "codex", "exhausted", "native_case"]


def history_for(journal, roots, *, diagnostic_last=True, retry_status="complete"):
    rows = []
    for position, root in enumerate(roots):
        request = {"prompt": "historical-" + str(position), "purpose": root["purpose"]}
        retry = None if diagnostic_last and position == len(roots) - 1 else {"status": retry_status}
        rows.append(inheritance.identified({"request": request, "request_hash": digest(request),
            "profile_hash": "profile-" + str(position), "canary": {"status": "complete"},
            "retry": retry, "diagnostic_only": retry is None}))
    history = inheritance.identified({"version": "inherited-reconnect-sequences-v1",
        "source": journal.binding["document"], "stages": [{"sequences": [row["identity"] for row in rows]}],
        "sequences": rows, "new_reserved_calls": 0})
    mapping = {row["identity"]: root["identity"] for row, root in zip(rows, roots, strict=True)}
    handoff = {"sequence_identity": rows[-1]["identity"], "incident_hash": "historical-incident"}
    return history, mapping, handoff


def imported(journal, roots):
    history, mapping, handoff = history_for(journal, roots)
    journal.inherit_history(history, mapping, handoff)
    return history, mapping, handoff


def test_eight_imports_preserve_all_thirty_two_new_pairs(tmp_path):
    journal = reservations(tmp_path, incident_allowance=32, root_sequences=12)
    roots = [journal.register_root(purpose="concept_extraction", owned=["old-" + str(index)])
             for index in range(8)]
    history, mapping, handoff = imported(journal, roots)
    assert len(journal.read()["inherited_recovery"]["sequences"]) == 8
    assert journal.read()["sequences"] == {}
    before = journal.path.read_bytes()
    journal.inherit_history(history, mapping, handoff)
    assert journal.path.read_bytes() == before
    for index in range(32):
        root = journal.register_root(purpose="concept_extraction", owned=["new-" + str(index)])
        journal.reserve(lineage=root["identity"], incident="incident-" + str(index),
                        request_hash="request-" + str(index), profile_hash="new-profile")
    extra = journal.register_root(purpose="concept_extraction", owned=["extra"])
    with pytest.raises(RuntimeError, match="complete canary and retry"):
        journal.reserve(lineage=extra["identity"], incident="extra", request_hash="extra", profile_hash="new-profile")
    assert len(journal.read()["sequences"]) == 32
    assert sum(slot["tokens"] for row in journal.read()["sequences"].values()
               for slot in row["slots"].values()) == 64 * 544000
    journal.inherit_history(history, mapping, handoff)
    assert len(journal.read()["inherited_recovery"]["sequences"]) == 8


def test_diagnostic_handoff_is_funded_once_and_preserves_old_consumption(tmp_path):
    journal = reservations(tmp_path, incident_allowance=3, root_sequences=12)
    root = journal.register_root(purpose="coverage_verification", owned=["span"])
    history, mapping, handoff = imported(journal, [root])
    old = history["sequences"][0]
    arguments = {"lineage": root["identity"], "incident": handoff["incident_hash"],
                 "request_hash": old["request_hash"], "profile_hash": old["profile_hash"]}
    with pytest.raises(RuntimeError, match="exact diagnostic handoff"):
        journal.reserve(**arguments)
    with pytest.raises(RuntimeError, match="continuation changed"):
        journal.reserve(**{**arguments, "incident": "different"}, inherited_diagnostic=old["identity"])
    selected = journal.reserve(**arguments, inherited_diagnostic=old["identity"])
    assert all(slot["state"] == "reserved" for slot in selected["slots"].values())
    before = journal.path.read_bytes()
    assert journal.reserve(**arguments, inherited_diagnostic=old["identity"]) == selected
    journal.inherit_history(history, mapping, handoff)
    assert before == journal.path.read_bytes()
    with pytest.raises(RuntimeError, match="continuation changed"):
        journal.reserve(**{**arguments, "incident": "reopened"}, inherited_diagnostic=old["identity"])
    journal.reserve(lineage=root["identity"], incident="third-sequence", request_hash="third",
                    profile_hash="qualified-alternative")
    with pytest.raises(RuntimeError, match="qualified split or fallback"):
        journal.reserve(lineage=root["identity"], incident="fourth-sequence", request_hash="fourth",
                        profile_hash="another-alternative")


@pytest.mark.parametrize("status", ["complete", "incomplete", "allocated_unknown"])
def test_allocated_retry_is_never_diagnostic_only(tmp_path, status):
    journal = reservations(tmp_path, root_sequences=12)
    roots = [journal.register_root(purpose="concept_extraction", owned=[str(index)]) for index in range(2)]
    history, mapping, handoff = history_for(journal, roots, retry_status=status)
    if status == "allocated_unknown":
        with pytest.raises(RuntimeError, match="allocated retry state"):
            journal.inherit_history(history, mapping, handoff)
        return
    journal.inherit_history(history, mapping, handoff)
    old = history["sequences"][0]
    with pytest.raises(RuntimeError, match="qualified split or fallback"):
        journal.reserve(lineage=roots[0]["identity"], incident="same-profile-reroll",
                        request_hash=old["request_hash"], profile_hash=old["profile_hash"])
    changed = deepcopy(history)
    changed["sequences"][0]["diagnostic_only"] = True
    changed["sequences"][0] = inheritance.identified({key: value for key, value in changed["sequences"][0].items()
                                                     if key != "identity"})
    changed["stages"][0]["sequences"] = [row["identity"] for row in changed["sequences"]]
    changed = inheritance.identified({key: value for key, value in changed.items() if key != "identity"})
    with pytest.raises(RuntimeError, match="allocated retry state"):
        journal.inherit_history(changed, mapping, handoff)


def test_siblings_share_twelve_sequence_ceiling_after_import(tmp_path):
    journal = reservations(tmp_path, incident_allowance=4, split_allowance=5, root_sequences=12)
    root = journal.register_root(purpose="concept_extraction", owned=[str(index) for index in range(6)])
    children = journal.split(root["identity"], [[str(index)] for index in range(6)])
    roots = [child for child in children[:-1] for _repeat in range(2)] + [children[-1]]
    history, _mapping, handoff = imported(journal, roots)
    old = history["sequences"][-1]
    journal.reserve(lineage=children[-1]["identity"], incident=handoff["incident_hash"],
                    request_hash=old["request_hash"], profile_hash=old["profile_hash"],
                    inherited_diagnostic=old["identity"])
    with pytest.raises(RuntimeError, match="qualified split or fallback"):
        journal.reserve(lineage=children[-1]["identity"], incident="thirteenth", request_hash="new",
                        profile_hash="unused-qualified-profile")
    assert len(journal.read()["sequences"]) == 1
    assert len(journal.read()["inherited_recovery"]["sequences"]) == 11


@pytest.mark.parametrize("codex", [900], indirect=True)
def test_native_import_excludes_unallocated_descriptors_and_preserves_sealed_evidence(exhausted):
    from tools.inventory_recovery_v2 import runtime

    expected = exhausted.transition["recovery_history"]
    before = exhausted.account.read_bytes(), exhausted.grant.read_bytes(), (
        exhausted.output / "allocation-ledger.json").read_bytes()
    assert len(expected["sequences"]) == 2
    assert [row["diagnostic_only"] for row in expected["sequences"]] == [False, True]
    row = expected["sequences"][-1]
    assert exhausted.transition["diagnostic_handoff"]["sequence_identity"] == row["identity"]
    assert row["canary"]["runtime_record"] == exhausted.transition["migration"]["canary_receipt"]
    write_json(exhausted.output / "reconnect-attempts/99999.json", {"kind": "canary", "unallocated": True})
    actual = inheritance.collect(exhausted.output, account_path=exhausted.account,
                                 verify_settlement=runtime.verify_settlement)
    assert actual == expected
    assert before == (exhausted.account.read_bytes(), exhausted.grant.read_bytes(), (
        exhausted.output / "allocation-ledger.json").read_bytes())
    assert read_json(exhausted.output / "allocation-seal.json")["ledger_hash"] == digest(
        read_json(exhausted.output / "allocation-ledger.json"))


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("change", ["omit", "profile", "receipt"])
def test_direct_transition_rejects_rehashed_historical_mutation(exhausted, tmp_path, change):
    transition = deepcopy(exhausted.transition)
    history = transition["recovery_history"]
    row = history["sequences"][0]
    if change == "omit":
        history["sequences"].pop(0)
    else:
        if change == "profile":
            row["profile_hash"] = "foreign"
        else:
            row["canary"]["runtime_record"]["hash"] = "foreign"
        history["sequences"][0] = inheritance.identified({key: value for key, value in row.items() if key != "identity"})
    history["stages"][0]["sequences"] = [row["identity"] for row in history["sequences"]]
    transition["recovery_history"] = inheritance.identified({key: value for key, value in history.items() if key != "identity"})
    transition = inheritance.identified({key: value for key, value in transition.items() if key != "identity"})
    before = exhausted.account.read_bytes(), exhausted.grant.read_bytes()
    for action in (lambda: successor.require_transition(transition),
                   lambda: successor.plan_for(tmp_path / "unused", transition, {}, {}),
                   lambda: stage.Stage(tmp_path / "successor", transition)):
        with pytest.raises(RuntimeError, match="native historical recovery"):
            action()
    assert before == (exhausted.account.read_bytes(), exhausted.grant.read_bytes())


@pytest.mark.parametrize("codex", [900], indirect=True)
@pytest.mark.parametrize("exhausted", ["cancel_canary", "cancel_retry"], indirect=True)
def test_native_cancelled_allocation_survives_history_reopen(exhausted):
    from tools.inventory_recovery_v2 import runtime

    before = {path: path.read_bytes() for path in (exhausted.account, exhausted.grant,
              exhausted.output / "execution.json", exhausted.output / "allocation-ledger.json")}
    expected = exhausted.transition["recovery_history"]
    allocations = [item for row in expected["sequences"] for item in [row["canary"], *row["retry_allocations"]]]
    cancelled = [item for item in allocations if item.get("cancellation") is not None]
    assert len(cancelled) == 1 and cancelled[0]["status"] == "incomplete"
    assert cancelled[0]["cancellation"]["new_provider_calls"] == 0
    assert len(allocations) == 4
    assert expected["sequences"][-1]["diagnostic_only"] is True
    assert exhausted.transition["recovery_sessions_used"] == 17
    for _repeat in range(2):
        assert inheritance.collect(exhausted.output, account_path=exhausted.account,
                                   verify_settlement=runtime.verify_settlement) == expected
        assert successor.require_transition(exhausted.transition) == exhausted.transition
    assert all(path.read_bytes() == value for path, value in before.items())


@pytest.mark.parametrize("cut", ["before", "after"])
def test_import_publication_recovers_without_renewing_history(tmp_path, cut):
    from tools.inventory_recovery_v3.reservations import RecoveryReservations

    journal = reservations(tmp_path, root_sequences=12)
    roots = [journal.register_root(purpose="concept_extraction", owned=[str(index)]) for index in range(8)]
    history, mapping, handoff = history_for(journal, roots)

    def worker():
        native = journal.save

        def save(record):
            if "inherited_recovery" in record:
                if cut == "after":
                    native(record)
                os._exit(73)
            return native(record)

        journal.save = save
        journal.inherit_history(history, mapping, handoff)

    child = multiprocessing.get_context("fork").Process(target=worker)
    child.start()
    child.join(10)
    assert child.exitcode == 73
    restarted = RecoveryReservations(tmp_path, journal.policy, journal.binding)
    restarted.inherit_history(history, mapping, handoff)
    retained = restarted.path.read_bytes()
    restarted.inherit_history(history, mapping, handoff)
    assert retained == restarted.path.read_bytes()
    assert len(restarted.read()["inherited_recovery"]["sequences"]) == 8
    assert restarted.read()["sequences"] == {}


def test_changed_or_missing_import_cannot_follow_reservation(tmp_path):
    journal = reservations(tmp_path, root_sequences=12)
    roots = [journal.register_root(purpose="concept_extraction", owned=[str(index)]) for index in range(2)]
    history, mapping, handoff = imported(journal, roots)
    other = journal.register_root(purpose="concept_extraction", owned=["new"])
    journal.reserve(lineage=other["identity"], incident="new", request_hash="new", profile_hash="new")
    with pytest.raises(RuntimeError, match="membership or handoff"):
        journal.inherit_history(history, {identity: roots[0]["identity"] for identity in mapping}, handoff)
    record = journal.read()
    del record["inherited_recovery"]
    before = journal.path.read_bytes()
    with pytest.raises(RuntimeError, match="binding or history changed"):
        journal.save(record)
    assert journal.path.read_bytes() == before


@pytest.mark.parametrize("fault", [None, "profile", "retired", "handoff"])
def test_read_only_first_pair_check_matches_real_reservation(tmp_path, fault):
    journal = reservations(tmp_path, root_sequences=12)
    root = journal.register_root(purpose="concept_extraction", owned=["one", "two"])
    history, mapping, handoff = history_for(journal, [root, root])
    if fault == "profile":
        history["sequences"][0]["profile_hash"] = history["sequences"][-1]["profile_hash"]
        history["sequences"][0] = inheritance.identified({key: value for key, value in history["sequences"][0].items()
                                                        if key != "identity"})
        history["stages"][0]["sequences"] = [row["identity"] for row in history["sequences"]]
        history = inheritance.identified({key: value for key, value in history.items() if key != "identity"})
        mapping = {row["identity"]: root["identity"] for row in history["sequences"]}
    journal.inherit_history(history, mapping, handoff)
    if fault == "retired":
        journal.inherit_split(root["identity"], [["one"], ["two"]], evidence="retained-rule")
    selected = history["sequences"][-1]
    arguments = {"lineage": root["identity"], "incident": handoff["incident_hash"],
                 "request_hash": selected["request_hash"], "profile_hash": selected["profile_hash"],
                 "inherited_diagnostic": selected["identity"] if fault != "handoff" else "wrong"}
    before = journal.path.read_bytes()
    if fault is None:
        expected = journal.reserve(**arguments, check_only=True)
        assert journal.path.read_bytes() == before and journal.read()["sequences"] == {}
        assert journal.reserve(**arguments) == expected
    else:
        for check_only in (True, False):
            with pytest.raises(RuntimeError):
                journal.reserve(**arguments, check_only=check_only)
        assert journal.path.read_bytes() == before
