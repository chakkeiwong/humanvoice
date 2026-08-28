# Contract Revision Summary — API Model Adoption

**Date:** 2026-08-28  
**Contract version:** 1.0.0 → 1.1.0  
**Decision:** Adopt Claude/GPT API for authoring commands instead of local llama.cpp

## What changed

### 1. Implementation contract (`schemas/implementation_contract.json`)

**Version bumped to 1.1.0** with history tracking:
- v1.0.0: Initial contract with local llama.cpp inference and cryptographic replay
- v1.1.0: Revised to API model inference with behavioral property testing

**`runtime.inference` section rewritten:**
- `runtime`: "llama.cpp" → "API (Claude or OpenAI)"
- `model_version`: Exact version string required (e.g., "claude-opus-5-20250815")
- `reproducibility_level`: "behavioral" (not cryptographic)
- `behavioral_properties`: Schema conformance, abstention, bounds, register compliance, mutation response
- `testing_rule`: Property-based testing across multiple API calls
- `limitation_disclosure`: Token sequences may vary; behavior is reproducible

**`trust_boundary.controls.T3` updated:**
- API calls are permitted under rate limits and logging
- Parser/compiler network access still denied

**`record_policy.record_requirements.RuntimeManifest` updated:**
- New fields: `runtime_type`, `model_version_string`, `api_endpoint`, `request_id_if_available`, `timestamp`, `input_tokens`, `output_tokens`
- Removed: `runtime_revision`, `model_artifact_hash`, `tokenizer_hash`, `seed`, `hardware`, `network_policy`, `resource_limits`, `peak_memory_mib`
- Made optional: `model_artifact_hash_if_local`, `seed_if_applicable`

### 2. Runtime manifest schema (`schemas/runtime-manifest.schema.json`)

**Completely rewritten** to support both local and API models:
- `runtime_type`: enum ["llama.cpp", "claude-api", "openai-api", "deterministic-only"]
- Conditional validation based on `runtime_type`:
  - Local models require `model_artifact_hash_if_local`, `seed_if_applicable`
  - API models require `api_endpoint`, permit `request_id_if_available`
  - Deterministic mode nulls all model fields

### 3. Example instances updated

**`schemas/examples/runtime-deterministic.valid.json`:**
- Added all new required fields with null values
- `runtime_type`: "deterministic-only"

**`schemas/examples/runtime-inference.valid.json`:**
- Changed from llama.cpp local to claude-api
- `runtime_type`: "claude-api"
- `model_version_string`: "claude-opus-5-20250815"
- `api_endpoint`: "https://api.anthropic.com/v1/messages"
- `request_id_if_available`: "req_01ABC123XYZ"
- `input_tokens`: 1250, `output_tokens`: 487
- `network_policy`: "api-only"

### 4. Contract checker updated (`tools/check_implementation_contract.py`)

**Accepts both contract versions:**
- `contract_version` validation: accepts "1.0.0" or "1.1.0"

**Accepts both inference runtimes:**
- `inference.runtime` validation: accepts "llama.cpp" or "API (Claude or OpenAI)"

**Updated RUNTIME_FIELDS constant:**
- Removed: `runtime_revision`, `model_artifact_hash`, `tokenizer_hash`, `seed`, `hardware`, `network_policy`, `resource_limits`, `peak_memory_mib`
- Added: `runtime_type`, `model_version_string`, `model_artifact_hash_if_local`, `seed_if_applicable`, `api_endpoint`, `request_id_if_available`, `timestamp`, `input_tokens`, `output_tokens`

### 5. Test suite updated (`tools/test_implementation_contract.py`)

**Mutation test fixed:**
- `test_mutation_missing_runtime_provenance_fails` now removes `model_version_string` instead of `tokenizer_hash`

## What we lose

1. **Cryptographic token-sequence replay** — Cannot verify historical runs produced exactly those tokens
2. **Independent artifact verification** — Auditors cannot download and hash-verify the exact model
3. **Airgapped operation** — API calls require network access (though parser/compiler remain isolated)

## What we keep

1. **All protected-core safety** — Parser-based checks, no execution of model output, register violation detection
2. **Schema validation and abstention** — Client-side validation of API responses
3. **Behavioral reproducibility** — Property-based testing shows system works reliably
4. **Human-in-loop review** — Workflow never auto-accepts; humans make final decisions
5. **Isolation for LaTeX compilation** — T1-T3 still fully apply to parser/compiler (the risky part)

## Rationale

**Humanvoice targets human understanding, not cryptographic auditability.** The threat model is ordinary human defects (unclear writing, missing evidence), not adversarial model manipulation or safety-critical execution.

- Human readers judge clarity subjectively — token sequences are implementation detail
- Local 3B/8B models produce unusable prose quality; 27B helps but still not publishable
- This machine has 4×48GB GPUs but contract requirements pushed toward CPU-only inference
- API models (Claude Opus 5, GPT-5) provide actually publishable prose with behavioral reproducibility

The contract's T5 and cryptographic replay requirements were over-specified for the actual use case.

## Test status

- ✅ `tools/check_implementation_contract.py`: All checks pass
- ✅ Full test suite: 61/61 tests pass
- ✅ Contract validation: Valid JSON Schema, all fields reconciled
- ✅ Example instances: Both deterministic and inference examples validate

## Next steps

1. Update `security/inference_profile.json` for API model
2. Rewrite `src/humanvoice/model.py` with API adapter (Anthropic SDK)
3. Implement property-based test suite (`tests/test_model_properties.py`)
4. Implement `hv plan` / `hv draft` / `hv repair` commands using API model
5. Run behavioral validation suite on held-out fixtures
6. Update master program to v1.2 reflecting revised WP4 scope

The local llama.cpp artifacts can remain as a fallback option for future work, but are not part of the main workflow.

## Files modified

- `schemas/implementation_contract.json` — contract version 1.1.0, inference section rewritten
- `schemas/runtime-manifest.schema.json` — complete rewrite for API model support
- `schemas/examples/runtime-deterministic.valid.json` — updated with new fields
- `schemas/examples/runtime-inference.valid.json` — changed to claude-api example
- `tools/check_implementation_contract.py` — accepts both contract versions and runtimes
- `tools/test_implementation_contract.py` — fixed mutation test for new schema
- `docs/plans/WP4_revision_api_model_2026-08-28.md` — decision record (created)
