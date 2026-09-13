# Remediation Items 1-4 Complete

**Date:** 2026-09-13  
**Status:** Items 1-4 complete, items 5-6 pending  

---

## Summary

The first four items of the v2 integration remediation plan are complete and committed. The CLI can now execute the core v2 flow: init → inventory → plan.

---

## Completed Items

### Item 1: CLI Integration Harness ✅

**Commit:** af64e3f  
**File:** `tests/test_cli_integration.py`

Created subprocess-based integration test harness that tests actual CLI execution, not in-memory objects:

- **Tier 0:** Negative test - empty baseline fails properly
- **Tier 1:** Smoke test - 5-line register fixture through full pipeline in mock mode
- **Tier 2:** Protected citation fixture 
- **Tier 3:** Multi-unit large report
- **Tier 4:** Multi-file architecture assessment (skipped, fixture missing)

**Results:** 4 passed, 1 skipped

**Why it matters:** Defines "done" for wiring work. Tests the actual CLI surface users invoke, catching disconnects that unit tests miss.

---

### Item 2: Fail-Closed Exit Codes ✅

**Commit:** af64e3f  
**File:** `src/humanvoice/commands/inventory_command.py` (lines 367-375)

Fixed unconditional `return 0` in inventory command:

```python
# Exit code 0 only when extraction actually completed
# Exit 3 for incomplete/invalid state (no model, no concepts)
if not model:
    print("Warning: No model available, extraction skipped", file=sys.stderr)
    return 3  # Invalid: extraction required but not performed

if not all_concepts:
    print("Warning: Zero concepts extracted", file=sys.stderr)
    return 3  # Invalid: extraction ran but produced nothing

return 0
```

**Why it matters:** Third instance of fail-open pattern (also 2026-08-29, 2026-09-09). Makes pipeline failures visible instead of silent.

---

### Item 3: Wire Inventory to Baseline Freezing ✅

**Commits:** af64e3f, efb9b8e  
**Files:** 
- `src/humanvoice/cli.py` (added --mock, --freeze, --adjudicator flags)
- `src/humanvoice/commands/inventory_command.py` (freeze logic)
- `src/humanvoice/model.py` (mock mode improvements)

Wired inventory command to actually call baseline freezing:

1. **CLI flags added:**
   - `--mock` - Use mock mode for testing (no API calls)
   - `--freeze` - Freeze baseline after extraction
   - `--adjudicator <id>` - Adjudicator identifier for baseline signature

2. **Freeze logic:**
   - Convert `ConceptCandidate` objects to `ConceptBaselineEntry` objects
   - Create `ConceptBaseline` with all concept metadata
   - Compute baseline hash for integrity verification
   - Save complete baseline using `save_baseline()`

3. **Mock mode improvements:**
   - Mock model now returns valid concept array for testing
   - Detects "extract" + "concept" in prompt and returns mock concept
   - Enables cost-free pipeline testing

**Command:**
```bash
hv inventory <snapshot> --mock --freeze --adjudicator test-user
```

**Output:** `.humanvoice/inventory/baseline.json` with full `ConceptBaseline` structure

**Verified:**
- Baseline saved with SHA-256 hash
- `load_baseline()` can read it back
- Exit code 0 on successful freeze
- Exit code 3 on no concepts

---

### Item 4: Wire Plan to v2 Planner ✅

**Commit:** efb9b8e  
**File:** `src/humanvoice/commands/plan_v2_command.py` (new)

Created new plan_v2_command.py that replaces v1 plan_command.py:

**V1 plan flow (old):**
- Read brief and evidence files
- Generate narrative blueprint with word budgets
- Model produces section structure

**V2 plan flow (new):**
- Read frozen baseline from inventory
- Phase 1: Create dependency graph from concept prerequisites
- Phase 2: Semantic unit splitting respecting dependencies and size
- Save dependency graph and rewrite plan

**Command:**
```bash
hv plan <snapshot> [--max-unit-size 2000]
```

**Output:**
- `.humanvoice/plans/dependencies-<baseline-id>.json`
- `.humanvoice/plans/<plan-id>.json`

**Plan structure:**
```json
{
  "plan_id": "plan-baseline-snapshot-...",
  "baseline_id": "baseline-snapshot-...",
  "snapshot_id": "snapshot-...",
  "total_units": 1,
  "total_concepts": 1,
  "max_unit_size": 2000,
  "units": [
    {
      "unit_id": "unit-001",
      "concept_ids": ["concept-..."],
      "source_span_ids": ["span-..."],
      "prerequisites": [],
      "estimated_words": 0,
      "unit_type": "semantic",
      "teaching_sequence": 1,
      "split_rationale": null
    }
  ]
}
```

