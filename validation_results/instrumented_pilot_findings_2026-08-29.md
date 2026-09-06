# Phase 1.3 findings — instrumented pilot

Run date: 2026-08-29. Fixture: `fixtures/synthetic/register/001.tex`.
Runner: `tools/instrumented_pilot.py`. Data: `validation_results/instrumented_pilot_2026-08-29.json`.
Scope: internal evaluation (G4 Option A). Model: claude-opus-5, real API.

## Headline result

**The pipeline released a packet containing both planted violations.**

`fixtures/synthetic/register/001.tex` exists to carry two disclosure defects: the internal
label `WP3` and the path `/srv/humanvoice/private`. The pipeline behaved as follows:

| step | exit | outcome |
|---|---|---|
| init | 0 | snapshot-20260829-143112 |
| plan | 0 | 4 sections / 300 words |
| draft[0..3] | 0 | 3 of 4 drafts contain **zero words** |
| preflight | 1 | **2 register violations found** (WP3 @66, /srv/humanvoice/private @101) |
| repair | 2 | **abstained** — nothing repaired |
| release | **0** | **`"status": "released"`**, all five gates `"pass"` |

Preflight caught both violations. Repair fixed neither. Release passed every gate and
emitted a packet. The violations are in the released output:

    validation_results/pilot_workdir/release/packet/source/001.tex:3:
    The internal phase label WP3 and the path /srv/humanvoice/private are not

`release_decision.json` records `status: released`, `authorized_by: machine`,
`exceptions: []`, `unresolved_risks: []`, and:

```json
"gate_results": {
  "protected_correspondence": "pass",
  "brief_parsing_promises": "pass",
  "evidence_sufficiency": "pass",
  "source_build": "pass",
  "author_convergence": "pass"
}
```

This is the end-to-end demonstration of the fail-open predicted from static reading in
`fixtures/synthetic/large_report/findings_2026-08-29.md` (F-RELEASE-PATH-001). On the
large fixture, release blocked for an incidental reason and masked the problem. Here
nothing masked it.

## Two independent causes

**1. Release cannot see run records (F-RELEASE-PATH-001).** `plan`/`draft`/`repair` write
to `Path.cwd()/.humanvoice/runs/`; release reads `snapshot_dir/.humanvoice/runs/`. Confirmed
in this run — records landed in `.humanvoice/runs/run-20260829-1431*` while the snapshot at
`validation_results/pilot_workdir/snapshot/` contains only `manifest.json`.

**2. Repair abstention is never persisted (new — F-REPAIR-NOPERSIST-007).**
`repair_command.py:572-582` prints the abstention record to stdout and returns 2. It does
not write `unresolved_author_choice.json`, unlike the oscillation and stop paths at lines
537 and 626 which do. So an abstained repair leaves no on-disk trace.

These compound: even after fixing the path mismatch, `check_unresolved_author_choice` would
still find nothing, because repair wrote nothing. Fixing either defect alone does not close
the hole. **Both are required.**

There is also no preflight-findings gate in release at all. Release never consults preflight
output, so unresolved deterministic findings cannot block it by any path. The five
registered gates do not include one.

## F-DRAFT-EMPTY-008 — empty drafts pass the draft gate

3 of 4 drafts came back with `word_count: 0` against budgets of 60-90, 72-108, and 68-102
words. Each printed `Warning: Word count 0 outside target range` and **exited 0**, writing
a `.tex` artifact with no prose.

Word budget is a warning, not a gate (noted on the large fixture; here it is load-bearing).
A zero-word draft is not a budget-variance case, it is a missing unit, and it propagated
to release. This also caused the repair abstention — the model was handed an empty draft
and correctly reported: *"The supplied draft contains no text. Both findings reference
strings that are absent from the draft."*

Repair abstained for a sound reason. The upstream defect is that an empty draft was
accepted and passed downstream at all.

## Measurements

End-to-end wall clock: **104.4 s** (10 commands). Tokens: **11,411 in / 2,092 out**.

| step | wall clock | tokens |
|---|---|---|
| init | 37 ms | — |
| plan | 21,839 ms | 8,802 in / 758 out |
| draft[0] | 18,103 ms | 654 / 431 |
| draft[1] | 19,691 ms | 658 / 447 |
| draft[2] | 19,106 ms | 655 / 290 |
| draft[3] | 16,831 ms | 642 / 166 |
| preflight | 54 ms | — |
| preflight (2nd) | 56 ms | — |
| repair | 8,627 ms | — |
| release | 41 ms | — |

- **Deterministic command overhead is negligible**: init 37 ms, preflight ~55 ms,
  release 41 ms. Total deterministic time 188 ms, ~0.2% of wall clock. All cost is API
  latency, ~17-22 s per model invocation.
- **`latency_ms` is 0 in every runtime manifest**, as on the large fixture. This wrapper
  measures externally; without it there is no per-invocation latency data.
- **Plan consumed 8,802 input tokens** against ~650 per draft call — the plan request ID
  `msg_2f18c8a1fdd14752bc5d4192cda386b7` is 32-char hex, matching the high-input gateway
  path identified on the large fixture. Same anomaly, reproduced independently.
- **Operator time not measured.** No human was in the loop; 104.4 s is machine time. The
  contract's 180-minute operator cap is untested by this run.

## Contract comparison

| contract expectation | this run |
|---|---|
| operator time ≤ 180 min | not measured (no operator) |
| token cost ≤ $20 | 11,411 in / 2,092 out — well inside |
| unresolved findings never released | **violated** |
| deterministic gates authoritative | preflight exit 1 did not affect release |

## Assessment for v1.2 external release

The never-except conditions are the contract's central claim, and this run releases a
packet with two known unrepaired disclosure violations while reporting all gates green.
A `release_decision.json` showing five passes and `unresolved_risks: []` for this snapshot
is affirmatively misleading — worse than no gate, because it looks like verification.

Minimum fixes before external release:

1. Single canonical run-directory resolution shared by all commands (F-RELEASE-PATH-001).
2. Persist repair abstention as an unresolved marker (F-REPAIR-NOPERSIST-007).
3. Gate release on preflight findings for the snapshot — no such gate exists today.
4. Make zero-word drafts a hard failure (F-DRAFT-EMPTY-008).
5. Invert the evidence-appraisal check to an allowlist (F-EVIDENCE-003).

Items 1-3 are what let this specific packet out. These belong in Phase 2 alongside the
four known blockers; I'd treat 1-3 as higher priority than the corpus rights work, since
they concern whether the gates function at all.
