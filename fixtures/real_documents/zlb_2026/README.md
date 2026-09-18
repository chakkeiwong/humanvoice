# ZLB 2026 Manuscript - Golden Test Fixture

## Overview

This is a real academic manuscript (3,368 lines, 189KB) used as the gold standard integration test for the Humanvoice V2 pipeline.

**Source:** Zero Lower Bound and Japanese Economy (2026)  
**Complexity:** Graduate-level economics, DSGE models, Bayesian inference  
**Features:** 47 equations, 54 citations, 6 sections, technical LaTeX

## Purpose

This fixture serves as the single most important test in the entire suite. If the pipeline successfully processes this document end-to-end, it demonstrates readiness for real-world manuscripts of similar complexity.

## What It Tests

1. **Real LaTeX complexity:** Multi-byte Unicode, nested math, custom commands
2. **Concept extraction:** 1,113 concepts from technical economic content
3. **Planning:** ~50 units with contiguity enforcement
4. **Rewriting:** Full humanization with 100% concept preservation
5. **Assembly:** Byte-level patch application with V2-G5 identity verification
6. **Scale:** Realistic document size (3,368 lines)

## Known Issues It Exposed

1. **Unit-005 gap bug:** 140KB gap between spans created false overlaps
2. **Unit-014 deleted concepts:** Model deleted 15 concepts during rewrite
3. **Missing span offsets:** 56 span IDs missing from inventory

All three issues have been documented and must remain fixed for this test to pass.

## Test Execution

**Manual run:**
```bash
pytest tests/integration_real/test_zlb_golden.py --expensive -v
```

**CI schedule:** Nightly (2 AM)

**Cost:** ~$10 per run (live model inference)

**Duration:** ~20 minutes

## Answer Key

The `answer_key.json` file locks in expected behavior:
- Concept count: 1,113 ± 50
- Units: ~50 ± 10
- Correspondence: 1.0 (no deleted concepts)
- Assembly: 100% success, >95% coverage
- Byte identity: Required (V2-G5 property)

## Files

- `manuscript.tex` - Source LaTeX (DO NOT MODIFY - locked by SHA256)
- `brief.json` - Reader profile for extraction
- `answer_key.json` - Expected pipeline results
- `README.md` - This file

## Maintenance

If the pipeline architecture changes significantly:
1. Run pipeline manually to verify it still passes
2. Update answer key if expectations change (with justification)
3. Never modify manuscript.tex (defeats purpose of regression test)
4. Document any tolerance adjustments in git commit message

## Success Criteria

All phases must exit 0 and produce artifacts matching answer key:
- ✓ Inventory: 1,113 concepts extracted
- ✓ Planning: ~50 contiguous units, no overlaps
- ✓ Rewrite: 100% correspondence, no deleted concepts
- ✓ Preflight: All units pass verification
- ✓ Assembly: 100% patches applied, byte identity verified
- ✓ Build: assembled.tex compiles to PDF

**If this test fails, the pipeline is broken. Period.**
