"""The precondition for rewriting (WP-V2-1, gate V2-G1).

V2-G1 requires that a fixture cannot reach rewriting with an uncovered source
span, an unresolved concept or scaffolding classification, a dangling
dependency, a missing explanation obligation, or an invalid protected-object
link. The schemas and link validators in `schemas.py` already reject each of
those individually. What was missing is the thing that asks the question at the
one moment it matters: before a rewrite call is made.

This module is that gate. It is deliberately not a validator among validators.
It returns a single verdict — `ready` or not — with every reason stated and
located, and the caller has nothing to interpret. A rewrite command calls
`assert_ready_to_rewrite` and either proceeds or stops.

Three design choices are load-bearing:

**Refusal is the default.** `Readiness.ready` is true only when every check
ran and every check passed. A check that could not run (a record type absent
from the bundle, a file whose bytes were not supplied) produces a blocker, not
a pass. An incomplete inventory must not look like a clean one, which is
exactly the failure mode that let the ZLB run appear healthy.

**Byte-exact coverage, not a maximum offset.** `_snapshot_coverage_errors` in
`schemas.py` compares `max(byte_end)` to the declared file size, so spans
[0,5] and [10,20] over a 20-byte file pass while five bytes go unread. Those
five bytes could hold a qualification. This module walks the sorted spans and
reports every gap and every overlap by offset.

**Unresolved is a blocker, never a warning.** A span the partitioner could not
classify, a concept a reviewer marked ambiguous, a scaffolding disposition
nobody adjudicated: each is a question for a person. Rewriting past one means
guessing at meaning, and a wrong guess is the failure this product exists to
prevent.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from humanvoice.partition import UNRESOLVED

# Review states that mean a human has not settled the question.
UNSETTLED_CONCEPT_REVIEW = ("proposed", "ambiguous")
UNSETTLED_SCAFFOLDING = ("unresolved",)

# Obligation states that cannot support a rewrite call: the obligation exists
# and nothing has assessed it. `unassessed` is legal before rewriting and is
# checked separately from `unmet`, which means assessment found it failing.
BLOCKING_OBLIGATION_STATUS = ("unresolved",)


@dataclass
class Blocker:
    """One located reason rewriting may not start.

    `check` names the V2-G1 condition so a caller can report which of the five
    failed. `locator` is whatever identifies the thing at fault — a span ID, a
    byte range, a concept ID — so a person can go look at it.
    """

    check: str
    locator: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.locator}: {self.detail}"


@dataclass
class Readiness:
    """Whether rewriting may start, and if not, every reason it may not."""

    blockers: list[Blocker] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """True only when every required check ran and none produced a blocker."""
        return not self.blockers and set(REQUIRED_CHECKS) <= set(self.checks_run)

    def by_check(self) -> dict[str, list[Blocker]]:
        grouped: dict[str, list[Blocker]] = defaultdict(list)
        for blocker in self.blockers:
            grouped[blocker.check].append(blocker)
        return dict(grouped)

    def summary(self) -> str:
        if self.ready:
            return f"ready to rewrite: {len(self.checks_run)} checks passed"
        missing = sorted(set(REQUIRED_CHECKS) - set(self.checks_run))
        parts = [f"{len(self.blockers)} blocker(s)"]
        if missing:
            parts.append(f"{len(missing)} check(s) could not run: {', '.join(missing)}")
        return "not ready to rewrite: " + "; ".join(parts)

    def report(self) -> str:
        lines = [self.summary()]
        for check, blockers in sorted(self.by_check().items()):
            lines.append(f"  {check}: {len(blockers)}")
            for blocker in blockers[:10]:
                lines.append(f"    {blocker.locator}: {blocker.detail}")
            if len(blockers) > 10:
                lines.append(f"    ... and {len(blockers) - 10} more")
        return "\n".join(lines)


# The five V2-G1 conditions. Every one must run for a ready verdict; a check
# that cannot run is not a check that passed.
REQUIRED_CHECKS = (
    "span_coverage",
    "classification_resolved",
    "dependency_integrity",
    "obligation_presence",
    "protected_object_links",
)


class NotReadyToRewrite(RuntimeError):
    """Raised when a rewrite is attempted against an incomplete baseline."""

    def __init__(self, readiness: Readiness) -> None:
        super().__init__(readiness.report())
        self.readiness = readiness


def _group(records: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        record_type = record.get("record_type")
        if isinstance(record_type, str):
            grouped[record_type].append(record)
    return dict(grouped)


def _index(
    records: Sequence[Mapping[str, Any]], key: str
) -> dict[str, Mapping[str, Any]]:
    return {
        row[key]: row for row in records if isinstance(row.get(key), str)
    }


def check_span_coverage(
    spans: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
) -> list[Blocker]:
    """Every declared source byte belongs to exactly one span.

    Walks each file's spans in offset order and reports gaps and overlaps by
    byte range rather than comparing a maximum offset to a file size. A gap is
    text nobody classified; an overlap means two spans claim the same bytes and
    a rewrite of both would duplicate or contradict them.
    """
    blockers: list[Blocker] = []
    if not snapshots:
        return [
            Blocker(
                "span_coverage",
                "bundle",
                "no SourceSnapshot: nothing declares which bytes must be covered",
            )
        ]

    by_file: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for span in spans:
        path = span.get("source_file")
        if isinstance(path, str):
            by_file[path].append(span)

    for snapshot in snapshots:
        declared: dict[str, Any] = {}
        for row in snapshot.get("source_files", []):
            if isinstance(row, Mapping) and isinstance(row.get("path"), str):
                declared[row["path"]] = row.get("byte_size")

        for path, size in sorted(declared.items()):
            file_spans = by_file.get(path)
            if not file_spans:
                blockers.append(
                    Blocker(
                        "span_coverage",
                        path,
                        "declared in the snapshot with no spans at all",
                    )
                )
                continue
            blockers.extend(_file_coverage_blockers(path, file_spans, size))

        for path in sorted(set(by_file) - set(declared)):
            blockers.append(
                Blocker(
                    "span_coverage",
                    path,
                    "spans reference a file the snapshot does not declare",
                )
            )
    return blockers


def _file_coverage_blockers(
    path: str, spans: Sequence[Mapping[str, Any]], declared_size: Any
) -> list[Blocker]:
    """Report gaps, overlaps, and a short or long partition for one file."""
    blockers: list[Blocker] = []
    ordered = sorted(
        (
            span
            for span in spans
            if isinstance(span.get("byte_start"), int)
            and isinstance(span.get("byte_end"), int)
        ),
        key=lambda span: (span["byte_start"], span["byte_end"]),
    )
    if len(ordered) != len(spans):
        blockers.append(
            Blocker("span_coverage", path, "a span has a non-integer byte offset")
        )

    cursor = 0
    for span in ordered:
        start, end = span["byte_start"], span["byte_end"]
        span_id = span.get("record_id", "unidentified span")
        if start > cursor:
            blockers.append(
                Blocker(
                    "span_coverage",
                    f"{path}[{cursor}:{start}]",
                    f"{start - cursor} unclassified byte(s) before span {span_id}",
                )
            )
        elif start < cursor:
            blockers.append(
                Blocker(
                    "span_coverage",
                    f"{path}[{start}:{min(cursor, end)}]",
                    f"span {span_id} overlaps the preceding span",
                )
            )
        cursor = max(cursor, end)

    if isinstance(declared_size, int):
        if cursor < declared_size:
            blockers.append(
                Blocker(
                    "span_coverage",
                    f"{path}[{cursor}:{declared_size}]",
                    f"{declared_size - cursor} trailing byte(s) never classified",
                )
            )
        elif cursor > declared_size:
            blockers.append(
                Blocker(
                    "span_coverage",
                    f"{path}[{declared_size}:{cursor}]",
                    "spans extend past the declared end of the file",
                )
            )
    else:
        blockers.append(
            Blocker(
                "span_coverage",
                path,
                "snapshot declares no byte_size, so coverage cannot be verified",
            )
        )
    return blockers


def check_classification_resolved(
    spans: Sequence[Mapping[str, Any]],
    concepts: Sequence[Mapping[str, Any]],
    scaffolding: Sequence[Mapping[str, Any]],
) -> list[Blocker]:
    """No span, concept, or scaffolding decision may still be open.

    The partitioner deliberately marks every reader-facing span `unresolved`
    because it classifies form and cannot judge meaning. That is the correct
    starting state and an impossible rewriting state: something has to decide
    whether each span carries a concept before a call is made about it.
    """
    blockers: list[Blocker] = []

    for span in spans:
        disposition = span.get("coverage_disposition")
        span_id = span.get("record_id", "unidentified span")
        locator = "{}[{}:{}]".format(
            span.get("source_file", "?"),
            span.get("byte_start", "?"),
            span.get("byte_end", "?"),
        )
        if disposition == UNRESOLVED:
            blockers.append(
                Blocker(
                    "classification_resolved",
                    locator,
                    f"span {span_id} is still unresolved; no one has decided "
                    "whether it carries a concept",
                )
            )
        elif disposition == "concept_bearing" and not span.get("concept_ids"):
            blockers.append(
                Blocker(
                    "classification_resolved",
                    locator,
                    f"span {span_id} is marked concept_bearing but names no concept",
                )
            )
        elif disposition == "non_substantive_scaffolding" and not span.get(
            "scaffolding_disposition_ids"
        ):
            blockers.append(
                Blocker(
                    "classification_resolved",
                    locator,
                    f"span {span_id} is called scaffolding with no accountable "
                    "disposition record",
                )
            )

    for concept in concepts:
        status = concept.get("review_status")
        concept_id = concept.get("concept_id", concept.get("record_id", "?"))
        if status in UNSETTLED_CONCEPT_REVIEW:
            blockers.append(
                Blocker(
                    "classification_resolved",
                    concept_id,
                    f"concept review_status is {status!r}; a reviewer has not "
                    "accepted it",
                )
            )
        elif status == "rejected":
            # A rejected concept must not remain linked from a rewrite unit.
            # That is checked in dependency/obligation integrity; here it only
            # matters that it is not silently treated as accepted.
            continue

    for disposition in scaffolding:
        decision = disposition.get("disposition")
        disposition_id = disposition.get("disposition_id", "?")
        if decision in UNSETTLED_SCAFFOLDING:
            blockers.append(
                Blocker(
                    "classification_resolved",
                    disposition_id,
                    "scaffolding disposition is unresolved; removal or retention "
                    "has not been decided",
                )
            )
        elif decision in ("move_backstage", "remove_nonconcept") and not disposition.get(
            "embedded_concepts_extracted", True
        ):
            blockers.append(
                Blocker(
                    "classification_resolved",
                    disposition_id,
                    f"scaffolding marked {decision} before its embedded domain "
                    "content was extracted",
                )
            )
    return blockers


def check_dependency_integrity(
    dependencies: Sequence[Mapping[str, Any]],
    concepts: Sequence[Mapping[str, Any]],
) -> list[Blocker]:
    """Dependency endpoints resolve, and the graph has no cycle.

    A dangling endpoint means a prerequisite the plan believes in and the
    baseline does not contain. A cycle means no teaching order exists, so
    scheduling prerequisites before dependents is impossible and rewriting
    would produce use-before-explain somewhere by construction.
    """
    blockers: list[Blocker] = []
    by_id = _index(concepts, "concept_id")

    edges: dict[str, set[str]] = defaultdict(set)
    for dependency in dependencies:
        dependency_id = dependency.get("dependency_id", dependency.get("record_id", "?"))
        prerequisite = dependency.get("prerequisite_concept_id")
        dependent = dependency.get("dependent_concept_id")
        for field_name, concept_id in (
            ("prerequisite_concept_id", prerequisite),
            ("dependent_concept_id", dependent),
        ):
            if not isinstance(concept_id, str):
                blockers.append(
                    Blocker(
                        "dependency_integrity",
                        dependency_id,
                        f"{field_name} is missing",
                    )
                )
            elif concept_id not in by_id:
                blockers.append(
                    Blocker(
                        "dependency_integrity",
                        dependency_id,
                        f"{field_name} names a concept absent from the baseline: "
                        f"{concept_id}",
                    )
                )
            elif by_id[concept_id].get("review_status") == "rejected":
                blockers.append(
                    Blocker(
                        "dependency_integrity",
                        dependency_id,
                        f"{field_name} names a rejected concept: {concept_id}",
                    )
                )
        if isinstance(prerequisite, str) and isinstance(dependent, str):
            if prerequisite == dependent:
                blockers.append(
                    Blocker(
                        "dependency_integrity",
                        dependency_id,
                        f"concept {prerequisite} is its own prerequisite",
                    )
                )
            edges[prerequisite].add(dependent)

    for cycle in _find_cycles(edges):
        blockers.append(
            Blocker(
                "dependency_integrity",
                " -> ".join(cycle),
                "dependency cycle: no teaching order can satisfy it",
            )
        )
    return blockers


def _find_cycles(edges: Mapping[str, set[str]]) -> list[list[str]]:
    """Return one representative cycle per strongly connected component.

    Iterative depth-first search: a manuscript can carry thousands of concepts
    and recursion depth is not worth risking on a check whose whole purpose is
    to run before anything expensive happens.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = defaultdict(int)
    cycles: list[list[str]] = []
    seen_signatures: set[frozenset[str]] = set()

    for root in sorted(edges):
        if colour[root] != WHITE:
            continue
        stack: list[tuple[str, Iterable[str]]] = [(root, iter(sorted(edges.get(root, ()))))]
        path = [root]
        colour[root] = GREY
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if colour[child] == GREY:
                    cycle = path[path.index(child):] + [child]
                    signature = frozenset(cycle)
                    if signature not in seen_signatures:
                        seen_signatures.add(signature)
                        cycles.append(cycle)
                elif colour[child] == WHITE:
                    colour[child] = GREY
                    path.append(child)
                    stack.append((child, iter(sorted(edges.get(child, ())))))
                    advanced = True
                    break
            if not advanced:
                colour[node] = BLACK
                stack.pop()
                if path:
                    path.pop()
    return cycles


