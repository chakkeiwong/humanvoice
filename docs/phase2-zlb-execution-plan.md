# Phase 2: ZLB Benchmark Execution Plan

**Master Program Reference:** § 6.6 WP-V2-6, line 80  
**Prerequisites:** ✓ Phase 1 complete (fixtures locked)  
**Target:** Complete ZLB benchmark execution demonstrating full pipeline

## Objective

Execute the complete humanvoice v2 pipeline on the ZLB manuscript to produce:
1. Human-readable output demonstrating 1.0 concept retention
2. Evidence that mutation safety blocks all violations
3. Comparison against v1.2 baseline
4. Foundation for reader evaluation (Phase 3)

## Required Inputs

### 1. ZLB Source Manuscript
**Location candidates:**
- `docs/survey/zlb_original.tex` (if exists)
- `docs/zlb/` directory
- Original paper from corpus

**Requirements:**
- Complete LaTeX source
- Rights-cleared for internal use (already verified per memory)
- Suitable length for benchmark (2000-4000 words target)

### 2. Configuration
- API credentials for rewrite/verification calls
- Output directory structure
- Logging configuration

## Execution Steps

### Step 1: Acquire and Verify Source
```bash
# Locate ZLB source
find docs/ -name "*zlb*" -type f

# If not present, document source location
# Verify file is readable and well-formed LaTeX
```

### Step 2: Generate Concept Inventory (WP-V2-2)
```bash
hv inventory docs/zlb_source.tex \
  --output baselines/zlb-v2-baseline.json \
  --freeze
```

**Deliverables:**
- Frozen concept baseline with SHA256 hash
- Source span coverage (100% required)
- Concept dependency graph
- Ambiguity log (if any, requires human adjudication)

**Gate:** V2-G2 - all spans covered, dependencies resolved, baseline frozen

### Step 3: Generate Rewrite Plan (WP-V2-2)
```bash
hv plan baselines/zlb-v2-baseline.json \
  --output plans/zlb-v2-plan.json
```

**Deliverables:**
- Unit boundaries (semantic units with source offsets)
- Obligation assignments (definition/mechanism/example per concept)
- Unit sequencing (respects dependencies)

### Step 4: Execute Rewrite Phase (WP-V2-3)
```bash
hv rewrite plans/zlb-v2-plan.json \
  --baseline baselines/zlb-v2-baseline.json \
  --output sessions/zlb-v2-rewrite/ \
  --log-level DEBUG
```

**Deliverables:**
- Rewritten units (one per plan unit)
- Concept correspondence records
- Mutation safety verdicts
- Rejected units requiring split/repair

**Gate:** V2-G3 - no mutations accepted, all concepts retained

### Step 5: Preflight Verification (WP-V2-4)
```bash
hv verify sessions/zlb-v2-rewrite/ \
  --baseline baselines/zlb-v2-baseline.json \
  --output sessions/zlb-v2-preflight/ \
  --max-cycles 3
```

**Deliverables:**
- Independent semantic verification results
- Repair cycles (if needed, max 3 per unit)
- Final verification status per unit
- Oscillation detection logs

**Gate:** V2-G4 - all units pass or repair converges

### Step 6: Patch Assembly (WP-V2-5)
```bash
hv assemble sessions/zlb-v2-preflight/ \
  --source docs/zlb_source.tex \
  --output releases/zlb-v2-revised.tex \
  --blackline releases/zlb-v2-comparison.pdf
```

**Deliverables:**
- Revised manuscript (complete LaTeX)
- Blackline comparison PDF
- Assembly verification report
- Untouched region verification

**Gate:** V2-G5 - clean build, byte-stable untouched regions

### Step 7: Run Fixture Validation
```bash
python tools/run_fixture_suite.py fixtures/unit/ \
  --against sessions/zlb-v2-rewrite/ \
  --output results/zlb-fixture-validation.json

python tools/run_fixture_suite.py fixtures/mutation/ \
  --against sessions/zlb-v2-rewrite/ \
  --output results/zlb-mutation-validation.json
```

