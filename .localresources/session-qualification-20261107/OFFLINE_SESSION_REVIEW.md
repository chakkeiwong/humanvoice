# Bounded offline authentication repair

The old check-system launcher invoked pkexec for every repair attempt. Each
short-lived helper exited after three probes, so the next retry requested the
administrator password again. Codex command approval did not cache this OS
authentication.

The new explicit open-system action authenticates once. The root helper lives
for at most one hour, bounded also by the existing November 9 01:29:40 Shanghai
execution deadline, and admits at most eight three-probe batches. check-system
reuses the local session; it never invokes pkexec, silently renews authority or
changes passwords/sudoers/polkit rules. close-system shuts it down early.

Privileged actions requested together: create the temporary protected Unix
socket under /run/humanvoice-offline-20261107; start, inspect, stop and collect
only the uniquely named environment, protocol and signal transient services;
remove the socket at close/expiry. Services retain User/Group ubuntu, no extra
capabilities, no-new-privileges, a private network, the reviewed mount view,
75-second service limits and whole-service cleanup. No boot service is enabled.
Only the three fixed namespace_probe.py actions can run. The protocol check
uses dummy credentials and a loopback gateway. There are no remote model calls.

The root helper uses /usr/bin/python3 -I -B and only standard-library imports.
It loads the reviewed scope once into memory and never imports project modules
as root. Socket peer credentials restrict clients to UID 1000; the client checks
that its server is root. Every request binds the exact scope digest, including
helper source, mounts and environment. Changed unprivileged probe code must pass
its source-bound regression gate; changed privileged scope requires a new
reviewed session. Attempt count advances before work, including failed attempts.
Expiry, close, peer abandonment after a batch and exceptions clean up owned
services. The previous failed attempts and evidence remain retained.

Prepared scope: offline-session.json.
Scope SHA-256: 52ea0267866de471e062afb99cca54b47866f1faa76bf68c280d5eec9556b64a.

Validation: 95 qualification/campaign tests pass using 16 workers, including
scope escalation rejection, caller identity, expiry, attempt exhaustion,
failure accounting, fixed commands, socket framing, and timeout cleanup.
Ruff passes. The socket regression initially hit sandbox EPERM; the identical
suite passed with the explicit fixed host-test approval. Real authentication
reuse and current-client startup remain to be tested in the host environment.

Exact privileged entry point:

```text
/tmp/humanvoice-release-env-20261029/bin/python /home/ubuntu/workspace/humanvoice/.localresources/session-qualification-20261107/offline_host.py open-system
```

The same prefix with check-system, session-status, or close-system uses the
already authenticated helper. prepare-system only writes its review packet.
This request does not approve the separate 235-call extension, live model
qualification, production launch or final ZLB acceptance.

Observed host validation: one authenticated helper executed two complete batches
with the same scope identity and expiry. The second required no new pkexec call.
All six services cleaned up. Native configuration parity and the synthetic client
now pass after consistent private index initialization. The archive-receipt
visibility repair keeps the same mount scope. Affected suite: 98 passes.

Final observed validation: the third batch passed environment/configuration,
synthetic response capture and exact SIGKILL status. All nine services from three
batches cleaned up; one authentication was reused, and close-system explicitly
closed the helper (clean exit). The suite passes 98 tests. Native/private index
snapshot and the pinned local archive receipt fixed the two remaining startup
issues without changing service scope. Live qualification review is prepared,
with separate budget/launch approval still required.

Live handoff review also found that its old 30-second client timeout included
interactive authentication and namespace construction. The fixed launch submits
with systemd-run --no-block, allows up to 180 seconds for authentication/submission,
and reports SUBMITTED until the actual service is observed. The existing service
startup/runtime bounds and cumulative execution deadline remain enforced.
The 98 affected tests and Ruff pass; earlier review artifacts remain retained.
