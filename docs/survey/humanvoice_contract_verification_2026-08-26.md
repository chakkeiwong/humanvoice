# Verification: is the governing document implementable now?

Verified 2026-08-26 against `docs/survey/humanvoice_survey.tex` (265 pp) and the
new contract artifacts. Method: read the annex, machine-validated every schema,
mutation-tested the contract checker, ran the test suite, and re-grepped all
earlier absence claims across the concatenated 31 `.tex` route files.

**Verdict: yes — contract-ready.** All nine gaps from the 2026-08-26 gap review
are closed with enforceable artifacts, not prose promises. Two of my three
"stops a team in week one" blockers are fully resolved; the third (model
selection) is resolved as far as it can be before hardware is in hand. What
remains is not specification work.

---

## 1. Claims audit

Every claim in the Codex message was checked. All are accurate.

| Claim | Status | Evidence |
|---|---|---|
| Annex at `21_implementation_contract.tex` | **True** | 311 lines, `\input` at `humanvoice_survey.tex:222` |
| Machine-readable contract | **True** | `schemas/implementation_contract.json`, `HV-IC-2026-08-26` v1.0.0, 12 top-level sections |
| JSON Schemas for 9 record types | **True** | all draft 2020-12, all with `required` |
| Threat controls T1–T5 | **True** | annex §A.2 + contract `trust_boundary.controls` |
| Named model candidates + hashes | **True** | Qwen3-8B-Instruct GGUF Q4_K_M ref, Llama-3.1-8B fallback |
| Stable CLI streams + exit codes | **True** | exit 0–5, 9 stable stdout fields, 4 advisory |
| Child-revision repair semantics | **True** | annex §A.7, never in-place |
| Security veto + never-except | **True** | 5 never-except conditions |
| Staffed roles + WP definitions of done | **True** | 8 roles, 6 WPs with exits |
| Corpus rights manifest | **True** | 5 items, all `pending-clearance` — honestly marked |
| Week-six protected-core gate | **True** | `tab:contract-scope`, extension conditional |
| Contract validation in build | **True** | `build_humanvoice.sh` calls the checker before `pdflatex` |
| Fragments archived not deleted | **True** | `archive/superseded-2026-08-26/` + README |
| 265 pages, 38 figures, 72 tables, 110 visuals | **True** | `pdfinfo` + `.aux` count + `check_visual_density.py` |
| 47 unit tests pass | **True** | `unittest discover`: `Ran 47 tests … OK` |
| No unresolved citations/refs/overfull | **True** | 0 / 0 / 0 in `.log` |
| Evidence still 9/15 | **True** | `humanvoice_evidence_status.json`, `release-blocked` |

### The checker has real teeth

The important question is whether `check_implementation_contract.py` enforces
the contract or merely confirms files exist. I mutation-tested it:

| Mutation | Result |
|---|---|
| Remove `-no-shell-escape` from required flags | **FAIL** `build contract omits -no-shell-escape`, exit 1 |
| Set `remote_default: allow` | **FAIL** `remote default is not deny` |
| Delete control T4 (injection boundary) | **FAIL** `trust-boundary controls T1-T5 are not complete` |
| Delete exit code 5 (security violation) | **FAIL** `CLI exit codes 0-5 are not complete` |

All four caught; contract restored byte-identically afterward. The checker also
cross-validates that `humanvoice_product_requirements.json` is exactly
`R1`…`R24`, that every rights item carries seven required fields, that the
manuscript `\input`s the annex, and — notably — that the annex contains **no
surviving `AC1`–`AC18` identifiers**. That last assertion is what makes the
"single canonical register" claim self-enforcing rather than aspirational.

---

## 2. The nine gaps, closed

| # | Gap (2026-08-26) | Now | Where |
|---|---|---|---|
| 1 | No threat model; untrusted input executed | **Closed** | T1–T5; `-no-shell-escape`, `-halt-on-error`, `-file-line-error`; read-only snapshot → allow-listed scratch; network deny; schema-validated critic I/O; injection fixture required |
| 2 | No model named | **Closed as far as possible** | Runtime `llama.cpp` at pinned commit; ref + fallback models with artifact/tokenizer/prompt hashes; change invalidates calibration |
| 3 | No numeric budgets | **Closed** | 250 MiB tree, 300 pp, 120k words, 2,000 objects, 30/90 min preflight, 3 repair cycles, 12k/2k tokens per unit, 2 GPU-h ∥ 10 CPU-h |
| 4 | Prose-not-schema records | **Closed** | 9 schemas; `record_type`/`schema_version`/`record_id`/`run_id`/`created_at` on every record; minor-adds-optional, major-requires-migration |
| 5 | No CLI contract | **Closed** | stdout = one JSON result, stderr = human; exit 0–5; stable vs advisory fields separated |
| 6 | Two competing registers | **Closed** | R1–R24 canonical in `app:requirements`; annex explicitly says it "does not create a second list"; checker enforces no `AC*` in annex |
| 7 | Unstaffed AC owners | **Closed** | 8 roles incl. security/policy owner with veto power that "cannot be overruled" |
| 8 | No corpus rights | **Closed (process), open (substance)** | Manifest + `corpus-item.schema.json`; all 5 items `pending-clearance` |
| 9 | No definition of done / exception authority | **Closed** | 6 WP exits; exception authority tiered; 5 never-except conditions |

### Scope-vs-calendar mismatch

My strongest recommendation was to promote the protected-core fallback from
consolation prize to a declared week-six checkpoint. **Adopted, and better than
I proposed**: the annex states the core "is not a consolation prize," makes the
authoring extension *conditional* on passing week six, and names the fallback
("the project narrows to this review utility"). This is the single most
important change in the revision, because it makes the ambitious half of the
product falsifiable on a date rather than at week twelve.

