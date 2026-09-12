"""Rewriting cannot start against an incomplete baseline (WP-V2-1, V2-G1).

V2-G1 names five conditions that must block a rewrite: an uncovered source
span, an unresolved concept or scaffolding classification, a dangling
dependency, a missing explanation obligation, and an invalid protected-object
link. `schemas.validate_bundle` already rejects most of those when the records
are present. The gap this module closes is different and more dangerous: every
bundle check is conditional on records existing, so an empty or partial bundle
passes all of them. `validate_bundle([])` returns no errors.

That is the same fail-open shape as the 2026-08-29 release-gate incident, where
a pilot released known violations with every gate reporting "pass" because the
checks had nothing to look at. These tests pin that absence is never a pass:
`Readiness.ready` requires that all five checks actually ran.
"""

import copy
import json
from pathlib import Path

import pytest

from humanvoice.readiness import (
    REQUIRED_CHECKS,
    NotReadyToRewrite,
    assert_ready_to_rewrite,
    assess_readiness,
    check_dependency_integrity,
    check_span_coverage,
)
from humanvoice.schemas import get_registry

BUNDLE = (
    Path(__file__).resolve().parents[1]
    / "schemas/examples/humanization-pipeline.bundle.valid.json"
)


@pytest.fixture
def bundle():
    return json.loads(BUNDLE.read_text())


def record(records, record_id):
    return next(row for row in records if row.get("record_id") == record_id)


def of_type(records, record_type):
    return [row for row in records if row.get("record_type") == record_type]


def without(records, *record_types):
    return [row for row in records if row.get("record_type") not in record_types]


class TestAbsenceIsNeverAPass:
    """The fail-open cases: nothing to check must not read as nothing wrong."""

    def test_empty_bundle_passes_the_bundle_validator(self):
        """Documents the gap this gate closes; not an endorsement of it.

        `validate_bundle` is a record validator: given no records it correctly
        reports no invalid records. That answer is right for its question and
        catastrophic as an answer to "may rewriting start".
        """
        assert get_registry().validate_bundle([], raise_on_error=False) == []

    def test_empty_bundle_is_not_ready(self):
        readiness = assess_readiness([], validate_schemas=False)
        assert not readiness.ready
        assert readiness.checks_run == []

    def test_readiness_requires_every_check_to_have_run(self):
        """A verdict with no blockers is still not ready if a check was skipped."""
        readiness = assess_readiness([], validate_schemas=False)
        readiness.blockers.clear()
        assert not readiness.ready, "no blockers must not mean ready"
        assert "could not run" in readiness.summary()

    def test_missing_spans_blocks_and_says_so(self, bundle):
        readiness = assess_readiness(without(bundle, "SourceSpan"), validate_schemas=False)
        assert not readiness.ready
        assert "span_coverage" not in readiness.checks_run
        assert any("never partitioned" in str(b) for b in readiness.blockers)

    def test_missing_concepts_blocks_and_says_so(self, bundle):
        readiness = assess_readiness(
            without(bundle, "SourceConcept"), validate_schemas=False
        )
        assert not readiness.ready
        assert "obligation_presence" not in readiness.checks_run
        assert any("empty inventory is not a complete one" in str(b)
                   for b in readiness.blockers)

    def test_missing_protected_manifest_blocks_when_objects_are_named(self, bundle):
        """Nothing would be watching the equations during the rewrite."""
        readiness = assess_readiness(
            without(bundle, "ProtectedManifest"), validate_schemas=False
        )
        assert not readiness.ready
        assert any("no ProtectedManifest" in str(b) for b in readiness.blockers)

    def test_missing_baseline_blocks(self, bundle):
        readiness = assess_readiness(
            without(bundle, "ConceptBaseline"), validate_schemas=False
        )
        assert not readiness.ready
        assert any("no ConceptBaseline" in str(b) for b in readiness.blockers)


