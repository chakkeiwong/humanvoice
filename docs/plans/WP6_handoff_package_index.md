# Humanvoice v1.1 Prototype Handoff Package (G4)

**Date:** 2026-08-28  
**Contract:** HV-IC-2026-08-26 v1.1.0  
**Evaluation Lead:** Claude Opus 5  
**Decision Gate:** G4 (proceed/revise/stop)

## Executive Summary

The humanvoice prototype v1.1 is **complete for internal evaluation scope** with documented gaps for external release. The system demonstrates feasibility for governed authoring: LaTeX documents can be generated, repaired, and released under deterministic gates while preserving protected vocabulary, citations, and numerical claims. Test coverage is strong (128 tests, 100% pass), cost model is reasonable (~$3/document, ~75 min operator time), and contract compliance is adequate for internal use.

**Recommendation:** **Proceed with Option A** (internal evaluation). External release requires 4-8 weeks for rights clearance, evidence-item emission implementation, and prompt-hash TODO resolution.

## Handoff Documents (Read in Order)

### 1. Decision Memo (START HERE)
**[WP6_decision_memo.md](WP6_decision_memo.md)** — 13-page sponsor decision memo

- Executive summary with proceed/revise/stop recommendation
- Work package completion status (5/6 complete, 1/6 partial)
- Four decision options with timeline and requirements
- Risk assessment (technical, operational, governance)
- 12 questions for sponsor decision
- Deliverables checklist

**Key finding:** Prototype works for internal evaluation; external release blocked by corpus rights (5/5 items pending clearance) and implementation gaps (prompt-hash TODOs, evidence-item emission).

### 2. Contract Verification Matrix
**[WP6_contract_verification_matrix.md](WP6_contract_verification_matrix.md)** — Specified vs implemented vs tested

- Trust boundary controls (T1-T5): 3/5 complete, 2/5 partial
- Runtime inference requirements: 6/7 complete, 1/7 gap (prompt-hash TODOs)
- Record policy: 10/13 records complete, 1/13 read-only (evidence-item)
- CLI contract: 8/8 exit codes implemented and tested
- Repair invariants: 8/8 complete
- Release authority: 5/8 complete, 1/8 partial, 2/8 missing
- Test coverage by module: 67 product tests, 61 tools tests

**High priority gaps:** Prompt-hash TODOs bypass validation, evidence-item records consumed but never emitted, external transmission tracking absent, source build not explicit release gate.

### 3. Cost and Burden Analysis
**[WP6_cost_burden_analysis.md](WP6_cost_burden_analysis.md)** — Token usage and operator time

- Token cost estimates: $2.65 typical, $5.30 complex, $20 at contract cap
- Operator burden: 40-110 minutes per document (median 75 min)
- Time savings: 95-97% vs traditional governed writing (60-100 hours)
- Bottlenecks: Brief authoring (manual structured input), repair iteration (human-in-the-loop)
- Cost sensitivity: Linear in repair cycles, well-controlled by cycle limits

**Gap:** No actual measurements from production runs; projections based on contract caps and test execution. Instrumented pilot on real document recommended.

### 4. Rights Review
**[WP6_rights_review.md](WP6_rights_review.md)** — Corpus permissions and clearance

- Corpus status: 0/5 cleared, 5/5 pending (BGS, ZLB, SMEwallet, CardNPV, MacroFinance)
- Historical sources: 0/5 available for replay, 3/5 located but rights pending
- Current permitted use: "internal fixture evaluation only"
- Clearing timeline: 4-8 weeks (owner identification, permission request, consent recording)
- Impact: Internal evaluation permitted, external release blocked

**Decision matrix:** Internal proof-of-concept (immediate), academic paper with corpus data (1-4 weeks), public benchmark (4-8 weeks), external readers (8-12 weeks).

### 5. Reproducibility Checklist
**[WP6_reproducibility_checklist.md](WP6_reproducibility_checklist.md)** — What can be independently verified

