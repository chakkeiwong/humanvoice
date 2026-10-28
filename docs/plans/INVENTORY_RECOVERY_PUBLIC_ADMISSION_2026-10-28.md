# TX3b public admission and ownership implementation contract

Prospective follow-on to the reviewed TX3a offline binding. This document does
not authorize deployment, inference, budget changes or edits to frozen history.

## Required public composition

1. Derive candidate root from source-bound preparation; do not let a caller
   select arbitrary seed, grant, account, stops or commands. Require the full
   `campaign-binding.json` publication and native seed/journal relationship.
2. Derive the predecessor chain from installed historical authority at transfer
   time. Preserve predecessor monitor/job exclusions, exact stop roots, shared
   program/stage ownership and original restart ceiling minus all charges.
3. Separate transfer-time observations from runtime authority: installed units,
   fixed configuration, frozen predecessor evidence and authorization remain
   immutable; account/grant-stage suffixes and prospective cursor must be
   monotonic under committed runtime floors. Do not repeatedly compare the
   entire mutable account to `installed_authority.capture()` from deployment.
4. Build canonical `execution_authority` for `CampaignAuthority` with exactly
   five fields: `program_base`, `supervisor_root`, `account`, `grant`, and
   `grant_identity`. Bind `recovery_journal` and independently derived
   `stop_bindings` at configuration top level, matching their consumers.
   Include exact fixed worker,
   campaign-execute, campaign-verify and campaign-repair commands, cwd, human
   approval settings, model-policy and current source/config identity.
5. Keep candidate configuration nondispatching until a separately verified
   release/preflight/host-authorization record binds all these fields. Neither
   a fixture callback nor an `authorized_by=user` value written by the program
   establishes host permission. Never infer approval from historical admission.
6. Share program/campaign/job ownership across monitor → worker → campaign.
   Validate inherited descriptors before any new grant hold or native claim.
   Preserve locks until all child provider processes are quiescent. Reconcile
   according to the closure plan's phase table before constructing StageOwner.

## Tests required before promotion

- Positive native initial stage, cold reopen and lawful sibling reserve/settle
  growth while immutable installation identity remains unchanged.
- Negative absent/stale/rehashed admission, skipped stops/predecessors, foreign
  command/cwd/account/grant/journal, symlink aliases, changed source or unit,
  replayed desktop/host authorization and partial deployment.
- Real subprocess ownership: parent death, surviving worker/provider, missed
  acknowledgement, reused PID, descriptor omission/substitution and duplicate
  supervisor must not permit parallel spending or duplicate restart charges.
- Both public cold commands must converge at every pending transaction cut;
  pending successor cannot be allocated before head/cursor/repair commit.
- Read-only status tolerates coherent pending publication but cannot reconcile
  writes or dispatch. Integrity loss must remain distinct from transient I/O.
- Account floor advancement needs write-ahead receipts at the spending boundary;
  do not claim initial TX3a floors alone protect subsequently appended suffixes.

## Ordered completion

Implement and test canonical configuration and admission first, then runtime
transfer/descriptor composition, then public cold-entry reconciliation. Keep
source frozen for each matching validation receipt. Follow the master
repair → retest → bounded review → refresh loop. Do not repeat actual
production-data preflight until the public implementation and full release
tests are complete.

### Source freeze and configuration bootstrap

The canonical candidate directory must be computed from `review.sources()`
before reading its preparation, not supplied by a command argument or inferred
from whichever historical directory was most recently modified. The previous
production-data preparation finished nonpass and its receipt fix was tested.
Any subsequent source edit makes earlier preparation historical; do not relabel it
as a release for the new code or repeatedly rerun this expensive gate while
implementation is still changing.

Avoid a source/configuration hash cycle: the source contract hashes code and
fixed policy inputs, not generated configuration or preparation output. The
configuration derives the candidate root from that source identity, binds the
completed native preparation/binding, and includes the source identity. The
later release and host admission bind the resulting configuration identity.
No generated file may become an input to its own source-root calculation.

28 October execution: `configuration.py` implements the read-only candidate
and `public.py` the isolated inspection CLI. Final exact-member focused tests
pass 738 cases in 211.63 seconds; bounded configuration review is closed. No runtime
factory or admission is claimed. All five live actions explicitly reject
before inspection, authority writes or inference. Full dependency bundling,
mutable floors and public ownership composition remain required.

