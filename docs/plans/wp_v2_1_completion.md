---
work_package: WP-V2-1
gate: V2-G1
completed: 2026-09-11
status: satisfied
---

# WP-V2-1 Completion: Semantic Source Model and Readiness Gate

## Gate V2-G1 Requirements

**V2-G1:** every schema has valid and invalid examples; rewriting rejects uncovered spans, unresolved classification, dangling dependencies, missing obligations, and invalid exact-object links.

## Deliverables

### 1. Readiness Gate (`src/humanvoice/readiness.py`, 797 lines, 49 tests)

Implements the five V2-G1 rejection conditions:

- **span_coverage**: byte-exact partition validation with gap and overlap detection
- **classification_resolved**: no unresolved spans, concepts, or scaffolding dispositions
- **dependency_integrity**: all endpoints resolve, no cycles
- **obligation_presence**: every concept has active obligations assigned to units
- **protected_object_links**: all protected references resolve to manifest objects

**Critical property**: fail-closed. An empty bundle passes `validate_bundle([])` because every check is conditional on records existing. The readiness gate returns `ready=False` unless all five checks actually ran.

Entry points:
- `assess_readiness(records)` → Readiness verdict with blockers
- `assert_ready_to_rewrite(records)` → raises NotReadyToRewrite if not ready

### 2. Source Partitioner (`src/humanvoice/partition.py`, 674 lines, 52 tests)

Deterministic byte-addressed span generation for LaTeX source:

- Prose, headings, comments, math, floats, bibliography, commands, whitespace
- Validates against ZLB manuscript: 189,829 bytes → 1,751 spans, exact roundtrip
- Validates against full proposal tree: 57 files, 2.08 MB → 13,385 spans
- `verify_partition()` detects gaps and overlaps the bundle validator missed

### 3. Source Map (`src/humanvoice/source_map.py`, 429 lines, 30 tests)

Consolidates two protected-object representations behind one contract:

- Unified `MappedObject` with source location, normalized form, content hash
- Bake-off support retained: parser generates candidates, verifier selects
- `link_objects_to_spans()` produces exact byte ranges for equations, citations, numbers

### 4. Brief Unification (`src/humanvoice/brief.py`, 172 lines, 24 tests)

Separates schema errors from critical blanks:

- `validate_brief()` distinguishes malformed structure from "TBD" placeholders
- Empty `policy_sources` array (schema invalid) and blank approver both block, documented separately

### 5. Schema Examples

Added missing invalid examples to complete V2-G1:
- `runtime-manifest-missing-activity.invalid.json`
- `semantic-preflight-result-missing-verifier.invalid.json`

All 21 v2 record types now have both valid and invalid examples (44 total in manifest).

## Verification

```
$ python -m pytest tests/ tools/ -q
530 passed, 2 xfailed in 39.33s

$ python tools/check_implementation_contract.py
PASS implementation_contract_v2
PASS catalogue_and_schema_alignment
PASS shared_registry_and_semantic_examples
PASS R1-R29_requirement_register
PASS v1_v2_migration_boundary
PASS release_and_runtime_invariants
STATE specified

$ python tools/check_program_consistency.py
PASS v2_program_structure_and_gates
PASS change_record_and_requirement_register
PASS contract_and_catalogue_alignment
PASS fixture_lifecycle_and_rights_rules
PASS historical_locator_registry
INFO fixture_readiness not-applicable=0 planned=12 ready=4 unavailable=0
STATE specified
PASS V2-G0_ready
```

## Next Steps

V2-G1 satisfied. The gate exists and is tested. Runtime wiring happens when the v2 commands that need it are implemented:

- **WP-V2-2**: `hv inventory` and `hv plan` will build the concept baseline the gate checks
- **WP-V2-3**: `hv rewrite` will call `assert_ready_to_rewrite()` before making inference calls

Wiring the gate into v1 commands (`draft_command.py`, `plan_command.py`) would be type-incoherent—those operate on ArgumentBlueprint/AuthoringBrief, while the gate checks ConceptBaseline/SourceConcept/ExplanationObligation.

## Line Counts

| Module | Source | Tests |
|--------|--------|-------|
| readiness | 797 | 546 |
| partition | 674 | 347 |
| source_map | 429 | 386 |
| brief | 172 | 321 |
| **Total** | **2,072** | **1,600** |

Total with tests: 3,672 lines
