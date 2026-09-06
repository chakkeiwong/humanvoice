# Humanvoice Release Pipeline — Reproduction Guide

**Goal:** Reproduce a release decision from source fixture to release gate evaluation.

This guide walks through the complete authoring pipeline: initializing a snapshot, planning sections, drafting prose, running preflight checks, repairing violations, and evaluating release gates. It uses a synthetic fixture with known violations to demonstrate gate behavior.

---

## Prerequisites

1. **Python 3.11+** with pip
2. **Anthropic API key** (for model invocation)
3. **Git** (for repository clone)

---

## Setup

### 1. Clone the repository

```bash
git clone <repository-url> humanvoice
cd humanvoice
```

### 2. Install dependencies

```bash
pip install -r requirements-dev.txt
```

This installs:
- `anthropic` (model API client)
- `pylatexenc` (LaTeX parser for protected-object extraction)
- `jsonschema` (schema validation)
- `pytest` (test runner)

The inspection commands below pipe JSON through `python -m json.tool` so no extra
tooling is required. `jq` is nicer for ad-hoc filtering if you have it, but it is
not a dependency of this guide.

### 3. Configure API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Without this key, model invocation will fail. Mock mode (`--mock`) can be used for testing without API calls.

### 4. Verify installation

```bash
python -m pytest tests/ -q
```

Expected: 76 passed, 2 skipped (as of 2026-08-29)

---

## Pipeline Commands

Humanvoice implements a staged pipeline:

```
hv init       → Initialize snapshot from LaTeX source
hv plan       → Generate argument blueprint from brief
hv draft      → Write prose for each planned section
hv preflight  → Run deterministic checks (register, protected objects)
hv repair     → Propose revisions to clear preflight findings
hv release    → Evaluate gates and emit reader packet
```

Each command writes structured JSON records under `<snapshot>/.humanvoice/runs/<run-id>/`.

---

## Reproduction Steps

### Step 1: Initialize a snapshot

Create a snapshot from a source fixture and authoring brief.

```bash
python -m humanvoice.cli init \
  fixtures/synthetic/register/001.tex \
  --brief fixtures/briefs/technical_memo.json \
  --output workdir/snapshot
```

**Expected output:**
```json
{
  "status": "initialized",
  "snapshot_id": "snapshot-YYYYMMDD-HHMMSS",
  "source_hash": "sha256:...",
  "brief_valid": true,
  "output_path": "workdir/snapshot"
}
```

**What happened:**
- Source copied to `workdir/snapshot/source/001.tex`
- Manifest written to `workdir/snapshot/manifest.json`
- Brief validated against schema

---

### Step 2: Generate a blueprint

Plan the document structure based on the brief and source.

```bash
python -m humanvoice.cli plan workdir/snapshot \
  --brief fixtures/briefs/technical_memo.json
```

**Expected output:**
```
Generating blueprint with claude-opus-5...
Blueprint written to: workdir/snapshot/.humanvoice/runs/run-YYYYMMDD-HHMMSS/blueprint.json
```

**What happened:**
- Model invoked with source + brief → argument blueprint
- Blueprint contains sections with titles, purposes, word budgets
- Transmission logged to `manifest.json`

**Inspect the blueprint:**
```bash
python - <<'PY'
import glob, json
path = glob.glob('workdir/snapshot/.humanvoice/runs/run-*/blueprint.json')[0]
for s in json.load(open(path))['blueprint']['sections']:
    print(f"{s['title']}: {s.get('word_budget')} words")
PY
```

---

### Step 3: Draft each section

For each section in the blueprint, invoke the model to write prose.

```bash
# Draft section 0
python -m humanvoice.cli draft workdir/snapshot \
  --brief fixtures/briefs/technical_memo.json \
  --blueprint workdir/snapshot/.humanvoice/runs/run-*/blueprint.json \
  --section 0

# Draft section 1
python -m humanvoice.cli draft workdir/snapshot \
  --brief fixtures/briefs/technical_memo.json \
  --blueprint workdir/snapshot/.humanvoice/runs/run-*/blueprint.json \
  --section 1

# Repeat for remaining sections...
```

**Expected output (per section):**
```
Generating draft for 'Introduction' with claude-opus-5...
Draft written to: workdir/snapshot/.humanvoice/runs/run-YYYYMMDD-HHMMSS/draft_introduction.tex
Word count: 487 (target: 500 ±20%)
```

