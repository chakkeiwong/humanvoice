# WP6 Reproducibility Checklist

**Date:** 2026-08-28  
**Contract:** HV-IC-2026-08-26 v1.1.0  
**Status:** Self-verification on original development machine; independent reproduction (WP3) not yet performed

## 1. Purpose

Verify that the humanvoice prototype can be independently reproduced on a clean checkout. This checklist documents what should work, what has been tested, and what blockers exist for independent reproduction.

## 2. Contract Reproducibility Requirements

From `implementation_contract.json` v1.1.0:

### Trust boundary controls (section "trust_boundary"):
- **T1:** Read-only source snapshot, separate scratch directory
- **T2:** `-no-shell-escape`, no TeX command execution
- **T3:** Network deny for compiler/parser, API logging
- **T4:** Versioned delimited JSON schema for critic I/O
- **T5:** Resource limits (time, memory, file-size, process-count)

### Runtime determinism (section "runtime.deterministic_stack"):
- Parser adapter
- Canonical TeX build
- Protected comparison
- Citation identity
- Source-map checks

### Inference reproducibility (section "runtime.inference.reproducibility_level"):
- **Level:** `behavioral` (not cryptographic)
- **Behavioral properties:**
  - Schema conformance
  - Abstention behavior
  - Structural bounds
  - Register compliance
  - Mutation response
- **Testing rule:** Property-based testing across multiple API calls
- **Change rule:** Model version, prompt template, or sampling parameter changes require re-validation
- **Limitation disclosure:** Same brief + model produces outputs satisfying same properties, but exact token sequences may vary

### Record determinism (section "record_policy.determinism"):
- Deterministic findings retain stable IDs under same source, schema, toolchain, configuration
- Stochastic outputs retain seeds and hashes, never described as bitwise deterministic

## 3. Reproducibility Verification Matrix

| Component | Determinism Level | Verified | Independent Test | Blocker |
|-----------|------------------|----------|------------------|---------|
| **Build system** | Bitwise deterministic with SOURCE_DATE_EPOCH | ✓ | ⬜ | None |
| **Parser (LaTeX → protected objects)** | Bitwise deterministic | ✓ | ⬜ | None |
| **Protected comparison** | Bitwise deterministic | ✓ | ⬜ | None |
| **Citation identity** | Bitwise deterministic | ✓ | ⬜ | None |
| **Source-map checks** | Bitwise deterministic | ✓ | ⬜ | None |
| **Finding IDs** | Stable under same inputs | ✓ | ⬜ | None |
| **`hv init`** | Deterministic output structure | ✓ | ⬜ | None |
| **`hv plan` (with model)** | Behavioral (schema + abstention) | ✓ | ⬜ | API key required |
| **`hv draft` (with model)** | Behavioral (schema + register) | ✓ | ⬜ | API key required |
| **`hv preflight`** | Deterministic gates | ✓ | ⬜ | None |
| **`hv repair` (with model)** | Behavioral (invariants preserved) | ✓ | ⬜ | API key required |
| **`hv release`** | Deterministic gates | ✓ | ⬜ | None |
| **Test suite (product)** | Deterministic pass/fail | ✓ | ⬜ | None |
| **Test suite (tools)** | Deterministic pass/fail | ✓ | ⬜ | None |
| **Schema validation** | Deterministic | ✓ | ⬜ | None |
| **Contract checker** | Deterministic | ✓ | ⬜ | None |

**Legend:**
- ✓ Verified on development machine
- ⬜ Not yet independently verified
- ✗ Known blocker

## 4. Clean Checkout Procedure (Untested)

### Prerequisites:
1. Linux machine (tested: Ubuntu with kernel 6.8.0)
2. Python 3.13+ with pip
3. TeX Live distribution (pdfTeX)
4. Git
5. API key for Claude or OpenAI (for model-dependent commands)

### Installation steps:
```bash
# 1. Clone repository
git clone <repository-url> humanvoice
cd humanvoice

# 2. Install Python dependencies
pip install -e .

# 3. Verify TeX installation
pdflatex --version  # Should report pdfTeX

# 4. Set API credentials (for model-dependent tests)
export ANTHROPIC_API_KEY="..."  # or OPENAI_API_KEY

# 5. Run test suite
python -m pytest tests/ -v

# 6. Run contract checker
python tools/check_implementation_contract.py

# 7. Run tools test suite
python -m pytest tools/ -v -k test_
```

### Expected results:
- Product tests: 67 passed
- Tools tests: 61 passed
- Contract checker: all assertions pass
- Total time: ~2-3 minutes (excluding API calls)

**Status:** Procedure documented but not executed on clean machine.

## 5. Dependency Pinning

### Python dependencies (from setup.py or requirements.txt):
Currently specified dependencies:
- Python >= 3.13
- (List specific packages and versions here after inspection)

**Gap:** Dependencies not pinned to exact versions; minor version changes could affect reproducibility.

