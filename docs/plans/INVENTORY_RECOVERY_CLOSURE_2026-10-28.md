# Recovery closure execution plan — 28 October 2026

Master 4.11 / ensemble 201. Scope: prospective v3 changes only. Frozen
v2/history source and sealed production evidence remain unchanged. Production
is still 166 retained / 439 unfinished, with no new manuscript receipt.
Larger token or call budgets cannot close missing correctness gates.

## Dependency-ordered closure gates

| Gate | Implementation and executable acceptance | State |
| --- | --- | --- |
| TX3 | Derive installed predecessor chain, stops/contracts and locks from installed authority, not caller assertions. Reject rehashed omissions, older valid supervisors, root aliases, changed admission/config/source and live predecessor owners. Bind deployment command/environment/human approval/account/grant; prove cold-child inherited lock coverage. | Next; not closed |
| TX4 / CP3 | Both public entrypoints reconcile pending restart, campaign head, receipt and cursor transactions under common ownership before dispatch. Test real death before/after each publication, repeated reopen, corrupt/missing evidence, concurrent status and late stop. | Depends on TX3 |
| TX5 | Serialize readiness through grant hold and claim; retire/reprepare stale unspent plans in a new immutable transaction without changing spent plans or renewing allowance. Test sibling reserve/settle growth, held reservations, crash and veto boundaries. | Safety slices pass; integration open |
| TX6 | Only verified committed manuscript receipt membership advances business progress. Identical rewrites, mtime, diagnostics, heartbeat and pending successors do not; final-generation completion does. | Open |
| TX7 | Measure ancestry/settlement/prefix verification costs by depth and size; enforce an explicit bound. Operation-local reuse binds exact source/account-prefix/file membership; changes or loss invalidate it. | Open |
| Native integration | Genuine qualified fallback and two native successors through public entrypoints, conserving tokens/calls/restart charges and inherited stops. Synthetic cursor advancement is insufficient. | Depends on TX3–TX7 |
| Combined soak | Thousands of requests, more than 16 incidents, shared siblings; combine timeout, oversize, fallback, outage, storage failure and crash. Assert once-only settlement and bounded automatic recovery. | Depends on native integration |
| Release | Freeze source/tests; exact-membership full validation with 16 workers, actual production-data no-call preflight, one bounded independent review. Source changes invalidate release evidence. | Not admitted |
| Live continuation | Group prospective deployment/limit approvals; launch after release gates and verify a new manuscript receipt. Inventory → writing/review/reproduction → final actual ZLB human acceptance. | Blocked on release |

## Plan review

Execution checkpoint: independent installed derivation and cold-child
predecessor exclusions are implemented; 524 focused tests pass with 16 workers
and unchanged source/authority. Full TX3 public admission integration remains
open. See the installed-execution report for exact evidence and limitations.

- Bootstrap replay validates a candidate, not installed authority; TX3 must
  precede launch and public restart integration.
- Hashes cannot establish completeness: derive authority roots independently,
  then compare exact membership and identities.
- Safe refusal is not automatic repair: TX5 requires successful stale-unspent
  retirement/repreparation, not only rejection tests.
- Crashes must preserve budget and stop authority, never rebuild old intent
  to obtain fresh allowance. Historical component receipts are not release.
- Do not repeatedly run expensive actual preflight while source still changes.

## Execution, refresh and commit protocol

1. Implement one dependency-complete slice locally. Use one findings-only
   inspector at a time; coordinator owns source/master edits.
2. Freeze source/tests during validation; run focused tests with 16 workers,
   bounded review, repair findings and rerun affected tests.
3. At every phase boundary or stop refresh all four master/checkpoint headers,
   evidence, active processes, remaining blockers and next executable action.
   Running tests are not passing receipts.
4. Commit an explicit repair checkpoint as requested; never add the whole dirty
   tree, unrelated manuscripts/sessions, credentials or bulk audit output.
   Record dependency limitations honestly. Do not push.
5. Continue the next safe offline gate without intermediate human judgments.
   Privileged deployment or expanded spend still needs grouped host approval.
