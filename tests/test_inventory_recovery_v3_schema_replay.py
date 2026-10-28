"""Bound schema-definition reuse while preserving all record and contract checks."""

import shutil
from contextvars import Context
from copy import deepcopy
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator, SchemaError
from referencing import Resource
from test_active_session_runtime import codex, invoke, prospective

from humanvoice import codex_runtime, inference_settings, schemas
from humanvoice.artifacts import digest, read_json, write_json
from tools import active_session_runtime as active
from tools.ensemble_closure_contract import AllocationLedger
from tools.inventory_recovery_v3 import schema_replay

__all__ = ["codex"]


def counter(monkeypatch):
    checks = []
    native = Draft202012Validator.check_schema

    def check(cls, schema, **keywords):
        checks.append(deepcopy(schema))
        return native(schema, **keywords)

    monkeypatch.setattr(Draft202012Validator, "check_schema", classmethod(check))
    return checks


def bindings():
    return (active.schema_for, active.schema_template, Draft202012Validator.check_schema,
            codex_runtime.launch, codex_runtime.command, schemas.SchemaRegistry.validate,
            AllocationLedger.reserve, inference_settings.selected_profile)


def test_identical_definition_checked_once_and_returned_objects_detached(codex, monkeypatch):
    profile = prospective(codex, monkeypatch)
    registry = schemas.get_registry()
    registry.schema("RuntimeManifest")
    checks = counter(monkeypatch)
    before = bindings()
    with schema_replay.scope() as cache:
        first = active.schema_for(registry, profile)
        first["title"] = "caller mutation"
        for _ in range(20):
            assert "caller mutation" != active.schema_for(registry, profile).get("title")
        assert len(checks) == 1
        assert len(cache.entries) == 1
    assert bindings() == before
    assert not cache.entries and cache.bytes == 0
    with schema_replay.scope():
        active.schema_for(registry, profile)
    assert len(checks) == 2


@pytest.mark.parametrize("fault", ["base", "base_contract", "template", "template_contract"])
def test_contract_drift_rejected_after_warm_cache(codex, monkeypatch, fault):
    profile = prospective(codex, monkeypatch)
    registry = schemas.SchemaRegistry()
    base = registry.schema("RuntimeManifest")
    with schema_replay.scope():
        active.schema_for(registry, profile)
        if fault == "base":
            base["title"] = "changed"
        elif fault == "template":
            original = active.schema_template
            monkeypatch.setattr(active, "schema_template",
                                lambda *args: {**original(*args), "title": "changed"})
        else:
            key = "base_schema_sha256" if fault == "base_contract" else "schema_template_sha256"
            profile["runtime"]["active_session"]["receipt_contract"][key] = "foreign"
        with pytest.raises(ValueError, match="frozen contract"):
            active.schema_for(registry, profile)


@pytest.mark.parametrize("field", ["model", "sampling", "endpoint", "responses", "identity"])
def test_changed_construction_inputs_rebuild_definition(codex, monkeypatch, field):
    profile = prospective(codex, monkeypatch)
    registry = schemas.get_registry()
    registry.schema("RuntimeManifest")
    checks = counter(monkeypatch)
    with schema_replay.scope():
        old = active.schema_for(registry, profile)
        changed = deepcopy(profile)
        if field == "model":
            changed["model"]["version_string"] = "different"
        elif field == "sampling":
            changed["sampling"]["reasoning_effort"] = "xhigh"
        elif field == "identity":
            changed["calibration"] = {"fixture": "new identity"}
        else:
            changed["runtime"]["endpoint" if field == "endpoint" else "responses_url"] += "/new"
        changed["runtime"]["active_session"]["receipt_contract"]["schema_template_sha256"] = (
            digest(active.schema_template(registry, changed)))
        new = active.schema_for(registry, changed)
        assert new != old
        assert len(checks) == 2


def test_invalid_schema_failures_never_cached(monkeypatch):
    checks = counter(monkeypatch)
    cache = schema_replay.DefinitionChecks()
    for _ in range(2):
        with pytest.raises(SchemaError):
            cache.check_schema({"type": "not-a-json-type"})
    assert len(checks) == 2 and not cache.entries


