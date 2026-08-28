# WP4 Completion — Inference integration

**Date:** 2026-08-27  
**Work package:** WP4 (authoring extension)  
**Status:** Environment ready; commands unimplemented  

## What was delivered

### 1. Runtime environment

llama.cpp built from pinned commit `539f24529bdf99e0baefd54fefff1660034bfe7b`:
- Executable: `/tmp/llama.cpp/build/bin/llama-cli`
- Version: `0.3.0-dev (build 1, commit 539f245)`
- Compiler: GNU 11.4.0 for Linux x86_64
- Acceleration: CPU-only (CUDA disabled per contract)
- Build system: CMake (Makefile path deprecated upstream)

### 2. Model artifact

Qwen2.5-3B-Instruct quantized Q4_K_M GGUF downloaded from `bartowski/Qwen2.5-3B-Instruct-GGUF`:
- Path: `/tmp/models/Qwen2.5-3B-Instruct-Q4_K_M.gguf`
- Size: 1.96 GB
- SHA-256: `9c9f56a391a3abbd5b89d0245bf6106081bcc3173119d4229235dd9d23253f94`
- Context length: 32,768 tokens

**Deviation from contract:** The contract names Qwen3-8B-Instruct and Llama-3.1-8B-Instruct as reference candidates. Qwen**2.5**-**3B**-Instruct was used for environment plumbing only. Any calibration, held-out, or release claim requires replay on a contract-named candidate.

### 3. Inference profile

`security/inference_profile.json` records:
- `artifact_sha256` and `prompt_template_hash` (required by contract before invocation)
- Sampling: temperature=0.0, top_k=1, seed=1 (greedy decoding for reproducibility)
- Isolation: bubblewrap, network unshared, model read-only, no tool authority
- Profile status: `ready`
- G2 readiness: `ready`

### 4. Prompt template

`security/prompt_template_critic.txt` defined and hashed:
- Template ID: `HV-CRITIC-V1`
- SHA-256: `9203411fa7aff6ff124cf6da2711ea561db874ee9c54134733d4c47785a79d74`
- Purpose: critic/repair cycle structured output

The template is generic placeholder text. Production use requires domain-tuned system prompts.

### 5. Model adapter

`src/humanvoice/model.py` extended:
- `ModelConfig.from_profile()` — loads config from the recorded inference profile; throws if `artifact_sha256` or `prompt_template_hash` is pending (contract enforcement)
- Hash verification on first invocation (cached per adapter instance to avoid re-reading 2GB)
- llama.cpp invocation with `--single-turn`, `--grammar-file`, timeout, stderr capture
- JSON extraction by brace-matching (llama-cli interleaves banner/footer with generated text)
- Schema validation with abstention on mismatch (T4: model output is data, not instructions)

### 6. Schema-derived grammars

Generated via llama.cpp's `json_schema_to_grammar.py`:
- `schemas/plan.gbnf` — constrains generation to `PLAN_SCHEMA`
- `schemas/draft.gbnf` — constrains generation to `DRAFT_SCHEMA`
- `schemas/repair.gbnf` — constrains generation to `REPAIR_SCHEMA`

Grammars enforce shape at the sampler, so off-schema outputs are prevented rather than caught after the fact. The generic `json.gbnf` only guarantees well-formed JSON, which led to abstentions on structurally valid but wrong-shaped responses.

### 7. Live verification

```bash
$ python src/humanvoice/model.py --real
Verifying model artifact hash... OK
Response (101 tokens):
{ "blueprint": {
    "sections": [
        {
            "title": "Introduction",
            "purpose": "To provide an overview...",
            "word_budget": 100
        },
        ...
    ],
    "total_words": 500
} }

Prompt hash: b95030ca71f9a2d7...
Abstention: none
```

Real inference end-to-end: hash verified, schema-constrained generation, valid output, no abstention.

## What was not delivered

The three authoring commands remain unimplemented:
- `hv plan` — generate narrative blueprint from brief + evidence
- `hv draft` — unit-level draft within blueprint boundary  
- `hv repair` — bounded edits (max 3 cycles, oscillation detection)

Per the contract's `fallback_rule`: "The deterministic protected-core path may continue when inference is unavailable, but it cannot claim a full writing/reconstruction release."

The protected core (`hv init`, `hv preflight`, `hv compare`, `hv findings`) is complete and tested. The authoring extension is environment-ready but command-incomplete.

## Decisions made

### Worktree isolation abandoned

Created `.claude/worktrees/wp4-inference` initially for llama.cpp build + model download isolation. Both artifacts went to `/tmp` (shared), not the worktree, so isolation bought nothing. The inference profile and prompt template were staged to `/tmp/hv-wp4-staging/`, the worktree was removed, and work consolidated in the main checkout where WP1–WP3 code lives.

### Schema-derived grammars over generic JSON

The generic `/tmp/llama.cpp/grammars/json.gbnf` only enforces "valid JSON." Without schema-specific constraints, the model generated structurally valid JSON in a different shape, triggering abstention. llama.cpp ships `json_schema_to_grammar.py` for this; using it eliminated spurious abstentions.

### Hash verification cached per adapter instance

The 2GB model artifact is hashed on first invocation and the result cached. Re-reading on every invoke() call would dominate runtime. The contract requires verification *before* invocation; it does not require verification *per* invocation.

### 3B model for plumbing only

Qwen2.5-3B-Instruct (3B parameters, not the contract's 8B candidates) was used to verify the inference pipeline works end-to-end. The contract explicitly allows smaller models for "prototype plumbing verification" but requires replay on Qwen3-8B-Instruct or Llama-3.1-8B-Instruct before any calibration, held-out, or release claim.

## Next action

Implement `hv plan` / `hv draft` / `hv repair` commands:
- Prompt engineering against the real 3B model or upgrade to a contract-named 8B candidate
- 3-cycle repair cap and oscillation detection
- Schema-validated I/O for all three
- Functional tests against live inference (not mocks)

Alternatively, proceed with the deterministic protected-core path only (no authoring commands) and defer WP4 to a funded phase. The contract permits this.

## Test impact

- 71/71 humanvoice tests pass
- `tools/check_program_consistency.py` updated: runner status check now looks for "planned" within 200 chars of the backticked runner name, not anywhere in the section (avoids false positives from lifecycle vocabulary definitions)
- `docs/plans/humanvoice_master_program_v1.1_2026-08-26.md` updated to reflect `run_fixture_suite.py` exists and has run

## Files modified

- `src/humanvoice/model.py` — extended with real llama.cpp invocation, hash verification, JSON extraction, schema-constrained generation
- `security/inference_profile.json` — created; records artifact hash, prompt template hash, profile status `ready`
- `security/prompt_template_critic.txt` — created; critic template with SHA-256
- `schemas/plan.gbnf`, `schemas/draft.gbnf`, `schemas/repair.gbnf` — generated from JSON schemas
- `tools/check_program_consistency.py` — tightened runner status heuristic
- `docs/plans/humanvoice_master_program_v1.1_2026-08-26.md` — updated runner status prose

## Artifacts at rest

- `/tmp/llama.cpp/` — 119 binaries, build artifacts, grammars, examples
- `/tmp/models/Qwen2.5-3B-Instruct-Q4_K_M.gguf` — 1.96 GB
- `/tmp/models/Qwen2.5-3B-Instruct-Q4_K_M.gguf.sha256` — hash record
- `/tmp/hv-wp4-staging/` — empty staging directory (files moved to `security/`)
