# Inventory recovery execution checkpoint — 27 October 2026

Current execution checkpoint, 28 October 2026: master 4.32 / ensemble 222.
Crash recovery confirmed no surviving validation process and production
inactive/disabled. Human approval remains on-request/user/workspace-write.
The previous floors gate failed 889/890 at the native public preflight; its
receipt is retained, with source/authority unchanged and no release acceptance.
A minimal diagnostic proves two incompatible fixture cursors: installed locks
used the caller's exhausted stage, while the installed cursor named the synthetic
old-campaign/generation-02. The fixture now binds its cursor before deriving
shared locks and binds program.BASE before fixture capture. A fast regression
asserts the complete cursor/program-lock membership. Production checks are
unchanged. All 120 focused configuration/runtime-closure/native-preflight cases
pass in 141.69 seconds with 16 workers; Ruff passes. Fixed floors validation
PASSES all 891 exact-member cases in 779.27 test seconds at
validation/bf6525157a631b6918e6/floors-3ca2d2557dfe, unchanged source/authority.
Executor validation PASSES all 12 exact-member cases in 850.78 test seconds
at executor-f4135811ea2e under the same source binding. Both receipts verify
unchanged source/production authority and release_acceptance=false. Sixteen
workers and original deadlines were retained; both validation processes ended.
The core source/test freeze ended after both gates and final hash verification.
An isolated offline witness/publication candidate is retained under
.localresources/control-witness-20261028; it is not in public runtime or release
admission. The frozen candidate gate passes 156 exact cases with 16 workers
in 2.702 test seconds. Separate collection and execution membership match,
Ruff passes, and before/after hashes match across 921 source/test/config files
and the three production account/grant authorities. The earlier 56-case
approval-policy regression also passes. Receipt: candidate validation/
projection-f752e96e5f7f/validation.json; release_acceptance=false.
Protected projection checks now reject writable ancestors, symlinks, hardlinks
and foreign-owned leaves. Review found and fixed an initialization defect:
child-file checks attempted to traverse the not-yet-created local root. Three
partial-initialization regressions cover absent root, root only and events
directory. Fixture protection adapters remain explicit, not host isolation proof.
The installer must still resolve workspace-path protection and read access for
the native runtime without changing inherited contracts or taking ownership
of the whole workspace. Human-request provenance, protected database bootstrap,
socket lifecycle, supervisor diagnostics and public factory remain open.
Next: implement/test the fixed protected host package and its native projection
access contract, then public factory/monitor, TX4–TX7, native multi-successor/
soak and dependency-complete release before live deployment.
The temporary control-store prototype is not a trusted host witness.
Production remains 166 retained / 439 unfinished, with no new ZLB receipt.
Repair/retest/review/refresh is mandatory at each phase and interruption.
Evidence: docs/reviews/INVENTORY_RECOVERY_CRASH_LOCK_REPAIR_2026-10-28.md.

Continuation completed locally: checkpoint commits 9120868 and ad17adc
retain the recovered core and publication candidate. The subsequent projection
protection/initialization repair and reproducible offline validation are included
in this checkpoint. Preserve unrelated files and frozen receipts.
No validation remains active. Production is inactive/disabled; no model call,
deployment, push or new ZLB receipt occurred. Review here is coordinator-only.
Next safe work and required executable checks are in the control-publication
plan; no fixture or source hash substitutes for the host authorization gate.


