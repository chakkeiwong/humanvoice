# Cumulative recovery limit and blocker classification

Current execution checkpoint, 28 October 2026: master 4.11 / ensemble 201.
The installed-authority/ownership/bootstrap slice passes 524 focused tests with
16 workers; source and production authority are unchanged. Actual read-only
installed-authority capture passes. This does not close full TX3 or resume ZLB.
Closure order, corner cases, test requirements and phase/stop refresh rules:
`docs/plans/INVENTORY_RECOVERY_CLOSURE_2026-10-28.md`. Evidence and boundaries:
`docs/reviews/INVENTORY_RECOVERY_INSTALLED_EXECUTION_2026-10-28.md`.
Independent review's path-alias finding is repaired and closed in follow-up.
Next after this checkpoint: public admission/transaction integration.
Do not substitute component passes for public-entrypoint or live receipts.

CI1 is independently closed. TX1 restart membership preserves cumulative
allowance; one-shot storage failures and repeated outbox-failure bursts now
retain retryable publication instead of becoming permanent engineering blocks.
Stop/admission/ownership and unrelated corruption blockers remain enforced.
The 148-case fast regression set passed, including 1/4/12 reporting failures,
persistent reporting failure with stop, and before/after restart publication.

TX2 now binds the admitted canonical journal and sealed stage consumption.
The initial candidate passed 62 journal/policy/native-executor cases in
754.79 seconds, including a genuine oversize-to-split successor. Review found
forged cancellation and uncheckpointed consumption loss; these were repaired
with validated cancellation transitions and a write-ahead consumption head.
The new head commits pending intent → journal → committed floor on every
mutation, rejecting deleted or rolled-back consumption before checkpointing.
The 93 journal/policy/registration/history regressions pass in 30.32 seconds.
The broad native run was interrupted after 82 failures / 65 passes: old
execution/resume fixtures omitted the newly required canonical journal
admission descriptor. Production guards remained strict. Corrected fixtures
pass 91 resume/execution/allocation cases in 42.20 seconds; requests fixtures
now bind the descriptor too. Independent follow-up closes TX2-F1, TX2-F2 and
TX1-IO1 within the inspected slices, not the campaign integration gates.
Read-only journal status no longer reconciles pending consumption writes.
The 16-worker full validation completed at
`validation/0a17039ddd70a9ec6e5c/566e559888e0`: 646 passed / 1 failed in
1259.33 seconds. The remaining crash test patched the old persistence module;
its journal-publication hook now targets journal_history too. Frozen production
guards were not weakened. The receipt is historical after subsequent edits.

The TX5 safety slice now rejects stale unspent account authority before a new
grant hold and under the claim lock, preserves pending intent, and rechecks
stop/ownership after replay and before native publications. Exact already-held
reservations can finish after lawful sibling growth. All 66 focused claim,
owner and capacity tests pass. Broader native execution/resume/allocation/
requests coverage passed 108 cases in 122.76 seconds. Independent review then
found the actual ledger writer lacked a post-lock veto and the stop test reused
the owner callback. Both are repaired: a private guarded native initializer
checks at ledger publication, and distinct stop/owner predicates cover replay,
lock and reserved-tail/sibling cuts. The combined claim/owner/capacity/campaign
set passes 123 cases in 8.65 seconds. Bounded independent follow-up closes
both claim findings. Repeated native execution/resume coverage passes all
108 cases in 123.30 seconds. These are not full current-source release gates.
Automatic retirement/repreparation and canonical campaign integration remain
open; a safe blocker does not close them.

A prospective campaign_history component now implements intent-first offline
initialization, monotonic exact transition membership, pending head/cursor/
repair reconciliation, read-only coherent status, fixed generation paths,
exclusive ownership and publication vetoes. Its 47 component tests pass,
including real process death, repeated I/O failures, impossible-state rejection
and two synthetic successors. This is NOT the canonical campaign factory or
the required genuine native two-successor/combined soak. CP3 restart/campaign
composition and public cold-entry integration remain open.
Storage review found CS1–CS4: atomic temporary-file false blockers, stable
malformed initialization mistaken for publication progress, lost committed
plan/probe evidence accepted, and a missing successful guard return. Repairs
use a separate temporary namespace, pre-parse head sampling, exact committed
plan/probe byte membership and a strict True guard contract. The 134-case
storage/journal/policy run passes in 6.19 seconds, including real process
death inside atomic replace and concurrent read-only status. Independent storage
follow-up closes CS1–CS4 within the inspected repairs, with no residual finding
in that slice. The inspector is closed. This is not full campaign integration
or release closure; CP1–CP4 retain their public-entrypoint acceptance gates.

The native read-only preparation descriptor test passes in 83.71 seconds,
including cold historical replay, unchanged artifact bytes/mtimes, late veto
and a malformed prepared marker. It is verification, not an automatic preparer
or canonical campaign admission. Its first run exposed an unconfigured cold
history test fixture; the production validation was retained and fixture fixed.

The 16-worker full exact-source validation passed all 746 tests in 1534.02
seconds at `validation/9b5678d92cd617c677a0/c6c6ddc13c53`, with unchanged
source and authority. That receipt is historical after the following bootstrap
repair. No actual preflight or live execution is running.

Continuation crossed midnight into 28 October. Bounded initialization review
identified IN1–IN4: journal bootstrap crash recovery, strict pending/complete
and legacy compatibility, nonmutating status, and acyclic admission binding.
A temporary-directory reproduction confirms IN1: fail the first head write
after marker publication and reopen returns BLOCKED_ACCOUNTING, permanently
stranding a never-spent journal. The prospective repair now uses a permanent
full initialization intent, pending/complete markers, an exact six-write empty
transaction, and an identity carried by later journal consumption. Legacy
journals reopen without upgrade; lost committed evidence remains blocked.
Construction/status no longer create directories or locks. False predicates
veto writes. The first 235-case focused suite passes after moving corrupt-state
inspection before lock creation. Added atomic-write process-death, bool-alias
and unstable-observation coverage passed 298 cases. Independent implementation
review found missing-J reconstruction through ordinary legacy reconciliation
and present-null intent misclassification. Both are repaired with shared-path
missing-J rejection and object-typed observation; bounded follow-up closes II1
and II2. Final focused/native compatibility passes 448 cases in 128.01 seconds
with 16 workers. Ruff passes. This is bounded bootstrap closure, not release.

The OFFLINE campaign_initialization candidate joins already prepared generation
zero, independent native replay, an acyclic proposal, one fixed journal,
inherited consumption and the campaign seed. The initial 225-case suite passed
in 110.10 seconds. Bounded binding review found a late grant-replacement gap
alongside the known verifier-to-publication and generation-zero status gaps.
Repairs bind exact preparation/probe/snapshot/source evidence before every
proposal/journal/seed publication, retain the verified grant/account prefix,
reject new target allocations/holds, and preserve lawful sibling extensions.
Native seeds have a distinct version and mandatory initial membership; coherent
read-only status rejects lost/changed plan/probe/transition/proposal evidence
and present non-object JSON. Inherited descriptors retain the outer lock.

Added deterministic source/grant/stop/allocation races, inherited-lock rejection,
24 composed process-death cuts, restart idempotence and nonmutating status
regressions. The first native-inclusive run finished 340 passed / 4 failed in
114.14 seconds. All four failures occurred before fault injection because the
new tests omitted the existing cold-history fixture setup; that fixture was
corrected without weakening production checks. The rerun passed all 344 cases
in 113.49 seconds with 16 workers; Ruff passed. Bounded independent follow-up
addresses all three inspected bootstrap findings and found no new concrete
defect. That inspector is closed; subsequent integration is recorded next.
The real offline-preparation command now prepares campaign/generation-00 and
uses the single bootstrap journal rather than a scratch journal. Its guard
checks actual held predecessor/program locks, source, production cursor and
authority throughout publication. The public cold-entry native test returned
PASS on both calls with identical seed/journal identities; its broad mtime
assertion incorrectly included deliberate probe revalidation working files.
The assertion now excludes only the probe snapshot/revalidation working trees;
all canonical control, journal, prepared files and the main snapshot remain
covered. All 339 integration/component cases pass in 96.20 seconds. Bounded
preflight review found no new actionable defect; that inspector is also closed.
Added generation-zero membership loss after zero/one/two successors and final
post-completion grant/stop veto tests. The combined source/authority-bound run
passed all 360 cases in 112.68 seconds at bootstrap-validation/b5f6f3f7b5b8:
zero failures/errors/skips, source and production account/grant/stages unchanged.
Ruff passes for all changed Python files. No test or inspector remains active.
The new bootstrap regression module is in the canonical full validator's fixed
test list. The retained checkpoint has hashed XML/logs and explicit nonrelease
scope; it does not substitute for final exact-membership release validation.
This is not canonical installed-supervisor admission, public live execution
or release acceptance. Earlier full-suite receipts remain historical.

The bounded protocol review found CP1–CP4: first initialization write cuts,
impossible pending artifact combinations, restart-receipt/cursor composition,
and coherent concurrent status reads. The repair plan now contains explicit
dispositions and regression obligations for each. They await implementation
and executable integration acceptance; no production restart is authorized.

Do not confuse these component results with release completion. TX3 canonical
installed-supervisor admission, TX4 campaign transaction/head/cursor recovery,
TX5 stale prepared authority, TX6 verified-receipt progress, TX7 replay-cost
bounds and the combined two-successor/long-document soak remain open.
Fresh exact-source full validation, actual no-call preflight and grouped new
limit/deployment approval must precede production. Repair → retest → review →
refresh remains mandatory after every phase and interruption.
Production remains stopped at 166 retained / 439 unfinished. No live calls,
account/grant/service mutations, commit or push. The proposed 535 calls and
291,040,000 tokens remain unadmitted. Final actual ZLB acceptance stays human;
intermediate checks are automatic regression tests.

Historical execution checkpoint, 27 October 2026: master 4.00 / ensemble 190.
## Historical checkpoint before the current repair

The exact-source 16-worker validation completed with 548 passes at
`validation/11178f9ae8d2920091fd/9df3783a48f6`; source and authority were unchanged.
Actual no-call preparation `preparation/4e6390b2750ff59be77e` completed with
OFFLINE_PREPARATION_PASS in 1120.10 seconds: 166 retained / 439 unfinished,
168 observations, eight historical sequences and idempotent history import.
It made zero model calls, reservations or production authority/cursor changes.
Both passing receipts are historical after the subsequent CI1/TX1 edits;
no full validation or preflight remains running at this checkpoint.

