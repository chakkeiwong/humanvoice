# Prospective native-consumption floors: bounded findings review

Date: 2026-10-28. Role: sole findings-only inspector.

## Scope and evidence

Static review of the eight requested source/test files against the spending-boundary
section of `docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md`. Direct
native callees and the floor-enabled executor fixture were read only to establish
the concrete consumer paths below. No tests, project imports, gateway calls,
services, inference, master actions, or production-artifact writes were performed.
The only inspector write is this report, through `apply_patch`.

The coordinator reports 88 passing floor/projection tests, including process-death
reserve/settle cuts and unknown-token refusal. That result is reported evidence,
not an inspector-run result. The actual native executor suite was running when
this review was requested; no pass is inferred from its source. The inspected
floor source includes the added immediate guard rechecks and native-parent
directory fsync before head commit. Earlier observations of the pre-fix floor
source are superseded by the hashes below.

There is deliberately no public admission factory or live deployment. Optional
component hooks, the remaining TX3b descriptor/admission work, and retaining the
strict installed-authority comparison are not defects in this slice. A future
public factory must require correctly bound floors and leaf admission predicates.

## Implementation findings

### CF1 — P1: dispatch authority does not inspect retained consumption

**Already acknowledged; coordinator fix queued.**

Location: `tools/inventory_recovery_v3/stage_authority.py:37-67`; consumer:
`tools/inventory_recovery_v3/stage_owner.py:29-38` and
`tools/inventory_recovery_v3/dispatcher.py:28-44`.

The constructor checks the floor's configuration/path binding, but `check()`
never inspects either floor. After a successful claim, remove a retained floor
head/transition, or restore an earlier otherwise-valid account or stage prefix.
The next `owner.check()` still checks admission, stops, descriptors and the plan,
without comparing that resource to its committed floor. The provider launch
check also reloads the local allocation ledger, which does not establish the
shared account/stage prefix. Thus the spending consumer can pass this guard
before the next reserve/settle writer discovers the loss.

Minimal fix: inspect both resources read-only in `CampaignAuthority.check()` when
floors are supplied, before it returns success. Keep inspection independent of
`floors.guard()`, floor mutation and native lock acquisition. A coherent pending
publication remains inspectable; missing/rehashed retained evidence must veto
dispatch. This is the queued local fix, not a request to implement public
admission. Add a post-claim/pre-dispatch mutation check asserting zero additional
provider launches for each resource.

### CF2 — P2: a coherent publication race is reported as accounting corruption

**Already acknowledged; coordinator retrying-status fix queued.**

Location: `tools/inventory_recovery_v3/consumption_floors.py:186-196,238-253`.

`inspect()` reads the head, native value and transition membership separately,
then maps every failed consistency check to `BLOCKED_ACCOUNTING`. For example:
the reader obtains committed head H0; the writer publishes pending H1 and its
transition; the reader then lists transition files using H0's empty membership.
Line 250 rejects a legitimate transition before the final stability check. A
reader that sees a pending head can similarly reject when the native value
changes between its first read and line 253. Both interleavings arise from the
specified publication order, with no lost authority.

Minimal fix: provide a bounded, read-only status reader that retries the entire
observation when publication evidence changed, including failures before the
final comparison. Return a distinct transient/busy result if no stable snapshot
is obtained; preserve accounting failures for stable corruption. Do not acquire
or create native/publication locks, reconcile, or write from status. Strict
writer inspection can remain fail-closed under its existing ownership. Exercise
head, transition and native replacements during inspection, plus unchanged
corrupt evidence, and assert unchanged bytes and mtimes.

### CF3 — P1: cold executor entry cannot reach claim-tail repair after reserve

Location: `tools/inventory_recovery_v3/executor.py:85-97`,
`tools/inventory_recovery_v3/stage_owner.py:67-70`, and
`tools/inventory_recovery_v3/stage_authority.py:73-78`. Direct consumer:
`tools/automatic_call_grant.py:67-74`.

A real reserve cut after the native account replacement, or after the floor
head commit, leaves the reservation in the account while
`account-reservation.json` and `allocation-ledger.json` have not yet been
published. This is an explicitly supported claim tail:
`claim.py:159-177` validates the retained intent and can complete those files.
The direct claim cold-recovery test reaches that repair.

