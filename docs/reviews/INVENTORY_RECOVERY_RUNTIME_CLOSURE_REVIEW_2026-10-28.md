# Runtime closure bounded findings — 28 October 2026

Final component disposition: **RC1, RC1-R and RC2 closed in the reviewed
OD3/OD4 unit-3 scope. No reproduced residual remains.** The separately supplied
authenticated-control authority is a required external prerequisite, not a
production authentication implementation or release admission.

This is a findings-only review of `runtime_closure.py`, `runtime_predicates.py`, their
`configuration.py` integration and the named closure/predicate/configuration
tests against OD3/OD4 and implementation unit 3. The externally verified
configuration/release admission prerequisite is accepted. This report does
not claim a public factory exists, treat a fixture callback as host permission,
or require the explicitly future CampaignAuthority/StageAuthority/provider
integration in this slice. Closed descriptor/lease/launcher reviews were not
reopened; adjacent consumers were read only to understand the new callbacks.

## Final RC1-R recheck — 28 October 2026

The coordinator requested a residual-only recheck after freezing the
byte-preserving repair. `stop_authority.py:32–34` now reads raw bytes and
decodes them strictly as UTF-8, with no universal-newline conversion. Both
transfer capture and runtime checks use this helper, preserving exact valid
UTF-8 bytes through the string representation and subsequent hash encoding.

**RC1-R is closed.** Both LF-to-CRLF and CRLF-to-LF changes now raise
`USER_STOPPED` for inherited/prospective roots and stop/resume independently.
Exact originally authenticated LF and CRLF documents remain accepted.
Independent temporary probes also confirm:

- The same eight combinations fail through an existing leaf, a fresh leaf,
  a real fresh subprocess and `OwnedPredicates.check` with a complete lease.
- Transfer capture preserves the original stop bytes exactly. For changed
  stop files, the native reader and runtime leaf both reject the mismatching
  raw stop hash. Restoring the exact originals restores eligibility.
- Successful and rejecting leaf/guard checks leave fixture file bytes and
  mtimes unchanged. Invalid UTF-8 stop/resume contents fail `USER_STOPPED`.

**Final inspector verification:** eight new repository regressions passed in
**0.99s** (36 unrelated predicate cases deselected); ten additional temporary
probes passed in **5.52s**; Ruff passes for the two touched files. Temporary
probe: `/tmp/test_humanvoice_runtime_rc1r_final.py`. The coordinator confirms
the final combined run: **277 passed in 12.55s**, with Ruff passing. This
combined result is coordinator-provided; the independent residual-only
inspection results are the eight repository cases and ten probes above.

Frozen repair identities:

```text
6a95a58709a07fa79686c1d4ed8f8c4199d8e635d17faae69a7eeb9a37c8419e  tools/inventory_recovery_v3/stop_authority.py
2c2e38381c15e49adef62919e62959ee527fc8b3e7109a01ffd80396bfff18d7  tests/test_inventory_recovery_v3_runtime_predicates.py
```

**Closure boundary:** The reviewed component accepts independently supplied,
authenticated monotonic control history; it does not create that trust root.
The future producer/public factory must authenticate current history/resume
provenance, protect the latest history head against rollback independently
of candidate-writable files, durably record each stop before publishing its
stop file, and handle interrupted publication fail-closed. Whole-history plus
stop/resume restoration must be rejected across process death by that external
authority. Reader callbacks must remain read-only and avoid native locks.
The temporary fixture file is not production authentication. Public factory,
control-publication producer, CampaignAuthority/StageAuthority/provider
composition and final release/preflight/host admission remain future gates;
this component closure grants no live permission. No source/test/master edits
or production/provider/service/authority changes were made by the inspector.

The earlier findings and intermediate recheck are retained below as history;
their open dispositions are superseded by this final component closure.

## Intermediate repair recheck — 28 October 2026

Rechecked the coordinator's frozen repair, adding `stop_authority.py` to the
same scope. At that intermediate freeze, RC2 was closed and RC1-R remained
open. The final residual recheck above now supersedes that disposition;
the original reproductions remain as historical findings.

### RC1-R — Medium: text-mode reads bypass exact stop/resume byte binding

**Locations:** `tools/inventory_recovery_v3/stop_authority.py:32–34`, consumed
by transfer capture at lines 48–58 and runtime comparisons at lines 101–115.
`runtime_predicates.py:54–57` delegates to this verifier.

