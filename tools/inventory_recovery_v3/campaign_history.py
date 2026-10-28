"""Publish campaign transitions without confusing pending work with lost history."""

import fcntl
import json
import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.reservations import persist as atomic_persist
from tools.inventory_recovery_v3.reservations import regular_path

VERSION = "inventory-campaign-history-v1"
NATIVE_VERSION = "inventory-native-campaign-history-v1"


def persist(path, value):
    atomic_persist(path, value, temporary_prefix=".campaign-publication-")


def identified(value):
    value = {key: item for key, item in value.items() if key != "identity"}
    return {**value, "identity": digest(value)}


def require(condition, detail):
    if not condition:
        raise RecoveryStop("BLOCKED_ACCOUNTING", detail)


class CampaignHistory:
    def __init__(self, root, seed, *, check):
        self.root = regular_path(Path(root) / "seed.json").parent
        require(isinstance(seed, dict) and seed == identified(seed)
                and set(seed) == {"version", "root", "binding", "maximum_generations",
                                  "initial", "journal", "identity"}
                and seed.get("version") in {VERSION, NATIVE_VERSION} and seed.get("root") == str(self.root)
                and isinstance(seed.get("binding"), dict) and bool(seed["binding"])
                and isinstance(seed.get("journal"), dict) and bool(seed["journal"])
                and type(seed.get("maximum_generations")) is int and seed["maximum_generations"] >= 1,
                "Campaign seed lost its admission, source or journal binding")
        initial = seed["initial"]
        require(isinstance(initial, dict) and set(initial) == {"generation", "output", "plan_identity",
                                                            "transition_identity"}
                and type(initial["generation"]) is int and initial["generation"] == 0
                and all(isinstance(initial[name], str) and initial[name]
                        for name in ("output", "plan_identity", "transition_identity"))
                and initial["output"] == str(self.root / "generation-00"),
                "Campaign initial stage must use its fixed generation-zero path")
        if not callable(check):
            raise TypeError("Campaign mutation requires an owned admission predicate")
        self.seed, self.check = deepcopy(seed), check
        self.handle = None
        self.owner_pid = None
        self.require_initial_binding()

    def require_initial_binding(self):
        binding = self.seed["binding"]
        native = self.seed["version"] == NATIVE_VERSION
        require(native or not (set(binding) & {"proposal", "prepared", "initial_journal"})
                and not regular_path(self.root / "campaign-proposal.json").exists(),
                "Native campaign cannot downgrade its initial binding")
        if native:
            require(set(binding) == {"proposal", "prepared", "initial_journal"}
                    and all(isinstance(value, dict) for value in binding.values()),
                    "Native campaign lost its initial preparation binding")
            proposal, prepared = binding["proposal"], binding["prepared"]
            require(proposal == identified(proposal) and proposal.get("root") == str(self.root)
                    and proposal.get("initial_output") == self.seed["initial"]["output"]
                    and proposal.get("plan_identity") == self.seed["initial"]["plan_identity"]
                    and proposal.get("transition_identity") == self.seed["initial"]["transition_identity"]
                    and isinstance(proposal.get("transition_sha256"), str) and bool(proposal["transition_sha256"])
                    and proposal.get("prepared") == prepared
                    and set(prepared) == {"plan_identity", "plan_sha256", "probe_sha256", "validation_identity"}
                    and all(isinstance(value, str) and value for value in prepared.values())
                    and prepared["plan_identity"] == self.seed["initial"]["plan_identity"],
                    "Native campaign initial descriptor differs from its seed")

    def guard(self):
        from tools.inventory_recovery_v3.descriptors import exclusive_descriptor

        if self.handle is None or self.owner_pid != os.getpid():
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign publication requires its current owner")
        exclusive_descriptor(self.root / "campaign.lock", self.handle.fileno())
        if self.check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign admission or ownership was vetoed")
        return True

    @contextmanager
    def owned(self, *, descriptor=None):
        if self.handle is not None:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign owner cannot be nested")
        if self.check() is not True:
            raise RecoveryStop("BLOCKED_OWNERSHIP", "Campaign admission or ownership was vetoed")
        self.root.mkdir(parents=True, exist_ok=True)
        path = regular_path(self.root / "campaign.lock")
        if descriptor is not None:
            from tools.inventory_recovery_v3.descriptors import exclusive_descriptor

            exclusive_descriptor(path, descriptor)
        selected = os.dup(descriptor) if descriptor is not None else os.open(
            path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(selected, "a") as handle:
            if descriptor is None:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise RecoveryStop("BLOCKED_OWNERSHIP", "Another owner holds campaign publication") from error
            self.handle, self.owner_pid = handle, os.getpid()
            try:
                self.guard()
                yield self
            finally:
                self.handle, self.owner_pid = None, None

    def write(self, name, value, *, immutable=False):
        self.guard()
        path = regular_path(self.root / name)
        if path.exists() and read_json(path) == value:
            return
        require(not immutable or not path.exists(), "Immutable campaign publication changed: " + name)
        persist(path, value)

    def cursor_for(self, stage, record=None):
        return identified({**stage, "seed_identity": self.seed["identity"], "record_identity": record})

    def empty_head(self):
        return identified({"version": VERSION, "seed_identity": self.seed["identity"],
                           "revision": 0, "committed": [], "pending": None})

    def marker(self):
        return identified({"version": VERSION, "seed_identity": self.seed["identity"], "status": "complete"})

    def initialize(self):
        self.guard()
        state = self.status()
        require(state["status"] != "PUBLICATION_IN_PROGRESS", "Initialization changed during observation")
        if state["status"] not in {"UNINITIALIZED", "INITIALIZING"}:
            return state
        require(not any((self.root / "generation-00" / name).exists() for name in
                        ("allocation-ledger.json", "account-reservation.json", "calls", "allocation-seal.json")),
                "Campaign initialization cannot follow native allocation")
        self.write("initialization-intent.json", self.seed, immutable=True)
        self.write("seed.json", self.seed, immutable=True)
        self.write("head.json", self.empty_head(), immutable=True)
        self.write("cursor.json", self.cursor_for(self.seed["initial"]), immutable=True)
        self.write("initialized.json", self.marker(), immutable=True)
        return self.status()

    def names(self):
        return sorted(path.name for path in self.root.iterdir() if
                      path.name.startswith(("transition-", "repair-", "generation-"))) if self.root.exists() else []

    def status(self):
        for _attempt in range(3):
            observed, members = {}, self.names()
            head_path = regular_path(self.root / "head.json")
            observed["head.json"] = head_path.read_bytes() if head_path.exists() else None

            def read_bytes(name, observed=observed):
                path = regular_path(self.root / name)
                if name not in observed:
                    observed[name] = path.read_bytes() if path.exists() else None
                return observed[name]

            def read(name):
                content = read_bytes(name)
                if content is None:
                    return None
                value = json.loads(content)
                require(isinstance(value, dict), "Campaign artifact must contain a JSON object: " + name)
                return value

            read.bytes = read_bytes
            error = None
            try:
                state = self.inspect(read, members)
            except (ValueError, KeyError, TypeError, OSError, RecoveryStop) as caught:
                error = caught
            stable = members == self.names()
            for name, expected in observed.items():
                path = regular_path(self.root / name)
                stable = stable and (path.read_bytes() if path.exists() else None) == expected
            head_path = regular_path(self.root / "head.json")
            stable = stable and (head_path.read_bytes() if head_path.exists() else None) == observed.get("head.json")
            if stable:
                if error is not None:
                    raise error
                return state
        return {"status": "PUBLICATION_IN_PROGRESS", "dispatch_allowed": False}

    def inspect(self, read, members):
        self.require_initial_binding()
        if self.seed["version"] == NATIVE_VERSION:
            binding = self.seed["binding"]
            require(read("campaign-proposal.json") == binding["proposal"],
                    "Native campaign lost its immutable proposal")
            initial = self.seed["initial"]
            transition = read("generation-00/transition.json")
            require(isinstance(transition, dict) and transition == identified(transition)
                    and transition["identity"] == initial["transition_identity"]
                    and digest(read.bytes("generation-00/transition.json")) == binding["proposal"]["transition_sha256"],
                    "Native campaign lost its initial transition")
            self.require_prepared({"output": initial["output"], "transition": transition}, binding["prepared"], read)
        intent, seed, marker = (read(name) for name in
                               ("initialization-intent.json", "seed.json", "initialized.json"))
        head, cursor = read("head.json"), read("cursor.json")
        if marker is None:
            require(intent in (None, self.seed) and seed in (None, self.seed),
                    "Campaign initialization changed its immutable seed")
            require(not any(name.startswith(("transition-", "repair-")) or
                            name.startswith("generation-") and name != "generation-00" for name in members),
                    "Incomplete campaign initialization has advancement evidence")
            require(not seed or intent == self.seed, "Campaign seed lost its initialization intent")
            require(head is None or seed == self.seed and head == self.empty_head(),
                    "Incomplete campaign initialization changed its head")
            require(cursor is None or head == self.empty_head() and cursor == self.cursor_for(self.seed["initial"]),
                    "Incomplete campaign initialization changed its cursor")
            return {"status": "UNINITIALIZED" if intent is None else "INITIALIZING", "dispatch_allowed": False}
        require(intent == self.seed and seed == self.seed and marker == self.marker(),
                "Committed campaign lost initialization membership")
        require(isinstance(head, dict) and head == identified(head) and set(head) ==
                {"version", "seed_identity", "revision", "committed", "pending", "identity"}
                and head["version"] == VERSION and head["seed_identity"] == seed["identity"]
                and isinstance(head["committed"], list), "Campaign head disappeared or changed binding")
        committed, pending = head["committed"], head["pending"]
        require(len(committed) < seed["maximum_generations"], "Campaign head exceeds generation allowance")
        previous = self.cursor_for(seed["initial"])
        allowed = {"generation-00"}
        plans = {previous["plan_identity"]}
        active_record = None
        for generation, reference in enumerate(committed, 1):
            name = f"transition-{generation:02d}.json"
            record = read(name)
            require(isinstance(record, dict) and record == identified(record)
                    and reference == {"generation": generation, "identity": record["identity"]}
                    and record.get("seed_identity") == seed["identity"],
                    "Committed campaign transition disappeared or changed")
            self.require_intent(record["intent"], previous)
            prepared = record["prepared"]
            require(isinstance(prepared, dict) and set(prepared) ==
                    {"plan_identity", "plan_sha256", "probe_sha256", "validation_identity"}
                    and all(isinstance(value, str) and value for value in prepared.values())
                    and prepared["plan_identity"] not in plans, "Campaign repeats a prepared plan")
            plans.add(prepared["plan_identity"])
            self.require_prepared(record["intent"], prepared, read)
            following = self.cursor_for({"generation": generation, "output": record["intent"]["output"],
                "plan_identity": prepared["plan_identity"],
                "transition_identity": record["intent"]["transition"]["identity"]}, record["identity"])
            repair_name = f"repair-{generation:02d}.json"
            repair = read(repair_name)
            allowed.update((name, repair_name, f"generation-{generation:02d}"))
            if pending is not None and generation == len(committed) and pending == record["intent"]:
                active_record = record
                require(cursor in (previous, following), "Pending campaign cursor has no exact predecessor proof")
                require(repair is None or cursor == following and repair == self.repair_record(record),
                        "Repair receipt precedes its cursor or changed identity")
            else:
                require(repair == self.repair_record(record), "Committed campaign repair disappeared or changed")
            previous = following
        if pending is not None:
            if active_record is None:
                self.require_intent(pending, previous)
                generation = pending["generation"]
                require(generation < seed["maximum_generations"], "Pending campaign exceeds generation allowance")
                require(cursor == previous, "Campaign cursor advanced before head membership")
                name = f"transition-{generation:02d}.json"
                record = read(name)
                require(record is None or record == identified(record) and record.get("intent") == pending
                        and record.get("seed_identity") == seed["identity"], "Pending transition publication changed")
                require(read(f"repair-{generation:02d}.json") is None, "Repair receipt precedes head membership")
                allowed.update((name, f"generation-{generation:02d}"))
            revision = 3 * len(committed) + (1 if active_record is None else -1)
        else:
            require(cursor == previous, "Campaign cursor differs from committed membership")
            revision = 3 * len(committed)
        require(type(head["revision"]) is int and head["revision"] == revision,
                "Campaign head revision disagrees with publication phase")
        require(set(members) <= allowed, "Campaign contains unreferenced generation or receipt evidence")
        for name in members:
            if name.startswith("generation-"):
                regular_path(self.root / name / "plan.json")
        return {"status": "PENDING" if pending is not None else "READY", "head": head,
                "cursor": cursor, "dispatch_allowed": False}

    def require_intent(self, intent, previous):
        require(isinstance(intent, dict) and intent == identified(intent) and set(intent) ==
                {"seed_identity", "generation", "previous", "output", "transition", "identity"}
                and intent["seed_identity"] == self.seed["identity"] and intent["previous"] == previous
                and type(intent["generation"]) is int and intent["generation"] == previous["generation"] + 1
                and intent["output"] == str(self.root / f"generation-{intent['generation']:02d}"),
                "Campaign intent changed its fixed predecessor or generation")
        transition = intent["transition"]
        require(isinstance(transition, dict) and transition == identified(transition)
                and transition.get("parent_plan_identity") == previous["plan_identity"]
                and transition.get("proof", {}).get("predecessor") == previous["output"],
                "Campaign transition differs from its exact predecessor")

    def begin(self, transition):
        self.guard()
        state = self.status()
        require(state["status"] in {"READY", "PENDING"}, "Campaign must be explicitly initialized")
        head = state["head"]
        if head["pending"] is not None:
            require(head["pending"]["transition"] == transition, "Cannot replace a pending campaign transaction")
            return head["pending"]
        generation = state["cursor"]["generation"] + 1
        if generation >= self.seed["maximum_generations"]:
            raise RecoveryStop("BLOCKED_BUDGET", "Campaign generation allowance exhausted")
        intent = identified({"seed_identity": self.seed["identity"], "generation": generation,
            "previous": state["cursor"], "output": str(self.root / f"generation-{generation:02d}"),
            "transition": deepcopy(transition)})
        self.require_intent(intent, state["cursor"])
        self.write("head.json", identified({**head, "revision": head["revision"] + 1, "pending": intent}))
        return intent

    def repair_record(self, record):
        return identified({"seed_identity": self.seed["identity"], "transition_record": record["identity"],
                           "prepared": record["prepared"], "journal": self.seed["journal"], "model_calls": 0})

    def require_prepared(self, intent, prepared, observer=None):
        output = Path(intent["output"])
        plan_path, probe_path = (regular_path(output / name) for name in ("plan.json", "admission-probe.json"))
        require(plan_path.is_file() and probe_path.is_file(), "Prepared campaign lost persisted plan or probe")
        if observer is None:
            plan, probe = read_json(plan_path), read_json(probe_path)
            plan_bytes, probe_bytes = plan_path.read_bytes(), probe_path.read_bytes()
        else:
            plan, probe = (observer(str(path.relative_to(self.root))) for path in (plan_path, probe_path))
            plan_bytes, probe_bytes = (observer.bytes(str(path.relative_to(self.root))) for path in (plan_path, probe_path))
        require(isinstance(plan, dict) and isinstance(probe, dict)
                and plan.get("plan_identity") == prepared["plan_identity"]
                and plan["plan_identity"] == digest({key: value for key, value in plan.items() if key != "plan_identity"})
                and digest(plan_bytes) == prepared["plan_sha256"]
                and digest(probe_bytes) == prepared["probe_sha256"]
                and probe.get("transition") == intent["transition"]["identity"]
                and probe.get("status") == "pass" and type(probe.get("model_calls")) is int
                and probe["model_calls"] == 0, "Prepared campaign descriptor differs from persisted evidence")

    def reconcile(self, validate_prepared):
        self.guard()
        state = self.status()
        require(state["status"] in {"READY", "PENDING"}, "Campaign is not initialized or coherently observed")
        if state["status"] == "READY":
            return state
        head, intent = state["head"], state["head"]["pending"]
        generation = intent["generation"]
        from tools.inventory_history_adoption import no_inference

        self.guard()
        with no_inference():
            prepared = validate_prepared(deepcopy(intent), self.guard)
        self.guard()
        require(self.status() == state, "Campaign changed during prepared-stage validation")
        require(isinstance(prepared, dict) and set(prepared) ==
                {"plan_identity", "plan_sha256", "probe_sha256", "validation_identity"}
                and all(isinstance(value, str) and value for value in prepared.values()),
                "Prepared campaign stage lacks exact validation evidence")
        self.require_prepared(intent, prepared)
        prior_plans = {self.seed["initial"]["plan_identity"]}
        for reference in head["committed"]:
            if reference["generation"] < generation:
                previous = read_json(regular_path(self.root / f"transition-{reference['generation']:02d}.json"))
                prior_plans.add(previous["prepared"]["plan_identity"])
        require(prepared["plan_identity"] not in prior_plans, "Campaign repeats a prepared plan")
        record = identified({"seed_identity": self.seed["identity"], "intent": intent, "prepared": prepared})
        self.write(f"transition-{generation:02d}.json", record, immutable=True)
        reference = {"generation": generation, "identity": record["identity"]}
        if len(head["committed"]) < generation:
            head = identified({**head, "revision": head["revision"] + 1,
                               "committed": [*head["committed"], reference]})
            self.write("head.json", head)
        else:
            require(head["committed"][-1] == reference, "Prepared stage differs from committed transition")
        cursor = self.cursor_for({"generation": generation, "output": intent["output"],
            "plan_identity": prepared["plan_identity"], "transition_identity": intent["transition"]["identity"]},
            record["identity"])
        self.write("cursor.json", cursor)
        self.write(f"repair-{generation:02d}.json", self.repair_record(record), immutable=True)
        self.guard()
        self.require_prepared(intent, prepared)
        self.status()
        self.write("head.json", identified({**head, "revision": head["revision"] + 1, "pending": None}))
        return self.status()
