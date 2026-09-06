# What is missing before `humanvoice_survey.tex` can govern an implementation

**Reviewer:** Claude Opus 5 (Claude Code session)
**Date:** 26 August 2026
**Artifact:** `docs/survey/humanvoice_survey.tex` and its 30 included files — 256 pages,
`main_route_word_count = 56,291`, evidence status `9/15 release-blocked`.
**Lens:** not "is this persuasive" (answered 25 August) but **"can a build team execute
from this without inventing the missing half?"**
**Nothing was changed.** This file is a proposal only.

---

## Verdict

**Close, but not yet.** As an argument for why to build, this document is now strong. As
the contract engineers build against, it specifies the *records* well, the *behaviors*
adequately, and the *operating conditions* barely at all. Three gaps would stop a
competent team in week one; five more would cause rework between weeks three and nine.

The single biggest governance risk is not a missing section. It is that **the product
roughly tripled in scope while the calendar and staffing did not move.** The earlier
system diagnosed, protected, and tested with a reader. This one also compiles a brief
into an argument blueprint, drafts prose in bounded units, runs four families of critics,
and repairs failures automatically — still in twelve weeks, still with one product
engineer. `hv plan` alone (claim map, concept-dependency graph, terminology order, visual
plan) is a research problem, not a sprint.

---

## What is already sound — do not rebuild these

Credit where the document has become genuinely usable as a spec:

| Area | Where | Why it works |
|---|---|---|
| Record model with named decision owners | `06_design.tex:58-97` | Nine records, each with required contents *and* who owns the decision |
| Protected-object dictionary with typed normalization | `19_reference_manual.tex:95-122` | Per-type normalization rules; `raw` and `norm` both retained |
| Fixture catalogue | `19_reference_manual.tex:141-196` | Eleven fixtures, each with positive, negative, **and abstention** behavior |
| Correspondence semantics | `16_architecture.tex:139-175` | Typed `≈`, four outcomes, unresolved blocks release; the `a/(b+c)` vs `a/(b−c)` case is exactly right |
| Three-view separation | `16_architecture.tex:216-256` | States what each view *deliberately omits* — the reader-independence requirement made concrete |
| Corpus split into three jobs | `part5_proposal.tex:196-228` | Regression / calibration / held-out now separated; this fixes the earlier tune-and-test-on-ZLB defect |
| The burden rule | `part5_proposal.tex:255-258` | `median(Uₖ − Bₖ) > 0` replaces "fires heavily" and "without resentment" with something falsifiable |
| Fail-closed release with abstention | `06_design.tex:136-141`, `258-267` | Unknown ≠ pass, stated repeatedly and consistently |

The parser bake-off now names `pylatexenc`, `unified-latex` and `TexSoup`
(`part5_proposal.tex:148-150`), and the calendar is single-sourced
(`part5_proposal.tex:272-274`). Both were defects on 25 August. They are fixed.

---

## Tier 1 — a build cannot responsibly start without these

### 1. There is no threat model, and the system now executes untrusted input

The product reads an arbitrary source tree, **compiles it**, and feeds its text to a
generative writer and four critic families. Every one of those is an untrusted-input
path. In 256 pages:

- `prompt injection` — **0 occurrences**
- `shell-escape` / `\write18` — **0 occurrences**
- `untrusted` — **0 occurrences**
- `sandbox` — **0 occurrences**
- `threat model` — 1 occurrence, and it is about *watermarking literature*
  (`part3_literature.tex:271`), not about Humanvoice

`part1_failures.tex:587` names "an instruction-injection boundary" as a design
requirement inherited from the AIpostdoc reader-proxy work. Nothing anywhere specifies
it. `15_component_choice.tex:185` lists "prompt-injection test" as work still to be done
on the selected model — correct, but a governing document should carry the boundary, not
defer it to component selection.

The build wrapper at `16_architecture.tex:86-92` performs four checks — entry point,
double compile, reference resolution, PDF hash. **None of them is "compile with
`-no-shell-escape` in a container with no network."** A manuscript that a Humanvoice
user did not write — a co-author's branch, a merged chapter, a fixture from another
project's repository, which is exactly how the evaluation corpus is assembled — can run
arbitrary commands at preflight.

*Needed:* one page naming the untrusted inputs (source tree, `.bib`, `\input` targets,
image files, model output), the trust boundary, and three controls: no shell-escape, no
compiler network access, and delimited/validated critic I/O.

### 2. No model is specified, and most of the system depends on one

Four preflight gates, `hv draft`, `hv repair`, and six of nine core acceptance tests
depend on model behavior. The document never states which model, what parameter count,
local or remote, or what a model change invalidates. `llama.cpp` is the only runtime
cited anywhere.