Previous checkpoint (historical; running/closure claims below are superseded):
Current execution checkpoint, 28 October 2026: master 4.28 / ensemble 218.
Recovered source and retained evidence remain available on SSD. CF1-R/CF3-R
are independently closed. The exact-member floors suite completed: 850 pass
in 1033.08 seconds with 16 workers and unchanged source/production authority.
Its receipt is historical after the subsequent validation-runner repair.
Bounded review identified VR1–VR3: final checks could leave a false pass,
ordinary leader exits could leave workers, and cleanup could wait indefinitely.
Repairs now force terminal failure on final mismatch/read error, clean owned
groups on all exit paths, and bound reap attempts while retaining original
failure and incomplete-cleanup evidence. Residual VR2-R is also repaired:
process-observation errors cannot suppress termination attempts. Fifteen runner
regressions pass in 10.59 seconds; Ruff and 56 permission-wrapper tests pass.
The independent residual review closes VR1–VR3/VR2-R; inspector is closed.
Frozen-source exact floors validation passes all 861 cases in 1037.27 seconds,
16 workers, unchanged source/authority: validation/5710efeb418e12455bfe/floors-ea2e56291fcf.
Native executor validation at executor-9323948631d4 failed its 1800-second
bound: 11 cases passed; oversized split execution reached pass and seal but
its final repeatability/accounting checks did not complete. The failure receipt
retains unchanged source/authority; cleanup completed and the test process ended.
This is not a passing executor gate. The completed 90-second offline profile
attributes 56.94 seconds to 261 schema-definition checks. Prospective operation-
scoped reuse now checks exact schema bytes and checker construction identity;
schema construction/contracts and every record/receipt check still run. Frozen
historical files remain unchanged. Initial integration validation passed 104
cases. Review then reproduced R1–R4: list/tuple key ambiguity, type-checker
drift, effective registry/resource drift, and independent-context restoration.
The executor rerun was intentionally interrupted after 6 passes in 305.25s;
its failed receipt retains unchanged source/authority and completed cleanup.
Repairs now restrict reusable keys to JSON-native trees, snapshot effective
meta-validation resources/type semantics, and reject overlapping independent
scope installation. Follow-up found one legacy resolver-default residual;
both legacy and keyword custom resolvers now always use native checking.
The intermediate ff905888ca5f run was interrupted before this source change
and is retained as failed, with unchanged source/authority and clean shutdown.
All 115 affected integration cases (35 dedicated) pass in 14.15 seconds; Ruff
passes. Independent residual review closes R1–R4 and the inspector is closed.
The final fixed executor gate PASSES all 12 exact-member cases in 902.11 test
seconds (904.13 runner seconds), including oversized split and final repeat/
accounting assertions: validation/408012e9b655b2e389b1/executor-0a3e19afec9f.
Source and production authority are unchanged. The original 1800-second limit
remains. Same-source floors validation PASSES all 861 exact cases in 732.963
test seconds at floors-5dd639f5fc1e, with unchanged source/production authority.
Both receipts are historical after the following descriptor implementation;
the source freeze ended only after both suites completed.
Repair contract and evidence:
docs/plans/INVENTORY_RECOVERY_SCHEMA_REPLAY_2026-10-28.md.
Ownership design review closes OD1–OD6 and residual OD2-R/OD6-R at design level;
its inspector is closed. Nonmutating descriptor proof and private legacy job
adapters pass 430 adjacent cases after repairing DR1's false-pass test oracle;
independent recheck closes OD2/OD2-R within its scope. Canonical role/lease
components pass 173 combined cases with 16 workers. Review LR1/LR2 found stale
transfer cleanup closing reused descriptors and early rejection not retiring
its capsule; both are repaired and independently closed. Complete-lease launch
integration passes 187 combined cases in 7.49 seconds; Ruff passes. Review
LU1–LU3 is closed: reporting failures preserve unresolved children, fallback
rejects ambient capsules before dispatch, and malformed transfers retire safely.
Independent verification passes 24 cases in 26.18 seconds with unchanged hashes.
Launcher inspection is closed. The next immutable-runtime component is
implemented: transfer-bound predecessor/qualification/source closure and
acyclic leaf → lease → read-only floors. Configuration binds this closure.
Review found RC1 (stop rollback) and RC2 (added source files); repairs require
authenticated monotonic stop evidence and exact source inventory. RC1-R's
newline-normalization defect is also repaired. All RC findings are independently
closed; 277 combined cases pass in 12.55 seconds and Ruff passes. Inspector
closed. Complete native callback/provider-lease integration passes 273 adjacent
cases in 64.55 seconds with 16 workers. Review P2 exposed stage-ownership loss
during existing claim-tail publication; shared stage ownership and twelve
regression cases repair it. Independent recheck passes all twelve in 92.46
seconds and closes P2; the inspector is closed. Provider collector/runtime/
rejection integration is now implemented: full inherited descriptors at final
spawn, private native settings checks, bounded cleanup, typed zero-launch
outcomes, and durable exact rejection replay. Combined provider/ownership/
execution validation initially passed 164 cases. Provider review P1 reproduced
a false zero-launch proof after a real post-fork constructor failure. The old
native gate executor-c097121b93b6 was intentionally interrupted after eleven
cases; its failed receipt retains unchanged source/authority and completed
cleanup. Repair now retains the Popen object before initialization, kills and
reaps observed children, and records uncertainty when no PID is available.
Only pre-spawn failures can certify zero launch. Combined repair validation
passes 172 cases in 79.13 seconds with 16 workers; Ruff passes. Independent
residual P1 review closes with 12 selected passes in 26.41 seconds and five
additional child-cleanup probes; source/tests unchanged. The repaired executor
gate passes all twelve exact-member cases in 805.56 test seconds / 808 runner
seconds at validation/a0aaa78de204019bfc3e/executor-c9e49e928a12. Source and
production authority are unchanged; executor phase is closed.
Real authenticated control publication and public factory integration remain
required. Control transaction/check matrix:
INVENTORY_RECOVERY_CONTROL_PUBLICATION_2026-10-28.md. Execution evidence:
INVENTORY_RECOVERY_PROVIDER_EXECUTION_2026-10-28.md.
Full public admission, TX4–TX7 and dependency-complete release remain open.
Production remains 166 retained / 439 unfinished, with no new ZLB receipt.
Tracked production services are inactive/disabled; human approval settings
remain on-request/user/workspace-write. No paid call or deployment occurred.