**Reproduced for both inherited and prospective roots, independently for stop
and resume files:** Create a valid retained stop with multiline LF JSON, then
an independently supplied matching authenticated resume and history. Verify
the leaf passes. Change only the selected on-disk file's LF bytes to CRLF,
leaving authenticated evidence and configuration unchanged. The on-disk
bytes differ, but both the existing and freshly constructed leaf still pass.
For the stop case, the authenticated resume's `stop_sha256` no longer equals
`digest(user-stop.json.read_bytes())`; the existing native
`control.require_running(root, contract=...)` correctly raises `USER_STOPPED`,
while the new leaf returns `True`.

`Path.read_text()` performs universal-newline translation. Consequently,
`content == retained_stop_bytes`, the authenticated resume comparison and
`digest(content.encode())` validate normalized text rather than the exact
bytes that were authenticated. This is a reproduced integrity mismatch, not
a claim that the newline rewrite changes the stop's semantic meaning.

**Correction:** Read raw bytes for all stop/resume observations and preserve
them exactly when representing them in evidence. If the contract remains
UTF-8 strings, use strict explicit UTF-8 decoding without newline conversion
and hash the original bytes (or an exact round-trip encoding). Reject invalid
encoding as `USER_STOPPED`. Apply the same rule at transfer capture and runtime.
Do not normalize either side before comparison.

**Required regressions:** At both roots, rewrite LF to CRLF and CRLF to LF
for stop and resume independently after authentication; all must fail on
the existing leaf, fresh leaf/process and owned guard without writes. Include
a positive case whose original authenticated stop/resume genuinely use CRLF
and retain those exact bytes. Require agreement with the native stop-file hash.

### RC1 architecture and remaining integration boundary

The chosen correction option is implemented: `RuntimeLeaf.__init__` now
requires an explicit callable `require_controls`, with no configuration-only
fallback. The verifier binds evidence to the complete admitted configuration,
initial stop observations, exact canonical roots/contracts, complete increasing
history and authenticated latest resume. The existing new regression matrix
rejects deletion, rollback, replayed resume and missing history across both
roots and transfer/new-stop cases. Fresh subprocess and owned-guard deletion
checks pass. An exact latest resume restores eligibility.

Two additional temporary probes cover the visible write-ahead publication
cuts: history containing the new stop while its stop file is absent, and
authenticated resume evidence published before its resume file. Both fail
`USER_STOPPED`; completing publication restores a passing same/fresh leaf.
The probes verify unchanged configuration identity and unchanged file bytes
and mtimes during the successful leaf checks. Runtime validation remains
read-only and does not derive configuration or acquire native locks.

**This accepts the component's explicit supplied-authority interface, not
production authentication.** The temporary file reader is only a test
authority fixture. No implementation of an independently authenticated,
rollback-protected producer/public factory is present or claimed. Before
public integration, that producer must durably record every stop before
publishing its stop file, authenticate resumes for the latest root/contract/
stop, and protect the current history head independently of candidate-writable
files. Restoration of history, stop and resume together must be rejected by
that trust boundary, including after process death. Publication/recovery must
preserve fail-closed cuts; leaf readers must neither publish nor enter locks.
Public live commands still explicitly reject. These future requirements do
not reopen the closed descriptor/lease/launcher reviews.

### RC2 closed

`runtime_closure.py:70–72,114–115,142–143` now directly retains and compares
the actual `*.py` member set of the source-contract root. The native
source-enumeration fixture rejects additions, renames, removals and symlinks;
generated JSON does not affect membership. Existing member-byte validation
remains active. No capture/derive/proposal or generated-configuration hash
cycle was introduced by this repair.

### Recheck evidence

- Inspector focused suite: **154 passed in 6.49s**, with 16 workers, pytest
  cache/bytecode writing disabled and temporary outputs under `/tmp`.
- Inspector Ruff check: all seven reviewed source/test files pass.
- Inspector temporary residual/cut suite: **6 passed in 1.03s**. Four passing
  assertions intentionally reproduce RC1-R; two validate publication cuts
  and read-only recovery. Probe:
  `/tmp/test_humanvoice_runtime_rc_recheck.py`.
- Coordinator reports **269 passed in 12.49s**, with receipt
  `.localresources/runtime-closure-rc-integrated-20261028.xml`; this is not
  represented as an independently rerun 269-case suite.
- Documented human-approval/status check succeeds: `on-request` / `user`,
  sandbox `workspace-write`, production stopped/disabled, `MainPID=0` and
  `ControlPID=0`. Only this report and `/tmp` probes were written; no source/
  test/master edits, privileged action, provider call, authority/service
  change, commit or push.
