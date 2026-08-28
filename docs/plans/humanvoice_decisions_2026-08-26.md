# Humanvoice WP0 decision record

**Status:** WP0 artifacts executed; G0 pending
**Program:** `docs/plans/humanvoice_master_program_v1.1_2026-08-26.md`
**Contract:** `schemas/implementation_contract.json`, version 1.0.0

The user authorized execution of WP0 on 26 August 2026. That authorization does
not pass G0 or authorize WP1. The records below separate technical defaults from
decisions that still require a named human owner.

| Decision | Working value | State | G0 consequence |
|---|---|---|---|
| Investment boundary | Build the protected core first; keep the authoring extension conditional on G1 | accepted program rule | none |
| Record inventory | Use the 13-object catalogue in `schemas/record_catalog.json`; use a standalone protected manifest with nested protected objects | recorded technical default | sponsor concurrence required |
| Schema policy | Reject unknown top-level fields; preserve additions only under `extensions`; the normative contract prevails over a conflicting schema | implemented for current schemas | none after checks pass |
| Runtime | Bubblewrap 0.6.1 with read-only mounts, no network, no capabilities, and explicit resource limits | selected but unverified | blocks G0 because this host denied the network namespace test |
| Engineering fixtures | Start with project-owned synthetic cases; count only `ready` rows with real files and hashes | accepted program rule | one register case is ready; remaining fixture construction is WP1 work |
| Historical evidence | Use only as provenance replay; absent snapshots or permissions are `unavailable` | accepted program rule | does not block deterministic engineering |
| Model policy | No model invocation until artifact, tokenizer, prompt, sampling, seed, hardware, and output hashes are recorded | accepted program rule | blocks model-dependent WP4 work, not WP1 |
| Live case | Select from a prespecified eligible intake pool and record the incumbent process before running Humanvoice | unresolved | blocks G3, not WP1 |
| Readers | Target two independent readers; one reader establishes integration only | accepted program rule | staffing still required |
| Outcomes | Acceptance by horizon and cumulative reader time are co-primary in a later comparative study; rounds are secondary | accepted program rule | none |
| Staffing | Use the roles and separation rules in `humanvoice_staffing_plan_2026-08-26.json` | unassigned | blocks G0 |

## Current G0 blockers

1. Assign the decision-owning and delivery roles with credible availability.
2. Verify T1--T5 under the selected runtime, or select and pin a runtime that can
   enforce the same boundary on the supported host.
3. Obtain sponsor concurrence on the record catalogue and the permitted fixture
   rights mode.
4. Choose the Increment A live-case path or explicitly narrow G0 to synthetic
   fixtures and a core-only integration case.