The actual executor does not. It first calls `current.validate()`, whose
`Stage.current_authority()` calls native grant status
(`stage.py:123-126,217-219`). Grant status reads `allocation-ledger.json` for
every account plan and raises `FileNotFoundError` for this new reservation.
Even if the validation obstacle were removed, `owned_stage()` enters
`grant_stage()` before `claim()`, and `grant_stage()` calls the same status reader
before yielding. Repeated cold executor entry therefore never reaches the
existing repair and leaves the legitimate reservation stuck. This is a
deterministic caller-order defect, not merely absent test evidence or missing
public-factory work.

Minimal fix: add a narrowly authorized claim-tail reconciliation phase under the
existing program/campaign, execution/provider, grant and account ownership,
before the first full grant-status consumer. Restrict it to the retained native
claim intent, exact account reservation, prepared marker and already-bound stage
hold; it must not create a fresh reservation or tolerate unexplained missing
ledgers. Split out the existing tail repair if needed so full stage validation
and normal claim remain after reconciliation. Verify cold re-entry through
`executor.execute()` and `owned_stage()` at native-account and head-commit cuts,
including receipt-before-ledger cuts, with one reservation event and no duplicate
provider dispatch. Do not weaken the native status reader globally.

### CF4 — P2: a lawful sibling suffix strands an applied pending transition

Location: `tools/inventory_recovery_v3/consumption_floors.py:238-249,263-265,276-284`;
callers: `native_consumption.py:14-20`, `claim.py:120-124`, and
`stage_authority.py:73-76`.

Take a process-death cut after an owned reserve, settle, or hold is written but
before its floor head commits. The retained pending target is A1. After the
native lock is released by process death, an independent lawful native consumer
appends a suffix, producing A2 with the exact A1 prefix intact. On cold entry,
`inspect()` requires the whole current floor to equal either A1 or the old
committed floor; it rejects A2 before `reconcile()` can use the normal
`EXTENDED` observation path. The native lock held during the later reconciliation
does not undo this intervening, already-completed sibling operation. The same
failure occurs if an `observe` intent is interrupted before commit and another
sibling extends the resource.

Minimal fix: recognize a fully validated extension of the pending *after*
prefix, verify the exact historical target against `target_hash`, commit that
retained pending transition, then record the additional suffix as observation
under the same native lock. For accounts, reconstruct the pending historical
target from its event/plan prefixes and replay-derived counters; checking counts
alone is insufficient. Do not treat a merely changed pending-before account as
successful spending or overwrite sibling changes with the stale target. Add a
pending-after cut followed by an independent native extension and repeated cold
re-entry; retain rejection for altered pending prefixes.

### CF5 — P2: native-after recovery silently recreates a lost transition file

Location: `tools/inventory_recovery_v3/consumption_floors.py:240-249,256-261`;
ordering evidence: `consumption_floors.py:323-333`.

For an owned `reserve`, `settle` or `hold`, `write()` durably publishes the
numbered transition before invoking the native writer. Cut after that native
write but before head commit, then remove only the numbered transition file.
`inspect()` still returns `PENDING_AFTER`: the transition is optional at lines
242-244, and the membership set excludes the missing file. `reconcile()` then
enters `_commit()`, which recreates that file from the pending head and commits
it. This accepts and repairs individual evidence loss after spending, although
that state cannot result from the owned publication order alone. The existing
missing-transition case deletes a fully committed record, so it misses this
pending-after case.

Minimal fix: for owned operations, require the matching numbered transition
whenever the native resource is at or beyond pending-after; reject its absence
without writing. Preserve the valid pending-before/intention-only cut. Handle
`observe` separately: its native extension precedes its observation intent, so
an interrupted observe intent legitimately can lack the numbered record. This
finding concerns lost evidence; it does not claim the present recovery alone
releases tokens or duplicates spending.

## Coverage boundaries and inspected safeguards

- The component cut tests exercise direct `ConsumptionFloors.write()`,
  `claim.claim()` and wrapped native settlement. They establish different
  caller coverage from `executor.execute()`. The floor-enabled executor fixture
  now binds `floors.check = authority.check` and covers pass/nonpass, stop and
  retry paths; its reviewed parameter list does not inject claim account/head
  publication cuts. Its running result is a proof gap, while CF3 is established
  independently by the consumer ordering.
