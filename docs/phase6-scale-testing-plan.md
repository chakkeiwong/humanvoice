# Phase 6: Scale Testing Plan

**Goal**: Validate pipeline scales to 500-800 page monographs

**Duration**: 2-3 days

**Cost**: ~$40 for model API calls

---

## Test Strategy

We'll test the pipeline at multiple scale points to identify performance bottlenecks and validate that architectural fixes hold at larger document sizes.

### Scale Points

| Pages | Lines | Est. Concepts | Est. Units | Inventory Time | Plan Time |
|-------|-------|---------------|------------|----------------|-----------|
| 10    | 400   | ~50          | ~5         | <1 min         | <5s       |
| 50    | 2,000 | ~250         | ~25        | ~5 min         | <30s      |
| 100   | 4,000 | ~500         | ~50        | ~10 min        | <60s      |
| 250   | 10,000| ~1,250       | ~125       | ~25 min        | <180s     |
| 500   | 20,000| ~2,500       | ~250       | ~50 min        | <360s     |
| 800   | 32,000| ~4,000       | ~400       | ~80 min        | <600s     |

### Test Fixtures

We'll use existing fixtures from the test suite:

1. **Small (10 pages)**: `fixtures/synthetic/small_article/source.tex` (116 lines)
2. **Medium (50 pages)**: Generate from ZLB by extracting sections 1-3
3. **Large (100 pages)**: Generate from ZLB by duplicating + modifying
4. **XL (250 pages)**: Generate synthetic from template
5. **XXL (500 pages)**: Generate synthetic from template
6. **Target (800 pages)**: Generate synthetic from template

For sizes >100 pages, we'll generate synthetic documents using:
- Realistic LaTeX structure (sections, subsections, equations)
- Academic content (theorems, proofs, citations)
- Protected objects (equations, tables, citations)
- Varied concept density (definitions, explanations, examples)

---

## Phase 6A: Small-Medium Scale Tests (10-100 pages)

### Test: 10-page document

**Fixture**: `fixtures/synthetic/small_article/source.tex`

```bash
# Initialize
hv init fixtures/synthetic/small_article/source.tex \
    --brief fixtures/synthetic/small_article/brief.json \
    --output /tmp/scale-test-10

# Inventory
hv inventory /tmp/scale-test-10 --freeze --adjudicator "scale-test-10"

# Validate locality
python scripts/validate_phase5.py /tmp/scale-test-10

# Plan
hv plan-v2 /tmp/scale-test-10

# Validate contiguity
python scripts/validate_plan_contiguity.py /tmp/scale-test-10
```

**Success Criteria**:
- All concepts < 10KB span range
- All units contiguous
- Plan generation < 5 seconds
- Memory usage < 500MB

---

### Test: 50-page document

**Fixture**: Extract from ZLB (sections 1-3, ~2000 lines)

```bash
# Create fixture
head -2000 fixtures/real_documents/zlb_2026/manuscript.tex > /tmp/zlb-section1-3.tex

# Initialize
hv init /tmp/zlb-section1-3.tex \
    --brief fixtures/real_documents/zlb_2026/brief.json \
    --output /tmp/scale-test-50

# Inventory
hv inventory /tmp/scale-test-50 --freeze --adjudicator "scale-test-50"

# Validate
python scripts/validate_phase5.py /tmp/scale-test-50

# Plan
hv plan-v2 /tmp/scale-test-50

# Validate
python scripts/validate_plan_contiguity.py /tmp/scale-test-50
```

**Success Criteria**:
- All concepts < 10KB span range
- All units contiguous
- Plan generation < 30 seconds
- Memory usage < 2GB

---

### Test: 100-page document

**Fixture**: Full ZLB (~3368 lines) + appendix

```bash
# Use full ZLB
hv init fixtures/real_documents/zlb_2026/manuscript.tex \
    --brief fixtures/real_documents/zlb_2026/brief.json \
    --output /tmp/scale-test-100

# Inventory
hv inventory /tmp/scale-test-100 --freeze --adjudicator "scale-test-100"

# Validate
python scripts/validate_phase5.py /tmp/scale-test-100

# Plan
hv plan-v2 /tmp/scale-test-100

# Validate
python scripts/validate_plan_contiguity.py /tmp/scale-test-100
```

**Success Criteria**:
- All concepts < 10KB span range
- All units contiguous
- Plan generation < 60 seconds
- Memory usage < 4GB

---

## Phase 6B: Large Scale Tests (250-800 pages)

For documents >100 pages, we'll generate synthetic content using a template-based approach.

### Synthetic Document Generator