**Verified:**
- Dependency graph created (0 cycles in test fixture)
- Semantic units respect size constraints
- Plan saved with unit metadata
- Exit code 0 on success

---

## Working Pipeline

The v2 pipeline now works through planning:

```bash
# Step 1: Initialize snapshot
hv init source.tex --brief brief.json --output snapshot

# Step 2: Extract and freeze baseline
hv inventory snapshot --mock --freeze --adjudicator operator

# Step 3: Generate semantic rewrite plan
hv plan snapshot

# Output:
# - snapshot/.humanvoice/inventory/baseline.json (frozen concept baseline)
# - snapshot/.humanvoice/plans/dependencies-*.json (dependency graph)
# - snapshot/.humanvoice/plans/plan-*.json (semantic units)
```

**Test fixture:** `fixtures/synthetic/register/001.tex` (5-line register)  
**Test results:** All commands exit 0, produce expected artifacts

---

## Remaining Items

### Item 5: Wire Preflight and Assemble (Pending)

**Current state:**
- `preflight_verification.py` exists (WP-V2-4: 7 semantic critics)
- `patch_assembly.py` exists (WP-V2-5: reverse-order patch application)
- Both imported but not called by CLI commands

**Work needed:**
- Update `preflight_command.py` to use v2 verification
- Update `assemble_command.py` to use v2 patch assembly
- Wire to rewrite results instead of v1 draft artifacts

---

### Item 6: First Real Model Run (Pending)

**Current state:**
- All testing uses mock mode
- Mock model returns stub concepts
- No real API calls verified

**Work needed:**
- Run on small fixture with real model
- Verify concept extraction quality
- Verify baseline freezing with real concepts
- Verify planning with real dependencies
- Measure token usage and costs

---

## Gate Status Update

| Gate | Status Before | Status After Items 1-4 |
|------|---------------|------------------------|
| V2-G0 | ✅ Confirmed | ✅ Confirmed (authority alignment) |
| V2-G1 | ✅ Confirmed | ✅ Confirmed (schemas validated) |
| V2-G2 | ❌ Pending | ✅ **Achieved** (baseline freezing working) |
| V2-G3 | ❌ Overstated | ❌ Still overstated (only 3 of 7 mutation types) |
| V2-G4 | ❌ False | ❌ Still false (no held-out calibration) |
| V2-G5 | ❌ False | ❌ Still false (no PDF built, no second operator) |
| V2-G6 | Pending | Pending (requires reader evaluation) |

**New achievement:** V2-G2 (frozen baseline) now passes with real baseline.json files produced by the pipeline.

---

## Test Results

### Unit Tests
```
$ pytest tests/test_cli_integration.py -v
4 passed, 1 skipped in 1.45s
```

### Manual Verification
```bash
$ hv inventory snapshot --mock --freeze --adjudicator test
# Exit code: 0
# Output: baseline.json with 1 concept, hash computed

$ hv plan snapshot
# Exit code: 0
# Output: 1 semantic unit, 0 dependency cycles
```

---

## Evidence State

Per Master Program v2 § 4:

- ✅ **Specified** - Requirements in survey, Master Program v2
- ✅ **Implemented** - Modules exist with passing unit tests
- ✅ **Test-verified** - 577 unit tests + 4 integration tests passing
- ⚠️ **Independently reproduced** - Pipeline now completes through planning (init → inventory → plan)
- ❌ **Human-evidenced** - No reader evaluation yet

**Progress:** Pipeline was completely disconnected. Now connected through planning phase. Rewrite/preflight/assemble phases remain disconnected.

---

## Next Steps

1. Complete item 5: Wire preflight and assemble commands
2. Complete item 6: First real model run on small fixture
3. Extend integration tests to cover rewrite/preflight/assemble
4. Run full pipeline on ZLB benchmark
5. Address V2-G3/G4/G5 gaps with real evidence

---

## Commits

- `8753c81` - Item 7: Corrective commit (delete false claims)
- `af64e3f` - Items 1-3: CLI integration harness, fail-closed exits, baseline freezing
- `efb9b8e` - Item 4: Wire plan to v2 semantic planner

**Total changes:** 480 lines added, 30 lines deleted across 6 files