Bounded implementation review found C1/C2: require the final ownership-preflight
evidence rather than treating initial campaign binding as preparation completion,
and disable shared diagnostic publication during native read-only warmup. Both
repairs are implemented and native-tested. Completion is rederived using native
request ownership and first-pair checks on an immutable initial journal; any
missing membership is rejected, never filled. Original preparation-authority
bytes bind its observation to the prepared anchor and account/stage floors.
Native settlement warmup remains active but uses its existing nonpublishing
mode. Bounded follow-up closes C1/C2 and the exact-type residual C1-R; final
exact-member validation passes 738 cases with unchanged source and authority.

The first implementable slice is an independently derived, read-only
configuration candidate: exact isolated-Python action commands, canonical
account/grant/journal, initial qualified profile, ordered routing policy,
inherited plus prospective stop roots, and cumulative restart/generation
ceilings. Mutation tests must rehash a changed candidate and still be rejected
by fresh independent derivation. Configuration inspection must never create
an admission, consume authority, reconcile a pending transaction, or dispatch.

### Installation identity versus mutable runtime

Only the shared account and grant-stage membership are mutable within the
historical installation capture. The old campaign cursor belongs to the
sealed predecessor and must remain fixed; the new campaign cursor is a
separate prospective authority. Grant definition, installed units, predecessor
configuration/adoption/job evidence, approval settings and source identity
remain immutable. Do not drop the old cursor or grant from comparison when
removing account-byte equality.

An immutable projection alone is not a live guard. It must be combined with
native account validation and durable monotonic account/stage floors advanced
at every owned reserve/settle boundary. Tests must distinguish lawful sibling
growth from a validly rehashed shorter suffix, and reject the latter after
cold restart. No runtime use of a relaxed installation comparison is admitted
until those write-ahead floors and shared ownership are composed.

### Runtime spending-boundary implementation order

Code trace confirms three account writes that must share one durable floor:
`stage_authority.grant_stage` publishes the stage hold; `claim.claim` invokes
the private guarded native account writer; `executor` settles through the
native account implementation in three terminal paths. A read-only admission
check must not take grant/account locks recursively inside these writers.

1. Retain the transfer capture unmodified. Build a separate immutable projection
   excluding only account and grant-stage bytes, not the grant definition,
   installed units, predecessor cursor, source or original stop contracts.
2. Bind initial runtime-floor authority to the admitted configuration and native
   campaign binding. Persist write-ahead intent before account/stage mutation,
   then commit its monotonic prefix after the exact native write. Never create
   a missing head after spending. Read-only checks can recognize a coherent
   pending publication but cannot complete it.
3. Reconcile the exact pending target under existing program/campaign ownership
   and the same native spending lock. Unknown-token reservations stay held.
   Account reserve, account settle and stage-hold writes each need tests for
   process death before intent, after intent, after native write and after head
   commit; repeated cold entry must converge without duplicate charges.
4. Independently validated lawful sibling extensions may advance the observed
   floor under shared ownership; reject lost/rehashed shorter prefixes after
   cold restart. Do not replace native account/receipt validation with hashes.
5. Only after these writers are wired may runtime installation checks stop
   comparing entire account bytes. Keep candidate derivation as a transfer-time
   reader; do not call it recursively from `CampaignAuthority.check()`.

Required negative tests also cover incomplete first publication, missing head,
foreign account/grant, interrupted settle after seal, reordered events, changed
immutable grant/old cursor, stop/owner veto at every publication, and concurrent
status reads. These are not satisfied by current offline binding floors.

28 October spending-slice execution: `consumption_floors.py` retains the exact
configuration/campaign seed, immutable grant bytes, initial account and stage
prefixes, with native validation. The prospective claim, grant-stage and all
three executor settlement routes have floor hooks. Private native function
namespaces place writes inside their existing locks; floor checks do not take
grant/account locks recursively. Publication is pending head → immutable
transition → native write → directory fsync → committed head. Cold recovery
commits a verified native-after state or requires recomputing the exact pending
native-before write. It does not invent native account receipts or release
unknown-token allocations. Component/process-death coverage is implemented;
actual native executor validation and bounded review are underway.

