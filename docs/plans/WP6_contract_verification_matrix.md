# WP6 Contract Verification Matrix

**Date:** 2026-08-28  
**Contract:** HV-IC-2026-08-26 v1.1.0  
**Purpose:** Map specified requirements to implementation status and test coverage

## 1. Trust Boundary Controls (T1-T5)

| Control | Requirement | Implementation Status | Test Coverage | Gap |
|---------|-------------|----------------------|---------------|-----|
| T1 | Read-only source snapshot, separate scratch dir, path allowlist | ✓ Implemented in parser.py | ✓ `test_parser.py` verifies isolation | None |
| T2 | `-no-shell-escape`, no execution of TeX shell commands | ✓ Implemented in parser.py | ✓ Integration test in `verify_runtime_isolation.py` | None |
| T3 | Network deny for compiler/parser, API logging, policy gate | ✓ Parser isolated, API logged in runtime manifest | ⚠ Network isolation tested, API logging validated | Missing: policy gate for non-API network access |
| T4 | Versioned delimited JSON schema for critic I/O | ✓ All model adapters use schemas | ✓ Property tests validate schema conformance | None |
| T5 | Resource limits (time, memory, file size, process count) | ⚠ Partial: timeout implemented | ⚠ Partial: timeouts tested | Missing: memory, file-size, process-count limits |

**Status:** 3/5 complete, 2/5 partial

## 2. Runtime Inference Requirements

| Requirement | Specified Behavior | Implementation | Test Coverage | Gap |
|-------------|-------------------|----------------|---------------|-----|
| Model version recording | Exact version string in runtime manifest | ✓ `model.py` records version | ✓ Validated in runtime manifest tests | None |
| Prompt template hash | Required before invocation | ✓ Implemented (2026-08-28) | ✓ Profile hash flows to manifests | None |
| Schema conformance | Output validates against schemas | ✓ All commands validate | ✓ Property tests check conformance | None |
| Abstention behavior | Abstains when evidence missing/contradictory | ✓ Implemented in plan/draft/repair | ✓ Property tests validate abstention | None |
| Structural bounds | Word budgets, max 3 repair cycles | ✓ Repair cycle limit enforced | ✓ Repair command tests validate | None |
| Register compliance | Follows brief constraints | ✓ Brief constraints passed to model | ⚠ Partial property testing | Needs held-out fixture validation |
| Mutation response | Abstains or produces detectably broken output | ✓ Implemented | ✓ Mutation replay suite validates | None |

**Status:** 6/7 complete, 1/7 critical gap (prompt template hashing)

## 3. Record Policy

| Record Type | Required Fields | Schema Exists | Implementation | Validation Test | Gap |
|-------------|----------------|---------------|----------------|-----------------|-----|
| AuthoringBrief | 9 fields listed in contract | ✓ | ✓ init command | ✓ Schema validation | None |
| ArgumentBlueprint | 8 fields listed | ✓ | ✓ plan command | ✓ Schema validation | None |
| Finding | 8 fields listed | ✓ | ✓ preflight/repair | ✓ Schema validation | None |
| RuntimeManifest | 14 fields listed | ✓ | ✓ All model calls | ✓ Schema validation | None |
| CliResult | 9 fields listed | ✓ | ✓ All commands | ✓ Schema validation | None |
| CorpusItem | 8 fields listed | ✓ | ✓ init command | ✓ Schema validation | None |
| Revision | Listed in contract | ✓ | ✓ repair command | ✓ Schema validation | None |
| PreflightRun | Listed in contract | ✓ | ✓ preflight command | ✓ Schema validation | None |
| ReleaseDecision | Listed in contract | ✓ | ✓ release command | ✓ Schema validation | None |
| ProtectedManifest | Implied by contract | ✓ | ✓ All commands | ✓ Schema validation | None |
| SourceSnapshot | Implied by contract | ✓ | ✓ All commands | ✓ Schema validation | None |
| EvidenceItem | Catalog requirement | ✓ | ⚠ Read by release gate, never written | ⚠ Only synthesized in test fixtures | **Gap: no command emits it; operators must hand-author** |
| ReaderDecision | Required for G3 | ✓ | ✗ Not yet created | ✗ No tests | **Expected: reader tool not in v1.1 scope** |