CI1 now restores aliases imported during document/qualification scopes and
deactivates retained qualification wrappers on exit; 26 semantic tests pass.
TX1 now uses a source/run/ceiling-bound restart head, initialization marker,
exact committed membership and one recoverable pending receipt. Missing
committed files cannot renew restart allowance. Combined semantic, restart,
supervisor and launch coverage passes 110 cases, including 14 process-death
cuts, stop/disk failures and missing-head/receipt rejection. Independent
follow-up is pending; component evidence is not campaign/release acceptance.

Next: close that follow-up, enforce canonical cross-generation journal
authority (TX2), then integrate durable campaign transactions and canonical
installed-supervisor handover (TX3–TX5), receipt-only business progress (TX6),
and measured ancestry replay bounds (TX7). Require public multi-generation
and long-document failure soak, fresh exact-source validation/preflight,
and grouped prospective admission before any production launch. The TX
closure matrix in the repair plan remains mandatory; no gate is waived.
Repair → retest → bounded review → refresh applies after every phase/stop.
Production remains stopped: 166 retained / 439 unfinished; proposed 535 calls /
291,040,000 tokens are not admitted. No paid calls, authority/service changes,
commit or push. Intermediate checks are automatic; only final ZLB content
acceptance requires human review.
Current repair delta: CI1 is independently closed. TX1-F1's one-shot disk
publication defect is repaired; 125 focused cases pass. Follow-up TX1-IO1
finds repeated reporting-outbox failures can still become terminal on reopen;
this is the next repair and must cover error-handler/observer/entry-flush cuts.
TX2 canonical journal binding and sealed stage consumption checkpoints are
implemented as a candidate; 16-worker journal/policy/native-executor tests are
running. Do not edit source until that source-bound native run finishes.
Neither TX1 nor TX2 has full integration acceptance yet.

## Historical execution plan — master 3.99 / ensemble 189

The actual ZLB ownership preflight PASSED in687.82 seconds at
preparation/892aa313ce903e79a301:166 retained/439 unfinished,8 historical recovery
sequences,3 sharing window0054 and1 on its unfinished child. Exact fresh-pair
eligibility and idempotent import pass; zero model calls/new reservations,
unchanged source/account/grant/cursor. Rule-context follow-up independently
closes the receipt-scope defect. The501-case full suite is historical after edits.
Semantic origin/scope repairs pass60 focused cases. Follow-up closed SM1/SM2
and identified a remaining historical critic ancestry substitution in SM3.
The graph now reconstructs exact native parent prompts, context and complete
chains for historical as well as new rules;18 semantic tests pass, including
coverage/reconstruction A/B ancestry versus unrelated X. Independent follow-up
closes that defect. Native oversize-to-split-to-completion and failed-canary
continuation tests now pass (2 cases,332.82 seconds), including cold reopen,
exact-once expansion charge and no duplicate execution. Initial scoped native
preparation/completion also pass. Broader preparation/crash tests and bounded
continuation review remain in progress; these are not release acceptance.
Production preflight now explicitly switches historical to document semantics.
The recursive ancestry/native/cold-probe set passed9 cases in642.61 seconds.
CD2-F1 now binds the complete accepted probe report/transcript digest into
the admitted native plan; rehashed observation/report mutations are tested
against the sealed plan. Exact 16-worker validation completed with 541 passes
and one failure in 859.28 seconds at
`validation/9720dfe3740c77adf406/9193886f5920`: the native ownership fixture
still selected historical semantics for a document-policy plan. Keep the
production ownership guard and update the fixture to the versioned runtime.
Actual no-call preflight `preparation/f4911c92ee64fd8b71e2` failed after
262.75 seconds: its historical accounting context remained active when it
installed document semantics. Fully unwind that context, validate origin in
a temporary historical scope, then install document hooks before reentering
history. Add exception/nesting regressions and rerun both failed boundaries.
Context lifetime and the native ownership fixture are repaired: 39 focused
cases pass in 89.14 seconds, including exception cleanup and wrong nesting.
The next actual preflight, `preparation/23a28f15063581b078a4`, failed in
484.75 seconds with unchanged source/authority and zero calls. Qualification
corpus replay was intercepted by the document-only critic ownership hooks.
Qualification now evaluates through its captured native critic bindings while
document calls still reject missing extraction ownership. All24 semantic
regressions pass, including exact qualification requests, sensitivity membership,
no observation contamination, interruption restoration and orphan rejection.
Actual no-call preflight is running at `preparation/4e6390b2750ff59be77e`;
exact-source 16-worker validation is running at
`validation/11178f9ae8d2920091fd/9df3783a48f6`. Failed receipts remain
engineering evidence, not deployment acceptance. No production restart.
The bounded transaction design review identifies TX1–TX7: lost restart
membership, cross-generation journal substitution, omitted inherited stops,
pending head/cursor reconciliation, stale pre-claim authority, receipt-based
progress and repeated ancestry cost. These are open implementation gates, not
closed by documentation or the running tests. See the repair plan's TX closure
matrix and the independent transaction design review for exact regressions.
Remaining: finish semantic closure, generic settled successors, durable repair/
cursor transactions, canonical admission/supervision, combined long-document
soak, then exact-source release/preflight and concrete grouped admission.
Repair/retest/refresh remains mandatory between phases and after interruptions.
Production has NOT resumed.535 calls/291,040,000 tokens remain unadmitted.
No live provider calls, production authority changes or service restart.
Intermediate verification is automated; final actual ZLB review remains human.

Retained receipts: full suite `validation/3473e1451996260e713b/f7191fcdaeca`
(490 passes,323.83 seconds); actual failed preparation
`preparation/2a2ac863733f40338155` (567.29 seconds, exact166-prefix reached,
zero calls/writes). Neither is current-source release acceptance after edits.
OP acceptance requires public outer-scope replay with prior observations,
interruptions after observation/verification/intent publication, rehashed removed
or reordered transcript rejection, cold replay after legitimate account growth,
and no-write eligibility parity for retired parents, used profiles and changed
handoffs. Historical rule receipt validation must remain in its original route
and exact source scope; do not widen corpus rights to cure a context error.

### Additional reviewed failure boundaries

- Cold revalidation must never modify accepted probe evidence. An exception or
  hard process death after a partial replay must leave the original intent,
  observations, verification and log byte-identical and permit a later reopen.
- Historical receipt validation must run under its original model/route and
  source permissions. A copied receipt cannot acquire today's route by accident;
  widening corpus rights is not an acceptable repair for a context mismatch.
- Distinguish document split capacity from original-root limits. Count inherited
  and prospective descendants by source file, original window and purpose, and
  never charge inherited expansion twice. A new semantic rule must reconstruct
  its exact recipe from observed immutable source and independently settled
  failure before dispatch; a rehashed wrong recipe still fails validation.
- Split discovery may change the first unfinished request only to the verified
  first child, preserving every completed prefix receipt. It must not purchase
  a canary or retry during preparation. Ordinary successors retain the exact
  unfinished request and all original migration/ownership records.
- Every successor carries cumulative failed/diagnostic allocations and split
  overhead once. Reserved-but-unused slots, cancellations, unknown allocations
  and successful manuscript requests have distinct accounting; local generation
  numbers must never renew the document budget or profile/root allowances.
- The transaction must tolerate interruption before/after intent, preparation,
  transition, cursor and repair-result publication. A missing committed record
  is corruption, while an intact pending intent is recoverable. Check user stop
  and ownership again immediately before each mutation and any provider launch.
- Supervisor progress follows the committed generation's actual receipts and
  repair transaction, including offline finalization. Heartbeat is liveness;
  unchanged receipt progress must remain visible even with a healthy heartbeat.

### Prospective semantic implementation boundary

Use a separate v3 semantic rule/runtime module. Preserve old rule bytes and
validators; identify the inherited rule prefix from the original migration,
then bind each new rule to its normalized native observation, original source
scope, parent chain and settled failure. Reconstruct the exact native recipe
and require unique request/failure receipts. Do not accept a rule merely because
its internal hashes agree. Apply the original extraction merge, reconstruction
and coverage checks to every split and retain fail-before-sibling behavior.

The document journal must distinguish inherited splits (zero new expansion)
from prospective splits (children minus one). Current `NativeRequests` imports
every rule as inherited; generic successor integration must replace that path
for new v3 rules. Persist the rule identity with the charged split so later
generations cannot reimport it for free or charge it twice. Root registration
also binds one source-file/window/purpose scope to its original owned membership;
changed critic concept identifiers must not create a fresh root allowance.

Required tests include independent incidents beyond16, repeated window names
in different files, overlapping windows, historical-size plus new semantic
descendants, third-level sibling splits, depth/child/document capacity boundaries,
changed/reordered/dropped ancestors, altered root membership, rehashed recipe
corruption, nested critics preserving complete original context, failed child
judgments, and exact receipt/accounting replay through the public executor.

The full document soak remains an integration gate after the native successor
and campaign transaction exist. Passing semantic unit tests alone cannot admit
production or claim the long-document recovery requirement is complete.

Independent design review SD1–SD3 additionally requires:

- Keep acceptance keyed to the original file/window across extraction and both
  critics, while counters include purpose. An extraction split must still make
  unsplit reconstruction and coverage reject missing/negative judgments. A later
  overlapping window or another file must not inherit that acceptance state.
- Validate a single application graph across historical size rules, historical
  semantic rules and prospective rules after their original validators pass.
  Reject duplicate request/failure consumption, conflicting parent edges and
  absent ancestors before charged registration or child dispatch. Copies of an
  identical old edge are references, not new children or free new split rights.
- Use one version-aware observation/rule interface in the semantic runtime and
  normal resolver constructor. Nested scopes reuse only identical bindings and
  restore the historical interface after exceptions; never patch frozen limits.
- Count14 as all non-root nodes, including internal nodes: a complete binary
  depth3 tree has14 children,8 leaves and7 edges. Each new binary edge consumes
  one document expansion. Historical extraction depth does not consume the
  independent merged-window critic depth, which starts at0.
- Keep sibling-local concept renaming and prerequisite rewriting. Identical
  local concept IDs in different children remain valid; duplicates within one
  child fail. Test native protected boundaries, both marked/unmarked contexts,
  every ancestor context suffix and fail-before-next-sibling behavior.

