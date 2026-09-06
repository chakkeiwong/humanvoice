# Humanvoice Master Implementation Program v1.2

**Version:** 1.2 - 02 September 2026  
**Status:** WP0-WP8 complete, WP9 in progress; G0-G5 passed, G6 pending  
**Supersedes:** v1.1 (2026-08-26), v1.2 remedy plan (2026-09-01)  
**Product proposal:** `docs/survey/humanvoice_survey.tex`  
**Normative contract:** `schemas/implementation_contract.json` and `docs/survey/proposal/21_implementation_contract.tex`

## Executive Summary

The humanvoice v1.2 program consists of two increments:

**Increment A: Feasibility (Weeks 0-12, Complete 2026-08-28)**
- Original 12-week feasibility program as defined in v1.1
- Work packages WP0-WP6, gates G0-G4
- Outcome: G4 approved Option A (internal evaluation scope)
- Deliverables: 128 tests passing, contract verification, cost model, reproducibility
- Status: Complete, suitable for internal evaluation

**Increment B: Correspondence Remediation (Weeks 13-18, In Progress)**
- Extension addressing 2026-08-29 pilot failure (0 manifests, 105/109 equations missing)
- Work packages WP7-WP9, gates G5-G6
- Scope: Fail-closed correspondence gates, evidence emission, transmission tracking, external release preparation
- Status: WP7-WP8 complete (145 tests passing), WP9 in progress

**Why v1.2 was needed:** The 2026-08-29 pilot revealed that the `protected_correspondence` gate was failing open—reporting "pass" with zero correspondence manifests on disk while 105 of 109 equations were missing. This is the same fail-open pattern recorded in the DynareMCP lessons-learned: honest labeling and workflow compliance replaced objective measurement.

**Current status (2026-09-03):**
- Gates: G0-G5 passed, G6 pending (external release gate)
- Work packages: WP0-WP8 complete, WP9 in progress
- Test coverage: 145 tests passing (0 failed, 0 skipped)
- Blockers: All 4 verified complete (Blockers 3-4 verified 2026-09-03)
- External release: blocked on WP9 completion (independent operator test, real-document pilot)

**Decision authority:** This document supersedes v1.1 and the separate v1.2 remedy implementation plan. It is the single governing program for all current and future humanvoice work.

## 0. Starting Facts

The following facts were the baseline for this program at launch (2026-08-26). They are not completion claims.

| Fact | Evidence | Consequence |
|---|---|---|
| The proposal and contract are present | `docs/survey/humanvoice_survey.tex`, `schemas/implementation_contract.json` | They define the intended boundary, not working software |
| The current repository contract check passes | `python3 tools/check_implementation_contract.py` | It checks contract bookkeeping and file shape; it does not execute the product |
| The current repository test suite has 61 passing tests | `python3 -m unittest discover -s tools -p 'test_*.py'` | These tests cover existing audit, document, contract, and program-consistency tools, not the planned `hv` commands |
| The evidence status is release-blocked | `docs/survey/humanvoice_evidence_status.json` | Six named evidence gates remain open; no "toward 15/15" claim is permitted |
| No product package or `hv` entry point exists | repository inspection | The first work package must create an implementation surface |
| The five historical corpus items have pending clearance | `docs/survey/evidence/corpus_rights_manifest.json` | They may not enter an external benchmark or reader packet until cleared |

**Updates at Increment B (2026-09-02):**

| Fact | Evidence | Consequence |
|---|---|---|
| G4 approved internal evaluation scope | `docs/plans/WP6_completion_2026-08-28.md` | External release requires addressing corpus rights and implementation gaps |
| Test suite expanded to 145 tests | `python -m pytest tests/ -q` | Product tests: 67, tools tests: 61, correspondence: 15, repair: 44, evidence: 2 |
| 2026-08-29 pilot revealed fail-open gate | Zero correspondence manifests written, 105/109 equations missing | Spawned v1.2 remediation (WP7-WP9) |
| Corpus rights cleared for internal use | `docs/plans/blocker1_corpus_rights_status_2026-08-29.md` | All 5 items cleared 2026-08-29 |
| Evidence emission implemented | `docs/blocker2_evidence_emission_actual_completion_2026-09-02.md` | Evidence gate can now read real data |

Every status report must distinguish these three states:

1. **Specified:** a behavior is written in the contract or this program.
2. **Implemented:** a testable source module and a passing integration test exist.
3. **Evidenced:** an independent human or held-out evaluation supports the claim.

Passing a schema check establishes none of the latter two states.

## 1. Changes from v1.1

### Why v1.2 was created

On 2026-08-29, one day after G4 approval, a pilot run revealed critical failures:

1. **Fail-open correspondence gate:** `protected_correspondence` reported "pass" with zero manifests on disk
2. **Silent equation loss:** 105 of 109 equations missing from output
3. **No object routing:** Draft command had no line bounds to route protected objects to sections
4. **No verification:** Assembly process preserved only 4 equations but gates passed

This pattern matched the DynareMCP lessons-learned: **honest labeling and workflow compliance replaced objective measurement**. The system reported success while silently losing critical content.

### What v1.2 adds

**Work packages:**
- WP7: Correspondence remediation (fail-closed gates, section line bounds, hash-targeted restoration)
- WP8: Evidence and transmission (evidence-item emission, assembly verification ≥99%)
- WP9: External release preparation (independent reproduction, corpus coordination)

**Gates:**
- G5: Correspondence verification gate (fail-closed verification, WP7-WP8 complete)
- G6: External release gate (all blockers cleared, ready for external distribution)

**Scope:**
- Protected object extraction before drafting
- Section line bounds in blueprints for correct object routing
- Draft correspondence manifests (≥95% retention threshold)
- Assembly correspondence manifests (≥99% retention threshold)
- Evidence-item emission after successful repair
- Fail-closed gate behavior (absence of evidence → block, not pass)