class TestCanonicalBundleIsReady:
    """Guard the fixture: if the valid bundle stops passing, the gate is wrong."""

    def test_valid_bundle_is_ready(self, bundle):
        readiness = assess_readiness(bundle)
        assert readiness.ready, readiness.report()
        assert set(readiness.checks_run) == set(REQUIRED_CHECKS)
        assert readiness.summary().startswith("ready to rewrite")

    def test_assert_ready_returns_the_verdict(self, bundle):
        readiness = assert_ready_to_rewrite(bundle)
        assert readiness.ready

    def test_schema_invalid_bundle_reports_only_schema_failures(self, bundle):
        """Semantic checks must not run over malformed records."""
        broken = copy.deepcopy(bundle)
        del record(broken, "span-1")["byte_start"]
        readiness = assess_readiness(broken)
        assert not readiness.ready
        assert all(b.check == "schema_validity" for b in readiness.blockers)
        assert any("not schema-valid" in note for note in readiness.notes)


class TestUncoveredSpan:
    """V2-G1 condition 1: no reader-facing byte goes unclassified."""

    def test_interior_gap_is_located_by_byte_range(self, bundle):
        """A hole between two spans, with the file's last offset still correct.

        This is the shape a maximum-offset check cannot see: spans end at the
        declared file size, so the file looks covered, while twenty bytes in
        the middle belong to no span. Those bytes could hold a qualification.
        """
        holed = copy.deepcopy(bundle)
        record(holed, "span-2")["byte_start"] = 80
        readiness = assess_readiness(holed, validate_schemas=False)
        assert not readiness.ready
        gaps = readiness.by_check()["span_coverage"]
        assert any(g.locator == "main.tex[60:80]" for g in gaps), [str(g) for g in gaps]
        assert any("20 unclassified byte(s)" in g.detail for g in gaps)

    def test_overlapping_spans_are_rejected(self, bundle):
        """Two spans claiming the same bytes would be rewritten twice."""
        overlapped = copy.deepcopy(bundle)
        record(overlapped, "span-2")["byte_start"] = 40
        readiness = assess_readiness(overlapped, validate_schemas=False)
        assert not readiness.ready
        assert any("overlaps the preceding span" in str(b) for b in readiness.blockers)

    def test_trailing_bytes_are_rejected(self, bundle):
        truncated = copy.deepcopy(bundle)
        record(truncated, "span-3")["byte_end"] = 180
        readiness = assess_readiness(truncated, validate_schemas=False)
        assert not readiness.ready
        assert any("trailing byte(s) never classified" in str(b)
                   for b in readiness.blockers)

    def test_spans_past_the_declared_size_are_rejected(self, bundle):
        long_spans = copy.deepcopy(bundle)
        record(long_spans, "span-3")["byte_end"] = 260
        readiness = assess_readiness(long_spans, validate_schemas=False)
        assert not readiness.ready
        assert any("past the declared end" in str(b) for b in readiness.blockers)

    def test_undeclared_file_is_rejected(self, bundle):
        stray = copy.deepcopy(bundle)
        record(stray, "span-3")["source_file"] = "appendix.tex"
        readiness = assess_readiness(stray, validate_schemas=False)
        assert not readiness.ready
        assert any("snapshot does not declare" in str(b) for b in readiness.blockers)

    def test_declared_file_with_no_spans_is_rejected(self, bundle):
        recs = copy.deepcopy(bundle)
        snapshot = of_type(recs, "SourceSnapshot")[0]
        snapshot["source_files"].append(
            {"path": "appendix.tex", "byte_size": 40, "sha256": "d" * 64}
        )
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("no spans at all" in str(b) for b in readiness.blockers)

    def test_missing_byte_size_cannot_be_verified(self):
        """An unmeasurable file is a blocker, not an assumption of coverage."""
        spans = [{
            "record_type": "SourceSpan", "record_id": "s1",
            "source_file": "main.tex", "byte_start": 0, "byte_end": 10,
        }]
        snapshots = [{"source_files": [{"path": "main.tex"}]}]
        blockers = check_span_coverage(spans, snapshots)
        assert any("coverage cannot be verified" in b.detail for b in blockers)

    def test_no_snapshot_means_nothing_declares_the_bytes(self):
        blockers = check_span_coverage([{"source_file": "main.tex"}], [])
        assert blockers
        assert "no SourceSnapshot" in blockers[0].detail


