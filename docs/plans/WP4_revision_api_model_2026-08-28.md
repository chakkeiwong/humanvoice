# WP4 Revision — API model adoption

**Date:** 2026-08-28  
**Supersedes:** `docs/plans/WP4_completion_2026-08-27.md`  
**Status:** Decision to revise contract inference requirements  
**Decision maker:** User (project owner)

## Decision

Adopt Claude or GPT API for authoring commands instead of local llama.cpp with pinned GGUF artifacts. Test behavioral properties (schema conformance, abstention behavior, structural bounds) rather than cryptographic token-sequence replay.

## Rationale

**The contract's T5 and reproducibility requirements were over-specified for humanvoice's actual use case.**

Humanvoice targets **human understanding** — helping technical authors produce clearer documents. The threat model is ordinary human defects (unclear writing, missing evidence, register drift), not adversarial model manipulation or safety-critical byte-identical execution.

**What matters for this use case:**
1. Does the draft prose make concepts clearer for human readers?
2. Does the workflow catch structural defects (register violations, missing evidence, oscillating repairs) before human review?
3. Can a reviewer trust the output? (Protected core provides this via parser-based checks, no execution of model output)
4. Is the system honest about uncertainty? (Abstention mechanism)

**What cryptographic replay provides:**
- Bit-identical token sequences across runs
- Independent audit via artifact hash verification
- Provably no cherry-picking of results

**Why this doesn't fit humanvoice:**
- Human readers judge clarity subjectively — token sequences are implementation detail
- The protected core (deterministic checks) provides safety; the model drafts prose which humans review anyway
- The workflow never auto-promotes `author_repaired_draft` to `human_accepted`
- Running local 3B/8B models produces unusable prose quality; 27B helps but still not publishable
- This machine has 4×48GB GPUs but the contract's requirements push toward CPU-only inference

**API models (Claude Opus 5, GPT-5) provide:**
- Actually publishable prose quality
- Faster iteration during prototype phase
- Behavioral reproducibility (same brief + model version → outputs satisfying same structural properties)
- Property-based testing across multiple runs shows system reliability

## Contract changes required

### Section: `runtime.inference`

**Current (line 60-70):**
```json
"inference": {
  "runtime": "llama.cpp",
  "runtime_revision": "exact commit required in runtime manifest",
  "reference_model_candidate": "Qwen3-8B-Instruct GGUF Q4_K_M",
  "fallback_model_candidate": "Llama-3.1-8B-Instruct GGUF Q4_K_M",
  "artifact_sha256": "required before invocation",
  "prompt_template_hash": "required before invocation",
  "full_path_rule": "A model-dependent writing or reconstruction gate may enter release only after calibration and held-out replay on the exact runtime, model artifact, and prompt template.",
  "change_rule": "Any runtime, model, quantization, prompt-template, tokenizer, or sampling change invalidates the affected calibration and held-out results and requires replay before release.",
  "fallback_rule": "The deterministic protected-core path may continue when inference is unavailable, but it cannot claim a full writing/reconstruction release."
}
```

**Revised:**
```json
"inference": {
  "runtime": "API (Claude or OpenAI)",
  "model_version": "exact version string required in runtime manifest (e.g., claude-opus-5-20250815, gpt-4-turbo-2024-04-09)",
  "artifact_sha256": "not applicable (API models)",
  "prompt_template_hash": "required before invocation",
  "reproducibility_level": "behavioral",
  "behavioral_properties": [
    "schema conformance (validates against PLAN_SCHEMA/DRAFT_SCHEMA/REPAIR_SCHEMA)",
    "abstention behavior (abstains when evidence missing or contradictory)",
    "structural bounds (respects word budgets, max 3 repair cycles)",
    "register compliance (follows brief constraints)",
    "mutation response (abstains gracefully or produces detectably broken output on corrupted input)"
  ],
  "testing_rule": "Property-based testing across multiple API calls demonstrates behavioral consistency. Record model version, timestamp, input fixture hash, full response, and test verdict (pass/fail on properties) for each test run.",
  "full_path_rule": "A model-dependent writing or reconstruction gate may enter release only after property-based validation on held-out fixtures using the declared model version.",
  "change_rule": "Any model version, prompt-template, or sampling parameter change requires re-validation on held-out fixtures before release.",
  "fallback_rule": "The deterministic protected-core path may continue when inference is unavailable, but it cannot claim a full writing/reconstruction release.",
  "limitation_disclosure": "Reproducibility is behavioral, not cryptographic. The same brief + model version produces outputs satisfying the same structural and semantic properties, but exact token sequences may vary across runs. Independent auditors can validate behavior by running the same property tests; they cannot cryptographically verify historical token sequences."
}
```

### Section: `record_policy.record_requirements.RuntimeManifest`

**Current (line 99):**
```json
"RuntimeManifest": ["runtime_revision", "model_artifact_hash", "tokenizer_hash", "prompt_template_hash", "sampling", "seed", "hardware", "network_policy", "resource_limits", "latency_ms", "peak_memory_mib", "output_hash", "not_applicable_reason"]
```