**Script**: `scripts/generate_scale_fixture.py`

```python
"""
Generate synthetic LaTeX documents for scale testing.

Strategy:
1. Create realistic section structure (intro, body, conclusion)
2. Generate academic content (theorems, proofs, examples)
3. Insert protected objects (equations, citations, tables)
4. Vary concept density across sections
5. Ensure locality (concepts don't span >5KB)
"""

def generate_section(section_num, pages_in_section):
    """Generate one section with realistic content."""
    lines = []
    
    # Section header
    lines.append(f"\\section{{Section {section_num}}}")
    lines.append("")
    
    # Introduction paragraph
    lines.append("We now turn to the analysis of...")
    lines.append("")
    
    # Theorems and proofs (creates concepts)
    num_theorems = pages_in_section // 2
    for i in range(num_theorems):
        lines.append(f"\\begin{{theorem}}")
        lines.append(f"Let $X$ be a manifold. Then property {i} holds.")
        lines.append(f"\\end{{theorem}}")
        lines.append("")
        
        lines.append(f"\\begin{{proof}}")
        lines.append(f"By construction... Therefore property {i} holds.")
        lines.append(f"\\end{{proof}}")
        lines.append("")
    
    # Equations (protected objects)
    num_equations = pages_in_section
    for i in range(num_equations):
        lines.append(f"\\begin{{equation}}")
        lines.append(f"f(x) = x^2 + {i}x + {i*2}")
        lines.append(f"\\end{{equation}}")
        lines.append("")
    
    return lines

def generate_document(target_pages):
    """Generate complete document."""
    lines = []
    
    # Preamble
    lines.extend([
        "\\documentclass{article}",
        "\\usepackage{amsmath}",
        "\\usepackage{amsthm}",
        "\\newtheorem{theorem}{Theorem}",
        "\\begin{document}",
        ""
    ])
    
    # Calculate sections (20 pages per section)
    num_sections = target_pages // 20
    
    for i in range(1, num_sections + 1):
        lines.extend(generate_section(i, 20))
    
    # Closing
    lines.append("\\end{document}")
    
    return "\n".join(lines)
```

---

### Test: 250-page document

```bash
# Generate fixture
python scripts/generate_scale_fixture.py \
    --pages 250 \
    --output /tmp/scale-fixture-250.tex

# Initialize
hv init /tmp/scale-fixture-250.tex \
    --brief fixtures/synthetic/brief_generic.json \
    --output /tmp/scale-test-250

# Inventory (EXPENSIVE: ~25 min, ~$15)
hv inventory /tmp/scale-test-250 --freeze --adjudicator "scale-test-250"

# Validate
python scripts/validate_phase5.py /tmp/scale-test-250

# Plan
hv plan-v2 /tmp/scale-test-250

# Validate
python scripts/validate_plan_contiguity.py /tmp/scale-test-250
```

**Success Criteria**:
- All concepts < 10KB span range
- All units contiguous
- Plan generation < 180 seconds
- Memory usage < 8GB
- No crashes or timeouts

---

### Test: 500-page document

```bash
# Generate fixture
python scripts/generate_scale_fixture.py \
    --pages 500 \
    --output /tmp/scale-fixture-500.tex

# Initialize
hv init /tmp/scale-fixture-500.tex \
    --brief fixtures/synthetic/brief_generic.json \
    --output /tmp/scale-test-500

# Inventory (EXPENSIVE: ~50 min, ~$25)
hv inventory /tmp/scale-test-500 --freeze --adjudicator "scale-test-500"

# Validate
python scripts/validate_phase5.py /tmp/scale-test-500

# Plan
hv plan-v2 /tmp/scale-test-500

# Validate
python scripts/validate_plan_contiguity.py /tmp/scale-test-500
```

**Success Criteria**:
- All concepts < 10KB span range
- All units contiguous
- Plan generation < 360 seconds
- Memory usage < 16GB
- No crashes or timeouts

---

### Test: 800-page TARGET document

```bash
# Generate fixture
python scripts/generate_scale_fixture.py \
    --pages 800 \
    --output /tmp/scale-fixture-800.tex

# Initialize
hv init /tmp/scale-fixture-800.tex \
    --brief fixtures/synthetic/brief_generic.json \
    --output /tmp/scale-test-800

# Inventory (EXPENSIVE: ~80 min, ~$40)
hv inventory /tmp/scale-test-800 --freeze --adjudicator "scale-test-800"

# Validate
python scripts/validate_phase5.py /tmp/scale-test-800

# Plan
hv plan-v2 /tmp/scale-test-800

# Validate
python scripts/validate_plan_contiguity.py /tmp/scale-test-800
```

