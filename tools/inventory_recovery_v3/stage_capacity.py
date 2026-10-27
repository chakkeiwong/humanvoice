"""Earmark pairs inside native held capacity without a second account claim."""

from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.policy import TOKEN_RESERVATION, integer


def native_stage_capacity(output, *, account_path, grant_path):
    from tools import automatic_call_grant as grants
    from tools import token_epoch_20261025 as epoch

    output = Path(output).resolve()
    if not (output / "allocation-ledger.json").is_file():
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Read-only capacity inspection cannot create a ledger")
    paths = [output / name for name in ("plan.json", "account-reservation.json", "allocation-ledger.json")]
    paths += [Path(account_path), Path(grant_path), Path(grant_path).with_suffix(".stages.json")]
    before = {path: digest(path.read_bytes()) for path in paths}
    plan = read_json(output / "plan.json")
    receipt = read_json(output / "account-reservation.json")
    account = epoch.validate_account(read_json(account_path))
    grant = grants.status(grant_path)
    ledger = object.__new__(epoch.EpochLedger)
    ledger.path, ledger.plan = output / "allocation-ledger.json", plan
    ledger.allowed = {item["key"]: item for item in epoch.attempt_calls(plan)}
    ledger.account_allowance = epoch.bound_account_allowance(output, plan)
    ledger.reload()
    maximum = epoch.call_limit(plan)
    entry = receipt.get("entry", {})
    reserved = read_json(Path(grant_path).with_suffix(".stages.json"))["stages"]
    rows = [row for row in reserved if row["output"] == str(output)
            or row["plan_identity"] == plan["plan_identity"]]
    expected = {"output": str(output), "plan_identity": plan["plan_identity"],
                "grant_identity": grant["identity"], "maximum_calls": maximum}
    if (plan["plan_identity"] != digest({key: value for key, value in plan.items()
                                         if key != "plan_identity"})
            or receipt.get("account") != str(Path(account_path).resolve())
            or read_json(grant_path).get("account") != str(Path(account_path).resolve())
            or account["plans"].count(entry) != 1 or receipt.get("entry_hash") != digest(entry)
            or entry.get("calls") != maximum or entry.get("reserved_tokens") != maximum * TOKEN_RESERVATION
            or rows != [expected] or (output / "allocation-seal.json").exists()
            or any(event["kind"] == "settle" and event["usage"]["plan_identity"] == plan["plan_identity"]
                   for event in account["events"])):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native stage lacks its unique unsettled call and token holds")
    allocated = len(ledger.record["calls"])
    native_rows = [row for row in grant["stages"] if row["plan_identity"] == plan["plan_identity"]]
    if (native_rows != [{"output": str(output), "plan_identity": plan["plan_identity"], "new_calls": allocated}]
            or any(digest(path.read_bytes()) != expected for path, expected in before.items())):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native capacity snapshot changed during inspection")
    if any(row["status"] == "allocated_unknown" for row in ledger.record["calls"]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native stage has unresolved spending")
    return {"plan_identity": plan["plan_identity"], "native_verified": True,
            "maximum_calls": maximum, "allocated_calls": allocated,
            "held_calls": maximum - allocated,
            "held_tokens": (maximum - allocated) * TOKEN_RESERVATION,
            "global_available": grant["available"], "grant_identity": grant["identity"],
            "ledger_hash": digest(ledger.record), "account_entry_hash": digest(entry)}


def pair_capacity(stage, *, earmarked_calls, unfinished_base_calls, retry_is_base=False):
    if type(retry_is_base) is not bool:
        raise ValueError("Base-call reservation flag must be boolean")
    for name in ("maximum_calls", "allocated_calls", "held_calls", "held_tokens"):
        integer(stage.get(name), name)
    integer(earmarked_calls, "earmarked_calls")
    integer(unfinished_base_calls, "unfinished_base_calls")
    if (not stage.get("plan_identity") or stage.get("native_verified") is not True
            or stage["maximum_calls"] - stage["allocated_calls"] != stage["held_calls"]
            or stage["held_tokens"] != stage["held_calls"] * TOKEN_RESERVATION
            or earmarked_calls + unfinished_base_calls > stage["held_calls"]
            or retry_is_base and unfinished_base_calls < 1):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native stage holds do not reconcile")
    extra = 1 if retry_is_base else 2
    free = stage["held_calls"] - earmarked_calls - unfinished_base_calls
    if free < extra:
        raise RecoveryStop("BLOCKED_BUDGET", "Complete recovery pair cannot fit native stage holds",
                           evidence={"required_extra_calls": extra, "available_extra_calls": free})
    value = {"plan_identity": stage["plan_identity"], "pair_calls": 2,
             "extra_calls": extra, "pair_tokens": 2 * TOKEN_RESERVATION,
             "consumed_base_reservation": int(retry_is_base),
             "native_claims": 0, "native_refunds": 0}
    return {**value, "identity": digest(value)}


def held_pair_state(journal, record, output, account_path, grant_path):
    from tools.inventory_recovery_v3.native_dispatch import modules

    stage = native_stage_capacity(output, account_path=account_path, grant_path=grant_path)
    scoped = [row for row in record["sequences"].values()
              if row.get("native_capacity", {}).get("output") == str(output)]
    stage_journal(journal, output, stage, account_path, grant_path, required=bool(scoped))
    plan = read_json(output / "plan.json")
    execution, _runtime = modules(plan)
    entries = read_json(output / "allocation-ledger.json")["calls"]
    state = execution.layout(output, plan, entries)
    if state["pending"] is not None:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Unresolved native allocation retains its capacity")
    earmarked, assigned_base = 0, set()
    for sequence in record["sequences"].values():
        capacity = sequence.get("native_capacity")
        if capacity is None or capacity["output"] != str(output):
            continue
        if (capacity["identity"] != digest({key: value for key, value in capacity.items()
                                             if key != "identity"})
                or capacity["sequence"] != sequence["identity"]
                or capacity["plan_identity"] != plan["plan_identity"]
                or capacity["policy_identity"] != journal.policy["identity"]
                or capacity["account"] != str(account_path)
                or capacity["grant"] != str(grant_path)
                or capacity["grant_identity"] != stage["grant_identity"]
                or capacity["account_entry_hash"] != stage["account_entry_hash"]
                or len(entries) < capacity["prefix_count"]
                or digest(entries[:capacity["prefix_count"]]) != capacity["prefix_hash"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native earmark lost its exact authority or prefix")
        earmarked += sum(slot["state"] in {"reserved", "dispatching"} for slot in sequence["slots"].values())
        if capacity["retry_is_base"] and sequence["slots"]["retry"]["state"] in {"reserved", "dispatching"}:
            logical = capacity["logical"]
            if logical in assigned_base or logical in state["selected"]:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Native base reservation was assigned twice")
            assigned_base.add(logical)
    base = len(plan["calls"]) - len(state["selected"]) - len(assigned_base)
    if base < 0 or earmarked + base > stage["held_calls"]:
        raise RecoveryStop("BLOCKED_BUDGET", "Native stage cannot fund all earmarks and unfinished base work")
    return stage, state, entries, earmarked, base


def stage_journal(journal, output, stage, account_path, grant_path, *, required):
    from tools.inventory_recovery_v3.reservations import regular_path

    path = regular_path(output / "recovery-pair-journal.json")
    value = {"journal": str(journal.path), "policy_identity": journal.policy["identity"],
             "binding": journal.binding, "output": str(output),
             "plan_identity": stage["plan_identity"], "account": str(account_path),
             "grant": str(grant_path), "grant_identity": stage["grant_identity"]}
    expected = {**value, "identity": digest(value)}
    if path.exists():
        if read_json(path) != expected:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native stage belongs to another paired reservation journal")
    elif required:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native pair journal binding disappeared")
    return path, expected


def earmark_pair(journal, identity, output, *, account_path, grant_path, owner_check, stop_check):
    from tools.inventory_recovery_v3.reservations import persist, regular_path

    output = Path(output).absolute()
    account_path, grant_path = regular_path(account_path), regular_path(grant_path)
    with journal.locked():
        if owner_check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Earmark requires exclusive stage ownership")
        stop_check()
        record = journal.read()
        sequence = record["sequences"][identity]
        scope = sequence.get("native_stage", {})
        if scope.get("output") != str(output):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Earmark requires the bound native stage")
        if any(slot["state"] == "dispatching" for row in record["sequences"].values()
               for slot in row["slots"].values()):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Resolve native dispatch before earmarking")
        stage, state, entries, earmarked, base = held_pair_state(
            journal, record, output, account_path, grant_path)
        if sequence.get("native_capacity") is not None:
            return deepcopy(sequence["native_capacity"])
        if (any(slot["state"] != "reserved" for slot in sequence["slots"].values())
                or scope.get("plan_identity") != stage["plan_identity"]
                or state["mode"] != "canary" or not state["incident"]
                or digest(state["incident"]) != sequence["incident"]
                or state["incident"]["request_hash"] != sequence["request_hash"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Earmark must precede the exact native canary")
        retry_is_base = state["logical"] not in state["selected"]
        capacity = pair_capacity(stage, earmarked_calls=earmarked, unfinished_base_calls=base,
                                 retry_is_base=retry_is_base)
        binding_path, binding = stage_journal(journal, output, stage, account_path, grant_path, required=False)
        if not binding_path.exists():
            if owner_check() is not True:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Stage ownership changed before journal binding")
            stop_check()
            persist(binding_path, binding)
        value = {"version": "native-pair-earmark-v1", "sequence": identity, "output": str(output),
                 "plan_identity": stage["plan_identity"], "policy_identity": journal.policy["identity"],
                 "account": str(account_path), "grant": str(grant_path),
                 "grant_identity": stage["grant_identity"], "account_entry_hash": stage["account_entry_hash"],
                 "logical": state["logical"], "retry_is_base": retry_is_base,
                 "prefix_count": len(entries), "prefix_hash": digest(entries),
                 "capacity": capacity}
        sequence["native_capacity"] = {**value, "identity": digest(value)}
        if owner_check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Stage ownership changed before earmark commit")
        stop_check()
        held_pair_state(journal, record, output, account_path, grant_path)
        journal.save(record)
        return deepcopy(sequence["native_capacity"])


def require_earmark(journal, record, identity):
    sequence = record["sequences"][identity]
    capacity = sequence.get("native_capacity")
    if capacity is None:
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native allocation requires a durable complete-pair earmark")
    stage, state, _entries, _earmarked, _base = held_pair_state(journal, record, Path(capacity["output"]),
        Path(capacity["account"]), Path(capacity["grant"]))
    if (state["logical"] != capacity["logical"]
            or not state["incident"] or digest(state["incident"]) != sequence["incident"]
            or stage["held_calls"] < sum(slot["state"] in {"reserved", "dispatching"}
                                          for slot in sequence["slots"].values())):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native pair capacity no longer owns this incident")
    return deepcopy(capacity)
