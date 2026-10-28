# Inventory recovery ownership design review — 2026-10-28

Findings-only, static DESIGN review of the **Recovered implementation trace and
next executable slice** in
`docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md:205–269`.
The six findings below are implementation-contract omissions or integration
blockers, not claims that the proposed ownership component already exists.

Read `/home/ubuntu/AGENTS.md`, repository `AGENTS.md`, the design, and immediate
ownership/launch/runtime dependencies. Only this report was written. No project
imports, executable project commands, tests, model/provider calls, service
actions, source/test/master edits, or frozen-suite input changes were made.
Closed floor and validation-runner reviews are outside this review. Regression
cases below are requirements for the coordinator's later implementation; none
was executed here. This report makes no live-readiness determination.

## OD1 — P1: Specify role-specific extension and consumption of the canonical set

**Evidence.** The proposed API has only `expected(configuration)`,
`acquire(configuration, check)`, `inherit(configuration, capsule, check)`,
`check()` and `capsule()` (plan:242–253), while requiring child-specific job/stage
additions. The job is generated at launch (`launcher.py:20–30`); stage locks are
created later from `output` (`stage_owner.py:47–61`). Neither is a fixed
configuration-only member. The installed `shared_locks` also already contains
`active-session-program.lock` (`inventory_history_live.py:59–65`), although the
new acquisition order places historical stage locks before a separately named
program lock. Existing consumers include `CampaignHistory.owned(descriptor=...)`
(`campaign_history.py:91–109`) and monitor entry that independently opens its
lock (`inventory_recovery_v2/supervisor.py:127–134`).

**Blocker / required design.** Define the ordered role schema, its independently
verified job/stage inputs, the operation that adds only those roles, and how
consumers obtain the matching inherited descriptor. A fixed-only capsule either
rejects lawful child additions as extras or leaves their membership outside
validation. Treating the entire historical `shared_locks` list as the stage
group would acquire the program lock early and possibly open it again. Bind
each canonical resource once, with an explicit rule for repeated paths/inodes;
do not silently deduplicate conflicting roles. Name the monitor and campaign
adapters that consume this capability instead of reopening a held lock.

**Required regressions.** Verify the exact acquisition trace using a production-
shaped installed list that already includes the program lock. Cover monitor →
worker → campaign → stage/provider role sets, two successive jobs/stages, swapped
or retired request/plan evidence, extra environment-selected roles, path aliases
and different role paths sharing an inode. A real campaign owner must enter
using the inherited campaign descriptor; monitor entry must not acquire its
already-owned lock again.

## OD2 — P1: The existing descriptor verifier can acquire or upgrade ownership

**Evidence.** `inventory_history_job.exclusive_descriptor:22–32` first expects
an independent exclusive-lock attempt to fail, then calls exclusive `flock` on
the supplied descriptor. It is used by current handover, stage, campaign and
job checks. The new contract instead requires verification of already-exclusive
inherited open-file-description ownership and forbids child reacquisition
(plan:221–224,245–246).

**Blocker / required design.** Do not equate a successful call to this helper
with that stronger contract. A supplied descriptor holding the sole shared
lock makes the independent exclusive probe fail, then can be upgraded by the
second call and accepted. There is also a two-step race: a foreign owner can
release after blocking the independent probe, allowing a fresh supplied open
to acquire the lock on the second call. Specify a verification protocol that
cannot create or convert the ownership it is supposed to prove. Keep any
prospective replacement private rather than changing frozen helpers.

**Required regressions.** In addition to ordinary same-inode fresh-open
rejection, pass a solely shared-locked descriptor and require rejection without
upgrading it. Synchronize foreign-owner release between the two probe points
and require the fresh descriptor to remain unaccepted. Repeat for a true dup
of an exclusive owner, an unlocked former owner, and a replaced inode. Failed
validation must not release or change another descendant's valid ownership.

## OD3 — P1: The immutable runtime guard needs the full retained predecessor closure

**Evidence.** `installed_authority.capture:39–95` records installed admission,
adoption, configuration, units, old campaign cursor and consumption resources.
It does not itself record the latest supervisor's state/job receipts. Those
are captured separately by `inventory_history_handover.snapshot:34–121` into
the newly appended handover record (`handover.py:62–75`). Existing
`ChainLease.check()` reaches those checks through `require_running → validate →
proposal`, which also calls `installed_authority.capture`
(`handover.py:49–50,78–99,113–119`). `immutable_projection:107–118` projects only
the installed binding; it is not a replacement for the separate chain checks.
Historical qualification lock membership is likewise enumerated from plan
paths by `inventory_history_live.shared_locks:59–65`.

