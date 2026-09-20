# Phase 5 Execution Status: ZLB End-to-End Validation

**Program ID:** MP-ZLB-REBUILD  
**Phase:** 5 of 6  
**Started:** 2026-09-21  
**Status:** IN PROGRESS (Inventory extraction)

---

## Execution Summary

### Phases 1-4: COMPLETE ✅

All architectural fixes implemented and committed:

1. **Phase 1:** Concept Locality Enforcement (COMPLETE)
   - File: `src/humanvoice/model_extraction.py`
   - Function: `validate_concept_locality()`
   - Tests: `tests/test_concept_extraction_locality.py` (5 tests)
   - Commit: `3a7c8f1`

2. **Phase 2:** Planner Contiguity Enforcement (COMPLETE)
   - File: `src/humanvoice/semantic_unit_splitting.py`
   - Functions: `build_span_clusters()`, `finalize_unit()` modified
   - Tests: `tests/test_semantic_unit_splitting_contiguity.py` (8 tests)
   - Commit: `9b4d5e2`

3. **Phase 3:** Phase Boundary Validation (COMPLETE)
   - Files: `commands/inventory_command.py`, `commands/plan_v2_command.py`
   - Functions: `validate_plan()` added
   - Tests: `tests/test_phase_boundary_validation.py` (6 tests)
   - Commit: `7f3a1c8`

4. **Phase 4:** Assembly Simplification (COMPLETE)
   - File: `src/humanvoice/patch_assembly.py`
   - Function: `_collect_patches_from_unit()` simplified
   - Tests: `tests/test_patch_assembly_simplified.py` (4 tests)
   - Commit: `2d9e6b5`

### Phase 5: IN PROGRESS 🔄

**Current Step:** Inventory extraction with Phase 1 locality enforcement

**Command:**
```bash
hv inventory sessions/zlb-v2-snapshot --freeze --adjudicator test-harness
```

**Progress:**
- Window: 24/146 (16.4%)
- Estimated time remaining: ~9 minutes
- Rate: ~1.5 windows/minute
- Expected concepts: ~1,100 (with span range < 10KB)

**Background Task:**
- Task ID: `b7hwdt02w`
- Output: `/tmp/claude-1000/.../tasks/b7hwdt02w.output`
- Started: ~4 minutes ago
- Status: Running

**Warning Detected:**
```
Warning: Protected object linking failed: from_parser_objects() takes 1 positional argument but 2 were given
```
- Impact: Non-fatal, extraction continues
- Note: Protected object links may be incomplete

---

## Phase 5 Remaining Steps

Once inventory completes:

### Step 2: Capture Baseline ID
```bash
BASELINE_ID=$(jq -r '.baseline_id' sessions/zlb-v2-snapshot/.humanvoice/inventory/baseline.json)
echo "Baseline: $BASELINE_ID"
```

### Step 3: Verify Concept Locality
```bash
python3 -c "
import json
from pathlib import Path

baseline = json.loads(Path('sessions/zlb-v2-snapshot/.humanvoice/inventory/baseline.json').read_text())
spans_path = Path('sessions/zlb-v2-snapshot/.humanvoice/inventory/spans.jsonl')

# Load span offsets
span_offsets = {}
with open(spans_path) as f:
    for line in f:
        if line.strip():
            span = json.loads(line)
            span_offsets[span['record_id']] = {'byte_start': span['byte_start'], 'byte_end': span['byte_end']}

# Check locality
violations = []
for entry in baseline['concept_entries']:
    if not entry['source_span_ids']:
        continue
    
    positions = [span_offsets[sid] for sid in entry['source_span_ids'] if sid in span_offsets]
    if not positions:
        continue
    
    min_start = min(p['byte_start'] for p in positions)
    max_end = max(p['byte_end'] for p in positions)
    span_range = max_end - min_start
    
    if span_range > 10 * 1024:
        violations.append((entry['concept_id'], span_range))

if violations:
    print(f'❌ FAIL: {len(violations)} concepts exceed 10KB span range')
    for cid, span_range in violations[:5]:
        print(f'  {cid}: {span_range/1024:.1f} KB')
else:
    print(f'✅ PASS: All {len(baseline[\"concept_entries\"])} concepts have span range < 10KB')
"
```

### Step 4: Plan with Contiguity Enforcement
```bash
hv plan sessions/zlb-v2-snapshot --baseline-id $BASELINE_ID
```

Expected:
- Unit count: 50-60 units (may increase from original 33)
- All units contiguous (max 10KB gap)
- Zero overlapping units

### Step 5: Validate Plan
```bash
python scripts/validate_plan_contiguity.py sessions/zlb-v2-snapshot
```

Expected output:
```
✅ VALIDATION PASSED: All checks successful

Summary:
  - 50-60 units
  - All units contiguous (max 10KB gap)
  - No overlapping units
  - All span IDs exist
  - No passenger concepts
```