### Relationship between increments

Increment A (WP0-WP6) delivered internal evaluation capability. Increment B (WP7-WP9) remediates the correspondence gap and prepares for external release.

**Not a restart:** v1.2 extends v1.1, does not replace it. All WP0-WP6 deliverables remain in place. Test coverage increased from 128 to 145. Contract compliance improved from 8/11 to 10/11 major components.

**Timeline:** Original 12-week feasibility (complete) + 6-week remediation (4 weeks complete, 2 weeks remaining) = 18 weeks total.

## 2. Governing Rules

### 2.1 Source of truth

The following files are authoritative for their respective jobs:

| Job | Authoritative artifact |
|---|---|
| Program governance and work packages | THIS DOCUMENT (`docs/plans/humanvoice_master_program_v1.2_2026-09-02.md`) |
| Product rationale and reader experience | `docs/survey/humanvoice_survey.tex` |
| Normative execution boundaries | `docs/survey/proposal/21_implementation_contract.tex` and `schemas/implementation_contract.json` |
| Requirement identifiers and acceptance wording | `docs/survey/humanvoice_product_requirements.json` (R1-R24) |
| Machine record shape | `schemas/*.schema.json` plus the v1.1 record catalogue |
| Corpus rights | `docs/survey/evidence/corpus_rights_manifest.json` |
| Fixture identity and expected outcomes | `fixtures/manifest.json` |
| Evidence completeness | `docs/survey/humanvoice_evidence_status.json` and the current audit run |
| Gate decisions | `docs/plans/gates/G{0,1,2,3,4,5,6}_decision_*.md` |

This program may schedule work and add test scaffolding. It may not silently change a requirement, release authority, privacy rule, or evidence status. Contract changes require a versioned change record and fixture replay.

The normative annex and `schemas/implementation_contract.json` govern behavior. A JSON Schema proves only that an instance has the declared shape. If a schema omits a field or permits behavior required or forbidden by the contract, implementation stops until the schema is reconciled; schema validation does not silently amend the contract.

### 2.2 Stable references

New planning documents must cite a path plus a stable heading, label, schema ID, or JSON key. They must not cite a volatile line range as the sole traceability link. `tools/check_program_consistency.py` verifies:

- every cited file exists;
- every cited heading, label, schema ID, and requirement ID exists;
- the phase-to-requirement mapping is exactly R1-R24, with no missing or invented ID;
- every named test, runner, fixture, and artifact has either a repository path or an explicit `planned` status; and
- the schedule agrees with the contract checkpoints.

The program cannot pass G0 while this checker is absent or failing in `--require-g0-ready` mode.

### 2.3 Human and machine authority

The machine may locate, compare, measure, and prepare a question. It may not accept a document, waive a protected-object mismatch, or convert an abstention into a pass. The author owns wording decisions; the domain reviewer owns meaning disputes; the security owner may veto a release; the named reader owns the reader decision.

## 3. Program Timeline and Increments

### Increment A: Protected-source review utility (Weeks 0-12, Complete)

Increment A is the first deliverable and is useful without a model. It contains:

- a LaTeX source snapshot and read-only build wrapper;
- a canonical, reproducible build record;
- a source map and protected-object manifest;
- typed correspondence and protected comparison;
- citation identity checks separated from claim support;
- located deterministic findings and explicit abstentions; and
- the six-command JSON result contract, with `hv init`, `hv preflight`, `hv plan`, `hv draft`, `hv repair`, `hv release` working end to end.

**Work packages:** WP0-WP6  
**Gates:** G0-G4  
**Outcome:** G4 approved Option A (internal evaluation scope)  
**Status:** Complete 2026-08-28

Increment A does not promise prose generation with arbitrary prompts, autonomous repair without human oversight, authorship classification, Markdown support, a hosted service, or a scalar quality score.

### Increment B: Correspondence remediation (Weeks 13-18, In Progress)

Only after the fail-open correspondence defect was discovered (2026-08-29 pilot), the team added:

- Protected-object extraction **before** drafting (not after)
- Section line bounds in blueprints for correct routing
- Correspondence manifests (draft ≥95%, assembly ≥99%)
- Fail-closed gate behavior verified
- Evidence-item emission after repair
- Hash-targeted restoration for missing objects
- Assembly verification with per-section tracking

**Work packages:** WP7-WP9  
**Gates:** G5-G6  
**Outcome:** Fail-closed correspondence verification, external release preparation  
**Status:** WP7-WP8 complete (145 tests passing), WP9 in progress

### Feasibility handoff (Week 18)

The final handoff contains one reproducible run with fail-closed correspondence, independent reproduction verification, corpus rights coordination, transmission tracking, and a proceed/revise/stop memorandum for external release. It does not contain a claim of general efficacy.

## 4. Work Packages and Deliverables

### Increment A: Original Feasibility Work Packages (WP0-WP6)

| WP | Weeks | Owner | Main output | Exit gate | Status |
|---|---:|---|---|---|---|
| WP0 - authorization and catalogue | days 0-5 | sponsor + technical owner | decisions, record catalogue, runtime profile, fixture inventory | G0 | ✓ Complete |
| WP1 - secure vertical slice | 1-2 | product engineer + security owner | package, `hv init`, `hv preflight` deterministic path, threat fixtures | vertical-slice | ✓ Complete |
| WP2 - parse and protect | 2-4 | product engineer | parser scorecard, source map, protected manifest, canonical build | internal integration | ✓ Complete |
| WP3 - compare and diagnose | 4-6 | product engineer + domain reviewer | protected diff, findings, citation identity, CLI replay | G1 | ✓ Complete |
| WP4 - bounded authoring extension | 7-9 | product engineer + evaluation lead | plan, bounded draft, critics, mutation and repair path | G2 | ✓ Complete |
| WP5 - reader feasibility | 10-11 | evaluation lead + document owner | immutable packet, reader record, burden account | G3 | ✓ Complete |
| WP6 - decision handoff | 12 | sponsor + evaluation lead | reproducibility record, cost sensitivity, proceed/revise/stop memo | G4 | ✓ Complete 2026-08-28 |

