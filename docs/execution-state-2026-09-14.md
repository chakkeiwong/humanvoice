# Humanvoice v2 Integration Remediation: Execution State
**Date:** 2026-09-14  
**Status:** Blocked on model initialization bug  
**Current Phase:** Item 6 of remediation plan (First real model run)

---

## Goal

Execute the complete v2 pipeline end-to-end on a small fixture to validate integration. This is remediation plan item 6: "First real model run on small fixture."

---

## Governing Program

**Master Program v2** (`docs/plans/humanvoice_master_program_v2.md`) is the authoritative specification. Key points:

- **Product mission (§1):** Fidelity-preserving humanization of finished AI-drafted manuscripts, measured against frozen concept baselines
- **Authority (§2):** This program, survey, R1-R29 requirements, contract, schemas, inference profile
- **Non-negotiable invariants (§5):**
  - `hv humanize` is sole production orchestrator (not yet implemented)
  - 1.0 retention over frozen baseline
  - No concept deletion or compression
  - Protected objects (equations, citations, labels) must be byte-identical
  - ~2000-word estimate triggers decomposition, never compression
- **Work packages (§6):** WP-V2-0 through WP-V2-6, each with a gate
- **Evidence states (§4):** specified → implemented → test-verified → independently-reproduced → human-evidenced

**Remediation Plan** (`.claude/plans/mutable-baking-globe.md`) documents the integration problem:

- Root cause: v2 modules exist but are orphaned from CLI commands
- `hv inventory` stops after partitioning; never calls `freeze_baseline` or `save_baseline`
- `hv plan` is still the v1 blueprint generator
- `hv preflight` and `hv assemble` don't import v2 modules
- 577 tests pass because they construct inputs in memory, never exercise CLI boundaries

**Current status claim in `docs/master-program-v2-status-final.md`:**
- Claims "All WP-V2-0 through WP-V2-6 implementation complete"
- Claims "127 tests passing, 24 fixtures validated"
- Claims gates V2-G1, V2-G3, V2-G4, V2-G5 complete
- **However:** remediation plan shows these claims are based on in-memory tests that don't exercise the actual CLI pipeline

---

## Current Execution State

### What Has Been Completed

1. **Snapshot creation successful** (remediation plan item 1, init phase)
   - Fixture: `fixtures/synthetic/equation/001.tex` (22 lines, 4 equations including inline and display)
   - Brief: `fixtures/synthetic/equation/brief.json` (valid v2 HumanizationBrief)
   - Snapshot: `test_output/equation_snapshot/`
   - Snapshot ID: `snapshot-20260914-091151`
   - Source hash: `5f775273a32a7ed4da2c92e6f5526719261d6260bc384e98b6ec8bc90738a432`
   - Protected objects: 2 extracted with 100% parser agreement
   - Exit code: 0

2. **Source partitioning successful** (inventory Phase 1)
   - Command: `hv inventory test_output/equation_snapshot --freeze --adjudicator test-harness`
   - Spans created: 20 spans covering 436 bytes
   - Output: `test_output/equation_snapshot/.humanvoice/inventory/spans.jsonl`
   - Exit code: 3 (partial failure, continued to later phases)

### What Is Blocked

3. **Baseline creation BLOCKED** (inventory Phase 4)
   - Command attempted: `hv inventory --freeze`
   - Blocker: ModelConfig.from_profile() contract violation
   - Error: "Contract violation: prompt_template_hash is required before invocation"
   - Location: `src/humanvoice/model.py:129-132`
   - Exit code: 3

4. **All downstream phases BLOCKED**
   - `hv plan` requires frozen baseline (exits 3 without it)
   - `hv rewrite` requires plan
   - `hv preflight-v2` requires rewrite output
   - `hv assemble-v2` requires preflight results

---

## Root Cause: Model Initialization Bug

### The Bug

**File:** `src/humanvoice/model.py`  
**Method:** `ModelConfig.from_profile()` (lines 106-143)  
**Line 127:**
```python
template = profile.get("prompt_template", {})  # BUG: singular key
```

**Actual JSON structure** in `security/inference_profile.json` (lines 28-61):
```json
"prompt_templates": {
  "v1_critic": {...},
  "v2_extraction": {...},
  "v2_reconstruction": {...},
  "v2_coverage": {...},
  "v2_rewrite": {...}
}
```

### The Problem

1. Code looks for `"prompt_template"` (singular)
2. JSON has `"prompt_templates"` (plural)
3. This causes `template` to be an empty dict `{}`
4. So `template.get("template_sha256")` returns `None`
5. Validation at line 129-132 fails: `if not template_hash or template_hash == "pending"`
6. Raises: `ValueError("Contract violation: prompt_template_hash is required before invocation")`

### Why This Is Wrong

The SHA256 hashes ARE present in the inference profile and ARE correct:
- `v2_extraction`: `0dfac2c2556a7f66d6068b24615097c7be955d3dfcdae6c847ba1ab5f40b8d05`
- `v2_reconstruction`: `a85287c431c60e0741e24ce8bd70dff3416d246303e27f302e5cbde6fc4eed90`
- `v2_coverage`: `08989aa25f1a18903ff93ce4550e94069d9d8e57130e1541c84bfd83a0604d00`
- `v2_rewrite`: `8c24fca27d0392f22f017e7bd76ddccb1fc1a73cdd1ddbe68e1af93784fff5d1`

