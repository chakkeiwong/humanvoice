# Canonical campaign binding execution — 28 October 2026

Master 4.12 / ensemble 202. Prospective offline repair only; not live admission.

## Code trace and plan corrections

The production chain is stopped at a sealed nonpass. `Stage.run()` refuses
execution without separate campaign admission, and `CampaignAuthority` still
expects a verified configuration callback. Installed-authority capture freezes
mutable account/stage/cursor bytes and therefore cannot be used unchanged as
an ongoing spending guard. Canonical offline bootstrap existed, but public
preparation did not emit a separate exact binding suitable for later admission.

The refreshed closure plan covers these interfaces, phase-dependent cold
recovery, stale-plan repair, receipt-based progress, measured validation costs,
native multi-successor/fallback tests, combined long-document soak, reproducible
release, live inventory and the full product phase sequence. Independent plan
review found and closed two defects: a universal recovery order could claim
an uncommitted successor, and the plan omitted held-out benchmark/reproduction
prerequisites. Both are now explicit gates.

## Implemented

- `tools/inventory_recovery_v3/campaign_binding.py` derives immutable membership
  from the native campaign's fixed paths, seed, proposal, generation-zero
  preparation, grant and canonical journal, rather than accepting a caller's
  file list. A new binding requires independent unallocated native replay.
- It rejects noncanonical/symlink roots, omitted/rehashed immutable membership,
  changed source contract, foreign journal/grant, account-prefix loss and
  lost retained grant stages. Reads compare the same bytes used for parsing
  and hashing; late changes veto publication.
- Immutable bindings exclude changing execution status/account suffixes.
  Read-only inspection allows append-only account/journal/campaign growth
  without issuing dispatch authority. The binding is not a replacement for
  ongoing admission, receipt verification or monotonic runtime floors.
- Public `prepare_inventory_recovery_v3.py prepare` now produces the binding
  and includes its identity in the offline preparation report.
- Exact source release membership includes the new regression module.

## Executed validation

Initial focused run found one component fixture bypassed its mocked independent
allocation check. Added direct unallocated checks before replay and publication;
did not weaken guards. The corrected 56 component cases plus real native public
preflight passed: **57 cases**, 98.01 seconds.

The broader source-bound, exact-membership run passed **553 cases**, zero
failures/errors/skips, **16 workers**, 110.01 seconds wall time. Source, harness
and production account/grant/stages remained unchanged. The suite includes
bootstrap, campaign/history, journal, ownership, claim, installed-authority,
handover and the real native public-preflight path. Component fixtures stub
native validation; the public-preflight test uses actual native replay.

Receipt directory:
`docs/audits/2026-10-05/master-program/automatic-execution/sol-inventory-failure-first-20261026-01/recovery-policy-repair-20261027-01/campaign-binding-validation/36b9726c9a96/`.

Harness: `/tmp/humanvoice_campaign_binding_validation_20261028.py`.
Ruff passes the prospective v3 package and affected scripts/tests. This is a
focused integration receipt, not the complete release suite. That receipt is
historical after the following review repairs.

## Independent review and repairs

CB1 found actual snapshot bytes/membership were absent from reopen verification.
The new check enforces the complete prepared tree before allocation and keeps
immutable inputs afterward; only named inventory output and runtime/CLI
additions are permitted after exact account allocation. Every publication
rechecks the tree, including after native replay.

CB2 found rehashing the candidate could lower its own initial account/stage
floors. New `binding_publication.py` retains the complete binding in a separate
owned intent and publishes pending marker → binding → complete marker. Readers
require exact membership; interrupted publication resumes retained floors and
never reconstructs missing committed evidence. Real process-death tests cover
before/after each of the four publications.

All 90 focused component cases pass. The broader exact-membership suite then
passes **587 cases**, zero failures/errors/skips, 16 workers, 111.80 seconds
wall, unchanged source/harness/production authority. Receipt directory:
`docs/audits/2026-10-05/master-program/automatic-execution/sol-inventory-failure-first-20261026-01/recovery-policy-repair-20261027-01/campaign-binding-validation/1372e5f2655e/`.

Bounded independent follow-up closes CB1/CB2 in this offline slice; inspector
is closed. Review: `INVENTORY_RECOVERY_CAMPAIGN_BINDING_REVIEW_2026-10-28.md`.
A further native public-path allocation/settlement test passes in 132.22 seconds.
It binds a real prepared candidate, claims native test-account capacity, permits
generated inventory output, verifies unchanged binding after settlement and
rejects altered source. Its first run exposed a test-only cold replay count
still expecting one settled stage after adding a second; the fixture count was
updated, not production validation.

The complete fixed recovery suite **passes all 1,167 cases**, zero failures,
errors or skips, 16 workers, source/tests frozen, at
`docs/audits/2026-10-05/master-program/automatic-execution/sol-inventory-failure-first-20261026-01/recovery-policy-repair-20261027-01/validation/edcd55178baa8afb1b4c/782c502d4540/`.
Pytest time is 1694.23 seconds; end-to-end validation is 1697.43 seconds. Exact
collection/execution membership agrees, source and production authority are
unchanged, and a later read confirms the receipt still matches current source.
This completes the existing fixed test suite, not the still-unimplemented
TX3b–TX7/public integration/soak gates or live release admission.

Actual production-data no-inference preparation finished nonpass at
`docs/audits/2026-10-05/master-program/automatic-execution/sol-inventory-failure-first-20261026-01/recovery-policy-repair-20261027-01/preparation/3bdfb5ca168022e995c1/`.
It retained execution locks and wrote prospective preparation artifacts only.
After 1063.83 seconds bootstrap rejected a copied historical size-rule receipt
because native ownership initialization omitted original-profile replay scope.
Production account/grant/stages and source stayed unchanged; zero calls/writes.
Follow-on repair/evidence: `INVENTORY_RECOVERY_RECEIPT_BOOTSTRAP_EXECUTION_2026-10-28.md`.
The 1,167-case full pass above is historical after those source edits.

## Reproducibility inspection

The static-import/current-contract audit inventories 767 files: 524 untracked
and 58 modified tracked dependencies. This broader scope includes tests and
transitive helpers, so it is not comparable to the earlier 227-dependency
count. Manifest: `INVENTORY_RECOVERY_DEPENDENCY_AUDIT_2026-10-28.json`.
It does not certify dynamic dependency completeness or reproducibility.
No unrelated files were changed or staged; release must capture the exact
reviewed dependency bundle rather than claiming these checkpoints reproduce
from Git alone.

## Production and remaining work

Read-only retained state still reports job=null, last_job=job-0001 and the
historical cumulative allowance exhaustion. Production remains **166 retained /
439 unfinished**; no model calls, deployment, service start or account/grant
write occurred in this work. No new manuscript receipt is claimed.

The old master register labels E4-Q/E2-R/E5-Q/E7-RS complete and E7-RB
held_out_complete_zlb_pending. These historical labels require current identity
audits, not automatic reruns or automatic admission. Sealed records were not
rewritten.
The initial read-only identity screen matches the qualification and held-out
reproduction implementation hashes to the current product source, and all five
reproduction-extension file hashes match. This narrows the reuse investigation;
full receipts and prompt/model/configuration identities still need replay.

Next: resolve implementation findings, refresh matching evidence, then TX3b
prospective configuration/deployment admission and immutable-installation versus
mutable-runtime ownership. TX4/CP3 public cold recovery, TX5 automatic reprepare,
TX6/TX7 progress/cost bounds, native integration/soak and release remain open.
No change to approval policy, limits, frozen history, or unrelated dirty files.