Previous pre-crash checkpoint (superseded running/review status):
Historical-receipt bootstrap repair passes the actual-data diagnostic in
53.09 seconds: the unscoped path reproduces the destination failure, while
original-snapshot/profile replay accepts the exact retained size rule.
Source, both snapshots and production authority remain unchanged; zero calls
or account/grant writes. Independent bounded review reports no findings.
The repaired slice passed 648 exact-member tests with 16 workers. That receipt
and the earlier 1,167-case full pass are historical after new source changes.
TX3b now has a read-only canonical configuration candidate and isolated public
inspection CLI. It derives source-bound preparation, native campaign binding,
account/grant/journal, cumulative handover limits, both stop roots, fixed
commands and retained profile. All live actions still fail closed before
inspection or spending. Final configuration-slice validation: 738 exact-member
tests pass in 211.63 seconds with 16 workers; source, harness and production
authority unchanged. Bounded review closes C1/C2 and exact-type residual C1-R.
Evidence: `campaign-binding-validation/ce9e31a2e13c`. This is a focused slice,
not full release authorization. Native runtime floors are implemented at stage
hold, claim and all three settlement paths. Nine native executor fault routes
passed in 869.00 seconds before follow-up fixes. Bounded review found CF1–CF5:
dispatch floor checks, racing status reads, cold claim-tail ordering, sibling
growth after pending writes, and missing pending transition evidence. First
repairs pass 151 focused regressions; three actual cold-executor cut tests
remain running on frozen source. Follow-up closes CF2/CF4/CF5 but retains
CF1-R (cold checks lack explicit mixed-history replay) and CF3-R (unlocked
whole-account equality falsely rejects a lawful sibling append). Repair these
with a leaf read-only native validator and a native-write veto for existing-
only claim repair, then add cold and interleaving regressions. The workers are
CPU-active, not proven deadlocked. No current-source full release is claimed.
Runtime evidence: `docs/reviews/INVENTORY_RECOVERY_CONSUMPTION_FLOORS_EXECUTION_2026-10-28.md`.
Remaining: admitted runtime floors/descriptor composition, public cold recovery,
automatic stale-plan repair, receipt-only progress, bounded replay, native
multi-successor/soak and full release before host-approved live deployment.
No live ZLB resumption or new manuscript receipt: 166 retained / 439 open.
Plan: `docs/plans/INVENTORY_RECOVERY_CLOSURE_2026-10-28.md`. Evidence:
`docs/reviews/INVENTORY_RECOVERY_PUBLIC_CONFIGURATION_EXECUTION_2026-10-28.md`.

