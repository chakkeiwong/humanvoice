# Bounded launch union review — 28 October 2026

Final disposition: **LU1, LU2, and LU3 are closed for the repaired revision.**
The bounded OD1/OD4/OD5 unit-2 launch integration review is closed with no
additional reproduced blocker. Original findings and failure evidence below
are retained; the closure section supersedes their initial open disposition.
This is component acceptance only, not live execution authorization.

## Scope

One findings-only inspector reviewed launch_ownership.py, launcher.py,
the launch_handoff.require_inherited refactor, ownership.inherit's new
incoming_check, and test_inventory_recovery_v3_launch_ownership.py against
OD1/OD4/OD5 unit 2. Public factory/admission, retained immutable runtime
closure, monitor entry factory, and provider collector are excluded future
units. Closed descriptor findings and lease LR1/LR2 are not reopened.
The coordinator reports master 4.22/212, unchanged reviewed launcher source,
172 combined tests passing in 7.33s with 16 workers, and Ruff passing. These
reported suite results are not independent inspector test results.

## LU1 — P1: Post-spawn reporting failure publishes completion before quiescence

**Location:** tools/inventory_recovery_v3/launcher.py:112–130, especially
the exception-to-result conversion at lines 125–130.

The worker catches an OSError from the post-spawn acknowledgement or
heartbeat writes and immediately publishes an ordinary exit-90 result. It
neither waits for nor establishes quiescence of the already spawned campaign.
This applies to the new complete-lease path as well as the fallback path.

**Independent reproduction:** Use the existing launch-ownership fixture in a
temporary directory, acquire the real monitor union, capture and duplicate
the launch transfer descriptors exactly as the final-stop test does, and
consume them through launch_ownership.entry for the worker. Run the actual
launcher.worker with a real subprocess.Popen campaign using the fixture's
cold_entry. Override only durable.save in the probe process: on the first
heartbeat.json write, wait for campaign-entered.json, then raise
OSError(EIO, "offline heartbeat I/O failure"); allow all other writes.
No source or repository test is modified. Observed output:

~~~json
{"probe":"premature_result","worker_return":90,"result":90,"campaign_alive":true,"campaign_entered":true,"excluded_locks":9,"total_locks":9,"campaign_complete":false}
{"probe":"campaign_after_result","exit_code":1,"completed":false}
~~~

The second line is obtained by releasing and waiting for that same temporary
campaign after recording the first line. Its final held.check() fails at
ownership_roles.py:110–111 because the premature result retires its current
job: ValueError: Ownership job is changed, retired or outside its admitted
command. This is observable corruption of the running child's lifetime,
not merely an inaccurate report. The existing supervisor also treats an
ordinary nonnegative result as transitionable in supervision.tick(),
without the crash-recovery quiescence branch. No production supervisor was run.

**Required correction:** Distinguish failures before spawn from reporting or
observation failures after a child exists. Do not publish an ordinary terminal
result or retire the job until the spawned campaign is quiescent; retain its
ownership and process evidence while reporting the observation failure.

**Required regression:** Inject a one-shot post-spawn acknowledgement failure
and a heartbeat-write failure with a real waiting campaign. Require no
terminal result while it is alive, preserve the complete lock union and valid
campaign lease, then verify result/recovery publication only after quiescence.
This concerns the current worker-to-campaign edge, not the future collector.

## LU2 — P2: Fallback monitor launch forwards an ambient complete capsule without its FDs

**Location:** tools/inventory_recovery_v3/launcher.py:61–63; compare the
fallback worker rejection at lines 81–85 and launch_ownership.options:32–35.

Only the complete-lease branch scrubs inherited ownership environment keys.
With lease=None, monitor launch copies the entire ambient environment but
passes only the newly prepared job descriptor. An ambient complete capsule
therefore reaches a child without its advertised union. The fallback worker
explicitly rejects any such capsule, after the parent has published durable
launch intent and DISPATCHING state and invoked spawn.

