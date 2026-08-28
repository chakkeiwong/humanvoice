# Review: Humanvoice master program v1.1

**Reviewer:** Claude Opus 5 (Fable)
**Date:** 26 August 2026
**Artifact reviewed:** `docs/plans/humanvoice_master_program_v1.1_2026-08-26.md`
**Prior version:** `docs/plans/humanvoice_master_program_2026-08-26.md` (v1.0)
**Review request:** `docs/plans/humanvoice_master_program_v1.1_review_request_2026-08-26.md`

**Recommendation: AUTHORIZE G0 with two pre-WP1 conditions.**

---

## Verdict

v1.1 is a substantial improvement over v1.0 and is ready to govern implementation with
two changes before WP1 starts. The document correctly shifted from "implementation
specification" to "executable program" — it now has gates with named owners, decision
templates (G0–G4), explicit starts/stops, and a runtime profile.

The program is **faithful to the contract**, executable, and complete except for two
work-products that must exist before anyone writes `hv init`. Neither is a judgment call;
both are concrete artifacts that block the start of engineering.

---

## Summary of changes v1.0 → v1.1 (assessed)

| Change | Assessment |
|---|---|
| Added G0–G4 gate structure with decision templates | **Excellent** — makes "true gate at week 6" precise; every gate now has owner, inputs, stop condition |
| Separated governing rules (§2) from phase detail | **Good** — fail-closed, never-silent, source-byte-identical, security-veto, never-except extracted as invariants |
| Added §6 schema reconciliation and §8 runtime profile | **Essential** — both were implied, now explicit and verifiable |
| Added §7 fixture/rights/regression policy | **Good** — clarifies the 815-repair corpus is ZLB history, not a training set |
| Split §10 schedule from §4 work packages | **Good** — calendar now separate from deliverables |
| Expanded §11 test tiers from unit/regression to 5 tiers | **Correct** — contract, fixture, mutation, regression, reader each need different harnesses |
| Changed structure from 9 to 15 top-level sections | **Neutral** — adds navigation cost but groups related material better |

One concern: v1.1 grew from 33K to 36K. The self-imposed limit (§6 in v1.0, now §2 rule 9
in v1.1) says "one plan, one result." This is still one plan, but the line between
"executable detail" and "re-exposition of the contract" is getting thin. If v1.2 is
needed, consolidate rather than add.

---

## Answers to the 10 review questions

### Q1: Does any `hv` command or installable package exist?

**No.** Verified:
- No `pyproject.toml`, `setup.py`, or `src/humanvoice/__init__.py`
- `which hv` returns nothing
- `import humanvoice` fails

**Status:** correct. v1.1 states "no product code has been written" (line 4) and §0
confirms "the repository currently reports … no `hv` commands exist." Accurate.

### Q2: Does `fixtures/manifest.json` exist?

**No.** The `fixtures/` directory does not exist.

**Status:** this is one of the two **pre-WP1 blockers** (see §Conditions below). WP1's
own definition of done requires "threat fixtures pass validation," and v1.1 §7 requires
"a fixture manifest with source and answer-key hashes before WP1 starts." The artifact is
specified but does not exist. Must be created before G0.

### Q3: Do the JSON Schemas' `required` fields match what the program calls mandatory?

**Checked.** All 9 record schemas carry `required` arrays:

| Schema | Required count |
|---|---|
| `authoring-brief` | 11 |
| `argument-blueprint` | 10 |
| `finding` | 9 |
| `revision` | 10 |
| `preflight-run` | 10 |
| `release-decision` | 10 |
| `cli-result` | 7 |
| `corpus-item` | 12 |
| `runtime-manifest` | 9 |

**Cross-check:** v1.1 §6 table lists 9 schemas with field counts. The table matches the
actual schemas except for one discrepancy — `runtime-manifest` shows "11+" in the table
but the schema has 9 `required`. Minor; the schema is authoritative.

**Status:** schemas are real and enforce structure. The contract checker already asserts
all 9 exist. **Pass.**

### Q4: Does `tools/check_program_consistency.py` exist?

**No.** The file does not exist.

**Status:** this is the second **pre-WP1 blocker**. v1.1 §11 states: "Before WP1 starts,
the program consistency checker must pass. This check asserts that … [6 conditions]." The
checker is specified but does not exist. Must be created before G0 (see §Conditions).

### Q5: Does a `tests/` directory with test scaffolding exist?

**No.** No `tests/` directory exists. The 47 tests currently passing are in `tools/test_*.py`.

**Status:** acceptable. v1.1 does not require a `tests/` directory before WP1 — it
requires the consistency checker and fixture manifest. The existing `tools/test_*.py`
layout matches the convention established in 47 working tests. When P1 tests are written,
they can live in `tools/test_threat_controls.py`, etc., or be moved to `tests/`. Not
blocking.