- The unknown-allocation fixture correction is acknowledged and is not reported
  as a defect. Native settlement refuses unknown allocations before seal/account
  advancement in the inspected path.
- Immutable projection removes only the canonical account and grant-stage
  evidence hashes; grant definition, predecessor cursor, source/configuration,
  units and stop contracts remain in the projected value. No additional
  projection defect was established.
- Initial publication checks exact native initial snapshots and an ordered
  seed/head prefix. Once the marker exists, missing heads are inspected and
  rejected instead of recreated. Committed transition membership, identities
  and event/plan or stage prefixes are checked against retained history. CF5
  concerns the narrower owned pending-after exception.
- The native wrappers run floor reconciliation from the account read inside the
  native account lock; stage reconciliation occurs inside the grant lock. Floors
  acquire only their own nonblocking publication lock. No direct native lock
  reacquisition was found in these hooks. Keep the queued authority inspection
  leaf-only and nonmutating so this remains true.
- Guard rechecks immediately precede intent, native write and committed-head
  publication. The native parent directory is fsynced before the head commits.
  These coordinator fixes are present in the reviewed hash and are not open
  findings. Broader descriptor transfer, deployment and public admission are
  outside this report.

## Exact reviewed SHA-256 values

Primary files (raw file bytes):

```text
172ec22d9ad80d44655b3a6b45a2f6644663c77060d588714e8e48b1c15fcc04  tools/inventory_recovery_v3/consumption_floors.py
a7bd7c0a3e134a4dd481228d723463df562bc4813ca87ee37dc5a341c0d0c830  tools/inventory_recovery_v3/native_consumption.py
b7c17f9aeb6fbe871fb04cc8b235b9f54d64de7b86f16303737eec662708f39b  tools/inventory_recovery_v3/installed_authority.py
f96a842313d92c82ad024c1b72c6d0ebf1022f641d4561e918a353a74ee52636  tools/inventory_recovery_v3/claim.py
c50fc16a1cb08428b3f7458748cc57e74d43aee1db70903b1cb852b1e0d74e18  tools/inventory_recovery_v3/stage_authority.py
0cdc5242a7d18ecc395794626355e8f5363c7b10180b3dd0427bd2f09a0814e9  tools/inventory_recovery_v3/stage_owner.py
515642f4b604339c0d2d3f82dcf0024afeeeecefdff90c8b7e323744f232c7d7  tools/inventory_recovery_v3/executor.py
fc390a490e0f8d479ddfc9b3f72d39ab668886bf22a758f4cf36a6a382bdeb19  tests/test_inventory_recovery_v3_consumption_floors.py
8dd01b34d5c952e3f08fffefe43c8e2ed07bf5be596b598d0290ad0ae5fed6fa  docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md
```

Direct caller/validator and fixture references used to substantiate findings
(read only; not a wider audit):

```text
616ac738d08498e417d4a99fed0e686b6edabeeba590df9b4ab7924ddd2fb380  tools/inventory_recovery_v3/stage.py
767d536c023cfa777317950f5e39f1288f522f33dde380e6b8823c815fde1bce  tools/inventory_recovery_v3/dispatcher.py
24cc4b61582ddd5e7aad6c67f154dd3370ae407a93bee8b322a42f07316bd350  tools/inventory_recovery_v3/runtime.py
3d108a9786ce138543c1bf876d6f0f9951210e6a7aca83b39995f7893fb86eb2  tools/inventory_recovery_v3/campaign_binding.py
0c07f02d5123ce34971f054ef6020a86e9be1dfd67720abe23555a70df041bd2  tools/inventory_recovery_v3/reservations.py
025b6f65ef8eac9cb7a6a8f2a395a1628a897833ef4ff748a952dfb06827d210  tools/token_epoch_20261025.py
6f7e8e4aa44ab5c24945103c837997e631ccffb14a92a139e285fae26504e715  tools/automatic_program_account.py
16417c3cca2459181152f9908261298f473c1802523c30c30db3e9e2ad89d024  tools/automatic_call_grant.py
3eca36b689ebb2fcc5a26fbfb14d775e1656e7aa3ad91f38b50cb0ad877d78ad  src/humanvoice/automatic_settlement.py
3e445a4b1d7bafc50e5b33f13df2629ffba3bea2069a695d306f8639138f219e  src/humanvoice/artifacts.py
8aec31df43ebe0044cc39ef55f5a9e64d637b0deb0e51c6c4fd82c1b95319361  tools/inventory_recovery_v3/failures.py
9b5bac6a7c9808f2c4819e57dd0f44e670a36e33d782553bc40a265b4a7f86d5  tests/test_inventory_recovery_v3_executor.py
4320a25f61f057a545eec16332794e25aa99b644d8a1c1035b39d6bf26d33c81  tests/test_inventory_recovery_v3_owner.py
7d5e1a8f43f33a956d22cb6948298e624ee7b829d041be661e9018a29137ed50  tests/test_inventory_recovery_v3_installed_authority.py
```

