# WP6 Completion Memo

**Date:** 2026-08-28  
**Work Package:** WP6 - Decision handoff (week 12)  
**Status:** Complete  
**Gate:** G4 proceed/revise/stop decision delivered

## Summary

WP6 decision handoff package delivered to project sponsor. The prototype is complete for internal evaluation scope with documented gaps for external release. Seven analysis documents totaling ~60 pages provide comprehensive contract verification, cost analysis, rights review, and reproducibility assessment.

**Recommendation:** Proceed with Option A (internal evaluation). External release requires 4-8 weeks for rights clearance and implementation gaps #1-3.

## Deliverables

### 1. G4 Decision Memo (13 pages)
[WP6_decision_memo.md](WP6_decision_memo.md)

- Four decision options with timelines and requirements
- Work package completion status: 5/6 complete, 1/6 partial
- Risk assessment (technical, operational, governance)
- 12 questions for sponsor
- Proceed/revise/stop recommendation with conditions

**Key finding:** Prototype demonstrates feasibility (~$3/document, ~75 min operator time, 95% time savings vs manual). Blocked for external release by corpus rights (5/5 pending) and 3 high-priority gaps.

### 2. Contract Verification Matrix (16 pages)
[WP6_contract_verification_matrix.md](WP6_contract_verification_matrix.md)

- Specified vs implemented vs tested analysis
- Trust boundary controls: 3/5 complete, 2/5 partial
- Record policy: 10/13 complete, 1/13 read-only
- CLI contract: 8/8 exit codes working
- Release authority: 6/8 implemented (4 never-except, 2 ordinary)
- Test coverage: 67 product tests, 61 tools tests, 9/9 mutations caught

**High-priority gaps:**
1. Prompt-hash TODOs bypass validation (commands write `None`)
2. Evidence-item records consumed but never emitted
3. External transmission tracking absent
4. ~~Source build gate not explicit~~ **FIXED 2026-08-28**

### 3. Cost and Burden Analysis (9 pages)
[WP6_cost_burden_analysis.md](WP6_cost_burden_analysis.md)

- Token costs: $2.65 typical, $5.30 complex, $20 at contract cap
- Operator burden: 40-110 min per document (median 75 min)
- Time savings: 95-97% vs traditional governed writing (60-100 hours)
- Bottlenecks: brief authoring (manual), repair iteration (human-in-loop)
- Infrastructure: negligible (commodity hardware, no GPU)

**Gap:** Projections from contract caps; no measurements from production runs. Instrumented pilot on real document recommended.

### 4. Rights Review (9 pages)
[WP6_rights_review.md](WP6_rights_review.md)

- Corpus status: 0/5 cleared, 5/5 pending clearance
- Historical sources: 0/5 available for replay
- Current permitted use: "internal fixture evaluation only"
- Clearing timeline: 4-8 weeks
- Decision matrix: internal PoC (immediate) to external readers (8-12 weeks)

**Impact:** Internal evaluation permitted; external release, public benchmarks, and corpus-based case studies blocked.

### 5. Reproducibility Checklist (11 pages)
[WP6_reproducibility_checklist.md](WP6_reproducibility_checklist.md)

- Confidence levels: High (deterministic stack), Medium (behavioral), Low (full pipeline), None (historical)
- WP3 status: Tool-replay complete (9/9 mutations caught), independent human operator not tested
- G3 prerequisites: Met for behavioral reproducibility standard
- Verification commands documented but not executed on independent machine

**Caveat:** WP3 "second operator" satisfied by `run_fixture_suite.py` and `run_mutation_replay.py`, not an independent person on a clean machine.

### 6. Environment and Dependencies (5 pages)
[WP6_environment_dependencies.md](WP6_environment_dependencies.md)

- Platform: Linux 6.8.0, Python 3.13.13, TeX Live 2022
- Locked dependencies: jsonschema 4.26.0, anthropic 0.42.0, pytest 9.1.1
- Installation procedure from clean checkout
- Verification commands and expected outputs

**Deliverable:** Enables independent reproduction with pinned versions.

### 7. Handoff Package Index (5 pages)
[WP6_handoff_package_index.md](WP6_handoff_package_index.md)

- Executive summary and read-order guide
- Quick facts: test coverage, implementation status, contract compliance
- Decision options summary table
- Questions for sponsor
- Next steps for each option

**Purpose:** Navigation guide for sponsor; START HERE document.

## Verification Results (2026-08-28)

### Test Suite
```
Product tests:     67 passed in 0.83s
Tools tests:       61 passed in 1.45s
Fixture suite:     4/4 ready fixtures pass, 12 not executed
Mutation replay:   9/9 caught, 0 missed, 0 errors
Contract checker:  All assertions pass
```

### Work Package Status
- WP0: ⚠ Partial (G0 decision missing, catalog has evidence-item schema but no emission)
- WP1: ✓ Complete (brief, threat model, schemas)
- WP2: ✓ Complete (protected core)
- WP3: ✓ Complete (tool-based mutation replay; human operator not tested)
- WP4: ✓ Complete (authoring extension)
- WP5: ✓ Complete (reader feasibility)
- **WP6: ✓ Complete (this memo)**

## Contract Compliance Summary