Review: `docs/reviews/INVENTORY_RECOVERY_SEMANTIC_DESIGN_REVIEW_2026-10-27.md`.
The501-case receipt is `validation/a383097681657f4d8974/782ec36477ea`;
the second failed no-call preparation is `preparation/42eab50a4c709c10a7cd`
(561.56 seconds, source and authority unchanged). Current rule-context rerun:
`preparation/892aa313ce903e79a301`. Do not infer its result from targeted tests.

Current disposition of that rerun: PASS,687.82 seconds,168 normalized native
observations, eight imported recovery sequences and exact3/1 original-root/child
consumption. This closes the actual historical ownership preflight for its
frozen source; subsequent semantic edits require a new final release preflight.

SM1–SM3 review repairs require direct regressions for a prospective rule relabeled
as inherited, a downgraded old-shaped envelope, omitted/replaced original origin,
deleted scope map/entry with retained consumption, omitted extraction parents,
nonchild critic targets and changed ancestor context. Bind zero-charge origin
to the independent original migration, never to a version string or supplied
boolean. Scope mappings must be reconstructible from canonical lineage records.
Reject unsupported legacy scope upgrades explicitly; no automatic fresh-root
fallback. Require valid legacy/size ancestry and native mixed-rule replay too.

### Current continuation corner-case acceptance

#### Durable campaign publication protocol

#### TX review closure matrix

The bounded independent report is
`docs/reviews/INVENTORY_RECOVERY_TRANSACTION_DESIGN_REVIEW_2026-10-27.md`.
TX1 restart membership and TX1-IO1 reporting retries have bounded component
closure. TX2 canonical binding and TX2-F1/F2 consumption defects also have
bounded closure; the independent canonical admission factory and genuine
two-successor integration remain open. TX3–TX7 remain implementation gates.
Passing component tests does not close campaign or release acceptance.

| Finding | Required implementation and executable acceptance |
| --- | --- |
| TX1 High: lost restart membership | Persist monotonic committed restart membership plus pending publication; reconcile published high-water state before spending. Delete the last/all committed receipts at the ceiling and require no launch or renewed ordinal. Preserve the valid receipt-before-state crash cut exactly once. |
| TX2 High: successor journal substitution | Bind canonical absolute journal path and stable authority identity in admission/seed; enforce at public executor entry before claims or registration. Reject a second initialized journal, changed authority, missing journal/marker, and lost prospective consumption. Reopen the same journal across two genuine successors. |
| TX3 High: omitted predecessor stops | Derive chain/stops/descriptors independently from installed history admission; reject rehashed removed old stops or an older valid supervisor. Require all inherited locks in the cold child, source/command/environment/approval bindings and actual quiescence. |
| TX4 Medium: head/cursor lag | Interpret pending state read-only, then reconcile under ownership before dispatch. Only an intact pending intent permits predecessor cursor lag; neither status getters nor heartbeat may repair it. Test both public cold entrypoints at head/cursor/receipt cuts and each stop boundary. |
| TX5 Medium: stale authority before claim | A preserved prepared plan can be valid evidence but not executable. Serialize authority from final readiness through claim, or explicitly retire and reprepare an unspent stale plan in a new transaction. Never rewrite old intent; test lawful sibling reserve/settle growth before/after the target reservation. |
| TX6 Medium: activity masks progress | Separate verified manuscript receipt identities from diagnostics, offline-phase activity and heartbeat. Rewriting identical files or an uncommitted successor must not reset business-progress age; committed completion at the final generation must advance it. |
| TX7 Medium: replay cost | Instrument settlement and receipt verification counts per operation across depth/prefix sizes. Use an explicit measured cost bound and exact source/account-prefix/file membership for any operation-scoped reuse; changed/missing files and account extensions require revalidation. |

Implementation order: close current context/preflight regressions, then TX1 and
canonical campaign transaction/journal binding (TX2/TX4/TX5), canonical installed
supervisor admission (TX3/TX6), and the combined multi-generation cost/soak gate
(TX7). Repair/retest/review/refresh after each phase. Full final exact-source
validation and real no-call preflight precede grouped new-limit/deployment
approval; a new verified manuscript receipt is required for a resumed claim.

#### Cross-cutting corner-case obligations

#### Bootstrap binding acceptance — 28 October review

The bootstrap review and its follow-up are bounded guardrails, not intermediate
human acceptance. Every finding must have executable regression coverage:

1. Capture preparation files, native probe membership, snapshot content and
   source contract before independent replay; compare again afterwards. Derive
   the descriptor from captured bytes, not an unchecked later plan read.
2. Recheck that descriptor and source contract immediately after replay and
   before every proposal, journal/import and campaign publication. A durable
   write followed by process death reopens the same transaction, not a new
   allowance. Add a final return-time check after completion publication.
3. Retain the verified grant identity and canonical account path. A different
   internally valid grant, deletion, target allocation/hold, or changed original
   account prefix must veto publication. Legitimate unrelated account suffixes
   remain compatible; offline evidence is not authority to claim a stale plan.
4. Native campaign seeds require a distinct version and complete initial
   binding. Status checks initial plan/probe/transition/proposal membership from
   one coherent sample at generation zero and after successor advancement.
   Missing directory/files and present null/list/scalar JSON never mean absence
   or initialization-in-progress. Status never repairs or authorizes dispatch.
5. Exercise same-held descriptor duplication, unheld/wrong/replaced/foreign
   descriptors, nesting, forked owner rejection and retained outer lock lifetime.
   Combine process death before/after proposal, journal initialization/import,
   seed, head, cursor and completion; retain identical bytes on exact reopen.
6. Keep synthetic fault-injection coverage separate from real native replay.
   Require both. Cross-generation public entrypoints, installed predecessor
   derivation, quiescence, retirement, receipt progress and cost/soak gates still
   apply; none is waived by successful bootstrap tests.

#### Combined failure matrix

The transaction and recovery tests must combine failure dimensions, not just
exercise isolated helpers. A successful persistence unit test cannot establish
the behavior of its supervisor exception handler or next cold entry.

| Boundary | Required combined cases and safe disposition |
| --- | --- |
| Storage/reporting | Fail before and after each fsync/replace/state publication; repeat a finite burst through handler, observer and next-entry flush. Retain original intent, retry only classified publication failures, never reset counters or hide corruption. Persistent storage failure is a visible no-dispatch condition. |
| Stop/admission/ownership | Inject each veto after expensive validation and immediately before every durable write/launch, including retry paths. Fresh stop supersedes old resume; live descendants retain exclusion. Neither reporting recovery nor status projection may grant execution authority. |
| Journal/generation | Same-policy alternate journal, missing initialization, rehashed removed pairs/splits, cancelled canaries and unused retry slots, two genuine successors, cycles and final-generation boundaries. Preserve committed native consumption and distinguish unsealed recoverable progress from sealed immutable checkpoints. |
| Prepare/claim race | Sibling reserve/settle before intent, after intent and after target allocation. Deterministically block stale unspent authority or retire/reprepare in a new transaction; no in-place intent rewriting and no duplicate grant hold. |
| Head/cursor/repair | Reopen both public campaign and supervisor entrypoints after every commit cut, including head ahead of cursor and cursor ahead of repair receipt. Status remains read-only; only the owned reconciler completes exact pending work. Missing committed evidence is not a pending transaction. |
| Progress/cost | Identical file rewrites, fast heartbeats, stalled provider, offline preparation, pending successor and committed final generation. Count verified manuscript receipt advancement separately; measure repeated prefix/settlement work and invalidate caches on changed membership. |

Review findings are converted to deterministic regressions before another
review cycle. An independent inspector is an extra guardrail, not the primary
test oracle. No intermediate human judgments or model-generated approvals are
introduced by these gates. Every phase records actual completion versus pending
tests, current-source versus historical receipts, and next repair action.

#### Publication sequence

Pre-claim authority disposition is explicit: preparation remains historical
evidence after a lawful account suffix, but is not automatically executable.
Before a fresh grant hold and again under the native claim account lock, verify
the current ceiling and any pending claim's exact account prefix. A stale
unspent preparation produces a typed accounting blocker with a retire/reprepare
action; it must not acquire another hold, overwrite either intent or dispatch.
An already-reserved exact target may finish its publication tail after unrelated
lawful account growth. Automatic retirement/repreparation belongs to the bound
campaign transaction and remains open until that integration is tested.
Recheck stop/ownership after account replay and before each claim publication;
test late vetoes at intent, receipt, ledger and completion cuts.

Use a source-bound campaign seed containing the initial prepared stage, policy,
document/migration identity, and one canonical reservation-journal binding.
Initialization is an explicit offline operation with a retained intent. Once
initialized, a missing head, journal or committed record is corruption; live
execution must never call initialization to replace missing history.

The authoritative head contains the ordered committed transition references
and at most one pending intent. Publish that intent before successor preparation.
Preparation may resume only the same transition and fixed generation path.
Independently revalidate the prepared stage and its probe, then publish its
immutable transition record. Commit that record's hash into the head before
updating the derived cursor. Publish an immutable verified repair receipt, then
clear pending state. A crash with an intact pending intent may finish only the
missing publication steps. A committed transition, cursor or repair receipt
missing without that pending evidence must fail closed.

Require exclusive campaign ownership and the inherited stop predicates before
every write and after expensive replay. The transaction performs no inference
and changes no account/grant authority. The next executor uses the exact same
document journal. Generation limits derive from committed membership, never a
resettable counter. Reject unreferenced generation directories, duplicate output
or plan identities, stale cursors, malformed records, rehashed wrong predecessors,
changed source/authority/journal binding, and symlinked mutable state.

Acceptance requires process-death and disk-error injection on both sides of
each durable publication; stop/resume and competing-owner cases; repeated
recovery without duplicate preparation or spend; lost committed history; and
a genuine native oversize-to-split continuation through this transaction. The
combined document soak must include a second successor, qualified fallback,
thousands of logical requests, more than16 incidents, shared-root siblings,
outages and validation-cost measurements. Component mocks cannot substitute
for those native integration gates.

#### Transaction implementation checklist

