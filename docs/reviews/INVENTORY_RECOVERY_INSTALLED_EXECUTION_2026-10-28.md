# Installed-authority repair execution — 28 October 2026

Scope: prospective v3 repair checkpoint, not live deployment or ZLB acceptance.

## Implemented and exercised

- Replaced self-referential stop validation with independently observed fixed
  installed historical admission/config/adoption, canonical campaign stops,
  active-stage and qualification locks, preflight authorization, installed
  unit bytes, source and account/grant/stages evidence.
- Reject rehashed stop omissions/replacements, altered contracts, old valid
  supervisor roots, missing/nonobject/symlink evidence and path aliases.
- Keep predecessor monitor/job exclusions exclusively held across transfer.
  Cold children must inherit the complete exact descriptor set; foreign,
  duplicate, omitted, unheld or wrong-identity descriptors are rejected.
  Duplicated child handles do not release the parent's ownership.
- Recheck installed binding, stops, environment/human approval policy and
  predecessor ownership before using a transfer lease.

## Validation

Source-bound focused run: **524 passed**, no failures/errors/skips, 16 workers,
14.25 seconds wall time. Source and production account/grant/stages hashes
unchanged. Ruff passes the five changed/new Python targets.

Receipt directory:
`docs/audits/2026-10-05/master-program/automatic-execution/sol-inventory-failure-first-20261026-01/recovery-policy-repair-20261027-01/installed-authority-validation/f214ebd30caa/`.
The receipt binds selected tests, source hashes, authority hashes and test
XML/log hashes. This is not the full exact-membership release validator.

The actual read-only installed-authority capture also passed: 11 evidence
files, five shared locks and the original canonical campaign stop root. No
model call, service operation or production authority write occurred.
The actual two-predecessor proposal and validation also passed read-only:
restart ceiling 16, cumulative transfers/restarts charged 2, remaining 14.
This proposal is only a no-write probe, not a stored deployment authorization.

An earlier broad run had four test-only failures after a redundant type check
was removed: the shared JSON reader already rejects nonobjects with ValueError.
The expectation was corrected without weakening production validation; the
520-case rerun passed. Subsequent hardening parses exactly the bytes hashed
(rather than reading twice), and rejects dangling stop/resume symlinks. The
522-case run validated these changes. Independent review then found POSIX
double-leading-slash aliases could bypass repeated-root checks. The canonical
path now requires the single-slash anchor, with direct and self-handover
regressions. The 524-case final run validates this repair; earlier receipts
are historical.
Independent follow-up closes that sole reported finding in this bounded slice.
The inspector is closed; no test or live process remains active at checkpoint.

## Remaining boundaries

Post-commit execution of the native bootstrap/public-preflight suite passed
**360 cases**, zero failures/errors/skips, 16 workers, 116.24 seconds wall
(pytest 115.63 seconds). Source and production authority remained unchanged.
Receipt:
`docs/audits/2026-10-05/master-program/automatic-execution/sol-inventory-failure-first-20261026-01/recovery-policy-repair-20261027-01/bootstrap-validation/fc35f50d2e4a/`.
These cases overlap the earlier suite and are not 884 distinct regressions.
Both runs have finished. No inference or production launch was attempted.
The installed historical state still has job=null and its sealed budget
exhaustion blocker; the frozen legacy category is not rewritten.

TX3 is not entirely closed: prospective deployment admission still needs full
release/service readiness and canonical execution/journal authority binding.
The fixed historical adapter is intentionally not a generic registry of future
v3-installed supervisors. Transfer captures current account/cursor bytes; live
execution must separately validate lawful account extensions instead of
reusing that immutable transfer snapshot as ongoing spending authority.
Cold predecessor descriptor tests are not both public execution entrypoints.
TX4/CP3, TX5 automatic reprepare, TX6 receipt-only progress, TX7 measured replay
bounds, native two-successor/fallback, combined soak and final release remain
open in the closure plan. Production remains 166 retained / 439 unfinished.

## Commit scope

The requested commit is a repair checkpoint: prospective v3 Python package,
v3 tests, its preparation/review/validation commands and master/review documents.
The large preexisting workspace also has uncommitted historical/runtime
dependencies (227 untracked static dependencies outside that scope observed).
This checkpoint is not represented as a standalone reproducible release.
Unrelated manuscript, session, schema and runtime edits are not staged; no
credentials, bulk audit artifacts or interpreter caches belong in the commit.
No push is requested. The release gate must reconcile dependency membership
before deployment.

Repair checkpoint committed: `2d54195` (95 explicitly scoped files, including
previously untracked v3 work). This subsequent document refresh records the
post-commit native validation. Unrelated workspace changes remain untouched.
