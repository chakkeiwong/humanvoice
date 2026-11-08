# Shared-memory startup repair and grouped conditional restart

The second qualification launch stopped before allocating calls. Python could
not create multiprocessing.SemLock in systemd's private /dev/shm, which inherited
root-only write permissions. The prior bubblewrap preflight had writable shared
memory and therefore missed this systemd-specific defect.

The prospective service retains every existing mount, write root, account,
gateway, native sandbox and budget. Add mode=1777 only to its private /dev/shm
TemporaryFileSystem, matching POSIX shared-memory behavior. The host /dev/shm
is unchanged. Keep both failed attempts and the original three-launch ceiling.
The original November 9 01:29:40 Shanghai deadline and total 2,235 calls remain;
no additional calls or tokens are requested.

The grouped host helper authenticates once, runs a 15-minute network-isolated
preflight as ubuntu with the actual systemd mount configuration, verifies native
configuration parity, actual shared-memory lock creation, all native historical
settlements and the extended grant status, then checks service cleanup. Only a
passing preflight allows reset/submission of the same live qualification unit,
using the final allowed process launch. A failed preflight cannot start live work.
The receipt-copy adapter and its spawn-worker initializer retain exact pinned
receipt validation. Native settlement and account checks remain unchanged.

All 29 affected regression tests pass, including twelve repair tests covering scope, attempt exhaustion, unresolved
usage, prior cleanup, copied grant readers, changed receipts/usage/plans and the
rule that preflight failure cannot launch production.
The prior receipt adapter has 16 passing tests and its restart boundary eight;
its offline history validation passed all 229 settlements with 16 workers.
Ruff passes. The first actual systemd preflight passed shared-memory creation
and all 229 historical settlements in 34.247 seconds. It then rejected grant
status: the additive grant reader had copied its globals before the native
history scope installed versioned settlement dispatch. That copied function
therefore used the ambient profile when reading an older stream receipt.
The conditional launcher withheld the live restart; two launches remain used,
zero qualification calls have been allocated, and one launch remains available.

The revised adapter binds the existing accounting.completed_usage dispatcher
before grant_extension.scope copies the reader. Both the offline preflight and
live worker use this ordering. The native status function still compares every
replayed settlement against its retained account event and checks the original
stage bounds, baseline prefix, identity and approved cumulative ceiling. The
adapter restores the reader on every exit; it does not cache account validity.
A distinct forwarding function prevents native alias replacement from replacing
the historical dispatcher itself. A nested-scope regression checks both native
and copied grant readers, and verifies the dispatcher's identity stays intact.
The previous packet, executable sources and failed result are preserved under
shm-repair-20261108/retained/grant-dispatch-failure-01.

Before another administrator authentication, diagnostic.py run exercises the
full native history and grant path as ubuntu inside a read-only bubblewrap
view with an isolated network and 16 workers. The actual systemd preflight
still must pass before conditional submission. Sandbox permission to create
the diagnostic namespace is separate from the administrator password.

The first unprivileged full replay passed: ceiling 2,235, previously used 1,424,
remaining/available 811, outstanding holds zero. Account and grant bytes did
not change. Its proof is retained under dispatch-pass-before-nested-scope-fix;
the final nested-scope revision also passed the full isolated diagnostic with
the same 811 available calls and complete process cleanup. Both master programs
are refreshed before the already-approved grouped systemd preflight/restart.

Exact grouped host action:

```text
/tmp/humanvoice-release-env-20261029/bin/python /home/ubuntu/workspace/humanvoice/.localresources/session-qualification-shm-repair-20261108/repair.py start
```

The root helper uses isolated system Python and standard-library imports only;
all manuscript/client/history work remains under UID ubuntu. Automatic restarts
cannot replenish budget or the launch count. Production inventory admission and
final ZLB acceptance remain separate.

Actual host result: SYSTEM_NATIVE_HISTORY_PASS for repair identity
0cee686120b560e8692eab5a17ed97aa9b2747c53ed04ce481d585b8e8e0b44a.
Preflight exited successfully and cleaned up. The same authenticated helper
reset and submitted the qualification unit, which is active with supervisor
PID 303532, launch 3 of 3. No extra call/token authorization was consumed by
preflight. The supervisor's native status remains authoritative for live work.
