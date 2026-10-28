"""Retain native spending prefixes before mutation and across cold recovery."""

import fcntl
import json
import os
from contextlib import contextmanager
from copy import deepcopy

from humanvoice.artifacts import digest, read_json
from tools import automatic_call_grant as grants
from tools import token_epoch_20261025 as epoch
from tools.inventory_recovery_v3.campaign_binding import account_floor
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.installed_authority import canonical_path
from tools.inventory_recovery_v3.reservations import persist, regular_path

VERSION = "native-consumption-floors-v1"
RESOURCES = ("account", "stages")


def same(left, right):
    return digest({"value": left}) == digest({"value": right})


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_ACCOUNTING", detail)


def identified(value):
    value = {key: item for key, item in value.items() if key != "identity"}
    return {**value, "identity": digest(value)}


def seed(configuration, binding):
    scope = configuration["execution_authority"]
    account = canonical_path(scope["account"])
    grant = canonical_path(scope["grant"])
    require(binding["identity"] == configuration["campaign_binding_identity"]
            and same(binding, identified(binding))
            and binding["account_floor"]["path"] == str(account)
            and binding["grant"] == str(grant)
            and binding["grant_identity"] == scope["grant_identity"],
            "Consumption floors require the configuration's bound native campaign")
    return identified({"version": VERSION, "configuration": digest(configuration),
        "campaign_binding": binding["identity"],
        "root": str(canonical_path(configuration["campaign_root"]) / "consumption-floors"),
        "grant": str(grant), "grant_identity": scope["grant_identity"],
        "grant_sha256": binding["immutable"][str(grant)],
        "initial": {"account": deepcopy(binding["account_floor"]),
            "stages": {"path": str(grant.with_suffix(".stages.json")),
                "count": len(binding["grant_stages_floor"]),
                "sha256": digest(binding["grant_stages_floor"])}}})


