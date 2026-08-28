# WP6 Cost and Burden Analysis

**Date:** 2026-08-28  
**Contract:** HV-IC-2026-08-26 v1.1.0  
**Status:** Preliminary analysis based on contract caps and test suite execution

## 1. Purpose

Document actual resource consumption, operator burden, and cost sensitivity for the humanvoice prototype. Required for G4 handoff decision.

## 2. Contract Operating Envelope (Planning Caps)

From `implementation_contract.json`:

| Parameter | Contract Cap | Measurement Status |
|-----------|--------------|-------------------|
| Max source tree | 250 MiB | Not enforced; ZLB benchmark ~2 MiB |
| Max rendered pages | 300 | Not enforced; ZLB benchmark ~40 pages |
| Max prose words | 120,000 | Not enforced; ZLB benchmark ~15,000 words |
| Max protected objects | 2,000 | Not enforced; ZLB benchmark ~200 objects |
| Deterministic preflight minutes | 30 | Parser + comparison < 5 seconds on fixtures |
| Model-assisted preflight minutes | 90 | Not measured on full documents yet |
| Max repair cycles per unit | 3 | Enforced in code |
| Model input tokens per unit | 12,000 | Not enforced; typical brief ~2,000 tokens |
| Model output tokens per unit | 2,000 | Not enforced; typical plan ~800 tokens |
| Document model input tokens | 250,000 | Not enforced |
| Document model output tokens | 50,000 | Not enforced |
| Inference cost cap | 2 GPU-hours or 10 CPU-hours | Not measured; API model has no local compute |

**Assessment:** Contract explicitly states these are "planning caps for the MVP, to be measured at the week-six checkpoint rather than presented as observed performance." WP6 is the measurement checkpoint.

## 3. Test Suite Performance

### Full test suite execution:
- **Product tests:** 67 tests in `/tests/`
- **Tools tests:** 61 tests in `/tools/`
- **Total:** 128 tests
- **Execution time:** 0.82s for product tests (tools tests not timed this run)
- **Pass rate:** 100%

### Deterministic pipeline performance (no model calls):
Based on test execution patterns:
- `hv init`: < 0.1s (schema validation, directory setup)
- Parser + build: < 1s for synthetic fixtures (1-2 page documents)
- Protected comparison: < 0.1s per object
- `hv preflight` (deterministic only): < 1s for fixture documents
- `hv release` (gate evaluation): < 0.5s

**Deterministic path is well within contract caps.**

## 4. Model-Dependent Cost Estimates

### API Model Assumptions:
- Using Claude or OpenAI API models per contract v1.1
- No local GPU compute; costs are token-based
- Runtime manifests record: model version, input tokens, output tokens, latency

### Typical Token Consumption (Estimated from Schema Sizes):

| Command | Phase | Typical Input Tokens | Typical Output Tokens | Notes |
|---------|-------|---------------------|----------------------|-------|
| `hv plan` | Single invocation | 2,000 - 5,000 | 500 - 1,500 | Brief + evidence → argument blueprint |
| `hv draft` | Per section/unit | 3,000 - 8,000 | 800 - 2,000 | Blueprint + evidence + unit context → prose |
| `hv repair` | Per cycle | 2,000 - 6,000 | 300 - 1,000 | Finding + context → revision pairs |
| `hv preflight` | If model-assisted | 1,000 - 3,000 | 200 - 800 | Quality checks on generated content |

### Document-Level Projection (15,000-word document, ~40 pages):
Assumptions:
- 1 planning invocation
- 10 drafting units (sections/subsections)
- 5 repair cycles (mix of units)
- 2 model-assisted preflight checks

**Estimated total:**
- Input tokens: 2,500 + (10 × 5,000) + (5 × 4,000) + (2 × 2,000) = ~76,500 tokens
- Output tokens: 1,000 + (10 × 1,500) + (5 × 600) + (2 × 500) = ~20,000 tokens
- **Total tokens:** ~96,500 tokens (within contract cap of 300,000 combined)

### Cost Sensitivity (Illustrative, August 2024 pricing):
Using Claude Opus 5 as reference (actual pricing varies):
- Input: ~$15 per million tokens
- Output: ~$75 per million tokens

**Per-document cost estimate:**
- Input: 76,500 × $15 / 1,000,000 = $1.15
- Output: 20,000 × $75 / 1,000,000 = $1.50
- **Total: ~$2.65 per document**