- Deterministic stack: High confidence (parser, gates, comparison all tested)
- Behavioral stack: Medium confidence (property-tested, API model dependent)
- Full pipeline on real docs: Low confidence (not tested on representative corpus)
- Historical reproduction: None (sources unavailable, rights pending)
- WP3 checkpoint: Complete for tool-based replay; independent human operator not tested
- G3 checklist: Prerequisites met for behavioral reproducibility standard

**Verification commands:** Clean checkout procedure documented but not executed on independent machine.

### 6. Environment and Dependencies
**[WP6_environment_dependencies.md](WP6_environment_dependencies.md)** — Tested platform and locked versions

- Platform: Linux 6.8.0, Python 3.13.13, TeX Live 2022
- Locked dependencies: jsonschema 4.26.0, anthropic 0.42.0, pytest 9.1.1
- Installation procedure from clean checkout
- Verification commands and expected outputs
- Version compatibility notes

### 7. Work Package Completion Memos

Prior work package documentation (background context):

- **[WP1_completion_2026-08-26.md](WP1_completion_2026-08-26.md)** — Brief, threat model, schemas
- **[WP2_completion_2026-08-26.md](WP2_completion_2026-08-26.md)** — Protected LaTeX core (parser, build, comparison)
- **[WP3_completion_2026-08-26.md](WP3_completion_2026-08-26.md)** — Mutation replay (9/9 caught), G1 gate satisfied
- **[WP4_completion_2026-08-28.md](WP4_completion_2026-08-28.md)** — Bounded authoring extension (plan, draft, repair)
- **[WP5_completion_2026-08-28.md](WP5_completion_2026-08-28.md)** — Reader feasibility (release gates, packet independence)

## Quick Facts

### Test Coverage
- **Product tests:** 67 passing (init: 5, model properties: 4, preflight: 5, release: 9, repair: 44)
- **Tools tests:** 61 passing
- **Fixture suite:** 4/4 ready fixtures match, 12 not executed (planned/unavailable)
- **Mutation replay:** 9/9 mutations caught, 0 missed, 0 errors
- **Execution time:** 0.82s for product suite, ~3s total

### Implementation Status
- **CLI commands:** 6/6 implemented (init, plan, draft, preflight, repair, release)
- **Schemas:** 13 total, 10 complete, 1 read-only (evidence-item), 2 out-of-scope (reader)
- **Exit codes:** 8/8 implemented and tested (0=pass, 1=gate failure, 2=abstention, 3=invalid input, 4=internal error, 5=security violation)
- **Release gates:** 5/8 complete (protected correspondence, brief promises, evidence sufficiency, author convergence, reader-packet independence)

### Contract Compliance
- **Trust boundary:** T1-T2 complete (isolation, no shell-escape), T3-T5 partial (network, resource limits)
- **Deterministic stack:** Parser, comparison, gates all reproducible and tested
- **Behavioral stack:** Property-tested (schema, abstention, bounds, register, mutation response)
- **Record policy:** All required fields present, deterministic IDs, abstentions preserved

### Known Gaps
1. **Prompt-hash TODOs:** Commands write `None` instead of profile hash (bypasses validation)
2. **Evidence-item emission:** Schema exists, gate reads them, no command writes them
3. **External transmission tracking:** Never-except condition not implemented
4. **Source build gate:** Parser validates but not explicit release gate
5. **Corpus rights:** All 5 items pending clearance (blocks external release)
6. **WP3 human operator:** Tool-replay works; independent human reproduction untested

## Decision Options Summary

| Option | Scope | Timeline | Requirements | Outcome |
|--------|-------|----------|--------------|---------|
| **A (Recommended)** | Internal evaluation | Immediate | Accept gaps + rights limitation | Proceed 2026-08-29 |
| **B** | External release | 4-8 weeks | Clear rights, fix gaps #1-4, WP3 human | Revise to 2026-09-26 |
| **C** | Protected-core only | Immediate | Remove authoring extension | Narrow scope |
| **D** | Stop development | Immediate | None | Allocate resources elsewhere |

