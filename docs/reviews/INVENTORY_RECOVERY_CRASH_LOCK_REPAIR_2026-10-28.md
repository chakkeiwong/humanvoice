# Crash recovery and installed-lock fixture repair — 28 October 2026

## Recovered state

No surviving recovery validation process was found on entry. The canonical
humanvoice_manual_approvals.py status command confirms human approval
on-request/user/workspace-write and production services inactive/disabled.
No inference, host deployment, authority edit, commit or push was performed.

The retained floors failure is
validation/a0aaa78de204019bfc3e/floors-5951dc19a43d under the prospective
recovery-policy-repair-20261027-01 output. It records 889 passing cases and
one failure in test_public_offline_preflight_initializes_canonical_campaign[900].
Source and production authority remained unchanged; release_acceptance=false.
The isolated retry before this recovery also failed. Both are historical
failure evidence, not acceptance. The preceding twelve-case executor pass
predates subsequent test-fixture changes and needs a new exact binding.

## Root cause and repair

installed_for() created old-campaign/generation-02 and retained it as the
installed cursor. Its new live.shared_locks() call instead read a cursor()
monkeypatch left by the native public-preflight test, which pointed to the
exhausted predecessor. A minimal offline probe confirmed the exact difference:
only the two execution.lock/executor.lock paths differed; program.BASE agreed.
The production runtime closure correctly rejected this inconsistent record.

The fixture now binds cursor() to its own cursor.json before deriving locks.
The configured fixture also sets program.BASE before installed_for(), avoiding
a second order-dependent mismatch in ordinary configuration tests. The added
fast regression seeds the conflicting caller cursor and asserts the exact
installed cursor and all three expected lock paths. No production guard,
frozen historical source or retained audit receipt was changed.

## Validation and continuation

Ruff passes for the changed fixture. All 120 focused configuration/runtime-closure
cases and the formerly failing native public-preflight test pass in 141.69 seconds
with sixteen workers. XML is retained at docs/reviews/crash-lock-repair-2026-10-28/focused.xml.
The fixed floors gate passes 891 exact-member cases in 779.27 test seconds at
validation/bf6525157a631b6918e6/floors-3ca2d2557dfe. The same-source executor
passes all 12 cases in 850.78 test seconds at executor-f4135811ea2e. Both retain
unchanged source/production authority and release_acceptance=false. Final
verification rechecks current binding, authority bytes, receipt evidence hashes
and XML membership. Summary: docs/reviews/crash-lock-repair-2026-10-28/verified-gates.json.
Both validation processes have ended. The core source freeze ends at this boundary.

TX3b still needs the reviewed host-authenticated monotonic control witness and
public factory/monitor composition. The /tmp prototype relies on fixture trust
callbacks and is not a production implementation. Then complete TX4 cold
reconciliation, TX5 stale-plan repair, TX6 receipt-only progress, TX7 bounded
replay, native multi-successor/soak and full release. Live deployment requires
the concrete grouped host action. Inventory remains 166 retained/439 unfinished.


## Parallel offline continuation

While the core source/tests remain frozen, a prospective witness implementation
was built under .localresources/control-witness-20261028. It does not enter the
current validation binding or public runtime. Storage uses durable SQLite
transactions with full pending commands, exact CAS and idempotent retry. The
read transport uses bounded frames/deadlines, a fresh nonce and kernel peer
identity. The read service checks host-owned storage and bounds client handling.
Its tests deliberately identify same-user service fixtures; they do not prove
host installation. There is no writer/control CLI or runtime admission.

Next implement the reviewed exact host writer, trusted monotonic stop times,
witness-first workspace projections and crash reconciliation; then integrate
RuntimeLeaf/public factory and review the whole slice. The existing /tmp trust-
callback prototype remains unpromoted. No host action or paid inference occurred.


Final witness candidate check: 73 tests pass in 4.76 seconds with 16 workers,
Ruff passes, and before/after candidate source/test/lint-config hashes match.
Evidence: .localresources/control-witness-20261028/candidate-status.json.
The scoped checks do not close the independent review or host integration gaps
listed in .localresources/control-witness-20261028/REVIEW.md.
