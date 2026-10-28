"""Read-only stop floors and explicitly supplied monotonic control authority.

The authenticated reader is a required external trust boundary, just like
release admission. It must retain every published stop across process death and
authenticate resume provenance. This module does not manufacture that authority
from a current stop file or an authorized_by string. No public factory supplies
the reader yet; production remains disabled until control publication is wired.
"""

import json
import math

from humanvoice.artifacts import digest
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools.inventory_recovery_v3.installed_authority import canonical_path
from tools.inventory_recovery_v3.reservations import regular_path

VERSION = "runtime-authenticated-stop-history-v1"
FLOOR = "runtime-initial-stop-floor-v1"


def require(condition, detail):
    if not condition:
        raise RecoveryStop("USER_STOPPED", detail)


def identified(value):
    value = {key: item for key, item in value.items() if key != "identity"}
    return {**value, "identity": digest(value)}


def read_optional(path):
    path = regular_path(path)
    return path.read_bytes().decode("utf-8") if path.exists() else None


def stop_record(content):
    require(isinstance(content, str) and bool(content), "Retained stop bytes are missing")
    stop = json.loads(content)
    require(isinstance(stop, dict) and stop.get("status") == "USER_STOPPED"
            and isinstance(stop.get("request_id"), str) and bool(stop["request_id"])
            and type(stop.get("requested_at")) in (int, float)
            and math.isfinite(stop["requested_at"]) and stop["requested_at"] > 0,
            "Retained stop lacks its exact request identity and time")
    return stop


def capture(bindings):
    rows = []
    for binding in bindings:
        root = canonical_path(binding["root"])
        content = read_optional(root / "user-stop.json")
        if content is not None:
            stop_record(content)
        rows.append({**binding, "stop_bytes": content})
    require(rows and len({row["root"] for row in rows}) == len(rows),
            "Initial stop floor requires every canonical root exactly once")
    return identified({"version": FLOOR, "roots": rows})


def verify(configuration, evidence):
    """Validate an authenticated reader's complete latest histories, without writes."""
    floor = configuration["stop_floor"]
    bindings = configuration["stop_bindings"]
    require(isinstance(floor, dict) and set(floor) == {"version", "roots", "identity"}
            and floor["version"] == FLOOR and digest(floor) == digest(identified(floor))
            and isinstance(floor["roots"], list)
            and all(isinstance(row, dict) and set(row) == {"root", "contract", "stop_bytes"}
                    for row in floor["roots"])
            and [{key: row[key] for key in ("root", "contract")} for row in floor["roots"]] == bindings,
            "Runtime stop floor lost its canonical root binding")
    require(isinstance(evidence, dict) and set(evidence) == {"version", "configuration",
            "histories", "resumes", "identity"} and evidence["version"] == VERSION
            and digest(evidence) == digest(identified(evidence))
            and evidence["configuration"] == digest(configuration)
            and isinstance(evidence["histories"], dict) and isinstance(evidence["resumes"], dict)
            and set(evidence["histories"]) == set(evidence["resumes"])
                == {row["root"] for row in bindings},
            "Runtime lacks authenticated latest stop-history evidence")
    for origin in floor["roots"]:
        root = canonical_path(origin["root"])
        rows = evidence["histories"][str(root)]
        require(isinstance(rows, list), "Retained stop history is missing")
        previous, seen = None, set()
        latest = None
        for sequence, row in enumerate(rows, 1):
            require(isinstance(row, dict) and set(row) == {"sequence", "previous",
                "stop_bytes", "identity"} and digest(row) == digest(identified(row))
                and type(row["sequence"]) is int and row["sequence"] == sequence
                and row["previous"] == (previous["identity"] if previous else None),
                "Retained stop history lost its complete monotonic chain")
            stop = stop_record(row["stop_bytes"])
            require(stop["request_id"] not in seen
                    and (latest is None or stop["requested_at"] > latest["requested_at"]),
                    "Retained stop history rolled back or reused a request")
            seen.add(stop["request_id"])
            previous, latest = row, stop
        if origin["stop_bytes"] is not None:
            require(rows and rows[0]["stop_bytes"] == origin["stop_bytes"],
                    "Retained stop history lost the stop present at transfer")
        content = read_optional(root / "user-stop.json")
        require(content == (previous["stop_bytes"] if previous else None),
                "Current stop was deleted, rolled back or not durably observed")
        resume = evidence["resumes"][str(root)]
        resume_bytes = read_optional(root / "resume-authorization.json")
        require(resume == resume_bytes, "Current resume differs from authenticated control authority")
        if previous is None:
            require(resume is None, "Resume without a retained stop cannot authorize execution")
            continue
        require(isinstance(resume, str), "Latest retained stop requires explicit resume authorization")
        authorized = json.loads(resume)
        require(isinstance(authorized, dict) and authorized.get("action") == "explicit-resume"
                and authorized.get("authorized_by") == "user"
                and digest(authorized.get("contract")) == digest(origin["contract"])
                and authorized.get("stop_sha256") == digest(content.encode()),
                "Resume authorization does not bind the latest retained stop")
    return True
