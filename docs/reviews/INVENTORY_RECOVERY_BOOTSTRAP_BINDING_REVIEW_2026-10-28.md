# Inventory recovery bootstrap binding review — 2026-10-28

Static, findings-only review of `campaign_initialization.py`, inherited-descriptor ownership in `campaign_history.py`, and `test_native_campaign_initialization_binds_one_journal`. Read `/home/ubuntu/AGENTS.md` and repository `AGENTS.md`. No source/test imports, execution, edits, or other agents. The coordinator reports **225 native/bootstrap/component tests passed in 110.10s and Ruff passed**; those checks were not rerun here. The earlier 448-test result predates this factory.

Scope is offline binding of already prepared generation zero through its independently verified descriptor, immutable noncyclic proposal, fixed journal and inherited consumption, and campaign seed. Missing live integration is not a finding.

## Additional finding

### P2 — Publication does not retain the verified grant binding

**Locations:** `tools/inventory_recovery_v3/campaign_initialization.py:57`, `:85`, `:118`, `:131`; verified authority comparison in `tools/inventory_recovery_v3/ancestry.py:70` and `:74`.

The native verifier checks the prepared authority against the current grant, but the factory subsequently reads the grant independently to construct the proposal. That read checks only the grant's self-identity and canonical account path. More decisively, after `resolver.import_history(observations)` returns, the remaining publication checks compare ownership, proposal contents, implementation contract and journal descriptor/extension; none reads the grant again.

**Concrete failing sequence:** start with valid preparation and grant G; let verification and inherited-history import finish; replace the grant with a different, internally identified grant G2 before the guard at line 122, leaving plan, probe, transition and proposal unchanged and ownership valid. The remaining code can publish initialization intent, seed, head, cursor and completion marker and return `OFFLINE_CAMPAIGN_INITIALIZED` with a proposal still naming G. No remaining check observes G2. This is an offline evidence-binding defect, not a claim that live execution becomes authorized. A later verifier can reject the campaign despite the earlier successful bootstrap result.

The proposed exact plan/probe/transition publication guards do not cover this separate authority artifact. **Minimal fix:** retain the grant identity verified against `prepared-authority.json`, require the proposal's grant to equal that identity, and include canonical grant path/account/self-identity plus equality to the retained identity in the guard used before every proposal, journal and seed publication. Preserve legitimate account-extension semantics rather than requiring the entire account file to remain byte-identical.

**Regressions:** after the real native verifier returns, and separately immediately after history import, replace only the grant with an internally valid differently identified record while the ownership predicate remains true. Require a binding failure before the next publication, no completed seed, no reset of retained journal evidence, and no factory account/grant writes. Also check grant removal at the same final boundary. These are proposed regressions, not executed reproductions.

## Evidence for the coordinator's already acknowledged fixes

### Prepared descriptor can diverge from the published plan

`campaign_initialization.py:85–87` accepts the verifier descriptor, rereads the plan, and constructs the proposal without comparing the reread bytes/identity to that descriptor. The seed at lines 124–128 can therefore combine the verified descriptor with a different plan identity. `admission_check` at lines 131–136 does not inspect prepared plan/probe/transition files. The intended exact-preparation publication guards and verifier-to-reread comparisons address this observed gap.

**Minimal regressions:** mutate or remove plan/probe/transition immediately after the real verifier returns and at subsequent publication boundaries. Include a changed, self-consistent plan identity and a byte-only change. Require rejection before the next durable publication. Separately make the ownership predicate return false at those boundaries and require no subsequent publication; the existing ownership guards should continue enforcing that behavior.

### Generation-zero status omits retained prepared membership

`campaign_history.py:185–203` checks prepared descriptors only for committed successors. Generation zero is inserted into `allowed`, but the later `regular_path` call at lines 236–239 neither requires its plan to exist nor checks its probe or descriptor. With an otherwise intact initialized campaign, removing generation zero or changing its plan/probe can still produce `READY` from `status()`. A direct status read does not invoke the factory's native verifier.

**Minimal fix/regressions:** include the initial prepared descriptor and its plan/probe identities and bytes in the stable status observation, with agreement to `seed.initial`. Test deletion and mutation of generation-zero plan/probe, removal of the generation-zero directory, and mismatched initial descriptor identity after initialization and after successors. Require status to reject retained-history loss without recreating evidence. The existing committed-preparation regression at `tests/test_inventory_recovery_v3_campaign_history.py:294` targets generation one, so it does not cover this case. This is the acknowledged generation-zero defect, not an additional integration finding.

## Remaining requested checks

No additional concrete defect was established in the reviewed bootstrap journal crash tails, missing retained journal handling, duplicate-descriptor lock lifetime, or proposal/seed identity dependency direction. Before a campaign seed exists, `journal.initialize()` reconciles interrupted journal publication; with a retained seed, descriptor and extension checks reject lost journal history. The inherited ownership branch duplicates the validated descriptor and closes the duplicate without explicitly unlocking the outer owner's shared lock. The proposal identity is computed before the journal and seed and does not depend on either identity.

The native test's cursor-publication interruption and idempotent rerun do not themselves exercise every journal boundary; that coverage limit is not reported as a defect. No test execution was performed during this review.
