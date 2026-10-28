# Prospective control witness work — 28 October 2026

This is an offline implementation candidate kept outside the frozen recovery
source/test binding while floors and executor validation run. It is not imported
by public.py, supplies no production admission, and installs no service.

- control_witness.py: SQLite FULL-synchronous transactions, exact genesis and
  configuration, full pending commands, compare-and-swap preparation, monotonic
  committed events and idempotent prepare/commit retries. Reads never initialize
  missing storage. Partial initialization fails closed.
- control_transport.py: bounded framed canonical JSON, fresh nonce binding,
  root-owned canonical endpoint and Linux SO_PEERCRED verification. The service
  connection handler exposes snapshot only. No writable action exists on the
  reader socket.
- control_service.py: protected host storage checks and bounded read daemon;
  no installer, initializer or writable action is exposed.
- test_control_witness.py/test_control_transport.py/test_control_service.py: explicitly offline storage
  and same-user socket fixtures. The FixtureReader bypasses the production
  root boundary only in tests. Passing these tests does not prove deployment
  isolation or permission to resume production.

Seventy-three cases pass with 16 workers in 4.76 seconds; Ruff passes. Tests include
real process exits inside prepare/commit transactions and immediately after
commit, cold retries, concurrent prepares/commits, interrupted storage updates,
lock contention, missing/corrupt state, symlinks, stale nonce/rebound replies,
forbidden write actions, bounded frames and total I/O deadline.

Protected database ownership/permissions and a bounded read-service lifecycle
are now implemented and tested with explicitly offline peer fixtures.
Remaining before promotion: exact host-approved
writer operations with monotonic trusted stop times; witness-first workspace
publication/reconciliation; real RuntimeLeaf integration; bounded independent
review and full fault matrix. The host installer must freeze and copy every
dependency to protected storage. Never execute privileged imports from this
writable candidate directory. A workspace directory and an identity digest
cannot substitute for the authenticated host boundary.

The earlier /tmp control-store prototype has not been promoted or used as
authority. Its trust callbacks do not implement this boundary.

Final candidate-status.json records unchanged source/test/lint-config hashes
and passing Ruff. This is candidate evidence only, with release_acceptance=false.
