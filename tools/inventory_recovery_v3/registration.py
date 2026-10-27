"""Register source scopes and charged split origins atomically."""

from copy import deepcopy

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.lineage import (
    root_lineage,
    split_lineage,
    validate_lineage,
)


def scoped_root(journal, *, scope, owned):
    if (not isinstance(scope, dict) or set(scope) != {"source_file", "window", "purpose"}
            or any(not isinstance(value, str) or not value for value in scope.values())
            or ".split-" in scope["window"]):
        raise RecoveryStop("BLOCKED_ACCOUNTING", "Root registration requires an exact original source scope")
    lineage = root_lineage(journal.binding["document"], scope["purpose"], owned, scope=scope)
    key = digest(scope)
    with journal.locked():
        record = journal.read()
        expected = {}
        for selected in record["lineages"].values():
            validate_lineage(selected, ancestors=record["lineages"])
            if selected["parent"] is None and "scope" in selected:
                identity = digest(selected["scope"])
                if identity in expected:
                    raise RecoveryStop("BLOCKED_ACCOUNTING", "Original scope has multiple root lineages")
                expected[identity] = {"scope": selected["scope"], "lineage": selected["identity"]}
        if record.get("source_scopes", {}) != expected:
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Committed source scope registry disappeared or changed")
        value = {"scope": deepcopy(scope), "lineage": lineage["identity"]}
        prior = record.get("source_scopes", {}).get(key)
        if prior is not None:
            if prior != value or record["lineages"].get(lineage["identity"]) != lineage:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Original scope changed its root membership")
            return deepcopy(lineage)
        if lineage["identity"] in record["lineages"]:
            if record["lineages"][lineage["identity"]] != lineage:
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Source scope changed registered ownership")
            if any(row["lineage"] == lineage["identity"] for row in record.get("source_scopes", {}).values()):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Two original scopes cannot share a lineage")
        for selected in record["lineages"].values():
            validate_lineage(selected, ancestors=record["lineages"])
            if (selected["parent"] is None and selected["identity"] != lineage["identity"]
                    and selected["purpose"] == lineage["purpose"] and set(selected["owned"]) & set(lineage["owned"])):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Independent request roots overlap ownership")
        record.setdefault("source_scopes", {})[key] = value
        record["lineages"][lineage["identity"]] = lineage
        journal.save(record)
        return deepcopy(lineage)


def register_split(journal, identity, children, *, evidence, inherited):
    if type(inherited) is not bool or not isinstance(evidence, str) or not evidence:
        raise ValueError("Split registration requires its verified origin and evidence identity")
    with journal.locked():
        record = journal.read()
        parent = record["lineages"][identity]
        descendants = split_lineage(parent, children, ancestors=record["lineages"],
                                    maximum_depth=journal.policy["maximum_split_depth"])
        value = {"parent": identity, "root": parent["root"],
                 "children": [child["identity"] for child in descendants],
                 "extra_calls": 0 if inherited else len(descendants) - 1,
                 "inherited_evidence" if inherited else "prospective_evidence": evidence}
        previous = record["splits"].get(identity)
        if previous is not None:
            if previous != value or any(record["lineages"].get(child["identity"]) != child for child in descendants):
                raise RecoveryStop("BLOCKED_ACCOUNTING", "Registered split changed ancestry, origin or charge")
            return deepcopy(descendants)
        if any(slot["state"] == "dispatching" for row in record["sequences"].values()
               for slot in row["slots"].values()):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Cannot register split with unresolved dispatch")
        if any(row.get("inherited_evidence", row.get("prospective_evidence")) == evidence
               for row in record["splits"].values()):
            raise RecoveryStop("BLOCKED_ACCOUNTING", "Split evidence was already consumed by another parent")
        count = sum(len(row["children"]) for row in record["splits"].values() if row["root"] == parent["root"])
        if count + len(descendants) > journal.policy["maximum_lineage_children"]:
            raise RecoveryStop("BLOCKED_DECOMPOSITION", "Original root child allowance exhausted")
        expansion = sum(row["extra_calls"] for row in record["splits"].values())
        if expansion + value["extra_calls"] > journal.policy["split_allowance"]:
            raise RecoveryStop("BLOCKED_BUDGET", "Document split expansion exceeds reserved capacity")
        record["splits"][identity] = value
        record["lineages"].update({child["identity"]: child for child in descendants})
        journal.save(record)
        return deepcopy(descendants)