def check_obligation_presence(
    obligations: Sequence[Mapping[str, Any]],
    concepts: Sequence[Mapping[str, Any]],
    units: Sequence[Mapping[str, Any]],
) -> list[Blocker]:
    """Every substantive concept carries at least one active obligation.

    This is the check that separates retention from teaching. A concept can be
    present in the output, correspond to its source span, and still be a name
    the reader cannot use. The obligation says what has to be explained about
    it, so a concept with no obligation is a concept nothing will require the
    rewrite to explain.

    Note what is *not* checked here: whether obligations are fulfilled. That is
    a post-rewrite question for preflight. Before rewriting, the requirement is
    that the obligation exists, is active, names a teaching function, and is
    assigned to a unit that will have to satisfy it.
    """
    blockers: list[Blocker] = []
    by_id = _index(obligations, "obligation_id")
    concept_ids = {
        concept["concept_id"]
        for concept in concepts
        if isinstance(concept.get("concept_id"), str)
        and concept.get("review_status") != "rejected"
    }

    obligations_by_concept: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for obligation in obligations:
        concept_id = obligation.get("concept_id")
        obligation_id = obligation.get("obligation_id", "?")
        if not isinstance(concept_id, str):
            blockers.append(
                Blocker("obligation_presence", obligation_id, "names no concept")
            )
            continue
        if concept_id not in concept_ids:
            blockers.append(
                Blocker(
                    "obligation_presence",
                    obligation_id,
                    f"names a concept absent from the baseline: {concept_id}",
                )
            )
            continue
        obligations_by_concept[concept_id].append(obligation)

        if obligation.get("active"):
            if not obligation.get("required_teaching_functions"):
                blockers.append(
                    Blocker(
                        "obligation_presence",
                        obligation_id,
                        "is active but requires no teaching function, so it "
                        "demands nothing of the rewrite",
                    )
                )
            if obligation.get("fulfillment_status") in BLOCKING_OBLIGATION_STATUS:
                blockers.append(
                    Blocker(
                        "obligation_presence",
                        obligation_id,
                        "fulfillment is unresolved and needs adjudication",
                    )
                )
        else:
            # Deactivation is legitimate, and it is the one place a concept can
            # lose its teaching requirement. It must carry a recorded reason,
            # otherwise deactivating is indistinguishable from dropping.
            deactivation = obligation.get("deactivation")
            if not isinstance(deactivation, Mapping) or not deactivation.get("reason"):
                blockers.append(
                    Blocker(
                        "obligation_presence",
                        obligation_id,
                        "is inactive with no recorded deactivation reason",
                    )
                )

    for concept_id in sorted(concept_ids):
        assigned = obligations_by_concept.get(concept_id, [])
        if not assigned:
            blockers.append(
                Blocker(
                    "obligation_presence",
                    concept_id,
                    "has no explanation obligation; nothing would require the "
                    "rewrite to teach it",
                )
            )
        elif not any(obligation.get("active") for obligation in assigned):
            blockers.append(
                Blocker(
                    "obligation_presence",
                    concept_id,
                    f"has {len(assigned)} obligation(s), all inactive; the concept "
                    "would be retained without being explained",
                )
            )

    # Every active obligation must be assigned to a unit that will meet it.
    if units:
        assigned_ids: set[str] = set()
        for unit in units:
            for obligation_id in unit.get("explanation_obligation_ids", []):
                if isinstance(obligation_id, str):
                    assigned_ids.add(obligation_id)
                    if obligation_id not in by_id:
                        blockers.append(
                            Blocker(
                                "obligation_presence",
                                unit.get("unit_id", "?"),
                                f"names an obligation absent from the baseline: "
                                f"{obligation_id}",
                            )
                        )
        for obligation in obligations:
            obligation_id = obligation.get("obligation_id")
            if (
                obligation.get("active")
                and isinstance(obligation_id, str)
                and obligation_id not in assigned_ids
            ):
                blockers.append(
                    Blocker(
                        "obligation_presence",
                        obligation_id,
                        "is active but assigned to no rewrite unit, so no call "
                        "would ever be responsible for it",
                    )
                )
    return blockers