The canonical journal has its own initialization transaction; campaign
initialization cannot make a partially created journal safe. Code inspection
on 27 October found that the existing marker-before-first-head order strands
the marker-only crash cut. Repair this before building the canonical factory:
retain a full empty-record initialization intent, a distinguishable pending
marker, initial consumption-head/journal publication, and a completion marker.
Only the explicit offline initializer may complete that exact empty tail.
Normal reads/locks/dispatch reject incomplete initialization; once complete,
missing membership stays corruption. Preserve valid legacy journals unchanged
and never infer a legacy journal from a partially lost new-format transaction.
Test process death and before/after storage errors at every initial write, late
stop/ownership loss, mutated/rehashed intent, consumption-before-completion,
missing committed members, and byte-stable reopen. This is an implementation
gate, not an excuse to recreate lost consumption.

Avoid circular admission identities: derive the journal authority from the
immutable proposal's source, policy, migration, fixed paths and authority
descriptor, not from the final seed hash. Then initialize/verify the journal,
bind its exact descriptor into the independently verified campaign seed, and
bind that seed into final admission. No initializer grants live authority.
The bounded initialization review is
`docs/reviews/INVENTORY_RECOVERY_INITIALIZATION_REVIEW_2026-10-27.md`.
Its IN1/IN2 repair preserves exact legacy marker/head/journal triples without
upgrading them. New-format intent is permanent; complete initialization never
permits missing committed evidence to be reconstructed. The fresh empty record
also carries initialization identity, preventing a retained new-format head
from being reclassified as legacy after marker/intent loss. A false ownership
predicate is a veto, not success. IN3 requires a nonmutating, bounded coherent
initialization classifier for composite status: construction and observation
must not create directories or lock files. IN4 is the acyclic authority binding
rule above. Wholesale loss of every witness cannot be distinguished locally
from a virgin root; canonical admission must independently retain the journal
path/authority witness, and an admitted live entrypoint must never initialize.

1. Initialization first publishes an immutable intent containing the full exact
   source/admission-bound seed, then the seed, empty head and initial cursor,
   then a complete marker. Only the explicit offline initializer may finish an
   exact intent-only or seed-only tail. Existing advancement or native spending
   forbids initialization replay; a complete marker never permits recreation of
   a missing head/cursor. Test before/after every first-write boundary.
2. A pending successor records the full exact transition, predecessor cursor,
   generation path and seed identity before preparation. The returned plan must
   equal independently validated persisted preparation; a caller's success flag
   or callback return alone cannot become the transition proof.
3. Head membership records exact immutable transition and repair identities.
   A committed reference may coexist with its matching pending intent only at
   the declared publication tail. Missing nonpending members, extra generations,
   duplicate plans/outputs, reordered references and head rollback are errors.
4. The cursor may be exactly the predecessor or successor only while the head
   contains that same pending transaction. Neither heartbeat nor read-only
   status completes writes. Both cold entrypoints must reconcile under owned
   admission before any dispatch; no caller may dispatch a projected cursor.
5. Before clearing pending, independently verify the repair receipt and its
   source/plan/probe/journal/parent bindings. Its presence alone is insufficient.
   An I/O failure after a successful durable write is retried idempotently, not
   classified as evidence corruption. Other validation failures remain blocked.
6. A stale unspent preparation is retained, not overwritten. Its explicit
   retirement/replacement must conserve generation and incident accounting,
   including any preexisting grant hold. This is not closed by a safe blocker.
7. Admission/ownership/stop checks precede every publication, follow expensive
   validators, and run again after locks are acquired. Publication errors do
   not authorize a retry after stop or ownership loss.

These are executable acceptance obligations, not a claim that the canonical
campaign factory/reconciler exists. Keep that distinction in every checkpoint.

#### Independent protocol review additions

The bounded static follow-up is
`docs/reviews/INVENTORY_RECOVERY_CAMPAIGN_PROTOCOL_REVIEW_2026-10-27.md`.
CP1–CP4 are design/integration obligations, not observed production incidents.
CP1 is addressed in the initialization order above; executable closure is pending.

CP2 requires this artifact-order table, not merely individually valid hashes:

| Head/pending state | Cursor/repair | Disposition |
| --- | --- | --- |
| Pending successor, not committed | Predecessor cursor, no repair | Finish fixed preparation/transition, then head commit. |
| Exact successor committed, pending retained | Predecessor cursor, no repair | Transition must already exist; publish cursor then repair. |
| Exact successor committed, pending retained | Successor cursor, no repair | Independently verify and publish repair. |
| Exact successor committed, pending retained | Successor cursor, exact repair | Verify then clear only this pending intent. |
| No pending | Exact committed cursor and all repairs | Read-only settled state; dispatch only through owned admission. |
| Committed transition missing; successor cursor before head; repair with predecessor cursor | Any | Corruption; do not recreate missing evidence or spend. |

Run all positive and forbidden combinations for both successors. Pending G+2
cannot excuse missing G+1 membership. A final permitted pending tail may finish;
opening the next generation is forbidden. Initial seeded stage is generation 0.

CP3 fixes transaction composition: under common campaign ownership, reconcile
any already-published restart receipt and its monitor-state tail against the
original cursor before allowing campaign advancement. Both cold entrypoints
must use this order. Never rewrite an old restart receipt to a new cursor.
If later committed evidence already advanced, accept only an explicitly bound
descendant proof; otherwise block without renewing allowance. Exercise both
entry orders, competing recoverers and stop between the two publications.

CP4 requires coherent read-only status: sample a monotonic head revision before
and after the related files, retry a bounded number of times if it changes,
and report in-progress rather than corruption if no stable snapshot is obtained.
A stable malformed snapshot remains a blocker. Status must not call
Stage.validate/probe/preparation or journal reconciliation, create lock files,
modify bytes/mtimes/membership, or infer dispatch authority. Test virgin,
initializing, pending, stopped, complete and corrupt states while a writer
crosses one and then two successor commits.

SM3 mixed-history ancestry is closed by bounded independent inspection in
`INVENTORY_RECOVERY_SEMANTIC_CHAIN_FOLLOWUP_2026-10-27.md`. Its18-case semantic
suite includes both critic purposes and actual historical A/B prompt recursion.
The initial native preparation and completed-executor paths now pass with
scoped v3 journals. New real settled oversize/canary-failure successor tests are
under repair; their failures are retained as engineering evidence, not release.

- Independently reconstruct every later parent, not merely its recomputed hash.
  Carry original migration, inherited rule bytes, full completed prefix, source
  permissions and profile qualification unchanged; legitimate account suffix
  growth must not renew budgets or invalidate an older exact settlement.
- Keep original failed-parent proof separate from the probed first child. A
  no-call replay must prove the applied split and identical completed prefix;
  bind that observed child into both plan replay and the required fresh canary.
  Test cold reopen, changed first child, lost/reordered observations and death
  before/after probe intent, observation, report, plan and terminal publication.
- Use the same scoped document reservation journal across generations. Reopening
  a child cannot forget failed canaries, retry allocations, profile consumption,
  inherited diagnostic handoff or charged split expansion. Test siblings sharing
  a root, last funded pair, failed canary with unallocated retry, and a later
  second successor after a completed first child.
- Validate ordered fallback against the exact independently replayed qualification
  receipt, not a caller's asserted profile/hash. Canary-only, skipped, rejected,
  stale-route and unfunded qualifications must fail before any new reservation.
- Plan construction, history replay and native dispatch have different runtime
  scopes. Public entrypoints must reproduce cold-process operation without
  requiring an already-installed historical semantic context or nested global
  warmup. Actual production preflight must rerun after this integration.

Transaction release requires a monotonic head with committed transition hashes
and pending intent. Missing committed cursor/history/repair receipt is not an
empty campaign. Pending preparation may resume exactly; no fallback guessing or
repeated purchase. Cover death before/after each publication, stale cursor,
duplicate generation, concurrent owner, symlinked mutable path, malformed JSON,
disk-write failure, stop during commit and recovery after a legitimate account
extension. Native settlement/receipt progress must drive supervisor status.

Continuation review CD1/CD2 adds two mandatory direct predicates: persist only
the canonical qualification returned by independent verification, and validate
every intervening v3 generation's prepared transition/probe/authority before
extending its prefix or cumulative charge. The candidate `ancestry.py` performs
bounded read-only traversal ending at the original budget source gate, rejects
cycles and missing preparation records, checks exact first-child proof rewrites,
and re-verifies inherited fallback qualifications. Follow-up and native
regressions remain required. Do not treat an authentic immediate settlement as
proof that the entire source/admission chain is intact. Ancestor checks precede
new execution locks; reacquire and compare the parent plan before reading its
settled state. No release approval is inferred from these candidate repairs.

Follow-up closes CD1 and the recursive portion of CD2, but CD2-F1 requires the
complete accepted probe report (including transcript digest) to be bound into
the admitted native plan. Mutually consistent rehashes of observation/report
files must not pass against a sealed plan. Add remove/reorder-and-rehash cases
through the actual ancestor gate, not only ordinary cold preparation.

Long-document qualification must measure validation cost across generations,
not just correctness. Avoid repeatedly warming the entire historical account
inside each native settlement helper. Any future replay cache must be bounded
to an exact operation/source/account-prefix view and validate immutable file
membership; never skip ancestry solely because a prior generation once passed.
Record phase/receipt progress during expensive offline replay so a healthy
worker does not conceal a stalled validation phase.

Actual current-source preflight `preparation/f4911c92ee64fd8b71e2` failed after
262.75 seconds with unchanged source/account/grant/cursor and zero calls. Root
cause: closing the explicit historical semantic scope does not close the
original-window context installed inside `accounting.history_scope`; document
semantics then correctly rejects installation beneath that live context. Repair
the scope lifetime, not the guard: fully unwind the old accounting/semantic
stack, validate document origin inside a fresh historical read scope, install
document semantics before reentering historical accounting. Avoid globally
resetting context flags or widening receipt permissions. Reproduce this exact
outer-context ordering in a small regression before another actual preflight.

## Historical checkpoint — master 3.91 / ensemble 181