**What happened:**
- Model invoked with section purpose + brief + source context
- Prose written as standalone `.tex` file
- Word budget checked (±20% tolerance)
- Transmission logged

**Note:** If a draft has `word_count: 0`, it exits 1 (as of Fix 4). The fixture `001.tex` may trigger this on certain sections.

---

### Step 4: Run preflight checks

Deterministic checks run without model invocation.

```bash
python -m humanvoice.cli preflight workdir/snapshot \
  --brief fixtures/briefs/technical_memo.json \
  --deterministic
```

**Expected output (for fixture with violations):**
```
Found 2 register violations
```

**Exit codes:**
- `0` = pass (no deterministic failures)
- `1` = violations found

**Inspect findings:**
```bash
python - <<'PY'
import glob, json
path = glob.glob('workdir/snapshot/.humanvoice/runs/run-*/preflight-*.json')[0]
findings = json.load(open(path))['findings']
print(f"Found {len(findings)} finding(s):")
for f in findings:
    print(f"  - {f['category']}: {f['message']}")
PY
```

**What happened:**
- Source parsed for protected objects
- Register checks detected internal labels (`WP3`) or private paths (`/srv/humanvoice/private`)
- Findings written with locations, matched text, consequences

---

### Step 5: Repair violations (optional)

Propose edits to clear preflight findings. This step is optional — you can proceed directly to release to see gates block.

```bash
python -m humanvoice.cli repair \
  workdir/snapshot/.humanvoice/runs/run-*/draft_*.tex \
  --findings workdir/snapshot/.humanvoice/runs/run-*/preflight-*.json \
  --brief fixtures/briefs/technical_memo.json
```

**Possible outcomes:**
- **Exit 0:** Repair succeeded, revision published
- **Exit 1:** Blocked (cycle limit, oscillation, or verbatim mismatch)
- **Exit 2:** Abstention (model declined; insufficient basis)

**What happened:**
- Model invoked with draft + findings → proposed string replacements
- Each change validated verbatim (no fuzzy matching)
- Protected-object correspondence checked
- Evidence-item record emitted (if successful)

**Inspect revision:**
```bash
ls workdir/snapshot/.humanvoice/runs/run-*/revisions/
```

---

### Step 6: Evaluate release gates

Check whether the snapshot passes all release conditions.

```bash
python -m humanvoice.cli release workdir/snapshot \
  --brief fixtures/briefs/technical_memo.json
```

**Expected output (for fixture with unresolved violations):**
```
Release blocked by 1 never-except condition(s):
  - deterministic_preflight: 2 deterministic finding(s) stand unresolved
```

**Exit codes:**
- `0` = released (all gates pass, reader packet emitted)
- `1` = blocked (one or more gates failed)
- `2` = abstention (missing configuration)

**Inspect decision:**
```bash
python - <<'PY'
import json
d = json.load(open('workdir/snapshot/release/release_decision.json'))
print(f"status: {d['status']}")
print(f"packet_hash: {d['packet_hash']}")
print("gate_results:")
for k, v in d['gate_results'].items():
    print(f"  {k}: {v}")
if d.get('unresolved_risks'):
    print(f"unresolved_risks: {d['unresolved_risks']}")
PY
```

**What happened:**
- Seven gates evaluated:
  1. `protected_correspondence` (never-except)
  2. `brief_parsing_promises` (never-except)
  3. `evidence_sufficiency` (never-except)
  4. `unauthorized_transmission` (never-except)
  5. `deterministic_preflight` (never-except)
  6. `source_build` (never-except)
  7. `author_convergence` (ordinary)
- Decision record written to `workdir/snapshot/release/release_decision.json`
- If all gates pass: reader packet emitted to `workdir/snapshot/release/packet/`

---

## Expected Results

### With fixture `001.tex` (planted violations)

Verified end-to-end on 2026-08-29 from a clean directory:

| Step | Exit | Result |
|---|---|---|
| init | 0 | `snapshot_id` minted, `brief_valid: true` |
| plan | 0 | 4 sections, 300 words, 422 in / 272 out tokens |
| draft (section 0) | 0 | 78 words, 1 citation, 457 in / 149 out tokens |
| preflight | 1 | 2 register findings (`WP3` @66, `/srv/humanvoice/private` @83) |
| release | 1 | **blocked** on `deterministic_preflight` |