def check_protected_object_links(
    units: Sequence[Mapping[str, Any]],
    concepts: Sequence[Mapping[str, Any]],
    manifests: Sequence[Mapping[str, Any]],
) -> list[Blocker]:
    """Protected-object references resolve to objects in the manifest.

    An equation, citation, number, or table named by a unit but absent from the
    manifest cannot be checked for exact preservation after the rewrite. The
    reference has to resolve *before* the call, because afterwards there is no
    way to distinguish "the model changed it" from "nothing was watching it".
    """
    blockers: list[Blocker] = []
    if not manifests:
        if any(unit.get("protected_object_ids") for unit in units) or any(
            concept.get("protected_object_ids") for concept in concepts
        ):
            return [
                Blocker(
                    "protected_object_links",
                    "bundle",
                    "records name protected objects with no ProtectedManifest "
                    "to resolve them against",
                )
            ]
        return blockers

    known: set[str] = set()
    for manifest in manifests:
        for obj in manifest.get("objects", []):
            if isinstance(obj, Mapping) and isinstance(obj.get("object_id"), str):
                known.add(obj["object_id"])

    for records, kind, key in (
        (units, "rewrite unit", "unit_id"),
        (concepts, "concept", "concept_id"),
    ):
        for record in records:
            locator = record.get(key, record.get("record_id", "?"))
            for object_id in record.get("protected_object_ids", []):
                if not isinstance(object_id, str) or object_id not in known:
                    blockers.append(
                        Blocker(
                            "protected_object_links",
                            str(locator),
                            f"{kind} names protected object {object_id!r}, which "
                            "is not in the manifest",
                        )
                    )
    return blockers