EX1 is repaired: late stops publish a durable pause while preserving any sealed
terminal; 30 executor/owner/terminal regressions pass. Actual offline production
preparation replayed all166 retained responses and reached the exact439-request
continuation with unchanged source, account, grant and cursor. That receipt and
the earlier465-case suite predate current migration edits and are historical.
Root migration now imports allocated historical consumption separately from new
funded pairs. The unadmitted proposal distinguishes3 sequences per lineage and
12 shared per root, preserving all8 old diagnostics and the independent17-charge
carry-forward. Fresh diagnostic-only continuation consumes a new funded pair.
Review found RI1 (rehashed history omission at direct validation) and RI2 (valid
zero-process cancellation/resume rejected by adjacency). Repairs and genuine
native regressions are running with16 workers; follow-up review is pending.
The offline probe now retains complete normalized source observations for the
required actual eight-sequence/window0054 ownership preflight and crash replay.
Next gates: this ownership proof, prospective semantic bounds, durable campaign
transitions, canonical supervisor admission/handover, combined long-document
failure soak, then exact-source release validation and grouped admission.
Repair/retest/refresh remains mandatory after every phase and stop.
Production has NOT resumed:166 retained/439 unfinished; no live calls or
production authority/service mutations.535 calls/291,040,000 tokens remain a
proposal, not newly admitted authority.

Current evidence: all50 focused migration/ownership/preparation regressions
passed in172.85 seconds; independent follow-up closes RI1/RI2. The full exact
suite passes490 cases with16 workers in323.83 seconds, unchanged source and
authority, at `validation/3473e1451996260e713b/f7191fcdaeca/validation.json`.
Actual ZLB ownership preparation remains running at
`preparation/2a2ac863733f40338155`; do not infer its result from the suite.

Required review additions: reject rehashed omitted/profile/receipt history at
direct transition and plan boundaries, not only Stage preparation. Preserve
native zero-process cancellation charges and all cancelled retry allocations;
exact resume must neither erase history nor make an allocated retry diagnostic.
Persist complete native observations before the probe success marker; test
both publication cuts, import cuts, duplicate/restarted parse metadata, altered
immutable source/request/depth/membership and missing import after reservation.
The actual no-call preflight must join all8 allocated historical diagnostics,
including3 sequences sharing window0054 and1 on its unfinished child, to live
ownership IDs. Require idempotent import and sufficient3/12 lineage/root room
before any live claim. Keep all prior phase/exit gates and failure refreshes.

### Remaining integration design and corner cases

1. Version prospective semantics separately. Keep immutable historical rule and
   receipt verification. Validate each rule against independently settled native
   failure, unique request/receipt membership and regenerated exact recipe.
   Enforce depth3 and14 total children per original source-file/window/purpose
   root, including old size-split ancestors. Document split capacity bounds total
   expansion;16 independent incidents must not become a global document limit.
   Repeated window names in different files, overlapping windows, nested critic
   context, child abstention/empty/foreign concepts and missing judgments need
   explicit tests. A split must preserve original merged-window acceptance.
2. Build every later successor from the settled native parent under exclusive
   locks, preserving exact completed prefix and unfinished request. Carry the
   same document journal, original migration and inherited consumption; never
   reimport only the most recent stage. Count every cancelled/failed allocation,
   diagnostic and split expansion once against the cumulative call envelope.
   Exclude unknown live allocations and uncertain process ownership. Discover
   children with no inference; require actual first-child request and unchanged
   retained prefix before preparation. Ordered fallback requires existing native
   qualification; zero qualification capacity is a real budget stop.
3. Make campaign advancement a durable transaction: persist source-bound repair
   intent, prepare/validate the exact successor, persist its immutable transition,
   commit the cursor, then publish the repair result. Reopen any intermediate
   cut from the intent. A committed cursor must have its complete predecessor
   chain; missing latest/intermediate receipts, replaced intent, a foreign plan
   or a competing preparer must never silently roll back or allocate again.
   Stops between any two commits remain durable vetoes; completion after native
   bundle publication is offline reconciliation with zero new provider calls.
4. Integrate the actual admission factory and supervisor using the current
   installed history supervisor as predecessor. Retain all old stop roots and
   exclusion locks, remaining restart charges and inherited worker ownership.
   Bind plan/policy/source, existing account/grant, route and human approval
   settings to the executable command. Observe actual new generation files;
   heartbeat alone is not work progress. A failed worker, lost acknowledgement,
   surviving provider, accounting failure and finalization failure each need
   distinct status and restart handling. Prove this through the public entrypoint.
5. Run a combined multi-generation document fixture: thousands of requests,
   more than16 independent incidents, network backoff, failed/successful canaries,
   timeout/oversize splitting, siblings, qualified fallback, repeated stops,
   and process deaths at transaction cuts. Assert exact-once native allocations,
   stable cumulative budgets, precise source coverage and original validators.
   Synthetic registry scale alone is insufficient. Finally freeze the completed
   integration, run exact-source suite and production no-call preflight, close
   independent findings, refresh both masters, and prepare grouped admission.

## Historical checkpoint — master 3.90 / ensemble 180

ST1/ST2 and RQ1 are independently closed in their bounded follow-ups. Native
executor and dynamic ownership are implemented, including extraction-child to
merged-critic ancestry, exact parent rule matching and overlapping windows.
The combined 32-case run produced31 passes and one test-reference failure;
correcting that reference yields a passing completed-v3 cold-history case.
Actual production successor preparation is running offline. Executor review
is pending. No paid inference, account/grant mutation or service change.

Additional required corner cases from current review:
- Import every actually allocated historical recovery sequence, not unallocated
  attempt descriptors. Preserve diagnostic-only sequences and completed retries,
  exact source ancestry, profile and receipt identity. A fresh diagnostic may
  be required; an old passing canary never grants a new retry by itself.
- Check inherited root limits before admitting a successor. The real unfinished
  request is an extraction split child, unlike the reconstruction fixture.
  Test sibling retries and diagnostic-only budget exhaustion explicitly; do not
  reset root allowances or silently omit history to make preparation pass.
- Replace prospective semantic global16-rule/14-child limits with document
  capacity plus per-root depth/child limits; leave historical validators frozen.
- Retain native semantic rejection as nonpass; exercise crashes after native
  bundle publication and before settlement, with zero duplicate provider calls.
- Finish replayable repair-intent/successor/cursor commits, canonical supervisor
  admission, old stop authorities and combined long-document failures before
  exact-source release validation and concrete grouped deployment approval.

Repair/retest/refresh after every phase and stop remains mandatory. Production
stays at166 retained/439 unfinished;535 calls/291,040,000 tokens and ceiling113
are proposed, not admitted. The prior phase/exit matrix remains operative.

### Reviewed next repair boundaries

The source-frozen 465-case suite passes at
`validation/ffa141d30671e6930c17/7ce5580ce14e`. EX1 remains open despite this
pass: a user stop arriving inside failure finalization bypasses durable pause
publication. Catch finalization interruptions while native ownership is still
held. Before terminal commit, publish the ordinary unsealed pause; after a
pass/nonpass commit, preserve that terminal and publish a separate pause with
pending-settlement status. Cover real stop files before/after terminal commit,
success and nonpass settlement, exact authorization, and process death. A stop
must neither disappear from reporting nor rewrite already sealed evidence.

The first actual production preparation failed before replay on an older
receipt lacking `qualification-capture.json`. The prospective dispatcher now
delegates that case to its exact retained historical validator; it still rejects
foreign receipt membership. Three targeted dispatch cases pass; the second
actual preparation is running. The failed preparation retained its receipt and
left source, account, grant and production cursor unchanged.

Historical root migration must bind only actually allocated calls and validate
the complete old layout and native settlement. The real lineage contains eight
allocated canaries across four reconnect generations. Three belong to original
window0054: the failed root, successful first child, and diagnostic-only second
child. Therefore the current shared three-sequence root default would stop the
new successor immediately if history were imported correctly. The proposed
production policy must distinguish three sequences per exact lineage from a
shared twelve-sequence root ceiling (three ordered profiles across four depth
levels); siblings consume that shared ceiling. This changes the unadmitted
proposal, not existing authority. The document envelope remains535 calls and
291,040,000 tokens. Import diagnostic-only history as consumed diagnostics
without marking an unlaunched retry as attempted; require a fresh paid canary
before its new retry. Never reuse the old canary or erase its existing charge.

RM1/RM2 plan review amendments: historical consumption is stored separately
from prospective pair reservations. Its eight rows consume root/lineage slots
but no new earmarks or slots in the32-new-pair envelope. Native allocation
charges, sequence counts, reserved pair capacity and the independently proven
17-charge carry-forward remain distinct. Test acceptance of new pair32 and
rejection of33 on independent roots after import, with zero authority writes.

Diagnostic-only means the old retry was provably unallocated, not merely
incomplete or missing a response. Bind the replacement reservation to that
exact historical diagnostic and incident, preserve the old charge, retire its
unused retry opportunity, and allocate a fresh funded canary/retry pair. This
replacement consumes another lineage/root sequence slot. Exact reentry returns
the same reservation; neither a failed fresh canary nor a later generation
reopens the historical opportunity. An allocated incomplete/unknown retry
cannot use this path. Proven zero-process cancellation keeps its separate rules.

The twelve-root ceiling is an independent shared policy cap; three profiles
across four depths does not grant every sibling three new attempts. Exhaustion
blocks even with unused depth or qualified profiles remaining. Qualification
capacity stays zero. Canonical no-call replay must join every historical row
to the same live ownership IDs, including the real window0054 child and its
successful sibling. Bind complete unique predecessor allocation membership,
not duplicated copied-prefix references; missing or ambiguous mapping blocks.

Required regressions: eight-sequence exact native import; incomplete pair;
unallocated descriptor excluded; same-profile completed retry cannot reroll;
diagnostic-only continuation; parent/child/sibling shared limits; interrupted
import, missing or changed migration records; and zero-call preflight of the
actual window0054 successor. No new root allowance is live before the grouped
recovery-limit admission gate.

## Historical component checkpoint — master 3.89 / ensemble 179

SC1/SC2 successor findings are independently closed. Stage findings ST1/ST2
are repaired prospectively and awaiting follow-up: native grant validation
binds the current account and stage holds; a durable preparation intent binds
the original account prefix and exact plan before either artifact is published.
Crashes followed by valid reservation or settlement growth replay that intent;
insufficient current capacity blocks without renewing authority. Mixed-history
settlement now avoids captured legacy readers and preserves conservative usage
markers for both old and new plans. Thirty-two focused cases passed together;
the corrected cold public entrypoint passes separately. Freeze and repeat the
complete source-bound suite after integration; the 409-case receipt is historical.