## Bounded CF1–CF5 repair follow-up — 28 October 2026

This section supersedes the open/closed disposition of CF1–CF5 above, not the
original evidence or its source hashes. Static source review only: no tests,
lint, project imports, gateway calls, services, or production/master changes
were performed. Only this findings file is edited. The spending-boundary and
leaf-authority requirements in the public-admission plan remain unchanged.
There is no public-factory/deployment finding.

The coordinator reports that the earlier nine floor-enabled native executor
cases passed in 869.00 seconds, and previously reported 88 floor/projection
tests passing. At the first follow-up, session 68492 was running three cases
selected by -k claim, not an expanded twelve-case run. The coordinator later
confirmed interruption after 792.57 seconds to repair the known defects, with
zero completed cases and no pass claimed. These are coordinator-reported
results, not inspector-run verification. The residual-repair recheck below
records the separate fast-suite status.

### Disposition

| Finding | Bounded source disposition |
| --- | --- |
| CF1 | Both floors are now checked on every campaign check; original missing veto repaired. A concrete unscoped replay caller failure remains (CF1-R). |
| CF2 | Addressed in source: read-only status retries changed observations on success and caught error exits; stable errors remain errors, and sustained motion blocks dispatch as publication in progress. |
| CF3 | Original missing-ledger ordering repaired by existing-only claim-tail reconciliation before full validation/grant status. Unlocked whole-account comparison still rejects lawful sibling writes (CF3-R). |
| CF4 | Addressed in source: reconstruct/native-validate exact pending target, commit original transition, then observe suffix under native ownership. |
| CF5 | Addressed in source: owned pending-after/extended mutation requires existing numbered transition; only observation publication can synthesize that record. |

### CF1-R — P2: floor validation depends on ambient replay scope

**Locations:** tools/inventory_recovery_v3/stage_authority.py:46,66–69;
tools/inventory_recovery_v3/executor.py:86–90;
tools/inventory_recovery_v3/consumption_floors.py:81–86.

**Concrete caller trace:** CampaignAuthority.__init__() calls check() without
establishing replay scope. Likewise, execute() calls authority.check() before
entering its own runtime.settlement_scope(). The new check calls account floor
status; snapshot validation calls epoch.validate_account() without an explicit
usage reader. With no outer replay scope, its settlement branch calls ordinary
automatic_settlement.completed_usage() (token_epoch_20261025.py:71–76,89–103).

An otherwise valid account containing a settled v3 document stage therefore
reaches the unadapted native settlement reader. That reader invokes
attempt_layout() (src/humanvoice/automatic_settlement.py:97), whose frozen
policy whitelist rejects the document policy version
inventory-document-runtime-v3 with "Recovery limits or eligibility policy
changed" (src/humanvoice/automatic_recovery.py:248–258;
tools/inventory_recovery_v3/runtime.py:16,41–49,63–67). The unadapted allowance
reader also accepts only 500M/600M rather than the stage's 1.1B epoch
(automatic_settlement.py:31–57). A stable snapshot causes status() to rethrow
this error, so publication retry does not solve it. Valid cold authority
construction/executor entry after such a settlement fails; this is not a
failure claim about the still-running session. An enclosing correct
history/settlement scope can mask the defect.

