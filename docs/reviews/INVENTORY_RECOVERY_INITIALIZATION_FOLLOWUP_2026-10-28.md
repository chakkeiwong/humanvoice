# Journal initialization follow-up — 2026-10-28

Bounded static follow-up of II1 and II2 in `docs/reviews/INVENTORY_RECOVERY_INITIALIZATION_IMPLEMENTATION_2026-10-28.md`. Read `/home/ubuntu/AGENTS.md`, repository `AGENTS.md`, the changed history/observation logic, relevant reservation entry points, and the added regression cases. This report is the only write. No source/test edits, imports, source/test execution, service operations, or other agents.

**Disposition: II1 and II2 are closed by static inspection of the prospective source. No concrete residual of either finding was identified.** This is implementation-review closure, not an independently executed validation result.

## II1 — Closed: missing J cannot be reconstructed through normal entry

`tools/inventory_recovery_v3/journal_history.py:52` now requires a present current journal unconditionally. The former `prior is None` exception is gone. `reconcile()` calls this inspection at line 66 before either persistence operation, so an exact legacy marker with `H(None,E_legacy)` and missing J raises before it can reconstruct J or commit the head. Default `RecoveryReservations.locked()` still reaches that guarded reconciliation at `tools/inventory_recovery_v3/reservations.py:81`.

For a complete new-format marker, `journal_history.py:40` additionally requires a non-null committed head record. A retained intent plus complete marker and `H(None,E)` is therefore rejected whether J is present or absent. The existing binding, initialization-identity, record-extension, and current/prior/pending membership checks remain in the common history path.

The valid legacy case remains supported: with no intent artifact, an exact legacy marker, valid `H(None,E_legacy)`, and intact J equal to the pending record, inspection succeeds. Reconciliation skips the journal write because J already equals pending and commits the head. This preserves existing journal membership rather than reconstructing a missing journal.

The explicit new bootstrap remains separate. `journal_initialization.py:85` compares incomplete states with exact six-publication prefixes; `initialize()` at line 139 publishes their missing tail directly under `locked(reconcile=False)`. General history inspection is reached for complete/legacy states, not for pending bootstrap prefixes. Thus the stricter normal-entry checks do not block the authorized pending-head-before-J bootstrap cut.

**Regression inspection:** `tests/test_inventory_recovery_v3_initialization.py:423` covers the four legacy/new-format × J present/absent combinations. Its three rejected combinations exercise initializer, status, read, and default lock entry with unchanged artifact snapshots. The valid legacy/present case checks nonmutating status, successful normal entry, and head commitment. These cases address the original normal-entry omission. They were read, not run.

## II2 — Closed: present non-object intent cannot masquerade as absence

`tools/inventory_recovery_v3/journal_initialization.py:104` now returns `None` only when the captured artifact bytes are absent. Every present artifact is decoded and required to be a dictionary at line 108. Present `null` therefore raises before the legacy marker branch can mistake it for an absent intent; arrays, booleans, numbers, and strings are rejected as well. This matches the object requirement in `src/humanvoice/artifacts.py:25`, used by ordinary accounting reads.

The observation error remains inside the existing bounded stability check: a stable malformed snapshot re-raises the error at `journal_initialization.py:121`, rather than returning READY or treating stable corruption as publication progress. `RecoveryReservations.status()` consumes this observation directly without entering a lock.

**Regression inspection:** `tests/test_inventory_recovery_v3_initialization.py:457` supplies an otherwise valid legacy triple and each of `null`, `[]`, `false`, `0`, and a JSON string as the retained intent artifact. Each case checks rejection through direct observation, status, read, and initializer entry, and compares snapshots after each action. This directly covers the absent-versus-present defect. These cases were read, not run.

## Validation boundary

The coordinator reports 439 cases passed before these final fixes; that result does not validate the source and nine added cases inspected here. The new focused suite was reported running during this follow-up, and no outcome is claimed for it. Canonical initializer permission and the absent canonical factory remain outside this exact-findings follow-up. No release, deployment, restart, or paid-execution claim or authorization follows.
