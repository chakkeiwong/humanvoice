# ZLB Golden Test - Implementation Complete

**Date:** 2026-09-19  
**Status:** Ready for execution

## Summary

The ZLB manuscript has been integrated as a permanent golden test fixture, fulfilling the user's directive to "clone the ZLB document and make it part of the integration test."

## Deliverables

### 1. Test Fixture (fixtures/real_documents/zlb_2026/)

- **manuscript.tex** - 189,841 bytes, 3,368 lines (locked with SHA256)
- **brief.json** - Reader profile for test execution
- **answer_key.json** - Expected results for all pipeline phases
- **README.md** - Documentation and maintenance instructions

### 2. Test Implementation (tests/integration_real/test_zlb_golden.py)

Complete end-to-end test validating:

#### Phase 1: Init
- Snapshot directory creation
- Manifest generation

#### Phase 2: Inventory
- Expected concept count: 1,113 ± 50 concepts
- Baseline freezing
- Span offset generation

#### Phase 3: Plan
- Expected units: ~50 ± 10 units
- **Critical invariant 1:** All units contiguous (max gap < 10KB)
- **Critical invariant 2:** Zero overlapping units

#### Phase 4: Rewrite
- 100% correspondence ratio required
- Zero failed units expected
- Timeout: 3,600 seconds (1 hour)

#### Phase 5: Preflight
- All units verified
- Zero blocked units

#### Phase 6: Assembly
- 100% patches applied
- **V2-G5 byte identity** verification
- Minimum 95% coverage

### 3. Helper Functions

Implemented in test file:

- `check_unit_contiguity()` - Validates gap threshold between spans
- `find_overlapping_units()` - Detects byte range conflicts
- `verify_byte_identity()` - Validates V2-G5 property
- `build_latex_pdf()` - Validates document compilation
- `verify_source_integrity()` - Prevents fixture tampering

### 4. CI Integration (docs/ci-golden-test.md)

Documentation for:
- Nightly execution schedule (2 AM)
- Manual testing procedures
- Cost control strategies (~$10/run)
- Failure alerting workflow
- Test selection patterns

### 5. Pytest Configuration

Added custom markers to `pyproject.toml`:
- `@pytest.mark.real` - Real manuscript tests
- `@pytest.mark.expensive` - Tests >$1 or >5 min
- `@pytest.mark.requires_model` - Live model required

## Test Execution

```bash
# Run golden test (20 min, $10)
python -m pytest tests/integration_real/test_zlb_golden.py -v -s

# Or run directly
python tests/integration_real/test_zlb_golden.py

# Exclude from PR CI
pytest -m "not expensive"
```

## Critical Invariants Enforced

This test catches the exact issues that blocked ZLB assembly:

1. **Non-contiguous units** - Rejects units with gaps >10KB (catches unit-005's 140KB gap)
2. **Overlapping units** - Rejects any byte range overlaps (catches unit-004/005/007/008/009/010)
3. **Deleted concepts** - Requires 100% correspondence (catches unit-014's 15 deleted concepts)
4. **Missing spans** - Validates all span IDs exist in inventory (catches 56 missing spans)
5. **Byte identity** - Verifies untouched bytes match source (V2-G5 property)

## Expected Outcome

When the architectural rebuild is complete (enforcing contiguity in the planner), this test will:

1. **Pass inventory** - Extract ~1,113 concepts
2. **Pass planning** - Generate ~50 contiguous units with zero overlaps
3. **Pass rewrite** - Achieve 100% correspondence with zero deleted concepts
4. **Pass preflight** - Verify all units meet safety requirements
5. **Pass assembly** - Apply all patches with byte identity preserved

## Next Steps

1. **Run architectural rebuild** - Implement Phases 1-6 from comprehensive-test-strategy.md
2. **Execute golden test** - Validate pipeline works end-to-end
3. **Set up CI** - Configure nightly runs with Slack alerts
4. **Expand fixture suite** - Add 10 edge cases, 10 concept patterns, 10 scale increments

## Test Philosophy

From the fixture README:

> "If this test fails, the pipeline is broken. Period."

This is not a unit test. This is not a mock test. This is the real thing - a 3,368-line manuscript that exposed fundamental pipeline defects. It will remain in the test suite permanently as the gold standard for "does the pipeline work?"

Any change that breaks this test must be reverted or fixed before merge. No exceptions.