### Q6: Do the historical replay artifacts (ZLB 815 repairs, sloptrim calibration) exist?

**Partially.** `vendor/sloptrim/` exists but contains only installation instructions, not
calibration data. The 815-repair corpus is referenced in `docs/survey/evidence/` but I
did not find a file named `frozen_repair_map_v7.jsonl` in this repository.

**Status:** v1.1 §7 says these are *"historical records from the sibling BayesFilter and
DynareMCP repositories; this repository holds pointers and answer keys."* If true, then
this repository only needs the answer keys, and WP1 does not depend on them — they're
used at G2 (regression gate). The program should clarify **where the 815 pairs live** and
whether the pointer exists here. Not blocking G0, but must be resolved before G2.

**Recommendation for v1.2:** add one sentence to §7 stating the repository and file path
for the 815-repair corpus and the three sloptrim calibration documents.

### Q7: Does `tools/run_fixture_suite.py` exist?

**No.** The file does not exist.

**Status:** v1.1 §11 requires it to exist "before WP1 starts." This is implied by the
fixture-manifest blocker (Q2) — you cannot run a fixture suite without a manifest. Once
Q2 and Q4 are resolved, this becomes a 50-line harness. Not separately blocking.

### Q8: Do decision-record templates or prior instances exist?

**No G0–G4 templates found.** No files matching `*G[0-4]*`, `*gate*`, or
`*decision*record*` in `docs/plans/`.

**Status:** v1.1 specifies the structure of each gate's decision record (§5), but no
template exists. However, the specification in §5 is detailed enough to write one from.
Not blocking — the G0 decision can be the first instance. But having a template before G0
would improve consistency.

**Recommendation for v1.2:** add `docs/plans/templates/gate_decision_record.md` with
fields from §5.

### Q9: Does P2.4's claim to "reuse `tools/concept_density.py`" hold?

**Yes.** `tools/concept_density.py` exists, 438 lines, implements `first_use_audit()`,
`analyze()` with burst detection, and `added_assertions()`. v1.1 P2 correctly references
it and does not claim to have extended it yet.

**Status:** accurate. **Pass.**

### Q10: Is v1.1 an acceptable expansion over v1.0?

**Yes, with restraint.** v1.0 was 33K, v1.1 is 36K (+9%). The expansion bought real
value — gates with owners, decision templates, runtime profile, fixture policy, and test
tiers. But the program's own rule (§2.9) is "one plan, one result," and the BGS lesson
was "floors get gamed and become ceilings." If the program continues expanding, it will
become the thing it warns against.

**Status:** v1.1 is still a single plan. If v1.2 is needed, consolidate duplicate
exposition rather than add new sections.

---

## Two conditions before authorizing G0

Both are work-products v1.1 itself declares must exist "before WP1 starts."

### Condition 1: Create the fixture manifest

**What:** `fixtures/manifest.json` with entries per v1.1 §7:
```json
{
  "fixture_manifest_version": "1.0",
  "fixtures": [
    {
      "id": "F-THREAT-T1-READONLY",
      "type": "threat",
      "source_hash": "sha256:...",
      "answer_key_hash": "sha256:...",
      "rights_status": "internal-use-only",
      "description": "read-only snapshot; no write outside allowlist"
    },
    ...
  ]
}
```

Minimum 11 fixture types × 3 test cases (positive/negative/abstention) = 33 entries. The
5 threat fixtures (T1–T5, 3 each = 15) can be stubs initially, but their IDs and expected
outcomes must be listed.

**Why blocking:** WP1 `done` requires "threat fixtures pass validation," and v1.1 §7
requires the manifest before WP1. You cannot write `test_threat_controls.py` without
knowing which fixtures to load.

**Who creates it:** evaluation lead, from the 11-fixture catalogue at
`19_reference_manual.tex:148-179` and the T1–T5 controls at contract §trust_boundary.

**Effort:** 4–6 hours to list the 33 IDs and write the schema; threat fixture source
files follow in P1.

### Condition 2: Create the program consistency checker

**What:** `tools/check_program_consistency.py` that asserts (from v1.1 §11):
1. Every G0–G4 gate in the program has an owner in the staffed-roles list
2. Every WP deliverable in §4 maps to a schema in `schemas/`
3. Every requirement R1–R24 appears in at least one phase
4. Every phase's requirement list matches `humanvoice_product_requirements.json`
5. Fixture manifest exists and every fixture has source + answer-key hashes
6. No fixture is marked both `internal-use-only` and used in an external claim

Plus a test: `tools/test_program_consistency.py` that mutation-tests it (remove a gate
owner, break a requirement mapping, mark a fixture wrongly → checker fails).

**Why blocking:** v1.1 §11 states "before WP1 starts, the program consistency checker
must pass." Without it, the program's claim to be "executable" is unverified.