def test_changed_on_disk_schema_is_not_hidden_by_warm_definition(codex, monkeypatch, tmp_path):
    profile = prospective(codex, monkeypatch)
    root = tmp_path / "schemas"
    shutil.copytree(schemas.SCHEMA_ROOT, root)
    registry = schemas.SchemaRegistry(root, root / "record_catalog.json")
    with schema_replay.scope():
        active.schema_for(registry, profile)
        path = registry.schema_path("RuntimeManifest")
        changed = read_json(path)
        changed["title"] = "replaced file"
        write_json(path, changed)
        fresh = schemas.SchemaRegistry(root, root / "record_catalog.json")
        with pytest.raises(ValueError, match="frozen contract"):
            active.schema_for(fresh, profile)


def test_changed_template_with_updated_contract_still_checks_schema(codex, monkeypatch):
    profile = prospective(codex, monkeypatch)
    registry = schemas.get_registry()
    registry.schema("RuntimeManifest")
    checks = counter(monkeypatch)
    original = active.schema_template
    with schema_replay.scope():
        active.schema_for(registry, profile)
        monkeypatch.setattr(active, "schema_template",
                            lambda *args: {**original(*args), "type": "invalid"})
        profile["runtime"]["active_session"]["receipt_contract"]["schema_template_sha256"] = (
            digest(active.schema_template(registry, profile)))
        with pytest.raises(SchemaError):
            active.schema_for(registry, profile)
    assert len(checks) == 2


def test_nested_exception_restores_scope_and_shared_bindings(codex, monkeypatch):
    profile = prospective(codex, monkeypatch)
    registry = schemas.get_registry()
    registry.schema("RuntimeManifest")
    checks = counter(monkeypatch)
    before = bindings()
    with pytest.raises(RuntimeError, match="unwind"), schema_replay.scope() as outer:
        active.schema_for(registry, profile)
        scoped = bindings()
        with pytest.raises(ValueError, match="nested"), schema_replay.scope() as inner:
            assert inner is outer
            active.schema_for(registry, profile)
            raise ValueError("nested")
        assert bindings() == scoped
        assert len(checks) == 1
        raise RuntimeError("unwind")
    assert bindings() == before and schema_replay.ACTIVE.get() is None
    assert not outer.entries


def test_other_context_gets_no_operation_cache(codex, monkeypatch):
    profile = prospective(codex, monkeypatch)
    registry = schemas.get_registry()
    registry.schema("RuntimeManifest")
    checks = counter(monkeypatch)
    with schema_replay.scope():
        active.schema_for(registry, profile)
        Context().run(active.schema_for, registry, profile)
        Context().run(active.schema_for, registry, profile)
        active.schema_for(registry, profile)
    assert len(checks) == 3


@pytest.mark.parametrize("change", ["checker", "meta", "validator", "format", "registry"])
def test_checker_construction_changes_invalidate_cache(monkeypatch, change):
    checks = counter(monkeypatch)
    cache = schema_replay.DefinitionChecks()
    schema = {"type": "string"}
    cache.check_schema(schema)
    if change == "checker":
        original = Draft202012Validator.check_schema

        def reject(cls, schema):
            raise ValueError("new checker")

        monkeypatch.setattr(Draft202012Validator, "check_schema", classmethod(reject))
        with pytest.raises(ValueError, match="new checker"):
            cache.check_schema(schema)
        assert not cache.entries
        monkeypatch.setattr(Draft202012Validator, "check_schema", original)
        cache.check_schema(schema)
    elif change == "meta":
        monkeypatch.setattr(Draft202012Validator, "META_SCHEMA",
                            {**Draft202012Validator.META_SCHEMA, "title": "changed"})
        cache.check_schema(schema)
    elif change == "validator":
        original = Draft202012Validator.VALIDATORS["type"]
        monkeypatch.setitem(Draft202012Validator.VALIDATORS, "type", lambda *args: original(*args))
        cache.check_schema(schema)
    elif change == "format":
        monkeypatch.setitem(Draft202012Validator.FORMAT_CHECKER.checkers, "test-only", (lambda x: True, ()))
        cache.check_schema(schema)
    else:
        native = schema_replay.validators.validator_for
        monkeypatch.setattr(schema_replay.validators, "validator_for", lambda *args, **kw: native(*args, **kw))
        cache.check_schema(schema)
    assert len(checks) == 2


