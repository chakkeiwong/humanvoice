# Validation recovery: bounded findings-only review

Date: 2026-10-28. Role: sole findings-only inspector.

## Scope and evidence

Static inspection only of `tools/validate_inventory_recovery_v3.py`,
`tests/test_inventory_recovery_v3_validation.py`, and the partial-read/busy
fixtures at `tests/test_inventory_recovery_v3_floor_followup.py:152-226`
(plus that fixture file's imports). Read `/home/ubuntu/AGENTS.md` and the
project `AGENTS.md`. No imports, tests, subprocess demonstrations, gateway,
service, master, or production actions were performed. The only inspector
write is this report. Suggested regressions below were not executed.

CF1-R/CF3-R production closure in
`INVENTORY_RECOVERY_CONSUMPTION_FLOORS_REVIEW_2026-10-28.md:416` is accepted
as the supplied review boundary; those repairs and the broad audit are not
reopened. The coordinator reports 171 fast tests and four runner tests passing
after the crash, with a source-frozen exact floors suite running. These are
reported results, not inspector verification. Lost temporary evidence is not
treated as retained evidence, and no result is inferred for the running suite.

## Findings

### VR1 — P1: a failed final source/authority check can still publish pass

**Location:** `tools/validate_inventory_recovery_v3.py:161-179`.

The first source/authority comparisons at 163-164 guard construction of the
passing result. The second comparisons at 174-175 overwrite
`source_unchanged` and `authority_unchanged` without changing `status`. If a
source or retained authority changes after the first comparison but before
the second, the runner persists `status: pass` with an unchanged flag set to
false, prints pass, and returns zero. This is an explicitly detected mismatch
being accepted, independent of any undetectable change after the final read.

The same finalization is outside the exception handler. If its binding or
authority read instead raises, even a failure already caught at 171-173 is
not durably finalized; the previous receipt remains running. This latter
path does not itself produce pass, but loses the terminal failure evidence.

**Required correction:** make all final comparisons part of the protected
acceptance decision. Any false result must force a failing receipt and
nonzero exit; any final read error must preserve the failure and finalize a
failure receipt when the output remains writable. Do not leave a pass status
paired with failed source/authority predicates.

**Focused regression:** exercise `run()` with temporary artifacts and bounded
stubbed subprocess calls: make the first checks match and only the final
source check, then only the final authority check, differ. Require persisted
fail and nonzero return. Also inject a final read error after an earlier
command failure. The current test at
`tests/test_inventory_recovery_v3_validation.py:25-30` only checks
`command_run()` raising on exit 23; it never inspects a receipt or `run()`.

### VR2 — P2: ordinary leader exits bypass descendant cleanup

**Location:** `tools/validate_inventory_recovery_v3.py:95-117`; coverage:
`tests/test_inventory_recovery_v3_validation.py:33-57`.

Process-group cleanup runs only when the initial `process.wait()` raises.
A leader can fork a same-group child and exit while that child continues
running. If the leader exits nonzero, `CalledProcessError` is raised at 117
outside the cleanup handler; if it exits zero, the function returns normally.
Neither path sends a group signal or checks whether descendants survive.
The `Popen` context only waits for its direct child. Thus an ordinary failed
validation can leave workers alive, and a successful leader can advance the
runner while a descendant still runs and holds its log descriptor. No
detached session or unusual signal behavior is needed for this trace.

The existing parameterized timeout fixture correctly covers a different
case: the initial wait times out, SIGINT makes the leader exit, and the
finally block still kills its child even when that child ignores SIGINT.
That does not cover a leader that exits before the initial timeout.

**Required correction:** retain process-group ownership and perform bounded
cleanup on every command exit, including zero and nonzero leader exits.
Do not infer group termination from the leader's return code. Preserve a
nonzero command failure and refuse acceptance if cleanup cannot establish
that the owned descendants have stopped.

**Focused regression:** parameterize leader exit 0/23 with a synchronized
same-group child that remains alive and ignores SIGINT. Require bounded
return and no running descendant, and require the original exit-23 failure
to remain a failure. Keep an independent cleanup guard in the fixture.

### VR3 — P2: the timeout cleanup itself has no final time bound

**Location:** `tools/validate_inventory_recovery_v3.py:96-114`.

After the ten-second SIGINT grace period, the code sends SIGKILL and calls
`process.wait()` without a timeout at 114. SIGKILL delivery does not guarantee
immediate exit, for example when the leader is stuck in uninterruptible I/O.
That wait can outlive the advertised command limit indefinitely, preventing
the failure receipt from being written. The enclosing `with Popen(...)`
also has an implicit wait on exit, so adding a timeout only at 114 would
still leave an unbounded context-manager cleanup path.

**Required correction:** use an explicit bounded cleanup/reap deadline and
avoid an unconditional context-manager wait when it expires. Record cleanup
incomplete, the owned process identity/group, and the original failure;
return failure rather than claiming termination or waiting without limit.
This cannot promise immediate termination of an OS-uninterruptible task,
but it can keep the validator's own wait bounded and its evidence honest.

**Focused regression:** use a controlled process stub whose timed waits
continue to expire after kill; require bounded failure without any unbounded
wait or implicit exit wait. Also cover interruption during cleanup while
preserving the original error. The current four cases use normal sleeping
processes and do not establish this bound.

## Race-fixture disposition

No additional concrete defect established in the authorized fixture changes.
The read hook at 185-191 captures the original bytes before publishing and
returns those stale bytes. The exists hook at 193-197 similarly preserves
the original existence result. Publication is one-shot, temporarily restores
both original Path methods, and uses the resource lock and real writer
(173-181); it does not recursively trigger its own hooks. Head/native cases
select the second matching read, and the transition case selects the exact
numbered path; the fired assertion prevents a silently unused hook.

The busy fixture at 209-226 invokes the original inspection, then appends a
real sibling reservation on each observation. It requires precisely three
observations, `PUBLICATION_IN_PROGRESS`, dispatch refusal, and unchanged
retained floor bytes/mtimes. These are source observations, not a rerun or
proof of all production interleavings. The partial-read fixture's final
bytes/mtime comparison checks the subsequent stable status call; it does
not independently prove absence of extra writes during the injected race.
This distinction does not reopen the separately closed production review.

## Exact reviewed SHA-256 values

Raw file-byte hashes, checked again after inspection. The floor-followup
hash identifies the entire file; only the stated imports/race-fixture slice
was inspected here. Git HEAD was
`23c4948753682d263d540689ea055cce8b9ce647`; the runner was modified and both
test files were untracked, so HEAD is not a substitute for these hashes.

```text
5b34c6a7494d8b0de30ec75a7ed0565e934aba2353d0643cee82f27d805df57e  tools/validate_inventory_recovery_v3.py
8468b5a12ba4fe3184ecfb8ecc4dd870b031635b6ca0703875a82b1da23be1c9  tests/test_inventory_recovery_v3_validation.py
f5c4f57d5b3db4589cab80ba824a925af50238246e74a52f5e7df938da802e76  tests/test_inventory_recovery_v3_floor_followup.py
```

Closure-context document hash (read-only; not a new production inspection):

```text
93baa36df356e94234584f637d702fa187917389b922282c2d10b1192a178f0a  docs/reviews/INVENTORY_RECOVERY_CONSUMPTION_FLOORS_REVIEW_2026-10-28.md
```

## VR1–VR3 repair follow-up — 28 October 2026

This follow-up supersedes the disposition of VR1–VR3 for the exact hashes
below. Static inspection of the runner, its validation tests, and immediate
process-observation/receipt helpers only. The prior floor-production closure
and race-fixture disposition are not reopened. No project imports, tests,
Ruff, process demonstrations, master/authority changes, live calls, or service
actions were performed. Only this findings file is appended.

### Disposition

| Finding | Disposition at the reviewed revision |
| --- | --- |
| VR1 | Closed: final mismatches and final read failures force a persisted failure; original command errors are retained. |
| VR2 | Ordinary-exit defect repaired; remains open as VR2-R below because failed observation can bypass group signaling. |
| VR3 | Closed: cleanup uses bounded polling and signal phases, without an unconditional wait or Popen context exit. |

### VR1 — closed: protected final acceptance

At `tools/validate_inventory_recovery_v3.py:209-219`, final flags start false,
both comparisons run inside a protected block, a false comparison raises,
and caught finalization errors force `status: fail` before persistence. The
earlier `error` field survives separately from `finalization_error`. Exit
status at 222 follows the finalized status. The previously identified
pass-with-false-flags and final-read-error-after-exit23 paths are repaired.

The receipt fixture invokes real `run()` with temporary authority, fixed
source binding and stubbed command evidence (validation tests:17-50). The
source/authority mutation cases change only the third comparison read and
require failure in the persisted receipt (61-88). The read-error cases fail
the final source or authority read after an original exit23, then assert
both errors remain in the finished failure receipt (91-122). These exercise
the repaired acceptance path rather than only checking a helper exception.

### VR2-R — P2: observation errors can bypass both cleanup signals

**Locations:** `tools/validate_inventory_recovery_v3.py:107-125`; immediate
helper `tools/recovery_observation.py:198-207`.

Cleanup is now reached after both zero and nonzero leader exits
(runner:134-150), fixing the original ordinary-exit omission. However, each
signal phase calls `observe()` at 116 before reaching `os.killpg()` at 119,
and the outer exception handler advances to the next phase when observation
raises. If `group_members()` raises on both initial scans, neither SIGINT
nor SIGKILL is attempted. The final scan only records another error.

This has a direct helper path: enumeration reads stat files for all visible
processes and propagates an OSError such as PermissionError for an unreadable
entry, including an unrelated process; only disappeared entries are ignored.
With an owned sleeping leader/child and that persistent read error, the
runner returns `CommandCleanupError` while leaving the group running without
even attempting a signal. A KeyboardInterrupt during the initial observation
of the SIGKILL phase likewise skips the hard-stop attempt after SIGINT. The
receipt correctly remains fail; this residual is lost cleanup, not false pass.

**Minimal correction:** separate observation failures from the bounded signal
attempts so inability to enumerate cannot veto best-effort termination of
the owned command group. Retain observation errors, original failure and
identity evidence, and keep the result incomplete when quiescence cannot be
established. Preserve process ownership checks and the existing deadlines.

**Focused regression:** keep a fake leader unreaped, make `group_members()`
raise OSError on every observation, and assert that SIGINT and SIGKILL are
both attempted, return remains bounded, and the original failure plus
observation errors survive in `CommandCleanupError`. Also inject interruption
at the SIGKILL phase's first observation and require the hard-stop attempt.
The current fake test (validation tests:211-261) keeps observation successful
and injects interruption inside the SIGINT signal call; it does not cover
either observation-failure branch. No such regression was run by the inspector.

The new ordinary-exit fixture (170-208) is correctly synchronized: its child
installs SIGINT ignore and writes its PID before acknowledging readiness
through a pipe, then the leader exits 0 or 23. It checks bounded return,
absence of a running child and preservation of exit23. Its independent
finally cleanup remains. This is targeted coverage of the repaired original
VR2 trace, not evidence closing VR2-R.

### VR3 — closed: bounded reap and failure evidence

The runner has no Popen context manager and its only `wait()` supplies the
command timeout (134-140). Cleanup uses `poll()`, monotonic phase deadlines
and sleeps capped at 50 ms (103-131). After those phases, an unreaped leader
or nonquiescent group produces incomplete evidence and `CommandCleanupError`,
which `run()` records as a failure with cleanup details (204-208). There is
no unconditional reap wait after SIGKILL. This closes the specific VR3 wait
defect; VR2-R concerns skipped termination attempts, not renewed unbounded
waiting.

The fake-process fixture refuses a wait without a timeout and any context
entry/exit, always reports unreaped, advances a simulated monotonic clock,
and requires only the initial wait, both signal attempts, at most 5.01 seconds
of cleanup time, incomplete evidence and the original exception as cause
(validation tests:211-261). This establishes the intended branch coverage in
source, without claiming that arbitrary blocked OS operations have a hard
real-time bound. The intentional BaseException catch at runner:143 is
documented and preserves the original failure after cleanup; it does not
convert that failure into success.

### Retained validation evidence and exact hashes

Read the supplied SSD XML: it records 13 cases, zero failures, zero errors,
zero skips and suite time 10.250 seconds. The coordinator reports 13 passes
in 10.36 seconds and the subsequent Ruff noqa annotation. These timings are
different reported measurements, not an inspector rerun. The XML contains
no source-hash binding, so its passing result is not independent proof of
the exact post-annotation source bytes below or of the untested VR2-R branch.

Primary reviewed files (raw-byte SHA-256):

```text
b0e6b13feb2415ca52bf64f3c30e9ee2971c7c225769b80dac567c5e8e00a07d  tools/validate_inventory_recovery_v3.py
5fb5650226082e35a550b40fd07b466a0526784244acf1a8258400200772857e  tests/test_inventory_recovery_v3_validation.py
```

Immediate helper/reference files (only the relevant helper slices were
inspected; their unrelated entry points are outside this review):

```text
a8a2b21ec301b02babb918f39ba6a5cafc8b2cc1ead6c3ed28d9fc750a46ac88  tools/recovery_observation.py
243cd87ef67f1e254170ca6be8963253cf17846458eb2ac29f36c091b419cc87  tools/durable_program_supervisor.py
08b1b01175e60deceb27f68c87cbea6d30ad01f8b2182e524101902835855788  tools/validate_inventory_history.py
0c07f02d5123ce34971f054ef6020a86e9be1dfd67720abe23555a70df041bd2  tools/inventory_recovery_v3/reservations.py
3cd1627d36b261701afc40e96db316365b6057c9d08f871f1300df2c747a3448  tools/review_inventory_recovery_v3.py
c1576d25d400e3cb9758f069c8a78e92200b0761deafc9524812dbeee04391cc  tools/inventory_history_live.py
b670981147be8a51086be247494277e432a229792a5bda4009f643d2683a48eb  .localresources/validation-runner-recovery-20261028.xml
```

## VR2-R residual recheck — 28 October 2026

**Disposition: VR2-R closed at the exact hashes below. No concrete residual
defect established in this bounded recheck.** This supersedes the open VR2-R
disposition above. VR1/VR3 and the previously closed floor-production and
race-fixture slices are not reopened.

Scope: static inspection of the observation-error repair and its immediate
cleanup caller (`tools/validate_inventory_recovery_v3.py:103-154`), plus the
expanded fake-process regression
(`tests/test_inventory_recovery_v3_validation.py:211-274`). No tests, imports,
Ruff, process demonstrations, master/authority changes, live calls or service
actions were performed. Only this report is appended.

### Repair and regression disposition

- `observe()` resets the current observation fields before scanning, catches
  OSError/ValueError/KeyboardInterrupt internally, retains deduplicated error
  descriptions, and returns False on a failed observation (107-118). An
  enumeration error therefore no longer escapes to the phase-level handler
  before its signal attempt. In particular, persistent PermissionError and
  interruption of the initial SIGKILL-phase observation reach the respective
  bounded signal attempts instead of skipping them (120-132).
- A failed scan cannot reuse stale quiescence: `remaining` starts unknown and
  `group_quiescent` starts false. Errors remain retained even if later scans
  succeed; `complete` still requires a reaped leader, quiescent group and no
  errors (133-134). The caller preserves owner/original-error evidence and
  chains incomplete cleanup from the original failure (149-154). No
  observation error is converted into successful cleanup.
- The existing two- and three-second phase deadlines, capped sleeps and
  absence of unconditional cleanup waits remain intact in this slice. The
  repair does not introduce retries outside those phases.
- The persistent-error fixture raises PermissionError on every membership
  scan (239-242). The interruption fixture remains active after simulated
  time reaches two seconds until SIGKILL is recorded (243-244), so it reaches
  the hard-stop phase's initial observation rather than only interrupting a
  signal callback. Both cases require SIGINT followed by SIGKILL, bounded
  simulated cleanup time, the original exception as cause, incomplete
  evidence and the expected observation error (258-274). Persistent scan
  failure must leave membership unknown. These directly cover the reported
  VR2-R traces; the inspector did not execute them.

### Retained evidence and exact hashes

Read `.localresources/validation-runner-recovery-vr2r-20261028.xml`: 15 cases,
zero failures/errors/skips, including both added observation-fault cases;
XML suite time is 10.466 seconds. The coordinator reports 15 passes in
10.59 seconds and Ruff passing. These are retained/reported results, not
inspector executions. The XML itself contains no source-hash binding.

Raw-byte SHA-256 values for this recheck:

```text
cab15fa329c1e2f7a868e34034c573f28be6c28e8d2fe99888efaa84b083932b  tools/validate_inventory_recovery_v3.py
a50b4c0611ab1bc6ba789e1e53e85388db98dcaa14812b1a4c3a643081a037dc  tests/test_inventory_recovery_v3_validation.py
bc0eb6800044aeae3e0e8f6a536f1453b065714efc4ef176b0a3bf6082455e8d  .localresources/validation-runner-recovery-vr2r-20261028.xml
```

The immediate enumeration helper's bytes are unchanged from the preceding
review; its behavior was not re-audited:

```text
a8a2b21ec301b02babb918f39ba6a5cafc8b2cc1ead6c3ed28d9fc750a46ac88  tools/recovery_observation.py
```
