"""Brief validation has one definition (WP-V2-1).

`init_command` used to check five flat v1 fields while
`schemas/humanization-brief.schema.json` defined a twenty-field structured
record. The two could disagree in both directions. These tests pin that the
schema is now the only definition for a v2 brief, that a legal-but-unanswered
field blocks rewriting, and that the v1 path still works while it is legacy.
"""

import json

import pytest

from humanvoice.brief import (
    CRITICAL_PATHS,
    assess_brief,
    validate_brief,
)
from humanvoice.commands.init_command import _validate_brief, _validate_v1_brief


def v2_brief(**overrides):
    brief = {
        "record_type": "HumanizationBrief",
        "schema_version": "HV-SCHEMA-2.0",
        "record_id": "brief-1",
        "run_id": "run-001",
        "created_at": "2026-09-11T00:00:00Z",
        "source_entry_point": "main.tex",
        "reader": {
            "role": "senior macroeconomist outside the project",
            "prior_knowledge": ["Bayesian inference", "DSGE models"],
            "reading_context": "deciding whether to fund a larger comparative run",
        },
        "purpose": "make the ZLB comparison understandable without project history",
        "decision": "authorize the larger comparative run",
        "genre": "technical research survey",
        "known_vocabulary": ["posterior", "likelihood", "kink"],
        "exemplars": [
            {
                "path": "docs/exemplars/card_npv.tex",
                "sha256": "c" * 64,
                "use": "teaching_order",
            }
        ],
        "evidence_boundary": "only the source manuscript and its cited works",
        "privacy_class": "internal",
        "remote_inference": {
            "authorized": True,
            "provider": "Anthropic",
            "purpose": "concept extraction and passage rewriting",
            "approved_by": "project owner",
        },
        "voice_constraints": {
            "register": "formal academic prose",
            "person": "mixed",
            "additional": ["no marketing register", "no defensive nonclaims"],
        },
        "protected_object_policy": "equations, numbers, citations, and tables may not change silently",
        "unresolved_assumptions": [],
        "authorizing_action": {
            "actor": "project owner",
            "role": "author",
            "action": "humanize_finished_manuscript",
            "authorized_at": "2026-09-11T00:00:00Z",
        },
        "policy_sources": [
            {
                "path": "../claudecodex/policies/humanizer-ai-writing-patterns.md",
                "sha256": "b" * 64,
            }
        ],
    }
    for key, value in overrides.items():
        brief[key] = value
    return brief


def v1_brief(**overrides):
    brief = {
        "reader_role": "senior economist",
        "decision_type": "funding",
        "time_available_minutes": 30,
        "prior_knowledge": "Bayesian inference",
        "success_criteria": "can state the requested action",
    }
    brief.update(overrides)
    return brief


class TestSchemaIsTheDefinition:
    def test_complete_v2_brief_is_ready(self):
        assessment = assess_brief(v2_brief())
        assert assessment.valid, assessment.errors
        assert assessment.critical_blanks == []
        assert assessment.ready_for_rewrite
        assert assessment.summary() == "brief is complete"

    def test_missing_schema_field_is_invalid(self):
        brief = v2_brief()
        del brief["genre"]
        assessment = assess_brief(brief)
        assert not assessment.valid
        assert not assessment.ready_for_rewrite
        assert any("genre" in error for error in assessment.errors)

    def test_wrong_record_type_is_invalid(self):
        assessment = assess_brief(v2_brief(record_type="AuthoringBrief"))
        assert not assessment.valid

    def test_command_and_schema_now_agree(self):
        """The same brief must get the same verdict from both entry points."""
        brief = v2_brief()
        assert _validate_brief(brief)[0] is True
        assert validate_brief(brief)[0] is True

        broken = v2_brief()
        del broken["evidence_boundary"]
        assert _validate_brief(broken)[0] is False
        assert validate_brief(broken)[0] is False