Additional release cases: cold import within historical accounting scopes;
old/new completed/incomplete settlements and zero-allocation refunds; real
grant holds before/after claim; changed grant contents with retained identity;
death after authority publication followed by reservation/settlement growth;
missing intent, exhausted remaining capacity, and actual public preparation.
Next implement dynamic native request ownership, inherited ancestry/root charges,
campaign/admission and transition recovery, then combined long-document soak.
The prior phase/exit matrix and repair-refresh procedure below remain required.
Production is unchanged at166 retained/439 unfinished; no live continuation.

## Historical execution plan — master 3.88 / ensemble 178

RR1-F1 is independently closed in
`docs/reviews/INVENTORY_RECOVERY_RR1_FOLLOWUP_2026-10-27.md`. The durable head
binds committed transition membership, hashes and generations; pending intent
allows exact replay after any publication cut. Missing head or committed
transition blocks rollback. Sixty-nine resume cases pass, including two roots
with identical original stop bytes and independent authorized successors.
Native successor construction now preserves the 17-charge migration boundary,
request/prefix/profile and retained qualification. The account source anchor
checks immutable event/plan prefixes so new legitimate reservations do not
invalidate old migration evidence. Three focused native tests pass; successor
review is pending. Preparation/admission/campaign remain implementation gates.

Latest full suite receipt (409 cases):
`validation/37e969211fd645b878c1/5c19eae51a23/validation.json`.
Latest completed migration audit: `migration/9546e122c8c0582fd27f` (30 sources,
166/439, sufficient proposed envelope, zero calls/writes, authority unchanged).
Both receipts are historical after subsequent edits; freeze and revalidate
the completed integration before release. No production execution has resumed.

Additional acceptance checks for the next phase: reinspection after a valid
native reservation, rejection of truncated/replaced account history or changed
allowance, source-bound preparation after interrupted snapshot/plan publication,
and canonical request ownership derived from native semantic observations.
Future prompts depend on earlier accepted responses, so do not preassign their
source lineage solely from logical slot numbers. Validate inherited split
ancestry before the first new request; preserve per-root limits across siblings.

## Historical execution plan — master 3.87 / ensemble 177

Review of the actual dispatcher exposed missing durable phases: RT1,
allocated but rejected before process launch; RT2, dispatch committed but no
native allocation. Candidate repairs are implemented and 97 focused cases
pass with 16 workers. Independent follow-up and full exact-source validation
are running. The 362-case pass predates these repairs and is historical.

Bounded follow-up then identified RR1: after cancellation A is retired, a
later stop B must not invalidate A's exact authorization, but still requires
its own current exact resume. Immutable cancellation-bound authorization and
stop-supersession receipts now retain that history. Rollback, missing current
stop/resume or wrong current authorization remains fail-closed. New regressions
cover A→resume A→retire→B, B before allocation or launch, exact-once restart,
wrong/missing B authorization and a cold cut at retirement. Independent review
and full exact-source revalidation are required after this repair.

The completion criterion is native execution and verified output, not a count
of component tests. Remaining work proceeds in this order:

| Phase | Execution and corner cases | Automated exit evidence |
| --- | --- | --- |
| Resume repair | Distinguish intent-only, allocated unknown, persisted result and cancelled-before-launch. Preserve UUID/descriptor/prefix, stop authority, canary freshness, root limits and every charge. Retain chained authorization when later valid stop controls supersede retired ones. | Hard exits before allocation and before/after cancellation retirement, both roles; stop A/resume A/retire/B before allocation or launch; missing/wrong B authorization, rollback, absent stop, expired canary, foreign call/runtime evidence; exact-once reopen and budget exhaustion. |
| Successor and admission | Build from independently replayed sealed generation-02; carry 17 charges, 166 retained and 439 unfinished, qualified Astra, full ancestry and immutable source/profile/route. Bind current supervisor handover, canonical locks, stop roots, account and grant. | Mutated source/policy/qualification/request/authority rejected before reservation; actual native factory fixture, historical reader compatibility and no production writes during preflight. |
| Campaign execution | Connect native executor, paired dispatcher, request-to-lineage mapping, semantic validators, typed terminal settlement and source-bound status refresh. | Exact request replay; base-request stop; native incomplete/semantic/oversize/unknown paths; no success on missing output or semantic reroll; complete/incomplete mixed history accounting. |
| Transition recovery | Persist repair intent, successor and cursor separately with replayable commits. Retain root budgets across split siblings, generations and profiles. | Process death before/after each commit; repeated restart; cancelled pair never reopens; stale canary cannot fund a retry; split coverage is exact and disjoint; unqualified fallback blocks. |
| Document soak and release | Combine transient outages, 900-second waits, repeated timeout, bounded output, splits, fallback, sibling interleaving, user stop and machine crash on a large document. Freeze sources for final validation and migration/preflight. | Full exact-source 16-worker suite; combined multi-generation soak, not only 1,000 registry roots; sequential review with no unresolved high findings; source/authority stable audit and reproducible receipts. |
| Controlled continuation | After gates pass, present one concrete recovery-limit/deployment request if outside existing authority. Install and launch under verified supervision, preserving qualified route. | Verified new manuscript receipt before reporting resumed execution; truthful progress/blocker and no final ZLB acceptance claim. |

Cross-cutting invariants: no reset of cumulative budgets; no duplicate purchase
for an uncertain launched request; only intact zero-process evidence can be
cancelled; no symlinked mutable journals; no release from a stale source audit;
no inference or account/service mutation in offline validation. Disk-full,
partial JSON, lost ledger, ownership loss, changed authority and unknown process
state must retain evidence and publish a precise blocker. A stop callback
without exact control-file proof remains blocked; resume matches the current
stop and source contract. Filesystem cuts around atomic replace leave either
the prior valid record or a verifiable new one, never guessed spending. Every bounded wait
must expose its next eligible time; elapsed time alone grants no restart.

After every phase or stop: reconcile native process/allocation state, classify
the cause, retain the failure receipt, run targeted regressions, inspect the
findings, update both masters and the execution checkpoint, and continue any
independently authorized work. Source edits invalidate release bindings;
freeze again before the full suite, migration audit and deployment preflight.
All intermediate acceptance is repeatable code/receipt validation. Human
content review is reserved for the final actual ZLB output.

Production remains stopped at the last verified 166 retained/439 unfinished.
The proposed 535-call/291,040,000-token envelope and ceiling 113 are not admitted.

## Historical integration sequence — master 3.86 / ensemble 176

SO1/SO2 fixes pass 20 owner regressions and bounded independent follow-up.
The actual production admission factory must bind the configuration returned
to CampaignAuthority; self-consistent caller data is not sufficient authority.
Next units, each with regression and sequential findings-only review:
1. Versioned plan/runtime/layout: support inherited charge 17 and ceiling 113
   without changing frozen v2 readers or widening historical eligibility.
   Reject altered policies, attempt membership, negative/bool counters, wrong
   retained profile and unqualified fallback. Read old/new accounts together.
2. Owned paired dispatch: reserve the full canary/retry before any canary,
   conserve base slots and retained work, reconcile native tails and completed
   pairs before retry. Unknown/no-result allocations never retransmit blindly.
3. Launch-time native UUID/runtime directory join: reject substitution even
   for identical prompts/profiles; stop and ownership veto immediately before
   launch. Cover death before/after each intent/result/account commit.
4. Executor/campaign: bind actual admission, inherited stop and handover,
   full lineage/split/semantic rules, monotone cursor/repair transitions and
   source-bound refresh. Do not seal user pause or reroll semantic rejection.
5. Combined fallback/split/sibling/stop/crash document soak, full exact-source
   suite and sequential migration/preflight. Freeze sources during audits.
6. Only after release gates pass, grouped recovery-limit/deployment approval
   and a verified new manuscript receipt. Only final ZLB content acceptance
   requires human judgment; intermediate checks are repeatable regressions.

The older 312-case receipt is historical after these changes. Production and
authority stay untouched; no candidate integration pass implies live admission.

## Current implementation gate — master 3.85 / ensemble 175

The exact-source validator passes 312 cases with 16 workers at
`validation/4c89a42fef4326e69892/9f13e4cf6ef3`; source and authority unchanged.
Completed prospective units: inherited parent-held job lock and acknowledged
worker launch; typed prelaunch stop preservation; durable pair earmarks;
native-result-to-pair settlement with exact request/runtime join; real native
stage ownership and claim-before-executor metadata ordering. These are not a
deployable campaign. Earmark review has no concrete high finding under the
owner prerequisite; SV1/SV2 safety, LH1 and NS1 have bounded follow-up closure.
Owner review remains pending. Failed/source-invalidated receipts stay intact.

Additional corner cases and remaining executable acceptance gates:
- Bind the configured global ownership path and inherited predecessor lease
  in canonical admission; a caller-supplied lock alone is not entrypoint proof.
- Persist allocation-to-runtime identity at actual launch. Exact prompt/profile
  equality rejects foreign requests but cannot distinguish identical calls.
- Compose new-policy plan, native replay/layout/attempt keys and executor without
  weakening frozen v2 readers. Preserve inherited 17 charges and qualified Astra.
- Map every native execution/settlement through owned paired operations; test
  later failures with previous complete pairs, same-prompt receipt substitution,
  unknown allocation, stop after allocation, incomplete native results and
  cold process death at every commit boundary.
- Integrate current supervisor handover, canonical old-root stop authority,
  transition/cursor/repair commit recovery and source-bound master refresh.
- Validate combined large-document failure sequences, not only registry scale.
- Freeze sources before migration audit: the last audit at
  `migration/87827503d4e4b00418be` failed because candidate edits raced the audit;
  authority was unchanged and zero provider calls/account writes occurred.
- After complete integration/review/preflight, request grouped explicit limit
  and concrete deployment approval; verify a new manuscript receipt before
  reporting production progress. Production is still sealed at 166/439.

## Current repair result — master 3.84 / ensemble 174

The exact-source 285-case suite passes with 16 workers at
`validation/bbcda114bbb8d3761ccb/0eef18912a42`; source and authority checks pass.
The historical 259/260 failure and candidate 274/275 failure below remain
evidence, not overwritten reruns. The new monitor has deterministic old/new
race comparison, absent-ack/result publication races and true cold unpublished
worker tests. SV1 is independently closed; SV2's unsafe restart is closed by
conservative observation, with full launch handoff still pending. The revised
native allocator requires a durable pair earmark, binds one stage to one
document journal and preserves existing account/grant holds. Stage-binding
and journal-commit hard exits resume idempotently; a late owner veto does not
commit the pair; a competing journal is refused. Capacity review is pending.
Migration audit `migration/e2ad8621638c8d2a4a2f` passes for 18 current candidate
sources, verifies 166 retained/439 unfinished, preserves authority and makes
zero provider calls/account writes. No live deployment or inference is authorized.