## Questions for Sponsor

1. **External release intent:** Is public benchmark release or academic publication a near-term goal (next 3 months)?
2. **Rights clearance authority:** Can you obtain written permission from ZLB/BGS corpus owners?
3. **Timeline preference:** Proceed now with internal scope, or wait 4-8 weeks for external-ready release?
4. **WP3 priority:** Is independent human operator reproduction required before G4, or acceptable post-G4?
5. **Gap tolerance:** Are prompt-hash TODOs, evidence-item emission gap, and transmission tracking absence acceptable for internal evaluation?

## Next Steps if Proceeding (Option A)

### Immediate (this week):
1. Sponsor reviews handoff package
2. Sponsor decides: proceed / revise / narrow / stop
3. If proceed: finalize G4 handoff, archive v1.1 milestone

### Short-term (2-4 weeks):
4. Create large synthetic document (15,000 words) for cost validation
5. Lock dependency versions (`requirements-lock.txt`)
6. Document tested TeX Live version
7. Decide: iterate toward external release or pivot scope

### Long-term (if external release):
8. Initiate ZLB rights clearance
9. Implement evidence-item emission
10. Replace prompt-hash TODOs with profile hash
11. Recruit independent operator for WP3 human reproduction
12. Execute instrumented pilot on real document

## Files Included in Package

```
docs/plans/
├── WP6_decision_memo.md                    (START HERE - 13 pages)
├── WP6_contract_verification_matrix.md     (Specified vs implemented)
├── WP6_cost_burden_analysis.md             (Token cost and operator time)
├── WP6_rights_review.md                    (Corpus permissions)
├── WP6_reproducibility_checklist.md        (Independent verification)
├── WP5_completion_2026-08-28.md            (Release gates and reader packet)
├── WP4_completion_2026-08-28.md            (Authoring extension)
├── WP3_completion_2026-08-26.md            (Mutation replay, G1 gate)
├── WP2_completion_2026-08-26.md            (Protected core)
├── WP1_completion_2026-08-26.md            (Brief and schemas)
└── humanvoice_master_program_v1.1_2026-08-26.md (Full program definition)

schemas/
├── implementation_contract.json            (Contract v1.1.0)
└── *.schema.json                          (13 JSON Schema Draft 2020-12 definitions)

tests/
├── test_init.py                           (5 tests)
├── test_model_properties.py               (4 tests)
├── test_preflight.py                      (5 tests)
├── test_release_command.py                (9 tests)
└── test_repair_command.py                 (44 tests)

tools/
├── run_fixture_suite.py                   (4/4 ready fixtures pass)
├── run_mutation_replay.py                 (9/9 mutations caught)
├── check_implementation_contract.py       (Contract assertions pass)
└── test_*.py                              (61 tests)

src/humanvoice/
├── cli.py                                 (Entry point)
├── commands/                              (6 CLI commands)
├── parser.py                              (LaTeX → protected objects)
├── compare.py                             (Protected comparison)
├── findings.py                            (Finding framework)
└── model.py                               (API model adapter)
```

## Contact and Continuity

**Prepared by:** Claude Opus 5 (evaluation lead)  
**Session context:** /home/ubuntu/workspace/humanvoice  
**Full transcript:** Available at session JSONL if needed  
**Decision requested by:** 2026-08-29  

**To continue this work:**
- Read the decision memo first ([WP6_decision_memo.md](WP6_decision_memo.md))
- Review specific analysis documents as needed
- Run test suite: `python -m pytest tests/ -v`
- Run contract checker: `python tools/check_implementation_contract.py`
- Run mutation replay: `python tools/run_mutation_replay.py`

---

**Status:** ✓ Prototype complete for internal evaluation  
**Recommendation:** ✓ Proceed with Option A (internal scope)  
**Blocker for external release:** Corpus rights (5/5 pending) + gaps #1-4  
**Timeline for external release:** 4-8 weeks if sponsor commits resources