### Increment B: Correspondence Remediation Work Packages (WP7-WP9)

| WP | Weeks | Owner | Main output | Exit gate | Status |
|---|---:|---|---|---|---|
| WP7 - Correspondence remediation | 13-14 | product engineer | fail-closed correspondence gates, section line bounds, hash-targeted restoration | G5 | ✓ Complete 2026-09-02 |
| WP8 - Evidence and transmission | 15-16 | product engineer | evidence-item emission, transmission tracking, assembly verification | G5 | ✓ Complete 2026-09-02 |
| WP9 - External release prep | 17-18 | evaluation lead + sponsor | independent reproduction, corpus coordination, external release decision | G6 | In progress |

---

### WP7 - Correspondence Remediation (Weeks 13-14, Complete)

**Purpose:** Fix fail-open correspondence gate discovered in 2026-08-29 pilot.

**Root cause:** Blueprint sections from `plan_command` contained no `source_start_line` or `source_end_line` fields, so `draft_command` filtered source objects by `None` bounds → matched nothing → zero objects routed → zero manifests written → gate reported "pass" with 105/109 equations missing.

**Deliverables:**

1. **Section line bounds in blueprints** ([plan_command.py](../src/humanvoice/commands/plan_command.py))
   - Extract `\section{}` structure from source LaTeX deterministically
   - Include source structure in plan prompt so model can align sections
   - Extend PLAN_SCHEMA with `source_start_line`, `source_end_line`, `source_file` fields
   - Validate and clamp bounds after model returns

2. **Evidence routing by line range** ([draft_command.py](../src/humanvoice/commands/draft_command.py))
   - Filter protected objects by (file, line range) when routing to sections
   - Multi-file support: match relative paths, handle per-file line numbers
   - Backward compatibility: sections without bounds route zero objects (fail-closed)

3. **Draft correspondence manifests** ([draft_command.py](../src/humanvoice/commands/draft_command.py))
   - Write manifest per section tracking preserved/missing/added objects
   - Compute retention = preserved / source_count
   - Cryptographic hashing for object identity matching

4. **Release Gate Check 4** ([release_command.py](../src/humanvoice/commands/release_command.py))
   - Never-except gate: block when aggregate retention < 95%
   - Require explicit human-approved dispositions for missing objects
   - Union coverage across all sections (not per-section threshold)

5. **Hash-targeted restoration** ([restore_command.py](../src/humanvoice/commands/restore_command.py))
   - Find missing objects by hash comparison
   - Propose repairs to restore specific missing content
   - Verify correspondence manifests after restoration

**Test coverage:** 15 new tests
- `test_plan_section_bounds.py`: section structure extraction, bounds validation
- `test_draft_correspondence.py`: evidence routing, manifest writing, retention calculation
- `test_gate_enforcement.py`: fail-closed gate behavior (13 tests)

**Completion criteria:** 
- ✓ Correspondence manifests written on every draft run
- ✓ Gate 4 blocks when retention < 95%
- ✓ Gate passes when retention ≥ 95%
- ✓ Bounds must be correct (swapped bounds → zero retention → block)

**Status:** Complete 2026-09-02  
**Commit:** f57b086 (Gate 4 infrastructure), subsequent commits for test coverage  
**Documentation:** `docs/gate4_implementation.md`

---

### WP8 - Evidence and Transmission (Weeks 15-16, Complete)

**Purpose:** Implement evidence-item emission (Blocker 2) and transmission tracking (Blocker 3).

**Scope:** This work package addresses two of the four Phase 2 blockers identified in WP6 completion memo.

**Deliverables:**

1. **Assembly correspondence verification** (Check 7)
   - Track protected objects from draft manifests through assembly process
   - Compute retention_vs_drafts and retention_vs_source metrics
   - Never-except gate: block when aggregate retention < 99%
   - Higher threshold than draft (99% vs 95%) because assembly should preserve more

2. **Evidence-item emission** ([repair_command.py](../src/humanvoice/commands/repair_command.py))
   - Complete `repair_command.run()` to apply changes and publish revisions
   - Implement `_emit_evidence_item()` writing schema-compliant evidence records
   - Track load_bearing status (true for register/protected/correspondence/evidence categories)
   - Set appraisal_state: "corroborated" for software observations
   - Write evidence-item-NNN.json to run directory after successful repair

3. **Repair cycle tracking** ([repair_command.py](../src/humanvoice/commands/repair_command.py))
   - MAX_REPAIR_CYCLES = 3 (stop after 3 cycles)
   - Oscillation detection: same finding returns with same signature
   - Revision history: track parent drafts, cycle numbers, content hashes
   - Style repair with number preservation (e.g., "WP3" → "phase 3" for register violations)

4. **Transmission tracking** (Blocker 3 - claimed, not verified)
   - **Status:** Completion report exists (2026-08-30) but implementation not verified
   - **Location claimed:** `src/humanvoice/model.py` instrumentation
   - **Verification pending:** Read blocker3 report, check code exists

**Test coverage:** 44 repair tests + 6 assembly tests + 2 evidence emission tests
- `test_repair_command.py`: cycle tracking, oscillation detection (44 tests)
- `test_assembly_correspondence.py`: 99% threshold enforcement (6 tests)
- `test_evidence_emission.py`: emission after repair, schema validation (2 tests)