**Independent reproduction:** In a temporary native fixture, acquire a valid
monitor lease, put its generated capsule into the environment alongside a
stale HUMANVOICE_CHAINED_HANDOVER_FDS value, and call launcher.launch with
owner_check=held.check but omit the optional lease. Capture the spawn
arguments and invoke launcher.worker under exactly that environment. The
probe deliberately uses an in-process spawn adapter to inspect this edge;
no claim of a real cold subprocess is made for this reproduction. Result:

~~~json
{"pass_fds_count":1,"full_capsule_forwarded":true,"old_chain_forwarded":true,"child_rejection":"Complete incoming ownership must be consumed at entry","intent":true,"ack":false}
~~~

The failure is fail-closed in the child, but the parent has performed a
durable dispatch that its own fallback child cannot consume. This is a
current fallback integration defect, not a public-factory prerequisite.

**Required correction:** Detect this incompatible ambient ownership state
before durable dispatch/spawn, or explicitly enforce a documented fallback
environment contract. Do not forward a capsule whose descriptors are absent
from pass_fds, and do not silently downgrade required complete ownership.

**Required regression:** Exercise fallback monitor launch with ambient
complete and obsolete next-hop ownership capsules. Require either early
rejection with no intent/spawn, or a valid explicitly supported fallback
handoff. Also verify the complete-lease branch still remaps and forwards its
entire checked union.

## LU3 — P2: Entrypoint descriptor-list rejection bypasses incoming cleanup

**Location:** tools/inventory_recovery_v3/launch_ownership.py:75–82,105,
at its call to ownership.py:228–231.

The new executable entry builds its explicit received tuple directly from
the capsule rows. If the capsule contains a duplicate row, that tuple has
repeated FD numbers. ownership.inherit rejects the tuple before creating
IncomingTransfer and before entering its cleanup scope. The executable entry
has no outer cleanup for this rejection, so all actual received references
remain open and the capsule remains unclaimed. This is the new entry adapter
violating the component's input precondition; it does not reopen LR1/LR2's
closed handling of valid explicit transfers.

**Independent reproduction:** Capture a valid monitor-to-worker transfer and
os.dup all nine pass_fds exactly as in the existing final-stop test. Remap the
complete and legacy capsules to those received originals. Append a copy of
the first descriptor row to the complete capsule and recompute its digest,
leaving all nine real descriptors and valid legacy job capsule present.
Invoke launch_ownership.entry in the receiving process and catch rejection:

~~~json
{"defect":"duplicate_row","error":"Invalid explicitly received descriptors","received_open":9,"received_total":9,"complete_env_retained":true,"parent_valid":true}
~~~

No lease body runs, but every received original still passes fstat afterward.
An executable that exits immediately would get kernel cleanup; that does not
satisfy the explicit entry rejection-cleanup contract when its caller catches
the exception. The probe closes those originals itself after measuring them.

**Required correction:** Make entry own and retire the received transfer
before rejecting capsule row shape/duplicates, with a reliable unique FD
cleanup inventory. Keep canonical capsule validation strict. Preserve the
closed LR1/LR2 rule: a replay must never reacquire cleanup ownership of reused
numbers. Do not weaken borrowed validation or make it close caller FDs.

**Required regression:** Duplicate a row while retaining every genuine
incoming reference, reject entry, verify all originals close once, naturally
reuse their numbers, and retry the same envelope. Rejection must preserve
those newly owned references and avoid callbacks. Include malformed row/FD
types with a clearly defined executable-entry cleanup inventory.

## Bounded positive checks

Independent entry probes with a valid nine-FD explicit tuple rejected both a
bad legacy capsule identity and an implementation.config() exception. Each
closed all nine originals and left the parent lease valid. This confirms the
new incoming_check placement covers failures inside its claimed-transfer
scope. Ambient capsule strings remain after those failures, but the existing
transfer retirement prevents valid-tuple replay from acquiring cleanup again.
The coordinator subsequently added a passing incoming_check failure/replay
case; that valid-tuple case is distinct from LU3's pre-claim rejection.

