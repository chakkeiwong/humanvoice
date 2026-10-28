# Native ownership integration — 28 October 2026

Component checkpoint, 28 October 2026. Production remains 166 retained / 439 unfinished,
inactive and disabled. No provider call, production authority write, deployment,
commit or push. This is component evidence, not a release or live admission.

The complete CampaignAuthority path requires RuntimeLeaf, campaign Lease,
CampaignHistory and matching ConsumptionFloors. Native claim/settlement/hold
callbacks use owned_check without recursively reading mutable floors. Stage
ownership extends the campaign lease with both current-stage locks and forwards
the full descriptor union into the native execution context. During the stage
the floor publication callback uses provider ownership and restores the
campaign callback on every unwind. Dispatch rechecks provider ownership after
read-only floor observation.

Twenty-seven full-chain cases use real retained closure, monitor/worker/campaign/
provider leases, native grant/account/floors and committed generation zero.
Admission/control provenance and campaign preparation are explicit fixture
boundaries. They cover full descriptor forwarding, role-selected executor,
callbacks with floor reads/flock forbidden, successful native settlement,
head/transition loss and rollback, inherited/current stops, final ownership
recheck, provider loss before publication, and four interrupted claim cuts
reopened twice without a second account reservation.

Review reproduced P2: existing claim-tail repair could publish ledger metadata
after losing stage ownership. Both ordinary stage entry and cold claim-tail
repair now use shared stage_ownership and its acyclic provider check at every
tail publication. Twelve new regressions cover both routes, both stage locks,
and the receipt/ledger/complete-intent boundaries. No duplicate spending or
provider launch was demonstrated by the original finding.

Final adjacent validation: 273 cases pass in 64.55 seconds with 16 workers;
`.localresources/native-ownership-repair-20261028.xml`. Ruff passes. Independent
residual recheck passes all 12 targeted cases in 92.46 seconds with unchanged
source/test hashes. P2 is closed and the inspector has exited. Evidence:
INVENTORY_RECOVERY_NATIVE_OWNERSHIP_REVIEW_2026-10-28.md. New tests are included
in the fixed full/floors inventory. The later provider fixture helper accepts
a journal descriptor; the combined provider integration run also covers these
ownership cases (164 passes in 76.86 seconds).

Next: the private bounded provider collector and typed idempotent rejection
publisher are implemented, with bounded review and the exact native executor
gate still running. Then real authenticated control publication, public configuration/factory,
TX4–TX7, complete release binding and actual-data no-call preflight. Request
grouped host approval for exact deployment/limit/launch actions only after
the release is concrete. A new verified manuscript receipt is required before
claiming production resumed.