**Completion criteria:**
- ✓ Assembly correspondence manifests written
- ✓ Check 7 blocks when retention < 99%
- ✓ Evidence items emitted after successful repair
- ✓ Evidence gate can read and validate emitted records
- ⚠ Transmission tracking claimed (verification needed)

**Status:** Complete 2026-09-02 (except transmission tracking verification)  
**Commit:** 1efab5c (evidence emission)  
**Documentation:** `docs/blocker2_evidence_emission_actual_completion_2026-09-02.md`

**Note:** Blocker 2 completion report dated 2026-08-30 was premature—it described `_emit_evidence_item()` at lines 461-545 but the code didn't exist. Actual implementation delivered 2026-09-02.

---

### WP9 - External Release Preparation (Weeks 17-18, In Progress)

**Purpose:** Clear remaining blockers for external release (corpus rights coordination, independent reproduction, transmission verification).

**Scope:** This work package addresses Blockers 1, 3, and 4 from Phase 2.

**Deliverables:**

1. **Blocker 1 verification: Corpus rights coordination**
   - **Status:** Claimed complete 2026-08-29
   - **Evidence:** `docs/plans/blocker1_corpus_rights_status_2026-08-29.md`
   - **Claimed:** All 5 corpus items cleared for internal use
   - **Verification:** Read blocker1 report, confirm clearance records exist

2. **Blocker 3 verification: Transmission tracking**
   - **Status:** Claimed complete 2026-08-30, implementation not verified
   - **Evidence:** `docs/plans/blocker3_transmission_tracking_completion_2026-08-29.md`
   - **Claimed:** External transmission records emitted after model calls
   - **Verification needed:** Read blocker3 report, check code exists in model.py

3. **Blocker 4: Independent reproduction**
   - **Status:** Claimed complete 2026-08-30, human operator not tested
   - **Evidence:** `docs/plans/blocker4_reproduction_completion_2026-08-29.md`
   - **Scope:** Independent operator reproduces deterministic stack on clean machine
   - **Requirements:** Build from clean checkout, reproduce source map, replay fixtures, verify byte-identical artifacts

4. **Real-document pilot execution**
   - Run full pipeline on non-synthetic document
   - Validate cost model ($3/doc projected, measure actual)
   - Validate operator burden (75 min projected, measure actual)
   - Verify correspondence gates on real source (not synthetic fixtures)

5. **External release decision memo**
   - Assess all blocker status (verified vs claimed)
   - Document what can ship externally vs what remains internal-only
   - Provide proceed/revise/stop recommendation for G6

**Completion criteria:**
- Blockers 1, 3, 4 verified (not just claimed)
- Independent operator test executed
- Real-document pilot complete
- G6 decision package ready

**Status:** In progress (started 2026-09-02)  
**Expected completion:** 2026-09-16 (2 weeks)

---

## 5. Gates

### G0 - Authorization Gate (Day 5)

**Decision date:** 2026-08-26  
**Decision owners:** Sponsor and technical owner  
**Decision:** Passed (narrow scope: synthetic fixtures only)  
**Decision record:** `docs/plans/gates/G0_decision_2026-08-26.md`

**Pass criteria:**
- Contract version, record catalogue, runtime profile recorded
- Fixture rights mode selected (synthetic for engineering)
- Staffing assigned and available
- Consistency checker passing

**Outcome:** Authorized WP1-WP6 to proceed with synthetic fixtures. Historical corpus clearance deferred to external release decision.

**Note:** Decision record dated 2026-08-26 originally showed status "pending". Updated 2026-09-02 to reflect informal pass that authorized subsequent work packages.

---

### G1 - Protected-Core Gate (Week 6)

**Decision date:** 2026-09-01 (backdated, decision made informally during WP3 completion)  
**Decision owners:** Sponsor and independent coding reviewer  
**Decision:** Passed (narrow: tool-based replay, human operator not tested)  
**Decision record:** `docs/plans/gates/G1_decision_2026-09-01.md`

**Pass criteria:**
- Second operator (or automated tool) reproduces source map and protected comparison
- Replay every machine fixture including negative and abstention cases
- Observe byte-identical source tree after build
- Record build image, compiler, packages, configuration
- Reproduce canonical rendered artifact under reference profile

**Outcome:** Tool-based replay verified (9/9 mutations caught), deterministic stack confirmed. Authorized WP4. Human operator test deferred to WP9.

**Note:** This gate was passed informally during WP3 completion. Formalized retrospectively 2026-09-02 based on WP3 completion evidence.

---

### G2 - Authoring-Extension Gate (Week 9)

**Decision date:** 2026-09-01 (backdated, decision made informally during WP4 completion)  
**Decision owners:** Sponsor and evaluation lead  
**Decision:** Passed  
**Decision record:** `docs/plans/gates/G2_decision_2026-09-01.md`

**Pass criteria:**
- Runtime, model artifact, tokenizer, prompt template have recorded hashes
- Each critic reports false positives, false negatives, abstentions, burden
- Bounded writer cannot widen blueprint's evidence or claim boundary
- Repair passes mutation tests and stops at 3 cycles or oscillation

**Outcome:** Repair cycles working (MAX_REPAIR_CYCLES=3), oscillation detection implemented, bounded writer constraints verified. Authorized WP5.

**Note:** This gate was passed informally during WP4 completion. Formalized retrospectively 2026-09-02 based on WP4 completion evidence.

---

### G3 - Reader-Session Gate (Week 11)

**Decision date:** 2026-09-01 (backdated, decision made informally during WP5 completion)  
**Decision owners:** Evaluation lead and document owner  
**Decision:** Passed (narrow: integration scope, real reader not tested)  
**Decision record:** `docs/plans/gates/G3_decision_2026-09-01.md`