**Blocker / required design.** Define the exact retained files and directory
memberships that the new direct runtime guard checks after removing that
transfer-time call chain. Comparing only `immutable_projection` plus the held
FD list would omit the latest predecessor's state/job evidence and could miss
new historical stage membership requiring additional exclusions. Revalidate
the transfer-bound predecessor snapshot and lock membership after taking its
monitor/job exclusions, before declaring quiescence; preserve those checks at
runtime without rebuilding the mutable installation capture. Continue to
exclude only the intended account/stage bytes from immutable equality.

**Required regressions.** After transfer binding, change a latest-predecessor
state/request/ack/result/recovery/heartbeat file, add a job or historical
qualification plan, and require rejection. Include a change between initial
validation and exclusion acquisition. After successful ownership, make
`capture()`, configuration `derive()` and transfer `proposal()` unavailable and
exercise inheritance and repeated runtime checks. Lawful native consumption
growth must still pass; changes to immutable grant, old cursor or retained
predecessor evidence must fail. This tests guard composition, not a reopening
of consumption-floor implementation.

## OD4 — P1: Separate the partial-acquisition predicate from the full lease check

**Evidence.** The API takes a single `check` callback for acquisition and
inheritance (plan:242–246), requires checks between acquisitions (255–259), and
requires runtime checks of the complete set, installation, stops and floors
(260–262). `CampaignAuthority` invokes admission during construction and every
check (`stage_authority.py:23,46–69`); `grant_stage` calls that check while
holding the grant lock (`75–80`). `StageOwner.check()` delegates to the
authority (`stage_owner.py:29–34`).

**Blocker / required design.** State which predicate is valid before a lease
exists, while only a prefix is held, and after the complete lease is active.
Passing a full lease/admission check during acquisition is circular or fails
because future descriptors do not yet exist; making it permissive can then
weaken runtime validation. Document an acyclic callback graph, with a leaf
admission/stop check for acquisition and a full checked lease for execution.
Require a final full-set validation before publishing the active lease or
allowing dispatch. Explicitly prevent full admission from calling back into
the same authority and prevent checks under native locks from reacquiring
those locks. This supplies the missing API contract for the plan's existing
nonrecursive-check requirement.

**Required regressions.** Veto before acquisition, between every adjacent role,
after the final acquisition, during duplication, and immediately before spawn.
Require complete unwind and no ack/hold/claim/dispatch on failed admission.
Exercise the actual authority callback graph under already-held grant/account
locks with bounded completion and re-entry detection; runtime checks must
reject a missing member rather than accept the partial-acquisition predicate.

## OD5 — P2: Define ownership of incoming FDs and regeneration of legacy job capsules

**Evidence.** Both `handover.inherited:175–180` and
`launch_handoff.inherited:95–99` duplicate incoming FDs and close only their
duplicates. The proposed interface also says “validates and duplicates” and
promises an explicit active lifetime (plan:245–250), without assigning cleanup
of the raw inherited handles. The campaign's legacy job record contains an FD
number and is checked repeatedly from the environment
(`inventory_history_job.py:49–68`, `stage_authority.py:62–70`).

**Omission / required design.** Choose a borrowing or consuming contract for
incoming descriptors and identify the owner responsible for every original
and duplicate on success, rejection and scope exit. Closing only lease-owned
duplicates can leave the raw inherited locks held in a surviving process after
the lease ends. Closing originals without rebinding the job record makes its
next check use a closed or reused FD. Specify the validated role-to-FD
translation for legacy job checks and every next-hop capsule, and retire stale
environment capsules. Cleanup must close owned references, never explicitly
unlock a shared open-file description still held by a descendant.

**Required regressions.** Keep a child process alive after its lease scope exits
and verify locks are released once its assigned references and all descendants
are gone. Verify that one process's normal exit/unwind cannot unlock a surviving
grandchild. Exercise failure halfway through duplication, descriptor-number
reuse, a second lease in the same process, and repeated legacy job checks after
FD remapping. Check that next-hop capsules contain only live owned descriptors.

## OD6 — P1: A private collector also needs a private, verified binding at the active call site

