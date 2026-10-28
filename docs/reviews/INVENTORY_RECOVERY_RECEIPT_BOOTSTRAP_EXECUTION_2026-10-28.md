# Historical receipt bootstrap repair — 28 October 2026

Master 4.13 / ensemble 203. No live deployment or manuscript inference.

## Actual failure and root cause

Recovered the existing preparation process rather than launching a duplicate.
It finished nonpass after 1063.83 seconds at
`preparation/3bdfb5ca168022e995c1/preparation.json` under the recovery repair
evidence root. Source and production account/grant/stages remained unchanged;
model calls, account writes and grant writes were zero.

`campaign_initialization.initialize()` constructed `NativeRequests` inside
accounting/semantic history scope, but outside the original-receipt replay and
nonlive runtime context. Its inherited size policy calls the native receipt
validator. The copied receipt belongs to an earlier destination and permissions;
validating it using the successor snapshot rejected its inference destination.
The normal Stage replay already knew how to verify the original snapshot,
profile, exact copied bytes and retained membership. Bootstrap failed to use it.
This is a composition bug, not a provider timeout or a request for wider rights.

## Repair and regression coverage

Extracted the existing Stage replay body into `stage.receipt_replay()` without
changing its checks; Stage delegates to it. Bootstrap enters this helper plus
`runtime.runtime(..., historical_validate=checked)` with live disabled while
constructing and importing native request ownership. Source and permission
validation are not bypassed; production rights/evidence were not modified.

Seven native regression cases create a real synthetic oversized receipt under
its original endpoint, copy the snapshot, and install successor-only endpoint
rights. The unscoped path reproduces the permission failure. The corrected
scope accepts exact original evidence and rejects altered copied receipt,
altered payload, missing original, unlisted receipt, foreign profile and changed
split recipe. Two bootstrap boundary cases enforce context nesting, nonlive
mode, unwind and rejection before seed publication.

An attempted broad mixed-history fixture initially failed in its own synthetic
parent setup, before exercising the repaired bootstrap. That fixture expansion
was removed; no production guard was weakened. The narrower native receipt
regression and existing native public-preflight integration cover the repair
independently. This does not claim a complete mixed-route live campaign test.

## Validation

- Nine new targeted cases pass in 5.25 seconds, 16 workers.
- Exact-member focused integration: **648 passed**, no failures/errors/skips,
  16 workers, 257.89 seconds pytest / 259.37 seconds harness. Source, harness and
  production authority unchanged. Receipt:
  `campaign-binding-validation/70edb5e90e97/validation.json`.
- Ruff passes all affected source/tests/scripts; scoped diff whitespace passes.
- The former complete 1,167-case validation is historical after source edits.
- Bounded independent repair review reports no concrete findings; inspector
  closed. The targeted actual-data receipt diagnostic passes in 53.09 seconds.
  Neither supplies live admission. No full preparation rerun while the public
  implementation remains unfinished.

The first read-only diagnostic omitted the historical instrumentation context
and failed a native request/permission/session/usage comparison before its
scoped leg. A second harness lacked a multiprocessing main guard and failed
before completing. Both changed no snapshot or authority. The corrected
guarded diagnostic uses the production historical context, reproduces the
unscoped destination failure, then validates the one inherited size rule
successfully in the original-receipt scope. Source, original/copied snapshot
membership and production authority remain unchanged. Model calls and
account/grant writes are zero. Receipt:
`receipt-bootstrap-diagnostic/a76a7c8e55da/diagnostic.json`. This is a targeted
historical diagnostic, not a complete preparation or release test.

## Plan review and remaining gates

TX3b design review records PC1–PC6: acyclic source identity, exact consumer
schema, immutable versus mutable runtime separation, complete descriptor
inheritance, external host-approval trust root, and prospective plus inherited
stop authority. The public-admission plan includes concrete remedies/tests.
These are implementation gates, not closed by documentation.

Continue with canonical public configuration/admission, monotonic runtime
floors/ownership, public cold reconciliation, stale-unspent reprepare,
receipt-only progress, bounded ancestry replay, native multi-successor/fallback
and long-document soak, full source-bound release, grouped host authorization,
then actual inventory and downstream ZLB/held-out benchmarks/reproductions.
Production remains **166 retained / 439 unfinished**. No new manuscript
receipt, finished ZLB, approval-policy change, budget increase or commit claimed.
