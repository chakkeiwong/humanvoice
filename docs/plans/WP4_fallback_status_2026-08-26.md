# WP4 status - authoring extension (fallback mode)

**Date:** 2026-08-26  
**Program version:** 1.1 (prototype scale)  
**Work package:** WP4 - authoring extension (weeks 6-9)  
**Status:** Fallback mode - structure delivered, inference unavailable

## Environment constraint

**Inference runtime:** Not installed (llama.cpp not found)  
**Model artifact:** None available on host  
**Contract fallback rule:** "The deterministic protected-core path may continue when inference is unavailable, but it cannot claim a full writing/reconstruction release."

Per implementation contract runtime.inference.fallback_rule, WP4 cannot proceed to a full authoring release without:
- llama.cpp runtime (exact commit pinned)
- Model artifact with verified SHA-256
- Prompt template with recorded hash
- Calibration and held-out replay on exact configuration

## What WP4 delivers in fallback mode

### Model adapter structure
- **Module:** `src/humanvoice/model.py` (235 lines)
- **Interface:** `ModelAdapter` with schema-validated invocation
- **T4 compliance:** Model output is delimited JSON, no tool authority
- **Mock mode:** Returns schema-compliant JSON for testing without inference
- **Production path:** Ready for llama.cpp integration when runtime available

### Schemas for bounded authoring
- `PLAN_SCHEMA`: Blueprint with sections, evidence, word budget
- `DRAFT_SCHEMA`: LaTeX output with word count, citations needed
- `REPAIR_SCHEMA`: Located changes with original/revised/rationale

### Command stubs
Already present in `src/humanvoice/cli.py`:
- `hv plan` - returns "not implemented yet (requires WP4)"
- `hv draft` - returns "not implemented yet (requires WP4)"
- `hv repair` - returns "not implemented yet (requires WP4)"

## What works now (deterministic path)

```bash
# Protected-core commands (no inference needed)
hv init source.tex --brief brief.json --output snapshot/
hv preflight snapshot/ --brief brief.json --deterministic

# Verification harnesses
python3 tools/run_fixture_suite.py      # 4/4 fixtures pass
python3 tools/run_mutation_replay.py    # 9/9 mutations caught
```

**Status:** 71 tests passing, G1 protected-core gate satisfied

## G2 authoring-extension gate (blocked)

Per v1.1 §5 G2 gate (end of week 9):

| Criterion | Status | Evidence |
|---|---|---|
| Exact runtime, model artifact, tokenizer hashes recorded | ✗ | No inference runtime installed |
| Calibration and held-out results measured | ✗ | Cannot run without model |
| Critics report FP/FN/abstentions/burden | ✗ | Requires model invocation |
| Bounded writer cannot widen evidence boundary | ✗ | No writer to test |
| Repair passes mutation tests and stops at 3 cycles | ✗ | No repair to test |

**Gate decision:** BLOCKED. Cannot proceed to G2 without inference runtime and model artifact.

## What's needed to unblock WP4

1. **Install llama.cpp:**
   ```bash
   git clone https://github.com/ggerganov/llama.cpp
   cd llama.cpp
   git checkout <specific-commit>  # Record in runtime manifest
   make
   ```

2. **Download model artifact:**
   - Qwen3-8B-Instruct GGUF Q4_K_M (reference candidate per contract)
   - OR Llama-3.1-8B-Instruct GGUF Q4_K_M (fallback candidate)
   - Compute SHA-256, record in runtime manifest

3. **Implement bounded authoring commands:**
   - `hv plan`: Parse brief → generate blueprint JSON → validate against PLAN_SCHEMA
   - `hv draft`: Blueprint + evidence → generate LaTeX → validate against DRAFT_SCHEMA
   - `hv repair`: Findings + source → generate repairs → validate against REPAIR_SCHEMA
   - Repair cycle limit (max 3) and oscillation detection

4. **T4 verification:**
   - Create fixture with instruction-looking LaTeX comments
   - Verify model output cannot acquire tool authority
   - Add to threat fixture suite as F-THREAT-T4-INJECTION

5. **Calibration and mutation testing:**
   - Run repair on seeded mutations
   - Measure false positive/negative rates
   - Record operator burden (review time, disposition decisions)

## Fallback-mode deliverables summary

| Component | Status | Notes |
|---|---|---|
| Model adapter structure | ✓ | Schema validation, T4-compliant interface |
| Command stubs | ✓ | Return "not implemented" with clear message |
| Bounded schemas | ✓ | Plan, draft, repair JSON contracts defined |
| Inference runtime | ✗ | llama.cpp not installed |
| Model artifact | ✗ | No GGUF model on host |
| T4 verification | ⏸ | Requires model invocation to test |
| Repair cycles | ⏸ | Requires model invocation to test |

## Recommendation

**Option 1 (continue in fallback):** Deliver WP1–WP3 protected-core as a feasibility prototype. The deterministic path (parser, comparison, mutation detection) is complete and verified. Document that authoring extension requires inference runtime.

**Option 2 (install runtime):** Install llama.cpp + model artifact (~5GB download), implement bounded authoring, run calibration. This extends timeline but delivers full WP4.

**Option 3 (mock-only WP4):** Implement authoring commands with mock responses that pass schema validation. Demonstrates structure and JSON contracts without actual model outputs. Clearly document that text generation quality is untested.

The contract's fallback rule permits Option 1: "The deterministic protected-core path may continue when inference is unavailable." The protected-core (WP1–WP3) is a valid deliverable without authoring.

## Current state

- **Protected-core:** Complete, verified, G1 gate satisfied
- **Authoring extension:** Structure defined, inference blocked
- **Next gate:** G2 requires model artifact and calibration
- **Release claim:** Protected-review utility only (not full authoring)
