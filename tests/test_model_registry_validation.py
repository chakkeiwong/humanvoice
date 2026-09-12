"""Model responses on the v2 path validate through the shared registry (WP-V2-1).

v1 kept its own inline copies of record shapes in `model.py`. Those copies were
looser than the on-disk schemas, so a model response could satisfy the runtime
and still be an invalid record — the runtime was the weakest validator in the
system and also the only one the model ever met.

These tests pin the replacement: `invoke(record_type=...)` checks the response
against the same file every other consumer validates against, a mismatch is an
abstention rather than a partial acceptance, and a model cannot substitute a
different record type than the one requested.
"""

import json
from unittest.mock import patch

import pytest

from humanvoice.model import ModelAdapter, ModelConfig
from humanvoice.schemas import RecordValidationError, get_registry


HASH = "a" * 64


def adapter():
    return ModelAdapter(ModelConfig(model_version="test-model"), mock_mode=True)


def valid_span_record():
    return {
        "record_type": "SourceSpan",
        "schema_version": "HV-SCHEMA-2.0",
        "record_id": "span-1",
        "run_id": "run-001",
        "created_at": "2026-09-11T00:00:00Z",
        "snapshot_id": "snapshot-001",
        "source_hash": HASH,
        "source_file": "main.tex",
        "byte_start": 0,
        "byte_end": 10,
        "line_start": 1,
        "line_end": 1,
        "exact_text_hash": HASH,
        "span_kind": "prose",
        "reader_facing": True,
        "structural_parent_id": None,
        "coverage_disposition": "unresolved",
        "concept_ids": [],
        "protected_object_ids": [],
        "scaffolding_disposition_ids": [],
    }


def respond(payload):
    """Patch the adapter's response so only validation is under test."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return patch.object(ModelAdapter, "_mock_response", return_value=text)


class TestRegistryValidation:
    def test_valid_record_passes(self):
        with respond(valid_span_record()):
            response = adapter().invoke("prompt", record_type="SourceSpan")
        assert response.abstention is None
        assert json.loads(response.text)["record_id"] == "span-1"

    def test_schema_violation_becomes_an_abstention(self):
        record = valid_span_record()
        del record["exact_text_hash"]
        with respond(record):
            response = adapter().invoke("prompt", record_type="SourceSpan")
        assert response.abstention is not None
        assert "SourceSpan validation" in response.abstention
        assert response.text == ""

    def test_semantic_violation_becomes_an_abstention(self):
        """An inverted byte range is schema-shaped but semantically invalid."""
        record = valid_span_record()
        record["byte_start"], record["byte_end"] = 10, 0
        with respond(record):
            response = adapter().invoke("prompt", record_type="SourceSpan")
        assert response.abstention is not None

    def test_wrong_record_type_is_rejected(self):
        """A model may not answer with a different record than requested."""
        with respond(valid_span_record()):
            response = adapter().invoke("prompt", record_type="SourceConcept")
        assert response.abstention is not None
        assert "expected record_type SourceConcept" in response.abstention

    def test_malformed_json_becomes_an_abstention(self):
        with respond("{not json"):
            response = adapter().invoke("prompt", record_type="SourceSpan")
        assert response.abstention is not None
        assert "not valid JSON" in response.abstention

    def test_legacy_record_cannot_satisfy_a_v2_call(self):
        legacy = {
            "record_type": "AuthoringBrief",
            "schema_version": "HV-SCHEMA-1.1",
            "record_id": "brief-1",
        }
        with respond(legacy):
            response = adapter().invoke("prompt", record_type="AuthoringBrief")
        assert response.abstention is not None
        assert "legacy_v1" in response.abstention

    def test_abstention_preserves_token_accounting(self):
        """A rejected response still cost tokens; the record must show it."""
        record = valid_span_record()
        del record["span_kind"]
        with respond(record):
            response = adapter().invoke("prompt", record_type="SourceSpan")
        assert response.abstention is not None
        assert response.model_version == "test-model"
        assert response.prompt_hash


class TestExpectedTypeCheck:
    def test_registry_rejects_mismatched_expected_type(self):
        registry = get_registry()
        errors = registry.validate(
            valid_span_record(), record_type="SourceConcept", raise_on_error=False
        )
        assert any("expected record_type SourceConcept" in error for error in errors)

    def test_registry_accepts_matching_expected_type(self):
        registry = get_registry()
        assert (
            registry.validate(
                valid_span_record(), record_type="SourceSpan", raise_on_error=False
            )
            == []
        )

    def test_expected_type_check_raises_when_asked(self):
        with pytest.raises(RecordValidationError):
            get_registry().validate(valid_span_record(), record_type="Revision")

    def test_omitting_expected_type_keeps_prior_behavior(self):
        assert get_registry().validate(valid_span_record(), raise_on_error=False) == []


class TestLegacySchemasMoved:
    def test_model_no_longer_defines_the_v1_schemas(self):
        """They must live in legacy_schemas, not be re-declared in model.py."""
        import inspect

        import humanvoice.model as model

        source = inspect.getsource(model)
        assert "PLAN_SCHEMA = {" not in source
        assert "DRAFT_SCHEMA = {" not in source
        assert "REPAIR_SCHEMA = {" not in source

    def test_v1_callers_still_resolve_the_names(self):
        from humanvoice.model import DRAFT_SCHEMA, PLAN_SCHEMA, REPAIR_SCHEMA

        assert PLAN_SCHEMA["required"] == ["blueprint"]
        assert DRAFT_SCHEMA["required"] == ["draft"]
        assert REPAIR_SCHEMA["required"] == ["repair"]

    def test_legacy_module_is_marked_audit_only(self):
        import humanvoice.legacy_schemas as legacy

        assert "audit" in (legacy.__doc__ or "").lower()
        assert "legacy_v1" in (legacy.__doc__ or "")

    def test_legacy_word_count_requirement_is_documented_as_superseded(self):
        """v2 has no length target; the v1 schema's word_count must not migrate."""
        import humanvoice.legacy_schemas as legacy

        assert "word_count" in (legacy.__doc__ or "")
        assert "word_count" in json.dumps(legacy.DRAFT_SCHEMA)
        # No current v2 record may require a word count.
        registry = get_registry()
        for record_type in sorted(registry.current_record_types):
            schema = json.dumps(registry.schema(record_type))
            assert "word_count" not in schema, record_type