**Revised:**
```json
"RuntimeManifest": ["runtime_type", "model_version_string", "model_artifact_hash_if_local", "prompt_template_hash", "sampling", "seed_if_applicable", "api_endpoint", "request_id_if_available", "timestamp", "latency_ms", "input_tokens", "output_tokens", "output_hash", "not_applicable_reason"]
```

### Section: `trust_boundary.controls` (T4 remains unchanged, T5 applies to API timeout)

T4 already correctly treats model output as data, not instructions. T5 applies timeout limits to API calls just as it would to local inference.

## What was delivered in WP4 (prior work)

The llama.cpp environment setup from `WP4_completion_2026-08-27.md` established:
- Inference profile structure (`security/inference_profile.json`)
- Prompt template with hash (`security/prompt_template_critic.txt`)
- Schema-derived grammars for constrained generation (concept still useful for local fallback)
- Model adapter architecture (`src/humanvoice/model.py`)
- Schema validation and abstention mechanism

**These components remain useful:**
- The adapter architecture adapts to API calls instead of llama.cpp invocation
- Prompt template hashing still applies
- Schema validation and abstention logic unchanged
- The profile structure extends to record API model version instead of artifact hash

## Implementation changes needed

1. **Update `security/inference_profile.json`:**
   - Change `runtime` from "llama.cpp" to "claude-api" or "openai-api"
   - Replace `artifact_sha256` with `model_version_string` (e.g., "claude-opus-5-20250815")
   - Add `api_endpoint` field
   - Remove `bubblewrap` isolation (not applicable to API calls; T3 network control handled differently)

2. **Rewrite `src/humanvoice/model.py` adapter:**
   - Replace `_invoke_llama_cpp()` with `_invoke_api()`
   - Use `anthropic` or `openai` Python SDK
   - Schema validation remains client-side (validate API response against PLAN/DRAFT/REPAIR schemas)
   - Abstention logic unchanged
   - Remove hash verification (not applicable)
   - Add API timeout (T5 control)

3. **Create property-based test suite:**
   - `tests/test_model_properties.py`
   - Test schema conformance, abstention behavior, bounds compliance, register compliance
   - Test mutation response (corrupted briefs trigger abstention or detectable failure)
   - Run each test N times (N=10-50 depending on criticality) to verify behavioral consistency
   - Record: model version, timestamp, input hash, output, verdict

4. **Update contract schema:**
   - `schemas/implementation_contract.json` with revised inference section
   - Bump `contract_version` to "1.1.0"
   - Add migration record explaining the change

5. **Update master program:**
   - Document the contract revision in program v1.2
   - Update WP4 deliverables to reflect API model approach
   - Revise G2 (authoring-extension gate) success criteria to reference behavioral property tests instead of mutation replay with pinned artifacts

## What we lose

- **Cryptographic token-sequence replay:** Cannot verify that historical runs produced exactly those tokens
- **Independent artifact verification:** Auditors cannot download and hash-verify the exact model that ran
- **Airgapped operation:** API calls require network access (violates original T3 for model invocation, though T3 still applies to parser/compiler)

## What we keep

- **All protected-core safety:** Parser-based checks, no execution of model output, register violation detection
- **Schema validation and abstention:** Client-side validation of API responses
- **Behavioral reproducibility:** Property-based testing shows system works reliably
- **Human-in-loop review:** Workflow never auto-accepts; humans make final decisions
- **Isolation for LaTeX compilation:** T1-T3 still fully apply to parser/compiler (the risky part); model is just drafting prose

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| API model versions change behavior silently | Pin exact version strings; re-validate on version changes; monitor vendor changelogs |
| API downtime blocks authoring workflow | Deterministic protected-core path continues (fallback rule); authoring is optional extension |
| Cost unpredictability | Set per-document token budget cap; monitor usage; fail explicitly on budget exceeded |
| Network dependency violates airgap requirement | Document: airgap applies to parser/compiler (untrusted code execution), not prose generation (validated data output) |
| Behavioral tests miss edge cases that bit-identical replay would catch | Expand property test coverage based on mutation suite; treat any behavioral inconsistency as a test failure |

## Status

- **Decision:** Approved by user (project owner) 2026-08-28
- **Contract revision:** Pending (this document defines required changes)
- **Implementation:** Not started (llama.cpp environment exists but will be replaced)
- **Testing approach:** Property-based behavioral validation defined, not yet implemented

## Next action

1. Revise `schemas/implementation_contract.json` (contract version 1.1.0)
2. Write contract change migration record
3. Update `security/inference_profile.json` for API model
4. Rewrite `src/humanvoice/model.py` with API adapter
5. Implement property-based test suite
6. Implement `hv plan` / `hv draft` / `hv repair` commands against API model
7. Run behavioral validation suite on held-out fixtures
8. Update master program to v1.2 reflecting revised WP4 scope

The local llama.cpp artifacts (`/tmp/llama.cpp/`, `/tmp/models/`) can remain as a fallback option for future work, but are not part of the main workflow.
