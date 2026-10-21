# Retained review boundary dispatch repair

Master 3.33 / ensemble 123 preserves the frozen 3.32 implementation. Held-out
reproduction execution now passes, including all 28 assembled leaf reviews.
The successor used three calls and is fully settled. Separate boundary
verification then failed with `Checkpoint cannot discard a critic or assembled
judgment`. Its generic predecessor dispatcher selected the earlier writer-only
checkpoint verifier for the newer retained-review continuation.

## Repair and regression contract

1. Add a prospective boundary adapter selected by the continuation's explicit
   version. Verify its frozen extension, exact predecessor proof, account,
   snapshot and remaining-call bound. Do not infer eligibility from an exception
   message or silently fall back after evidence validation fails. Other
   predecessors continue through their existing verifier.
2. Carry this adapter into the actual independent native boundary subprocess.
   Preflight the dispatch before expensive reproduction replay. Keep every
   native reproduction, receipt, settlement and account check. Explicitly
   prohibit provider transmission throughout verification.
3. Preserve the existing successful stage identity, ledger, seal, evaluation,
   process receipts, completed judgments and all earlier failed charges.
   Resume at its missing boundary; do not prepare or execute another model stage.
4. Regress the exact native boundary consumer, scope/evidence tampering,
   fallback isolation, exception cleanup, subprocess dispatch and controller
   stage identity. Verify the unchanged frozen upstream proof and all 203
   settlements with 16 workers. Freeze the new code, test report and sealed
   stage dependencies before supervised continuation.
5. Run the full native separate boundary on the actual retained reproduction.
   This independent consumer remains mandatory; an adapter preflight does not
   admit the reproduction. Retain timestamped verification progress and errors.

## Execution and remaining phases

`tools/run_review_boundary_20261021.py` supports refresh, freeze and verify.
`tools/supervise_review_boundary_20261021.py start` resumes the master program
under durable supervision. Both masters refresh at boundaries and stops.

After the held-out boundary passes, continue full ZLB inventory, humanization,
assembled review and release, independent ZLB reproduction and automatic final
admission. Only final acceptance of the immutable actual ZLB output needs human
content review. If ZLB split reservations exceed the current 600-slot stage
guard, implement and verify bounded batching before activating that stage.

Existing limits remain: 2,000 calls / 600 million aggregate tokens; writer
100k input / 32k output; assembled reviewer 80k / 32k; split depth three and
fourteen children per root; audits 900 seconds / $4. Eligible response-free
network failures wait 900 seconds across restarts. Work on SSD and follow
checksum-bound read-only archive aliases. Use 16 verification workers with
sequential provider calls/accounting. No semantic rerolls or repeated human
intermediate reviews are introduced.