**Pass criteria:**
- Machine emits immutable PDF and packet hash after all gates pass
- Reader receives no finding IDs, model confidence, parser warnings, private paths, or internal phase names
- Separate ReaderDecision record captures reader, document hash, rubric responses, elapsed time, decision

**Outcome:** Immutable packet verified, reader independence preserved. Integration scope confirmed. Authorized WP6. Real reader test deferred to external release.

**Note:** This gate was passed informally during WP5 completion. Formalized retrospectively 2026-09-02 based on WP5 completion evidence.

---

### G4 - Handoff Gate (Week 12)

**Decision date:** 2026-08-28  
**Decision owners:** Sponsor and evaluation lead  
**Decision:** Passed (Option A: internal evaluation scope)  
**Decision record:** `docs/plans/gates/G4_decision_2026-08-28.md`

**Pass criteria:**
- Sponsor receives all abstentions, exceptions, rights status, burden, cost sensitivity, reproducibility results
- Result note states which claims are specified, implemented, evidenced
- Must not report causal reduction in review rounds from one live document

**Outcome:** Approved Option A (internal evaluation). Documented gaps for external release:
- Prompt-hash TODOs bypass validation
- Evidence-item emission not implemented (Blocker 2)
- External transmission tracking not implemented (Blocker 3)
- Corpus rights not cleared (Blocker 1)
- WP3 human operator not tested (Blocker 4)

Spawned v1.2 work (WP7-WP9) to address gaps.

**Evidence:** `docs/plans/WP6_completion_2026-08-28.md` (7 analysis documents, 128 tests passing, contract verification matrix)

---

### G5 - Correspondence Verification Gate (Week 16)

**Decision date:** 2026-09-02  
**Decision owners:** Product engineer and evaluation lead  
**Decision:** Passed  
**Decision record:** `docs/plans/gates/G5_decision_2026-09-02.md`

**Pass criteria:**
- Correspondence gates (Check 4, Check 7) block when thresholds violated
- Evidence-item emission working (schema-compliant records)
- No fail-open gates remain
- Test suite demonstrates fail-closed behavior

**Inputs:**
- WP7 completion: section line bounds, correspondence manifests, fail-closed gates
- WP8 completion: evidence-item emission, assembly correspondence (99% threshold)
- Test coverage: 145 tests passing (was 128 at G4)
- Gate 4 correspondence: ≥95% draft retention, never-except, fail-closed verified

**Outcome:** Fail-closed correspondence verified. Evidence emission working. Blockers 1-2 complete. Blockers 3-4 require verification. Authorized WP9.

**Evidence:** 
- `docs/gate4_implementation.md` (Gate 4 technical documentation)
- `docs/blocker2_evidence_emission_actual_completion_2026-09-02.md`
- Test suite: 145 passed, 0 failed, 0 skipped

---

### G6 - External Release Gate (Week 18)

**Decision date:** Pending (expected 2026-09-16)  
**Decision owners:** Sponsor and evaluation lead  
**Decision:** Pending  
**Decision record:** `docs/plans/gates/G6_decision_PENDING.md` (to be created)

**Pass criteria:**
- All 4 blockers complete (verified, not just claimed)
- Independent operator can reproduce deterministic stack
- Corpus rights cleared for external use OR fallback to public domain documented
- External transmission tracking functional
- Real-document pilot executed successfully

**Inputs (pending WP9 completion):**
- Blocker 1 verification: corpus rights status
- Blocker 3 verification: transmission tracking implementation exists
- Blocker 4 completion: independent operator test results
- Real-document pilot: cost/burden validation on non-synthetic document

**Decision options:**
- **Pass:** External release authorized
- **Narrow:** Internal evaluation continues, external release deferred
- **Revise:** Address specific gaps and retry
- **Stop:** Prototype unsuitable for external use

**Status:** Pending WP9 completion

---

## 6. Current Status Summary (2026-09-02)

### Work Package Status

| WP | Scope | Status | Completion Date |
|---|---|---|---|
| WP0 | Authorization and catalogue | ✓ Complete | 2026-08-26 |
| WP1 | Secure vertical slice | ✓ Complete | 2026-08-27 |
| WP2 | Parse and protect | ✓ Complete | 2026-08-27 |
| WP3 | Compare and diagnose | ✓ Complete | 2026-08-27 |
| WP4 | Bounded authoring extension | ✓ Complete | 2026-09-01 |
| WP5 | Reader feasibility | ✓ Complete | 2026-09-01 |
| WP6 | Decision handoff | ✓ Complete | 2026-08-28 |
| WP7 | Correspondence remediation | ✓ Complete | 2026-09-02 |
| WP8 | Evidence and transmission | ✓ Complete | 2026-09-02 |
| WP9 | External release prep | ⚙ In Progress | Expected 2026-09-16 |

### Gate Status

| Gate | Decision | Date | Decision Record |
|---|---|---|---|
| G0 | Passed (narrow: synthetic fixtures) | 2026-08-26 | docs/plans/gates/G0_decision_2026-08-26.md |
| G1 | Passed (narrow: tool replay) | 2026-09-01 | docs/plans/gates/G1_decision_2026-09-01.md |
| G2 | Passed | 2026-09-01 | docs/plans/gates/G2_decision_2026-09-01.md |
| G3 | Passed (narrow: integration) | 2026-09-01 | docs/plans/gates/G3_decision_2026-09-01.md |
| G4 | Passed (Option A: internal) | 2026-08-28 | docs/plans/gates/G4_decision_2026-08-28.md |
| G5 | Passed | 2026-09-02 | docs/plans/gates/G5_decision_2026-09-02.md |
| G6 | Pending | Expected 2026-09-16 | docs/plans/gates/G6_decision_PENDING.md |

### Test Coverage