**Minimal fix:** make read-only account-floor validation explicitly own the
appropriate mixed-history/document replay adapter, or accept a bound read-only
usage validator instead of relying on mutable ambient aliases. Cover
constructor and all check entry points, not merely the later executor body.
Preserve native replay/evidence validation; do not skip settlements or weaken
admission. The validator must not invoke authority.check(), floors.guard(),
mutation, or lock-acquiring native account/grant status. A focused cold caller
with a settled v3 prefix and no outer scope distinguishes this implementation
defect from a missing broad integration run.

**Recursion:** no direct check → status → guard → check cycle or native
account/grant lock reacquisition was found in the inspected code.
status()/inspect() are read-only and do not call the floor guard; the document
replay adapter uses non-live runtime validation. The demonstrated problem is
missing replay scope, not an established recursive deadlock. Repeated history
verification is not elevated into a performance finding.

### CF3-R — P2: unlocked byte equality rejects a lawful sibling suffix

**Locations:** tools/inventory_recovery_v3/claim_tail.py:40–44;
tools/inventory_recovery_v3/claim.py:120–188,191–215;
tools/token_epoch_20261025.py:159–164.

**Concrete caller trace:** under_grant() records whole-account bytes before
calling claim(existing_only=True) and compares them after it returns. Those
reads do not own the native account lock. Stage/provider and grant ownership
do not exclude an independent lawful writer to the shared account. A sibling
reserve/settlement may append after the first read, between claim's two
account-lock phases, or after its return. Existing-only repair can correctly
retain the target reservation, reconcile the lawful suffix, and finish the
target receipt/ledger, yet the final comparison raises "Claim-tail repair
changed native reservation authority". The caller reports accounting failure
after a successful narrow repair. This is false failure, not renewed spending
authority.

**Minimal fix:** enforce the existing-only no-account-write property inside
the native account-owned phase (for example, reject an attempted account write
in that invocation), or compare validated monotonic extensions and the exact
retained target reservation instead of unlocked whole-file identity. Do not
wrap the whole call in another account lock: native claim already reacquires
that lock and such a repair could deadlock. One sibling append between the
before-read and claim entry is sufficient focused coverage.

### Claim-tail authorization and pending evidence

- The prevalidation repair is narrow in the inspected callers. Cold
  claim_tail.reconcile() holds execution, executor, and grant locks;
  owned_stage() holds stage/provider locks before entering grant_stage().
  Repair requires an existing native reservation plus the single exact
  retained stage hold and intact grant/account identity (claim_tail.py:20–62).
- claim(existing_only=True) rejects a missing intent and absent/nonexact
  reservation. It binds the persisted plan, exact expected receipt, original
  event prefix, pending intent/prepared marker, and single reserve; it refuses
  settled/sealed work and missing-ledger repair with calls or summary evidence
  (claim.py:88–184). No concrete fresh-claim/provider authorization bypass was
  established. Normal stage validation still follows this tail repair.
- Retained executor.json is accepted only with exactly integer pid and
  status "stopped", in an existing pending tail without calls/summary. The
  marker alone is not ownership: reviewed callers also hold stage/provider
  locks. Keep under_grant() behind that ownership contract; it does not itself
  acquire those two locks.
- Floor validation can validate a pending account after reserve publication
  but before that reserve's receipt/ledger exists. epoch.validate_account()
  processes reserves through _reserve() and replayed counters without reading
  their receipt/ledger. Only settlements require those retained usage
  artifacts. This is not a circular missing-ledger defect; historical
  settlement replay still needs the scope described in CF1-R.
- Latest grant_stage() publishes derived usage only on normal exit
  (stage_authority.py:112–117). Claim-cut exceptions now propagate without
  cleanup grants.status() masking them with missing-ledger failure;
  authoritative account/hold/intent evidence remains for cold repair. The
  queued equivalent lint simplification is not a behavioral finding.

### Repair evidence and remaining proof limits

