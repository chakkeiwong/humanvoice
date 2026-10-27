"""Derive request ancestry from actual native observations and frozen split rules."""

import json
from copy import deepcopy
from itertools import pairwise
from pathlib import Path

from humanvoice.artifacts import digest, load_spans, read_json
from tools import inventory_size_recovery
from tools.inventory_recovery_v3 import registration, runtime, semantics
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.lineage import validate_lineage
from tools.inventory_recovery_v3.reservations import persist, regular_path


def context_scope(request):
    marker = "\n\nInventory context request: "
    if marker not in request["prompt"]:
        return None
    text = request["prompt"].rsplit(marker, 1)[1]
    value, _end = json.JSONDecoder().raw_decode(text)
    if (not isinstance(value, dict) or value.get("policy") != semantics.context.VERSION
            or not isinstance(value.get("window"), str) or not value["window"]
            or not isinstance(value.get("source_file"), str) or not value["source_file"]
            or type(value.get("repair_round")) is not int or value["repair_round"] < 0):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Native context lost its original source window")
    return value


def source_observation(observation):
    value = deepcopy(observation)
    if value["purpose"] == "concept_extraction":
        value["spans"] = {identifier: semantics.split.source_basis(row)
                          for identifier, row in value["spans"].items()}
    return value


class NativeRequests:
    def __init__(self, plan, output, journal, owner):
        self.plan, self.output, self.journal, self.owner = plan, Path(output).absolute(), journal, owner
        self.snapshot = Path(plan["snapshot"])
        self.spans = load_spans(self.snapshot)
        marker = inventory_size_recovery.selected_policy(self.snapshot)
        self.size_rules = marker["rules"] if marker else []
        self.rules = plan[runtime.FIELD].get("split_rules", [])
        self.semantic_options = semantics.plan_policy(plan)
        active = semantics.ACTIVE.get()
        if active is None:
            semantics.validate_rules(self.rules, **self.semantic_options)
        elif active["rules"] != self.rules:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native ownership changed its validated semantic rules")
        if self.semantic_options:
            expected = {**self.semantic_options, "rules": self.rules}
            if active is not None and semantics.DOCUMENT.get() != expected:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Native ownership lacks its validated document semantic policy")
            semantics.validate_graph(self.rules, self.spans, self.size_rules)

    def root(self, scope, owned):
        if getattr(self, "semantic_options", {}):
            return registration.scoped_root(self.journal, scope=scope, owned=self.owned(scope, owned))
        return self.journal.register_root(purpose=scope["purpose"], owned=self.owned(scope, owned))

    def split(self, identity, children, evidence, inherited):
        if getattr(self, "semantic_options", {}):
            return registration.register_split(self.journal, identity, children, evidence=evidence, inherited=inherited)
        return self.journal.inherit_split(identity, children, evidence=evidence)

    def owned(self, scope, identifiers):
        return [digest({"scope": scope, "identifier": identifier}) for identifier in identifiers]

    def source_file(self, identifiers):
        if (not isinstance(identifiers, list) or not identifiers
                or len(identifiers) != len(set(identifiers)) or any(identifier not in self.spans for identifier in identifiers)):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native request lost unique immutable source membership")
        files = {self.spans[identifier]["source_file"] for identifier in identifiers}
        if len(files) != 1:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native request crossed original source files")
        return next(iter(files))

    def extraction(self, observation):
        window = observation["window"]
        source_file = self.source_file(window["span_ids"])
        spans = observation["spans"]
        if any(semantics.split.source_basis(spans[identifier]) != semantics.split.source_basis(self.spans[identifier])
               for identifier in window["span_ids"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Extraction observation changed immutable source")
        root_window = window["window_id"].split(".split-", 1)[0]
        scope = {"source_file": source_file, "window": root_window, "purpose": "concept_extraction"}
        rules = [{"window": row["window"], "children": row["children"], "identity": digest(row), "inherited": True}
                 for row in self.size_rules]
        rules += [{"window": row["recipe"]["window"], "children": row["recipe"]["children"], "identity": row["identity"],
                   "inherited": row in self.semantic_options.get("inherited", self.rules)}
                  for row in self.rules if row["recipe"]["kind"] == "extraction"]
        rules = [row for row in rules if row["window"]["window_id"].split(".split-", 1)[0] == root_window
                 and self.source_file(row["window"]["span_ids"]) == source_file]
        roots = [row["window"] for row in rules if row["window"]["window_id"] == root_window]
        if not roots and window["window_id"] != root_window:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Split extraction lost its inherited root")
        root = roots[0] if roots else window
        if any(value != root for value in roots):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited extraction roots disagree")
        lineage = self.root(scope, root["span_ids"])
        windows = {root_window: (root, lineage)}
        for row in sorted(rules, key=lambda item: item["window"]["window_id"].count(".split-")):
            name = row["window"]["window_id"]
            if name not in windows or windows[name][0] != row["window"]:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited extraction split skipped its parent")
            children = self.split(windows[name][1]["identity"],
                [self.owned(scope, child["span_ids"]) for child in row["children"]], row["identity"], row["inherited"])
            for child, ancestry in zip(row["children"], children, strict=True):
                retained = windows.get(child["window_id"])
                if retained is not None and retained != (child, ancestry):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Inherited extraction child changed")
                windows[child["window_id"]] = (child, ancestry)
        selected = windows.get(window["window_id"])
        if selected is None or selected[0] != window or selected[1]["depth"] != observation["depth"]:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native extraction reset or changed split ancestry")
        return selected[1], scope

    def critic(self, observation, observations):
        purpose, payload = observation["purpose"], observation["context"]
        identifiers = [row["record_id"] for row in payload["spans"]]
        source_file = self.source_file(identifiers)
        if any(row != semantics.split.source_basis(self.spans[row["record_id"]]) for row in payload["spans"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic context changed immutable source")
        context = context_scope(observation["request"])
        extractions = [row for row in observations if row["purpose"] == "concept_extraction"
                       and self.source_file(row["window"]["span_ids"]) == source_file]
        if not extractions:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic lacks its native extraction context")
        latest = extractions[-1]["window"]
        root_window = latest["window_id"].split(".split-", 1)[0]
        roots = [row["window"] for row in extractions if row["window"]["window_id"] == root_window]
        roots += [row["window"] for row in self.size_rules
                  if row["window"]["window_id"] == root_window
                  and self.source_file(row["window"]["span_ids"]) == source_file]
        if not roots or any(root != roots[-1] for root in roots):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic lost its original extraction ancestor")
        if not set(identifiers) <= set(roots[-1]["span_ids"]):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic escaped its original extraction source")
        if context is not None and (context["source_file"] != source_file
                or context["window"].split(".split-", 1)[0] != root_window):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic crossed its latest original extraction window")
        scope = {"source_file": source_file, "window": root_window, "purpose": purpose}
        owned = observation["owned"]
        expected = identifiers if purpose == "coverage_verification" else [row["concept_id"] for row in payload["concepts"]]
        if owned != expected:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic changed its native judgment membership")
        chain = []
        for observed in observations:
            if observed["purpose"] != purpose:
                continue
            depth = observed["depth"]
            if type(depth) is not int or not 0 <= depth <= len(chain):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Observed critic ancestry skipped a parent")
            chain = [*chain[:depth], observed]
        if not chain or chain[-1] != observation:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic lacks its exact observed parent request chain")
        rules = {digest(row["request"]): row for row in self.rules if row["recipe"]["kind"] == purpose}
        applicable = []
        for parent, child in pairwise(chain):
            rule = rules.get(digest(parent["request"]))
            if (rule is None or not semantics.matches(parent, rule)
                    or child["owned"] not in [item["owned"] for item in rule["recipe"]["children"]]):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic child lacks its exact applied parent request")
            applicable.append(rule)
        root_owned = chain[0]["owned"]
        root = self.root(scope, root_owned)
        lineages = {(0, tuple(sorted(root_owned))): root}
        for row in sorted(applicable, key=lambda item: item["recipe"]["depth"]):
            recipe = row["recipe"]
            key = (recipe["depth"], tuple(sorted(recipe["owned"])))
            parent = lineages.get(key)
            if parent is None:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Critic split lost inherited parent membership")
            children = self.split(parent["identity"],
                [self.owned(scope, child["owned"]) for child in recipe["children"]], row["identity"],
                row in getattr(self, "semantic_options", {}).get("inherited", self.rules))
            for child, lineage in zip(recipe["children"], children, strict=True):
                lineages[(recipe["depth"] + 1, tuple(sorted(child["owned"])))] = lineage
        selected = lineages.get((observation["depth"], tuple(sorted(owned))))
        if selected is None:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Native critic reset or changed split ancestry")
        return selected, scope

    def resolve(self, logical, request):
        self.owner.check()
        active = semantics.ACTIVE.get()
        if active is None or active["rules"] != self.rules:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Dispatch requires actual native semantic observations")
        observations = active["observations"]["observations"]
        if not observations or observations[-1]["request"] != request:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Dispatch differs from the latest native request")
        self.import_history(observations)
        observation = deepcopy(observations[-1])
        lineage, scope = self.extraction(observation) if request["purpose"] == "concept_extraction" else self.critic(
            observation, observations)
        record = self.journal.read()
        validate_lineage(lineage, ancestors=record["lineages"])
        if lineage["identity"] in record["splits"]:
            raise RecoveryStop("BLOCKED_DECOMPOSITION", "Retired native parent cannot execute")
        value = {"plan_identity": self.plan["plan_identity"], "logical": logical,
                 "request_hash": digest(request), "observation_hash": digest(source_observation(observation)),
                 "lineage": lineage["identity"], "source_scope": scope}
        expected = {**value, "identity": digest(value)}
        path = regular_path(self.output / f"request-lineages/{logical:04d}.json")
        if path.exists():
            if read_json(path) != expected:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Retained native request ownership changed")
        else:
            for descriptor in (self.output / "reconnect-attempts").glob("*.json"):
                if read_json(descriptor)["logical"] == logical:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Allocated request lost its native ownership")
            self.owner.check()
            path.parent.mkdir(parents=True, exist_ok=True)
            persist(path, expected)
        return lineage["identity"]

    def import_history(self, observations):
        transition = self.plan[runtime.FIELD].get("transition", {})
        history = transition.get("recovery_history")
        if history is None:
            return
        lineages = {}
        for row in history["sequences"]:
            matches = [index for index, observed in enumerate(observations) if observed["request"] == row["request"]]
            if not matches:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Historical recovery lost its exact native observation")
            selected = None
            for index in matches:
                observed = observations[index]
                if source_observation(observed) != source_observation(observations[matches[0]]):
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Repeated historical request changed native context")
                lineage, _scope = self.extraction(observed) if observed["purpose"] == "concept_extraction" else (
                    self.critic(observed, observations[:index + 1]))
                if selected is not None and lineage["identity"] != selected:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Repeated historical request changed native lineage")
                selected = lineage["identity"]
            lineages[row["identity"]] = selected
        self.journal.inherit_history(history, lineages, transition["diagnostic_handoff"])

    def diagnostic_handoff(self, incident):
        handoff = self.plan[runtime.FIELD].get("transition", {}).get("diagnostic_handoff")
        if handoff is not None and digest(incident) == handoff["incident_hash"]:
            return handoff["sequence_identity"]
        return None