The public factory must require these floors and validate their seed against
the independently admitted configuration and full native binding. Optional
component hooks are not a deployment bypass. The immutable installation
projection excludes only account and grant-stage hashes and is not yet used
to relax live handover checks. Do not call this slice full TX3b completion.

### Next ownership slice: concrete lock and callback order

The native account writer already owns its account lock; the stage owner holds
the grant lock across execution. Therefore floor publication takes only its
own nonblocking publication lock, never reacquiring account/grant ownership.
The public authority must supply a leaf stop/descriptor/admission predicate:
it cannot recursively call configuration derivation, floor mutation, or the
same lock-acquiring native readers. Inspect floors read-only on dispatch checks;
reconcile only at owned native mutation entry. Read-only status must retry
coherent concurrent publication, not label it permanent corruption.

1. Validate external admission and immutable installation projection, deriving
   exact old monitor/job paths and historical stage locks from that admission.
2. Take old monitor/job exclusions, prove old owners dead and stage quiescence,
   and retain historical stage locks rather than merely probing them.
3. Take the shared program lock, then new campaign lock. Do not run the old
   shared-lock probe against the already-held program lock. Validate native
   floor initialization under grant then account lock before new spending.
4. Bind canonical role/path membership in a process-local inherited capsule.
   Validate each descriptor is the exclusive owner of the exact inode; never
   accept an independently opened descriptor just because it names that inode.
5. Forward every fixed descriptor plus the job lock through monitor → worker
   → campaign. Provider execution receives the same union plus stage execution
   and executor locks. Keep those capabilities until descendants are quiescent.
6. At each edge test real child survival after parent death, missing/substituted
   descriptors, duplicate launch, pre-ack death and no repeated restart charge.
   Native public cold entry remains blocked until this graph is composed.

Required host actions remain deployment/limit admission and launch only after
release; none is requested while the implementation is not ready. The host-
approved exact fixed command is the trust root, not a generated JSON field.
The offline test runner must not be mistaken for a live gateway process.

### Recovered implementation trace and next executable slice

28 October post-crash trace confirms the descriptor loss at three concrete
edges: `launcher.launch` passes only the new job handle; `launcher.worker`
passes only that job handle to the campaign; `stage_owner.owned_stage` resets
the provider execution context to its executor handle. The active bounded
response collector also calls Popen with only `lock_fd`. Fixing only the
context variable would therefore leave the provider edge broken. Frozen
collectors cannot be edited; the prospective runtime must bind a private
collector implementation that forwards the verified union.

The next source slice is a canonical process-local ownership capsule, followed
by the immutable runtime installation guard and public admission factory.
Derive role/path membership from the admitted configuration: predecessor
monitor/job exclusions, historical execution/executor locks, shared program
lock, prospective campaign lock and monitor/job ownership. Each child receives
the complete ancestor union plus its own added locks. Verify exact roles, paths,
inode identity and exclusive open-file-description ownership at every edge;
same-inode fresh opens are not inherited ownership. Reject omitted, duplicate,
substituted or extra descriptors. Never reacquire ancestor locks in children.

Keep the lifetime graph separate from admission permission: possessing locks
does not grant live execution. The public factory must separately require the
fixed externally approved launch, exact release/preflight/configuration, native
floor seed and all stop bindings. Its runtime check must read immutable
installation evidence directly rather than call `capture()` or `derive()`:
those transfer-time readers include mutable account bytes and expensive replay.
The native floor readers remain the authority for account/stage evolution.

Verification for this slice uses real subprocesses and temporary locks: kill
each parent after child acknowledgement, retain a sleeping grandchild, and
require competing acquisition to fail until the final descendant exits. Cover
foreign/fresh descriptors, replacement inodes, incomplete capsules, existing
stops, interrupted acquisition and exception unwinding. Do not enable live
public commands from these component passes. Both fixed floors and executor
validation must first finish on the current frozen source.

The prospective `ownership.py` interface will separate three operations:
`expected(configuration)` derives the fixed ordered role/path mapping;
`acquire(configuration, check)` takes those exclusions in the documented order;
`inherit(configuration, capsule, check)` validates and duplicates inherited
open-file descriptions without independently reacquiring locks. A lease is
bound to its creating PID/boot/start identity, has an explicit active lifetime,
and offers `check()` plus `capsule()` for checked spawn arguments. Capsules
include configuration identity, exact ordered roles/paths/descriptors and inode
bindings; they are process capabilities only, never persistent permission.
Callers cannot supply alternative lock paths or extend membership through an
environment variable. Child roles derive the permitted job/stage additions
from independently checked request and native plan evidence.