**Evidence.** The design correctly identifies the collector's single-FD
`Popen` and requires a private implementation (plan:207–214,268–269). However,
the cloned v3/v2 runtime still imports the shared
`tools.qualification_capture_runtime` as `qualified`
(`inventory_recovery_v2/runtime.py:17–28`, `sol_inventory_runtime.py:12,58–64`).
The active launch closure calls `qualified.capture.launch` directly with
`lock_fd` (`sol_inventory_runtime.py:76–114`); the outer v3 wrapper delegates
to that closure (`inventory_recovery_v3/runtime.py:179–185,193–218`). Changing
`_EXECUTION_FDS` alone cannot change this call. Reassigning
`implementation.qualified.capture` would mutate a shared module. The current
collector has no ownership callback immediately before its actual `Popen`
(`response_capture_observation.py:40–88`).

**Blocker / required design.** Specify the private launch dependency binding,
not just the collector file. It must reach the active native launch closure
without replacing a frozen/shared collector binding. Define how that boundary
obtains the checked complete role union, selects the executor by role, and
rechecks ownership/stops at actual spawn after request validation and collector
setup. Define the FD list as borrowed launch capabilities so collector cleanup
does not close or unlock ancestor leases. Preserve the bounded response and
process-group cleanup contract.

**Required regressions.** Through the real prospective native runtime path,
intercept the final subprocess creation and assert exact full `pass_fds` and
valid next-hop metadata, including execution and executor roles. Assert frozen
module/function bindings are unchanged after both normal and exceptional
runtime exit. Inject a lost role/stop after outer validation but before actual
spawn and require zero child creation. Use local sleeping child/grandchild
processes for later parent-death, output-limit, deadline and cleanup-failure
cases, checking every ancestor exclusion until the final descendant exits.
No provider call is needed for these ownership regressions.

## Bounded correction-contract follow-up — 2026-10-28

Reviewed the appended **Ownership design review: required OD1–OD6 corrections**
in `docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md:271–329` against
the immediate consumer and launch paths. This is a static design follow-up.
Only this report was appended; no project imports, tests, experiments, provider
calls, service actions or source/test edits were performed. The coordinator's
reported fdinfo experiment and floor/executor validation progress were not
independently rerun or inspected. The existing source/test freeze remains a
constraint, not evidence of ownership implementation or live readiness.

**Design disposition.** OD1's canonical role/resource order and consumer
selection, OD3's complete predecessor closure, OD4's leaf/prefix/full graph,
and OD5's entry-owned transfer/remapping contract address their original
design omissions. Their regression requirements remain implementation gates.
OD2's proposed descriptor-specific, nonmutating proof addresses the original
probe/upgrade design defect, subject to the required Linux subprocess coverage.
OD6's private native namespace and qualified/capture objects address shared
collector rebinding. Two concrete integration omissions remain below; the
original six findings are not being restated as six unresolved blockers.

### OD2-R — P1: Carry nonmutating verification through the retained consumers

**Evidence.** OD1 explicitly sends the campaign descriptor to
`CampaignHistory.owned` (plan:286–287), while OD2 requires nonmutating inherited
ownership checks (288–296). That consumer currently calls the frozen mutating
verifier before duplication, calls `flock(LOCK_EX | LOCK_NB)` on the duplicate,
and calls the verifier again from `guard()`
(`tools/inventory_recovery_v3/campaign_history.py:81–113`). The retained job
`prepare()`/`require()` functions also call it
(`tools/inventory_history_job.py:49–66`); `CampaignAuthority.check()` reaches
`require()` and directly verifies the program descriptor with it
(`tools/inventory_recovery_v3/stage_authority.py:59–65`). Stage checks and
launch inheritance have further direct references
(`tools/inventory_recovery_v3/stage_owner.py:29–34`,
`tools/inventory_recovery_v3/launch_handoff.py:95–99`).

**Residual blocker.** Merely verifying the capsule with fdinfo, remapping its
FDs, and passing them to these named consumers does not produce a nonmutating
inheritance/check path. The consumer contract must explicitly replace or
bypass those embedded verification calls, including the unconditional
campaign `flock`, in prospective/private adapters. New role acquisition may
lock its newly opened descriptor; borrowing, inheritance and repeated checks
must only verify ownership already held. Do not patch a frozen/shared verifier
globally to achieve this. This is a missing consumer adaptation requirement,
not a rejection of the proposed fdinfo proof.

