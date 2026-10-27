"""Bind split ancestry to stable source ownership rather than local slot numbers."""

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3.policy import integer


def root_lineage(source_hash, purpose, owned, *, scope=None):
    if (not isinstance(source_hash, str) or not source_hash
            or purpose not in {"concept_extraction", "coverage_verification", "reconstruction_verification"}
            or not isinstance(owned, list) or not owned
            or any(not isinstance(item, str) or not item for item in owned)
            or len(owned) != len(set(owned))):
        raise ValueError("Lineage requires frozen source, purpose and unique owned membership")
    value = {"version": "inventory-request-lineage-v1", "source_hash": source_hash,
             "purpose": purpose, "owned": sorted(owned), "depth": 0, "parent": None}
    if scope is not None:
        if (not isinstance(scope, dict) or set(scope) != {"source_file", "window", "purpose"}
                or any(not isinstance(item, str) or not item for item in scope.values())
                or scope["purpose"] != purpose or ".split-" in scope["window"]):
            raise ValueError("Lineage requires an exact original source scope")
        value.update(version="inventory-scoped-lineage-v2", scope=dict(scope))
    identity = digest(value)
    return {**value, "identity": identity, "root": identity}


def validate_lineage(record, *, ancestors=None):
    selected, seen = record, set()
    while True:
        fields = {"version", "source_hash", "purpose", "owned", "depth", "parent", "root", "identity"}
        if isinstance(selected, dict) and selected.get("version") == "inventory-scoped-lineage-v2":
            fields.add("scope")
        if (not isinstance(selected, dict)
                or set(selected) != fields
                or selected.get("identity") in seen):
            raise ValueError("Lineage shape or ancestry cycle changed")
        seen.add(selected["identity"])
        integer(selected["depth"], "depth")
        root = root_lineage(selected["source_hash"], selected["purpose"], selected["owned"], scope=selected.get("scope"))
        if selected["parent"] is None:
            if selected != root:
                raise ValueError("Root lineage changed")
            return record
        value = {key: item for key, item in selected.items() if key != "identity"}
        if (selected["identity"] != digest(value) or selected["version"] != root["version"]
                or selected["owned"] != sorted(selected["owned"])
                or not isinstance(ancestors, dict) or selected["parent"] not in ancestors):
            raise ValueError("Child lineage requires its intact registered ancestry")
        parent = ancestors[selected["parent"]]
        if (parent.get("identity") != selected["parent"]
                or any(parent.get(name) != selected[name] for name in ("root", "purpose", "source_hash"))
                or parent.get("scope") != selected.get("scope")
                or type(parent.get("depth")) is not int or selected["depth"] != parent["depth"] + 1
                or not set(selected["owned"]) < set(parent.get("owned", []))):
            raise ValueError("Child lineage differs from its registered parent")
        selected = parent


def split_lineage(parent, children, *, maximum_depth=3, ancestors=None):
    validate_lineage(parent, ancestors=ancestors)
    integer(maximum_depth, "maximum_depth", 1)
    if parent["depth"] >= maximum_depth or not isinstance(children, list) or len(children) < 2:
        raise ValueError("Split depth or child count is invalid")
    if any(not isinstance(child, list) or not child for child in children):
        raise ValueError("Split children require nonempty owned membership")
    flattened = [item for child in children for item in child]
    if (any(not isinstance(item, str) for item in flattened)
            or len(flattened) != len(set(flattened)) or set(flattened) != set(parent["owned"])):
        raise ValueError("Split children must exactly partition owned membership")
    result = []
    for child in children:
        value = {"version": parent["version"], "source_hash": parent["source_hash"],
                 "purpose": parent["purpose"], "owned": sorted(child),
                 "depth": parent["depth"] + 1, "parent": parent["identity"],
                 "root": parent["root"]}
        if "scope" in parent:
            value["scope"] = dict(parent["scope"])
        result.append({**value, "identity": digest(value)})
    return result
