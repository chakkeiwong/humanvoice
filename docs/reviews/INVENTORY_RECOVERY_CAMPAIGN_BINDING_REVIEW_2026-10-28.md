# TX3a offline campaign binding review — 28 October 2026

## Scope and evidence

Bounded, single-inspector review of the offline binding, its public preparation
integration and the specified adversarial tests. The root `AGENTS.md` applies;
no nested instruction file was found under `docs`, `tools` or `tests`.
The earlier plan findings F1/F2 are resolved at the plan level; their disposition
is appended to `INVENTORY_RECOVERY_END_TO_END_PLAN_REVIEW_2026-10-28.md`.

Reviewed frozen identities (SHA-256):

| File | Identity |
| --- | --- |
| `tools/inventory_recovery_v3/campaign_binding.py` | `6dc8dd0a235ef6ea06ccc8b41cdb205c7c49d66cd788ccf9568731f3be002338` |
| `tools/prepare_inventory_recovery_v3.py` | `89a6ed354d3168e29e74fe22979b4e82f18dacead90f7bf3e82f9c500ffa1176` |
| `tests/test_inventory_recovery_v3_campaign_binding.py` | `31a28ba5ad8f5a13d9c6ae97fdc247e45181c05a4e6fd3d9ff4f3e4b76ecd95a` |
| `tests/test_inventory_recovery_v3_stage.py` (public replay test) | `737291020871da04f412114d41fd4c63fe07b7dc0c4f2389bc9cb06a7ef9cd8e` |

Method: static control-flow and evidence-membership review, with narrow reads
of preparation, campaign history, account/grant validation and journal helpers.
No tests or project entrypoints were executed in this review. The coordinator
reports 56 fixture cases plus one native public preparation/replay case passing
in 98.01 seconds; that run is not independently reproduced here. The fixture
explicitly mocks preparation/account/grant validation; the public test at
`tests/test_inventory_recovery_v3_stage.py:424` uses native replay against test
artifacts. Neither is an actual production-data preflight or live admission.
The coordinator subsequently reports 553 exact-member focused cases passing
in 110.01 seconds with 16 workers, unchanged full source binding and unchanged
production account/grant/stages. This is reported validation evidence, not an
inspector rerun. The four file hashes above were independently rechecked and
remain unchanged.

## CB1 — P2 / Medium: snapshot membership disappears from binding revalidation

**Location:** `tools/inventory_recovery_v3/campaign_binding.py:33`, `:121`,
`:175` and `:200`.

**Evidence:** `immutable_paths()` includes `prepared-snapshot.json` but none of
the actual `generation-00/snapshot` members. `observe()` never compares that
manifest with the current snapshot tree. `CampaignHistory.status()` does not
fill the gap: its preparation check compares plan/probe bytes and identities
(`campaign_history.py:322`), without recomputing the full preparation
`validation_identity`. Only the first `create()` calls the native verifier;
the existing-binding path returns `inspect()` directly. The native verifier
does include snapshot membership (`campaign_preparation.py:24`, `:72`), but
the subsequent `stable()` and final inspection do not retain that check.

**Concrete failure:** create a valid offline binding, then alter, delete or
symlink an existing immutable snapshot source/rights member while leaving its
manifest and other binding files intact, with generation zero still unallocated.
`inspect()` and an existing-binding
`create()` can still report `OFFLINE_CAMPAIGN_BOUND`. The same omission admits
a change after `verify_prepared()` returns but before the first publication.
The public happy-path test's later `current.validate()` can catch a snapshot
problem during that command; it does not repair the standalone binding API's
missing checks. This is an offline evidence-integrity defect, not a demonstrated
live-dispatch bypass.

**Required repair:** derive the required immutable snapshot members and hashes
from retained preparation evidence and verify their current canonical paths
and bytes on initial publication and every inspection. Recheck that membership
after native verification and before publication. For an unallocated candidate,
require the full prepared tree; for later runtime inspection, explicitly
distinguish allowed generated artifacts from immutable input members so lawful
growth remains valid. Do not silently freeze all mutable runtime output.

**Regression:** extend the mutation matrix at
`tests/test_inventory_recovery_v3_campaign_binding.py:101` with source/rights
snapshot changes, deletion, symlink substitution and unexpected pre-allocation
membership. Apply changes both after binding and immediately after the native
verifier returns. Require rejection without publication/repair, plus a positive
case for allowed runtime additions. The current matrix omits the snapshot.

## CB2 — P2 / Medium: a rehashed binding can lower its own consumption floors

**Location:** `tools/inventory_recovery_v3/campaign_binding.py:52` and `:143`.

**Evidence:** the binding's outer identity is a recomputable digest. Immutable
membership and proposal/journal identities are independently compared, but
`account_floor` and `grant_stages_floor` are not tied to an independently
retained binding-publication identity. `require_floor()` accepts any valid
shorter prefix, and lines 159–161 accept an empty stage floor. The seed and
proposal predate this binding and do not identify its recorded floors. The
public preparation report records the binding identity at line 145, but neither
`inspect()` nor the existing-binding `create()` reads an independently retained
expected identity.

