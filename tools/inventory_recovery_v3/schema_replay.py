"""Reuse successful schema-definition checks within one prospective operation."""

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from math import isfinite
from threading import RLock, get_ident
from types import FunctionType, SimpleNamespace

from jsonschema import validators

from humanvoice.schemas import canonical_json_bytes
from tools import active_session_runtime as active

ACTIVE = ContextVar("inventory_document_schema_checks", default=None)
MAX_ENTRIES = 64
MAX_BYTES = 4 * 1024 * 1024
MAX_ENV_BYTES = 4 * 1024 * 1024
INSTALLATION = None
INSTALL_LOCK = RLock()


def json_key(value):
    """Only JSON-native values can share a serialized native-validation key."""
    def valid(item):
        kind = type(item)
        if kind in (str, int, bool, type(None)):
            return True
        if kind is float:
            return isfinite(item)
        if kind is list:
            return all(valid(child) for child in item)
        if kind is dict:
            return all(type(key) is str and valid(child) for key, child in item.items())
        return False

    try:
        return canonical_json_bytes(value) if valid(value) else None
    except (RecursionError, TypeError, ValueError):
        return None


def checker_identity(checker):
    function = getattr(checker, "__func__", checker)
    return (getattr(checker, "__self__", None), function,
            getattr(function, "__code__", None))


def registry_state(registry):
    """Snapshot resource contents, including already-crawled anchor resources."""
    resources = []
    for uri, resource in sorted(registry.items()):
        content = json_key(resource.contents)
        if content is None:
            raise ValueError("Unsupported schema registry resource")
        resources.append((uri, resource._specification, content))
    anchors = []
    for key, anchor in sorted(registry._anchors.items()):
        content = json_key(anchor.resource.contents)
        if content is None:
            raise ValueError("Unsupported schema registry anchor")
        anchors.append((key, type(anchor), anchor.name, anchor.resource._specification, content))
    if sum(len(row[-1]) for row in [*resources, *anchors]) > MAX_ENV_BYTES:
        raise ValueError("Schema registry exceeds bounded reuse scope")
    return (type(registry), tuple(resources), tuple(anchors),
            tuple(sorted(registry._uncrawled)), checker_identity(registry._retrieve))


def definition_environment(kind):
    """Bind the checker and its actual meta-validation construction inputs."""
    selected = validators.validator_for(kind.META_SCHEMA, default=kind)
    defaults = selected.__init__.__kwdefaults__
    positional = selected.__init__.__defaults__
    if positional != (None, None) or defaults.get("_resolver") is not None:
        raise ValueError("Custom schema resolver requires native checking")
    post_globals = selected.__attrs_post_init__.__globals__
    observed = {}

    def snapshot(registry):
        if id(registry) not in observed:
            observed[id(registry)] = registry_state(registry)
        return observed[id(registry)]

    registry = snapshot(defaults["registry"])
    specification_registry = snapshot(post_globals["SPECIFICATIONS"])
    remote_registry = snapshot(post_globals["_REMOTE_WARNING_REGISTRY"])
    meta = json_key(kind.META_SCHEMA)
    if meta is None or len(meta) > MAX_ENV_BYTES:
        raise ValueError("Unsupported meta-schema representation")
    return (kind, checker_identity(kind.check_schema), validators.validator_for,
            meta, selected, registry, specification_registry, remote_registry,
            selected.__init__, positional,
            selected.__attrs_post_init__, selected.TYPE_CHECKER,
            selected.iter_errors, selected.descend, selected.ID_OF, selected.evolve,
            selected.is_type, selected._validate_reference,
            tuple(selected.VALIDATORS.items()), selected.FORMAT_CHECKER,
            tuple(selected.FORMAT_CHECKER.checkers.items()),
            tuple(validators._META_SCHEMAS.items()))


class DefinitionChecks:
    def __init__(self):
        self.entries = OrderedDict()
        self.bytes = 0
        self.environment = None
        self.thread = get_ident()

    def check_schema(self, schema):
        kind = active.Draft202012Validator
        key = json_key(schema)
        if key is None or get_ident() != self.thread:
            return kind.check_schema(schema)
        try:
            environment = definition_environment(kind)
        except (AttributeError, KeyError, TypeError, ValueError):
            self.clear()
            return kind.check_schema(schema)
        if environment != self.environment:
            self.clear()
            self.environment = environment
        if key in self.entries:
            self.entries.move_to_end(key)
            return
        kind.check_schema(schema)
        # Failed checks never enter the cache; large definitions remain uncached.
        if len(key) > MAX_BYTES:
            return
        while self.entries and (len(self.entries) >= MAX_ENTRIES or self.bytes + len(key) > MAX_BYTES):
            old, _ = self.entries.popitem(last=False)
            self.bytes -= len(old)
        self.entries[key] = True
        self.bytes += len(key)

    def clear(self):
        self.entries.clear()
        self.bytes = 0
        self.environment = None


@contextmanager
def scope():
    """Keep native schema construction/contract checks and every record check."""
    global INSTALLATION

    retained = ACTIVE.get()
    if retained is not None:
        if retained is not INSTALLATION or retained.thread != get_ident():
            raise RuntimeError("Schema replay scope belongs to another execution context")
        yield retained
        return
    checks = DefinitionChecks()

    def schema_for(registry, profile):
        if ACTIVE.get() is not checks:
            return original(registry, profile)
        # Copy current globals on every call: changed template/digest bindings
        # must still affect construction. Only the definition checker is private.
        namespace = dict(original.__globals__)
        namespace["Draft202012Validator"] = SimpleNamespace(check_schema=checks.check_schema)
        build = FunctionType(original.__code__, namespace, original.__name__,
                             original.__defaults__, original.__closure__)
        build.__kwdefaults__ = original.__kwdefaults__
        return build(registry, profile)

    with INSTALL_LOCK:
        if INSTALLATION is not None:
            raise RuntimeError("Independent schema replay operations cannot overlap")
        original = active.schema_for
        token = ACTIVE.set(checks)
        INSTALLATION = checks
        active.schema_for = schema_for
    try:
        yield checks
    finally:
        with INSTALL_LOCK:
            active.schema_for = original
            ACTIVE.reset(token)
            INSTALLATION = None
            checks.clear()