Transfer-time acquisition must first validate predecessor records and take
their monitor/job exclusions. Then prove predecessor owners are dead and hold
every historical stage execution/executor lock. Take the shared program lock,
prospective campaign lock and prospective monitor lock, checking stop/admission
between each acquisition. A busy lock unwinds all previously opened handles.
Do not repeat native shared-lock probing after taking these locks. At runtime
each check verifies the complete held set, immutable installation projection,
stop predicates and native floors without invoking transfer-time derivation.

The initial component can accept an already-derived exact ordered mapping for
temporary subprocess tests; public factories must derive that mapping themselves.
No generic caller-selected capsule may reach public execution. Component tests
must make that boundary explicit and keep `public.py` live actions rejecting.
The subsequent integration patch adds complete capsule forwarding to both
launcher edges and the provider collector, plus native executor coverage.

### Ownership design review: required OD1–OD6 corrections

The bounded review is recorded in
`docs/reviews/INVENTORY_RECOVERY_OWNERSHIP_DESIGN_REVIEW_2026-10-28.md`.
Its six findings are requirements for the implementation, not closed code
findings. The exact contracts below replace ambiguous parts of the interface.

- **OD1, role derivation and consumers.** `expected(configuration, role, job,
  stage)` derives an ordered mapping; job and stage are optional only for roles
  that do not yet own them. Job evidence must match the checked immutable
  request; stage evidence must match committed campaign cursor/native plan.
  Base order is predecessor monitor/jobs, historical execution/executor locks
  excluding the one separately bound program path, program, campaign, monitor.
  Worker/campaign add the exact job lock; provider adds current execution and
  executor locks. Reject duplicate resources, aliases and shared inodes rather
  than silently removing conflicting roles. Monitor entry consumes its held
  descriptor, and CampaignHistory.owned receives the campaign descriptor.
- **OD2, nonmutating ownership proof.** Do not use the frozen helper's flock
  probe as proof of preexisting ownership. On this Linux host inspect the
  descriptor-specific `/proc/self/fdinfo` lock entry and require a whole-file
  advisory FLOCK WRITE for the exact stat device/inode, with stable descriptor
  and path identity. Reject shared/unlocked/fresh opens without flock or any
  attempted conversion. Missing/unsupported fdinfo is an ownership failure.
  A local temporary-lock experiment distinguishes exclusive/dup (WRITE),
  shared (READ), and fresh/unlocked (no entry); subprocess regressions must
  additionally prove inherited ownership after parent death.
- **OD3, complete runtime closure.** Retain every predecessor snapshot's
  config/state and exact job receipt/directory membership, plus the independently
  derived historical qualification plan/lock membership. Recheck that closure
  after exclusions and at runtime without capture/derive/proposal. Combine it
  with immutable installation evidence and native mutable floors; an immutable
  projection alone is insufficient.
- **OD4, acyclic predicates.** Acquisition/inheritance use a leaf check of
  external admission, immutable evidence and stops which never calls a lease,
  CampaignAuthority, mutable floors or a lock-acquiring native reader. Each
  acquired/duplicated prefix is checked nonmutatingly; only the completed set
  becomes active. Execution composes leaf → complete lease → read-only floors.
  Native write hooks call the leaf/lease predicate, never recursively enter
  CampaignAuthority or reacquire native locks.
- **OD5, descriptor lifetime.** The executable entrypoint owns incoming FDs.
  It validates the complete capsule, duplicates into its lease, regenerates
  legacy job/next-hop capsule fields with the live role descriptors, then closes
  the transferred originals. Rejection closes explicitly received descriptors
  only within that process-entry contract; borrowed component checks never
  close caller FDs. Scope exit closes duplicates, never calls LOCK_UN on a
  shared open-file description. Unconsumed incoming capsules cannot survive to
  authorize a second lease or reused descriptor number.