**Concrete failure:** create a binding while a valid sibling stage has a call
hold but no account allocation. Remove that hold, set the persisted binding's
`grant_stages_floor` to `[]`, and recompute its identity. The prefix comparison
now succeeds. Native `automatic_call_grant.status()` validates only the holds
that remain and requires membership for allocated plans (`:83`–`:115`); an
unallocated sibling hold leaves no such account entry, so its loss is not
independently detected. The candidate is accepted despite discarding a hold
that existed when it was bound. Similarly, lowering/re-hashing the account
floor can conceal a valid-prefix rollback newer than the separate preparation
anchor. An unmodified binding rejects the losses; a self-rehashed one does not.

**Required repair:** bind these initial floors to separately retained, owned
publication evidence and verify the expected identity on reopen, or derive
them from an independently immutable checkpoint that cannot shrink when the
candidate is rehashed. Preserve an explicit crash/reopen protocol for that
publication; do not rebuild missing committed floors from whatever runtime
state remains. This can stay entirely offline and need not grant execution.
The finding concerns membership already captured at binding creation; it does
not require this offline candidate to protect every later runtime suffix.

**Regression:** use valid shorter floors, not only the negative event count
currently tested at `test_inventory_recovery_v3_campaign_binding.py:93`. Cover
an unallocated sibling hold present at binding and subsequently removed while
the candidate is rehashed, and a valid account suffix rolled back after binding.
Both must fail. Unchanged retained floors with lawful sibling append/settlement
must still pass. Include before/after-publication death cuts for any new anchor.

## Remaining scope and disposition

- The reviewed result stays explicitly offline and nondispatching. `create()`
  enters `no_inference()`, and public preparation retains execution locks and
  verifies unchanged production account/grant bytes. No finding asserts live
  authority or requires completing TX3b in this slice.
- Canonical root/account/grant/journal checks and before/after binding-publication
  death cases are present. Beyond CB1's unobserved snapshot change, no additional
  publication-cut or canonical-root finding is established in this review.
- The journal's retained descriptor, initialization identity and consumption
  head are checked; this review does not certify full runtime rollback
  resistance or the later deployment/monotonic-runtime-floor gates.
- **Disposition: changes required for CB1 and CB2 before claiming this offline
  binding fully preserves its prepared membership and captured consumption.**
  The reported passing cases do not exercise either counterexample.

Only the two review documents are written by this inspector. No source/master
edits, production operations, inference, new test runs or agents are performed.

## CB1/CB2 repair follow-up — 28 October 2026

**Disposition: CB1 and CB2 closed within this offline candidate slice.** No
concrete residual defect was found in the two repairs. This supersedes the
earlier changes-required disposition for these findings only.

Reviewed repair identities (SHA-256):

| File | Identity |
| --- | --- |
| `tools/inventory_recovery_v3/campaign_binding.py` | `3d108a9786ce138543c1bf876d6f0f9951210e6a7aca83b39995f7893fb86eb2` |
| `tools/inventory_recovery_v3/binding_publication.py` | `d64f2210128caf0e009463748210bf7af295a58f8474036f498cbf296431b8c5` |
| `tests/test_inventory_recovery_v3_campaign_binding.py` | `f4c7f2a5c340878382c61e36b076e133ba093fb9045c02243612f6918bd684bb` |

The public preparation integration remains at
`89a6ed354d3168e29e74fe22979b4e82f18dacead90f7bf3e82f9c500ffa1176`.

- **CB1 resolved.** `campaign_binding.py:64` compares an unallocated
  snapshot against the full retained prepared manifest using the existing
  tree-hashing contract. Canonical-path and tree checks reject symlinks.
  Allocation must match both output and plan identity in the validated account
  (`:138`) before the limited runtime exceptions apply. Immutable inputs
  remain required afterward; inventory output may change, and runtime/CLI
  additions are limited to their named directories. `observe()` checks actual
  snapshot membership (`:140`), and `stable()` repeats it (`:148`) after native
  verification and before each binding publication (`:237`). Existing-binding
  inspection also passes through these checks. The late/reopen mutation matrix
  at `test_inventory_recovery_v3_campaign_binding.py:242` covers source and
  rights changes, deletion, symlinks and extra files; `:282` covers allowed
  allocated output growth followed by rejection of changed source input.
- **CB2 resolved.** `binding_publication.py:20` retains the complete binding,
  including both captured floors, in a separate intent. The reader at `:29`
  accepts only the exact intent → pending marker → binding → complete marker
  states and compares the target against the retained full binding. Rehashing
  only the target with shorter floors therefore fails before candidate
  acceptance. `campaign_binding.create()` keeps a retained pending binding
  (`:224`), checks its original floors against current evidence (`:235`), and
  resumes its publication without recapturing those floors. Inspection
  requires complete publication (`:188`). Tests at `:297` cover both original
  shorter-floor counterexamples, `:322` covers individual committed-member
  loss/corruption, and `:201` covers real process death before and after all
  four publication boundaries, read-only incomplete inspection and reopen.

Validation boundary: the coordinator reports **90 passing component cases**.
This follow-up statically inspected the implementation and tests; it did not
rerun them. Broader exact-membership native integration was still running at
the supplied checkpoint and is not recorded as passing here. Closure covers
prepared input membership and the initially captured floors only; it does not
certify ongoing protection of later runtime suffixes, live admission, full
deployment, or release readiness. Only this review report is edited in this
follow-up; no production calls, source/master changes or agents are involved.