**Sensitivity analysis:**
- 2× token usage (complex document, more repairs): ~$5.30
- 10× token usage (very complex, extensive repairs): ~$26.50
- Contract cap (300k tokens): ~$20 at average input/output mix

**Assessment:** Token costs are modest for typical documents, well-controlled by contract caps and cycle limits.

## 5. Operator Burden Measurement

### Setup and Configuration (One-time per project):
1. Install dependencies: `pip install -e .` (~30 seconds)
2. Set API credentials: environment variable or config file (~2 minutes)
3. Prepare corpus rights manifest: manual review and data entry (~30 minutes per 10 sources)
4. Create authoring brief: structured JSON authoring (~20-45 minutes)

**One-time setup burden: ~1-2 hours**

### Per-Document Authoring Cycle:
Based on contract workflow (init → plan → draft → preflight → repair → release):

| Stage | Operator Activity | Estimated Time | Automation Level |
|-------|-------------------|----------------|------------------|
| `hv init` | Review brief, provide evidence files | 5-15 min | Manual: brief authoring |
| `hv plan` | Review argument blueprint, accept/revise | 5-10 min | Auto: model generates, operator reviews |
| `hv draft` | Review generated sections, accept/request repairs | 10-30 min | Auto: model generates, operator reviews |
| `hv preflight` | Review findings, prioritize repairs | 5-15 min | Auto: gates run, operator triages |
| `hv repair` | Authorize repair cycles, review revisions | 10-30 min | Semi-auto: model proposes, operator authorizes |
| `hv release` | Review gates, authorize exceptions if needed | 5-10 min | Auto: gates run, operator decides |

**Total operator time per document: 40-110 minutes (median ~75 minutes)**

### Breakdown by Skill Level:
- **Writing/domain expertise:** Brief authoring, blueprint review, revision acceptance (~50% of time)
- **Technical expertise:** Gate interpretation, exception authorization, rights review (~30% of time)
- **Clerical:** File preparation, evidence organization (~20% of time)

**Assessment:** Operator burden is acceptable for high-stakes documents (academic papers, regulatory submissions, auditable reports). The brief-authoring overhead is the largest fixed cost.

## 6. Comparison to Manual Baseline

### Traditional academic writing workflow (15,000-word paper):
- Initial draft: 20-40 hours
- Revision cycles: 10-20 hours
- Citation formatting: 2-4 hours
- Figure/table preparation: 4-8 hours
- Fact-checking: 4-8 hours
- **Total: 40-80 hours**

### Humanvoice-assisted workflow:
- Brief + evidence prep: 1-2 hours
- Operator review/authorization: 1-2 hours
- Model compute time: minutes (API latency)
- **Total operator time: 2-4 hours**

**Time savings: ~90-95% of operator time**

**However:** Humanvoice targets a different use case—*reconstruction* or *formally governed authoring* where:
- Every claim must trace to evidence
- Protected vocabulary must survive verbatim
- All decisions must be auditable
- The reader receives an immutable packet

A fair comparison is not "human draft from scratch" but "human draft + auditor review + revision under constraints + packet assembly." That baseline is closer to 60-100 hours for governed writing.

**Adjusted savings: ~95-97% of operator time for governed authoring**

## 7. Bottlenecks and Scaling Limits

### Identified bottlenecks:
1. **Brief authoring:** Manual structured input, ~20-45 minutes per document
2. **Evidence organization:** Operator must prepare and reference files
3. **Model latency:** API calls introduce seconds-to-minutes per invocation
4. **Repair iteration:** Human-in-the-loop for every cycle authorization

### Scaling considerations:
- **Single-document throughput:** Operator can manage 3-5 documents/day with model assistance
- **Parallel documents:** Model API calls can parallelize; operator review is the bottleneck
- **Batch processing:** Not currently supported; each document is independent
- **Corpus reuse:** Evidence and rights manifests can be shared across documents

**Assessment:** Current design optimizes for high-assurance single documents, not high-throughput production.

## 8. Cost Sensitivity to Design Choices

### Token consumption drivers:
1. **Brief length and detail:** More constraints → longer prompts → more input tokens
2. **Evidence volume:** More files → larger context → more input tokens
3. **Repair cycles:** More iterations → multiplicative token cost
4. **Model selection:** Larger models → higher per-token cost

### Sensitivity scenarios:

