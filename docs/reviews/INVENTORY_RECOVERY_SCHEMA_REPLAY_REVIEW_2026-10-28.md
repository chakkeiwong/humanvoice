# Schema replay repair — bounded findings review

## Final residual closure — 28 October 2026

**R1 CLOSED; R2 CLOSED; R3 CLOSED; R4 CLOSED. No remaining findings within
the requested R3 residual and R1/R2/R4 interaction review.**

Final reviewed helper SHA-256:
bb23d6d9a319f2498f40d58c5faa6f3004d6d5284baed8087f7e9f3550a61f91.
Final reviewed tests SHA-256:
0a2f6a1ec42cd278bc139d8c378fb57dfe73f05fab058f290710bd59929dc2c4.

At helper lines 72–75, the positional constructor defaults must now equal
(None, None), and the keyword-only _resolver must remain None. Unsupported
defaults reach the native checker through the existing clear-and-fallback path
at lines 113–117. The former mutable legacy resolver counterexample no longer
retains successful checks or bypasses subsequent native rejection.

The inspector directly invoked the following six targeted regression cases in
an isolated python -B process, with MonkeyPatch cleanup; all passed:

- Mutable legacy resolver default: clears a previously warm cache, retains no
  entries under the custom resolver, matches native SchemaError after reference
  results change, and restores caching after the default is restored.
- Keyword-only resolver default: two calls both reach native checking with no
  entries retained; restoration produces one native call followed by a cache hit.
- TYPE_CHECKER drift: preserves native rejection, invalidation, and recovery.
- Registry resource, constructor-registry, and anchor-content drift: all three
  preserve native rejection and recovery.

The keyword resolver test now roots its actual resolver at META_SCHEMA (test
line 374). The earlier empty-root fixture failed native resolution of meta/core
and was corrected by the coordinator before this successful verification.

An additional isolated in-memory probe passed with a custom legacy resolver
installed before the first call inside nested replay scopes. It verified no
retention, native/scoped rejection after resolver mutation, recovery within the
same outer scope after restoration, and unchanged rejection of a same-digest
list-to-tuple template mutation. Independent-context entry remained rejected
before binding changes; outer exit restored the exact native builder and cleared
scope/cache state; the next operation cached normally. These checks found no
regression in the previously closed R1, R2, or R4 behaviors.

**Closure boundary:** This closes the code-review findings. The coordinator
reports the corrected integration run completed: 115 passed in 14.15 seconds
(35 dedicated plus 80 adjacent), with 16 workers; Ruff passes. This integration
result is coordinator-reported, separate from the inspector's targeted checks.
The final exact executor/oversized repeat-and-accounting gate within the
unchanged 1800-second limit remains execution evidence to obtain. No R1–R4
review finding blocks that gate. No long suite, provider call, executor action,
source/test edit, or ownership audit was performed by this inspector. Only this
findings file was edited. Historical findings below are retained for traceability
and are superseded by this final disposition.

## Earlier follow-up disposition — historical

**Historical status: R1 CLOSED; R2 CLOSED; R3 OPEN; R4 CLOSED. Superseded by
final closure above.**
One inspector; follow-up confined to the repaired helper/tests and original
findings. Only this review file changed. No provider calls, long test suite,
source/test edits, executor actions, or ownership review were performed.

Follow-up helper SHA-256:
096da54616a953b962a0426288c1a68cf8c135369a5977a73adb59cbf340fdc4.
Follow-up tests SHA-256:
c457b4a0c795da2f427aa380ebcd4af70ebd74ad059e562c5949b8e4dc2f1973.

The coordinator reports 33 dedicated cases passing in 15.48 seconds and Ruff
passing. This inspector independently ran short, isolated python -B probes:

- **R1 closed:** The real template list-to-tuple drift preserves the contract
  digest; both native and scoped builders now raise SchemaError. Exact-type
  JSON checks route the tuple to native validation. The new test at lines
  255–271 exercises the former failure with a native oracle.
- **R2 closed:** Replacing TYPE_CHECKER with an object-rejecting checker now
  raises SchemaError through both paths, clears entries, and resumes caching
  after restoration. The new test at lines 274–287 covers this behavior.
- **R3 original cases repaired:** Resource mutation, effective constructor
  registry replacement, and anchor-content mutation each now raise SchemaError
  through both paths; each cache recovers after restoration. The new tests at
  lines 290–319 cover these cases. The resolver-default residual below prevents
  closing R3 as a whole.