Release decision:

```
status: blocked
packet_hash: ''
gate_results:
  protected_correspondence: pass
  brief_parsing_promises: pass
  evidence_sufficiency: pass
  unauthorized_transmission: pass
  deterministic_preflight: blocked
  source_build: pass
  author_convergence: pass
unresolved_risks: ['deterministic_preflight']
```

The release directory contains only `release_decision.json` — no reader packet is
emitted while a never-except gate is blocked. That is the point of the fixture:
it plants two disclosure violations and the pipeline must refuse to ship them.

Section titles and token counts vary between runs because the model samples
fresh each time. Exit codes and the blocked gate should not vary.

### With a clean fixture (no violations)

**Preflight:** Exit 0, no findings  
**Release:** Exit 0, reader packet emitted to `<snapshot>/release/packet/`

---

## Release Gates Reference

| Gate | Type | Blocks when |
|---|---|---|
| `protected_correspondence` | never-except | Protected objects in source not reflected in draft |
| `brief_parsing_promises` | never-except | Brief promises objects (e.g., equations) but parser found none |
| `evidence_sufficiency` | never-except | Load-bearing claim with insufficient/unappraised evidence |
| `unauthorized_transmission` | never-except | Transmission log contains unauthorized entries |
| `deterministic_preflight` | never-except | Preflight findings stand unresolved |
| `source_build` | never-except | LaTeX compilation fails or produces warnings |
| `author_convergence` | ordinary | Repair hit cycle limit, oscillation, or abstention |

**Never-except** conditions block release unconditionally — no human override.  
**Ordinary** conditions can be excepted by the operator (not implemented in v1.2).

---

## Instrumented End-to-End Test

A full pipeline test with token tracking:

```bash
python tools/instrumented_pilot.py \
  fixtures/synthetic/register/001.tex \
  validation_results/reproduction_$(date +%Y%m%d).json
```

**What it does:**
- Runs init → plan → draft (all sections) → preflight → repair → release
- Records exit codes, token counts, run directories
- Writes structured JSON log

**Expected:**
- Plan: exit 0
- Draft: some sections exit 1 (zero words), some exit 0
- Preflight: exit 1 (2 violations)
- Repair: exit 0 or 2
- Release: exit 1 (blocked)

**Inspect:**
```bash
python - <<'PY'
import glob, json
path = sorted(glob.glob('validation_results/reproduction_*.json'))[-1]
d = json.load(open(path))
for s in d['steps']:
    if s.get('skipped'):
        continue
    print(f"{s['step']:28} exit={s['exit_code']}  {s['wall_clock_ms']}ms")
print(f"\ntotals: {d['totals']['input_tokens']} in / {d['totals']['output_tokens']} out")
PY
```

---

## Troubleshooting

### API key not set
```
ValueError: ANTHROPIC_API_KEY environment variable required
```
→ Run `export ANTHROPIC_API_KEY="sk-ant-..."`

### Schema validation failed
```
Model abstained: Output failed schema validation
```
→ Retry the command (intermittent model output format issue)

### Zero-word draft
```
Error: Draft contains no prose (word_count=0); nothing written
```
→ Expected behavior (Fix 4). The model abstained or produced no extractable text.

### Repair refuses changes
```
Error: no proposed change matched the draft verbatim
```
→ Model proposed edits to text not in the draft. Repair uses exact string matching (no fuzzy repair).

### Tests fail
```
FAILED tests/...
```
→ Run `python -m pytest tests/ -xvs` to see detailed failure. Known issues in `docs/plans/phase2_progress_2026-08-29.md`.

---

## Next Steps

After reproducing the pipeline:

1. **Inspect run records:** All outputs under `<snapshot>/.humanvoice/runs/<run-id>/`
2. **Review gate logic:** `src/humanvoice/commands/release_command.py`
3. **Read the proposal:** `docs/survey/humanvoice_survey.pdf`
4. **Check evidence status:** `docs/survey/humanvoice_evidence_status.json`

---

## Contact

For questions about reproduction, see `docs/plans/` for implementation notes and known limitations.