- **OD6, private spawn binding.** Clone the native runtime function namespace
  and its qualified/capture dependency objects for the prospective invocation;
  bind only the private bounded collector there. Do not reassign shared module
  attributes. The collector borrows the complete lease FD union, selects the
  executor by role, and rechecks leaf/lease/stops immediately before Popen after
  setup. Its cleanup owns child streams/processes, never ancestor descriptors.

Acceptance includes the review's six negative/positive matrices: shared/fresh
FD rejection without lock conversion, exact role and lock-order tracing, all
predecessor membership mutation cuts, veto/unwind at every acquisition boundary,
FD remapping/reuse and surviving grandchild lifetime, and real native runtime
Popen inspection with unchanged frozen bindings on success and exception.

The correction-contract follow-up adds two mandatory integration details:

- **OD2-R:** every prospective consumer must use the nonmutating verifier,
  including worker inheritance, private legacy job prepare/require, campaign
  owned/guard, campaign authority and stage checks. CampaignHistory.owned must
  skip flock when receiving an inherited descriptor; only acquisition of a
  newly opened role may lock it. Bind private adapters for frozen functions;
  do not replace their globals. Test the actual borrowed paths with the old
  verifier unavailable and inherited-descriptor flock forbidden. Valid dups
  pass; shared, fresh, unlocked and replaced descriptors fail unchanged.
- **OD6-R:** the prospective collector owns final pre-Popen rejection cleanup
  and returns a typed zero-launch outcome to the runtime's single rejection
  publisher. It catches the original stop/ownership failure, closes and removes
  FIFO setup, leaves empty regular streams, and records no process-start file.
  The runtime publishes the nonverified qualification record, bound rejection
  and error process record once, with process_started=false and quiescence=true.
  USER_STOPPED enters the existing exact stop/cancellation evidence path.
  Cold handling validates/reuses identical evidence instead of retransmitting
  or overwriting conflicts. Failures after a child was created retain its real
  process identity and cleanup outcome; they cannot become zero-launch proof.
  Test both final-guard categories through the normal evidence reader, plus
  repeated cold handling and failure immediately after real child creation.

### Implementation units after the executor gate

Keep the reviewed ownership design, but execute it in the following testable
units instead of enabling the public commands in one large edit:

1. Nonmutating Linux descriptor proof and private legacy job adapters. Inspect
   descriptor-specific fdinfo twice around stable fstat/path identity; require
   one whole-file FLOCK/ADVISORY/WRITE entry for the exact device/inode. Reject
   bool/stdio/closed/shared/unlocked/fresh/aliased/replaced descriptors without
   invoking flock. Adapt every prospective borrower, including campaign owned
   (which skips acquisition for inherited descriptors), stage, handoff and
   authority. Exercise actual borrowers while the old verifier and inherited
   flock are forbidden. This component alone grants no launch permission.
2. Canonical role mapping, fixed lock-order acquisition and process-local lease.
   Bind configuration and checked job/stage membership, reject role/inode
   conflicts, duplicate inherited descriptors, close owned incoming references
   at executable entry only, and pass the complete union at both launcher
   edges. Test prefix vetoes and real descendants surviving parent death.
3. Immutable predecessor closure and acyclic admission predicate, composed with
   consumption floors. Capture complete predecessor receipt/directory and
   qualification membership at transfer; runtime reads that closure without
   transfer-time capture/proposal or native lock reentry.
4. Private provider collector and typed final-spawn rejection publication,
   followed by real public monitor/worker/campaign composition. Test exact FD
   union at Popen, final stop veto, zero-launch/cold reuse, and real post-spawn
   failure evidence. All OD1–OD6/OD2-R/OD6-R matrices remain required.

The 28 October temporary-process probe confirms that a child retains a WRITE
fdinfo lock after the parent closes its descriptor; a competing open remains
excluded until the child exits. This diagnostic is not regression acceptance
and does not replace the real parent-death/grandchild tests.

### Spending-slice review repairs before promotion

28 October ownership execution update: descriptor OD2/OD2-R is independently
closed after DR1 repaired the parent-death false-pass oracle (430 adjacent
passes). Canonical roles/leases are implemented; LR1/LR2 review found stale
transfer cleanup could close reused live descriptors and early rejection did
not retire its capsule. IncomingTransfer now retires envelope/nonce before
callbacks or cleanup ownership. Independent recheck closes both; 173 combined
cases pass. Real creator-death tests cover monitor/worker/campaign/provider
unions. These component closures confer no live authority.