class TestUnresolvedClassification:
    """V2-G1 condition 2: no open question about what a span or concept is."""

    def test_unresolved_span_blocks(self, bundle):
        """The partitioner's honest default is an impossible rewrite state.

        Every reader-facing span starts `unresolved` because the partitioner
        classifies form and cannot judge meaning. Something must decide before
        a rewrite call, and this is what forces it.
        """
        recs = copy.deepcopy(bundle)
        record(recs, "span-1")["coverage_disposition"] = "unresolved"
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("still unresolved" in str(b) for b in readiness.blockers)

    def test_concept_bearing_span_must_name_a_concept(self, bundle):
        recs = copy.deepcopy(bundle)
        record(recs, "span-1")["concept_ids"] = []
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("names no concept" in str(b) for b in readiness.blockers)

    def test_scaffolding_span_must_have_an_accountable_disposition(self, bundle):
        """Calling text scaffolding is a judgement someone has to own."""
        recs = copy.deepcopy(bundle)
        record(recs, "span-3")["scaffolding_disposition_ids"] = []
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("no accountable disposition" in str(b) for b in readiness.blockers)

    @pytest.mark.parametrize("status", ["proposed", "ambiguous"])
    def test_unaccepted_concept_blocks(self, bundle, status):
        recs = copy.deepcopy(bundle)
        of_type(recs, "SourceConcept")[0]["review_status"] = status
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("has not accepted it" in str(b) for b in readiness.blockers)

    def test_unadjudicated_scaffolding_blocks(self, bundle):
        recs = copy.deepcopy(bundle)
        of_type(recs, "ScaffoldingDisposition")[0]["disposition"] = "unresolved"
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("has not been decided" in str(b) for b in readiness.blockers)

    def test_unfrozen_baseline_blocks(self, bundle):
        """Uniquely caught here: the bundle validator permits an open baseline.

        `_baseline_errors` returns early unless `frozen` is true, so an unfrozen
        baseline skips every baseline check. Rewriting against an inventory that
        can still change means the plan and the baseline can silently diverge.
        """
        recs = copy.deepcopy(bundle)
        of_type(recs, "ConceptBaseline")[0]["frozen"] = False
        assert get_registry().validate_bundle(recs, raise_on_error=False) == []
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("not frozen" in str(b) for b in readiness.blockers)

    def test_baseline_without_a_reviewer_blocks(self, bundle):
        """A human signs the baseline; an unsigned one is not adjudicated."""
        recs = copy.deepcopy(bundle)
        of_type(recs, "ConceptBaseline")[0]["review_decision"]["reviewer"] = ""
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("names no reviewer" in str(b) for b in readiness.blockers)