### Three defects from the gap review

| Defect | Status |
|---|---|
| "the fifth criterion" mislabelled (was 7th) | Fixed — now `eq:diagnostic-burden-rule` prose reads correctly |
| Two consecutive `; and` list items | Fixed |
| Orphaned `part0_opening.tex`, `01_decision.tex` | Fixed — archived with README explaining supersession |

---

## 3. What remains — none of it specification work

These are the honest residue. Codex's own summary states them; I confirm all
five and add no new specification gaps.

1. **Model hashes are placeholders.** `artifact_sha256: "required before
   invocation"` is a contract obligation, not a value. Correct for a document
   written before hardware exists, but week 7 cannot start until someone
   downloads a GGUF and records its hash. **Owner: product engineer, week 6.**

2. **All five corpus items are `pending-clearance`.** Every historical fixture
   (BGS, ZLB, SMEwallet, CardNPV, MacroFinance) needs written owner permission.
   The contract permits internal fixture use where the owner allows it, so this
   does not block week 1 — but it blocks any published benchmark, and WP1's
   definition of done requires a passing rights manifest. **Owner: project
   owner, week 1–2. This is the nearest-term critical path item.**

3. **Evidence remains 9/15, `release-blocked`.** Outstanding: independent
   screening, full-text load-bearing anchors, critical appraisal, held-out
   package benchmark, external review. All require human work that cannot be
   automated. Correctly disclosed in-text.

4. **No independent reader review; `human_acceptance: pending_project_owner`.**
   The document is still inside the failure mode it diagnoses. Unchanged since
   Monday and openly recorded.

5. **The four cornerstone sources I flagged remain unimported.** Gopen & Swan,
   Oppenheimer, Kirchenbauer, Sadasivan. `part5_proposal.tex:277` now names
   importing "the four new cornerstone sources" as scheduled work, so this is
   tracked rather than missed.

### One residual observation, not a blocker

`hv plan` — compiling a brief into a claim map, concept-dependency graph,
section jobs, and terminology order — is still the least-specified command
relative to its difficulty. The contract bounds its *inputs, outputs, limits,
and failure behavior*, which is what a contract owes. But no fixture in the
catalogue tests whether a *generated* dependency graph is correct, only whether
a seeded violation is caught. That is an acceptable week-7 risk precisely
because the week-six gate now stands in front of it.

---

## 4. Concrete plan implied by the contract

The document now yields a buildable sequence without further interpretation:

| Weeks | Work | Exit condition | Blocking dependency |
|---|---|---|---|
| 1–2 | Brief, threat fixtures, schemas, rights manifest | Contract files validate; threat fixtures pass | **Rights clearance from 5 project owners** |
| 3–6 | Protected LaTeX core: parser bake-off (pylatexenc / unified-latex / TexSoup), canonical build, source map, protected comparison, CLI results | Fixtures locked; **second operator replays the core** | none |
| **6** | **Go/no-go** | Core replays → continue; else narrow to review utility | none |
| 7–9 | Authoring extension: blueprint, bounded writer, critics, mutation harness, bounded repair, fail-closed release | Mutation + held-out calibration gates pass | **Model artifact hashes recorded** |
| 10–12 | Feasibility case | One released packet, timed reader record, burden account, proceed/revise/stop memo | Live document + named reader approved |

Two things to settle before week 1, both owner decisions rather than
engineering ones:

- **Rights clearance** on the five corpus items — the only week-1 blocker.
- **Reference machine** procurement (8 cores / 32 GiB / optional 12 GiB VRAM),
  since the envelope caps are defined against it and week-6 measurement
  depends on it.

---

## Bottom line

Monday's review found a persuasive argument with too many implicit engineering
decisions. That is fixed. The contract is normative, machine-validated,
enforced in the build, and — verified by mutation — fails when violated. The
week-six gate is a genuine improvement on what I recommended.

"Contract-ready for implementation, not validated product" is the correct
characterization. I would add one sentence: the nearest-term risk is no longer
technical. It is the five `pending-clearance` rights items and one hardware
purchase.

---

## Reproducing this verification

```bash
cd /home/ubuntu/workspace/humanvoice

# contract checker baseline
python3 tools/check_implementation_contract.py

# schemas well-formed, dialect correct, required fields present
python3 - <<'PY'
import json,glob
for f in sorted(glob.glob('schemas/*.schema.json')):
    s=json.load(open(f)); print(f, s.get('$schema','')[-12:], len(s.get('required',[])))
PY

# mutation test: break the contract, confirm the checker fails
cp schemas/implementation_contract.json /tmp/ic.bak
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('schemas/implementation_contract.json'); c=json.loads(p.read_text())
c['runtime']['build']['required_flags']=[f for f in c['runtime']['build']['required_flags'] if f!='-no-shell-escape']
p.write_text(json.dumps(c,indent=2))
PY
python3 tools/check_implementation_contract.py   # expect FAIL, exit 1
cp /tmp/ic.bak schemas/implementation_contract.json

# test suite
python3 -m unittest discover -s tools -p 'test_*.py' -q

# rendered artifact
pdfinfo docs/survey/humanvoice_survey.pdf | grep -E '^Pages'
python3 tools/check_visual_density.py docs/survey/humanvoice_survey.aux

# rights status
python3 -c "import json;d=json.load(open('docs/survey/evidence/corpus_rights_manifest.json'));print([i['redistribution_status'] for i in d['items']])"
```