status() compares observations before/after strict inspection and retries
caught errors when observed publication changed (consumption_floors.py:145–170).
Writers retain strict fail-closed inspection. retained_target() reverses
suffix reserve/settle ceiling effects and slices exact event/plan prefixes,
then native-validates/hashes the reconstructed target (126–143,294–298).
Reconciliation commits that original pending target before observing its
suffix (327–336); owned transitions must already exist (296–309). Source guard
checks and native-parent fsync before head commit remain present. No new
initial-publication, immutable-projection, or owned-transition defect was
established in this bounded recheck.

Added tests cover pending-after extensions, owned-transition deletion, status
retry, post-claim veto, and owned-stage/actual-executor cold cuts in source.
The reviewed status-race fixture publishes an entire mutation inside mocked
inspection before raising; its boundary labels are not independent proof of
every partial-publication interleaving or sustained busy state. The new
pending-extension account fixture uses a reserve as the sibling suffix; the
inverse settlement-suffix counter branch lacks equivalent focused proof in
that fixture. Dedicated existing-only refusal cases would strengthen the
missing/changed intent, foreign hold, and stopped-marker boundaries. These are
integration/coverage limits, not additional implementation defects or requests
for a wider audit. Actual-executor validation remains the coordinator's task;
the three selected claim-cut cases were subsequently interrupted, not passed.

### Exact follow-up SHA-256 values

Raw file-byte hashes read at follow-up conclusion; the original hash block
above describes the earlier revision only.

```
b9a89d960dc5c2efd68fdb8d1a8a9cc94eb11194d6248cc39d16e7271696e686  tools/inventory_recovery_v3/consumption_floors.py
a7bd7c0a3e134a4dd481228d723463df562bc4813ca87ee37dc5a341c0d0c830  tools/inventory_recovery_v3/native_consumption.py
b7c17f9aeb6fbe871fb04cc8b235b9f54d64de7b86f16303737eec662708f39b  tools/inventory_recovery_v3/installed_authority.py
b648ec9236cf7c08e9ca0d56f757a260301a117504ae7fe84809ad1694297980  tools/inventory_recovery_v3/claim.py
a523a55bd2b91e511ce63435ebfd01fa976ea609ed72b107301bcd6bf3efc8d2  tools/inventory_recovery_v3/claim_tail.py
52cd84a9e15ca104d2f69ba79d551654e9fc803cd93675e3c1b1f9fc2923a01a  tools/inventory_recovery_v3/stage_authority.py
0cdc5242a7d18ecc395794626355e8f5363c7b10180b3dd0427bd2f09a0814e9  tools/inventory_recovery_v3/stage_owner.py
13f212712016191401874b3417c2c0cf8130a403334f70ef2ce9d10feb45bcc5  tools/inventory_recovery_v3/executor.py
a93522a0c31e9eb8d5a9a04a6ecd421e3061a33525f511dd530d1aa65e2ebe71  tests/test_inventory_recovery_v3_consumption_floors.py
133de760d6d972825c50a5b10fc4c1f54eb588c786d5f7985bf4b51229b84d20  tests/test_inventory_recovery_v3_executor.py
454f7245c2b2aecbae1800fd3ffeac903f3265ccadadb054d4cc8949ccce9578  tests/test_inventory_recovery_v3_owner.py
0d5b046dd613542e55dc9831813a4c6acc516cd489039e6963c9e84d40b01dc8  tests/test_inventory_recovery_v3_claim.py
7d5e1a8f43f33a956d22cb6948298e624ee7b829d041be661e9018a29137ed50  tests/test_inventory_recovery_v3_installed_authority.py
025b6f65ef8eac9cb7a6a8f2a395a1628a897833ef4ff748a952dfb06827d210  tools/token_epoch_20261025.py
24cc4b61582ddd5e7aad6c67f154dd3370ae407a93bee8b322a42f07316bd350  tools/inventory_recovery_v3/runtime.py
5ced4f768a9288ce83b3b31ce01b86ec7b5ec40d65e97c0ad03ed8169c0acf4c  tools/inventory_recovery_v3/accounting.py
3eca36b689ebb2fcc5a26fbfb14d775e1656e7aa3ad91f38b50cb0ad877d78ad  src/humanvoice/automatic_settlement.py
80633324d2730532b62225dcbf64077859467453b1d10e737f9399e28af8ef84  src/humanvoice/automatic_recovery.py
c7b4d89e3442e7098471f9e681cd35ff37bd8446e446493241d0556eee8f749a  src/humanvoice/automatic_accounting.py
1dd27c86e3b6fe5fe78b9e89e19932de6c65235193f3edf3fe2bb9a52fcf50fb  tools/inventory_recovery_v3/journal_binding.py
645a983eecf7d0458a3ddaa374676ffb1afb4fd0b9016b2735a009654557f583  docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md
```