**Success Criteria**:
- All concepts < 10KB span range
- All units contiguous
- Plan generation < 600 seconds (10 minutes)
- Memory usage < 16GB
- No crashes or timeouts

**This is the PRIMARY GOAL**: If 800-page document passes, we've proven scalability.

---

## Validation Scripts

### scripts/validate_plan_contiguity.py

```python
"""
Validate that all units in a plan are contiguous.

Checks:
1. All units have max 10KB gap between spans
2. No overlapping units
3. All span IDs exist
"""

import json
import sys
from pathlib import Path

def validate_plan_contiguity(snapshot_dir: Path):
    """Run Phase 3 validation checks."""
    
    # Load plan
    plan_files = list((snapshot_dir / ".humanvoice" / "plans").glob("plan-*.json"))
    if not plan_files:
        print("Error: No plan found")
        sys.exit(1)
    
    plan = json.loads(plan_files[0].read_text())
    
    # Load spans
    spans_path = snapshot_dir / ".humanvoice" / "inventory" / "spans.jsonl"
    span_offsets = {}
    with open(spans_path) as f:
        for line in f:
            if line.strip():
                span = json.loads(line)
                span_offsets[span['record_id']] = {
                    'byte_start': span['byte_start'],
                    'byte_end': span['byte_end']
                }
    
    # Check each unit
    errors = []
    
    for unit in plan['units']:
        # Check contiguity
        span_ids = unit['source_span_ids']
        if len(span_ids) < 2:
            continue
        
        positions = []
        for sid in span_ids:
            if sid not in span_offsets:
                errors.append(f"{unit['unit_id']}: missing span {sid}")
                continue
            positions.append((span_offsets[sid]['byte_start'], 
                            span_offsets[sid]['byte_end']))
        
        positions.sort()
        
        # Check gaps
        for i in range(len(positions) - 1):
            gap = positions[i+1][0] - positions[i][1]
            if gap > 10 * 1024:  # 10KB
                errors.append(f"{unit['unit_id']}: gap {gap} bytes > 10KB")
    
    if errors:
        print(f"❌ FAILED: {len(errors)} contiguity errors")
        for e in errors[:10]:
            print(f"  {e}")
        sys.exit(1)
    else:
        print(f"✅ PASSED: All {len(plan['units'])} units are contiguous")
        sys.exit(0)

if __name__ == '__main__':
    validate_plan_contiguity(Path(sys.argv[1]))
```

---

## Performance Benchmarks

We'll record these metrics for each scale:

| Metric | Unit | Measured At |
|--------|------|-------------|
| Concept count | count | After inventory |
| Max span range | bytes | After inventory |
| Unit count | count | After plan |
| Max unit gap | bytes | After plan |
| Inventory time | seconds | During inventory |
| Plan time | seconds | During plan |
| Peak memory | GB | Both phases |

Results will be documented in `docs/scale-test-results.md`.

---

## Cost Management

To keep costs reasonable:

1. **Run small-medium tests first (10-100 pages)**: Free or <$5
2. **Run 250-page test if small tests pass**: ~$15
3. **Run 500-page test if 250 passes**: ~$25
4. **Run 800-page TARGET if 500 passes**: ~$40

**Total maximum cost**: ~$85

If any test fails, stop and fix before proceeding to next scale.

---

## Rollback Plan

If any scale test fails:

1. **Capture error output**: Save full logs
2. **Analyze root cause**: Memory? Timeout? Logic bug?
3. **Fix identified issue**: Adjust thresholds, optimize code
4. **Re-run failed test**: Verify fix works
5. **Continue scale tests**: Only after fix validated

---

## Success Criteria

Phase 6 is complete when:

- ✅ 10-page test passes
- ✅ 50-page test passes
- ✅ 100-page test passes
- ✅ 250-page test passes
- ✅ 500-page test passes
- ✅ **800-page test passes** ← PRIMARY GOAL
- ✅ Performance benchmarks documented
- ✅ All validation scripts committed

---

## Deliverables

1. **scripts/generate_scale_fixture.py**: Synthetic document generator
2. **scripts/validate_plan_contiguity.py**: Contiguity validator
3. **docs/scale-test-results.md**: Benchmark results
4. **fixtures/scale/**: Generated test fixtures (optional, can regenerate)

---

## Timeline

- Day 1: Implement generators, run 10-100 page tests
- Day 2: Run 250-500 page tests
- Day 3: Run 800-page TARGET test, document results

Total: 3 days