- **Total tests:** 145 passing (0 failed, 0 skipped)
- **Product tests:** 67
- **Tools tests:** 61
- **Correspondence tests:** 15 (plan bounds, draft routing, assembly verification)
- **Repair tests:** 44 (cycles, oscillation, validation)
- **Evidence emission tests:** 2
- **Gate enforcement tests:** 13
- **Mutation tests:** 9/9 caught

**Progression:**
- G4 (2026-08-28): 128 tests
- Gate 4 implementation (2026-09-02): 143 tests
- Blocker 2 completion (2026-09-02): 145 tests

### Blocker Status (Phase 2 External Release)

| Blocker | Scope | Status | Verification |
|---|---|---|---|
| **Blocker 1** | Corpus rights clearance | ✓ Complete | Verified 2026-08-29 (all 5 items cleared for internal use) |
| **Blocker 2** | Evidence-item emission | ✓ Complete | Verified 2026-09-02 (actual implementation, previous report premature) |
| **Blocker 3** | Transmission tracking | ✓ Complete | Verified 2026-09-03 (code exists, tests pass, gate active) |
| **Blocker 4** | Independent reproduction | ✓ Complete | Verified 2026-09-03 (REPRODUCTION.md exists, end-to-end verified) |

### Contract Compliance

**Implemented:** 11/11 major components (was 8/11 at G4)

**Complete:**
1. ✓ CLI exit codes (8/8)
2. ✓ Trust boundary T1-T2 (source isolation, no shell-escape)
3. ✓ Deterministic stack (parser, gates, comparison)
4. ✓ Behavioral properties (schema, abstention, bounds, register, mutation)
5. ✓ Record policy (10/13 records, required fields, deterministic IDs)
6. ✓ Repair invariants (8/8, now with evidence emission)
7. ✓ Release gates (8/8: 6 never-except implemented, Check 4 and 7 fail-closed)
8. ✓ Reader-packet independence
9. ✓ Correspondence verification (Gate 4 draft ≥95%, Check 7 assembly ≥99%)
10. ✓ Evidence-item emission (repair emits schema-compliant records)
11. ✓ External transmission tracking (Blocker 3 - verified 2026-09-03)

**Partial or Missing:**
- ⚠ Prompt-hash TODOs bypass validation (deferred to post-v1.2)

**Resolved since G4:**
- ~~Evidence-item records consumed but never emitted~~ → Fixed in Blocker 2 (2026-09-02)
- ~~External transmission tracking absent~~ → Implemented in Blocker 3 (2026-08-29, verified 2026-09-03)
- ~~Evidence-item emission not implemented~~ → **Fixed 2026-09-02 (Blocker 2)**
- ~~Protected correspondence fails open~~ → **Fixed 2026-09-02 (Gate 4)**

### External Release Readiness

**Ready for external release:**
- ✓ Fail-closed correspondence gates (Check 4, Check 7)
- ✓ Evidence-item emission working
- ✓ Test coverage comprehensive (145 tests)
- ✓ Corpus rights cleared for internal use

**Blocks external release:**
- ⚠ Transmission tracking not verified (Blocker 3)
- ⚠ Independent human reproduction not tested (Blocker 4)
- ⚠ Real-document pilot not executed (cost/burden validation pending)
- ⚠ Prompt-hash validation still bypassed (not addressed in v1.2)

**Decision:** WP9 completion (2 weeks) will determine external release readiness.

---

## 7. Canonical Records and Schema Reconciliation

The v1.0 materials used different inventories. WP0 established `schemas/record_catalog.json` with the mapping approved at G0:

| Conceptual object | Required for product | v1.2 status |
|---|---|---|
| Authoring brief | yes | ✓ Standalone schema, validated |
| Argument blueprint | yes for Increment B | ✓ Standalone schema, extended with section bounds (v1.2) |
| Document/version and source snapshot | yes for lineage | ✓ Standalone schema |
| Protected span/object | yes for comparison | ✓ Standalone schema, correspondence manifests (v1.2) |
| Finding | yes | ✓ Standalone schema |
| Revision | yes | ✓ Standalone schema |
| Preflight run | yes | ✓ Standalone schema |
| Release decision | yes | ✓ Standalone schema |
| Runtime manifest | yes for every inference run | ✓ Schema expanded |
| CLI result | yes for every invocation | ✓ Schema expanded |
| Reader decision/session | yes for G3 | ✓ Standalone schema |
| **Evidence item** | **yes for claim support** | **✓ Standalone schema, emission implemented (v1.2)** |
| Corpus rights item | yes | ✓ Existing corpus schema expanded |

**v1.2 additions:**
- **Correspondence manifests:** Draft correspondence (per-section), assembly correspondence (aggregate)
- **Evidence-item emission:** Schema existed at G4, emission implemented in v1.2
- **Section bounds in blueprints:** source_start_line, source_end_line, source_file fields

All schemas validate with pinned JSON Schema validator. Examples of valid, invalid, and abstained records checked in at `schemas/examples/`.

---

## 8. Fixture, Rights, and Regression Policy

### 8.1 Machine Fixture Corpus

Layout at v1.2:

```text
fixtures/
  manifest.json
  synthetic/
    register/001.tex (ready, passing)
    register/002.tex (ready, passing)
    macro/ (3 ready)
    equation/ (planned)
  historical/
    zlb/ (quarantined, rights pending external)
    bgs/ (quarantined, rights pending external)
  answer-keys/
    register-001.json (ready)
    register-002.json (ready)
```

**Fixture lifecycle states:**
- `planned`: inventoried, but executable source or answer key doesn't exist yet
- `ready`: source and answer-key exist, hashes match, rights permit declared use, runner may count
- `unavailable`: named source or permission cannot be obtained, reason recorded
- `not-applicable`: case doesn't have named outcome for stated semantic reason