Source inspection confirms the complete branch duplicates the ancestor union,
remaps legacy job descriptors, uses current native checked_request, and runs
final lease/stop checks after log setup. Borrowed require_inherited performs
validation without closing caller descriptors. Campaign entry rebuilds its
legacy job capsule on its owned duplicate. Existing nine edge tests cover
real monitor/worker death, pre-ack survival, union omission, mismatched legacy
roles, and final-stop vetoes; their passing result is coordinator-supplied.
No further actionable defect was established in those bounded paths.

## Evidence and boundaries

The prescribed humanvoice_manual_approvals.py check confirms
on-request / user / workspace-write, seven rejected command forms, and
zero model calls. All reproduction activity is offline, with temporary files
and local fixture subprocesses. No privileged action, source/test/master
write, provider/production/service action, or restart was performed. Only
this findings file is a persistent review write.

Reviewed SHA-256 values:

~~~text
3feec435fc915ac0a83b0ae76a3b21909fb12e27e2da8702da431d28eebafead  launch_ownership.py
7028c97fe295cea8370838c76ce39f3780de110dd414e2ab129ffa0ca6c830e3  launcher.py
ef28b3d668e1ff8944ae39252333af588e2b7e547c0064b613be8a12ed1cb943  launch_handoff.py
66b077dc8e3a3050f2b50694422705576aac7e029e62c040c9163bf70cce60ac  ownership.py
77cb9ff6b7abd8faed88d0af8c9db5f62bcc4f0d58e151a82a8da9fdaa84bc73  test_inventory_recovery_v3_launch_ownership.py
~~~

## LU1–LU3 closure recheck — 28 October 2026

**Disposition: all three findings are closed for this bounded revision.**
No further actionable defect was reproduced in the authorized launch slice.
All original finding line references and hashes above refer to the original
review snapshot; the repaired revision is identified below.

### LU1 closure: preserve unresolved execution and wait for the child group

launcher.worker now retries post-spawn acknowledgement and heartbeat OSError
failures while retaining the worker and inherited union. The campaign starts
its own session. A reaped leader alone does not set child_finished: the
worker also requires recovery_observation.group_members(child.pid) to return
empty. Failures after a spawn attempt with unresolved child completion
propagate without manufacturing a terminal result (launcher.py:97–159).

Independent regression execution passes both transient reporting cuts and
the sustained heartbeat outage/restore cut. In the outage case the campaign
remains alive, all expected locks exclude contenders, repeated reporting
failures accumulate, and no result exists before reporting recovery and
campaign release. The normal campaign completes its final lease check.

Three additional stdin-fed temporary-process probes independently exercised
the repaired worker with real Popen children:

~~~json
{"probe":"poll","no_result_during_live_child_or_group":true,"excluded_locks":9,"campaign_completed":true,"worker_outcome":"propagated","terminal_result_present":false}
{"probe":"spawn_return","no_result_during_live_child_or_group":true,"excluded_locks":9,"campaign_completed":true,"worker_outcome":"propagated","terminal_result_present":false}
{"probe":"surviving_group","no_result_during_live_child_or_group":true,"excluded_locks":9,"live_group_observations":3,"campaign_completed":true,"worker_outcome":0,"terminal_result_present":true}
~~~

For poll, the child adapter raises OSError after the real campaign enters.
For spawn_return, the spawn adapter creates the real campaign, waits for its
entry, and then raises OSError instead of returning the process handle. In
both cases the worker propagates the error, its caller can still validate
the held lease, the real child remains alive, and no result is published.
After release the campaign completes successfully; result publication remains
absent for the unresolved worker path.

For surviving_group, the campaign leader creates a same-group descendant
holding the full union and exits. The probe wraps the actual group_members
reader without changing its result, verifies leader reaping, absence of
result and all nine exclusions on three consecutive nonempty-group checks,
then releases the descendant. Only after the group empties does worker
publish exit 0. The added repository descendant case also passes. This
establishes the current same-group lifetime boundary; provider-collector and
public runtime composition remain separate future units.