@pytest.mark.parametrize("limit", ["entries", "bytes"])
def test_bounded_eviction_rechecks_old_definitions(monkeypatch, limit):
    monkeypatch.setattr(schema_replay, "MAX_ENTRIES", 2)
    if limit == "bytes":
        monkeypatch.setattr(schema_replay, "MAX_BYTES", 40)
    checks = counter(monkeypatch)
    cache = schema_replay.DefinitionChecks()
    for name in ["string", "integer", "boolean", "string"]:
        cache.check_schema({"type": name})
        assert len(cache.entries) <= 2 and cache.bytes <= schema_replay.MAX_BYTES
    assert len(checks) == 4


def test_oversized_definition_not_retained(monkeypatch):
    monkeypatch.setattr(schema_replay, "MAX_BYTES", 1)
    checks = counter(monkeypatch)
    cache = schema_replay.DefinitionChecks()
    for _ in range(2):
        cache.check_schema({"type": "string"})
    assert len(checks) == 2 and not cache.entries


def test_all_native_record_checks_continue_after_warming(codex, monkeypatch):
    profile = prospective(codex, monkeypatch)
    before = bindings()
    with schema_replay.scope(), active.runtime(profile, live=True):
        _, response = invoke(codex)
        record = read_json(codex.snapshot / response.runtime_record["path"])
        registry = schemas.get_registry()
        assert registry.validate(record) == []
        for field, value in [("model_version_string", "foreign"), ("api_base_url", "http://elsewhere"),
                             ("input_tokens", -1), ("schema_version", "unknown")]:
            with pytest.raises(schemas.RecordValidationError):
                registry.validate({**record, field: value})
        with pytest.raises(schemas.RecordValidationError, match="expected record_type"):
            registry.validate(record, record_type="WrongType")
        assert registry.validate({**record, "input_tokens": -1}, raise_on_error=False)
        assert codex_runtime.validate_codex_record(codex.snapshot, response.runtime_record) == record
    assert bindings() == before


def test_tuple_template_drift_matches_native_rejection(codex, monkeypatch):
    profile = prospective(codex, monkeypatch)
    registry = schemas.get_registry()
    native = active.schema_for
    template = active.schema_template
    kind = [["object"]]
    monkeypatch.setattr(active, "schema_template", lambda *args: {**template(*args), "type": kind[0]})
    contract = profile["runtime"]["active_session"]["receipt_contract"]
    contract["schema_template_sha256"] = digest(active.schema_template(registry, profile))
    with schema_replay.scope():
        active.schema_for(registry, profile)
        kind[0] = ("object",)
        assert digest(active.schema_template(registry, profile)) == contract["schema_template_sha256"]
        with pytest.raises(SchemaError):
            native(registry, profile)
        with pytest.raises(SchemaError):
            active.schema_for(registry, profile)


def test_type_checker_drift_matches_native_rejection_and_recovers(monkeypatch):
    cache = schema_replay.DefinitionChecks()
    schema = {"type": "string"}
    cache.check_schema(schema)
    with monkeypatch.context() as patch:
        patch.setattr(Draft202012Validator, "TYPE_CHECKER",
                      Draft202012Validator.TYPE_CHECKER.redefine("object", lambda *args: False))
        with pytest.raises(SchemaError):
            Draft202012Validator.check_schema(schema)
        with pytest.raises(SchemaError):
            cache.check_schema(schema)
        assert not cache.entries
    cache.check_schema(schema)
    assert len(cache.entries) == 1


