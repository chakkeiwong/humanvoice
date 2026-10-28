# Inventory recovery end-to-end plan review — 28 October 2026

Bounded findings-only review of `docs/plans/INVENTORY_RECOVERY_CLOSURE_2026-10-28.md`,
master 4.12 / ensemble 202. Reviewed plan SHA-256:
`e187284695e2f4202ebb3a47d2efc381691adacbec67f700e3eed4e95cfc89d3`.
The root `AGENTS.md` applies; no nested `AGENTS.md` was found under `docs` or
`tools`. The six requested source modules were read, with narrow dependency
reads to resolve publication semantics and the active master release contract.
This is a static plan review, not implementation certification or a full audit.
No project modules, tests, inference, service commands or production-authority
operations were executed. No agents were spawned. Only this report is written.
The coordinator's independent TX3a implementation is outside this review.

## F1 — P2 / Medium: make cold recovery phase-dependent before imposing an order

**Plan evidence:** closure plan lines 38–43 explicitly require restart intent,
native claim, journal, campaign head, receipts and cursor reconciliation “in
that order.” This combines existing-spend recovery and publication of an
unallocated successor without stating which generation each operation owns.

**Source evidence:** `tools/inventory_recovery_v3/campaign_history.py:341`
revalidates a pending successor before publishing its transition. The native
preparation verifier rejects any account receipt, allocation ledger, seal or
calls directory (`tools/inventory_recovery_v3/campaign_preparation.py:37` and
`:67`). Campaign publication then writes head membership, cursor, repair
receipt and pending-clear, in that order (`campaign_history.py:368`). Its
reader explicitly rejects a repair receipt ahead of its cursor
(`campaign_history.py:254`). Bootstrap similarly forbids initializing after
allocation (`campaign_history.py:139`).

**Consequence:** interpreted as a single mutation sequence, the plan permits
claiming the pending successor before finishing its campaign publication,
after which native preparation replay refuses that allocated stage. Treating
“receipts” as campaign repair receipts also reverses their required cursor
dependency. These are recoverable publication cuts that can become permanent
refusals even when each individual component is correct. The plan needs to
distinguish read-only inspection from completion of existing claims and from
creation of a new claim; listing all artifacts once is insufficient.

**Required plan change:** specify a phase table keyed by committed generation,
pending generation and existing claim membership. Reconcile already-spent
predecessor/native obligations without allocating an uncommitted successor.
Finish an unallocated successor's campaign transaction through head membership
→ cursor → repair receipt → pending-clear before its fresh readiness/hold/claim.
Name native reservation receipts, restart receipts, campaign repair receipts
and manuscript receipts separately, and preserve each protocol's publication
order. Keep restart charging exactly once and status inspection read-only.

**Acceptance:** through both cold public commands, reopen after each campaign
publication cut with (a) an unallocated successor and (b) an existing native
claim on the committed generation. Require successful convergence with no
fresh successor claim before campaign commit, no receipt/cursor inversion and
no renewed charge. Stop and repeated-reopen variants must preserve those
outcomes. This refines TX4/CP3; it does not request changes to frozen evidence.

## F2 — P1 / High: retain the complete master prerequisites for final ZLB acceptance

**Plan evidence:** closure plan lines 68–75 and gate row 108 proceed from the
remaining ZLB inventory to writing/review, assembly/release, reproduction and
human acceptance. They omit the second benchmark and do not bind downstream
admission to the master product prerequisites.

**Contract evidence:** the active phase map in
`docs/plans/ENSEMBLE_MASTER_PROGRAM_2026-09-30.md:1638` requires E4-Q → E2-R →
E5-Q → E7-RS → E6-B → E7-RB → E7-H. E6-B explicitly includes ZLB **and one
distinct authorized held-out benchmark** (`:1642`); E7-RB reproduces **both**
packets (`:1643`); E7-H depends on E7-RB and A4 and binds acceptance to the
exact immutable ZLB identity (`:1644`). The same map requires qualification
after the integration freeze (`:1648`).

**Consequence:** the closure checklist can be satisfied with only a ZLB packet
and its reproduction while a required benchmark and its reproduction remain
absent. Retaining one qualified inventory route also does not, by itself,
establish current qualification and prior product gates for downstream writing
and review. This permits an incomplete end-to-end completion claim.

**Required plan change:** add an explicit dependency reference to the active
master phase map and a gate-evidence table covering qualification/calibration,
per-manuscript baseline, small production/reproduction, both benchmarks, both
reproductions and exact-identity final acceptance. Mark each prerequisite as
validly retained, invalidated, or outstanding against the current relevant
source/prompt/model/configuration identities. Reexecute invalidated or missing
gates under separately admitted budgets; do not automatically rerun valid
historical gates or treat the inventory budget as authority for later phases.

**Acceptance:** final-release admission must reject a missing held-out packet
or either reproduction, stale prerequisite identity, and a human decision
bound to another ZLB artifact. Passing inventory/recovery tests alone must not
satisfy any of these product gates.

## No additional finding in the remaining requested scope

- **Immutable versus mutable authority:** TX3a/TX3b explicitly separate frozen
  configuration from lawful consumption, require monotonic committed floors
  and reject rollback. This addresses the whole-file recapture problem in
  `installed_authority.py:76` and `handover.py:78`; its open implementation is
  not a new plan defect.
- **Readiness-to-claim serialization:** TX5 explicitly requires serialization,
  immutable retirement/repreparation and successful sibling-growth recovery.
  Those obligations cover the current account-lock gap between
  `claim.py:68` and the hold publication at `stage_authority.py:87`. No separate
  finding is raised for implementation work already declared open.
- **Meaningful progress:** TX6 explicitly requires verified committed manuscript
  membership, final-generation completion and rejection of mtime/heartbeat/
  identical-rewrite activity. This correctly replaces the behavior at
  `supervision.py:137`; no additional plan finding.
- **Other dependency and crash gates:** offline binding before public admission,
  common ownership, quiescence, inherited stops, crash cuts, nonrenewable budgets,
  native integration before combined soak, source-bound release and no-call
  preflight before live approval are explicitly required. Apart from F1, no
  additional finding in this bounded review; none of these gates is certified
  complete by this report.

## Bounded follow-up disposition — 28 October 2026

Reviewed the revised closure plan, SHA-256
`9a592374607f719354e3ca2d22c438a4f29192f4e7da6f8c164c8bd9a72161cc`,
only against F1 and F2.

- **F1: resolved at the plan level.** Lines 38–43 replace the universal
  mutation order with the phase table at lines 80–94. Existing committed
  claims and unallocated successors have distinct paths; successor head
  membership precedes cursor, repair receipt and pending-clear, and fresh
  hold/claim follows campaign commit. The table separately identifies receipt
  types and requires both cold commands to converge after publication cuts.
- **F2: resolved at the plan level.** Lines 68–78 retain E4-Q through E7-H
  and A4, both benchmarks and both reproductions. Lines 96–114 require
  prerequisite identity audits, reject missing/stale evidence and bind human
  acceptance to the exact immutable ZLB packet. Only invalidated/missing gates
  are rerun under separately admitted budgets.

No residual finding on these two plan changes. This disposition does not
certify their implementation, release admission or production completion.
The new TX3a offline binding is reviewed separately in
`docs/reviews/INVENTORY_RECOVERY_CAMPAIGN_BINDING_REVIEW_2026-10-28.md`.