The launcher now has a complete-lease path at both monitor→worker and
worker→campaign edges, with explicit entry consumption, remapped legacy
capsules and final guards after log setup. Nine new edge cases exercise real
cold processes, pre-ack/monitor/worker death, missing union roles, mismatched
legacy roles and immediate pre-spawn stops. Final combined 187 cases pass in
7.49 seconds with 16 workers; Ruff passes. LU1–LU3 are independently closed:
24 selected cases pass in 26.18 seconds with unchanged hashes. Post-spawn
reporting failures retain live children, fallback rejects ambient capsules
before intent, and malformed incoming transfer cleanup is replay-safe.
Public execution remains blocked until the following closure/admission and
private provider-collector units, TX4–TX7 and final release/preflight pass.

The immutable runtime closure must be captured once at transfer from the
independently derived adoption, then bound into configuration/release. Retain
each predecessor config/state and exact receipt/directory membership, all
qualification plan membership/bytes, installed immutable projection and exact
shared lock set. Lock files that acquisition may create are explicit canonical
slots, not immutable receipt members; ignore no other additions or removals.
At runtime, verify the retained closure directly without capture/derive/proposal
or native lock acquisition. Recheck after exclusions and immediately before
spending. Native account/stage floors remain a separate monotonic check.

Implementation checkpoint: runtime_closure.py and runtime_predicates.py now
implement this component and configuration.py binds the captured closure.
244 combined cases pass in 12.66 seconds with 16 workers; Ruff passes.
Runtime dispatch rejects pending floors; owned mutation uses the leaf/lease
callback without floor recursion. One bounded implementation review is active.
StageAuthority integration and private provider collection remain next; no
public factory or live admission is implied. Evidence:
docs/reviews/INVENTORY_RECOVERY_RUNTIME_CLOSURE_EXECUTION_2026-10-28.md.

The bounded component review identified RC1 (stop deletion/rollback accepted)
and RC2 (new source members omitted). Repairs add direct *.py source inventory
verification and a mandatory separately authenticated monotonic-control reader
to RuntimeLeaf. stop_authority.py validates every root's complete stop chain,
initial transfer stop floor, current latest bytes and latest exact authenticated
resume. The leaf never publishes history. A config-only callback is insufficient.
154 focused cases pass in 7.32 seconds; bounded recheck is active.

Public integration must supply the real control producer/reader: authenticate
host stop/resume provenance, retain durable monotonic heads outside freely
rewritable current stop files, publish stop intent/history before replacing
user-stop.json, and reconcile publication cuts under control ownership. The
reader must reject missing/rolled-back history before returning evidence. No
fixture reader or authorized_by string may stand in for that trust boundary.
The new read-only component does not claim this producer is implemented. Add
real producer crash/cold tests at intent, history, stop and resume publication
before public factory admission. Preserve original inherited stop contracts.

Additional native-consumer trace for the public factory: current read-only
configuration omits monitor timing/state fields required by durable.validate_config
and checked_request, including poll_seconds, acknowledgement_seconds,
maximum_repairs and progress_files. Keep inspection candidate nondispatching;
before public monitor construction derive the exact fixed supervisor controls
from its reviewed policy, bind them into configuration identity and add an
actual durable.Monitor construction/checked_request regression. Do not copy
historical progress_files uncritically: TX6 requires verified manuscript receipt
progress, not mtime/size. Initial stage/terminal bindings must also follow the
committed prospective cursor instead of a frozen historical generation.

### Concrete provider integration after immutable-closure review

28 October recovered execution: items 1–2 pass 273 adjacent regressions
(64.55 seconds, 16 workers). Native-ownership review P2 is independently
closed after twelve additional publication-veto regressions and a twelve-case
independent recheck. Items 3–5 are implemented; initial combined provider
integration passed 164 tests. Provider review reproduced P1: Popen can fork
successfully and then raise in its parent's exec-error-pipe read. Exception
type alone must never prove zero launch. Retain the process object before its
constructor runs; clean/reap any retained PID and group on constructor failure.
If no child identity is available, retain explicit uncertainty, block resend,
and preserve the charge. Only a pre-spawn guard/setup failure can return the
typed zero-launch result. Test real post-fork faults, not only mocked errors.

