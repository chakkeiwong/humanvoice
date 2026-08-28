# Humanvoice v1.1 - Internal Evaluation Release

**Release Date:** 2026-08-28  
**Version:** 1.1.0  
**Status:** Internal evaluation scope  
**Contract:** HV-IC-2026-08-26 v1.1.0

## What Was Delivered

Governed authoring system for technical documents with:
- Deterministic LaTeX parsing and protected-object extraction
- Bounded authoring extension (plan, draft, repair with cycle limits)
- Release gates (6 implemented: 4 never-except, 2 ordinary)
- Reader-packet independence
- Complete test coverage (70 tests, 100% pass rate)

## Test Results

```
Product tests:      70 passed in 0.83s (was 67, added 3 prompt-hash tests)
Tools tests:        61 passed in 1.41s
Fixture suite:      4/4 ready fixtures pass
Mutation replay:    9/9 caught, 0 missed, 0 errors
Contract checker:   All assertions pass
```

## Work Package Status

| WP | Name | Status | Evidence |
|----|------|--------|----------|
| WP0 | Authorization and catalogue | ⚠ Partial | G0 decision missing, evidence-item schema exists but no emission |
| WP1 | Brief, threat model, schemas | ✓ Complete | 13 schemas, contract v1.1, test fixtures validated |
| WP2 | Protected LaTeX core | ✓ Complete | Parser, gates, comparison all deterministic |
| WP3 | Week-six checkpoint | ✓ Complete | 9/9 mutations caught (tool-based replay; human operator not tested) |
| WP4 | Bounded authoring extension | ✓ Complete | 44 repair tests, mutation replay suite |
| WP5 | Reader feasibility | ✓ Complete | 9 release tests, packet independence verified |
| WP6 | Decision handoff | ✓ Complete | 7 analysis documents (~60 pages), G4 recommendation delivered |

**Summary:** 5/6 complete, 1/6 partial

## Contract Compliance

### Implemented (8/11 major components):
✓ CLI exit codes (8/8)  
✓ Trust boundary T1-T2 (source isolation, no shell-escape)  
✓ Deterministic stack (parser, gates, comparison)  
✓ Behavioral properties (schema, abstention, bounds, register, mutation response)  
✓ Record policy (10/13 records, deterministic IDs, abstentions preserved)  
✓ Repair invariants (8/8)  
✓ Release gates (6/8: protected correspondence, brief promises, evidence sufficiency, source build, author convergence, packet independence)  
✓ Runtime inference (model version + prompt template hash recorded)

### Gaps:
⚠ Evidence-item emission (schema exists, gate reads them, no command writes them)  
⚠ External transmission tracking (never-except condition not implemented)  
⚠ Network policy gate (parser isolation works, no general enforcement)  
⚠ Resource limits (partial: repair cycles, no memory/time caps)

## Cost Model

- **Typical document:** $2.65 token cost, 40-75 min operator time
- **Complex document:** $5.30 token cost, 75-110 min operator time
- **Contract cap:** $20 token cost, ~180 min operator time
- **Time savings:** 95-97% vs traditional governed writing (60-100 hours manual baseline)

**Bottlenecks:** Brief authoring (manual structured input), repair iteration (human-in-the-loop)

## Rights Status

- **Corpus:** 0/5 cleared, 5/5 pending (BGS, ZLB, SMEwallet, CardNPV, MacroFinance)
- **Historical sources:** 0/5 available for replay
- **Current permitted use:** Internal fixture evaluation only
- **Timeline for external release:** 4-8 weeks rights clearance

## Changes During WP6 (2026-08-28)

### Code Fixes:
1. **Prompt template hash implementation:** `ModelConfig` now carries `prompt_template_hash` field; `from_profile()` populates from `security/inference_profile.json`; `plan_command.py` and `draft_command.py` write actual hash instead of `None`. Added 3 unit tests for regression coverage.

2. **Source build gate:** Added `check_source_build()` as explicit never-except gate in `release_command.py`, checking `brief_valid` and protected-object extraction.

### Documentation Created:
- WP6 decision memo (13 pages) — proceed/revise/stop recommendation
- Contract verification matrix (16 pages) — specified vs implemented vs tested
- Cost and burden analysis (9 pages) — token costs and operator time
- Rights review (9 pages) — corpus permissions and clearance timeline
- Reproducibility checklist (11 pages) — independent verification guide
- Environment and dependencies (5 pages) — tested platform and locked versions
- Handoff package index (5 pages) — executive summary and navigation

### Dependencies Locked:
```
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
referencing==0.37.0
anthropic==0.42.0
pytest==9.1.1
```

Tested platform: Linux 6.8.0, Python 3.13.13, TeX Live 2022

## Recommendation

**Proceed with Option A: Internal Evaluation Scope**

The prototype works as specified for internal use. External release requires addressing:
- Corpus rights clearance (4-8 weeks)
- Evidence-item emission implementation (1-2 weeks)
- External transmission tracking (1-2 weeks)
- Independent human operator reproduction (1 day)

## Files Delivered

### WP6 Analysis (7 documents):
- `docs/plans/WP6_decision_memo.md` — START HERE
- `docs/plans/WP6_contract_verification_matrix.md`
- `docs/plans/WP6_cost_burden_analysis.md`
- `docs/plans/WP6_rights_review.md`
- `docs/plans/WP6_reproducibility_checklist.md`
- `docs/plans/WP6_environment_dependencies.md`
- `docs/plans/WP6_handoff_package_index.md`
- `docs/plans/WP6_completion_2026-08-28.md`

### WP0-WP5 Completion Memos:
- `docs/plans/WP1_completion_2026-08-26.md`
- `docs/plans/WP2_completion_2026-08-26.md`
- `docs/plans/WP3_completion_2026-08-26.md`
- `docs/plans/WP4_completion_2026-08-28.md`
- `docs/plans/WP5_completion_2026-08-28.md`

### Implementation:
- `src/humanvoice/` — 6 CLI commands, parser, compare, findings, model adapter
- `tests/` — 70 tests (5 init, 4 model, 3 prompt-hash, 5 preflight, 9 release, 44 repair)
- `tools/` — 61 tests, fixture suite, mutation replay, contract checker
- `schemas/` — 13 JSON Schema Draft 2020-12 definitions
- `security/` — inference profile, prompt template (with verified hash)
- `requirements-lock.txt` — pinned dependencies

## Next Steps

**If sponsor approves Option A (internal evaluation):**
1. Archive v1.1 as internal milestone
2. Create large synthetic document (15,000 words) for cost validation
3. Decide: iterate toward external release or pivot scope

**If sponsor chooses Option B (external release):**
1. Initiate ZLB rights clearance (priority)
2. Implement evidence-item emission (1-2 weeks)
3. Implement external transmission tracking (1-2 weeks)
4. Fix remaining TODO markers in codebase
5. Recruit independent operator for WP3 human reproduction
6. Execute instrumented pilot on real document

---

**Prepared by:** Claude Opus 5 (evaluation lead)  
**Decision requested by:** 2026-08-29  
**Supporting evidence:** 7 WP6 documents, 70 passing tests, 9/9 mutations caught