class TestCriticalBlanks:
    """Schema-valid but unanswered fields block a rewrite.

    Two mechanisms block an unusable brief and they are not interchangeable.
    An empty string or an empty `policy_sources` array violates the schema's
    own `minLength`/`minItems`, so it is an *error*: the file is malformed.
    A placeholder like "TBD", or an empty array the schema permits, is a
    *critical blank*: the file is well-formed and the question is unanswered.
    The tests below exercise the blank path deliberately, using values the
    schema accepts, so they cannot pass by accident on a schema failure.
    """

    def test_empty_prior_knowledge_blocks_rewrite(self):
        brief = v2_brief()
        brief["reader"]["prior_knowledge"] = []
        assessment = assess_brief(brief)
        assert assessment.valid, assessment.errors
        assert not assessment.ready_for_rewrite
        assert any("prior_knowledge" in blank for blank in assessment.critical_blanks)

    def test_placeholder_text_counts_as_blank(self):
        for placeholder in ("TBD", "unknown", "  ", "n/a", "pending", "?"):
            brief = v2_brief(purpose=placeholder)
            assessment = assess_brief(brief)
            assert not assessment.ready_for_rewrite, placeholder
            assert any("purpose" in blank for blank in assessment.critical_blanks)

    def test_empty_policy_sources_is_a_schema_error_not_a_blank(self):
        """The schema requires at least one policy source, so [] is malformed.

        Recorded as an error rather than a blank because the reader-facing
        rules in force are not a question for a human to answer later; a run
        without them cannot apply the policy layer at all.
        """
        assessment = assess_brief(v2_brief(policy_sources=[]))
        assert not assessment.valid
        assert not assessment.ready_for_rewrite
        assert any("policy_sources" in error for error in assessment.errors)

    def test_nested_voice_constraint_blank_is_caught(self):
        brief = v2_brief()
        brief["voice_constraints"]["register"] = "TBD"
        assessment = assess_brief(brief)
        assert assessment.valid, assessment.errors
        assert any(
            "voice_constraints.register" in blank
            for blank in assessment.critical_blanks
        )

    def test_empty_nested_string_is_a_schema_error(self):
        """`minLength` catches "" before the blank check ever sees it."""
        brief = v2_brief()
        brief["voice_constraints"]["register"] = ""
        assessment = assess_brief(brief)
        assert not assessment.valid
        assert not assessment.ready_for_rewrite
        assert any(
            "voice_constraints.register" in error for error in assessment.errors
        )

    def test_authorizing_action_blank_blocks_rewrite(self):
        brief = v2_brief()
        brief["authorizing_action"]["actor"] = "TBD"
        assessment = assess_brief(brief)
        assert any(
            "authorizing_action.actor" in blank
            for blank in assessment.critical_blanks
        )

    def test_authorized_remote_inference_needs_a_named_approver(self):
        """A placeholder approver is schema-legal and still not a person."""
        brief = v2_brief()
        brief["remote_inference"]["approved_by"] = "TBD"
        assessment = assess_brief(brief)
        assert assessment.valid, assessment.errors
        assert not assessment.ready_for_rewrite
        assert any("approved_by" in blank for blank in assessment.critical_blanks)

    def test_authorized_remote_inference_with_null_approver_is_invalid(self):
        """The schema's conditional catches an authorized-but-unapproved brief."""
        brief = v2_brief()
        brief["remote_inference"]["approved_by"] = None
        assessment = assess_brief(brief)
        assert not assessment.valid
        assert not assessment.ready_for_rewrite

    def test_every_critical_path_is_blocked_by_something(self):
        """Guard the table itself: emptying any listed path must block a rewrite.

        Which mechanism blocks it depends on the schema. `policy_sources: []`
        fails `minItems`; `voice_constraints.person: ""` fails its enum;
        `reader.prior_knowledge: []` is schema-legal and blocks as a blank.
        The invariant under test is that no critical field can be emptied and
        still reach a rewrite, and that whichever mechanism fires names the
        field, so the person fixing it knows where to look.
        """
        for dotted, _ in CRITICAL_PATHS:
            brief = v2_brief()
            target = brief
            parts = dotted.split(".")
            for part in parts[:-1]:
                target = target[part]
            original = target[parts[-1]]
            target[parts[-1]] = [] if isinstance(original, list) else ""
            assessment = assess_brief(brief)
            assert not assessment.ready_for_rewrite, dotted
            reported = assessment.errors + assessment.critical_blanks
            assert any(dotted in message for message in reported), (
                f"{dotted} blocked without naming the field: {reported}"
            )

    def test_placeholders_block_every_string_critical_path(self):
        """The blank check alone must cover every string field in the table.

        Distinct from the test above: a placeholder is schema-valid, so this
        exercises `_is_blank` with no help from the schema. Enum and array
        fields are excluded because a placeholder is not a legal value there.
        """
        for dotted, _ in CRITICAL_PATHS:
            brief = v2_brief()
            target = brief
            parts = dotted.split(".")
            for part in parts[:-1]:
                target = target[part]
            if not isinstance(target[parts[-1]], str):
                continue
            target[parts[-1]] = "TBD"
            assessment = assess_brief(brief)
            if not assessment.valid:
                # A `const`/`enum` field cannot hold a placeholder; the schema
                # already pins its only legal value.
                continue
            assert not assessment.ready_for_rewrite, dotted
            assert any(dotted in blank for blank in assessment.critical_blanks), dotted


