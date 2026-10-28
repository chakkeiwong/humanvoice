# Provider integration execution checkpoint — 28 October 2026

Historical recovery checkpoint at 06:48 UTC: the existing native executor gate survived
session recovery. Runner 665469/session 26230 is executing its exact 12-case
membership with 16 workers and an 1800-second bound. Evidence directory:
`validation/f60d0cf801c2378fdf82/executor-c097121b93b6` beneath the retained
recovery-policy-repair-20261027-01 audit directory. No pass is claimed yet.
Its source/test freeze is now ended as recorded below.

At 06:53 UTC the coordinator intentionally interrupted this gate after eleven
completed cases to repair provider-review P1. Its terminal receipt is fail /
KeyboardInterrupt, with source_unchanged=true and authority_unchanged=true.
The fixed runner completed group cleanup and exited before any source edit.
This interrupted receipt cannot establish executor acceptance.

P1 reproduces a real child running after Popen's parent-side constructor raises
OSError. The previous exception-class check falsely returned ZeroLaunch. The
repair retains the Popen object before initialization, cleans its group and
individual unreaped PID, and preserves started/unknown evidence after any
spawn attempt. Only a guard/setup veto before spawn may certify zero launch.
Six real post-fork regressions cover two constructor boundaries and three
exception types, plus missing executable, absent PID, and native no-resend
accounting checks. The bounded reviewer has concluded and exited; residual
repair validation/review remains required.

Post-fork integration result: 172 cases pass in 79.13 seconds with 16 workers;
`.localresources/provider-postfork-integration-20261028.xml`. Ruff passes.
The first 35-case run had 34 passes and one observation-hook failure because
the existing spy still patched subprocess.Popen instead of OwnedPopen. That
test hook was corrected and the 172-case result includes the corrected check.
Halley's bounded residual-only recheck closes P1: twelve selected tests pass
in 26.41 seconds with 16 workers, plus five extra early-constructor/PID/exception
probes. Source/tests remained unchanged and all review-owned processes exited.
The inspector is closed. Exact review evidence is appended to the assigned
provider review report.

The repaired source-bound native gate passes all twelve exact-member cases in
805.56 test seconds / 808 runner seconds with sixteen workers at
`validation/a0aaa78de204019bfc3e/executor-c9e49e928a12`, session 36094, runner
712051. Its receipt records `release_acceptance=false`; source and production
authority are unchanged. The source freeze ended after completion. This closes
the executor gate only, not public admission or release.

Prospective provider_capture.py, provider_runtime.py and rejection.py now bind
the complete inherited descriptor union to the final native spawn boundary.
They preserve private native settings/request checks, use a typed zero-launch
result, retain post-spawn uncertainty, and publish replayable rejection intent
before terminal evidence. Existing partial evidence never licenses a resend.

Combined fixture validation passes 164 cases in 76.86 seconds with 16 workers:
provider capture/runtime, execution, resume, native ownership and runtime.
Receipt: `.localresources/provider-integration-20261028.xml`. Ruff passes.
Halley's initial bounded findings-only review found P1; its report is
INVENTORY_RECOVERY_PROVIDER_REVIEW_2026-10-28.md. These are component results,
not full public admission or release acceptance.

The permission wrapper reconfirms on-request/user/workspace-write; production
services are inactive/disabled. Production remains 166 retained / 439 unfinished.
No paid call, production authority write, deployment, commit or push occurred.

Remaining critical path: implement authenticated
monotonic stop/control publication and public runtime factory; close TX4–TX7
and combined recovery/long-document tests; freeze complete dependency binding
and run full release plus actual-data no-call preflight. Only then request the
concrete grouped host deployment/limit/launch actions. A new verified manuscript
receipt is required before reporting production resumed.
