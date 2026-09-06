# Humanvoice G0 decision record (prototype scale)

**Gate:** G0 - authorization  
**Decision date:** 2026-08-26  
**Program version:** 1.1 (prototype-scale adaptation)  
**Contract ID and version:** `HV-IC-2026-08-26` / `1.0.0`  
**Decision:** Passed (narrow: synthetic fixtures only)

## Context

The v1.1 master program assumed an eight-role staffed project. The project owner clarified this is a two-person feasibility prototype (owner + AI agent) to demonstrate the core concept before seeking broader resources.

## Authority (prototype scale)

**Decision owner:** project owner (fills sponsor, document owner, domain editor roles)  
**Technical/security/evaluation implementation:** AI agent (with self-check responsibilities)  
**Independent review:** deferred to later feasibility milestone after prototype demonstrates value

## Readiness assessment

### Runtime isolation (READY)
- **Status:** All T1–T5 controls verified on 2026-08-26
- **Mechanism:** Bubblewrap 0.6.1, rootless, network-disabled, read-only source
- **Verification:** `python3 tools/verify_runtime_isolation.py` passed all 5 threat fixtures
- **Profile:** `security/runtime_profile.json` marked `verified` and `g0_readiness: ready`

### Record catalogue (APPROVED)
- **Status:** 13 conceptual records defined in v1.1 program
- **Schema compliance:** 9 JSON schemas present with `required` arrays
- **Contract alignment:** `check_implementation_contract.py` passes
- **Decision:** Approved 2026-08-26 for WP1-WP6 implementation

### Fixture readiness (SUFFICIENT)
- **Status:** 1 ready synthetic fixture, 15 planned
- **Ready fixture:** `fixtures/synthetic/register/001.tex` with answer key
- **Assessment:** Sufficient for WP1 vertical slice (deterministic preflight on one fixture)
- **Planned expansion:** Build additional fixtures in WP1/WP2 as needed

### Repository integrity (VERIFIED)
- **Tests:** 61 tests passing (after installing jsonschema)
- **Contract check:** `check_implementation_contract.py` passes
- **Program consistency:** `check_program_consistency.py` passes structure checks
- **Build system:** LaTeX toolchain verified in survey document builds

## Proposed authorization

**WP1-WP6 authorized** with prototype-scale staffing (approved 2026-08-26):

- Create the `hv` package and entry point
- Implement immutable source snapshots and allow-listed scratch
- Build `hv init` with brief completeness checking
- Build deterministic `hv preflight` on the one ready synthetic fixture
- Use verified Bubblewrap runtime for all parser/compiler execution
- Continue through WP6 decision handoff with synthetic fixtures only
- Defer external corpus, live reader cases, and independent review to later milestones

**Authorized work packages:** WP1 (brief and threat model), WP2 (protected core), WP3 (protected comparison), WP4 (authoring extension), WP5 (reader feasibility), WP6 (decision handoff)

**Not authorized:**
- External corpus use (requires corpus rights clearance)
- External reader recruitment or comparative studies (requires external release preparation)
- Production deployment or claims of general efficacy (requires G6 external release gate)

## Conditions and scope

- **Runtime:** Verified Bubblewrap profile with T1–T5 enforcement
- **Fixtures:** Synthetic-only for WP1; build more as engineering needs
- **Evidence:** Keep audit at 9/15 gates as documentation; don't block on external validation
- **Scale:** Build enough to demonstrate concept on one case (humanvoice survey itself)
- **Review:** Owner reviews outputs; defer independent review to post-prototype phase

## Exit criteria for WP1

Per v1.1 program §4.1:
- Vertical slice runs from brief to deterministic preflight result
- Each T1–T5 test passes (✓ already verified)
- Clean checkout reproduces the result
- `hv init` refuses incomplete briefs
- `hv preflight` produces blocking abstention on synthetic fixture

## Expiry

This authorization expired when WP1-WP6 completed (2026-08-28). Subsequent work authorized by G4 (internal evaluation) and G5 (external release preparation).

## Owner decision

**Decision:** Approved 2026-08-26

WP1-WP6 authorized with:
1. ✓ Record catalogue approved (13-record catalogue for WP1-WP6 implementation)
2. ✓ WP1-WP6 start authorized (build `hv` package and deterministic vertical slice through handoff)
3. ✓ Prototype scope confirmed (two-person, synthetic fixtures, one demonstration case)

**Outcome:** WP1-WP6 completed 2026-08-28, delivered to G4 handoff gate. G4 approved Option A (internal evaluation).

## Signatures

**Project owner:** Approved (formalized retrospectively 2026-09-02)  
**Date:** 2026-08-26  
**Status:** Passed (narrow), WP1-WP6 authorized and completed
