# Journal initialization implementation findings — 2026-10-28

Bounded static review against IN1–IN4 in `docs/reviews/INVENTORY_RECOVERY_INITIALIZATION_REVIEW_2026-10-27.md`. Read `/home/ubuntu/AGENTS.md`, repository `AGENTS.md`, the four requested files, and narrowly relevant validation helpers/callers. This report is the only write. No source or test edits, imports, source/test execution, service operations, or other agents. Findings below follow code paths; they were not executed.

The coordinator reports 298 focused cases passed in 95.83 seconds and Ruff passed. The earlier 746-case full-suite result predates these source edits. During review the coordinator updated only tests: the late-veto test now targets observations 2 and 3, which I inspected; additional post-publication veto coverage was reported. Neither those subsequent test edits nor this review inherit a new validation result. Canonical initializer permission remains an integration obligation, and the absent canonical factory/IN4 is outside this implementation review. No release, deployment, or paid-execution conclusion follows.

## II1 — High: ordinary reconciliation still reconstructs a missing legacy journal

**Locations:** `tools/inventory_recovery_v3/journal_history.py:49`, `tools/inventory_recovery_v3/journal_history.py:63`, `tools/inventory_recovery_v3/reservations.py:65`, `tools/inventory_recovery_v3/journal_initialization.py:43`.

An exact legacy two-field marker, no initialization intent, a valid head `H(committed=None, pending=E_legacy)`, and an absent `reservations.json` pass ordinary `journal.locked()` entry. This is the old initializer's first-head-before-journal crash cut; no fabricated hash or changed binding is needed.

1. `require_complete()` recognizes the exact legacy marker and returns `None` without requiring intact head/journal membership.
2. `journal_history.inspect()` accepts the head and its legacy pending record. The missing-journal guard passes because `prior is None`; the membership guard also passes because `current == prior == None`.
3. Default `locked()` calls `journal_history.reconcile()`, which publishes the absent journal from `head["pending"]`, then commits the head. The ordinary entry has therefore completed legacy initialization.

The explicit initializer and status reject this same snapshot because bootstrap `inspect()` adds `current is not None` at line 82. That protection is absent from the ordinary reconciling path. A complete new-format marker plus retained intent and an initial pending head has the same missing-journal hole through default `locked()`, although that complete-marker/head combination is not a valid new bootstrap cut.

This violates IN2's explicit requirement that legacy compatibility have intact H/J and that legacy missing J block without reconstruction. It also defeats the intended separation in which only the explicit offline initializer completes an exact new-format empty tail. This finding does **not** claim that the existing `prior is not None` guard recreates committed consumption; that guard still rejects the missing committed journal.

**Required correction:** enforce missing-journal rejection in the common normal history/reconciliation path for legacy and complete new-format markers. Keep reconstruction of `H(None,E)` confined to the explicit pending-bootstrap transaction, which already publishes its six-step tail directly.

**Focused regression needed:** retain an exact legacy marker and valid `H(None,E_legacy)`, omit J, and enter default `locked()`; require a blocker and unchanged JSON bytes/membership. Repeat with a complete new-format marker/intent and initial pending head. The current legacy missing-journal case in `tests/test_inventory_recovery_v3_initialization.py`, `test_legacy_journal_reopens_without_upgrade_or_history_recreation`, constructs a committed head and exercises `initialize()` after deletion, so it does not cover this path.

## II2 — Medium: read-only status treats a present JSON-null intent as absent

**Locations:** `tools/inventory_recovery_v3/journal_initialization.py:104`, `tools/inventory_recovery_v3/journal_initialization.py:46`, `tools/inventory_recovery_v3/journal_initialization.py:78`, `tools/inventory_recovery_v3/reservations.py:418`.

Start with an intact valid legacy marker/head/journal triple and add `initialization-intent.json` containing the valid JSON token `null`. A stable status observation accepts this state:

- The snapshot reader uses bare `json.loads`, so the present file becomes Python `None`, indistinguishable from a missing file.
- The legacy branch's `retained is None` test succeeds. Its READY branch never checks the observed filename membership, so the surviving intent filename does not veto legacy classification.
- `status()` returns ordinary completed-journal counters and false authority/dispatch flags.

In contrast, `journal.read()` and ordinary history reconciliation use `reader()` and `humanvoice.artifacts.read_json`, which require a JSON object and reject the same present-null intent. Thus status reports a valid legacy journal for a stable malformed state that the accounting reader blocks. This is an IN2 strict-legacy/IN3 status-validation mismatch, not a transient publication race; the bounded rereads cannot resolve it because the bytes are stable. It does not itself grant dispatch authority.

**Required correction:** preserve absent-versus-present membership in the snapshot reader and apply the same object validation as `read_json` to every present artifact. A legacy journal must have no retained intent artifact, rather than merely an intent value that decodes to `None`.

**Focused regression needed:** the legacy triple plus present-null intent must make `observe()`, `status()`, `read()`, and initializer entry reject without changing the artifacts. Existing malformed-status cases write invalid JSON (`"{"`) into a new-format journal; they do not exercise a syntactically valid non-object in legacy classification.

## Scope of the findings

The inspected bootstrap publication list follows IN1/IN2's six writes: intent, pending marker, pending head, exact empty journal, committed head, complete marker. Its pending-state classifier compares against reconstructed exact prefixes; completed heads retain initialization identity and extension validation. The normal missing-committed-journal guard remains present. These observations narrow II1 to the normal-entry missing-J exception rather than asserting general consumption renewal.

The source checks an installed publication predicate before entry, after acquiring ownership/observing state, and immediately before each bootstrap persistence call; non-`True` returns veto. The coordinator's acknowledged preflight-only test gap is not counted as an additional finding, and the now-inspected observation-2/3 parameterization reaches the intended in-lock/prewrite sites. The absent canonical permission binding is not re-reported as a source defect.

Construction and status no longer create the root or lock, and observation uses bounded byte/membership rereads. II2 concerns validation equivalence within that nonmutating path. The atomic-cut tests cover the six publication boundaries, injected file-fsync/replace/directory-fsync errors, and process death leaving initialization temporary files. Static inspection of those tests is not an independent crash-test result. No additional concrete atomic-cut defect was established within this bounded review.