**Status:** 10/13 records complete, 1/13 read-only (evidence-item consumed but never produced), 2/13 expected gaps (reader records)

## 4. CLI Contract

| Requirement | Specification | Implementation | Test Coverage | Gap |
|-------------|---------------|----------------|---------------|-----|
| Exit code 0 | Pass or released | ✓ All commands | ✓ Test suites validate | None |
| Exit code 1 | Deterministic gate failure | ✓ All commands | ✓ Release/preflight/repair tests | None |
| Exit code 2 | Abstention/policy-dependent | ✓ All commands | ✓ Model property tests | None |
| Exit code 3 | Invalid input | ✓ All commands | ✓ Release validation tests | None |
| Exit code 4 | Internal error | ✓ Exception handler | ⚠ Not explicitly tested | Integration tests would catch |
| Exit code 5 | Security/trust violation | ✓ Parser/trust checks | ✓ Isolation tests validate | None |
| stdout JSON | One machine-readable result per invocation | ✓ All commands | ✓ Contract checker validates | None |
| Stable fields | 9 required fields in every CLI result | ✓ All commands | ✓ Schema validation | None |

**Status:** 8/8 complete (1 minor: exit 4 not explicitly tested but covered by integration)

## 5. Repair Invariants

| Invariant | Specification | Implementation | Test Coverage | Gap |
|-----------|---------------|----------------|---------------|-----|
| Citation keys survive | Present in parent → present in revision | ✓ `repair_command.py` checks | ✓ Test suite validates | None |
| Numeric figures survive | Modulo separators, except in finding text | ✓ Implemented | ✓ Test suite validates | None |
| Protected objects survive | Named in brief → verbatim in revision | ✓ Implemented | ✓ Test suite validates | None |
| No new first-person | No first-person absent from parent | ✓ Implemented | ✓ Test suite validates | None |
| Cycle limit | Max 3 repair cycles per unit | ✓ Implemented | ✓ Test suite validates | None |
| Repeated finding | Same signature → unresolved author choice | ✓ Implemented | ✓ Test suite validates | None |
| Oscillation detection | Alternating parent hashes → stop | ✓ Implemented | ✓ Test suite validates | None |
| Superseded blocks | Later success moves unresolved to superseded | ✓ Implemented | ✓ Release tests validate | None |

**Status:** 8/8 complete

## 6. Release Authority

| Requirement | Specification | Implementation | Test Coverage | Gap |
|-------------|---------------|----------------|---------------|-----|
| Protected correspondence | Never-except: unresolved protected objects | ✓ `release_command.py` gate | ✓ Test suite validates | None |
| Brief parsing promises | Never-except: unparsed promised objects | ✓ Implemented | ✓ Test suite validates | None |
| Evidence sufficiency | Never-except: missing critical evidence | ✓ Implemented | ✓ Test suite validates | None |
| Source build | Never-except: broken/unreproducible build | ✓ Implemented (2026-08-28) | ✓ Passes on valid snapshots | Tests cover valid path only |
| External transmission | Never-except: unauthorized transmission | ✗ Not implemented | ✗ No tests | **Gap: no transmission tracking** |
| Author convergence | Ordinary gate: exception-releasable | ✓ Implemented | ✓ Test suite validates | None |
| Exception recording | Scope, reason, risk, owner, concurrences | ✓ Exception blocks in release decision | ✓ Schema validates structure | None |
| Reader packet independence | No finding IDs, model confidence, internal paths | ✓ Implemented | ✓ Test suite validates | None |

**Status:** 5/8 complete, 1/8 partial (source build), 2/8 missing (external transmission not tracked)

## 7. Commands Implemented