**Required regressions.** After initial acquisition, exercise the actual
prospective worker inheritance, remapped legacy job prepare/require, campaign
`owned`/`guard`, authority checks and stage checks with the old verifier made
unavailable and inherited-descriptor `flock` attempts detected. All valid
borrowed paths must succeed without a lock operation. A shared, fresh or
unlocked descriptor at each consumer must fail without conversion, and the
frozen helper bindings must remain unchanged. Keep genuine acquisition of new
job/stage roles distinguishable from these borrowed checks.

### OD6-R — P1: Route the final Popen veto through typed zero-launch publication

**Evidence.** OD6 places a new leaf/lease/stop check after collector setup and
immediately before `Popen` (plan:318–323). The current outer wrapper handles
prelaunch rejection only inside the `require_dispatch`/`bind` try block; its
call to the native launch is outside that block
(`tools/inventory_recovery_v3/runtime.py:193–218`). The inner native closure
already writes `qualification-capture.json` with `status=verified` before
calling the collector (`tools/sol_inventory_runtime.py:113–114`). A typed
`RecoveryStop` is a `RuntimeError` (`tools/inventory_recovery_v3/failures.py:21–27`),
which the current collector's exception list does not catch
(`tools/response_capture_observation.py:104–105`). If that new check raises
before `Popen`, the existing finally path has `process=None`, `reason=None` and
`quiescent=False`; it would write `status=complete`, `process_started=False` and
`group_quiescent=False` (`40–46,148–157`). It would also miss the outer typed
prelaunch/cancellation publication.

**Residual blocker.** The new guard needs an explicit rejection contract in
the private collector/runtime composition. Preserve the original stop or
ownership category and publish coherent, idempotent zero-launch evidence after
collector setup is cleaned up. For USER_STOPPED, connect to the existing bound
cancellation path: its reader requires an error result, no process start,
quiescence, empty captured streams and the original stop binding
(`tools/inventory_recovery_v3/cancellation.py:31–58,80–100`). Do not leave a
verified capture or manufacture a complete process result for a vetoed spawn.
Simply extending the outer try block is insufficient if it then refuses the
collector's already-written process evidence or collides with existing stream
files; define which layer owns this publication. Distinguish an actual
post-spawn failure, which must retain real process/quiescence evidence.

**Required regressions.** Inject USER_STOPPED and lost-ownership failures at
the final guard, after FIFO/stream setup and outer runtime binding. Assert zero
Popen calls, preserved typed failure, consistent nonverified qualification
capture, no process-start record, cleaned FIFO/streams and
`process_started=False`/`group_quiescent=True`. For the stop case, require the
normal cancellation evidence reader to accept the result and retain exact
resume provenance. Repeat cold handling without duplicate publication or
retransmission. Separately fail immediately after a real local child is
created and verify it cannot be mislabeled as a zero-launch cancellation.

## Final bounded design disposition — 2026-10-28

Scope: only the explicit OD2-R and OD6-R correction contracts in
`docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md:331–352`, compared
with the two residual findings above. No other slice was reopened.

- **OD2-R — addressed at design level.** The contract now explicitly covers
  every named prospective consumer, requires private adapters for frozen
  functions, and forbids inherited-descriptor flock, including in campaign
  owned/guard handling. Lock acquisition is limited to newly opened roles.
  The required consumer-path regressions disable the old verifier, detect
  inherited flock, accept valid duplicates and reject invalid ownership
  without changing it. This resolves the residual adaptation omission.
- **OD6-R — addressed at design level.** The collector now owns final-veto
  setup cleanup and returns the original typed zero-launch outcome to one
  runtime rejection publisher. The contract specifies nonverified capture,
  bound rejection, an error process record with no process start and proven
  zero-launch quiescence, exact USER_STOPPED cancellation provenance, and
  validation/reuse of identical evidence on cold handling. Conflicting
  evidence cannot be overwritten, and post-creation failures retain actual
  child identity and cleanup results. This resolves the residual publication
  ownership and typed-outcome omission.

**Disposition: DESIGN CLOSE-READY.** No residual design blocker was identified
in these two corrections. Together with the preceding design disposition,
the bounded ownership design review is ready to close. Implementation must
still prove all previously required regressions; this disposition does not
close implementation findings, validate running suites, lift the source/test
freeze, authorize execution, or imply live readiness.

Only this report was appended. This follow-up used document reads and no
source/test edits, project imports, tests, experiments, provider calls or
service actions.