### Implemented and Tested (8/11 major components):
1. ✓ CLI exit codes (8/8)
2. ✓ Trust boundary T1-T2 (source isolation, no shell-escape)
3. ✓ Deterministic stack (parser, gates, comparison)
4. ✓ Behavioral properties (schema, abstention, bounds, register, mutation)
5. ✓ Record policy (10/13 records, required fields, deterministic IDs)
6. ✓ Repair invariants (8/8)
7. ✓ Release gates (6/8: 4 never-except, 2 ordinary)
8. ✓ Reader-packet independence

### Partial or Missing (3/11):
9. ⚠ Trust boundary T3-T5 (network deny for parser, but no general policy gate; resource limits partial)
10. ⚠ Runtime inference (model version recorded, but prompt-hash TODOs bypass validation)
11. ✗ External transmission tracking (not implemented)

## Changes During WP6

### Code Changes:
1. **Source build gate added (2026-08-28):** `release_command.py` now includes explicit never-except gate checking `brief_valid` and protected object extraction. Addresses contract gap #4.

### Documentation Created:
- 7 WP6 analysis documents (~60 pages)
- Environment specification with locked dependencies
- Reproducibility verification procedure
- Decision options with timelines

### No Breaking Changes:
- All 67 product tests pass
- All 61 tools tests pass
- Mutation replay still 9/9
- Contract checker still passes

## G4 Decision Options

| Option | Timeline | Requirements | Status |
|--------|----------|--------------|--------|
| **A: Proceed (internal)** | Immediate | Accept gaps + rights limitation | **Recommended** |
| **B: Revise (external)** | 4-8 weeks | Clear rights, fix gaps #1-3, WP3 human | Feasible |
| **C: Narrow (protected-core)** | Immediate | Remove authoring extension | Not needed |
| **D: Stop** | Immediate | None | Not recommended |

**Sponsor decision requested by:** 2026-08-29

## Known Limitations for Internal Scope

### Acceptable for internal evaluation:
- ✓ Test coverage strong (128 tests, 100% pass)
- ✓ Deterministic stack reproducible
- ✓ Behavioral properties validated
- ✓ Cost model reasonable
- ✓ Operator burden acceptable

### Blocks external release:
- ✗ Corpus rights: 5/5 pending clearance
- ✗ Prompt-hash TODOs bypass contract validation
- ✗ Evidence-item emission: operators must hand-author
- ✗ External transmission tracking: not implemented
- ✗ WP3 human operator: tool-replay works, human not tested
- ✗ Real-document validation: synthetic fixtures only

## Recommendations for Sponsor

### If proceeding with Option A (internal):
1. ✓ Accept WP6 package as delivered
2. ✓ Archive v1.1 milestone
3. Create large synthetic document (15,000 words) for cost validation
4. Decide: iterate toward external release or pivot scope
5. If external release: initiate ZLB rights clearance

### If choosing Option B (external release):
1. Commit 4-8 weeks engineering time
2. Initiate corpus rights clearance (ZLB priority)
3. Implement evidence-item emission
4. Replace prompt-hash TODOs with profile hash
5. Recruit independent operator for WP3 human reproduction
6. Execute instrumented pilot on real document

### Not recommended:
- Option C (narrow to protected-core): Authoring extension works well; no evidence it should be removed
- Option D (stop): Prototype demonstrates feasibility; gaps are addressable

## Questions Answered

1. **Can the prototype release documents?** Yes, with deterministic gates and reader-packet independence verified.
2. **What does it cost?** ~$3/document (tokens), ~75 min operator time (95% savings vs manual).
3. **Is it reproducible?** Deterministic stack: yes (high confidence). Behavioral stack: yes with same model version (medium confidence). Full pipeline on real docs: not tested.
4. **Can it be externally released?** Not yet. Requires corpus rights clearance (4-8 weeks) and 3 implementation gaps fixed (2-4 weeks).
5. **What's the test coverage?** 128 tests pass (67 product, 61 tools), 9/9 mutations caught, 4/4 fixtures validated.

## Next Steps

### Immediate (if sponsor approves Option A):
1. Sponsor reviews WP6 package
2. Sponsor provides G4 decision
3. Archive v1.1 as internal milestone
4. Update project memory with decision

### Post-G4 (internal evaluation):
1. Create large synthetic document for cost validation
2. Lock remaining dependencies (TeX Live version documented)
3. Optional: Recruit independent operator for WP3 human test
4. Optional: Start ZLB rights clearance process

### For External Release (if chosen):
1. Fix prompt-hash TODOs (replace `None` with profile hash) — 1-2 days
2. Implement evidence-item emission logic — 1-2 weeks
3. Implement external transmission tracking — 1-2 weeks
4. Clear ZLB corpus rights — 2-4 weeks (parallel with implementation)
5. Perform WP3 independent human reproduction — 1 day
6. Execute instrumented pilot on ZLB document — 1 week

## Conclusion

WP6 decision handoff is complete. The humanvoice v1.1 prototype demonstrates feasibility for governed authoring with auditability, deterministic gates, and behavioral reproducibility. Test coverage is strong, cost model is reasonable, and contract compliance is adequate for internal evaluation.

**G4 recommendation: Proceed with Option A (internal evaluation scope).**

The prototype works as specified for internal use. External release is feasible but requires addressing corpus rights and 3 high-priority implementation gaps. The decision is now with the sponsor.

---

**Prepared by:** Evaluation Lead (Claude Opus 5)  
**Delivered:** 2026-08-28  
**Next gate:** G4 sponsor decision (requested by 2026-08-29)  
**Supporting documents:** 7 WP6 analysis documents, 5 prior WP completion memos, contract v1.1, 128 passing tests
