"""Carry all predecessor ownership exclusions and restart charges into adoption."""

import json
import os
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest
from tools import inventory_history_handover as native
from tools.inventory_recovery_v2 import control
from tools.inventory_recovery_v3 import installed_authority
from tools.inventory_recovery_v3.descriptors import exclusive_descriptor

DESCRIPTORS = "HUMANVOICE_CHAINED_HANDOVER_FDS"


def validate_chain(records):
    if not isinstance(records, list) or not records:
        raise ValueError("Chained handover requires retained adoption records")
    seen, previous, spent = set(), None, 0
    ceiling = records[0]["predecessor"]["ceiling"]
    for record in records:
        predecessor = record["predecessor"]
        if (record.get("version") != "inventory-history-handover-v1"
                or record.get("identity") != digest({key: value for key, value in record.items()
                                                       if key != "identity"})
                or record.get("handover_charge") != 1
                or predecessor["root"] in seen or record["replacement"] in seen
                or predecessor["root"] == record["replacement"]):
            raise ValueError("Handover chain has a changed record or repeated ownership root")
        if previous is not None and (predecessor["root"] != previous["replacement"]
                or predecessor["ceiling"] != previous["maximum_worker_restarts"]):
            raise ValueError("Handover chain skipped the latest installed supervisor")
        configuration = native.read_json(native.safe_path(Path(predecessor["root"]) / "config.json"))
        native.validate(record, predecessor["root"], configuration,
                        record["replacement"], record["contract"])
        if previous is not None and configuration.get("adoption_identity") != previous["identity"]:
            raise ValueError("Successor configuration lost its prior adoption binding")
        seen.add(predecessor["root"])
        spent += predecessor["inherited_restarts"] + 1
        if record["maximum_worker_restarts"] != ceiling - spent:
            raise ValueError("Chained adoption renewed cumulative restart authority")
        previous = record
    return {"original_ceiling": ceiling, "cumulative_restarts": spent,
            "remaining_restarts": records[-1]["maximum_worker_restarts"]}


def proposal(previous, current_root, expected, replacement, contract, *, stop_bindings=None):
    installed = installed_authority.capture()
    current_root = installed_authority.canonical_path(current_root)
    replacement = installed_authority.canonical_path(replacement)
    if (previous != installed["records"] or str(current_root) != installed["root"]
            or expected != installed["configuration"]
            or stop_bindings is not None and stop_bindings != installed["stop_bindings"]):
        raise ValueError("Handover must preserve the complete installed authority")
    stop_bindings = installed["stop_bindings"]
    validate_chain(previous)
    current_root, replacement = native.safe_path(current_root), native.safe_path(replacement)
    if str(current_root) != previous[-1]["replacement"]:
        raise ValueError("Adoption must use the latest installed history supervisor")
    next_record = native.proposal(current_root, expected, replacement, contract)
    records = [*deepcopy(previous), next_record]
    totals = validate_chain(records)
    if (not isinstance(stop_bindings, list) or not stop_bindings
            or any(set(row) != {"root", "contract"} for row in stop_bindings)
            or len({row["root"] for row in stop_bindings}) != len(stop_bindings)):
        raise ValueError("Adoption requires explicit inherited campaign stop authorities")
    for row in stop_bindings:
        native.safe_path(row["root"])
    value = {"version": "inventory-chained-handover-v1", "records": records,
             "replacement": str(replacement), "contract": deepcopy(contract),
             "stop_bindings": deepcopy(stop_bindings), "installed": installed,
             **totals, "live_execution_enabled": False}
    return {**value, "identity": digest(value)}


