# ZLB recovery after gateway worker cleanup failed

## Observed incident

The durable user service survived the editor reload and completed admission.
Five paid HTTPS requests started at approximately November 14, 04:43 Shanghai.
One response completed in 191 seconds (55,227 input and 7,760 output tokens).
The scheduler then called recover_workers for that normally exited worker.
Its stale profile comparison rejected the admitted HTTPS capture against the
original HTTP plan. The scheduler's exception cleanup cancelled four other
requests after about 190–199 seconds. They have empty response envelopes, no
reported token usage and quiescent process groups.

This is a local recovery bug, not evidence of a gateway timeout. The original
140 allocations, 110 bank entries, the additional completed response, and the
four interrupted captures are retained. Thirty-seven of the original 177 slots
remain. Recovery must not erase the four unknown charges.

## Repair and review

Extend the existing admitted gateway/session/durable-settings verifier to the
worker ownership check. Select the actually transmitted profile from the exact
admitted request and all three transition markers. Check the original source,
implementation, prompt, purpose, binding and command evidence. Leave the native
worker identity, PID/start time, process-group, private session and inherited
descriptor checks in place. Launch-time evidence is sufficient even before
record.json exists; receipt validation still happens separately.

Repair the four identified interrupted tasks inside the existing wave-003
SQLite batch. Append one idempotent repair event and return only those tasks
to pending. Keep all original attempt rows, negative/successful answers,
charges, manifest, deadlines, retry counters and canaries unchanged. The normal
three-attempt-per-task cap and shared 177-call pool still apply. Do not relabel
a failed allocation as successful or release its unknown charge.

A narrow dispatch adapter may skip the original blocked result only for one
of those four exact, verified local interruptions, only in the same batch and
only after the repair event. Further unrelated local failures remain blocked.
Successful or negative answers are always reused. The next provider attempt
gets its own paid allocation and receipt.

The repair is additive: old admission, reviewed sources and paid evidence remain
intact. The existing ordinary-user service is replaced after checks pass.
No sudo, permission-policy change, client upgrade or budget replenishment is
required. Settings are checked again by the actual user-service preflight.

## Verification

The primary regression runs a real fixture worker to completion, reproduces the
old failure when its scheduler reclaims it, and verifies corrected recovery.
It exercises missing final record, edited gateway/session/durable markers,
changed request/source/command and living-owner rejection.

A second regression interrupts an actual fixture capture, verifies its retained
failure, reopens the same scheduler task, then executes and validates a new
native response. It checks unchanged first-attempt bytes and charges, increasing
attempt counters, idempotent restart and no duplicate successful request.
Additional cases reject known/negative/partial responses, invalid evidence,
live processes, changed charges, exhausted retries and terminal network circuits.

The production offline replay checks all five new captures, the exact completed
response, original accounting and pending batch without model calls or writes
to accounting/batch/response-bank state. Existing unchanged tests/baseline
evidence are retained, rather than repeating the full historical replay just
for this local repair.

## Execution and remaining work

Run the tested transition, refresh both masters, commit only this repair and
its evidence, install the ordinary-user successor and resume the existing batch.
Verify actual provider progress separately from local admission. Preserve
16 workers, 900-second provider limits, 1050-second scheduler limits,
15-minute network retry and the November 20, 17:03:49 Shanghai execution window.

After unit repairs and automatic independent reviews, the program still needs
assembled relationships/build/release, benchmark/regression, separately budgeted
reproduction and final human review. Automatic repair after assembled semantic
rejection remains the explicit gap in ZLB_SESSION_BINDING_REPAIR_2026-11-13.md.
This operational repair does not claim final ZLB acceptance.

## Verified readiness

All 16 regressions PASS in 29.31 seconds. The actual five-capture offline audit
PASS in 25.92 seconds, with zero model calls and zero accounting writes.
It retains 110 earlier bank entries and verifies the additional completed
response and four empty interrupted captures. The source-bound execution
review is READY. The grouped deployment commits only the repair/evidence and
two masters, checks actual user-service settings, then replaces the failed
user service and resumes the existing batch. No administrator authentication
or additional execution-window authorization is required.