This is not a detail to defer. It determines:
- whether "local by default" (`part5_proposal.tex:64`) is achievable at all
- the entire privacy argument in `16_architecture.tex:258-285`
- the per-document cost line in the economic model
- whether `median(Uₖ − Bₖ) > 0` is reachable — a weak local critic that produces noisy
  findings fails that inequality by construction

*Needed:* named model(s) with pinned version or file hash, a declared fallback, the
memory envelope they assume, and a rule stating which fixtures must be replayed when the
model changes.

### 3. Not one numeric operating budget exists

Searched across all 30 files: no latency target, no throughput figure, no memory ceiling,
no maximum document size, no per-document inference cost. `16_architecture.tex:349`
says the envelope is "intentionally modest" and that capacity is "measured per document
and per protected object, not inferred from a model's context-window advertisement" —
the right principle, followed by no numbers.

This matters concretely because the project's own case record contains a **526-page** BGS
volume and a **665-page** MacroFinance monograph, and this survey is itself 256 pages. An
engineer cannot design the extractor, choose a parser, or size the critic context without
knowing whether those are in scope for the MVP.

*Needed:* maximum document size and protected-object count for the first release, target
preflight wall-clock, memory ceiling, and a per-document inference cost cap.

---

## Tier 2 — these will cause rework between weeks 3 and 9

### 4. The records are described in prose, not defined as schema

`19_reference_manual.tex` gives good field tables. But `16_architecture.tex:324` says
"the exact serialization may change during implementation." For a governing document that
is inverted: the records **are** the contract between six commands, across replays, and
between the two operators required by AC16.

Two acceptance criteria are unachievable without a versioned schema:
- **AC8** — "the same run and configuration replay to the same finding ids"
- **AC16** — "another operator can replay a selected run from the recorded environment"

