# Native consumption-floor execution — 28 October 2026

Prospective TX3b spending-boundary slice. Public dispatch remains blocked;
no deployment, provider calls or production authority changes are authorized
by this report. Source and tests are coordinator-owned; one bounded findings-
only inspector reviews this slice. No historical v2 files are edited.

## Trace and repair

Whole-account installation equality rejects lawful spending, but dropping it
without a durable prefix would permit rollback after restart. The three
native mutation paths are grant-stage holds, epoch account claims, and native
settlement (normal success, failed terminal, and cold terminal reconciliation).
The prospective floor helper binds exact configuration, campaign-binding,
account, immutable grant bytes and initial account/stage prefixes. Immutable
installation projection removes only account and grant-stage hashes; old
cursor, grant definition, installed units and predecessor evidence remain.
The projection is not yet used to relax any live handover guard.

Runtime writes retain pending head → immutable transition → native mutation
→ committed head. Cold entry recognizes exact before/after native state; it
never guesses or reapplies a native write from the floor record. Pending-before
retries must recompute the exact native target through the original writer.
Pending-after commits the retained floor once. Sibling extensions retain an
observed prefix; deleted/rehashed-shorter suffixes and missing transition
membership fail. A missing head cannot be initialized after spending.
Unknown-token allocations remain reserved. Native account/stage directory
is fsynced before publishing a committed floor, supplementing the unchanged
native writer's existing file fsync.

Private function namespaces wrap native account I/O inside native locks,
without globally changing historical functions or acquiring their locks
recursively. Optional component hooks are not production admission: the future
public factory must require the independently admitted floor binding.

## Evidence and pending validation

### Crash recovery update

The machine restart ended prior test handles and removed `/tmp` reports.
The initial three executor-cut tests had already been deliberately interrupted
after 792.57 seconds with zero completed cases to repair confirmed defects.
The later focused run had not produced a final result before the crash.
Neither run is accepted as passed or described as still running.

The retained independent recheck closes CF1-R/CF3-R: floor account snapshots
use the explicit native mixed-history verifier; existing-only repair forbids
account writes under native ownership instead of comparing unlocked bytes.
Local snapshot reuse avoids repeated validation of the identical value within
one inspection only; no cross-inspection cache is introduced.

Recovery found two test-only defects: the native-read cut patched `read_text`
although native JSON uses `read_bytes`, and sustained-publication injection
recursively entered sibling reservation from a patched account read while
the sibling already held its native account lock. The corrected hooks pass
all 171 focused cases in 18.92 seconds; Ruff passes. This is not evidence
about the cause of the machine crash. JUnit now resides on SSD at
`.localresources/floor-followup-recovery-20261028.xml`.

The validation runner now provides fixed `floors` and `executor` actions,
durable source/authority/test-membership receipts and boot identity, and
process-group cleanup on bounded timeout or interruption. Four runner tests
pass in 2.52 seconds, including an interrupt-ignoring surviving child.
The exact-member floor suite completed: 850 passed in 1033.08 seconds with
16 workers and unchanged source and production authority. Its retained receipt
was independently read as pass, with exact membership and all hashes present.
Evidence directory: `validation/4af4f4baca1a6c09bc5f/floors-5d666d370329`.

Subsequent runner review found VR1–VR3: final mismatch could still publish pass,
ordinary leader exit could leave descendants, and cleanup had unbounded waits.
Repairs protect final acceptance, clean all exit paths, and report bounded
incomplete cleanup with original failure retained. Thirteen runner cases pass
in 10.36 seconds and Ruff passes; follow-up review is pending. The 850-case
receipt predates this harness change. Fresh fixed floors and executor validation
must complete on frozen source before promotion. No live dispatch is implied.
Runner evidence: `.localresources/validation-runner-recovery-20261028.xml`.
The residual VR2-R observation-error branch is repaired and independently
closed. Fifteen runner tests pass in 10.59 seconds; retained JUnit is
`.localresources/validation-runner-recovery-vr2r-20261028.xml`. Source/tests
are now frozen. New exact floors validation collected 861 cases with 16
workers at `validation/5710efeb418e12455bfe/floors-ea2e56291fcf`; all 861 pass in
1037.27 seconds, with source and authority unchanged. Executor validation at
`validation/5710efeb418e12455bfe/executor-9323948631d4` fails the 1800-second
bound after 11 passes. The oversized split reaches a passing sealed terminal
but final repeated execution/accounting assertions do not finish before timeout.
The validator records terminal failure, confirms unchanged source/authority and
completes cleanup. A bounded profile, not a blind rerun or raised deadline, is
the next step. Both source/test-bound processes are finished.

