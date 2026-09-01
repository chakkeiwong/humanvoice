"""
Tests for hv repair - bounded repair with cycle tracking and oscillation detection.

These are deterministic tests of the repair machinery: stop conditions, verbatim
replacement, and revision validation. They do not invoke the model. Behavioral
properties of the model itself live in tests/test_model_properties.py.
"""

import json
from pathlib import Path

import pytest

from humanvoice.commands.repair_command import (
    MAX_REPAIR_CYCLES,
    _apply_changes,
    _assign_finding_ids,
    _check_oscillation,
    _check_stop_conditions,
    _clear_unresolved_marker,
    _exempt_digits,
    _content_hash,
    _finding_signature,
    _load_revision_history,
    _publish_revision,
    _resolve_parent_draft,
    _validate_revision,
)


def finding(matched, message="private label", category="register"):
    return {
        "category": category,
        "message": message,
        "location": {"matched_text": matched},
    }


class TestFindingSignature:
    def test_signature_is_order_independent(self):
        a, b = finding("WP3"), finding("we", "first person")
        assert _finding_signature([a, b]) == _finding_signature([b, a])

    def test_different_findings_differ(self):
        assert _finding_signature([finding("WP3")]) != _finding_signature(
            [finding("WP4")]
        )

    def test_empty_findings_are_stable(self):
        assert _finding_signature([]) == _finding_signature([])

    def test_assign_finding_ids_is_sequential_and_preserves_existing(self):
        ids = [f["finding_id"] for f in _assign_finding_ids([finding("a"), finding("b")])]
        assert ids == ["F001", "F002"]

        preset = [{**finding("a"), "finding_id": "CUSTOM"}]
        assert _assign_finding_ids(preset)[0]["finding_id"] == "CUSTOM"


class TestStopConditions:
    """Pre-model stop conditions: cycle limit and repeated finding signature."""

    def test_first_cycle_proceeds(self):
        assert _check_stop_conditions([], "sigA") is None

    def test_progress_proceeds(self):
        history = [{"cycle": 1, "finding_signature": "sigA", "content_hash": "h1"}]
        assert _check_stop_conditions(history, "sigB") is None

    def test_cycle_limit_blocks(self):
        history = [
            {"cycle": i, "finding_signature": f"sig{i}", "content_hash": f"h{i}"}
            for i in range(1, MAX_REPAIR_CYCLES + 1)
        ]
        stop = _check_stop_conditions(history, "sigNew")
        assert stop["stop_condition"] == "cycle_limit"
        assert stop["cycles_used"] == MAX_REPAIR_CYCLES
        assert "author_choice" in stop

    def test_repeated_finding_signature_blocks(self):
        history = [{"cycle": 1, "finding_signature": "sigA", "content_hash": "h1"}]
        stop = _check_stop_conditions(history, "sigA")
        assert stop["stop_condition"] == "repeated_finding_signature"
        assert stop["first_seen_cycle"] == 1

    def test_unreadable_manifest_consumes_a_cycle(self, tmp_path):
        """Corruption must not buy extra repair attempts."""
        revisions = tmp_path / "revisions"
        for i in range(MAX_REPAIR_CYCLES):
            rev = revisions / f"rev-00{i}-abc"
            rev.mkdir(parents=True)
            (rev / "revision_manifest.json").write_text("{ not json")

        history = _load_revision_history(revisions)
        assert len(history) == MAX_REPAIR_CYCLES
        assert _check_stop_conditions(history, "s")["stop_condition"] == "cycle_limit"


class TestOscillationDetection:
    """Post-model check: alternation is only knowable once the repair exists."""

    def test_chaining_from_parent_is_not_oscillation(self):
        """Cycle 1's published hash IS cycle 2's parent; that is normal progress."""
        history = [{"cycle": 1, "finding_signature": "sigA", "content_hash": "hParent"}]
        assert _check_oscillation(history, "hParent", "hNew") is None

    def test_returning_to_a_pre_parent_state_blocks(self):
        history = [
            {"cycle": 1, "finding_signature": "sigA", "content_hash": "hOld"},
            {"cycle": 2, "finding_signature": "sigB", "content_hash": "hParent"},
        ]
        stop = _check_oscillation(history, "hParent", "hOld")
        assert stop["stop_condition"] == "alternating_parent_hashes"
        assert stop["seen_at_cycle"] == 1

    def test_no_op_repair_blocks(self):
        stop = _check_oscillation([], "hSame", "hSame")
        assert stop["stop_condition"] == "no_op_repair"
        assert "author_choice" in stop

    def test_novel_content_proceeds(self):
        history = [{"cycle": 1, "content_hash": "hOld"}]
        assert _check_oscillation(history, "hParent", "hBrandNew") is None


