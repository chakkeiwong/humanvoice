"""Model-response schemas for the superseded v1 authoring path.

These three schemas constrained the v1 `plan -> draft -> repair` model calls.
They lived in `model.py`, which meant the runtime carried its own weaker copies
of record shapes that `schemas/` also defined — the duplication that let a
draft validate against a permissive inline schema while failing the on-disk
one.

They are kept here, unchanged, for two reasons: the v1 commands still run under
the legacy namespace during migration, and v1 run records must stay
reproducible for audit. They are `legacy_v1` in exactly the sense the record
catalogue means:

    Readable for audit only. Cannot satisfy a v2 gate.

The v2 path does not import this module. Model responses on the v2 path are
validated through the shared registry in `humanvoice.schemas`, against the same
on-disk schema a record is checked against everywhere else. Note in particular
that DRAFT_SCHEMA requires `word_count`: v2 has no prose length target, and
nothing on the v2 path may reintroduce one.
"""

from __future__ import annotations

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "blueprint": {
            "type": "object",
            "properties": {
                # Legacy format: flat sections array
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "purpose": {"type": "string"},
                            "evidence_needed": {"type": "array", "items": {"type": "string"}},
                            "word_budget": {"type": "number"},
                            "source_file": {"type": "string"},
                            "source_start_line": {"type": "integer", "minimum": 1},
                            "source_end_line": {"type": "integer", "minimum": 1}
                        },
                        "required": ["title", "purpose"]
                    }
                },
                # New format: chapters with subsections
                "chapters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "purpose": {"type": "string"},
                            "subsections": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "purpose": {"type": "string"},
                                        "evidence_needed": {"type": "array", "items": {"type": "string"}},
                                        "word_budget": {"type": "number"},
                                        "source_file": {"type": "string"},
                                        "source_start_line": {"type": "integer", "minimum": 1},
                                        "source_end_line": {"type": "integer", "minimum": 1}
                                    },
                                    "required": ["title", "purpose"]
                                }
                            }
                        },
                        "required": ["title", "purpose", "subsections"]
                    }
                },
                "total_words": {"type": "number"},
                "abstention": {"type": "string"}
            },
            # Either provide total_words (normal case) or abstention (insufficient evidence)
            "anyOf": [
                {"required": ["total_words"]},
                {"required": ["abstention"]}
            ]
        }
    },
    "required": ["blueprint"]
}

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "draft": {
            "type": "object",
            "properties": {
                "latex": {"type": "string"},
                "word_count": {"type": "number"},
                "citations_needed": {"type": "array", "items": {"type": "string"}},
                "abstention": {"type": "string"}
            },
            "required": ["latex", "word_count"],
            # Either provide latex content (normal case) or abstention (insufficient evidence)
            "anyOf": [
                {"required": ["latex"]},
                {"required": ["abstention"]}
            ]
        }
    },
    "required": ["draft"]
}

REPAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "repair": {
            "type": "object",
            "properties": {
                "changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "finding_id": {"type": "string"},
                            "original": {"type": "string"},
                            "revised": {"type": "string"},
                            "rationale": {"type": "string"}
                        },
                        "required": ["finding_id", "original", "revised", "rationale"]
                    }
                },
                "unaddressed": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "finding_id": {"type": "string"},
                            "reason": {"type": "string"}
                        },
                        "required": ["finding_id", "reason"]
                    }
                },
                "abstention": {"type": "string"}
            },
            "required": ["changes"]
        }
    },
    "required": ["repair"]
}
