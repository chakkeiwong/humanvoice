"""Derive canonical ownership roles from already admitted configuration.

This component does not admit configurations or authorize execution. Public
entrypoints must independently verify admission and supply native job/history
readers. Caller-selected paths are never accepted through the FD capsule.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from humanvoice.artifacts import digest, read_json
from tools import durable_program_supervisor as durable
from tools.inventory_recovery_v3.descriptors import identity
from tools.inventory_recovery_v3.installed_authority import canonical_path
from tools.inventory_recovery_v3.reservations import regular_path


@dataclass(frozen=True)
class Role:
    name: str
    path: Path


@dataclass(frozen=True)
class Membership:
    configuration: str
    role: str
    roles: tuple
    job_identity: str | None = None
    stage_identity: str | None = None

    def record(self):
        return {"configuration": self.configuration, "role": self.role,
                "roles": [{"role": item.name, "path": str(item.path)} for item in self.roles],
                "job_identity": self.job_identity, "stage_identity": self.stage_identity}


def distinct(roles):
    names, paths, inodes = set(), set(), set()
    for item in roles:
        path = regular_path(canonical_path(item.path))
        if item.name in names or path in paths:
            raise ValueError("Ownership roles cannot repeat a name or resource")
        names.add(item.name)
        paths.add(path)
        if path.exists():
            inode = identity(path.stat())
            if inode in inodes:
                raise ValueError("Different ownership roles cannot share an inode")
            inodes.add(inode)
    return tuple(roles)


def expected(configuration, role, *, job=None, checked_request=None, history=None, stage=None):
    if role not in {"monitor", "worker", "campaign", "provider"}:
        raise ValueError("Unknown canonical ownership role")
    if role == "monitor" and (job is not None or checked_request is not None):
        raise ValueError("Monitor cannot select job ownership")
    if role != "provider" and (history is not None or stage is not None):
        raise ValueError("Only a provider adds committed stage ownership")
    scope = configuration["execution_authority"]
    supervisor = canonical_path(scope["supervisor_root"])
    campaign = canonical_path(configuration["campaign_root"])
    program = canonical_path(scope["program_base"]) / "active-session-program.lock"
    adoption = configuration["handover"]
    if adoption["replacement"] != str(supervisor) or not adoption["records"]:
        raise ValueError("Ownership requires the admitted predecessor chain")
    roles = []
    previous = None
    for index, record in enumerate(adoption["records"]):
        predecessor = record["predecessor"]
        root = canonical_path(predecessor["root"])
        if previous is not None and previous != str(root):
            raise ValueError("Ownership predecessor chain is incomplete")
        previous = str(canonical_path(record["replacement"]))
        roles.append(Role(f"predecessor:{index}:monitor", root / "monitor.lock"))
        jobs = predecessor["jobs"]
        if (not isinstance(jobs, list) or jobs != sorted(set(jobs))
                or any(not isinstance(name, str) or not re.fullmatch(r"job-[0-9]{4,12}", name) for name in jobs)):
            raise ValueError("Ownership predecessor jobs are ambiguous")
        roles.extend(Role(f"predecessor:{index}:{name}", root / "jobs" / name / "worker.lock") for name in jobs)
    if previous != str(supervisor):
        raise ValueError("Ownership chain does not reach this supervisor")
    shared = [canonical_path(path) for path in adoption["installed"]["shared_locks"]]
    if shared.count(program) != 1 or len(set(shared)) != len(shared):
        raise ValueError("Installed ownership must bind the shared program exactly once")
    historical = sorted(path for path in shared if path != program)
    if any(path.name not in {"execution.lock", "executor.lock"} for path in historical):
        raise ValueError("Unknown historical stage lock")
    for path in historical:
        partner = path.with_name("executor.lock" if path.name == "execution.lock" else "execution.lock")
        if partner not in historical:
            raise ValueError("Historical stage ownership requires both locks")
        roles.append(Role(f"historical:{len(roles)}:{path.name}", path))
    roles.extend((Role("program", program), Role("campaign", campaign / "campaign.lock"),
                  Role("monitor", supervisor / "monitor.lock")))
    job_identity = stage_identity = None
    if role != "monitor":
        if not isinstance(job, str) or not re.fullmatch(r"job-[0-9]{4,12}", job) or not callable(checked_request):
            raise ValueError("Child ownership requires an independently checked job")
        request = checked_request(supervisor, job)
        action = {"RUNNING": "run", "ADMITTING": "admission"}.get(request.get("phase"))
        directory = supervisor / "jobs" / job
        if (not action or request.get("job_id") != job
                or request.get("config_identity") != durable.fingerprint(configuration)
                or request.get("command") != configuration[action]
                or request.get("cwd") != configuration["cwd"]
                or request != read_json(regular_path(directory / "request.json"))
                or any(regular_path(directory / name).exists() for name in ("result.json", "recovery.json"))):
            raise ValueError("Ownership job is changed, retired or outside its admitted command")
        job_identity = durable.fingerprint(request)
        roles.append(Role("job", directory / "worker.lock"))
    if role == "provider":
        if history is None or canonical_path(history.root) != campaign or not isinstance(stage, dict):
            raise ValueError("Provider ownership requires native committed history")
        state = history.status()
        cursor = state.get("cursor", {})
        if (state.get("status") != "READY" or set(stage) != {"output", "plan"}
                or type(cursor.get("generation")) is not int or cursor["generation"] < 0):
            raise ValueError("Provider ownership requires a fully committed stage")
        output = canonical_path(stage["output"])
        plan = stage["plan"]
        if (output != campaign / f"generation-{cursor['generation']:02d}"
                or cursor.get("output") != str(output)
                or cursor.get("plan_identity") != plan.get("plan_identity")
                or read_json(regular_path(output / "plan.json")) != plan
                or regular_path(output / "allocation-seal.json").exists()):
            raise ValueError("Provider stage differs from its committed native plan")
        stage_identity = digest(cursor)
        roles.extend(Role(name, output / (name + ".lock")) for name in ("execution", "executor"))
    return Membership(digest(configuration), role, distinct(roles), job_identity, stage_identity)