class TestVerbatimReplacement:
    DRAFT = "We measured 12,000 qps. The pool saturates. The pool saturates again."

    def test_exact_match_applies(self):
        revised, applied, refused = _apply_changes(
            self.DRAFT,
            [{"finding_id": "F1", "original": "We measured", "revised": "Measurements show"}],
        )
        assert revised.startswith("Measurements show 12,000")
        assert len(applied) == 1
        assert refused == []

    def test_absent_original_is_refused_not_fuzzy_matched(self):
        revised, applied, refused = _apply_changes(
            self.DRAFT,
            [{"finding_id": "F1", "original": "we measured", "revised": "X"}],
        )
        assert revised == self.DRAFT
        assert applied == []
        assert "not found verbatim" in refused[0]["refusal"]

    def test_ambiguous_original_is_refused(self):
        """Two occurrences means we cannot know which the model meant."""
        revised, applied, refused = _apply_changes(
            self.DRAFT,
            [{"finding_id": "F1", "original": "The pool saturates", "revised": "Y"}],
        )
        assert revised == self.DRAFT
        assert applied == []
        assert "ambiguous" in refused[0]["refusal"]

    def test_empty_original_is_refused(self):
        _, applied, refused = _apply_changes(
            self.DRAFT, [{"finding_id": "F1", "original": "", "revised": "Z"}]
        )
        assert applied == []
        assert refused[0]["refusal"] == "empty original string"

    def test_changes_apply_against_progressively_revised_text(self):
        """A later edit must not resurrect text an earlier edit removed."""
        revised, applied, refused = _apply_changes(
            "alpha beta gamma",
            [
                {"finding_id": "F1", "original": "alpha beta", "revised": "delta"},
                {"finding_id": "F2", "original": "beta gamma", "revised": "epsilon"},
            ],
        )
        assert revised == "delta gamma"
        assert len(applied) == 1
        assert len(refused) == 1

    def test_partial_application_reports_both(self):
        revised, applied, refused = _apply_changes(
            self.DRAFT,
            [
                {"finding_id": "F1", "original": "We measured", "revised": "Data show"},
                {"finding_id": "F2", "original": "nonexistent", "revised": "X"},
            ],
        )
        assert len(applied) == 1
        assert len(refused) == 1
        assert "Data show" in revised


class TestRevisionValidation:
    DRAFT = r"Peak was 12,000 qps and 2.1 TB \cite{baseline_metrics}."

    def test_clean_repair_passes(self):
        revised = r"The peak reached 12,000 qps and 2.1 TB \cite{baseline_metrics}."
        assert _validate_revision(self.DRAFT, revised, {}) == []

    def test_dropped_citation_fails(self):
        assert "citation" in _validate_revision(
            self.DRAFT, "Peak was 12,000 qps and 2.1 TB.", {}
        )[0]

    def test_dropped_number_fails(self):
        failures = _validate_revision(
            self.DRAFT, r"Peak was 12,000 qps \cite{baseline_metrics}.", {}
        )
        assert any("numeric" in f for f in failures)

    def test_altered_number_fails(self):
        failures = _validate_revision(
            self.DRAFT, r"Peak was 13,000 qps and 2.1 TB \cite{baseline_metrics}.", {}
        )
        assert any("12000" in f for f in failures)

    @pytest.mark.parametrize(
        "reformatted",
        [r"12{,}000", "12\\,000", "12000"],
    )
    def test_latex_digit_grouping_is_not_a_dropped_number(self, reformatted):
        """12{,}000 is the same figure as 12,000, not two figures."""
        revised = (
            f"Peak was {reformatted} qps and 2.1 TB \\cite{{baseline_metrics}}."
        )
        assert _validate_revision(self.DRAFT, revised, {}) == []

    def test_empty_revision_fails(self):
        assert _validate_revision(self.DRAFT, "   ", {}) == ["revision is empty"]

    def test_digits_inside_an_offending_label_may_be_removed(self):
        """Clearing the finding 'WP2' necessarily removes that 2; that is the point."""
        original = r"In WP2 the team logged 76 minutes \cite{ih}."
        revised = r"The team logged 76 minutes \cite{ih}."
        findings = [finding("WP2", "private workflow label")]

        assert _validate_revision(original, revised, {}, findings) == []
        # Without the finding as context, the lost digit looks like a lost figure.
        assert _validate_revision(original, revised, {}) != []

    def test_exemption_does_not_license_dropping_evidentiary_figures(self):
        original = r"In WP2 the team logged 76 minutes \cite{ih}."
        revised = r"The team logged some minutes \cite{ih}."
        failures = _validate_revision(original, revised, {}, findings=[finding("WP2")])
        assert any("76" in f for f in failures)

    def test_exempt_digits_extracts_only_finding_digits(self):
        assert _exempt_digits([finding("WP2"), finding("WP3")]) == {"2", "3"}
        assert _exempt_digits([finding("we")]) == set()
        assert _exempt_digits(None) == set()

    def test_citations_are_never_exempt(self):
        """A finding cannot license dropping a citation key."""
        original = r"Logged 76 minutes \cite{ih}."
        revised = "Logged 76 minutes."
        failures = _validate_revision(original, revised, {}, findings=[finding(r"\cite{ih}")])
        assert any("citation" in f for f in failures)

    def test_introduced_first_person_fails(self):
        failures = _validate_revision("Measurements show 5 items.", "We show 5 items.", {})
        assert any("register" in f for f in failures)

    def test_preexisting_first_person_is_not_charged_to_the_repair(self):
        """Repair is judged on what it introduces, not what it inherited."""
        assert _validate_revision("We show 5 items.", "We showed 5 items.", {}) == []

    def test_removed_protected_object_fails(self):
        brief = {"protected_objects": [r"\ref{eq:cap}"]}
        original = r"See \ref{eq:cap} for the bound. Value 5."
        failures = _validate_revision(original, "See the bound. Value 5.", brief)
        assert any("protected object" in f for f in failures)