Previous checkpoint evidence (not current-source release authorization):
The installed-authority/ownership/bootstrap slice passes 524 focused tests with
16 workers; source and production authority are unchanged. Actual read-only
installed-authority capture passes. This does not close full TX3 or resume ZLB.
Closure order, corner cases, test requirements and phase/stop refresh rules:
`docs/plans/INVENTORY_RECOVERY_CLOSURE_2026-10-28.md`. Evidence and boundaries:
`docs/reviews/INVENTORY_RECOVERY_INSTALLED_EXECUTION_2026-10-28.md`.
Independent review's path-alias finding is repaired and closed in follow-up.
Repair source is committed as 2d54195. Continued native bootstrap/public-
preflight validation passes 360 cases in 116.24 seconds (16 workers), with
unchanged source and authority. Both suites finished; inspector closed.
Next: bind prospective public admission/configuration/journal authority, then
TX4/CP3 common-ownership restart/campaign reconciliation. Live ZLB remains
unresumed at 166 retained / 439 unfinished; this is not release completion.
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

## Historical work — master 3.99 / ensemble 189

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
Continuation review CD1/CD2/CD2-F1 is closed at the inspected code boundaries:
canonical qualification persistence, bounded recursive preparation/source checks,
and sealed full-probe report binding. Qualification mutation boundary:6 passes;
recursive native/cold-probe set:9 passes before the final transcript patch.
The current full suite, actual preflight, transactional campaign integration,
canonical supervisor admission and combined long-document soak remain release
gates. These component closures do not authorize production deployment.
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

## Historical work — master 3.88 / ensemble 178

RR1-F1 independent follow-up closes the control-history defect. The durable
head records committed membership plus pending transition intent. Focused
resume suite: 69 passed, 16 workers, including A/B/C, lost intermediate/latest
records, missing/foreign/malformed heads, two roots with identical original
stop bytes, independent successors and all actual publication process cuts.

Exact full suite before these last additions: 409 passed,16 workers, no skips,
unchanged source/authority at
`validation/37e969211fd645b878c1/5c19eae51a23`. Its test import was subsequently
formatted; more tests and successor code followed. This is historical evidence.
Earlier migration audit `migration/9546e122c8c0582fd27f` passed for30 sources,
zero calls/writes,166/439 and unchanged authority; later edits invalidate it
as current-source admission. Do not rerun migration while editing candidate code.

New `successor.py` builds the prospective budget transition/plan directly from
independent replay, preserves17 charges and retained profile/qualification.
`migration.py`/`source_gate.py` retain immutable account event/plan anchors and
permit legitimate suffix growth; native successor claim/reinspection regression
passes. Three focused native tests pass. Bounded successor review is running.
Next: actual Stage preparation/probe, source lineage, canonical admission,
executor/campaign and crash/combined-soak gates. No provider/account/grant/service
production mutation, deployment, commit or push. Production remains166/439.

## Historical work — master 3.87 / ensemble 177

RT1/RT2 from `INVENTORY_RECOVERY_RUNTIME_REVIEW_2026-10-27.md` are repaired in
the candidate and awaiting bounded follow-up. RT2 recognizes the unchanged
native prefix with no allocation, keeps its dispatch intent and routes the
normal attempt through current stop/authority/earmark/canary validation.
RT1 records the exact allocated/runtime/stop identity without provider launch,
requires exact source-bound resume, atomically cancels/retires the old pair,
retains charges and uses a new bounded sequence. Exhausted allowance reports
BLOCKED_BUDGET. Arbitrary missing runtime association is never cancellation.

