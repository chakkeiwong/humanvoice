# Unspent qualification receipt repair

The first approved live service stopped before allocating calls. The complete
native history stack reads storage-cleanup-20261019/humanvoice/receipt.json,
which ProtectHome=tmpfs hides. The earlier environment probe validated namespace
and client parity but did not enter this history stack.

Keep the approved qualification source files, authorization bytes, budget
addition, account, grant, call/output directory and original service unit intact.
The separate repair adapter reads an exact SHA-256-checked receipt copy inside
the already approved output directory. It also passes that path to each fresh
verification-worker initializer before the original archive initializer runs.
Native image, alias, semantic, permission, account and settlement checks remain
unchanged. No service mount/network/write scope is added.

The preflight enters the complete history stack inside a network-isolated mount
view. All 229 historical settlements pass with 16 workers in 38.99 seconds;
account/grant bytes are unchanged and owned cleanup is complete. Sixteen repair
regressions and eight restart regressions pass; Ruff passes. Earlier failures
are retained under repair-20261108/attempt01. The restart guard requires the exact
missing-receipt error, zero allocations/settlements, complete cleanup and dead
previous owners. It rejects semantic failures, unknown receipts, live workers,
changed spending and exhausted launches.

Resume preserves launch one and permits only the original remaining two process
launches, the original November 9 01:29:40 Shanghai deadline, 2,235 total calls,
276 qualification sessions and the existing token authority. It requests no
additional budget. Source and repair identities are rechecked before dispatch.
The original supervisor continues to own cleanup and refresh both master files.

Grouped privileged restart: inspect the one failed transient qualification unit;
reset its failure state only when MainPID=ControlPID=0; submit that same unit with
identical properties and the fixed repair entry point. The root helper uses
isolated system Python and standard-library imports only. One pkexec invocation
performs the reset and submission, so they share one password request. Systemd
owns subsequent allowed crash restarts.

Exact host action:

```text
/tmp/humanvoice-release-env-20261029/bin/python /home/ubuntu/workspace/humanvoice/.localresources/session-qualification-resume-launch-20261108/resume.py start
```

The already granted live qualification authority is reused. The host approval
is for the concrete repair restart executable. Production inventory admission
and final ZLB acceptance remain separate.