## CF1-R / CF3-R residual-repair recheck — 28 October 2026

**Disposition: both residuals addressed in the reviewed source. No additional
concrete implementation defect established in this bounded recheck.** This
supersedes the open CF1-R/CF3-R disposition above. CF2/CF4/CF5 are not reopened.
Scope is only the two repairs, local snapshot reuse, and their new regression
fixtures/direct replay dependencies; this is not a public-admission approval
or a broader audit. Only this report is edited, using apply_patch. No tests,
lint, imports, runtime, services, or gateway calls were executed by the
inspector, and no source/test/master/production artifacts were changed.

### CF1-R: explicit read-only settlement replay

- consumption_floors.py:81–88 now supplies an explicit usage_reader that takes
  accounting.verify_settlement(output)["report"]. The epoch validator therefore
  no longer chooses its ambient default reader for the floor snapshot. This
  fixes the concrete constructor/pre-settlement-scope check failure, rather
  than merely moving the executor's scope boundary.
- accounting.py:13–22 chooses the historical verifier for non-document plans;
  document plans receive document validation plus epoch, settlement, routing,
  and conservative-accounting scopes. The document route reaches the retained
  native settlement verifier and its report, not campaign authority or floor
  mutation. The leaf parallel_verification_replay.verify_settlement() at
  lines 35–47 performs synchronous replay; this route does not call its separate
  process-pool warmup routine. No new check/status/guard recursion or native
  account/grant lock reacquisition was established in the inspected chain.
- The new cold fixture genuinely closes its setup replay scopes before
  yielding (tests/test_inventory_recovery_v3_owner.py:188–190). The follow-up
  test constructs an actually settled zero-attempt v3 nonpass stage, first
  demonstrates the unscoped native validator rejects it, then constructs and
  checks CampaignAuthority outside those scopes; it also rejects a changed
  seal and checks unchanged native/floor bytes and mtimes
  (tests/test_inventory_recovery_v3_floor_followup.py:28–53). This is targeted
  proof in source, not inspector execution or proof of every settled-history
  shape. The coordinator reports this test passed its first run.

### CF3-R: no-account-write enforcement under native ownership

- claim_tail.py:40–42 removes the unlocked before/after whole-account equality
  test. Lawful sibling reserve/settle suffixes no longer produce that false
  accounting failure.
- claim.py:194–207 rechecks the exact existing entry inside the validator
  called by native claim while native account ownership is held, and refuses
  any account-path write for existing_only. It preserves the original locked
  floor reconciliation at lines 120–124. Only existing-only calls bypass the
  outer reserve floor wrapper (216–220); fresh claims still use it. No account
  write is permitted on the bypassed path, so this is not an untracked fresh
  reservation path. It also avoids introducing an outer recursive account
  lock around native claim's own lock.
- The previous retained intent, event prefix, exact reserve/receipt, stage
  hold, calls/summary/seal, and executor-marker checks remain. The inspected
  repair is still existing-only; no new claim-tail authorization bypass was
  established. A helper returning False when there is no matching reservation
  is not itself a refusal defect: it performs no repair; direct existing_only
  must reject, as the corrected missing-reservation fixture now asserts.
- New sibling fixtures perform native reserve and optional native settlement
  before entering the actual existing-only claim, then assert unchanged account
  bytes through repair, one target reserve, and completed/idempotent repair
  (floor_followup.py:72–97). Negative fixtures cover missing/changed intent,
  foreign hold, active/changed stopped marker, calls, summary, missing reserve,
  and a fresh existing-only invocation (100–148). These address the earlier
  focused proof gaps; their presence is not a claimed full-suite pass.

### Local snapshot reuse and cleanup