Focused RT1/RT2 suite: 97 passed, 16 workers. The full exact-source validator
passed 385 cases at `validation/9c292cd82ca1a0734f55/020c946ba9b7`; no skips,
source or authority mutation. Ruff passes. Independent report
`INVENTORY_RECOVERY_RESUME_REVIEW_2026-10-27.md` found RR1: later valid stop B
conflicts with retired stop A. Durable source/stop-bound authorization
history and repeated-stop regressions are now added. A new full suite and
bounded independent RR1 review are required before this checkpoint is current.
New files include `cancellation.py` and `test_inventory_recovery_v3_resume.py`.
Both masters and the repair plan list remaining integration phases and
restart/authority/semantic/split/soak gates.
No production inference, authority mutation, service change, commit or push.

## Historical work — master 3.86 / ensemble 176

Twenty owner regressions pass with 16 workers. SO1/SO2 follow-up closes the
helper defects conditional on independently admitted configuration. Actual
production factory and policy/runtime/campaign integration remain unfinished.
The last full 312-case receipt is historical; freeze and revalidate after
current changes. No production inference or authority/service mutation.

## Current checkpoint — master 3.85 / ensemble 175

Exact current-source offline suite: 312 passed, 16 workers, unchanged sources
and authority, no missing/skipped cases. Receipt:
`validation/4c89a42fef4326e69892/9f13e4cf6ef3/validation.json`. Ruff passes.
The prior 298/302/303/305/310-case runs are historical snapshots only.

New prospective units: `launch_handoff.py`, `launcher.py`, `native_settlement.py`
and `stage_owner.py`, plus repaired `supervision.py` and `allocation.py`.
Inherited lock handoff covers unpublished/never-spawned workers, wrong/fresh/
foreign descriptors, same-monitor recovery and stop-after-ack with exact resume.
Native finish precedes pair settlement; four hard-exit cuts cover both roles.
NS1 review found valid foreign-prompt runtime substitution; exact runtime
request/profile/source/implementation/deadline joins now reject it, and genuine
foreign-receipt regressions prove unchanged journal/account/grant/native ledger.
NS1 and LH1 follow-ups close specific defects, not whole release. Earmark
review is complete under the actual-owner prerequisite; owner review pending.

Migration audit `migration/87827503d4e4b00418be` failed source-stability checks
because new candidate edits occurred while it ran. Authority stayed unchanged;
zero provider calls/account writes. Keep that failure and rerun after freezing.
No production activity: 166 retained responses, 439 unfinished requests.
Follow the current repair plan's remaining integration/admission/crash gates.

## Latest verified boundary — master 3.84 / ensemble 174

The fixed validator passes 285 cases with 16 workers, exact collected/executed
membership, no skips/errors, source unchanged and authority unchanged. Receipt:
`recovery-policy-repair-20261027-01/validation/bbcda114bbb8d3761ccb/0eef18912a42/validation.json`.
Ruff passes for the candidate sources and changed tests. Earlier snapshots:
`9b7b0e3420f51972670a/4ceae3377ef9` failed 1/260;
`f42bf00261ca755ab031/9eff9ad9ba28` failed 1/275;
`0d1ef7d922973c055e1e/728c271882da` passed 277 before the last eight tests.
Never use those older passes as a current-source release admission.

The initial cold-start race is reproduced deterministically. A new prospective
monitor removes fallthrough into a second liveness decision, preserves a child
holding the inherited job lock, rereads acknowledgements when a result appears,
and avoids acquiring the lock of a known live pre-ack launcher. Sequential
inspection found SV1/SV2; follow-up closes their specific unsafe behavior. A
cold unpublished worker remains observed as UNRESOLVED_LAUNCH_OWNERSHIP without
restart charge until it acknowledges. This is safety, not complete automatic
recovery: authenticated parent-owned pre-ack handoff remains required.