- Frozen hashes were identical at initial and final source checks:

```text
7e312a9872e4263c60e16aab43451d7332ed46e8476293cd4f7e5dc90d952a37  tools/inventory_recovery_v3/runtime_closure.py
02b6569e409f21dada79022ffa388f9227aa13dd8e65e0ae530fbcd4f8029d09  tools/inventory_recovery_v3/runtime_predicates.py
f9dc1491863acb4b78914d66dab7a24528c903b2fbb187939283fa2df6c9e31e  tools/inventory_recovery_v3/stop_authority.py
c127c08d3715715ed1275a74fffd3980edb7cbcf7b1ce91ac36984baa174c3eb  tools/inventory_recovery_v3/configuration.py
59c006ffdf67afb9a1a78caa1db25c1c3e785b764ec2807f25cbb3d7473b5b52  tests/test_inventory_recovery_v3_runtime_closure.py
36cb877dd8db7947b443f2ebbb41d8f89ac2c48c85b462c29a45f1c5539d87fe  tests/test_inventory_recovery_v3_runtime_predicates.py
2ee8ef997822e46abab3929f17e5f7cf3f552cb955baa7b656570266697e6d48  tests/test_inventory_recovery_v3_configuration.py
```

## RC1 — High: deleting or rolling back a stop restores a passing runtime leaf

**Locations:** `tools/inventory_recovery_v3/runtime_predicates.py:47–56`,
especially the delegation at lines 52–56;
`tools/inventory_recovery_v3/runtime_closure.py:106–109,130–138`;
`tests/test_inventory_recovery_v3_runtime_predicates.py:63–71,143–159`.
The native behavior reached by the new leaf is
`tools/inventory_recovery_v2/control.py:26–45`.

**Reproduction:** Using the existing `predicates` fixture, independently for
inherited stop index 0 and prospective stop index 1:

1. The admitted configuration and retained closure are unchanged; `leaf()`
   returns `True`. Call `control.stop(root)`; `leaf()` raises `USER_STOPPED`.
2. Remove only `root/user-stop.json`, leaving no resume authorization. The same
   `leaf()` returns `True`; a newly constructed leaf for the same admitted
   configuration also returns `True`.
3. In a separate case, retain stop A and a matching exact-contract resume A.
   Verify it is accepted. Publish stop B and verify `USER_STOPPED`. Restore
   the bytes of stop A while leaving resume A in place. Both the existing
   and fresh leaf return `True`, despite no authorization to resume stop B.

Four temporary cases reproduce deletion and rollback at both roots. Two
positive-control cases confirm a resume with the wrong contract is rejected.
Thus the issue is absence of retained stop history, not failure to compare
the contract or stop hash when those files are present. The probe uses an
unchanged admitted configuration callback, exactly as the component fixture
does; it does not alter or forge admission.

**Why it matters:** `regular_path()` permits absence, and the delegated native
reader returns immediately when the stop file is absent. Neither the retained
closure nor the new leaf retains an observed stop generation. A newer stop
can therefore cease vetoing acquisition or `OwnedPredicates.check/dispatch`
after deletion or rollback. The plan explicitly requires inherited and
prospective stops with original contracts, explicit-resume provenance, and
stop deletion/rollback checks. Release/configuration authenticity alone does
not establish that an evolving stop was explicitly resumed. This is a
component gap before promotion, not a claim that the blocked public commands
currently dispatch.

**Correction required:** Bind an independently retained, monotonic stop
observation for every canonical stop root and require exact authorization
for the latest stop. If that state belongs to a separately supplied authority,
make the leaf require and validate its explicit evidence; merely returning
the same configuration does not supply it. Keep runtime validation read-only
and free of native lock reentry; publication of any stop history belongs at
the appropriate owned boundary. Do not solve this by freezing stop files
against all changes, which would reject lawful new stops/resumes.

**Regression required:** Cover inherited/prospective roots, stop present at
transfer and stop created afterward, deletion, replacement with older bytes,
replayed older resume, missing retained stop evidence, and fresh-process
reopen. Exercise both the leaf and the owned guard. Positive cases must
include a newly issued exact resume for the latest stop and unchanged
account/stage growth. Preserve `USER_STOPPED` veto semantics.

## RC2 — Medium: runtime source checks do not retain exact source membership

**Locations:** `tools/inventory_recovery_v3/runtime_closure.py:99–109,135–138`;
`tools/inventory_recovery_v3/configuration.py:41–43,114–122,138–139`;
`tests/test_inventory_recovery_v3_runtime_closure.py:56–76`. The native source
membership definition is `tools/review_inventory_recovery_v3.py:23–27`.