class TestDependencyIntegrity:
    """V2-G1 condition 3: prerequisites resolve and can be ordered."""

    @pytest.mark.parametrize(
        "field", ["prerequisite_concept_id", "dependent_concept_id"]
    )
    def test_dangling_endpoint_blocks(self, bundle, field):
        recs = copy.deepcopy(bundle)
        of_type(recs, "ConceptDependency")[0][field] = "concept-absent"
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("absent from the baseline" in str(b) for b in readiness.blockers)

    def test_self_dependency_blocks(self, bundle):
        recs = copy.deepcopy(bundle)
        dependency = of_type(recs, "ConceptDependency")[0]
        dependency["prerequisite_concept_id"] = dependency["dependent_concept_id"]
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("its own prerequisite" in str(b) for b in readiness.blockers)

    def test_cycle_blocks_and_names_the_path(self, bundle):
        """A cycle means no teaching order exists at all."""
        recs = copy.deepcopy(bundle)
        dependency = of_type(recs, "ConceptDependency")[0]
        reverse = copy.deepcopy(dependency)
        reverse["record_id"] = reverse["dependency_id"] = "dependency-2"
        reverse["prerequisite_concept_id"] = dependency["dependent_concept_id"]
        reverse["dependent_concept_id"] = dependency["prerequisite_concept_id"]
        recs.append(reverse)
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        cycles = [b for b in readiness.blockers if "cycle" in b.detail]
        assert cycles
        assert "concept-1" in cycles[0].locator and "concept-2" in cycles[0].locator

    def test_longer_cycle_is_found(self):
        concepts = [
            {"record_type": "SourceConcept", "concept_id": f"c{i}",
             "review_status": "accepted"}
            for i in range(1, 4)
        ]
        dependencies = [
            {"dependency_id": "d1", "prerequisite_concept_id": "c1",
             "dependent_concept_id": "c2"},
            {"dependency_id": "d2", "prerequisite_concept_id": "c2",
             "dependent_concept_id": "c3"},
            {"dependency_id": "d3", "prerequisite_concept_id": "c3",
             "dependent_concept_id": "c1"},
        ]
        blockers = check_dependency_integrity(dependencies, concepts)
        assert any("cycle" in b.detail for b in blockers)

    def test_acyclic_chain_is_accepted(self):
        """A long prerequisite chain is correct, not a cycle."""
        concepts = [
            {"record_type": "SourceConcept", "concept_id": f"c{i}",
             "review_status": "accepted"}
            for i in range(1, 12)
        ]
        dependencies = [
            {"dependency_id": f"d{i}", "prerequisite_concept_id": f"c{i}",
             "dependent_concept_id": f"c{i + 1}"}
            for i in range(1, 11)
        ]
        assert check_dependency_integrity(dependencies, concepts) == []

    def test_diamond_is_accepted(self):
        """Two paths to the same dependent is not a cycle."""
        concepts = [
            {"record_type": "SourceConcept", "concept_id": c,
             "review_status": "accepted"}
            for c in ("a", "b", "c", "d")
        ]
        dependencies = [
            {"dependency_id": "d1", "prerequisite_concept_id": "a",
             "dependent_concept_id": "b"},
            {"dependency_id": "d2", "prerequisite_concept_id": "a",
             "dependent_concept_id": "c"},
            {"dependency_id": "d3", "prerequisite_concept_id": "b",
             "dependent_concept_id": "d"},
            {"dependency_id": "d4", "prerequisite_concept_id": "c",
             "dependent_concept_id": "d"},
        ]
        assert check_dependency_integrity(dependencies, concepts) == []

    def test_dependency_on_a_rejected_concept_blocks(self):
        concepts = [
            {"record_type": "SourceConcept", "concept_id": "a",
             "review_status": "accepted"},
            {"record_type": "SourceConcept", "concept_id": "b",
             "review_status": "rejected"},
        ]
        dependencies = [
            {"dependency_id": "d1", "prerequisite_concept_id": "b",
             "dependent_concept_id": "a"}
        ]
        blockers = check_dependency_integrity(dependencies, concepts)
        assert any("rejected concept" in b.detail for b in blockers)


class TestObligationPresence:
    """V2-G1 condition 4: something requires each concept to be explained.

    This is the condition that separates retention from teaching. Every other
    check would pass on a revision that names all the concepts and explains
    none of them, which is exactly the failure the ZLB run produced.
    """

    def test_concept_without_an_obligation_blocks(self, bundle):
        recs = [
            row for row in bundle
            if row.get("obligation_id") != "obligation-1"
        ]
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("nothing would require the rewrite to teach it" in str(b)
                   for b in readiness.blockers)

    def test_obligation_with_no_teaching_function_blocks(self, bundle):
        """An obligation that demands nothing is not an obligation."""
        recs = copy.deepcopy(bundle)
        of_type(recs, "ExplanationObligation")[0]["required_teaching_functions"] = []
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("demands nothing of the rewrite" in str(b)
                   for b in readiness.blockers)

    def test_deactivation_without_a_reason_blocks(self, bundle):
        """Deactivating is the one way to drop a teaching requirement.

        It is legitimate and it must be attributable, otherwise deactivating an
        obligation is indistinguishable from quietly dropping the explanation.
        """
        recs = copy.deepcopy(bundle)
        obligation = of_type(recs, "ExplanationObligation")[0]
        obligation["active"] = False
        obligation["deactivation"] = None
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("no recorded deactivation reason" in str(b)
                   for b in readiness.blockers)

    def test_concept_with_only_inactive_obligations_blocks(self, bundle):
        """Retained but never explained is the failure mode being prevented."""
        recs = copy.deepcopy(bundle)
        for obligation in of_type(recs, "ExplanationObligation"):
            obligation["active"] = False
            obligation["deactivation"] = {
                "reason": "reader already knows this",
                "decided_by": "reviewer",
                "decided_at": "2026-09-11T00:00:00Z",
            }
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("retained without being explained" in str(b)
                   for b in readiness.blockers)

    def test_unresolved_fulfillment_blocks(self, bundle):
        recs = copy.deepcopy(bundle)
        of_type(recs, "ExplanationObligation")[0]["fulfillment_status"] = "unresolved"
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("needs adjudication" in str(b) for b in readiness.blockers)

    def test_unassessed_fulfillment_is_the_correct_prerewrite_state(self, bundle):
        """Before rewriting, unassessed is right; fulfilment is preflight's job."""
        recs = copy.deepcopy(bundle)
        for obligation in of_type(recs, "ExplanationObligation"):
            obligation["fulfillment_status"] = "unassessed"
            obligation["fulfillment_evidence"] = []
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not any(b.check == "obligation_presence" for b in readiness.blockers), \
            readiness.report()

    def test_obligation_assigned_to_no_unit_blocks(self, bundle):
        """An active obligation no call is responsible for would never be met."""
        recs = copy.deepcopy(bundle)
        for unit in of_type(recs, "RewriteUnit"):
            unit["explanation_obligation_ids"] = []
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("assigned to no rewrite unit" in str(b)
                   for b in readiness.blockers)

    def test_unit_naming_an_absent_obligation_blocks(self, bundle):
        recs = copy.deepcopy(bundle)
        of_type(recs, "RewriteUnit")[0]["explanation_obligation_ids"] = ["obligation-absent"]
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("absent from the baseline" in str(b) for b in readiness.blockers)

    def test_obligation_for_an_absent_concept_blocks(self, bundle):
        recs = copy.deepcopy(bundle)
        of_type(recs, "ExplanationObligation")[0]["concept_id"] = "concept-absent"
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("names a concept absent" in str(b) for b in readiness.blockers)