class TestWarnings:
    def test_missing_exemplars_warns_without_blocking(self):
        assessment = assess_brief(v2_brief(exemplars=[]))
        assert assessment.ready_for_rewrite
        assert any("exemplars" in warning for warning in assessment.warnings)

    def test_empty_vocabulary_warns_without_blocking(self):
        assessment = assess_brief(v2_brief(known_vocabulary=[]))
        assert assessment.ready_for_rewrite
        assert any("known_vocabulary" in warning for warning in assessment.warnings)

    def test_carried_assumptions_are_reported(self):
        assessment = assess_brief(
            v2_brief(unresolved_assumptions=[
                "the wedge is an illustrative calibration, not an estimate"
            ])
        )
        assert assessment.ready_for_rewrite
        assert any("unresolved assumption" in w for w in assessment.warnings)


class TestNoLengthTarget:
    def test_v2_brief_has_no_reading_time_budget(self):
        """A reading-time budget invites shortening; v2 has no length target."""
        brief = v2_brief()
        assert "time_available_minutes" not in brief
        text = json.dumps(brief)
        assert "time_available" not in text
        assert "word_count" not in text
        assert "word_budget" not in text

    def test_schema_defines_no_length_field(self):
        from humanvoice.schemas import get_registry

        schema = json.dumps(get_registry().schema("HumanizationBrief"))
        for forbidden in ("word_count", "word_budget", "target_words",
                          "max_words", "time_available_minutes"):
            assert forbidden not in schema, forbidden


class TestLegacyPath:
    def test_v1_brief_still_validates_through_the_legacy_check(self):
        assert _validate_v1_brief(v1_brief())[0] is True

    def test_v1_brief_routes_to_the_legacy_check(self):
        assert _validate_brief(v1_brief())[0] is True

    def test_incomplete_v1_brief_fails(self):
        brief = v1_brief()
        del brief["success_criteria"]
        ok, errors = _validate_brief(brief)
        assert ok is False
        assert any("success_criteria" in error for error in errors)

    def test_v1_brief_cannot_pass_as_a_v2_brief(self):
        """A v1 brief lacks genre, voice, boundary, and authorization."""
        assessment = assess_brief(v1_brief())
        assert not assessment.valid

    def test_nonpositive_reading_time_still_rejected_in_v1(self):
        ok, errors = _validate_brief(v1_brief(time_available_minutes=0))
        assert ok is False
        assert any("positive" in error for error in errors)