- **R4 closed:** Independent contexts are rejected before binding mutation.
  Both cleanup orders, normal/exceptional exits, exact original binding
  restoration, same-context nesting, and caching in the next operation passed.
  The four new cases at lines 322–347 cover the former failure.

### Historical R3 residual — CLOSED: Positional legacy resolver defaults remain cacheable

**Location:** tools/inventory_recovery_v3/schema_replay.py:72–74,91–92,120–122;
tests/test_inventory_recovery_v3_schema_replay.py:290–319.

The unsupported-resolver guard checks only the keyword-only _resolver default.
The installed validator also has a positional resolver default, stored in
__init__.__defaults__[0] and assigned to self._ref_resolver. Native reference
validation uses this legacy resolver when present. The environment stores the
resolver object in a tuple but does not snapshot its state or decline caching.
A mutable legacy resolver can therefore change reference results while every
captured environment component compares equal.

**Reproduction (isolated process; all temporary defaults restored):**

    from types import SimpleNamespace
    from jsonschema import Draft202012Validator as V
    from tools.inventory_recovery_v3 import schema_replay as replay

    state = {"definition": {}}
    resolver = SimpleNamespace(
        resolve=lambda ref: ("", state["definition"]),
        push_scope=lambda scope: None,
        pop_scope=lambda: None,
    )
    original = V.__init__.__defaults__
    try:
        V.__init__.__defaults__ = (resolver, None)
        cache = replay.DefinitionChecks()
        schema = {"type": "string"}
        cache.check_schema(schema)  # observed: one entry retained
        state["definition"] = False
        # Independently observed results, catching the native exception:
        # V.check_schema(schema)      -> SchemaError
        # cache.check_schema(schema)  -> accepted
    finally:
        V.__init__.__defaults__ = original

**Required closure:** Treat any effective non-None positional resolver default
as unsupported and use native checking, as already done for keyword _resolver,
or snapshot its effective semantics safely. Add a regression that installs the
legacy resolver before warming, mutates its reference result, and requires the
same rejection as native validation. For the fallback design, assert that no
entries are retained and that normal caching returns after restoration. Include
a keyword-only _resolver fallback assertion as well; the current new registry
tests cover neither resolver-default branch.

The coordinator reports the earlier executor stopped cleanly after six passes
in 305 seconds with a failed receipt retained and source/authority unchanged.
That report is not a final-source executor pass. After the residual repair,
rerun affected regressions and retain the previously required final-source
executor/oversized repeat-and-accounting gate within the unchanged 1800-second
limit; this inspector did not run that gate.

## Initial review history — superseded by follow-up disposition

The initial review below recorded four open findings against the earlier hashes.
Its locations, test counts, execution status, and closure requirements are
historical; the current status is stated above. The coordinator then reported
24 dedicated tests, 104 combined tests in 15.00 seconds, and Ruff passing.

Reviewed cache source SHA-256:
66454b25050587061e96e056f526905e4d59fc0b45707283400910e1c878ba43.
Reviewed dedicated tests SHA-256:
16b31b4a2298ade8673a39b64fc1792c2a94f6f37e561e69cf73614bdb2f6b31.

## Initial R1 — CLOSED in follow-up: Canonical bytes can identify different native schema inputs

**Location:** tools/inventory_recovery_v3/schema_replay.py:49–52;
tests/test_inventory_recovery_v3_schema_replay.py:127–141.

canonical_json_bytes uses JSON serialization, which converts Python tuples
to arrays. After warming with {"type": ["object"]}, changing the schema
template to return {"type": ("object",)} leaves the canonical bytes and
template contract digest unchanged. Native Draft202012Validator.check_schema
rejects the tuple with SchemaError, but the cache returns success. This was
also reproduced through the real active.schema_for builder with a minimal
in-memory registry: the frozen native builder rejected the changed template;
the scoped builder accepted it and retained one entry. Thus copying the
current template binding does not by itself preserve native acceptance.

**Closure:** Reuse only inputs proven to have an unambiguous JSON-native
representation, or use a key that preserves distinctions relevant to native
validation. Unsupported representations should reach the native checker. Add
a warmed-template regression for list-to-tuple drift with unchanged contract
digests, asserting the same rejection as the uncached builder. The new invalid
template test changes canonical bytes and therefore misses this case.

