# Humanvoice v2 contract change record

**Decision date:** 11 September 2026  
**Decision:** replace the v1 semantic production path; preserve reusable safety and lineage infrastructure  
**Owner authorization:** production-level implementation approved 10 September 2026; v2 plan approved 11 September 2026

## Defect requiring a major version

The v1 path interpreted a finished manuscript as evidence for a newly planned, word-budgeted document. On the ZLB benchmark, a roughly 22,000-word source was implicitly planned toward 5,000 words. Substantive definitions and distinctions disappeared while exact protected-object metrics could still appear healthy. Preflight inspected the source rather than semantic correspondence in the candidate; repair retained placeholder behavior; assembly concatenated generated sections rather than revising the immutable source tree.

This is not a compatible minor correction. The input contract, semantic identity model, planner, writer, preflight, assembly, release gate, and evidence claims all change.

## Authority decision

`humanvoice_master_program_v1.2_2026-09-02.md` and its G0–G6 records are frozen historical records. They are not edited to imply that they tested v2. The pending v1 G6/external-release route is suspended. Version 2 becomes the only current production program through `humanvoice_master_program_v2.md`.

R1–R24 retain their identifiers and historical wording. Their v2 application is recorded here rather than silently rewritten. R25–R29 add the missing central invariants.

## Required interpretation of retained requirements

- R3: an explicit `hv humanize` request is the author/editor action that permits a separate child revision; the source is never edited in place.
- R5: exact-object protection complements, but cannot establish, semantic fidelity.
- R17: `AuthoringBrief` is superseded for production by `HumanizationBrief`; old records remain readable as `legacy_v1`.
- R18: a v2 teaching plan follows a frozen concept baseline and has no prose-length target.
- R19: bounded execution means semantic source units with split/resume, not content compression.
- R20: v2 never-except semantic gates supersede percentage correspondence thresholds.
- R21: the writer’s own correspondence report is evidence to inspect, never certification.
- R24: human attention is measured operationally; reader understanding is not traded against concept retention.

## Added requirements

- R25: finished-manuscript humanization as the primary production operation.
- R26: complete deterministic source coverage and a frozen, human-reviewed concept baseline before rewriting.
- R27: verified concept correspondence exactly 1.0, with merge/split/reorder lineage and unresolved uncertainty.
- R28: typed reader-specific explanation obligations with located fulfillment evidence.
- R29: accountable scaffolding disposition and patch-based, byte-preserving release.

## Migration rules

1. All v2 records use contract `HV-IC-2026-09-11`, major schema family `HV-SCHEMA-2.x`, and a v2 run identity.
2. v1 records are classified `legacy_v1`. They may be displayed or audited but never accepted as a v2 semantic record.
3. A v1 snapshot may be copied into a new v2 immutable snapshot. Its blueprint, word budgets, exact-object percentages, or release decision are not migrated into concepts or correspondence.
4. Greenfield `plan → draft` authoring remains available only through an explicit legacy/experimental surface during migration.
5. `hv humanize` becomes the sole production orchestrator after its implementation passes the applicable gate; documentation must not present an unimplemented command as working.
6. API/model output remains untrusted schema-validated data without tool authority. Each remote call requires explicit authorization in the brief and a transmission record.

## Preserved infrastructure

The migration retains immutable snapshots, hashes, run directories, runtime and transmission manifests, exact protected-object extraction, atomic child revisions, cycle/repetition/no-op/oscillation controls, source immutability, and fail-closed packet mechanics. Retention is conditional on conforming to the v2 semantic contract.

## Superseded behavior

The following cannot appear in the v2 production path: global document or section word targets; source-word retention as fidelity; 95/99-percent semantic thresholds; inline weaker model schemas; source-only semantic preflight; generated-section concatenation; placeholder repairs; automatic third-person rules; or release claims based on file existence, schema success, or protected-object counts alone.

## Evidence status at decision

The v2 behavior is specified. It is not yet implemented, test-verified, independently reproduced, or human-evidenced. Those states require V2-G1 through V2-G6 and must be reported separately.