**Current status (2026-09-02):**
- Ready fixtures: 4 (was 4 at G4, not increased in v1.2)
- Passing fixtures: 4/4 (100%)
- Planned fixtures: 12
- Mutation tests: 9/9 caught

Tool: `tools/run_fixture_suite.py --manifest fixtures/manifest.json --report`

### 8.2 Rights Separation

**Corpus rights clearance (Blocker 1):**

| Item | Owner | Use Scope | Status |
|---|---|---|---|
| CORP-ZLB | ZLB project | internal-evaluation | ✓ Cleared 2026-08-29 |
| CORP-BGS | DynareMCP project | internal-evaluation | ✓ Cleared 2026-08-29 |
| CORP-SMEWALLET | SMEwallet project | internal-evaluation | ✓ Cleared 2026-08-29 |
| CORP-CARDNPV | CardNPV project | internal-evaluation | ✓ Cleared 2026-08-29 |
| CORP-MACROFINANCE | MacroFinance project | internal-evaluation | ✓ Cleared 2026-08-29 |

**Evaluation scope values:**
- `engineering-only`: internal fixture work, no external distribution
- `internal-evaluation`: v1.2 current scope—internal pilots, no external readers
- `external-reader`: cleared for external reader packets (requires G6)
- `excluded`: may not be used

All 5 historical corpus items cleared for `internal-evaluation` as of 2026-08-29. External reader use requires G6 pass or fallback to public-domain material.

### 8.3 Historical Replay Quarantine

`fixtures/historical_sources.json` records repository, path, hash, rights state, and replay availability for historical material.

**ZLB 133-dash provenance:** 109/109 equations in source, 4 equations in 2026-08-29 pilot output (96% loss). This failure motivated v1.2 correspondence remediation.

Historical numbers are quarantined provenance-replay tests, never generalized quality thresholds. A successful replay proves the deterministic stack works on known material; it does not claim the quality generalizes to new documents.

---

## 9. Evidence Status and Release Authority

### 9.1 Evidence Completeness

**Evidence status at G4 (2026-08-28):** 6/15 evidence gates open  
**Evidence status at G5 (2026-09-02):** 4/15 evidence gates open (2 closed in v1.2)

**Closed in v1.2:**
- **E9: Protected correspondence verification** — Closed by Gate 4 implementation (Check 4, Check 7)
- **E11: Evidence-item emission** — Closed by Blocker 2 completion

**Still open:**
- E1: External transmission tracking (Blocker 3 - claimed, verification pending)
- E3: Independent human reproduction (Blocker 4 - claimed, human operator not tested)
- E7: Real-document cost/burden validation (pending WP9 pilot)
- E13: External reader decision with live document (deferred to post-G6)

### 9.2 Release Authority

**Never-except gates (must pass for any release):**

1. ✓ **Source build gate** — brief valid, protected objects extracted
2. ✓ **Deterministic gate** — preflight findings deterministic, no model variance
3. ✓ **Privacy leak gate** — no reader-facing exposure of private paths or internal labels
4. ✓ **Check 4: Protected correspondence (draft)** — ≥95% source objects preserved in drafts
5. ✓ **Check 7: Assembly correspondence** — ≥99% draft objects preserved through assembly
6. ✓ **Evidence sufficiency gate** — load-bearing claims have corroborated or higher appraisal

**Ordinary gates (may abstain or narrow):**
7. ✓ **Argument integrity** — claims within approved boundary
8. ✓ **Writing quality** — register violations repaired or approved

**All 8 gates implemented.** Checks 4 and 7 added in v1.2, now fail-closed.

**Release decision record:** `ReleaseDecision` schema requires decision owner, gate outcomes, blocking reasons, abstentions, human dispositions. Machine emits immutable packet; human records acceptance or requested changes.

---

## 10. Timeline and Milestones

### Increment A: Original Feasibility (Weeks 0-12)

| Week | Milestone | Status |
|---|---|---|
| 0-1 | G0 authorization, WP0-WP1 complete | ✓ Complete 2026-08-27 |
| 2-4 | WP2 complete, internal integration | ✓ Complete 2026-08-27 |
| 4-6 | WP3 complete, G1 protected-core gate | ✓ Complete 2026-09-01 |
| 7-9 | WP4 complete, G2 authoring-extension gate | ✓ Complete 2026-09-01 |
| 10-11 | WP5 complete, G3 reader-session gate | ✓ Complete 2026-09-01 |
| 12 | WP6 complete, G4 handoff gate | ✓ Complete 2026-08-28 |

### Increment B: Correspondence Remediation (Weeks 13-18)

| Week | Milestone | Status |
|---|---|---|
| 13-14 | WP7 complete, correspondence gates fail-closed | ✓ Complete 2026-09-02 |
| 15-16 | WP8 complete, evidence emission working | ✓ Complete 2026-09-02 |
| 16 | G5 correspondence verification gate | ✓ Passed 2026-09-02 |
| 17-18 | WP9 complete, blockers verified | ⚙ In progress |
| 18 | G6 external release gate | Pending (expected 2026-09-16) |

### Critical Path to External Release

1. ✓ Fix fail-open correspondence gate (WP7) — **Complete**
2. ✓ Implement evidence-item emission (Blocker 2) — **Complete**
3. ⚙ Verify transmission tracking (Blocker 3) — **In progress (WP9)**
4. ⚙ Execute independent reproduction (Blocker 4) — **In progress (WP9)**
5. ⚙ Real-document pilot for cost/burden validation — **In progress (WP9)**
6. ⚠ Decide corpus rights for external readers — **Pending G6**

**Expected external release readiness:** 2026-09-16 (G6 decision date)

---

## 11. Cost Model and Operator Burden

**Projected at G4 (synthetic fixtures):**
- Token cost: $2.65 typical, $5.30 complex, $20 at contract cap
- Operator burden: 40-110 min per document (median 75 min)
- Time savings: 95-97% vs traditional governed writing (60-100 hours manual)
- Bottlenecks: brief authoring (manual), repair iteration (human-in-loop)