class ConsumptionFloors:
    def __init__(self, configuration, binding, *, check):
        self.seed = seed(configuration, binding)
        self.root = canonical_path(self.seed["root"])
        self.check = check

    def guard(self):
        if self.check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Consumption floor ownership was vetoed")
        grant = regular_path(self.seed["grant"])
        require(digest(grant.read_bytes()) == self.seed["grant_sha256"],
                "Consumption floor lost its immutable grant definition")

    def path(self, resource):
        require(resource in RESOURCES, "Unknown native consumption resource")
        return regular_path(self.seed["initial"][resource]["path"])

    def current(self, resource):
        path = self.path(resource)
        value = read_json(path) if path.exists() else None
        require(resource == "stages" or isinstance(value, dict), "Native account disappeared")
        if resource == "stages" and value is None:
            value = {"stages": []}
        return value

    def snapshot(self, resource, value):
        path = self.path(resource)
        require(isinstance(value, dict), "Native consumption must be an object")
        if resource == "account":
            from tools.inventory_recovery_v3.accounting import verify_settlement

            epoch.validate_account(deepcopy(value), usage_reader=lambda output: verify_settlement(output)["report"])
            return account_floor(path, value)
        require(set(value) == {"stages"} and isinstance(value["stages"], list),
                "Native grant stages lost exact membership")
        seen, outputs = set(), set()
        for row in value["stages"]:
            require(isinstance(row, dict) and isinstance(row.get("output"), str),
                    "Native stage hold is malformed")
            output = canonical_path(row["output"])
            plan = read_json(regular_path(output / "plan.json"))
            expected = {"output": str(output), "plan_identity": plan["plan_identity"],
                "grant_identity": self.seed["grant_identity"],
                "maximum_calls": grants.call_limit(plan)}
            require(same(row, expected) and same(plan, identified_plan(plan))
                    and row["plan_identity"] not in seen and row["output"] not in outputs,
                    "Native grant stage differs from its unique plan authority")
            seen.add(row["plan_identity"])
            outputs.add(row["output"])
        return {"path": str(path), "count": len(value["stages"]),
                "sha256": digest(value["stages"])}

    def extension(self, resource, floor, value):
        current = self.snapshot(resource, value)
        return self._extension(resource, floor, value, current)

    def _extension(self, resource, floor, value, current):
        require(isinstance(floor, dict) and set(floor) == set(current)
                and floor["path"] == current["path"], "Consumption floor changed its resource")
        if resource == "account":
            require(same(floor["fixed"], current["fixed"]) and all(
                type(floor[name]) is int and 0 <= floor[name] <= current[name]
                and digest(value[name][:floor[name]]) == floor[name + "_hash"]
                for name in ("events", "plans")), "Native account lost a committed consumption prefix")
        else:
            require(type(floor["count"]) is int and 0 <= floor["count"] <= current["count"]
                    and digest(value["stages"][:floor["count"]]) == floor["sha256"],
                    "Native grant lost a committed stage prefix")
        return current

    def initial_head(self, resource):
        return identified({"version": VERSION, "seed": self.seed["identity"],
            "resource": resource, "committed": self.seed["initial"][resource],
            "history": [], "pending": None})

    def retained_target(self, resource, floor, current):
        self.extension(resource, floor, current)
        if resource == "stages":
            return {"stages": current["stages"][:floor["count"]]}
        target = deepcopy(current)
        for event in target["events"][floor["events"]:]:
            if event["kind"] == "reserve":
                target["reservation_ceiling"] -= event["entry"]["reserved_tokens"]
            elif event["kind"] == "settle":
                target["reservation_ceiling"] += event["released_headroom_tokens"]
            else:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Pending target crossed an account authorization epoch")
        target["gross_reservation_ceiling"] -= sum(
            entry["reserved_tokens"] for entry in target["plans"][floor["plans"]:])
        target["events"] = target["events"][:floor["events"]]
        target["plans"] = target["plans"][:floor["plans"]]
        require(same(self.snapshot(resource, target), floor), "Pending account target lost its native prefix")
        return target

    def observation(self, resource):
        paths = [self.path(resource), regular_path(self.seed["grant"]),
            *(self.root / name for name in ("seed.json", "initialized.json", resource + "-head.json")),
            *sorted(self.root.glob(resource + "-[0-9]*.json"))]
        result = {}
        for target in paths:
            path = regular_path(target)
            try:
                result[str(path)] = path.read_bytes()
            except FileNotFoundError:
                result[str(path)] = None
        return result

    def status(self, resource):
        for _attempt in range(3):
            before = self.observation(resource)
            error, state = None, None
            try:
                state = self.inspect(resource)
            except (RecoveryStop, ValueError, KeyError, TypeError, OSError) as caught:
                error = caught
            if before == self.observation(resource):
                if error is not None:
                    raise error
                return state
        return {"status": "PUBLICATION_IN_PROGRESS", "dispatch_allowed": False}

    @contextmanager
    def locked(self):
        self.guard()
        path = regular_path(self.root / "publication.lock")
        with os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RecoveryStop("BLOCKED_OWNERSHIP", "Another native floor publication owns this campaign") from error
            self.guard()
            yield

    def initialize(self):
        self.guard()
        regular_path(self.root / "seed.json")
        self.root.mkdir(parents=True, exist_ok=True)
        with self.locked():
            marker = regular_path(self.root / "initialized.json")
            if marker.exists():
                for resource in RESOURCES:
                    self.inspect(resource)
                return
            steps = [("seed.json", self.seed), *[(name + "-head.json", self.initial_head(name))
                for name in RESOURCES], ("initialized.json", {"version": VERSION, "seed": self.seed["identity"]})]
            names = {path.name for path in self.root.iterdir()
                     if path.name != "publication.lock" and not path.name.startswith(".floor-")}
            require(names <= {name for name, _value in steps}, "Cannot initialize floors after consumption")
            missing = False
            for name, expected in steps[:-1]:
                path = regular_path(self.root / name)
                if path.exists():
                    require(not missing and same(read_json(path), expected),
                            "Incomplete consumption initialization changed its publication order")
                else:
                    missing = True
            for resource in RESOURCES:
                require(same(self.snapshot(resource, self.current(resource)), self.seed["initial"][resource]),
                        "Cannot initialize floors after native spending")
            for name, value in steps:
                path = regular_path(self.root / name)
                if not path.exists():
                    self.guard()
                    persist(path, value, temporary_prefix=".floor-")

    def inspect(self, resource):
        self.path(resource)
        observed = {}

        def read(path):
            path = regular_path(path)
            content = path.read_bytes()
            observed[path] = content
            return json.loads(content)

        require(same(read(self.root / "seed.json"), self.seed)
                and same(read(self.root / "initialized.json"), {"version": VERSION, "seed": self.seed["identity"]}),
                "Consumption floors lost completed initialization")
        grant = regular_path(self.seed["grant"])
        require(digest(grant.read_bytes()) == self.seed["grant_sha256"],
                "Consumption floor lost its immutable grant definition")
        head_path = self.root / (resource + "-head.json")
        head = read(head_path)
        require(isinstance(head, dict) and same(head, identified(head))
                and set(head) == set(self.initial_head(resource))
                and head["version"] == VERSION and head["seed"] == self.seed["identity"]
                and head["resource"] == resource and isinstance(head["history"], list),
                "Native consumption head lost its exact binding")
        value = self.current(resource)
        current = self.snapshot(resource, value)
        previous = self.seed["initial"][resource]
        self._extension(resource, previous, value, current)
        names = set()

        def transition(record, sequence):
            require(isinstance(record, dict) and same(record, identified(record))
                    and set(record) == {"version", "seed", "resource", "sequence", "before", "after",
                        "target_hash", "operation", "identity"}
                    and record["version"] == VERSION and record["seed"] == self.seed["identity"]
                    and record["resource"] == resource and type(record["sequence"]) is int
                    and record["sequence"] == sequence and same(record["before"], previous)
                    and record["operation"] in ({"reserve", "settle", "observe"} if resource == "account"
                                                else {"hold", "observe"})
                    and isinstance(record["target_hash"], str) and len(record["target_hash"]) == 64,
                    "Native floor transition lost its exact predecessor")
            after = record["after"]
            require(isinstance(after, dict) and set(after) == set(previous)
                    and after["path"] == previous["path"], "Native floor transition changed its scope")
            counters = ("events", "plans") if resource == "account" else ("count",)
            require(all(type(after[name]) is int and after[name] >= previous[name] for name in counters)
                    and any(after[name] > previous[name] for name in counters),
                    "Native floor transition renewed or omitted consumption")
            if resource == "account":
                require(same(after["fixed"], previous["fixed"]), "Native floor transition changed immutable account")
                if record["operation"] != "observe":
                    require(after["events"] == previous["events"] + 1
                            and after["plans"] == previous["plans"] + (record["operation"] == "reserve"),
                            "Native floor transition omitted a spending boundary")
            elif record["operation"] == "hold":
                require(after["count"] == previous["count"] + 1, "Native floor transition omitted a stage hold")
            return after

        for sequence, identity in enumerate(head["history"], 1):
            name = resource + f"-{sequence:08d}.json"
            record = read(self.root / name)
            after = transition(record, sequence)
            require(record["identity"] == identity, "Committed native floor evidence changed")
            self._extension(resource, after, value, current)
            previous = after
            names.add(name)
        require(same(head["committed"], previous), "Native floor head lost committed history")
        pending = head["pending"]
        status = "READY" if same(current, previous) else "EXTENDED"
        if pending is not None:
            after = transition(pending, len(head["history"]) + 1)
            name = resource + f"-{pending['sequence']:08d}.json"
            target = regular_path(self.root / name)
            if target.exists():
                require(same(read(target), pending), "Pending native floor evidence changed")
                names.add(name)
            if same(current, previous) and pending["operation"] != "observe":
                status = "PENDING_BEFORE"
            else:
                retained = self.retained_target(resource, after, value)
                require(digest(retained) == pending["target_hash"], "Pending native mutation changed its exact target")
                require(target.exists() or pending["operation"] == "observe",
                        "Applied native mutation lost its write-ahead transition")
                status = "PENDING_AFTER" if same(current, after) else "PENDING_EXTENDED"
        require({path.name for path in self.root.glob(resource + "-[0-9]*.json")} == names,
                "Native floor lost retained transition membership")
        require(all(regular_path(path).read_bytes() == content for path, content in observed.items())
                and same(self.current(resource), value), "Native consumption changed during inspection")
        return {"status": status, "head": head, "value": value, "floor": current}

    def _commit(self, resource, state):
        pending = state["head"]["pending"]
        path = regular_path(self.root / (resource + f"-{pending['sequence']:08d}.json"))
        require(path.exists() or pending["operation"] == "observe",
                "Applied native mutation lost its write-ahead transition")
        if not path.exists():
            self.guard()
            persist(path, pending, temporary_prefix=".floor-")
        self.guard()
        require(same(self.inspect(resource)["head"], state["head"]), "Pending floor changed before commit")
        require(digest(self.retained_target(resource, pending["after"], self.current(resource)))
                == pending["target_hash"], "Cannot commit a floor before its exact native mutation")
        descriptor = os.open(self.path(resource).parent, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        head = {**state["head"], "committed": pending["after"],
                "history": [*state["head"]["history"], pending["identity"]], "pending": None}
        self.guard()
        persist(regular_path(self.root / (resource + "-head.json")), identified(head), temporary_prefix=".floor-")

    def reconcile(self, resource):
        with self.locked():
            state = self.inspect(resource)
            if state["status"] in {"PENDING_AFTER", "PENDING_EXTENDED"}:
                self._commit(resource, state)
                state = self.inspect(resource)
            if state["status"] == "EXTENDED":
                self._intent(resource, state, state["value"], "observe")
                self._commit(resource, self.inspect(resource))
            return self.inspect(resource)

    def _intent(self, resource, state, value, operation):
        after = self.extension(resource, state["head"]["committed"], value)
        require(operation in ({"reserve", "settle", "observe"} if resource == "account"
                              else {"hold", "observe"}), "Unknown native spending operation")
        before = state["head"]["committed"]
        if operation == "observe":
            require(same(value, state["value"]), "Sibling observation cannot invent native consumption")
        elif resource == "account":
            require(after["events"] == before["events"] + 1
                    and after["plans"] == before["plans"] + (operation == "reserve")
                    and value["events"][-1]["kind"] == operation,
                    "Native write must contain one exact spending event")
        else:
            require(after["count"] == before["count"] + 1, "Native write must contain one stage hold")
        pending = identified({"version": VERSION, "seed": self.seed["identity"],
            "resource": resource, "sequence": len(state["head"]["history"]) + 1,
            "before": state["head"]["committed"], "after": after,
            "target_hash": digest(value), "operation": operation})
        self.guard()
        require(same(self.inspect(resource), state), "Native consumption changed before write-ahead intent")
        self.guard()
        persist(regular_path(self.root / (resource + "-head.json")),
                identified({**state["head"], "pending": pending}), temporary_prefix=".floor-")

    def write(self, resource, value, *, operation, writer):
        with self.locked():
            state = self.inspect(resource)
            require(state["status"] != "EXTENDED", "Reconcile sibling consumption before native mutation")
            if state["head"]["pending"] is None:
                require(not same(state["floor"], self.snapshot(resource, value)),
                        "Native floor write must advance consumption")
                self._intent(resource, state, value, operation)
                state = self.inspect(resource)
            pending = state["head"]["pending"]
            require(pending["operation"] == operation and pending["target_hash"] == digest(value)
                    and same(pending["after"], self.snapshot(resource, value)),
                    "Native mutation differs from its retained write-ahead intent")
            target = regular_path(self.root / (resource + f"-{pending['sequence']:08d}.json"))
            if not target.exists():
                self.guard()
                persist(target, pending, temporary_prefix=".floor-")
            self.guard()
            if state["status"] == "PENDING_BEFORE":
                require(same(self.inspect(resource)["value"], state["value"]),
                        "Native consumption changed before owned write")
                self.guard()
                writer(self.path(resource), value)
            self._commit(resource, self.inspect(resource))


def identified_plan(plan):
    body = {key: value for key, value in plan.items() if key != "plan_identity"}
    return {**body, "plan_identity": digest(body)}