`19_reference_manual.tex:131-133` already gets this half right for normalizers ("when a
later implementation changes `g_k`, it must replay old fixtures"). The same discipline
needs to apply to the records themselves.

*Needed:* a `schema_version` field on every record, a stated compatibility rule, and the
JSON Schema files living in the repository — referenced from the PDF, not printed in it.

### 5. No machine-interface contract for six machine-facing verbs

No exit-code table. No stdout/stderr separation. No statement that machine output is
stable. The entire design assumes these commands are scriptable, replayable and
CI-runnable, and the interface that makes that possible is unspecified.

*Needed:* half a page — exit codes (e.g. `0` pass, `1` gate failure, `2` blocked by
abstention, `3` input/brief error, `4` internal error), machine output on stdout and
human output on stderr, and which fields are stable versus advisory.

### 6. Two acceptance registers exist and neither references the other

- `06_design.tex:279-317` — `tab:core-tests`, **9 tests**, columns: Test / Pass condition / Failure meaning
- `11_expanded_appendices.tex:295-327` — **AC1–AC18**, columns: ID / Behavior / Acceptance observation / Owner

They overlap substantially (protected objects, abstention, reader packet, reproducibility)
but use different vocabularies and different granularity. A build team will not know which
one is the gate, and a sponsor cannot tell whether 9 or 18 things must pass.

*Needed:* one register. Make the other a derived view of it.

### 7. The AC register assigns work to roles the plan does not staff

| AC owner named | Staffed in `08_implementation.tex`? |
|---|---|
| Engineer (7 ACs) | ✅ Product engineer |
| Researcher (3) | ✅ ≈ Evaluation lead |
| Product owner (2) | ✅ Sponsor or project owner |
| Author (2) | ✅ implicitly |
| **Security owner** (AC15) | ❌ **not staffed** |
| **Editor** (AC12) | ❌ **not staffed** |
| **Analyst** (AC5) | ❌ **not staffed** |

AC15 is the one that "blocks an unapproved remote call" — the enforcement point for the
entire local-first privacy commitment — and it is owned by a role that does not exist in
the resource envelope.

### 8. The evaluation corpus has no rights or provenance settlement

`copyright` appears **0 times** in 256 pages. The corpus is assembled from BGS, ZLB,
SMEwallet and BayesFilter material owned by other projects and other repositories
(`part5_proposal.tex:201-228`). The corpus is arguably the most durable asset the twelve
weeks produce — it outlives any given parser choice — and its reuse rights, especially if
the product is ever commercialized or the benchmark published, are unaddressed.

---

## Tier 3 — needed before the live case, not before week one

### 9. No definition of done per work package
`definition of done` appears 0 times. The calendar gives intervals
(`part5_proposal.tex:265-274`) and the deliverables are listed, but no interval has an
explicit exit test. Given the BGS finding that a thesis snapshot "changed only its title
metadata passed a checkpoint because the checkpoint" tested artifact existence rather
than content (`part1_failures.tex:287`), this project of all projects should not leave
completion to judgment.

### 10. Exception authority is unspecified — and it is the highest-risk surface

`ReleaseDecision` records "gate results, exceptions, packet hash, unresolved risks, and
the person who authorized release" (`06_design.tex:85-87`). Nothing states **who may
grant an exception**, or whether an exception can override a protected-object failure.
The document's own central lesson is that "floors get gamed and become ceilings"
(`part1_failures.tex:569`). The exception path is where that will happen.

*Needed:* three lines — who may grant, what may never be excepted (unresolved protected
correspondence), and that exceptions are counted and reported in the feasibility record.

### 11. `hv repair` writes, and its blast radius is undefined

Criterion 4 states "capture and inspect leave the source tree byte-identical"
(`part5_proposal.tex:240`) — good, but that covers inspection only. `hv repair` "applies
a named repair strategy" and rebuilds. Nothing states whether it requires a clean version
control tree, writes to a branch, or edits in place. AC11 (rollback) and AC18 (failure
recovery) imply the intent; neither specifies the mechanism.

---

## Defects worth fixing regardless

1. **`part5_proposal.tex:251`** — "The fifth criterion replaces phrases such as `fires
   heavily`…" The burden rule is criterion **seven**; criterion five is the PDF-hash
   reproduction test. Mis-numbered cross-reference in the one place the document repairs
   a previously flagged defect.
2. **`part5_proposal.tex:242` and `:245`** — two consecutive enumerate items both end
   `"; and"`.
3. **Orphan files.** `part0_opening.tex` and `proposal/01_decision.tex` are on disk but
   no longer `\input` by `humanvoice_survey.tex`. Anyone treating `docs/survey/` as the
   spec — which is exactly what an implementer will do — will read two superseded
   chapters as current. Delete or move to `archive/`.

---

## What I propose adding

**A single annex of roughly six pages — and nothing else.**

The document grew 52 pages in two days and is now 256. The narrative is not the problem
anymore; the governing content is thin *relative to* the narrative. The fix is a short,
dense, explicitly normative annex, not more exposition.

| § | Content | Length |
|---|---|---|
| A.1 | **Threat model** — untrusted inputs, trust boundary, three controls (no shell-escape, no compiler network, delimited critic I/O) | 1 p. |
| A.2 | **Model and runtime specification** — named models, pinned versions, memory envelope, fallback, replay-on-change rule | 1 p. |
| A.3 | **Operating budgets** — max document size, protected-object count, preflight wall-clock, memory ceiling, per-document cost cap | ½ p. |
| A.4 | **Record and schema policy** — `schema_version`, compatibility rule, pointer to JSON Schemas in the repo | ½ p. |
| A.5 | **CLI contract** — exit codes, stream separation, stable-field list, determinism guarantee | ½ p. |
| A.6 | **Unified acceptance register** — one table replacing `tab:core-tests` and AC1–AC18, with owners drawn only from staffed roles | 2 p. |
| A.7 | **Exception and escalation authority** — who may grant, what may never be excepted, how exceptions are counted | ½ p. |

Two conditions on that annex, in the document's own spirit:

- **It is normative, not narrative.** No worked examples, no motivation paragraphs. Those
  exist already in Chapters 14–16.
- **It replaces rather than adds.** A.6 must delete the two registers it supersedes,
  otherwise this document acquires a third acceptance list and proves the BGS thesis one
  more time.

---

## One thing I would raise with the sponsor before week one

The scope question is not addressed anywhere in the document, and it is the decision most
likely to determine whether the twelve weeks succeed.

`hv init` + `hv preflight`(integrity) + protected comparison + reader task is a
demanding but plausible twelve weeks for one engineer. Adding `hv plan` (blueprint
compiler with dependency graph and terminology ordering), `hv draft` (bounded generative
writer), `hv repair` (repair controller with oscillation detection), and three further
critic families is, on any ordinary estimate, a multi-quarter program.

`part5_proposal.tex:160-165` already contains the right instinct — it describes a
fallback where "if the diagnostic layer fails to earn attention, the source snapshot and
protected comparison can still become a small review utility." I would make that the
**declared week-six checkpoint** rather than a consolation prize: build the protected
core first, and treat planning, drafting and repair as the second increment that the
first increment earns.

That is a sponsor decision, not a reviewer's. But the document should ask it explicitly
rather than presenting a tripled scope inside an unchanged calendar.

---

## Verification note

Every count and file:line anchor above was derived from the sources at
**26 August, 03:10**. The tree is being edited actively — `16_architecture.tex` changed at
02:00 and `part5_proposal.tex` at 01:38 on the 26th — so re-derive before acting on any
specific line number. Absence claims (`prompt injection`, `shell-escape`, `copyright`,
`definition of done`, `exit code`) were checked by case-insensitive grep across all 30
`.tex` files concatenated, not against a subset.