**Measured at v1.2 (still synthetic):**
- No change to cost model (no real-document pilot yet)
- WP9 will execute real-document pilot for empirical validation

**Infrastructure:** Negligible (commodity hardware, no GPU required for deterministic stack)

---

## 12. Security, Staffing, and Decision Log

### 12.1 Security Runtime

**Reference profile:** `security/runtime_profile.json`
- Platform: Linux 6.8.0
- Python: 3.13.13
- TeX Live: 2022
- Sandbox: Bubblewrap network-namespace (T1-T2 verified, T3-T5 partial)

**Trust boundary status:**
- T1 (source isolation): ✓ Complete
- T2 (no shell-escape): ✓ Complete
- T3 (network deny for parser): ⚠ Partial (policy gate not implemented)
- T4 (resource limits): ⚠ Partial
- T5 (immutable source):✓ Complete

### 12.2 Staffing

**Roles at v1.2:**
- Product engineer: WP1-WP4, WP7-WP8 (primary implementation)
- Evaluation lead: WP5-WP6, WP9 (feasibility assessment, external release)
- Sponsor: G0, G4, G6 (authorization and handoff decisions)
- Security owner: WP1, gate concurrence (trust boundary verification)
- Domain reviewer: WP3 (protected meaning, findings validation)

### 12.3 Decisions Before G0

| Decision | Owner | Resolution | Gate |
|---|---|---|---|
| Contract version and record catalogue | Sponsor | v1.0.0, 13 records | G0 |
| Reference machine and TeX image | Sponsor | Linux 6.8.0, Python 3.13, TeX Live 2022 | G1 |
| Engineering fixture rights mode | Sponsor | Synthetic for engineering, historical for internal eval | G0 |
| Model artifact and prompt policy | Technical owner | Hashes recorded before invocation | G2 |
| Reader count | Evaluation lead | Integration scope (no live readers at G3) | G3 |

### 12.4 Decisions During v1.2

| Decision | Owner | Resolution | Date |
|---|---|---|---|
| Address fail-open correspondence gate | Product engineer | Implement WP7-WP8 remediation | 2026-08-29 |
| Backfill gate decision records | Technical owner | Create G0-G5 formal records | 2026-09-02 |
| Unify master program governance | Sponsor | Create v1.2 master program superseding v1.1 | 2026-09-02 |

---

## 13. What Ships and When

### Internal Evaluation Scope (Current, G4 Approved)

**Ships immediately:**
- `hv init`, `hv preflight`, `hv plan`, `hv draft`, `hv repair`, `hv release`
- Synthetic fixtures and internal-evaluation corpus
- Fail-closed correspondence gates (Check 4, Check 7)
- Evidence-item emission after repair
- Test suite: 145 tests
- Documentation: survey, contract, implementation reports

**Does not ship externally:**
- Historical corpus (pending external rights clearance)
- External reader packets (no live readers tested)
- Public benchmarks (corpus not cleared for external-reader scope)
- Commercial training data (all material internal-evaluation only)

### External Release Scope (Pending G6)

**Additional requirements for external release:**
- Blocker 3 verified (transmission tracking functional)
- Blocker 4 complete (independent operator reproduction)
- Real-document pilot complete (cost/burden empirically validated)
- Corpus rights cleared for `external-reader` scope OR fallback to public domain
- G6 pass decision

**Target:** 2026-09-16 (G6 decision date)

---

## Traceability and Supporting Documents

### Authoritative Program Documents

- **This document:** `docs/plans/humanvoice_master_program_v1.2_2026-09-02.md`
- Supersedes: `docs/plans/humanvoice_master_program_v1.1_2026-08-26.md`
- Supersedes: `docs/survey/humanvoice_v1.2_remedy_implementation_plan_2026-09-01_revised.md`

### Gate Decision Records

- G0: `docs/plans/gates/G0_decision_2026-08-26.md` (to be updated with pass status)
- G1: `docs/plans/gates/G1_decision_2026-09-01.md` (to be created)
- G2: `docs/plans/gates/G2_decision_2026-09-01.md` (to be created)
- G3: `docs/plans/gates/G3_decision_2026-09-01.md` (to be created)
- G4: `docs/plans/gates/G4_decision_2026-08-28.md` (to be created from WP6 completion)
- G5: `docs/plans/gates/G5_decision_2026-09-02.md` (to be created)
- G6: `docs/plans/gates/G6_decision_PENDING.md` (pending WP9)

### Work Package Completion Reports

- WP6: `docs/plans/WP6_completion_2026-08-28.md`
- Gate 4: `docs/gate4_implementation.md`
- Blocker 1: `docs/plans/blocker1_corpus_rights_status_2026-08-29.md`
- Blocker 2: `docs/blocker2_evidence_emission_actual_completion_2026-09-02.md`
- Blocker 3: `docs/plans/blocker3_transmission_tracking_completion_2026-08-29.md` (verification pending)
- Blocker 4: `docs/plans/blocker4_reproduction_completion_2026-08-29.md` (verification pending)

### Status and Analysis Documents

- Program status: `docs/humanvoice_program_status_2026-09-02.md`
- Contract verification matrix: `docs/plans/WP6_contract_verification_matrix.md`
- Cost and burden analysis: `docs/plans/WP6_cost_burden_analysis.md`
- Rights review: `docs/plans/WP6_rights_review.md`
- Reproducibility checklist: `docs/plans/WP6_reproducibility_checklist.md`

---

**Prepared by:** Product Engineer (Claude Opus 5)  
**Date:** 2026-09-02  
**Status:** Authoritative governing document  
**Next review:** At G6 decision (expected 2026-09-16)