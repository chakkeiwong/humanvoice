"""Retain restart membership independently of directory discovery and state lag."""

from copy import deepcopy

from humanvoice.artifacts import digest, read_json
from tools import durable_program_supervisor as durable
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist, regular_path

VERSION = "inventory-restart-membership-v1"


def identified(value):
    value = {key: item for key, item in value.items() if key != "identity"}
    return {**value, "identity": digest(value)}


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_ACCOUNTING", detail)


def binding(monitor):
    ceiling = monitor.config["maximum_worker_restarts"]
    require(type(ceiling) is int and ceiling >= 0, "Restart ceiling is invalid")
    return {"version": VERSION, "root": str(monitor.root.absolute()),
            "config_identity": monitor.state["config_identity"],
            "run_id": monitor.state["run_id"], "ceiling": ceiling}


def receipt_path(monitor, receipt):
    job = receipt.get("job")
    require(isinstance(job, str) and job.startswith("job-") and job[4:].isdigit()
            and len(job) <= 16, "Restart receipt lost its canonical job")
    return regular_path(monitor.root / "jobs" / job / "recovery.json")


def verify_receipt(monitor, receipt, ordinal):
    require(isinstance(receipt, dict) and receipt == identified(receipt)
            and type(receipt.get("worker_restart")) is int and receipt["worker_restart"] == ordinal
            and receipt.get("config_identity") == monitor.state["config_identity"]
            and receipt.get("run_id") == monitor.state["run_id"]
            and type(receipt.get("new_provider_calls")) is int and receipt["new_provider_calls"] == 0
            and receipt.get("action") == "resume-with-native-reconciliation",
            "Restart receipt lost its exact run, ordinal or action")
    path = receipt_path(monitor, receipt)
    require(receipt.get("request_identity") == durable.fingerprint(
        read_json(regular_path(path.parent / "request.json"))), "Restart receipt changed its request")
    return path


def read(monitor):
    expected = binding(monitor)
    head_path = regular_path(monitor.root / "restart-head.json")
    marker_path = regular_path(monitor.root / "restart-initialization.json")
    published = monitor.state.get("worker_restarts", 0)
    require(type(published) is int and 0 <= published <= expected["ceiling"],
            "Published restart usage is invalid")
    files = {str(regular_path(path)) for path in (monitor.root / "jobs").glob("*/recovery.json")}
    marker = read_json(marker_path) if marker_path.exists() else None
    if marker is not None:
        require(isinstance(marker, dict) and marker == identified(marker)
                and marker.get("binding") == expected and marker.get("status") in {"pending", "complete"}
                and set(marker) == {"binding", "status", "identity"}, "Restart initialization changed")
    if not head_path.exists():
        require((marker is None or marker["status"] == "pending") and published == 0
                and monitor.state.get("worker_recovery") is None and not files,
                "Committed restart head or receipts disappeared")
        return None
    require(marker is not None, "Restart initialization marker disappeared")
    head = read_json(head_path)
    require(isinstance(head, dict) and head == identified(head) and head.get("binding") == expected
            and set(head) == {"binding", "committed", "pending", "identity"}
            and isinstance(head.get("committed"), list), "Restart head lost its exact binding")
    references = head["committed"]
    require(len(references) <= expected["ceiling"], "Restart head exceeds admitted ceiling")
    receipts, retained_files = [], set()
    for ordinal, reference in enumerate(references, 1):
        require(isinstance(reference, dict) and set(reference) == {"receipt", "sha256"},
                "Restart head changed committed membership")
        receipt = reference["receipt"]
        path = verify_receipt(monitor, receipt, ordinal)
        require(str(path) not in retained_files and path.exists()
                and digest(path.read_bytes()) == reference["sha256"]
                and read_json(path) == receipt, "Committed restart receipt disappeared or changed")
        retained_files.add(str(path))
        receipts.append(receipt)
    pending = head["pending"]
    if pending is not None:
        require(len(receipts) < expected["ceiling"], "Pending restart exceeds admitted ceiling")
        path = verify_receipt(monitor, pending, len(receipts) + 1)
        require(str(path) not in retained_files and pending["job"] == monitor.state.get("job"),
                "Pending restart changed its current job")
        if path.exists():
            require(read_json(path) == pending, "Pending restart receipt changed")
            retained_files.add(str(path))
    require(files == retained_files, "Restart head lost retained receipt membership")
    require(published <= len(receipts) <= published + 1, "Restart head and published usage disagree")
    if published:
        require(monitor.state.get("worker_recovery") == receipts[published - 1],
                "Published restart high-water receipt changed")
    else:
        require(monitor.state.get("worker_recovery") is None, "Zero restart usage has a retained receipt")
    if len(receipts) > published:
        require(pending is None and receipts[-1]["job"] == monitor.state.get("job"),
                "Unpublished restart does not belong to the current job")
    if marker["status"] == "pending":
        require(not references and pending is None and published == 0,
                "Incomplete initialization cannot contain restart spending")
    return head


def initialize(monitor, check):
    head = read(monitor)
    expected = binding(monitor)
    marker_path = regular_path(monitor.root / "restart-initialization.json")
    if head is None:
        check()
        if not marker_path.exists():
            persist(marker_path, identified({"binding": expected, "status": "pending"}))
        check()
        head = identified({"binding": expected, "committed": [], "pending": None})
        persist(regular_path(monitor.root / "restart-head.json"), head)
    if read_json(marker_path)["status"] != "complete":
        check()
        persist(marker_path, identified({"binding": expected, "status": "complete"}))
    return read(monitor)


def commit(monitor, receipt, check):
    head = initialize(monitor, check)
    for reference in head["committed"]:
        if reference["receipt"]["job"] == receipt["job"]:
            require(reference["receipt"] == receipt, "Committed restart cannot change its evidence")
            return deepcopy(receipt)
    if head["pending"] is not None:
        require(head["pending"] == receipt, "Restart cannot replace its pending intent")
    else:
        require(len(head["committed"]) == monitor.state.get("worker_restarts", 0),
                "Publish the prior restart before allocating another")
        if len(head["committed"]) >= head["binding"]["ceiling"]:
            raise RecoveryStop("BLOCKED_BUDGET", "Cumulative worker restart allowance exhausted")
        verify_receipt(monitor, receipt, len(head["committed"]) + 1)
        require(receipt["job"] == monitor.state.get("job"), "Restart intent changed current job")
        head["pending"] = deepcopy(receipt)
        check()
        persist(regular_path(monitor.root / "restart-head.json"), identified(head))
    path = receipt_path(monitor, receipt)
    check()
    if path.exists():
        require(read_json(path) == receipt, "Pending restart publication conflicts")
    else:
        persist(path, receipt)
    head["committed"].append({"receipt": deepcopy(receipt), "sha256": digest(path.read_bytes())})
    head["pending"] = None
    check()
    persist(regular_path(monitor.root / "restart-head.json"), identified(head))
    read(monitor)
    return deepcopy(receipt)