| Scenario | Token Multiplier | Cost Multiplier | Mitigation |
|----------|-----------------|-----------------|------------|
| Very detailed brief (2× length) | 1.3× | 1.3× | Brief templates, constraint pruning |
| Extensive evidence (3× files) | 1.5× | 1.5× | Evidence summarization, selective inclusion |
| High repair rate (10 cycles) | 2.5× | 2.5× | Better base model, improved prompts, earlier preflight |
| Cheaper model (e.g., Sonnet vs Opus) | 1.0× | 0.2× | Property tests ensure quality threshold |

**Highest leverage:** Reducing repair cycles through better prompts and earlier preflight checks.

## 9. Infrastructure and Dependency Costs

### Development dependencies:
- Python 3.13+
- pdfTeX (included in TeX Live distributions, free)
- API key for Claude or OpenAI (usage-based, documented above)

### Runtime environment:
- 8 CPU cores, 32 GiB RAM (contract reference machine)
- Typical laptop (4 cores, 16 GiB) is sufficient for prototype
- No GPU required (API model)

### Storage:
- Source snapshots: ~2-10 MiB per document
- Run records: ~100-500 KiB per document
- Reader packets: ~2-5 MiB per document (includes PDF, manifests, evidence)

**Infrastructure cost:** Negligible; runs on commodity hardware, storage is minimal.

## 10. Rights and Governance Overhead

### Corpus rights tracking:
From `implementation_contract.json`, every corpus item requires:
- `source_path_or_url`
- `source_hash`
- `owner`
- `license_or_permission`
- `permitted_use`
- `redistribution_status`
- `retention_class`
- `consent_date`

**Burden:** ~5 minutes per source for initial entry, one-time per corpus. Shared across documents that reuse the same corpus.

### Release exception process:
If a gate fails and operator seeks exception:
- Document scope, reason, residual risk
- Obtain domain-reviewer concurrence
- Obtain security/policy-owner concurrence
- Never-except conditions cannot be released

**Burden:** ~15-30 minutes per exception. Should be rare in steady-state (exceptions indicate process gaps).

**Assessment:** Governance overhead is intentional and proportional to assurance level. Not optimizable without reducing auditability.

## 11. Gap Analysis: What Wasn't Measured

### Missing measurements (require live document runs):
1. **Actual model token consumption:** No runtime manifests available from production runs
2. **Full-document latency:** End-to-end time for 15,000-word document
3. **Repair cycle distribution:** How often do units need 0, 1, 2, or 3 cycles?
4. **Model abstention rate:** How often does the model abstain vs. produce output?
5. **Operator decision time:** How long do reviews actually take per stage?
6. **Peak memory usage:** Observed RAM consumption during parser/model runs
7. **Network bandwidth:** API request/response sizes

### Why measurements are missing:
- Test suite uses mocked model responses (no actual API calls)
- Synthetic fixtures are minimal (1-2 pages, not representative documents)
- No live authoring runs captured in runtime manifests yet
- WP5 focused on *feasibility* (can we release a packet?), not *measurement* (what does it cost?)

**Recommendation:** Run instrumented pilot on ZLB benchmark document to capture actual resource consumption.

## 12. Recommendations for Proceed/Revise/Stop Decision

### Proceed if:
- Cost model ($2-5 per document) is acceptable for target use cases
- Operator burden (1-2 hours per document) delivers value vs. manual baseline (40-80 hours)
- Token consumption is within contract caps
- Infrastructure requirements are met (API access, modest compute)

### Revise if:
- Actual measurements on ZLB benchmark exceed projections by >3×
- Operator burden is unacceptable for intended deployment
- Cost sensitivity to repair cycles is too high (need better base prompts)
- Missing measurements (token consumption, latency) are critical for sponsor decision

### Stop if:
- API model costs are prohibitive for target user base
- Operator burden doesn't deliver sufficient value over manual authoring
- Infrastructure requirements (API access, network) are unavailable

## 13. Next Steps

1. ✓ Cost and burden analysis framework (this document)
2. ⬜ **Instrumented pilot run:** Execute full pipeline on ZLB benchmark, capture runtime manifests
3. ⬜ **Token measurement:** Aggregate input/output tokens from runtime manifests
4. ⬜ **Latency measurement:** Wall-clock time for each command on representative document
5. ⬜ **Operator time study:** Timed walkthrough of brief authoring → release with naive operator
6. ⬜ **Cost sensitivity analysis:** Vary brief length, evidence volume, repair cycles; measure impact
7. ⬜ Update this document with actual measurements before G4 handoff

**Estimated completion:** 2026-08-29 (requires one full-document run with instrumentation)