inspect() reads and validates its local native value at 244–245, then passes
that same value and snapshot to _extension() for the seed and each committed
transition (247,278–285). _extension() retains exact path/fixed fields, integer
monotonic counts, and hashes of the corresponding native prefixes (112–124).
Head/transition identity and membership checks and the final native/evidence
re-read remain (239–243,250–307). There is no instance/global cache or reuse
across inspections. Pending-target reconstruction still separately validates
the current value and reconstructed target (131–147,299); the change is not
a promise of exactly one native validation on every pending-state path.
No correctness regression was established from this local reuse.

The new ready-state regression checks one native validation despite retained
floor history (floor_followup.py:238–252). Partial head/native/transition read
interleavings and bounded sustained publication have distinct fixtures
(151–235), and reserve/settle/observe pending targets now receive a sibling
settlement suffix (255–302). These replace the previous narrower fixture
limitations without claiming exhaustive concurrency proof. The yield-then-
persist simplification at stage_authority.py:112–113 preserves normal-exit-only
derived usage publication; exceptional exits still do not mask the original
claim-cut error with grant-status cleanup.

### Validation status and exact hashes

Coordinator-reported status at this recheck: first fast pass had 165 passes
and one missing-reservation fixture failure; that fixture was corrected to
test direct existing-only rejection, and the expanded 171-case suite is still
running. No all-pass claim is made for that run. The earlier three native
claim-cut cases were interrupted after 792.57 seconds with zero cases
completed; they were not a twelve-case run. Static closure of the residuals
does not substitute for the coordinator's pending validation.

Exact SHA-256 values of the reviewed repairs, local callers, fixtures, and
direct replay-delegation references follow. Prior hash blocks are retained as
revision-specific evidence, not substituted for these bytes.

```
c03d2b3b4df569c10390e5410799afc7e041d6ee7261fc959a00669048b766c4  tools/inventory_recovery_v3/consumption_floors.py
8d279268b33fcfd76c30e5d8f17b325734f1df8c4e4398b45e7c5b878ad437aa  tools/inventory_recovery_v3/claim.py
2ee50f62eb8a92c28adc699545e3e93ed78f660314aa9a9c13d7967dfb50ac41  tools/inventory_recovery_v3/claim_tail.py
ef0440ddff54c5ceeb44d58d82204442f50db30b95822b117a32d74c2333b465  tools/inventory_recovery_v3/stage_authority.py
5ced4f768a9288ce83b3b31ce01b86ec7b5ec40d65e97c0ad03ed8169c0acf4c  tools/inventory_recovery_v3/accounting.py
24cc4b61582ddd5e7aad6c67f154dd3370ae407a93bee8b322a42f07316bd350  tools/inventory_recovery_v3/runtime.py
13f212712016191401874b3417c2c0cf8130a403334f70ef2ce9d10feb45bcc5  tools/inventory_recovery_v3/executor.py
0cdc5242a7d18ecc395794626355e8f5363c7b10180b3dd0427bd2f09a0814e9  tools/inventory_recovery_v3/stage_owner.py
025b6f65ef8eac9cb7a6a8f2a395a1628a897833ef4ff748a952dfb06827d210  tools/token_epoch_20261025.py
a892e953476509945a9dbc22c21caa28dbc7ab35d532186b77665453151dc7b6  tools/parallel_verification_replay.py
1346fd80eb12fedd81eecd273ce0b0d9aff4f549965c755cf2685665ddd7b764  tools/qualification_capture_runtime.py
b4b3f4032af71ef23a7fcc95640c609b20388487deea7a065b48ecce40cfd3b3  tools/inventory_recovery_v2/qualification.py
4f7e49bab9bd5355dec597d058e438633ed9edc48c9e132ead27c90cbb07c546  tools/inventory_recovery_v2/runtime.py
78b340353ebd39e4cc6d56f4434d32f51594e839fb78fe2aa85c92a15db36a95  tests/test_inventory_recovery_v3_floor_followup.py
2cb95e54da5b6f6be512696712bcc007244496b104b9d673e2c51c5f0ac878b5  tests/test_inventory_recovery_v3_owner.py
a93522a0c31e9eb8d5a9a04a6ecd421e3061a33525f511dd530d1aa65e2ebe71  tests/test_inventory_recovery_v3_consumption_floors.py
```