Native pair earmarks bind the source journal, exact account/grant holds and
ledger prefix; both calls must fit before the canary. Base retry ownership is
counted once, no extra account claim/refund is performed, and allocation checks
the earmark again. Hard exits after native journal binding or journal commit,
late owner veto and competing journal tests pass. Independent capacity review
is pending. Migration audit `migration/e2ad8621638c8d2a4a2f` passes for the
18-file candidate binding with unchanged sources and authority, zero model
calls/account writes, 166 retained responses and 439 unfinished requests.

Production remains sealed at 166 retained/439 unfinished. No paid provider call,
production account/grant write, service change, limit approval, commit or push.
Executor/campaign integration and full release gates remain as described in
the current repair plan. Historical results below retain their original scope.

## Verified work

The selected candidate and historical compatibility suite passed **254 tests
in 32.65 seconds**, using 16 workers. The membership plugin records exactly
254 collected and 254 unique executed node IDs, no missing/unexpected tests,
no deselection, no collection errors, and exit code zero. Raw JUnit and
membership records are currently `/tmp/humanvoice-v3-tests-20261027.xml` and
`/tmp/humanvoice-v3-membership-20261027.json`; these are a checkpoint, not a
release admission or a claim that later source edits retain this pass.

The selected files include all eleven then-existing v3 test modules, progress
watch tests, the native failure-first suite, and history live/current-stage/
integration suites. Two additional native seal/account settlement interruption
tests subsequently passed in 5.76 seconds. They are not included in the 254.
Ruff passed on the candidate sources and then-existing v3 test modules.

Independent native-boundary review found NB1–NB4; the focused follow-up closes
those specific component findings. Review reports are retained unchanged:
`INVENTORY_RECOVERY_NATIVE_BOUNDARY_REVIEW_2026-10-27.md` and
`INVENTORY_RECOVERY_NATIVE_BOUNDARY_FOLLOWUP_2026-10-27.md`.
The next sequential review covers allocation and stage capacity, not the full
release. A current-source read-only migration audit is in progress under
`recovery-policy-repair-20261027-01/migration/36e9c61b2665f28f2d5f`.

## Implemented candidate boundaries

- Typed cause survives invocation wrapping and is persisted before native
  seal; a durable user pause and late stop/owner veto cannot be overwritten.
- Claim intent preserves an exact prepared marker and repairs account/receipt/
  ledger interruption without a second reserve event. Both exception cuts and
  abrupt `os._exit` process deaths are tested; unknown outcomes remain charged.
- Retry dispatch checks freshness, supersession, native request/profile/source/
  scope, one-time consumption and stop/ownership. Sealed canaries cannot be
  implicitly relabeled into a new policy; cross-stage adoption stays disabled.
- Native pair allocation intent precedes actual native invocation. Fixtures
  match real canary/retry UUIDs and receipts, and reconcile a native reserve
  that committed before its pair mapping without retransmitting it.
- Source-bound lineage registry rejects changed ancestry and retired parents;
  32 independent split operations persist across restarts while root limits
  remain bounded and split expansion is charged only once.
- Dedicated budget migration gate accepts reconciled evidence while the old
  successor constructor continues to reject the budget stop.
- Candidate chained ownership preserves previous exclusions, pending restart
  charges and old-root stop authority; native stage capacity uses already-held
  slots even when global available authority is zero.

## Remaining release gates

The components are **not yet a deployed or complete native execution program**.
Connect the pair/hold reservation to the native launch path and new-policy
stage/campaign dispatcher; preserve historical settlement and qualification
readers; carry full inherited split/root state; enforce all semantic rule and
attempt-key ceilings; validate actual second supervisor handover/admission.
Complete transition/cursor/repair crash cuts, native no-result/unknown outcomes,
combined split/fallback/sibling/stop/crash workload and thousands-request soak.
Then freeze exact source/test membership, run final release review and
preflight, and request grouped concrete recovery-limit and host permission.

No production restart, paid provider call, account/grant modification, limit
increase, commit or push occurred. Generation-02 remains sealed; 166 responses
are retained and 439 logical requests remain. The legacy semantic status is
incorrect; the reconciled stop is budget exhaustion. Only final actual ZLB
output acceptance requires a human content judgment.