class TestProtectedObjectLinks:
    """V2-G1 condition 5: every protected reference resolves before the call."""

    def test_unit_naming_an_unknown_object_blocks(self, bundle):
        recs = copy.deepcopy(bundle)
        of_type(recs, "RewriteUnit")[0]["protected_object_ids"] = ["eq-absent"]
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("not in the manifest" in str(b) for b in readiness.blockers)

    def test_concept_naming_an_unknown_object_blocks(self, bundle):
        recs = copy.deepcopy(bundle)
        of_type(recs, "SourceConcept")[0]["protected_object_ids"] = ["eq-absent"]
        readiness = assess_readiness(recs, validate_schemas=False)
        assert not readiness.ready
        assert any("not in the manifest" in str(b) for b in readiness.blockers)

    def test_no_manifest_and_no_references_is_permitted(self):
        """A source with no equations or citations needs no manifest."""
        from humanvoice.readiness import check_protected_object_links

        assert check_protected_object_links(
            [{"unit_id": "u1", "protected_object_ids": []}],
            [{"concept_id": "c1", "protected_object_ids": []}],
            [],
        ) == []


class TestRefusalIsLoud:
    """The gate raises rather than returning a flag a caller could ignore."""

    def test_assert_raises_on_an_incomplete_baseline(self, bundle):
        recs = copy.deepcopy(bundle)
        record(recs, "span-2")["byte_start"] = 80
        with pytest.raises(NotReadyToRewrite) as caught:
            assert_ready_to_rewrite(recs, validate_schemas=False)
        assert "not ready to rewrite" in str(caught.value)
        assert caught.value.readiness.blockers

    def test_report_groups_by_check_and_locates_each_blocker(self, bundle):
        recs = copy.deepcopy(bundle)
        record(recs, "span-1")["coverage_disposition"] = "unresolved"
        of_type(recs, "ConceptDependency")[0]["dependent_concept_id"] = "concept-absent"
        readiness = assess_readiness(recs, validate_schemas=False)
        report = readiness.report()
        assert "classification_resolved" in report
        assert "dependency_integrity" in report
        assert set(readiness.by_check()) >= {
            "classification_resolved", "dependency_integrity"
        }

    def test_report_truncates_long_blocker_lists(self):
        """A thousand gaps must not produce a thousand-line refusal."""
        spans = [
            {
                "record_type": "SourceSpan", "record_id": f"s{i}",
                "source_file": "main.tex",
                "byte_start": i * 10, "byte_end": i * 10 + 5,
            }
            for i in range(30)
        ]
        snapshots = [{"source_files": [{"path": "main.tex", "byte_size": 300}]}]
        from humanvoice.readiness import Readiness

        readiness = Readiness(
            blockers=check_span_coverage(spans, snapshots),
            checks_run=list(REQUIRED_CHECKS),
        )
        assert not readiness.ready
        assert "and " in readiness.report() and "more" in readiness.report()