### LU2 closure: reject incompatible fallback before dispatch

launcher.launch now rejects any ownership ENVIRONMENT_KEYS when lease=None
at lines 21–22, before configuration access, immutable request publication,
intent creation, state publication or spawn. All six ambient-key cases pass;
each verifies unchanged monitor state, no spawn, and no jobs directory.
Complete-lease launch remains covered by real cold edge tests, including
both parent-death paths, union omissions and final-stop vetoes.

### LU3 closure: independently declare cleanup inventory before capsule validation

launch_ownership.options supplies HUMANVOICE_RECOVERY_RECEIVED_FDS from the
same tuple used for pass_fds. Entry validates that explicit unique integer
inventory separately, then passes it to ownership.inherit. Malformed capsule
JSON is retained as raw input for retirement; capsule-shape and legacy
validation occur in incoming_check, after IncomingTransfer has claimed and
retired the transfer (launch_ownership.py:33–37,76–113).

The four entry regressions pass for duplicate rows, a non-dict row, an FD
with the wrong type, and invalid JSON. All transferred originals close after
the first rejection. After sentinel descriptors occupy those numbers, replay
rejects as already consumed and preserves the sentinels and parent lease.
The incoming_check callback regression also passes: first failure closes the
originals before Lease construction; replay neither reruns the callback nor
closes the reused references. Canonical validation stays strict and borrowed
inheritance remains non-consuming. This closes the entry-adapter finding
without reopening component LR1/LR2.

### Independent verification and final revision

Final frozen-snapshot run: **24 passed in 26.18s** — the complete launch
ownership test module (23 cases) plus the incoming_check failure/replay case.
All six recorded source/test hashes matched before and after this run.
An earlier repair snapshot had 23 selected passes; the later two added cuts
also passed separately (2 passed, 21 deselected, 5.07s). These separate runs
are not summed into a claimed full-suite count. The coordinator's final
**187 combined passes in 7.49s and Ruff pass** are reported evidence, not an
independent inspector rerun of that combined suite.

Tests were invoked through pytest.main from Python -B, with cacheprovider
disabled and a TemporaryDirectory basetemp. The only in-memory fixture
adaptation prepended sys.dont_write_bytecode=True to generated temporary
entry scripts so isolated child interpreters did not write repository
bytecode. There was one pytest warning about an already imported anyio
module not receiving assertion rewriting; all selected cases passed.
No repository test or source was changed by the inspector.

~~~text
fe31cff267874fbb059ed1fbba6556ad6af48bb8f3daeb501fa9b614512e9bb7  launch_ownership.py
df0900e7ea156def061cc8cefbf7e7ee2271c8257eca7d160a25bd77d0cb6c59  launcher.py
ef28b3d668e1ff8944ae39252333af588e2b7e547c0064b613be8a12ed1cb943  launch_handoff.py
66b077dc8e3a3050f2b50694422705576aac7e029e62c040c9163bf70cce60ac  ownership.py
cb593c31fa8969e9d3fa3c2e94f1a6d92e98b59352856a227132e7409b97e086  test_inventory_recovery_v3_launch_ownership.py
ddd5bbc00e3c64c8bb5d958800d44bd50085aaffb1896ebc459fde81c1fe8072  test_inventory_recovery_v3_ownership.py
~~~

The attempted interim closure probe during coordinator edits is not used as
acceptance evidence: its processes crossed the separate-inventory protocol
change. The final tests and additional probes above use the completed repair.
The user-stopped master and no-live state are unchanged by this review.
Public.py still rejects live actions; public factory/admission, immutable
runtime closure, monitor entry factory and provider collector are excluded.
Closed descriptor and lease reviews remain closed. Only this report was
persistently written; no production/provider/service or privileged action
was performed.