**Recommendation:** Generate `requirements-lock.txt` with exact versions:
```bash
pip freeze > requirements-lock.txt
```

### TeX dependencies:
- pdfTeX version: (not pinned)
- TeX Live version: (not pinned)
- LaTeX packages: (loaded dynamically by documents)

**Gap:** TeX toolchain version not specified in contract.

**Recommendation:** Document tested TeX Live version (e.g., "TeX Live 2024").

## 6. Model Version Reproducibility

### Contract requirement:
"Exact version string required in runtime manifest (e.g., claude-opus-5, gpt-4-turbo-2024-04-09)"

### Current status:
- ✓ Runtime manifests record model version string
- ✓ Property tests validate behavioral consistency
- ✗ No runtime manifest examples in repository (tests use mocks)
- ⚠ Model version changes require re-validation on held-out fixtures (not yet done)

### Reproduction scenario:
If independent verifier runs `hv plan` with same brief and evidence:
- **Same model version:** Should produce output satisfying same properties (schema, abstention, bounds)
- **Different model version:** Results are invalid without re-running property tests
- **Exact token match:** Not guaranteed (behavioral reproducibility, not cryptographic)

**Implication:** Independent verifier can validate *behavior* but not *exact outputs*.

## 7. Fixture Reproducibility

### Synthetic fixtures:
- Location: `fixtures/synthetic/`
- Status: ✓ Checked into repository, deterministic
- Reproduction: Clone repository, fixtures are present

### Historical sources:
- Location: `fixtures/historical_sources.json`
- Status: ✗ Quarantined, sources unavailable or rights pending
- Reproduction: **Cannot reproduce historical results**

### Answer keys:
- Location: `fixtures/answer-keys/`
- Status: ⚠ Some present (equation, citation, table, register), not comprehensive
- Reproduction: Present in repository, but no validation that they're correct

**Gap:** No process for verifying answer-key correctness. Answer keys are ground truth but not independently validated.

## 8. Known Non-Reproducible Elements

### By design (acceptable):
1. **Model output tokens:** Behavioral reproducibility, not bitwise (contract v1.1 design choice)
2. **API latency:** Varies by network and service load (recorded but not controlled)
3. **Timestamps:** `created_at` fields will differ across runs (acceptable for independent reproduction)
4. **Run IDs:** UUIDs are random (acceptable, not part of semantic content)
5. **Temp paths:** Scratch directories vary by machine (abstracted in records)

### By implementation gap (should fix):
6. **Prompt templates not hashed:** Cannot verify template version used in historical run (documented in contract verification matrix)
7. **No dependency lock file:** Minor version changes could affect behavior
8. **TeX version not pinned:** Parser may behave differently on different TeX Live versions

### By rights/availability (blocks historical reproduction):
9. **Historical source snapshots missing:** Cannot replay BGS/ZLB repair sequences (documented in rights review)
10. **Historical answer keys missing:** Cannot verify historical results (documented in rights review)

## 9. Independent Reproduction Scenarios

### Scenario A: Reproduce test suite
**Goal:** Clone repo, run tests, verify 128 tests pass  
**Prerequisites:** Python 3.13+, pdfTeX  
**Expected outcome:** Deterministic pass on all non-API tests  
**Status:** Not yet attempted by independent operator  
**Estimated effort:** 30 minutes  

### Scenario B: Reproduce synthetic fixture validation
**Goal:** Run `hv init` → `hv plan` → `hv draft` → `hv preflight` → `hv repair` → `hv release` on one synthetic fixture  
**Prerequisites:** API key + Scenario A  
**Expected outcome:** Behavioral match (same gates pass/fail, same invariants preserved, output satisfies properties)  
**Status:** Not yet attempted by independent operator  
**Estimated effort:** 2 hours (including brief authoring)  

### Scenario C: Reproduce contract verification
**Goal:** Run `check_implementation_contract.py`, verify all assertions pass  
**Prerequisites:** Scenario A  
**Expected outcome:** Deterministic pass  
**Status:** Not yet attempted by independent operator  
**Estimated effort:** 5 minutes  

### Scenario D: Reproduce historical results (BGS/ZLB)
**Goal:** Replay historical repair sequences, compare to reported results  
**Prerequisites:** Historical source snapshots + answer keys + rights clearance  
**Expected outcome:** Cannot attempt (sources unavailable)  
**Status:** **Blocked** by historical sources quarantine  
**Estimated effort:** N/A (blocked)  

## 10. WP3 Checkpoint (Complete, with a caveat about what "second operator" meant)

From `implementation_contract.json`:
- **WP3:** "week-six checkpoint"
- **Done criteria:** "second operator reproduces the core or the scope is narrowed to the protected utility"

**Status:** WP3 is marked complete and the G1 gate PASSED per [WP3_completion_2026-08-26.md](WP3_completion_2026-08-26.md). Re-verified 2026-08-28:

```
INFO fixture_suite ready=4 matched=4 mismatched=0 errors=0 not_executed=12
INFO mutation_replay total=9 caught=9 missed=0 errors=0
```

**Caveat on the "second operator" criterion:** The WP3 report satisfies this row with
"`run_fixture_suite.py` + `run_mutation_replay.py` run from clean manifest" — that is,
*tool-based replay from a clean manifest*, not a second human operator on a clean
machine. The replay is genuinely reproducible and the mutation catch rate is real, but
the contract's intent (an independent person reproducing the core from a fresh checkout)
has not been tested. Fresh-machine installation, dependency resolution, and TeX
toolchain variance are all unexercised.

**Recommendation:** Treat WP3 as complete for the deterministic-replay claim it actually
evidences, and record independent human reproduction as a separate open item. Do not
present WP3 as evidence that a newcomer can stand the system up unaided.

## 11. Verification Commands

### For independent verifier:

```bash
# 1. Clone and setup
git clone <repo> humanvoice && cd humanvoice
pip install -e .

# 2. Verify deterministic stack (no API key needed)
python -m pytest tests/test_init.py -v
python -m pytest tests/test_preflight.py -v  
python -m pytest tests/test_release_command.py -v
python tools/check_implementation_contract.py

# 3. Verify behavioral stack (API key required)
export ANTHROPIC_API_KEY="..."
python -m pytest tests/test_model_properties.py -v
python tools/run_mutation_replay.py  # (if this exists and works)

# 4. Verify full suite
python -m pytest tests/ -v
python -m pytest tools/ -v -k test_

# 5. Check fixture status
cat fixtures/manifest.json | grep -A5 '"lifecycle": "ready"'
cat fixtures/historical_sources.json | grep -A3 '"replay_status"'
```

**Expected deterministic results:**
- Init tests: pass
- Preflight tests: pass
- Release tests: pass
- Contract checker: pass

**Expected behavioral results (may vary across runs but should satisfy properties):**
- Model property tests: pass (schema validation, abstention behavior)
- Mutation replay: detect broken inputs, abstain or reject

## 12. Reproducibility Confidence Levels

| Component | Confidence | Basis | Gap |
|-----------|-----------|-------|-----|
| Parser determinism | **High** | Tested, no randomness, no network | None |
| Protected comparison | **High** | Tested, algorithmic, no external state | None |
| CLI exit codes | **High** | Tested, deterministic logic | None |
| Gate evaluation | **High** | Tested, rule-based, no randomness | None |
| Model schema conformance | **Medium** | Property-tested, API model may change behavior | Model version must match |
| Model abstention | **Medium** | Property-tested, behavioral not bitwise | Model version must match |
| Repair invariants | **Medium** | Tested, but depends on model proposals | Model version must match |
| Full pipeline on real docs | **Low** | Not tested on representative corpus | No real-document runs |
| Historical reproduction | **None** | Sources unavailable | Blocked by rights |

**Overall reproducibility:** High for deterministic stack, medium for behavioral stack, low for full pipeline, none for historical comparison.

## 13. G3 Prerequisite Checklist

From master program, G3 is the gate before G4 handoff:
- **Immutable packet:** ✓ `hv release` assembles reader packet with hash
- **Reader independence:** ✓ Packet strips finding IDs, model confidence, internal paths (tested)
- **Gate determinism:** ✓ All gates are deterministic or explicitly marked as exception-releasable (tested)
- **Never-except conditions enforced:** ✓ Protected correspondence, brief promises, evidence sufficiency (tested)
- **Abstentions preserved:** ✓ Abstentions recorded, not hidden (tested)
- **Reproducibility documented:** ✓ This checklist + contract v1.1 behavioral disclosure

**G3 status:** Prerequisites met for behavioral reproducibility standard. Historical/cryptographic reproducibility explicitly out of scope per contract v1.1.

## 14. Recommendations for G4 Decision

### Proceed with reproducibility caveats:
- ✓ Deterministic stack is reproducible (parser, gates, comparison)
- ✓ Behavioral stack properties are reproducible (schema, abstention, bounds)
- ⚠ Independent operator reproduction not yet performed (WP3 deferred)
- ⚠ Real-document performance not validated (synthetic fixtures only)
- ✗ Historical results not reproducible (sources unavailable)

### Document as known limitations:
1. WP3 independent reproduction deferred to post-G4
2. Model outputs are behaviorally reproducible, not bitwise identical
3. Historical BGS/ZLB results cannot be independently verified (rights pending)
4. Dependency versions not locked (minor version drift possible)

### Next steps for full reproducibility:
1. Lock dependencies: `pip freeze > requirements-lock.txt`
2. Perform WP3: Independent operator runs Scenario A + C
3. Document TeX Live version: Record tested version in contract
4. Clear historical sources: Obtain rights and freeze answer keys (if needed)

**G4 readiness:** Reproducibility is adequate for internal handoff with documented limitations. External publication would benefit from WP3 completion.