Remaining implementation order, without new human intermediate judgments:
1. Finish bounded earmark review; fix findings and rerun exact-source checks.
2. Add parent-acquired, authenticated per-job lock inheritance from launch
   intent through worker acknowledgement. Cover death before Popen, after
   Popen before PID publication, and child death before ack. Until this exists,
   unpublished/no-ack work stays unresolved without taking its lock or charging
   a restart; timers alone cannot prove a never-launched worker.
3. Integrate new-policy stage/runtime/campaign dispatch, atomic native ownership
   and authority scopes, full source ancestry, split rules and attempt keys.
   Claim before executor metadata publication; do not weaken the claim reader
   or edit frozen v2 contracts. Reuse the retained qualified Astra profile.
4. Complete native allocation/result/pair settlement, stage transition/cursor,
   source-bound second handover and stop continuity crash tests. Then combined
   fallback/split/sibling/stop/crash large-document testing; the 1,000-root
   registry test alone is not a document soak.
5. Bind final sources, migration, review and preflight; request grouped explicit
   recovery-envelope and concrete deployment approval. Verify a new manuscript
   receipt before reporting resumed production.

## Current execution gate — master 3.83 / ensemble 173

The latest retained validation snapshot `9b7b0e3420f51972670a/4ceae3377ef9`
fails one of 260 cases: the pre-child-ack cold monitor restart. The isolated
rerun passed but does not invalidate the failure. The recovery wrapper can
observe a live worker, then delegate to a monitor that sees the same worker
dead and publishes BLOCKED_ENGINEERING before the surviving inherited-lock
child passes source-bound launch admission. A new versioned monitor must use
one ownership decision per tick and route disappearance through native
reconciliation. Never authorize a blocked-state child or remove lock checks.

Required tests: force the live-to-dead observation ordering; preserve phase
while an inherited child holds the job lock without a persisted child PID;
recover only once after quiescence; retain results arriving at either boundary;
reject wrong acknowledgement/request/heartbeat identities; respect stop and
terminal states; maintain progress warnings without duplicate launches. Retain
the failing historical fixture unchanged and add prospective cold-process
coverage. A later green historical run cannot close this gate by itself.

Allocation follow-up closes AL1–AL3 specifically. Still add cold allocation
cuts, changed-prefix/intervening-tail/duplicate-UUID/wrong-incident negatives,
and capacity inspection with a populated disappearing ledger. Pair reservation
must commit a durable native-stage earmark under the same exclusive owner;
an inspection snapshot alone is not spending permission. New source edits
invalidate prior validation/migration bindings; retain historical receipts.

Status at 27 October 2026, 13:35 Asia/Shanghai: execution stopped at 04:36:36.
Generation-02 completed one manuscript request after the successful split;
166 responses are retained and 439 logical requests remain. The stage is
terminal nonpass and the worker has an exit-code-1 result. No automatic restart
or final ZLB acceptance is claimed.

## Confirmed causes

The recovery limit is 16 cumulative extra sessions, separate from the total
token/call authority and supervisor worker-restart limit. Generation-zero began
with three inherited charges; its seven allocations and three completions
carried seven charges into generation-01. That stage used 30 allocations for
24 completed manuscript requests. Six unproductive/diagnostic allocations plus
one extra split child raised generation-02's inherited charge to 14. Its two
canaries consumed the remaining two slots. After request 0001 timed out and its
canary passed, the guard refused another paid retry at 16/16. The recorded
limit enforcement is consistent with the current frozen contract; this is not
evidence that the much larger token budget is exhausted.

There is a separate diagnosis defect. `execution.accounted_model` raises
`RecoveryBlocked("BLOCKED_BUDGET", ...)`, but the manuscript boundary retains
only its wrapped error text. `campaign.diagnose_terminal` derives the terminal
category from the reconstructed layout's `mode="request"`; `lifecycle.POLICY`
maps that mode to `BLOCKED_SEMANTIC`. Consequently the supervisor reports a
semantic failure even though the terminal error explicitly identifies budget
exhaustion. No failed semantic judgment is established by this stop.

Evidence: campaign/generation-02/{plan,transition,allocation-ledger,execution}.json;
campaign/incidents/6dcb206a981846867c0b46682c7d33252e4ed2d682c3120288bed1fdc70c7ebe.json;
history-repair-20261026-01/live/supervision/jobs/job-0001/result.json under
docs/audits/2026-10-05/master-program/automatic-execution/sol-inventory-failure-first-20261026-01.
The independent reporter accepted the terminal desktop notification.

## Implementation sequence and acceptance gates

Plan revision, 27 October 2026: master 3.80 / ensemble 170. The following is
prospective implementation work. Runtime changes, new policy admission and live
execution have not occurred. Preserve the sealed production evidence and use
the SSD workspace for candidate code, offline fixtures and derived reports.

### 1. Reproduce and reconcile before changing policy

Build a regression through the real invocation wrapper, execution terminal,
settlement reader, campaign diagnosis and supervisor publication. Reproduce
14 inherited charges, a successful initial canary and manuscript response,
the next request's timeout, a successful second canary, and refusal of the
retry. It must expose both the unusable final canary and the wrong semantic
label. A test of the limit check alone does not cover these defects.

Create a read-only migration report binding the generation-02 plan, terminal,
ledger, allocation seal, unique account settlement, retained prefix and
qualification. Cross-check all 166 retained responses. Generation-02 has four
allocations and one completed manuscript response: applying the existing
carry-forward formula would yield 14 + (4 - 1) = 17. Its in-stage extra-call
counter reached 16. These are different accounting boundaries; a successor
must reconcile them rather than set its inherited usage to 16 or reset it.
Do not call the old successor constructor blindly: it accepts decomposition
or provider-availability incidents, not this budget stop.

Pass gate: an immutable migration report explains every allocation and each
counter, binds the actual unfinished request, and records zero provider calls
and zero account/grant writes. Any unresolved settlement or ownership blocks
spending. Historical terminals remain unchanged; corrections are derived
records linked to their original evidence.

### 2. Preserve the actual failure and unify reporting

Introduce a versioned structured failure record with category, originating
phase, request/incident identity, evidence references and retry eligibility.
Propagate it through the invocation wrapper, terminal, settlement, campaign
and notification. Preserve the causal error text as supporting information.
Budget, accounting, ownership, user stop, provider/transport, request size,
protocol/engineering and semantic failures remain distinct. An unknown cause
is an engineering/accounting investigation, not an inferred semantic verdict.

Only explicit validator evidence establishes semantic rejection; operational
phase names cannot establish it. True semantic failures retain the existing
no-reroll behavior. A historical compatibility reader must justify any derived
category from bound ledger/runtime evidence; loose error-string matching is
insufficient to authorize a new call.

Pass gate: the full reproduction reports BLOCKED_BUDGET consistently, including
the supervisor and desktop payload. Independent negative cases prove that
semantic, authentication, stop and ambiguous-ownership failures cannot acquire
transport-retry eligibility through wrapping or restart.

### 3. Admit one coherent document recovery policy

Centralize prospective policy in one validated configuration consumed by the
planner, allocator, continuation builder, supervisor and replay verifier.
Inventory all current ceilings together: recovery sessions (16), campaign
generations (16), aggregate split children (14), split depth (3), worker
restarts, aggregate calls/tokens and existing request-size limits. Changing
only one ceiling is not a long-document repair. Separate per-request split
depth from document-wide child counts; derive any structural stage ceiling
from the admitted recovery plan rather than reuse a small constant everywhere.

Use two levels of control. The document has an explicit cumulative allowance
within its authorized call/token limits. Each original request lineage has a
bounded retry/fallback/split policy, so one bad passage cannot spend the whole
document budget. Persist consumed actions across stages and child requests;
splitting or changing models must not renew an exact-retry counter. Preserve
existing split depth/protected-object rules unless separately justified by
tests; expanding document capacity does not relax semantic boundaries.

Before admission, compute a concrete capacity table from the retained spend,
439 unfinished requests, permitted recovery sequences, split overhead and
any genuinely missing qualification. Report planned base calls, diagnostic
calls, retry calls, extra child work, token reservations and aggregate
headroom separately. Qualification already valid for the bound profile is
reused. Choose and record an explicit fault-tolerance envelope, then calculate
the allowance required for it; do not substitute another unexplained constant
or promise unlimited recovery. Admission must disclose insufficient headroom
before deployment and must not silently raise the aggregate authority.

Under the existing exclusive spending owner, persist an idempotent reservation
for an entire recovery step before its canary: the diagnostic plus the exact
retry, covering both calls and conservative token bounds. Distinguish a base
request already reserved from an additional retry to avoid double charging.
Bind reservations to document, request lineage, incident and profile. Claim
and dispatch must be crash recoverable; reconcile pending allocations before
reuse. Release only provably undispatched capacity. Unknown outcomes retain
their reservation until evidence resolves them.

Represent split expansion explicitly. Extra children add planned work once;
their eventual provider allocations settle that reserved work rather than
charging the expansion again. Keep the original legacy charge visible in the
migration report and prove conservation during any normalization. The current
stage is sealed: changing its policy or receipts in place is prohibited.

Pass gate: one remaining recovery slot cannot buy a canary that requires a
second slot for its retry. Replaying or crashing at every reservation, dispatch,
settlement and successor boundary neither resets usage nor duplicates charges.
The reviewed capacity table covers the chosen long-document failure envelope.
An increased recovery allowance requires explicit prospective authorization;
the larger token grant alone is not an authorization to change this limit.

### 4. Make timeout recovery a bounded Python state machine

Use one coordinator for new plans, with durable actions and typed outcomes;
keep legacy readers only for compatibility with sealed evidence. Implement
the normal path as execute, validate, checkpoint, refresh and continue.
After an eligible timeout, reconcile ownership and usage, diagnose from the
retained request/process/stream receipts, reserve the recovery sequence, wait
until the receipt-bound 900-second backoff expires, canary, and retry the exact
request once on that profile. Reuse a still-valid bound canary after a crash;
do not repurchase it merely because a process or stage changed.