**Deliverables:**
- Unit fixture results (13 fixtures)
- Mutation fixture results (11 fixtures)
- Pass/fail summary
- Detailed findings log

### Step 8: Compare Against v1.2 Baseline
```bash
hv compare \
  --v1 releases/zlb-v1.2-revised.tex \
  --v2 releases/zlb-v2-revised.tex \
  --metrics results/zlb-comparison-metrics.json
```

**Deliverables:**
- Concept retention comparison (v1.2 vs v2)
- Mutation rate comparison
- Length/readability metrics
- Qualitative differences log

## Expected Outcomes

### Success Criteria
- ✓ 100% concept retention (1.0 correspondence)
- ✓ 0 mutations accepted (all safety blocks effective)
- ✓ All fixtures pass
- ✓ Clean PDF builds (revised + blackline)
- ✓ Repair converges within 3 cycles per unit
- ✓ No oscillation detected

### Failure Modes and Response

**Concept loss (correspondence < 1.0):**
- Identify which concepts lost
- Review unit splitting logic
- Check obligation assignments
- May require baseline correction (with lineage)

**Mutation acceptance:**
- Identify mutation type
- Review safety block logic
- Check threshold calibration
- Fix in implementation, re-run from rewrite phase

**Repair oscillation:**
- Review error signatures
- Check repair prompt construction
- May indicate unit split needed
- Document as human choice point

**Fixture failures:**
- Compare expected vs actual behavior
- Distinguish implementation bugs from calibration issues
- Implementation bugs require fix + full re-run
- Calibration issues inform reader evaluation design

## Timing Estimate

- Step 1: 15 minutes (source location + verification)
- Step 2: 30-60 minutes (inventory generation + review)
- Step 3: 15 minutes (plan generation)
- Step 4: 2-4 hours (rewrite phase, depends on manuscript length + API latency)
- Step 5: 1-2 hours (verification + repair cycles)
- Step 6: 15 minutes (assembly + build)
- Step 7: 30 minutes (fixture validation)
- Step 8: 30 minutes (comparison analysis)

**Total:** 5-9 hours (mostly API execution time)

## Next Phase Dependencies

Phase 3 (Reader Evaluation) requires:
- ✓ ZLB v2 revised manuscript
- ✓ ZLB v1.2 baseline manuscript
- ✓ Comparison metrics
- ⧗ Reader recruitment (10 graduate economics students)
- ⧗ Evaluation protocol design
- ⧗ Within-subjects counterbalanced experiment

Phase 4 (Second-Operator Replay) requires:
- ✓ Regression manifest (frozen inputs + expected outputs)
- ⧗ Independent operator
- ⧗ Clean environment setup

## Risk Mitigation

**Risk:** ZLB source not available in repository  
**Mitigation:** Document source location, verify corpus rights, acquire copy

**Risk:** API quota/rate limits during execution  
**Mitigation:** Implement resume capability, save intermediate state

**Risk:** First real execution reveals implementation bugs  
**Mitigation:** Fix bugs, update tests, re-run from failure point

**Risk:** Baseline ambiguity requires adjudication  
**Mitigation:** Document ambiguity, present to owner for decision, record lineage

## Artifacts Manifest

All artifacts saved to session directory with manifest:
- `baselines/zlb-v2-baseline.json` (frozen, SHA256-locked)
- `plans/zlb-v2-plan.json`
- `sessions/zlb-v2-rewrite/` (rewrite results)
- `sessions/zlb-v2-preflight/` (verification results)
- `releases/zlb-v2-revised.tex`
- `releases/zlb-v2-comparison.pdf`
- `results/zlb-fixture-validation.json`
- `results/zlb-mutation-validation.json`
- `results/zlb-comparison-metrics.json`
- `logs/zlb-v2-execution.log` (complete execution log)

All artifacts are required for V2-G6 and second-operator replay.
