"""Complete interrupted native claims using a durable, nonrenewable intent."""

import fcntl
from pathlib import Path
from types import FunctionType

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path


def guarded_ledger(path, plan, check, *, account_allowance):
    from tools import token_epoch_20261025 as epoch

    native = epoch.EpochLedger
    initializer = native.__init__
    namespace = dict(initializer.__globals__)

    def write(target, value):
        check()
        return initializer.__globals__["write_json"](target, value)

    namespace["write_json"] = write
    initialize = FunctionType(initializer.__code__, namespace, initializer.__name__,
                              initializer.__defaults__, initializer.__closure__)
    initialize.__kwdefaults__ = initializer.__kwdefaults__

    class GuardedLedger(native):
        __init__ = initialize

    check()
    return GuardedLedger(path, plan, account_allowance=account_allowance)


def require_ready(plan, output, account):
    from tools import token_epoch_20261025 as epoch

    output = Path(output).absolute()
    expected = {"plan_identity": plan["plan_identity"], "output": str(output),
                "calls": epoch.call_limit(plan),
                "reserved_tokens": epoch.call_limit(plan) * epoch.native.RESERVATION,
                "prior_reservation_ceiling": plan["prior_reservation_ceiling"],
                "account_allowance": epoch.ALLOWANCE}
    matches = [row for row in account["plans"] if
               row["plan_identity"] == plan["plan_identity"] or row["output"] == str(output)]
    if matches:
        if matches != [expected]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Prepared stage changed its existing native reservation")
        return
    intent_path = regular_path(output / "native-claim-intent.json")
    intent = read_json(intent_path) if intent_path.exists() else None
    if intent is not None and (
            not isinstance(intent, dict) or intent.get("version") != "native-claim-intent-v1"
            or intent.get("identity") != digest({key: value for key, value in intent.items() if key != "identity"})
            or intent.get("status") != "pending"
            or intent.get("receipt", {}).get("entry") != expected):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Prepared stage lost its intact native claim intent")
    if (account["reservation_ceiling"] != plan["prior_reservation_ceiling"]
            or intent is not None and intent.get("account_before") != digest(account)):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Stale unspent preparation requires bound retirement and repreparation",
            evidence={"disposition": "STALE_PREPARED_AUTHORITY", "next_action": "retire_and_reprepare",
                      "output": str(output), "plan_identity": plan["plan_identity"],
                      "prepared_ceiling": plan["prior_reservation_ceiling"],
                      "current_ceiling": account["reservation_ceiling"],
                      "intent_identity": intent["identity"] if intent is not None else None})


def readiness(plan, output, *, account_path, check):
    from tools import token_epoch_20261025 as epoch

    account_path = regular_path(account_path)
    check()
    with regular_path(account_path.with_suffix(".lock")).open("a") as account_lock:
        fcntl.flock(account_lock, fcntl.LOCK_EX)
        account = epoch.validate_account(read_json(account_path))
        check()
        require_ready(plan, output, account)