@pytest.mark.parametrize("change", ["resource", "constructor_registry", "anchor"])
def test_effective_registry_drift_matches_native_rejection(monkeypatch, change):
    cache = schema_replay.DefinitionChecks()
    schema = {"type": "string"}
    cache.check_schema(schema)
    constructor = Draft202012Validator.__init__
    registry = constructor.__kwdefaults__["registry"]
    uri = "https://json-schema.org/draft/2020-12/meta/validation"
    resource = registry[uri]
    changed = deepcopy(resource.contents)
    changed["properties"]["type"] = {"const": "integer"}
    with monkeypatch.context() as patch:
        if change == "resource":
            patch.setitem(resource.contents, "properties", changed["properties"])
        elif change == "constructor_registry":
            patch.setattr(constructor, "__kwdefaults__", {**constructor.__kwdefaults__,
                "registry": registry.with_resource(uri, Resource.from_contents(changed))})
        else:
            anchors = [anchor for (_uri, _name), anchor in registry._anchors.items() if _uri == uri]
            if not anchors:
                pytest.fail("Expected retained validation anchor")
            for anchor in anchors:
                patch.setitem(anchor.resource.contents, "properties", changed["properties"])
        with pytest.raises(SchemaError):
            Draft202012Validator.check_schema(schema)
        with pytest.raises(SchemaError):
            cache.check_schema(schema)
        assert not cache.entries
    cache.check_schema(schema)
    assert len(cache.entries) == 1


@pytest.mark.parametrize("exit_owner_first", [False, True])
@pytest.mark.parametrize("exception", [False, True])
def test_independent_overlap_rejected_without_poisoning_later_scope(codex, monkeypatch, exit_owner_first, exception):
    profile = prospective(codex, monkeypatch)
    registry = schemas.get_registry()
    registry.schema("RuntimeManifest")
    native = bindings()
    checks = counter(monkeypatch)
    counted = bindings()
    a, b = Context(), Context()
    first, second = schema_replay.scope(), schema_replay.scope()
    outer = a.run(first.__enter__)
    a.run(active.schema_for, registry, profile)
    with pytest.raises(RuntimeError, match="cannot overlap"):
        b.run(second.__enter__)
    assert bindings() != counted
    error = (ValueError, ValueError("unwind"), None) if exception else (None, None, None)
    order = [(a, first, error), (b, second, (None, None, None))]
    for context, manager, arguments in order if exit_owner_first else reversed(order):
        context.run(manager.__exit__, *arguments)
    assert bindings() == counted and schema_replay.INSTALLATION is None
    assert not outer.entries and a.run(schema_replay.ACTIVE.get) is None
    with schema_replay.scope():
        for _ in range(3):
            active.schema_for(registry, profile)
    assert len(checks) == 2 and active.schema_for is native[0]


def test_mutable_legacy_resolver_default_always_uses_native_check(monkeypatch):
    state = {"definition": {}}
    resolver = SimpleNamespace(resolve=lambda ref: ("", state["definition"]),
                               push_scope=lambda value: None, pop_scope=lambda: None)
    cache = schema_replay.DefinitionChecks()
    schema = {"type": "string"}
    cache.check_schema(schema)
    with monkeypatch.context() as patch:
        patch.setattr(Draft202012Validator.__init__, "__defaults__", (resolver, None))
        cache.check_schema(schema)
        assert not cache.entries
        state["definition"] = False
        with pytest.raises(SchemaError):
            Draft202012Validator.check_schema(schema)
        with pytest.raises(SchemaError):
            cache.check_schema(schema)
        assert not cache.entries
    cache.check_schema(schema)
    assert len(cache.entries) == 1


def test_keyword_resolver_default_always_uses_native_check(monkeypatch):
    constructor = Draft202012Validator.__init__
    resolver = Draft202012Validator(Draft202012Validator.META_SCHEMA)._resolver
    cache = schema_replay.DefinitionChecks()
    checks = counter(monkeypatch)
    schema = {"type": "string"}
    with monkeypatch.context() as patch:
        patch.setattr(constructor, "__kwdefaults__", {**constructor.__kwdefaults__, "_resolver": resolver})
        cache.check_schema(schema)
        cache.check_schema(schema)
        assert len(checks) == 2 and not cache.entries
    cache.check_schema(schema)
    cache.check_schema(schema)
    assert len(checks) == 3 and len(cache.entries) == 1