### Historical pre-crash evidence

- Prior configuration slice: 738 exact-member tests pass in 211.63 seconds,
  unchanged source/harness/authority, `campaign-binding-validation/ce9e31a2e13c`.
  Historical after the current floor source change, not current release proof.
- Initial floor component set: 36 pass in 7.13 seconds, 16 workers.
- Expanded native reserve/settle crash matrix plus installed projection:
  88 pass in 8.87 seconds, 16 workers. Test-only unknown-allocation fixture
  mistakes were corrected to use the real receipt-bound wait and native
  recovery runtime; no production validator was loosened.
- Actual native executor uses floors for all nine existing fault routes;
  those pass in 869.00 seconds (16 workers), including oversize split successor,
  normal/failed settlement, stop/resume and cold terminal reconciliation.
  `/tmp/humanvoice_floor_executor_20261028.xml` retains JUnit. This receipt
  precedes CF1–CF5 repairs and is not current release authorization.
- Full exact-member release is not run or admitted for this source.

## Bounded review: required repairs

The review identifies CF1–CF5; none is hidden by the passing component tests.
CF1 requires read-only floor inspection at every campaign authority check,
not merely at the writers. CF2 requires bounded coherent-snapshot retry for
concurrent status reads. CF3 establishes a caller-order failure: native grant
status reads the missing allocation ledger before cold executor entry reaches
claim-tail repair. Add a no-new-reservation reconciliation phase under exact
stage/provider/grant/account ownership before the first full grant-status
consumer. It must require the existing claim intent, exact reserve and bound
stage hold. CF4 requires pending-after plus independently validated sibling
growth to commit the original transition then observe the extension, never
overwrite the sibling or accept changed pending-before as applied. CF5 requires
the already-durable numbered transition for owned pending-after mutations;
its deletion is corruption, unlike a legitimately incomplete observe intent.

The prior executor validation completed before source repair. CF1–CF5 first
repairs are now implemented. Read-only authority checks inspect both floors;
status retries coherent evidence changes; pending-after siblings reconstruct
the exact historical native target before committing the original floor and
observing the suffix; missing owned write-ahead transitions are rejected.
`claim_tail.py` repairs only already-reserved exact claim tails before full
grant-status consumers; native claim's existing-only mode cannot allocate.
Prospective grant-stage exception cleanup no longer masks the original claim
failure by trying to derive usage from a not-yet-published ledger.

Floor/claim/owned-stage regressions pass 151 cases in 16.05 seconds, 16 workers.
Actual executor entry adds native-account/head/receipt cut cases; that bounded
three-case validation is running on frozen source. Host process inspection
finds all three active workers CPU-bound rather than waiting on a native lock;
this observation is not a pass or a bounded-runtime proof. Same inspector's
follow-up closes CF2/CF4/CF5 and retains CF1-R/CF3-R: cold floor checks need
explicit mixed-history replay, and unlocked account-byte equality can reject
a lawful sibling append during exact existing-only claim repair.
Exact-member focused and full release validation remain required after fixes.
Report: `INVENTORY_RECOVERY_CONSUMPTION_FLOORS_REVIEW_2026-10-28.md`.

## Remaining admission boundary

Still required: complete descriptor lifetime across monitor/worker/campaign/
provider, mandatory floor binding in externally approved public admission,
cold transaction recovery, unspent stale-plan retirement/reprepare, receipt-
only progress, bounded ancestry replay, public successors/fallback and combined
soak, frozen dependency-complete release and actual no-call preflight. Only
then group deployment/budget/launch host approvals and verify a new manuscript
receipt. Current production remains 166 retained / 439 unfinished.