### Step 6: Rewrite (Live Model - $8-10 cost)
```bash
PLAN_ID=$(jq -r '.plan_id' sessions/zlb-v2-snapshot/.humanvoice/plans/plan-*.json | head -1)

hv rewrite sessions/zlb-v2-snapshot \
    --baseline-id $BASELINE_ID \
    --plan-id $PLAN_ID \
    --timeout 3600
```

Expected:
- 50-60 units rewritten
- 100% correspondence (0 deleted concepts)
- Time: ~15-20 minutes
- Cost: ~$8-10

### Step 7: Preflight
```bash
hv preflight-v2 sessions/zlb-v2-snapshot
```

Expected:
- All units verified
- Exit code: 0

### Step 8: Assembly
```bash
hv assemble-v2 sessions/zlb-v2-snapshot
```

Expected:
```json
{
  "assembly_complete": true,
  "patches_applied": 50-60,
  "patches_failed": 0,
  "units_assembled": 50-60,
  "units_excluded": 0,
  "coverage_percent": 100.0
}
```

### Step 9: Run Golden Test
```bash
pytest tests/integration_real/test_zlb_golden.py::test_zlb_golden_path -v -s
```

Expected:
```
tests/integration_real/test_zlb_golden.py::test_zlb_golden_path PASSED

Phase 1: Init ✓
Phase 2: Inventory ✓
Phase 3: Plan ✓
Phase 4: Rewrite ✓
Phase 5: Preflight ✓
Phase 6: Assembly ✓
```

### Step 10: Commit Phase 5 Results
```bash
git add sessions/zlb-v2-snapshot/.humanvoice/
git commit -m "Phase 5 complete: ZLB end-to-end validation successful

Results:
- Inventory: ~1,100 concepts (all span range < 10KB)
- Plan: 50-60 units (all contiguous, no overlaps)
- Rewrite: 100% correspondence
- Assembly: 100% coverage
- Golden test: PASSED

All architectural fixes validated on real 189KB manuscript.
"
```

---

## Success Criteria

Phase 5 is complete when:
- ✅ Inventory completes with ~1,100 concepts
- ✅ All concepts have span range < 10KB
- ✅ Plan produces 50-60 contiguous units
- ✅ Zero overlapping units
- ✅ Rewrite achieves 100% correspondence
- ✅ Assembly achieves 100% coverage
- ✅ Golden test passes all 6 phases

---

## Current File Locations

**Snapshot:**
- Directory: `sessions/zlb-v2-snapshot/`
- Source: `sessions/zlb-v2-snapshot/source/zlb_source.tex` (189,841 bytes)
- Inventory: `sessions/zlb-v2-snapshot/.humanvoice/inventory/`
- Plans: `sessions/zlb-v2-snapshot/.humanvoice/plans/`
- Rewrites: `sessions/zlb-v2-snapshot/.humanvoice/rewrites/`

**Tests:**
- Golden test: `tests/integration_real/test_zlb_golden.py`
- Fixture: `fixtures/real_documents/zlb_2026/`

**Scripts:**
- Validation: `scripts/validate_plan_contiguity.py`
- Monitoring: `scripts/monitor_inventory.py`

**Documentation:**
- Context reset: `docs/ZLB_CONTEXT_RESET_MEMO.md`
- Master program: `docs/master-program-zlb-rebuild.md`
- Phase 6 plan: `docs/phase6-scale-testing-plan.md`

---

## Risk Assessment

**Risk 1: Rewrite may still have deleted concepts**
- Probability: Medium (30%)
- Root cause: Model prompt non-compliance
- Mitigation: Retry mechanism already in place
- Fallback: Accept <5% deleted concepts as model limitation

**Risk 2: Assembly may fail on edge cases**
- Probability: Low (10%)
- Reason: All fixes in place, validated with unit tests
- Mitigation: Detailed error logging in assembly

**Risk 3: Golden test may reveal unexpected issues**
- Probability: Low (10%)
- Reason: Each phase tested individually
- Mitigation: Step-by-step validation before golden test

---

## Next Actions

**Immediate (waiting for inventory):**
- Monitor progress: `python scripts/monitor_inventory.py /tmp/.../tasks/b7hwdt02w.output`
- Check for errors: `grep -i error /tmp/.../tasks/b7hwdt02w.output`

**After inventory completes:**
1. Verify concept locality (Step 3)
2. Run plan with contiguity (Step 4)
3. Validate plan (Step 5)
4. Decision point: Proceed with $8-10 rewrite?

**User confirmation needed before rewrite:**
- Confirm model API access
- Confirm $8-10 cost acceptable
- Confirm timeout settings (3600s)

---

## Phase 6 Preview

After Phase 5 completes, Phase 6 (Scale Testing) will:

1. Generate scale fixtures: 10, 50, 100, 250, 500, 800 pages
2. Run inventory + plan on each (no expensive rewrite)
3. Validate contiguity at each scale
4. Record performance metrics
5. Confirm 800-page fixture completes successfully

Estimated time: 2-3 hours  
Estimated cost: $0 (inventory+plan only, no rewrite)

---

## Status: WAITING FOR INVENTORY (ETA ~9 minutes)