def claim(plan, output, *, account_path, owner_check, stop_check):
    from tools import token_epoch_20261025 as epoch

    output, account_path = Path(output).absolute(), regular_path(account_path)
    intent_path = regular_path(output / "native-claim-intent.json")
    receipt_path = regular_path(output / "account-reservation.json")
    ledger_path = regular_path(output / "allocation-ledger.json")
    execution_path = regular_path(output / "execution.json")
    if (plan.get("plan_identity") != digest({key: value for key, value in plan.items()
                                            if key != "plan_identity"})
            or read_json(output / "plan.json") != plan):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Claim requires its intact persisted plan")
    entry = {"plan_identity": plan["plan_identity"], "output": str(output),
             "calls": epoch.call_limit(plan),
             "reserved_tokens": epoch.call_limit(plan) * epoch.native.RESERVATION,
             "prior_reservation_ceiling": plan["prior_reservation_ceiling"],
             "account_allowance": epoch.ALLOWANCE}
    expected = {"account": str(account_path), "entry": entry,
                "entry_hash": digest(entry), "unknown_tokens_released": False}

    def check():
        if owner_check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Native claim requires exclusive spending ownership")
        stop_check()

    with regular_path(output / "native-claim.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Another native claim owns this stage") from error
        if owner_check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Native claim requires exclusive spending ownership")
        stop_check()
        prepared_hash = None
        if not ledger_path.exists() and execution_path.exists():
            prepared = {"status": "prepared", "plan_identity": plan["plan_identity"],
                        "model_calls": 0, "required": len(plan["calls"]), "human_evidence": False}
            if digest(read_json(execution_path)) != digest(prepared):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Unallocated claim requires its exact prepared marker")
            prepared_hash = digest(execution_path.read_bytes())
        with regular_path(account_path.with_suffix(".lock")).open("a") as account_lock:
            fcntl.flock(account_lock, fcntl.LOCK_EX)
            account = epoch.validate_account(read_json(account_path))
            check()
            require_ready(plan, output, account)
            matches = [row for row in account["plans"] if
                       row["plan_identity"] == plan["plan_identity"] or row["output"] == str(output)]
            if intent_path.exists():
                intent = read_json(intent_path)
                if (intent.get("version") != "native-claim-intent-v1"
                        or intent.get("receipt") != expected
                        or intent.get("identity") != digest({key: value for key, value in intent.items()
                                                              if key != "identity"})
                        or intent.get("status") not in {"pending", "complete"}
                        or not ledger_path.exists() and intent.get("prepared_marker_hash") != prepared_hash):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Native claim intent changed")
            else:
                if matches or receipt_path.exists() or ledger_path.exists() or any(
                        (output / name).exists() for name in
                        ("calls", "executor.json", "allocation-seal.json")):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Cannot invent an intent after native spending")
                intent = {"version": "native-claim-intent-v1", "receipt": expected,
                          "status": "pending", "account_before": digest(account),
                          "prepared_marker_hash": prepared_hash,
                          "events_before": len(account["events"]),
                          "events_prefix": digest(account["events"])}
                intent["identity"] = digest(intent)
                check()
                persist(intent_path, intent)
            if (type(intent.get("events_before")) is not int or intent["events_before"] < 0
                    or digest(account["events"][:intent["events_before"]]) != intent.get("events_prefix")):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Native claim lost its original account history")
            settlements = [event for event in account["events"] if event["kind"] == "settle"
                           and event["usage"]["plan_identity"] == plan["plan_identity"]]
            if settlements or (output / "allocation-seal.json").exists():
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Settled native claim cannot resume")
            if matches:
                events = [event for event in account["events"] if event["kind"] == "reserve"
                          and event["entry"]["plan_identity"] == plan["plan_identity"]]
                if matches != [entry] or events != [{"kind": "reserve", "entry": entry}]:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Claim lacks one exact native reservation")
                if receipt_path.exists() and read_json(receipt_path) != expected:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Claim receipt differs from native reservation")
                if not receipt_path.exists() or not ledger_path.exists():
                    if intent["status"] != "pending" or ledger_path.exists() or any(
                            (output / name).exists() for name in
                            ("calls", "executor.json", "summary.json")):
                        raise RecoveryStop("BLOCKED_ACCOUNTING", "Missing native evidence is not a fresh claim tail")
                    if owner_check() is not True:
                        raise RecoveryStop("BLOCKED_OWNERSHIP", "Claim ownership changed during reconciliation")
                    stop_check()
                    if not receipt_path.exists():
                        persist(receipt_path, expected)
                    check()
                    guarded_ledger(ledger_path, plan, check, account_allowance=epoch.ALLOWANCE)
            elif (intent["status"] != "pending" or receipt_path.exists() or ledger_path.exists()
                  or digest(account) != intent["account_before"]):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Unreserved claim cannot reset changed authority")
        if owner_check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Claim ownership changed before native claim")
        stop_check()
        native = epoch.claim
        namespace = dict(native.__globals__)

        def validate(record, **keywords):
            retained = native.__globals__["validate_account"](record, **keywords)
            check()
            require_ready(plan, output, retained)
            return retained

        def write(path, value):
            check()
            return native.__globals__["write_json"](path, value)

        def ledger(*arguments, **keywords):
            check()
            return guarded_ledger(*arguments, check=check, **keywords)

        namespace.update(validate_account=validate, write_json=write, EpochLedger=ledger)
        invoke = FunctionType(native.__code__, namespace, native.__name__, native.__defaults__, native.__closure__)
        invoke.__kwdefaults__ = native.__kwdefaults__
        receipt = invoke(plan, output, account_path=account_path)
        if receipt != expected:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native claim returned changed authority")
        if intent["status"] != "complete":
            intent = {key: value for key, value in intent.items() if key != "identity"}
            intent["status"] = "complete"
            check()
            persist(intent_path, {**intent, "identity": digest(intent)})
        return receipt