**Who creates it:** product engineer, 2–3 hours.

**Model:** extend the existing `check_implementation_contract.py` (133 lines), which
already validates the contract's structure.

---

## Recommendation: AUTHORIZE G0

Once the two conditions above are met, **authorize G0 and WP1**.

The G0 decision record should state:
- **Decision:** authorize WP1 (contract, brief, parser, protection)
- **Inputs:** v1.1 program, passing contract checker, passing consistency checker, fixture
  manifest with 33 entries
- **Conditions on WP1:** rights clearance for 5 corpus items (still `pending-clearance`);
  reference machine procured (8 cores / 32 GiB); T1–T5 fixtures pass before parser
  bake-off starts
- **WP1 exit:** source map + protected manifest + CLI results locked on fixtures; parser
  scorecard published including failures
- **Next gate:** G1 at end of WP1, decision by product engineer + security owner

---

## What v1.1 gets right (preserve in any v1.2)

| Strength | Where | Why it matters |
|---|---|---|
| Fail-closed at every gate | §2 rule 1, §5 all gates | Abstention ≠ pass; distinguishes this from BGS |
| Security veto cannot be overruled | §2 rule 6, G1–G4 | Makes T1–T5 enforceable, not advisory |
| 5 never-except conditions | §2 rule 7 | Prevents exception authority from becoming a bypass |
| Source byte-identical after every operation | §2 rule 3 | Proof that "report, never auto-fix" is real |
| Week-six gate is genuinely conditional | G2, §3 | De-risks the ambitious half; stopping is not failure |
| Fixture negative and abstention cases required | §7, §11 | Prevents false-pass by dropping hard inputs |
| Historical numbers cannot be retro-fitted | §7 | 133 dashes, 109/109 equations, 815 repairs locked before anyone tunes |
| One metric: feedback rounds to acceptance | §2 rule 10, §9 | Everything else is instrumentation |

---

## Minor issues (fix in v1.2 if one is needed; not blocking)

1. **§6 schema table vs actual schemas:** `runtime-manifest` shows "11+" required fields
   in the table but the schema has 9. The schema is authoritative; update the table or
   remove the column (since the schemas themselves are the spec).

2. **§7 corpus location ambiguity:** The 815-repair corpus and sloptrim calibration data
   are "from sibling repositories," but no file path is given. Add one sentence: *"The
   815 ZLB repair pairs are at
   `BayesFilter/docs/surveys/zlb_discontinuous_hmc/frozen_repair_map_v7.jsonl`; sloptrim
   calibration documents are at …"*

3. **§10 capacity assumptions not validated:** The schedule assumes "one product engineer,
   half-time evaluation lead, available domain editor, available security owner." If any
   of those is not actually staffed, G0 should record the deviation before WP1 starts.

4. **No G0–G4 decision template:** §5 specifies the structure, but no reusable template
   exists. Add `docs/plans/templates/gate_decision_record.md` with the 8 fields.

5. **Test-tier naming inconsistency:** §11 introduces "contract / fixture / mutation /
   regression / reader" but earlier sections sometimes say "unit / integration /
   regression." Consolidate on one vocabulary. (Minor — intent is clear.)

---

## What I checked beyond the 10 questions

- **Traceability:** Every R1–R24 still traces to exactly one phase per the register's
  `phase` field. v1.1 did not break this.
- **Contract mutation test:** Re-ran my earlier 4 mutations (remove `-no-shell-escape`,
  set `remote_default: allow`, delete T4, delete exit 5). Checker still catches all four.
- **WP `done` strings:** All 6 work packages still quote the contract's `done` field
  verbatim or paraphrase it faithfully.
- **Never-except list:** The 5 conditions in §2 rule 7 match
  `implementation_contract.json` § `release_authority.never_except` exactly.

---

## If you must stop instead of proceeding

If the sponsor judges that the two pre-WP1 conditions are too much setup, or that the
week-six gate makes the path too uncertain, the honest move is **stop before WP1** rather
than quietly dropping the gate or the fixture discipline.

The stop decision would record: protected-source core remains valuable as a standalone
direction, but this twelve-week path requires more front-loaded scholarly and fixture
work than the current commitment supports. The contract and evidence base remain assets
for a future attempt.

That is not my recommendation. The two conditions are 6–9 hours of work, and both are
work the program itself declared necessary. But if the answer is stop, do it at G0 rather
than after engineer-weeks are spent.

---

## Disposition

**AUTHORIZE G0** once:
1. `fixtures/manifest.json` exists with 33+ entries (11 types × 3 cases), per §7
2. `tools/check_program_consistency.py` exists and passes, per §11

Then:
- Product engineer writes the G0 decision record
- Sponsor signs it
- WP1 (contract, brief, parser, protection) is authorized to start
- No `hv` command is written until T1–T5 threat tests pass

The program is ready. The next move is yours.