A passing canary establishes only that a small call worked. Record prompt
size, expected response size, elapsed time, stream/error observations and
termination so repeated large-request failures can be distinguished from
observed provider failures without inventing a root cause. When the same
request times out again after a passing canary, use the qualified split path
if legal; otherwise use the next eligible qualified model. Follow Sol/max,
Astra/xhigh, Sol/xhigh ordering while preserving the already-selected valid
fallback and completed work. A canary is not semantic qualification.

A failed canary blocks manuscript traffic to that profile. Persist a bounded
provider cooldown/fallback decision; any later retry observes the same
receipt-bound wait and admitted budget. Authentication, refusal, malformed
evidence, true semantic failure and unresolved live ownership do not enter a
blind retry loop. A legitimate final blocker records the exact reason and
next permitted action. No live patching of arbitrary code is delegated to the
supervisor.

Pass gate: repeated independent faults recover automatically within policy;
repeated faults on the same lineage reach a justified split/fallback or precise
terminal blocker. Stop requests survive all transitions. Offline recovery
does not depend on Claude or intermediate human judgments.

### 5. Integrate progress monitoring and phase refresh

Include the tested `inventory_campaign_progress.py` helper and its tests in
the new supervisor contract, adapting its bound if the admitted generation
policy changes. The existing helper itself accepts only 1–16 generations;
raising campaign capacity without updating it would leave another mismatch.
Cover every admitted successor and test the final permitted generation.

Publish one authoritative status projection: current phase/category, retained
and unfinished work, last completed manuscript receipt, current owned action,
last durable activity, recovery spend/reservations/remaining capacity and
next action with eligibility time. Distinguish new business completions from
diagnostic activity and heartbeat; heartbeat alone cannot establish progress.
Use the same projection for CLI status, supervisor notifications and master
checkpoints. Refresh it after each phase, repair, terminal stop and restart.

Pass gate: successor completions clear a false stall, genuine stalls still
alert, and all status surfaces agree after a budget stop or crash. A delivered
notification or successful process launch cannot mark recovery complete.

### 6. Validate, review and deploy the complete release

Run offline tests with 16 workers; provider calls and account mutations remain
sequential. Use deterministic local provider fixtures and the real persisted
execution/settlement/supervisor boundaries, with a synthetic clock for waits.
Bind exact source and test membership to the release and retain test evidence.

| Regression | Required outcome |
| --- | --- |
| Actual 14-inherited exhaustion sequence | Reproduces the old defects and verifies precise budget reporting |
| Only one slot remains | Zero new canary allocations when its retry cannot be reserved |
| Reservation/dispatch/receipt/settlement crash cuts | No duplicate purchase, forgotten reservation or unsafe refund |
| Sealed generation-02 migration | All 166 responses preserved; every allocation and inherited charge explained |
| Split and fallback across multiple stages | Conserved spend, preserved qualification and lineage retry bounds |
| Wrapper through desktop notification | Structured categories survive; genuine semantic failures remain terminal |
| Long document with more than 16 independent incidents | Completes within an explicitly sufficient policy; no hidden old ceiling |
| Deliberately insufficient allowance | Stops before unaffordable work with exact required/available capacity |
| Same passage repeatedly fails | Bounded retry then legal split/fallback; no infinite lineage renewal |
| Provider outage, partial response and unknown owner | Correct cooldown/reconciliation; no duplicate or unjustified retry |
| Successor progress, idle heartbeat and final generation | Accurate progress and genuine stall reporting |
| Cold restart and user stop | Correct ownership restoration and durable stop veto |

The long-document fixture must combine faults, splitting, stage transitions
and process deaths in one run, plus a representative large-document soak
covering thousands of requests for FinMarketing scale. Two isolated injected
transport failures do not establish readiness for that workload. Measure
replay/checkpoint cost and evidence growth as well as correctness.

Review the complete candidate against these gates, fix findings, then repeat
only affected checks. Prepare a separately versioned continuation rooted in
the sealed generation-02 evidence, reusing its completed work and qualification.
Before requesting host/limit approval, make the exact policy, capacity table,
tests, source identities and fixed deployment actions reviewable. Group the
required approvals, perform the admitted handover, and verify a newly completed
manuscript receipt before reporting that execution has recovered.

After inventory verification, continue downstream ZLB writing, automated
reviews, release/reproduction checks and automatic admission. Only final
acceptance of the actual ZLB output requires human content judgment.

## Corner-case review resolution — master 3.81 / ensemble 171

The independent findings in
`docs/reviews/INVENTORY_RECOVERY_PLAN_CORNER_REVIEW_2026-10-27.md` identify RC1–RC6.
These requirements are added to the implementation and release gates, not
declared closed merely because they are documented.

1. **RC1, units and suballocation.** Recovery pairs earmark already-held native
   stage capacity, not a second account/grant claim. Each allocated active
   session conservatively retains 544,000 tokens, including a canary. Missing
   fallback qualification requires its actual 276-call bound, not just its
   212 logical tests. Report policy charges, stage holds, step earmarks, paid
   allocations and token retention as separate dimensions. At zero global
   available calls, an existing stage may still use its own held slots.
2. **RC2, commit matrix.** Explicitly test interruption after grant hold, account
   reserve, reservation receipt, ledger creation, allocation, process start,
   call/result receipt, ledger finish, terminal, seal, settlement event,
   transition, cursor and repair receipt. Durable intents precede authoritative
   changes. Only exact, provable interrupted commits may be completed; sealed
   unknowns and success without a native result remain no-spend blockers.
3. **RC3, canary adoption.** Define finite freshness, exact incident/request/route/
   profile/source binding and one-time consumption. An old canary never grants
   live authority. Cross-version reuse requires a dedicated checked adoption
   receipt; expired or changed-context success requires a new funded canary.
   A failed canary's cooldown starts from its own failure receipt. Future or
   non-finite clocks, later failures and stop during a wait must fail safely.
4. **RC4, compatibility.** Keep all frozen v2 and history files unchanged. New
   plans dispatch to separately versioned code; historical receipts use their
   original reader and profile. The budget-stop source gate is distinct from
   the old decomposition-only constructor. Verify mixed-model cold warmup and
   qualification reuse with no rewritten lineage or repurchased controls.
5. **RC5, second handover.** Adopt the latest installed history supervisor, not
   just its original predecessor. Preserve all prior ownership exclusions,
   pending restart intents and cumulative restart charges. Bridge old-root
   stop authority explicitly. Bind one replacement root, charge handover once,
   and test surviving descendants, competing successors and repeated handover.
6. **RC6, ancestry and bounds.** Bind root identity to source, purpose and owned
   membership; record parent/child and model transitions. Separate child-local
   attempts, per-root work, split depth, per-root children, document expansion,
   split-rule count, attempt-key space and generation count. Do not expand a
   per-root semantic safeguard merely to support more unrelated roots. Test
   more than 16 independent splits, sibling partial completion and the final
   allowed generation plus one.

The first offline migration audit independently verifies all 166 retained
responses and unique settlement, with no inference or account/grant writes.
It confirms 17 legacy carry-forward charges, 439 unfinished requests and
576 available authorized calls. The illustrative proposal reserves 439 base
calls, 32 canary/retry pairs and 32 extra split calls: 535 calls and 291,040,000
conservative token units. It fits existing aggregate authority but is not
admitted, and it includes no new qualification. A missing 276-call qualification
would require a separately affordable envelope; automatic fallback cannot
promise unbudgeted work. The 32-incident envelope is a candidate, not an
empirical failure-rate guarantee or user-approved new limit.

Prospective modules under `tools/inventory_recovery_v3` are outside the frozen
release. The initial 34 component regressions pass with 16 workers. Native
integration, fault-matrix closure, final-source review and host admission remain
required; component success must not be described as production recovery.

## Plan review and current boundary

### Candidate execution checkpoint — master 3.82 / ensemble 172

The resumed 98-test baseline passed. Subsequent combined testing passed 139
tests using 16 workers; separate native-capacity and second-handover suites
passed one and four tests. The native suite passed again after the dedicated
budget source gate was added. These counts are component evidence, not full
release closure, and the earlier migration audit remains an older snapshot.

| Gate | Implemented and exercised | Still required before deployment |
| --- | --- | --- |
| RC1 | Native stage-held capacity with zero global availability; conservative pair units | Atomic earmark-to-native-attempt mapping in executor |
| RC2 | Durable claim intent cuts at intent/account/receipt/ledger/completion; typed terminal before seal and replay | Prepared-stage metadata, complete allocation/result/seal/settlement/transition/cursor fault matrix |
| RC3 | Native canary reader, expiry, one-time dispatch, supersession, stop/owner recheck, failed-canary cooldown | Native launch integration, adoption admission, durable dispatch reconciliation |
| RC4 | Dedicated budget source gate; old constructor still rejects; retained profile preserved | New-plan runtime dispatch, mixed-model cold CLI replay and release-wide source binding |
| RC5 | Chained exclusions, pending restart charge, inherited stop veto, idempotent proposal | Actual latest supervisor integration, canonical admission, cold-child descriptor and competing-owner tests |
| RC6 | Registered source ancestry, root retry cap, 32 independent splits, depth/membership tamper rejection | Actual semantic rule/attempt-key integration, combined siblings/fallback/crash/large-document soak |

Reviewer findings VC1–VC3 have candidate fixes and regressions, but are not
declared release-closed. A separate sequential review examines the actual
native-boundary unit. Root lineage consumes a shared bounded incident budget
across descendants; an exact child/profile pair cannot reset its retry by
renumbering or splitting. Splits retain parent charges and cannot buy native
calls until the executor binds the reserved work to its actual held slots.

Continue implementation automatically through these offline gates. Intermediate
judgments remain automated. Do not request human content reviews to replace
missing tests. Group only concrete new-limit and deployment permissions after
the integrated candidate has passed review and source-bound preflight.

Review of this sequence against the code exposed four additional constraints:
the successor must account for 17 legacy carry-forward charges rather than
reuse the displayed 16; budget stops need a dedicated migration path; the
generation/split limits and progress helper must be reviewed with the session
cap; and a passing canary cannot diagnose why a manuscript call timed out.
The gates above cover these constraints without changing historical evidence.

Both masters reference this implementation order. The plan is not an
implemented or deployed release, a test pass, or authorization to extend
recovery. The run remains stopped. The prior false progress warning is a
separate reporting defect with an undeployed tested candidate; it did not
cause the terminal budget stop.