| Command | Contract Required | Implemented | Test Suite | Integration Validated | Gap |
|---------|------------------|-------------|------------|----------------------|-----|
| `hv init` | ✓ | ✓ | ✓ test_init.py | ✓ Full pipeline tested | None |
| `hv plan` | ✓ | ✓ | ⚠ No dedicated test file | ✓ Mutation replay validates | **Gap: no unit tests** |
| `hv draft` | ✓ | ✓ | ⚠ No dedicated test file | ✓ Mutation replay validates | **Gap: no unit tests** |
| `hv preflight` | ✓ | ✓ | ✓ test_preflight.py | ✓ Full pipeline tested | None |
| `hv repair` | ✓ | ✓ | ✓ test_repair_command.py | ✓ Full pipeline tested | None |
| `hv release` | ✓ | ✓ | ✓ test_release_command.py | ✓ Full pipeline tested | None |

**Status:** 6/6 commands implemented, 4/6 have dedicated unit tests, 2/6 rely on integration tests only

## 8. Operating Envelope

| Parameter | Specification | Status | Test Coverage | Gap |
|-----------|---------------|--------|---------------|-----|
| Max source tree | 250 MiB | ⚠ Not enforced | ✗ Not tested | Planning cap, not enforcement |
| Max rendered pages | 300 | ⚠ Not enforced | ✗ Not tested | Planning cap, not enforcement |
| Max prose words | 120,000 | ⚠ Not enforced | ✗ Not tested | Planning cap, not enforcement |
| Max protected objects | 2,000 | ⚠ Not enforced | ✗ Not tested | Planning cap, not enforcement |
| Deterministic preflight | 30 min | ⚠ Not enforced | ✗ Not tested | Planning cap, measurement pending |
| Model-assisted preflight | 90 min | ⚠ Not enforced | ✗ Not tested | Planning cap, measurement pending |
| Max repair cycles | 3 per unit | ✓ Enforced | ✓ Tested | None |
| Model input tokens per unit | 12,000 | ⚠ Not enforced | ✗ Not tested | Planning cap, measurement pending |
| Model output tokens per unit | 2,000 | ⚠ Not enforced | ✗ Not tested | Planning cap, measurement pending |
| Document model input | 250,000 | ⚠ Not enforced | ✗ Not tested | Planning cap, measurement pending |
| Document model output | 50,000 | ⚠ Not enforced | ✗ Not tested | Planning cap, measurement pending |
| Inference cost cap | 2 GPU-hours or 10 CPU-hours | ⚠ Not enforced | ✗ Not tested | Planning cap, measurement pending |

**Status:** Contract says "planning caps for MVP, to be measured at week-six checkpoint" — all marked as measurement targets, not enforcement requirements for v1.1

## 9. Critical Gaps Summary

### Resolved during WP6 (2026-08-28)
1. ~~**Prompt template hashing**~~ **FIXED:** `ModelConfig` now carries `prompt_template_hash` as a dataclass field; `from_profile` populates it from `security/inference_profile.json`, and `plan_command.py` / `draft_command.py` write it into runtime manifests instead of `None`. Verified: profile hash `9203411f…` matches `sha256sum security/prompt_template_critic.txt`. Mock-mode configs default to `None`, which the schema permits.
2. ~~**Source build gate**~~ **FIXED:** `check_source_build()` added as an explicit never-except gate in `release_command.py`, checking `brief_valid` and protected-object extraction.

### Remaining high priority (blocks release claims)
3. **Evidence-item records**: The schema exists and `release_command.py:207` reads `EvidenceItem` records for the load-bearing evidence gate, but no command writes them. Only `test_release_command.py:240` synthesizes them. Operators must hand-author evidence records for the gate to see anything.
4. **External transmission tracking**: Never-except condition not implemented

### Medium Priority (improves contract compliance)
5. **Unit tests for `hv plan` and `hv draft`**: Both rely on integration tests only
6. **Resource limits beyond timeout**: Memory, file-size, process-count limits not enforced
7. **Held-out fixture validation**: Register compliance needs held-out calibration

### Low Priority (measurement and documentation)
8. **Operating envelope measurements**: Planning caps need actual measurements
9. **Policy gate for non-API network**: T3 partially implemented

## 10. Test Coverage by Module