def assess_readiness(
    records: Iterable[Mapping[str, Any]],
    *,
    validate_schemas: bool = True,
) -> Readiness:
    """Decide whether this baseline may be rewritten.

    Schema validity is checked first and its failure is terminal: the semantic
    checks below read fields whose types the schema guarantees, and running them
    over malformed records would produce misleading blockers. A caller that has
    already validated the bundle can pass `validate_schemas=False`.
    """
    materialized = list(records)
    readiness = Readiness()

    if validate_schemas:
        from humanvoice.schemas import get_registry

        errors = get_registry().validate_bundle(materialized, raise_on_error=False)
        if errors:
            readiness.blockers.extend(
                Blocker("schema_validity", "bundle", error) for error in errors
            )
            readiness.notes.append(
                "semantic checks were not run: the bundle is not schema-valid, "
                "and their results would not be trustworthy over malformed records"
            )
            return readiness

    by_type = _group(materialized)
    spans = by_type.get("SourceSpan", [])
    concepts = by_type.get("SourceConcept", [])
    dependencies = by_type.get("ConceptDependency", [])
    obligations = by_type.get("ExplanationObligation", [])
    scaffolding = by_type.get("ScaffoldingDisposition", [])
    units = by_type.get("RewriteUnit", [])
    snapshots = by_type.get("SourceSnapshot", [])
    manifests = by_type.get("ProtectedManifest", [])

    # A baseline must be frozen before rewriting: an unfrozen inventory can
    # change under a rewrite that already assumed it.
    baselines = by_type.get("ConceptBaseline", [])
    if not baselines:
        readiness.blockers.append(
            Blocker(
                "baseline_frozen",
                "bundle",
                "no ConceptBaseline: nothing states which inventory is being "
                "rewritten against",
            )
        )
    for baseline in baselines:
        if not baseline.get("frozen"):
            readiness.blockers.append(
                Blocker(
                    "baseline_frozen",
                    baseline.get("baseline_id", "?"),
                    "baseline is not frozen; its concepts could still change "
                    "under a rewrite that assumed them",
                )
            )
        review = baseline.get("review_decision")
        if isinstance(review, Mapping) and not review.get("reviewer"):
            readiness.blockers.append(
                Blocker(
                    "baseline_frozen",
                    baseline.get("baseline_id", "?"),
                    "baseline names no reviewer; a human signs the baseline",
                )
            )

    if spans:
        readiness.blockers.extend(check_span_coverage(spans, snapshots))
        readiness.checks_run.append("span_coverage")
        readiness.blockers.extend(
            check_classification_resolved(spans, concepts, scaffolding)
        )
        readiness.checks_run.append("classification_resolved")
    else:
        readiness.blockers.append(
            Blocker(
                "span_coverage",
                "bundle",
                "no SourceSpan records: the source was never partitioned, so "
                "coverage and classification cannot be checked",
            )
        )

    if concepts:
        readiness.blockers.extend(check_dependency_integrity(dependencies, concepts))
        readiness.checks_run.append("dependency_integrity")
        readiness.blockers.extend(
            check_obligation_presence(obligations, concepts, units)
        )
        readiness.checks_run.append("obligation_presence")
        readiness.blockers.extend(
            check_protected_object_links(units, concepts, manifests)
        )
        readiness.checks_run.append("protected_object_links")
    else:
        readiness.blockers.append(
            Blocker(
                "classification_resolved",
                "bundle",
                "no SourceConcept records: an empty inventory is not a complete "
                "one, and rewriting would have nothing to preserve",
            )
        )

    if not units:
        readiness.notes.append(
            "no RewriteUnit records: unit assignment was not checked"
        )

    return readiness


def assert_ready_to_rewrite(
    records: Iterable[Mapping[str, Any]],
    *,
    validate_schemas: bool = True,
) -> Readiness:
    """Return the readiness verdict, or raise `NotReadyToRewrite`.

    This is what a rewrite command calls. It raises rather than returning a
    flag because a caller that forgets to check a returned boolean would start
    rewriting against an incomplete baseline, which is the exact failure this
    gate exists to make impossible.
    """
    readiness = assess_readiness(records, validate_schemas=validate_schemas)
    if not readiness.ready:
        raise NotReadyToRewrite(readiness)
    return readiness
