"""One validator for the humanization brief.

Brief validation was split across the runtime and the schema directory, and the
two disagreed about what a brief is. `init_command._validate_brief` checked five
flat v1 fields (`reader_role`, `decision_type`, `time_available_minutes`,
`prior_knowledge`, `success_criteria`) while `schemas/humanization-brief.schema.json`
defines a structured v2 record with twenty. A brief could pass the command and
fail the schema, or the reverse.

This module makes the on-disk schema the only definition. Two things are
checked, and they are deliberately separate:

* **Validity** — does the brief satisfy its schema? Answered by the shared
  registry, the same way every other record is answered.
* **Critical blanks** — is a field present and schema-valid but empty of the
  information a rewrite actually needs? `reader.prior_knowledge: []` is a legal
  array and an unanswered question. Those block rewriting rather than failing
  validation, because the fix is a human answering them, not a corrected file.

`time_available_minutes` is gone and is not reinstated. A reading-time budget
invites shortening the document to fit it, and v2 has no length target. What
the reader knows and what decision they face determine how much explanation is
owed; how many minutes they have does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from humanvoice.schemas import get_registry

RECORD_TYPE = "HumanizationBrief"

# Fields that must carry real content before any rewrite call. Each is a
# question only a person can answer, and a wrong guess propagates into every
# rewritten passage.
CRITICAL_PATHS: tuple[tuple[str, str], ...] = (
    ("reader.role", "who will read the revision"),
    ("reader.prior_knowledge", "what the reader already knows"),
    ("reader.reading_context", "the situation the reader reads in"),
    ("purpose", "what the revision is for"),
    ("genre", "the genre whose conventions apply"),
    ("evidence_boundary", "which evidence the rewrite may use"),
    ("protected_object_policy", "which objects may not change silently"),
    ("voice_constraints.register", "the register the genre requires"),
    ("voice_constraints.person", "the grammatical person the genre requires"),
    ("authorizing_action.actor", "who authorized changing the text"),
    ("authorizing_action.action", "the invocation that authorized it"),
    ("policy_sources", "the reader-facing policies in force"),
)


@dataclass
class BriefAssessment:
    """The outcome of checking one brief.

    `errors` are schema failures: the file is not a brief. `critical_blanks`
    are unanswered questions: the file is a brief, and it is not yet usable.
    Keeping them apart matters because they need different responses from
    different people.
    """

    valid: bool
    errors: list[str] = field(default_factory=list)
    critical_blanks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ready_for_rewrite(self) -> bool:
        """True only when the brief is valid and every critical field answered."""
        return self.valid and not self.critical_blanks

    def summary(self) -> str:
        if not self.valid:
            return f"brief is invalid: {len(self.errors)} schema error(s)"
        if self.critical_blanks:
            return f"brief is valid with {len(self.critical_blanks)} unanswered field(s)"
        return "brief is complete"


def _resolve(brief: Mapping[str, Any], dotted: str) -> Any:
    value: Any = brief
    for part in dotted.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _is_blank(value: Any) -> bool:
    """True when a schema-valid value carries no usable information.

    A placeholder string counts as blank. v1 briefs shipped with "TBD" and
    "unknown" in required fields, which satisfied a non-empty check and told a
    rewrite nothing.
    """
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        return stripped.lower() in {
            "tbd",
            "todo",
            "unknown",
            "n/a",
            "na",
            "none",
            "pending",
            "?",
        }
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def assess_brief(brief: Mapping[str, Any]) -> BriefAssessment:
    """Validate a brief against its schema and report unanswered fields."""
    errors = get_registry().validate(
        brief, record_type=RECORD_TYPE, raise_on_error=False
    )
    if errors:
        return BriefAssessment(valid=False, errors=errors)

    blanks: list[str] = []
    for dotted, description in CRITICAL_PATHS:
        if _is_blank(_resolve(brief, dotted)):
            blanks.append(f"{dotted} is unanswered: {description}")

    warnings: list[str] = []
    if _is_blank(brief.get("exemplars")):
        # Not critical: pacing diagnostics degrade to reporting rather than
        # comparison, which is a weaker check but not an unsafe one.
        warnings.append(
            "exemplars is empty: pacing diagnostics will report patterns "
            "without an exemplar comparison"
        )
    if _is_blank(brief.get("known_vocabulary")):
        warnings.append(
            "known_vocabulary is empty: every term will be treated as "
            "needing introduction for this reader"
        )
    unresolved = brief.get("unresolved_assumptions") or []
    if unresolved:
        warnings.append(
            f"{len(unresolved)} unresolved assumption(s) carried forward; "
            "the owner has confirmed each is safe"
        )

    remote = brief.get("remote_inference") or {}
    if remote.get("authorized") and _is_blank(remote.get("approved_by")):
        # Authorized transmission with no named approver is not a warning.
        blanks.append(
            "remote_inference.approved_by is unanswered: remote inference is "
            "authorized but nobody is named as approving it"
        )

    return BriefAssessment(
        valid=True, errors=[], critical_blanks=blanks, warnings=warnings
    )


def validate_brief(brief: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Back-compatible shape for callers expecting `(ok, messages)`.

    Returns False when the brief is invalid *or* has critical blanks, since
    neither state may proceed to a rewrite.
    """
    assessment = assess_brief(brief)
    return assessment.ready_for_rewrite, assessment.errors + assessment.critical_blanks