The initial native gate executor-c097121b93b6 was intentionally interrupted
after eleven completed cases to repair P1; its fail receipt retains unchanged
source/authority and completed cleanup. The source freeze ended only after
runner exit. Post-fork repair passes 172 combined cases and a 12-case
independent residual review. The repaired exact-member native executor gate
passes all twelve cases in 805.56 test seconds with unchanged source/authority.
Its release-acceptance field remains false. Admission/control/preparation
fixture boundaries remain explicit.

Implementation details for the next collector slice:

- Keep native request/profile/command checks in a private FunctionType clone.
  Clone its qualified and capture namespaces; intercept the native rejection
  writer before its first side effect, preserving the original exception for
  the prospective single publisher. Shared/frozen namespaces remain unchanged.
- Prepare bounded sinks/FIFO first, then execute the final dispatch guard and
  select the complete provider descriptor union immediately before Popen.
  A cleanup-complete typed zero-launch outcome is distinct from an exception
  after a real child exists. Never infer no-launch from missing process-start.
- Use a write-ahead rejection intent binding failure, invocation, qualification,
  stream inventory and cancellation before publishing terminal no-launch proof.
  Exact retries only complete/reuse that intent; conflicts or nonempty streams
  block. Binding-only/ambiguous crash cuts never authorize retransmission.
- Bind retained process identity before fallible observation/publication; try
  all cleanup steps even if one fails, bound waits, and retain incomplete
  cleanup evidence. Ancestor descriptors remain borrowed throughout.
- Test both known veto categories at the post-FIFO boundary, exact cold reuse,
  rejection publication cuts, changed evidence, post-spawn write failure,
  output bounds on each stream, deadline and descendant cleanup.

The next change must preserve the proven native spending/recovery behavior while
connecting the new predicate and lease components at their actual consumers:

1. CampaignAuthority gets a complete campaign lease and RuntimeLeaf through the
   prospective factory. Its owned-write predicate checks leaf/lease plus checked
   request and program descriptor; it never reads mutable floors. Dispatch adds
   native read-only floors separately. Existing component callers retain their
   current behavior until the public factory is admitted. Native hold, claim-tail
   repair, claim and settlement callbacks must use the owned-write predicate;
   genuine post-claim dispatch must still detect a deleted/rolled-back floor.
2. owned_stage extends the campaign lease with exact committed execution/executor
   roles after acquiring those native locks; it borrows them and duplicates the
   full ancestry. StageOwner exposes the complete pass_fds union and role-selected
   executor. The execution ContextVar carries the complete union rather than
   resetting it to one descriptor. Pending/foreign/sealed stage membership fails.
3. Clone bridge.NATIVE_RUNTIME's wrapped function globals privately, along with
   its qualified/capture dependency objects. The native runtime's request/profile/
   command checks stay in force, but qualified.capture.launch resolves to the
   prospective collector. Do not reassign frozen/shared collector attributes.
   Test private identity and unchanged bindings on normal and exception exits.
4. The prospective collector owns only its local FIFO/pipes/process group. After
   FIFO and sink setup, perform the last leaf/complete-lease/stop/dispatch check
   immediately before Popen, passing all roles. A typed zero-launch outcome
   transports the original veto to one idempotent publisher after local cleanup.
   Retain the native bounded-output protocol and actual child identity after
   spawn; failures writing process-start or heartbeat require cleanup/evidence,
   never an invented unstarted result. Descendant quiescence must be proved.
5. Replace the two independently writing rejection paths with one exact publisher.
   It uses empty regular streams, no process-start, process_started=false and
   group_quiescent=true; preserves the original typed failure and exact stop
   cancellation bindings. Identical cold publication is reusable; conflicting or
   partly published records require reconciliation without a provider retry.
   Runtime binding and cancellation helpers currently reject existing process
   evidence, so cold reuse must verify their immutable join before publication.

Regression acceptance: complete provider FD union after parent death; veto after
FIFO setup for both ownership loss and USER_STOPPED; real native record validation
of zero-launch evidence; repeated cold reuse and conflicting receipt rejection;
failure immediately after real Popen/process-start write, surviving same-group
descendant, oversized stdout/stderr/final response, timeout and collector I/O
failure. Run native executor/accounting checks after this integration, then freeze
for the bounded review. No public CLI activation precedes those results.