class TestRevisionPublishing:
    def test_publish_is_atomic_and_leaves_no_staging_dir(self, tmp_path):
        revisions = tmp_path / "revisions"
        revisions.mkdir()
        manifest = {"revision_id": "rev-001", "cycle": 1, "content_hash": "a" * 64}

        final = _publish_revision(revisions, 1, "revised text", manifest, "draft.tex")

        assert final.is_dir()
        assert (final / "draft.tex").read_text() == "revised text"
        assert json.loads((final / "revision_manifest.json").read_text())["cycle"] == 1
        assert not list(revisions.glob(".staging-*"))

    def test_publish_refuses_to_overwrite_existing_revision(self, tmp_path):
        revisions = tmp_path / "revisions"
        manifest = {"revision_id": "rev-001", "cycle": 1, "content_hash": "b" * 64}
        revisions.mkdir()
        _publish_revision(revisions, 1, "first", manifest, "draft.tex")

        with pytest.raises(ValueError, match="already published"):
            _publish_revision(revisions, 1, "second", manifest, "draft.tex")

    def test_staged_but_unpublished_revision_does_not_consume_a_cycle(self, tmp_path):
        """An interrupted repair leaves staging behind; history must ignore it."""
        revisions = tmp_path / "revisions"
        staged = revisions / ".staging-rev-001-abc"
        staged.mkdir(parents=True)
        (staged / "draft.tex").write_text("half-written")

        assert _load_revision_history(revisions) == []

    def test_history_is_ordered_by_cycle(self, tmp_path):
        revisions = tmp_path / "revisions"
        for cycle in (3, 1, 2):
            rev = revisions / f"rev-{cycle:03d}-hash{cycle}"
            rev.mkdir(parents=True)
            (rev / "revision_manifest.json").write_text(
                json.dumps({"cycle": cycle, "revision_id": rev.name})
            )

        assert [m["cycle"] for m in _load_revision_history(revisions)] == [1, 2, 3]

    def test_missing_revisions_dir_is_empty_history(self, tmp_path):
        assert _load_revision_history(tmp_path / "nothing") == []

    def test_successful_cycle_retires_a_superseded_block_marker(self, tmp_path):
        """A converged repair must not leave hv release gated by an old block."""
        revisions = tmp_path / "revisions"
        final = revisions / "rev-002-abc"
        final.mkdir(parents=True)
        marker = revisions / "unresolved_author_choice.json"
        marker.write_text(json.dumps({"status": "blocked"}))

        _clear_unresolved_marker(revisions, final)

        assert not marker.exists()
        # Preserved for audit inside the revision that resolved it.
        assert (final / "superseded_author_choice.json").is_file()

    def test_clearing_marker_is_safe_when_absent(self, tmp_path):
        final = tmp_path / "rev-001"
        final.mkdir()
        _clear_unresolved_marker(tmp_path, final)  # must not raise


class TestParentResolution:
    def test_base_draft_is_parent_on_first_cycle(self, tmp_path):
        draft = tmp_path / "draft.tex"
        draft.write_text("original")
        parent, cycle = _resolve_parent_draft(draft, tmp_path / "revisions")
        assert parent == draft
        assert cycle == 1

    def test_latest_revision_is_parent_on_second_cycle(self, tmp_path):
        draft = tmp_path / "draft.tex"
        draft.write_text("original")
        revisions = tmp_path / "revisions"
        rev = revisions / "rev-001-abc"
        rev.mkdir(parents=True)
        (rev / "draft.tex").write_text("first repair")
        (rev / "revision_manifest.json").write_text(
            json.dumps({"cycle": 1, "revision_id": "rev-001-abc"})
        )

        parent, cycle = _resolve_parent_draft(draft, revisions)
        assert parent.read_text() == "first repair"
        assert cycle == 2

    def test_canonical_draft_is_never_written(self, tmp_path):
        """The base draft must survive a published revision byte-identical."""
        draft = tmp_path / "draft.tex"
        draft.write_text("original text")
        revisions = tmp_path / "revisions"
        revisions.mkdir()
        _publish_revision(
            revisions, 1, "repaired text",
            {"revision_id": "rev-001", "cycle": 1, "content_hash": "c" * 64},
            "draft.tex",
        )
        assert draft.read_text() == "original text"