**Reproduction:** In a temporary repository tree, execute the original
`review.sources` function body with only its `ROOT`/`__file__` globals bound
to that tree. Build the normal installed/adoption/closure/predicate fixtures
using that source reader. The source inventory initially equals
`adoption['installed']['sources']`, and the leaf passes. Add
`tools/inventory_recovery_v3/new_member.py` without changing any retained
file. The native source map now differs from the admitted source map, but
both `runtime_closure.verify()` and `leaf()` still return `True`. This probe
does not mutate repository source or replace the verifier.

**Why it matters:** Capture records the bytes of existing source members,
but runtime verification iterates only that recorded map. The source
contract is an inventory (`glob('*.py')`), so a new member changes the source
identity used to choose preparation/configuration even though every old
checksum still matches. The runtime closure therefore accepts a different
source inventory from its admitted transfer. Existing source tests overwrite
an already-recorded member and do not cover an added member. External
admission can add a redundant source check, but the new immutable-evidence
component currently does not enforce this part of its retained identity.

**Correction required:** Capture and recheck exact membership of the
source contract's enumerated roots in addition to member hashes. Use a
small direct read-only membership verifier; do not reenter configuration
derivation, adoption/capture/proposal or native accounting. Apply the same
membership predicate as the source contract so generated configuration,
preparation, runtime outputs and caches do not become source inputs.

**Regression required:** Add a native-source-enumeration temporary fixture
that adds a matching `.py` member after capture and requires closure/leaf
rejection. Cover rename/removal and symlink members. Positive cases should
show that generated configuration/preparation JSON and lawful mutable
account/stage growth leave the source identity and leaf valid, with no
source/configuration hash cycle.

## Executed checks and boundaries

- Read `/home/ubuntu/AGENTS.md`, repository `AGENTS.md`, the human approval
  policy and relevant OD3/OD4/unit-3 contract. No nested agents.
- The exact documented `humanvoice_manual_approvals.py check` and `status`
  commands succeeded. Human review is `on-request` / `user`, sandbox is
  `workspace-write`, and reported production services are stopped/disabled
  with `MainPID=0` and `ControlPID=0`. No privileged action was requested.
- Focused existing suite: **129 passed in 56.56s**, covering the three named
  closure/predicate/configuration modules. Ran with bytecode writing disabled,
  pytest cache disabled and a dedicated `/tmp` base directory. The supplied
  coordinator result of 244 cases / Ruff pass is not represented as a new
  inspector run.
- Temporary diagnostic suite: **9 passed in 1.23s**. Passing assertions
  intentionally reproduce RC1/RC2, plus wrong-contract resume rejection and
  detached configuration-property behavior. Probe file:
  `/tmp/test_humanvoice_runtime_review_probes.py`.
- Existing checks passed for predecessor file/directory/receipt mutations,
  qualification plan membership, lock-slot creation and symlink rejection,
  immutable grant/old cursor/source bytes, no transfer-reader/native-lock
  runtime recursion, recursive admission rejection/reset, pending-floor
  dispatch rejection, late-stop veto, native floor writes with a real lease,
  and read-only cold rollback rejection. Account and grant-stage bytes remain
  separate from the immutable installation projection. No additional
  reproduced lawful-growth rejection or source/config hash cycle was found.
- Repository writes are limited to this report. Temporary probes/fixtures
  are under `/tmp`; no production/provider/service/authority write, inference,
  restart, commit or push was performed.

## Reviewed frozen source identities

```text
1556267a5dd99c9e2c16179c8be57e35b20e13a486e5ede37ee347026a2a065c  tools/inventory_recovery_v3/runtime_closure.py
19617446b3f1e176a15b0460f5817fbd83c6f608ee053d2c95f965e91af89a72  tools/inventory_recovery_v3/runtime_predicates.py
61503a464a609030580e34031b76c295731a38d54ef50305674df9a4d89137e1  tools/inventory_recovery_v3/configuration.py
a2d946b52882ee115b6a228729e3507dfb48058be29dba971554a11e90c999cd  tests/test_inventory_recovery_v3_runtime_closure.py
84ea9900f17a7a6ec4c79288d4bf0b9ba9fa4952887f03732378eaa28bd76524  tests/test_inventory_recovery_v3_runtime_predicates.py
166f8881c1a9482cfb8cba0f04a47be03a8200e49999cf39fbc1c317c8a8fd30  tests/test_inventory_recovery_v3_configuration.py
```