The problem is a **key/path mismatch bug** in the code, not missing configuration.

### Design Question

The inference profile contains **multiple templates** with **separate hashes**. The current code expects a **single hash**. Need to determine:

**Option A:** Change code to read the correct key (`prompt_templates`) and select one template  
**Option B:** Change code to validate all active v2 templates  
**Option C:** Change JSON structure to have a single combined hash

---

## Secondary Issue: Protected Object Linking Bug

**File:** `src/humanvoice/commands/inventory_command.py:142`  
**Error:** `from_parser_objects() takes 1 positional argument but 2 were given`  
**Impact:** Non-blocking warning; protected objects not linked to spans  
**Priority:** Fix after model initialization bug

---

## Previous Execution Artifacts

### Successfully Created

- `test_output/equation_snapshot/manifest.json`
- `test_output/equation_snapshot/source/001.tex`
- `test_output/equation_snapshot/.humanvoice/brief.json`
- `test_output/equation_snapshot/.humanvoice/protected_objects/objects.json`
- `test_output/equation_snapshot/.humanvoice/inventory/spans.jsonl` (20 spans, 436 bytes)

### Missing (Blocked)

- `test_output/equation_snapshot/.humanvoice/inventory/baseline.json` (cannot create without model)
- All downstream artifacts (plan, rewrite results, preflight results, assembled output)

---

## Next Steps

### Immediate Action Required

1. **Resolve design question:** Which template hash(es) should ModelConfig.from_profile() validate?
2. **Fix model.py line 127:** Update key lookup to match actual JSON structure
3. **Test fix:** Re-run `hv inventory --freeze --adjudicator test-harness`
4. **Verify:** Check that baseline.json is created

### After Model Bug Fixed

5. Run `hv plan` (should now succeed with frozen baseline)
6. Run `hv rewrite --mock` (should create rewrite units)
7. Run `hv preflight-v2` (should verify concept correspondence)
8. Run `hv assemble-v2` (should apply patches and verify byte-identity)
9. Verify end-to-end completion with exit code 0 at every phase

### After Mock Pipeline Succeeds

10. Execute with live model on equation/001.tex (22 lines)
11. Execute with live model on large_report (116 lines)
12. Expect schema failures and malformed concept IDs (this is the test)

---

## Key Files

### Governing Documents
- `docs/plans/humanvoice_master_program_v2.md` - Master Program v2 specification
- `.claude/plans/mutable-baking-globe.md` - Remediation plan
- `docs/master-program-v2-status-final.md` - Status claims (needs correction per remediation plan)

### Blocking Bug
- `src/humanvoice/model.py:127` - Key mismatch bug
- `security/inference_profile.json` - Actual structure (correct hashes present)

### Pipeline Commands
- `src/humanvoice/commands/inventory_command.py` - Calls ModelConfig.from_profile()
- `src/humanvoice/commands/plan_v2_command.py` - Requires frozen baseline
- `src/humanvoice/commands/rewrite_command.py` - Requires plan
- `src/humanvoice/commands/preflight_v2_command.py` - Requires rewrite output
- `src/humanvoice/commands/assemble_v2_command.py` - Requires preflight results

### Test Artifacts
- `test_output/equation_snapshot/` - Current snapshot with partial inventory
- `fixtures/synthetic/equation/001.tex` - 22-line test fixture
- `fixtures/synthetic/equation/brief.json` - Valid v2 brief

---

## Verification Commands

After fixing the model bug, verify with:

```bash
# Should exit 0 and create baseline.json
hv inventory test_output/equation_snapshot --freeze --adjudicator test-harness

# Should exit 0 and create plan
hv plan test_output/equation_snapshot

# Should exit 0 and create rewrite results
hv rewrite test_output/equation_snapshot --baseline-id <id> --plan-id <id> --mock

# Should exit 0 with status: pass
hv preflight-v2 test_output/equation_snapshot

# Should exit 0 with assembly_complete: true
hv assemble-v2 test_output/equation_snapshot
```

---

## Context for New Agent

**You are picking up mid-execution of the v2 integration remediation plan.** The goal is to execute the first real model run on a small fixture to prove the v2 pipeline works end-to-end.

**Current blocker:** Model initialization fails due to a key mismatch bug in `model.py:127`. The code looks for `"prompt_template"` (singular) but the JSON has `"prompt_templates"` (plural). The hashes ARE present and correct in the file.

**What was NOT done yet:** The summary from the compacted session claimed that "Hash v2 prompt templates into inference profile" was completed, but this was revealed to be incorrect - the hashes ARE in the file, but there's a code bug preventing them from being read.

**Immediate decision needed:** The inference profile has 5 separate template hashes. The code expects a single hash. Determine the correct fix before modifying code.

**Do not:** Retry commands that already failed, re-read files that were already read (check summary first), or assume the status document claims are accurate (the remediation plan documents why they're not).

**Do:** Fix the model.py bug, verify the fix works, then continue through the pipeline phases in order.