## Initial R2 — CLOSED in follow-up: Type-checker changes do not invalidate successful checks

**Location:** tools/inventory_recovery_v3/schema_replay.py:24–34,45–52;
tests/test_inventory_recovery_v3_schema_replay.py:177–210.

The environment includes keyword validators and format checks but omits
selected.TYPE_CHECKER. Jsonschema's native is_type reads this class
attribute during meta-validation. In an isolated process, warm
{"type": "string"}, then replace Draft202012Validator.TYPE_CHECKER with
its redefine("object", ...) result that rejects objects. The native check
raises SchemaError; the cache accepts the same schema without rechecking.
Neither checker identity nor any currently captured environment member changes.

**Closure:** Include the effective type checker in invalidation, or explicitly
fall back to native checking when the supported validator configuration changes.
Add a warm-cache test that changes type-checker semantics to reject a previously
accepted schema and compares cached versus native results, then verifies recovery
after restoration. A call-count-only wrapper change is insufficient.

## Initial R3 — CLOSED after final residual repair: Registry fingerprint misses changes to effective meta-schema data

**Location:** tools/inventory_recovery_v3/schema_replay.py:27–34;
tests/test_inventory_recovery_v3_schema_replay.py:206–209.

The saved registry component is an attrs field's default object, not a snapshot
of referenced meta-schema contents or necessarily the constructor's current
default. Two isolated probes warmed {"type": "string"} and then observed
native SchemaError while the cache still accepted it:

- Change the default registry's Draft 2020-12 meta/validation resource so its
  properties.type requires {"const": "integer"}. Resource contents are mutable
  mappings. Both saved and newly computed environments retain the same registry
  object; serializing the top-level META_SCHEMA misses this resource.
- Replace Draft202012Validator.__init__.__kwdefaults__["registry"] with a
  registry carrying that changed resource. The actual constructor uses the new
  registry, while __attrs_attrs__ still advertises the old default.

The test case named registry only wraps validators.validator_for; it does
not change a registry or a referenced meta-schema and cannot detect either gap.

**Closure:** Bind reuse to the effective registry construction inputs and the
referenced meta-schema semantics, or decline caching when those inputs cannot
be shown unchanged. Add genuine registry/default and referenced-content drift
tests with a native rejection oracle. Preserve bounded memory and demonstrate
that the corrected check still avoids the measured repeated meta-validation.

## Initial R4 — CLOSED in follow-up: Independent overlapping scopes leave a stale global wrapper

**Location:** tools/inventory_recovery_v3/schema_replay.py:72–98;
tests/test_inventory_recovery_v3_schema_replay.py:144–174.

ACTIVE is context-local, but active.schema_for is process-global. Entering
scope B in a fresh Context while scope A is open captures A's wrapper as B's
original. B clones that wrapper rather than the native builder; its closure
still contains A's cache and falls through to native validation. In a
deterministic single-thread probe, A retained one entry and B retained zero
after repeated identical calls. Exiting A before B restored native temporarily,
then B restored A's dead wrapper. After both exits, ACTIVE was None but
active.schema_for is original was false. A later scope also retained zero
entries after repeated calls, so one overlap can disable the performance repair
for subsequent operations. No provider concurrency is required to reproduce it.

**Closure:** Give the global installation an ownership/lifetime discipline that
supports independent contexts, or explicitly reject overlapping independent
scopes before changing the binding. Test two fresh contexts entering scopes,
both exit orders, exceptions, exact restoration of the original function, and
successful caching in a later operation. Existing same-context nesting and
foreign-context calls without entering a scope do not cover this failure.

## Initial closure requirements — historical

All four counterexamples were reproduced with short, isolated, offline
python -B probes against the installed implementation. In-process mutations
were restored; no test files or fixture artifacts were written. These are
conditional drift/overlap failures, not evidence that unchanged JSON-native
profiles currently fail ordinary sequential replay.

Resolve R1–R4 with the specified negative regressions, retain the existing
record-validation/contract-drift/restoration coverage, and rerun the dedicated
and affected integration gates on the final source. The coordinator's pending
executor run c618909d2b9f9ac4a7a2/executor-b32b709d87c2 cannot close findings
against a subsequently changed source. Final closure still requires the exact
oversized executor case and full fixed executor suite within the unchanged
1800-second limit, including repeat/accounting assertions.
