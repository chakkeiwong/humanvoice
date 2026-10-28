"""Retain transfer evidence once; verify it without rebuilding live authority.

This record is not admission. A release must bind it through the independently
derived configuration before RuntimeLeaf may use it for execution.
"""

from copy import deepcopy
from pathlib import Path

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3 import handover, installed_authority
from tools.inventory_recovery_v3.installed_authority import canonical_path
from tools.inventory_recovery_v3.reservations import regular_path

VERSION = "inventory-immutable-runtime-closure-v1"


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def identified(value):
    value = {key: item for key, item in value.items() if key != "identity"}
    return {**value, "identity": digest(value)}


def tree(root, slots):
    """Freeze membership and bytes; only named lock slots may appear/disappear."""
    files, directories = {}, {}

    def visit(directory):
        directory = canonical_path(directory)
        require(directory.is_dir(), "Retained evidence directory disappeared")
        members = []
        for path in sorted(directory.iterdir()):
            canonical_path(path)
            if str(path) in slots:
                regular_path(path)
                continue
            if path.is_dir():
                members.append([path.name, "directory"])
                visit(path)
            else:
                members.append([path.name, "file"])
                files[str(path)] = digest(regular_path(path).read_bytes())
        directories[str(directory)] = members

    visit(root)
    return {"files": files, "directories": directories}


def qualification(root):
    """Bind the complete child/plan inventory, including children lacking plans."""
    root = canonical_path(root)
    if not root.exists():
        return {"root": str(root), "members": None, "plans": {}}
    require(root.is_dir(), "Qualification root is not a directory")
    members, plans = [], {}
    for child in sorted(root.iterdir()):
        canonical_path(child)
        require(child.is_dir(), "Qualification membership must contain directories")
        members.append(child.name)
        plan = regular_path(child / "plan.json")
        if plan.exists():
            plans[str(plan)] = digest(plan.read_bytes())
    return {"root": str(root), "members": members, "plans": plans}


def source_members(root):
    root = canonical_path(root)
    return sorted(str(regular_path(canonical_path(path))) for path in root.glob("*.py"))


def capture(adoption):
    """Transfer-time only: independently validate the entire adoption first."""
    from tools import review_inventory_recovery_v3 as review
    from tools.inventory_recovery_v2 import campaign, program

    retained = deepcopy(adoption)
    handover.validate(retained)
    installed = retained["installed"]
    projection = installed_authority.immutable_projection(installed)
    historical = qualification(canonical_path(campaign.ROOT) / "qualification")
    program_lock = canonical_path(program.BASE) / "active-session-program.lock"
    output = canonical_path(installed["cursor"]["output"])
    stage_roots = [output, *(Path(path).parent for path in historical["plans"])]
    shared = sorted([str(program_lock), *(str(root / name) for root in stage_roots
                    for name in ("execution.lock", "executor.lock"))])
    require(len(set(shared)) == len(shared) and shared == installed["shared_locks"],
            "Historical plan membership differs from installed exclusions")
    slots = sorted([*shared, *(str(path) for record in retained["records"]
                              for path in handover.exclusions(record))])
    require(len(set(slots)) == len(slots), "Runtime closure has repeated lock slots")
    predecessors = {}
    for record in retained["records"]:
        prior = record["predecessor"]
        root = canonical_path(prior["root"])
        observed = tree(root, slots)
        require(all(observed["files"].get(str(root / name)) == checksum
                    for name, checksum in prior["hashes"].items()),
                "Predecessor bytes changed after adoption")
        predecessors[str(root)] = observed
    sources = {}
    for name, checksum in installed["sources"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts,
                "Runtime source names must be repository-relative")
        sources[str(canonical_path(review.ROOT / name))] = checksum
    plans = {str(root / "plan.json"): digest(regular_path(root / "plan.json").read_bytes())
             for root in stage_roots}
    value = identified({"version": VERSION, "adoption_identity": retained["identity"],
        "installation": projection, "predecessors": predecessors,
        "qualification": historical, "stage_plans": plans, "sources": sources,
        "source_membership": {str(canonical_path(review.ROOT / "tools/inventory_recovery_v3")):
                              source_members(review.ROOT / "tools/inventory_recovery_v3")},
        "lock_slots": slots, "live_execution_enabled": False})
    # A second independent observation rejects mutations during capture. Runtime
    # verify below deliberately does not enter this transfer-time path.
    handover.validate(retained)
    verify(value, adoption=retained)
    return value


def verify(value, *, adoption):
    """Read retained evidence only; no proposal, capture, locks or mutable floors."""
    require(isinstance(value, dict) and set(value) == {"version", "adoption_identity",
        "installation", "predecessors", "qualification", "stage_plans", "sources",
        "source_membership", "lock_slots", "live_execution_enabled", "identity"}
        and value.get("version") == VERSION and value.get("live_execution_enabled") is False
        and digest(value) == digest(identified(value))
        and digest(adoption) == digest(identified(adoption))
        and value["adoption_identity"] == adoption["identity"]
        and value["installation"] == installed_authority.immutable_projection(adoption["installed"]),
        "Runtime closure lost its admitted transfer binding")
    for path in value["lock_slots"]:
        regular_path(canonical_path(path))
    for root, expected in value["predecessors"].items():
        require(tree(root, value["lock_slots"]) == expected,
                "Immutable predecessor bytes or directory membership changed")
    require(qualification(value["qualification"]["root"]) == value["qualification"],
            "Historical qualification plan membership changed")
    for root, members in value["source_membership"].items():
        require(source_members(root) == members, "Runtime source membership changed")
    for evidence in (value["installation"]["evidence"], value["stage_plans"], value["sources"]):
        for path, checksum in evidence.items():
            require(digest(regular_path(canonical_path(path)).read_bytes()) == checksum,
                    "Immutable runtime evidence changed: " + path)
    return True