def validate(record):
    if (not isinstance(record, dict) or record.get("version") != "inventory-chained-handover-v1"
            or record.get("identity") != digest({key: value for key, value in record.items()
                                                   if key != "identity"})
            or not isinstance(record.get("records"), list) or len(record["records"]) < 2
            or record.get("live_execution_enabled") is not False):
        raise ValueError("Chained handover binding changed")
    latest = record["records"][-1]
    expected = native.read_json(native.safe_path(Path(latest["predecessor"]["root"]) / "config.json"))
    rebuilt = proposal(record["records"][:-1], latest["predecessor"]["root"], expected,
                       record["replacement"], record["contract"], stop_bindings=record["stop_bindings"])
    if record != rebuilt:
        raise ValueError("Chained handover changed exclusions or cumulative limits")
    return record


def require_running(record):
    validate(record)
    for binding in record["stop_bindings"]:
        native.safe_path(Path(binding["root"]) / "user-stop.json")
        native.safe_path(Path(binding["root"]) / "resume-authorization.json")
        control.require_running(binding["root"], contract=binding["contract"])


class ChainLease:
    def __init__(self, record, held):
        self.record = deepcopy(record)
        self.held = held

    def __len__(self):
        return len(self.held)

    def __iter__(self):
        return iter(self.held)

    def check(self):
        require_running(self.record)
        installed_authority.require_environment(self.record["installed"])
        for held in self.held:
            held.check()
            for path, handle in held.handles:
                exclusive_descriptor(path, handle.fileno())
        return True

    def capsule(self):
        self.check()
        descriptors = [handle.fileno() for held in self.held for _path, handle in held.handles]
        return {"pass_fds": tuple(descriptors), "environment": {DESCRIPTORS: json.dumps(
            {"identity": self.record["identity"], "descriptors": descriptors})}}


def exclusions(adoption):
    root = Path(adoption["predecessor"]["root"])
    return [root / "monitor.lock", *[root / "jobs" / job / "worker.lock"
                                     for job in adoption["predecessor"]["jobs"]]]


@contextmanager
def lease(record, *, shared_locks=()):
    validate(record)
    installed_authority.require_environment(record["installed"])
    shared_locks = tuple(sorted({Path(path) for path in record["installed"]["shared_locks"]}
                                | {installed_authority.canonical_path(path) for path in shared_locks}))
    with ExitStack() as stack:
        held = []
        for adoption in record["records"]:
            root = Path(adoption["predecessor"]["root"])
            expected = native.read_json(root / "config.json")
            handles = [native.lock(stack, path) for path in exclusions(adoption)]
            item = native.Lease(adoption, root, expected, adoption["replacement"],
                                adoption["contract"], handles)
            stack.callback(setattr, item, "active", False)
            item.check(shared_locks)
            held.append(item)
        chain = ChainLease(record, held)
        chain.check()
        yield chain


@contextmanager
def inherited(record):
    validate(record)
    capsule = json.loads(os.environ.get(DESCRIPTORS, "null"))
    count = sum(len(exclusions(adoption)) for adoption in record["records"])
    if (not isinstance(capsule, dict) or set(capsule) != {"identity", "descriptors"}
            or capsule["identity"] != record["identity"]
            or not isinstance(capsule["descriptors"], list)
            or len(capsule["descriptors"]) != count
            or any(type(item) is not int or item < 3 for item in capsule["descriptors"])
            or len(set(capsule["descriptors"])) != count):
        raise ValueError("Cold child requires every inherited predecessor descriptor")
    with ExitStack() as stack:
        descriptors = iter(capsule["descriptors"])
        held = []
        for adoption in record["records"]:
            root = Path(adoption["predecessor"]["root"])
            expected = native.read_json(root / "config.json")
            handles = []
            for path in exclusions(adoption):
                descriptor = next(descriptors)
                exclusive_descriptor(path, descriptor)
                handle = stack.enter_context(os.fdopen(os.dup(descriptor), "a+"))
                handles.append((path, handle))
            item = native.Lease(adoption, root, expected, adoption["replacement"],
                                adoption["contract"], handles)
            stack.callback(setattr, item, "active", False)
            held.append(item)
        chain = ChainLease(record, held)
        chain.check()
        yield chain
