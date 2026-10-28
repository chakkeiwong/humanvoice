# Candidate review — 28 October 2026

Coordinator review only. No independent host review, deployment or release
admission is claimed.

The witness retains a complete pending command before local writes. Exact
sequence/head comparisons, request identities, idempotent retries and monotonic
initialization protect retained intent. Stored JSON null cannot silently erase
a pending command. Completed zero-sequence initialization cannot be recreated
after local evidence is deleted.

The publisher uses descriptor-relative regular-file access, bounded reads,
before/after byte checks, atomic replacement and file/parent fsync. Production
authority checks now reject unsafe ancestors, writable/foreign-owned leaves,
symlinks and hardlinks. The stable before/after witness reader performs no
repairs and produces the native stop-authority evidence shape.

Review of the protection patch found a real fresh-initialization defect:
child-file checks tried to read a directory before provision created it. The
repair checks the existing protected parent and delays child checks until the
local root exists. Three regressions preserve real missing-parent/type behavior
for absent root, root-only and events-directory states. The ancestry rejection
test now passes the fixture database boundary so it reaches the intended check.

Final validation: 156 exact cases with 16 workers, 2.702 test seconds, Ruff pass,
no failures/errors/skips/deselections or membership mismatch. The new fixed
runner retains before/after hashes for 921 source/test/config files and three
production authorities; all match. Evidence is in
validation/projection-f752e96e5f7f/validation.json. Its source remains frozen.
The prior 56-case approval-policy suite passed. Earlier 147/150/151-case receipts
are historical after these edits.

Remaining implementation boundaries:

1. The producer checks effective UID and protected paths; it does not itself
   authenticate the human request. A fixed protected action must bind the
   admitted release/configuration and exact approval before invoking it.
2. Compare-before-rename is not atomic against an untrusted writer. Protection
   checks reject the currently workspace-owned bound roots, so this candidate
   is intentionally not installable as-is. A protected namespace and native
   reader adapter must preserve original root/contract identities. Do not chown
   the workspace or treat a silently relocated root as equivalent.
3. Private files/directories currently created by the publisher are not proof
   that the unprivileged runtime can read them. Test real peer read/write
   permissions and the native consumer together before installation.
4. Local projection initialization recovery does not recover partially created
   protected SQLite storage. Installer-owned durable intent and fixed recovery
   actions are still required. Missing committed host state must remain a veto.
5. Stale endpoint recovery and durable supervisor diagnostics for operational
   read-service failures are not implemented. Full-history replay cost remains
   an explicit TX7 gate.
6. Public factory/monitor, TX4–TX7, native successors/soak, dependency-complete
   release and host authorization remain open. Tests use explicit fixture
   privilege adapters and do not establish production isolation or provenance.

Production remains stopped with 166 retained / 439 unfinished requests.
No new ZLB receipt, deployment or model inference occurred in this slice.
