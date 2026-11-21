# Humanvoice completion and recovery checkpoint

Updated November 22, 2026. Read [AGENTS.md](../AGENTS.md) and the authoritative
[scientific master](plans/ENSEMBLE_MASTER_PROGRAM_2026-09-30.md).

**The ZLB test candidate is complete; the user accepted the revised text on
November 22, 2026 and authorized Git commit and push.**
Native release finished at **16:08:24 Asia/Shanghai on November 18, 2026**,
with status `candidate-ready`, exit code 0, and no blocking reasons.
The [acceptance record and reader files](../releases/zlb-2026-11-18/README.md)
preserve that decision separately from the frozen November 18 packet. Its
historical pending-acceptance fields remain unchanged. The source erratum has
not been applied; generalization and independent reproduction remain open.

## Completed result

- Session: `20261117T235022.984126Z-8dc3251b`.
- Native release: `cli-4aa26337d9a2409caf433ab50e4de3cc`.
- 21 accepted units; all 5,042 canonical concept mappings supported; retention 1.0.
- All 20 relationship reviews pass and have native findings records.
- 66-page manuscript and 71-page blackline; all 14 release gates pass.
- Runtime admission passes: 1,902 runtime records and 985 retained historical API
  attempts. These historical counts differ from the continuation budget.
- Manifest and all 27,214 packet files verified. No blocking or unresolved
  canonical findings. The separate source erratum remains in the packet.

Packet, relative to `.localresources/scientific-extension-20261117/`:
`working-snapshot/release/20261117T235022.984126Z-8dc3251b/`.
Reader files: `reader/revision.pdf`, `reader/comparison.pdf`,
`reader/revision/zlb_source.tex` and `reader/original/zlb_source.tex`.
Audit evidence includes real receipts, retained negatives, original charges
and `audit/evidence/rewrites/SOURCE_ERRATUM.md`. The erratum explains the source's
momentum/velocity discrepancy; it is not an applied change to the preservation candidate.

`admission-runtime-repair/final-packet-check.json` records final verification.
Manifest SHA-256: `da8a3110639a01d51fec3ec2394218275dc60d8defd9a2c9035f9a3603ea4d19`.
Reader PDF SHA-256: `27b518c59be810b1d4e7aa79e97ffb7d563a80015860e1d463794460a5915754`.
Blackline SHA-256: `9d716e6f7f73ff90a242512a897983b144b2dbf2b575055f8883cf6da8697500`.
LaTeX SHA-256: `0ccc3ad083aab9e91df3747183e10d08538d3bf5e3cb8ec127ccf97a11714334`.

## Execution status and resources

`offline-status.json` and `frontier.json` both say `CANDIDATE_READY`, with no
remaining demands. The offline command, tool session 25063, exited successfully.
Coordinator wave 11 has no pending batch. Do not restart or rerun accepted ZLB
work. The stopped live service's `status.json` and observer banner retain the
earlier blocked attempt and do not override the completed offline result.

240/277 calls allocated: 176 historical and 64 extension. There are 206 retained
responses, 36 usable extension slots and one original unused slot held. Failed
starts stay charged. Final offline repairs and admission used no new provider
calls. Deadline remains November 26, 2026, 17:03:49 Asia/Shanghai. Do not renew
limits. Human approvals remain `on-request` / `user`; sandbox restrictions and
all frozen evidence remain. No subagents were used.

## Repairs and next work

The endpoint, parser-operation and extension-receipt routing repairs are complete.
`admission_receipts.py` routes extension receipts to their original charged-slot,
launch-marker and native capture verifier. The exact failed receipt replay and
eight new routing checks pass. The payload has 93 unique focused checks, and
its source-bound review passes. Failed historical releases remain failed.

Next: capture the execution dependencies for a clean-checkout reproduction and
prepare a bounded held-out pilot. Measure scientific quality and resource use
before increasing to the approximately 1,000-page FinMarketing workload. The
source erratum remains a separate scientific decision. Independent reproduction
requires its separate allocation; do not consume the ZLB manuscript pool.

Prior recovery chronology is retained in
`admission-runtime-repair/reset-before-refresh.md` and
`admission-runtime-repair/reset-before-completion.md`. Pending/running statements
in those archives are historical.
