# Schema replay execution checkpoint — 28 October 2026

Master 4.21 / ensemble 211. Recovery and repair continue on the SSD. Production
remains unresumed at 166 retained / 439 unfinished; no new manuscript receipt,
paid gateway call, deployment, production authority write, commit or push.

## Measured failure and repair

The original exact executor gate, `5710efeb418e12455bfe/executor-9323948631d4`,
failed its 1800-second bound after 11 completed cases. The oversized successor
reached pass and allocation seal, but final repeat/accounting assertions did
not finish. Source and production authority were unchanged and cleanup ended
the owned test processes. This was not an accepted executor result.

The bounded 90-second cProfile diagnostic in
`.localresources/executor-replay-profile-20261028/summary.txt` measured 261
schema-definition checks costing 56.94 seconds, including 260 active-session
schema builds. This identifies a local verification bottleneck; it does not
establish a provider fault, native-lock deadlock, or machine-crash cause.

Prospective `schema_replay.py` reuses only successful schema-definition checks
within one operation. Every candidate schema is rebuilt; profile/base/template
contracts and actual record/schema/semantic validation still run. No account,
settlement or runtime-receipt acceptance is cached by this helper. Frozen
historical code is executed through a private function namespace and restored
after the operation. Reuse has entry/byte bounds; unsupported inputs use the
native checker.

Independent review found and closed four concrete defects in the initial
candidate: JSON list/tuple ambiguity, type-checker changes, effective registry/
resource/resolver changes, and overlapping independent context installation.
Final regressions retain native rejection oracles and restoration/recovery
checks. Final review: `INVENTORY_RECOVERY_SCHEMA_REPLAY_REVIEW_2026-10-28.md`.
The inspector is closed.

## Verification evidence

- 35 dedicated cases are part of the 115-case affected integration pass in
  14.15 seconds with 16 workers. JUnit:
  `.localresources/schema-replay-integration-residual-fixed-20261028.xml`.
- Ruff passes for the helper, integrations, test module and fixed runner.
- Diagnostic unchanged-definition checks: native 0.07918 seconds; warm reuse
  0.002397 seconds, about 33x for that operation. No end-to-end ratio claimed.
- Two intermediate executor runs were deliberately interrupted for review
  repairs: `c618909d2b9f9ac4a7a2/executor-b32b709d87c2` (6 passes in305.25s)
  and `ad790b57f0228f286c11/executor-ff905888ca5f`. Both have durable failed
  receipts, unchanged source/authority, and no cleanup error. Neither passes.
- Final reviewed-source exact executor gate PASSES:
  `408012e9b655b2e389b1/executor-0a3e19afec9f`. All 12 cases in 902.112 test
  seconds (904.13 runner seconds), 16 workers, unchanged 1800-second bound.
  Oversized case completes in 900.582 seconds, including final repeat/accounting
  checks. Source and production authority remain unchanged.
  Collected SHA: `a15b23a1a71f5b7be0fe3216df282b11f4bb7e01192c80acb43bc6fa1b715c7f`;
  executed SHA: `ae3bd96b7c8f827a59db07c68c4510379929c80a8ccccb1ac8088749f22817ef`;
  XML SHA: `64a885d4f74bf84ef19ef1acc4f56e17e6d9f9a04401c8f4b6908331f49febb7`.
- The same-source exact floor suite PASSES at
  `408012e9b655b2e389b1/floors-5dd639f5fc1e`: 861 exact cases in 732.963
  test seconds, unchanged source and production authority.
  Collected SHA: `51aa3a32765ba3a8dcff9f22d20a8960479bef2fe02f10c7648d2b19ab0f1e2a`;
  executed SHA: `91dab43015a1789475c54dd6bbe4d44f6e8436d9d89f40e7652e54d1aafbbaf9`;
  XML SHA: `f1aeaa97a9a6a90aea0a9294fdb3a055e6b7992962c6ddb2acb81e771fa5a62c`.
  Both final suite receipts are historical after the subsequent descriptor
  implementation. Source/test freeze ended after both completed.

Validation paths above are relative to
`docs/audits/2026-10-05/master-program/automatic-execution/sol-inventory-failure-first-20261026-01/recovery-policy-repair-20261027-01/validation/`.

## Next boundary

After the passing floors and executor gates, implement the reviewed ownership
units in `INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md`. Temporary diagnostic
`.localresources/ownership_fd_probe_20261028.py` confirms descriptor-specific
Linux WRITE locks distinguish exclusive/dup from shared/unlocked/fresh/replaced
descriptors without flock mutation. A separate child probe retains exclusion
after parent close until child exit. These diagnostics are not acceptance;
the required real parent-death and surviving-grandchild regressions are now
included in the descriptor unit: 37 focused and 428 adjacent cases pass.
Its independent implementation review closes DR1 after adding ordered proof
acknowledgements and fault-injected negative cases; 430 adjacent tests pass.
Broader union/lifetime composition and public admission remain open.

Then complete public admission, cold transaction repair, stale-plan handling,
receipt-based progress, bounded replay/soak, frozen release and no-call actual
preflight before grouping required host deployment/budget/launch actions.