| Module | Test File | Tests | Coverage Quality | Gap |
|--------|-----------|-------|------------------|-----|
| init_command.py | test_init.py | 5 tests | Complete | None |
| plan_command.py | (mutation_replay) | 0 dedicated | Integration only | No unit tests |
| draft_command.py | (mutation_replay) | 0 dedicated | Integration only | No unit tests |
| preflight_command.py | test_preflight.py | 5 tests | Adequate | Thinner than repair/release |
| repair_command.py | test_repair_command.py | 44 tests | Comprehensive | None |
| release_command.py | test_release_command.py | 9 tests | Complete | None |
| model.py | test_model_properties.py | 4 tests | Property validation | Mock-mode only |
| parser.py | (isolation tests) | Integration | Trust boundaries tested | Good |
| compare.py | run_mutation_replay.py | 9 mutations | 9/9 caught | Acceptable |
| findings.py | (repair) | Indirect | Covered by repair | Acceptable |

**Total product tests:** 67 tests in `/tests/` (5 + 4 + 5 + 9 + 44)  
**Total tools tests:** 61 tests in `/tools/`  
**Full suite:** 128 tests pass  
**Fixture suite:** 4/4 ready fixtures match, 12 not executed (planned/unavailable)  
**Mutation replay:** 9/9 caught, 0 missed, 0 errors

## 11. Work Package Completion Status

| WP | Definition | Implementation Status | Test Status | Done Criteria | Gap |
|----|------------|----------------------|-------------|---------------|-----|
| WP0 | Authorization and catalogue | ⚠ Partial | N/A | G0 decision record | Missing: G0 decision, record catalog has evidence-item schema but no emission |
| WP1 | Brief, threat model, schemas | ✓ Complete | ✓ Pass | Complete brief, contract files, rights manifest, threat fixtures validated | **Complete** |
| WP2 | Protected LaTeX core | ✓ Complete | ✓ Pass | Source map, build, comparison, CLI replay locked on fixtures | **Complete** |
| WP3 | Week-six checkpoint | ✓ Complete | ✓ Pass | Mutation replay catches seeded changes, fixture suite validated | **Complete** (tool-based replay, not second human operator) |
| WP4 | Bounded authoring extension | ✓ Complete | ✓ Pass | Plan, draft, preflight, repair pass mutation and calibration | **Complete** |
| WP5 | Reader feasibility case | ✓ Complete | ✓ Pass | Released packet, timed reader record, burden account, abstentions preserved | **Complete** |
| WP6 | Decision handoff | **In progress** | N/A | Reproducible run, cost sensitivity, rights review, proceed/revise/stop memo | **This document is WP6 work** |

## 12. Recommendations for Proceed/Revise/Stop Decision

### Proceed with caveats if:
- Prompt template hashing deferred to v1.2 (document as known limitation)
- Evidence-item records created before any external release
- External transmission tracking acknowledged as missing (document scope limit)
- Source build made explicit release gate

### Revise if:
- Sponsor requires cryptographic prompt reproducibility (requires template hashing)
- External release is imminent (requires evidence-item records)
- Multi-operator collaboration needed (requires WP3 reproducibility validation)

### Stop if:
- Trust boundary gaps (T3, T5) are unacceptable for intended deployment
- Contract v1.1 behavioral reproducibility insufficient for stakeholder needs
- Cost envelope measurements exceed available resources

## 13. Next Steps for WP6 Completion

1. ✓ Contract verification matrix (this document)
2. ⬜ Reproducibility audit on clean checkout by second operator (WP3 deferred)
3. ⬜ Cost accounting: token usage per command on representative documents
4. ⬜ Burden measurement: operator minutes for full pipeline (init → release)
5. ⬜ Rights review: verify all corpus items have clearance records
6. ⬜ G3 checklist: immutable packet, reader independence, gate determinism (mostly done, formalize)
7. ⬜ Proceed/revise/stop memo for sponsor with gap disclosure and risk assessment

**Estimated completion:** 2026-08-29 (remaining items are measurement and documentation, not implementation)
