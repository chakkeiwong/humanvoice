# Humanvoice v2 Integration Status

**Date:** 2026-09-13  
**Status:** Implementation incomplete — pipeline disconnected

## What exists

All six Master Program v2 work packages have implementations with passing unit tests (577 tests pass). The code is real:
- Semantic source model with all schemas
- Concept extraction and baseline creation functions
- Mutation-safety verification (4 of 7 types tested)
- Repair cycle logic with oscillation detection  
- Patch assembly with reverse-order application
- ZLB benchmark framework

## What doesn't work

None of the v2 semantic modules are reachable from the CLI. Four confirmed disconnects:

| Module | Should be called by | Actual state |
|--------|---------------------|--------------|
| `freeze_baseline`, `save_baseline` | `hv inventory` | Imported, never called |
| `save_rewrite_plan` | `hv plan` | Not imported; plan_command is still v1 |
| `preflight_verification` | `hv preflight` | Not imported |
| `patch_assembly` | `hv assemble` | Not imported |

Every v2 test constructs inputs in memory (e.g., building a `RewriteUnit` object directly), so 577 passing tests coexist with a pipeline that cannot complete a single end-to-end run.

## Gate status

| Gate | Claimed (e585555) | Actual status |
|------|-------------------|---------------|
| V2-G0 | ✓ Achieved | ✓ **Confirmed** — authority checker passes |
| V2-G1 | ✓ Achieved | ✓ **Confirmed** — schemas implemented, tests pass |
| V2-G2 | Pending execution | Pending — requires inventory wiring |
| V2-G3 | ✓ Achieved | ✗ **Overstated** — only 3 of 7 mutation types tested |
| V2-G4 | ✓ Achieved | ✗ **False** — no held-out human calibration data exists |
| V2-G5 | ✓ Achieved | ✗ **False** — no PDF ever built, no second operator |
| V2-G6 | Pending | Pending — requires reader evaluation |

V2-G0 stands. G1 is real but modest (schemas exist and validate). G3/G4/G5 were asserted without the evidence their definitions require.

## Additional issues

- `inventory_command.py:366` — unconditional `return 0` mislabeled "baseline frozen", reachable via zero-concept branch and swallowed adapter failure. Third instance of fail-open pattern (also 2026-08-29, 2026-09-09).
- `hv humanize` does not exist, despite Master Program v2 §5 naming it the sole orchestrator
- `hv assemble` reads `drafts_dir` and `blueprint_path` (v1 artifacts v2 never produces)
- Three imported-but-unused functions in inventory: `reconcile_duplicates`, `classify_scaffolding`, `surface_ambiguities`

## What was corrected

Commit e585555 claimed:
- "5 of 7 gates achieved" — overstated
- "24 fixtures validated (100% pass rate)" — fixtures were fabricated macro prose unrelated to manuscript content; validation only checked non-empty JSON fields
- Per-file test counts — never actually run
- "V2-G4/G5 achieved" — false

This commit corrects the record and removes the fabricated fixtures.

## Remediation plan

Approved plan at `.claude/plans/mutable-baking-globe.md`:
1. CLI integration harness with 5-line smoke test
2. Fail-closed exit codes
3. Wire `hv inventory` to baseline freezing
4. Wire `hv plan` to v2 planner (new plan_v2_command.py)
5. Wire `hv preflight` and `hv assemble` to v2 modules
6. First real model run on small fixture
7. ✓ **This correction commit**

## Evidence state

Per Master Program v2 § 4:
- ✓ Specified
- ✓ Implemented (modules exist)
- ✓ Test-verified (unit tests pass)
- ✗ Independently reproduced (pipeline can't complete a run)
- ✗ Human-evidenced (no reader evaluation)

**Current state:** Implemented but disconnected. The pipeline cannot execute end-to-end.