CF1–CF5 in `INVENTORY_RECOVERY_CONSUMPTION_FLOORS_REVIEW_2026-10-28.md`
are concrete regression requirements, not optional review advice. Add
post-claim dispatch-veto checks for lost account/stage floors; read-only
status observation races; cold actual executor/owned-stage entry with
reserve-written/receipt-missing/ledger-missing claim tails; pending-after
plus a lawful native sibling extension; and deletion of an owned transition
after native mutation. Reconciliation must preserve exact original target
hashes and distinguish observe-intent publication from owned mutation order.
Do not broaden native grant status to tolerate missing ledgers. Repair only
the already-reserved exact tail before full grant-status validation, under
the existing native locks, then run normal stage validation.

### Bounded design review disposition

Spending follow-up CF1-R/CF3-R must close before ownership promotion. Account
floor validation must explicitly enter the nonpublishing mixed-history/document
adapter, including cold authority construction; it cannot depend on a caller's
ambient runtime aliases. Existing-only claim repair must reject any account
write inside the native invocation rather than compare unlocked account bytes
around it. Lawful sibling reserves/settlements may append during repair. Test
both without relaxing the exact pending intent, hold, prepared marker or
single-reservation requirements. Complete partial status-publication/busy and
settlement-suffix counter coverage before the bounded recheck.

Review `INVENTORY_RECOVERY_PUBLIC_CONFIG_DESIGN_REVIEW_2026-10-28.md`
identifies PC1–PC6. Their remedies are required implementation gates, not closed
code findings. PC1/PC2 are clarified by the acyclic graph and exact field
topology above. The remaining concrete composition requirements are:

- Leaf ownership/stop validation must not recursively call admission. Admission
  returns identical immutable configuration after checking evolving state; it
  must not return a report containing the advancing cursor. Existing grant and
  account locks cannot be reacquired by a nested admission check.
- Acquire predecessor exclusions and establish quiescence before taking the
  shared program/new campaign ownership. Pass the verified union of chain,
  program, campaign, job and stage descriptors through both child edges and
  preserve exclusion until provider quiescence. Ephemeral descriptor numbers
  are not configuration identity. Test surviving providers after each parent
  death, not just a clean subprocess exit.
- Host permission has an external trust root: exact host-approved invocation
  or independently authenticated receipt/capability, not a candidate-writable
  `authorized_by` field. If the runtime cannot establish that trust root, keep
  dispatch blocked. Record exact action, source/config/release/preflight,
  deployment target, limits and replay semantics; desktop delivery alone is
  not permission. Prospective preflight cannot reuse a historical writer that
  changes the frozen predecessor adoption.
- Preserve all inherited stop roots with their original contracts and add the
  prospective campaign stop root. Deployment cannot clear an old stop. Require
  exact explicit-resume provenance, including stop deletion/rollback checks.

### Real-data regression discovered during execution

The 28 October production-data preparation failed after 1063.83 seconds while
initializing `NativeRequests`: its copied historical size-rule receipt was
validated against the successor snapshot's inference destination instead of
the original receipt's bound snapshot/profile. This is not permission to widen
corpus rights. The bootstrap must enter the same original-receipt replay and
nonlive runtime scope as normal native replay before importing ownership.
Add mixed historical/current destination regression coverage plus copied-byte,
foreign-profile and missing-origin rejection. The previous 1,167-case pass
missed this composition because its native bootstrap fixture had no inherited
size-rule receipt. Source/account/grant remained unchanged and no inference
occurred in the failed real-data preparation.

## Downstream consumer trace

Reuse existing release consumers rather than inventing a second acceptance
system: `tools/prepare_final_review.py` requires both ZLB and held-out snapshot,
packet and reproduction paths. `humanvoice.automatic_release._benchmark()`
checks the actual assembled candidate, native live activity, role/source and
independent reproduction. `_evaluation()` requires distinct source identities.
`prepare_admission()` and `require_admission()` bind the final protocol to the
exact ZLB packet and current implementation/profile. The recovery controller
must supply verified artifacts to these existing consumers after downstream
phase completion; it must not mark E7-H ready directly from inventory success.

The retained reproduction master updates E6-B/E7-RB only when both roles exist
in its verified progress maps. Its frozen runner is not the new v3 supervisor
and must not be modified in place or used to manufacture current admission.
