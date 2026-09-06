# Review: `humanvoice_survey.pdf` (204 pp., v. 24 August 2026)

**Reviewer:** Claude Opus 5 (Claude Code session)
**Date:** 25 August 2026
**Artifact reviewed:** `docs/survey/humanvoice_survey.pdf`
`rendered_sha256 = 7d1eb206f15dbb0ee84cce54b9435fa5bbdae7f59afe3effd814141551fb9ad2`
`route_source_sha256 = 4be6f4c99037de2784ee8992489579321f67f72e39c4b66c24f9df4067f6a87e`
**Scope:** 28 `.tex` files, 9,109 lines; 204 pages; 74,245 extracted words (51,824 on the main route).

**Questions answered:** (1) prose quality and AI language; (2) omitted literature and
software; (3) soundness of the plan; (4) persuasiveness and honesty about risk.

> **Note on a moving target.** The sources were edited while this review was being
> written. `proposal/04_evidence.tex` and `proposal/09_appendix.tex` changed at 23:04 and
> `humanvoice_evidence_status.json` at 23:20 on 24 August, closing five evidence gates
> (see Q4). Line anchors below are correct as of **25 August 01:15**. All other reviewed
> files are unchanged since 21:08 on 24 August. `humanvoice_survey.bib` is unchanged
> (15:03, 83 entries), so every Q2 finding still holds.

---

## Verdict in one paragraph

The middle of this document — Chapters 5, 10, 12 and 13 — is genuinely good, at or near
the standard asked for. The front matter and the structural layer are not: by the
project's own metric, measured with the project's own recorded threshold, **this
manuscript would fail its own `hv rhythm` acceptance test**. Its intellectual honesty is
unusually high and should be preserved. Its main defects are proportionality (204 pages
to request a 12-week feasibility build), two mutually contradictory delivery schedules,
and a small number of unfalsifiable acceptance criteria.

---

## Q1 — Readability, AI language, prose standard

### Vocabulary layer: clean. This passes.

| Indicator | This document | Note |
|---|---:|---|
| em dash `—` (rendered) | **0** | ZLB case recorded 133; fully repaired |
| en dash `–` (rendered) | 73 | numeric ranges, legitimate typography |
| `delve` | 4 | all inside discussion of Kobak/Juzek |
| `crucial` / `tapestry` / `landscape` | 1 / 1 / 2 | quoted or incidental |
| `leverage` / `seamless` / `holistic` | 0 / 1 / 1 | no AI boilerplate accumulation |
| Sentence length, mean / CV | 18.7 w / 0.587 | healthy burstiness, not metronomic |

No reader will call this "AI slop" on vocabulary. That battle was won.

### Structural layer: fails, and fails against its own yardstick

`part3_literature.tex:71` names **"rule-of-three padding"** and **"negative parallelism
(`not just X, but Y`)"** as signatures of machine writing. `part4_oss.tex:114` quotes
`stop-slop` naming **"Negative listing: 'It wasn't X. It wasn't Y. It was Z.'"** as slop.
The same manuscript:

| Self-named defect | Measured in this document | Reference point |
|---|---:|---|
| Sections opening with "The" | **90 / 206 = 44%** | ZLB **at rejection** was 20/55 = 36%; accepted standard is ≤4 per opener word |
| Paragraphs opening with "The" | 249 / 590 = 42% | — |
| Negative parallelism `, not X` | 151 | self-named AI tell |
| Negative definition `is/are not a…` | 81 | — |
| Sentences opening `It cannot / does not / is not` | 85 | — |
| **All negative-definition sentences** | **424 = 14.9% of prose** | roughly 1 sentence in 7 |
| Tricolon `A, B, and C` | 175 | self-named AI tell ("rule-of-three padding") |
| Four-item lists `A, B, C, and D` | 69 | — |
| `not just / merely / simply` | 16 | self-named AI tell |

Heading grammar is on two templates:

- 229 headings total
- **75 begin "The…"**, **33 begin "What the…"**, 48 begin with a question word
- two templates account for **54%** of all headings
- **3 headings are exact duplicates**, incl. `What the product does in one document`,
  which is simultaneously a section in `part0_opening.tex:188` and the title of Ch. 14

**The clearest illustration is PDF p. 13.** The upper half carries Figure 2.1, diagnosing
*"Repeated shapes mask the point."* The lower half is five consecutive bolded run-in
headings — `Private register. / Mechanical regularity. / Defensive prose. / Missing
substance. / Reader failure.` — of near-identical length, syntax and cadence. The page
demonstrates the disease it diagnoses.

### Private register: the document leaks what it calls the #1 failure

| Token | Occurrences |
|---|---:|
| `BGS` | 46 |
| `ZLB` | 40 |
| `hv` | 20 |
| `sloptrim` | 16 |
| `WP1`/`WP2`/`WP3` | 14 |
| `Phase 2B` | 3 |

In fairness: `BGS` *is* defined on first use (`part1_failures.tex:57`), `ZLB` is defined
at its own section (`part1_failures.tex:390`), and the raw repository paths sit in
footnotes as evidence citations rather than in the argument. This is a much milder
version of the BGS failure, not a repeat of it. But the glossary is at
`19_reference_manual.tex:365` — **p. 182**, roughly 145 pages after first use.

### Against the two named standards

**Economist / NYT (prose).** Uneven. Chapters 5, 10 and 12 reach it:

> "Every floor became a target, every gate got gamed, and the gaming was not malicious;
> it was an agent optimizing exactly what the process measured." — `part1_failures.tex:289`

> "The doctrine is plausible, consistent, and untested." — `part2_existing_tools.tex:250`

Those are publishable sentences. The front matter (`00_orientation`, `01_decision`,
`02_problem`, `part0_opening`) is committee prose: abstract nouns in subject position,
paragraphs closing on "it is not X, it is Y."

**First-year textbook (technical).** The Kobak section (`part3_literature.tex:22-50`) hits
it — "borrowing the excess-mortality design from epidemiology" explains the
counterfactual in one clause, and concrete anchors ("delves" at a ratio near 28) do the
teaching. The rest does not. `V = N(r₀t₀ − r₁t₁)c_r − C` is "hours saved × rate − cost"
dressed in notation, and it appears **twice under two different labels** (`eq:value`,
`eq:opening-value`). `L(θ) = Σ(yₜ − f_θ(xₜ))²` is decorative. Technical readers read
over-formalized arithmetic as padding.

---

## Q2 — Omitted literature and software

Absences below were verified by grep against `humanvoice_survey.bib` and all 28 `.tex`
files, and re-verified at 01:15 on 25 August after the overnight gate closures.
Recommendations marked ✓ were confirmed to exist with real metadata; those marked ✗ are
from reviewer knowledge and **have not been independently verified** — check before citing.

**Material observation:** the gates `known-item-broad-recall`,
`known-item-challenge-recall` and `specialist-domain-coverage` were marked as passing at
23:20 on 24 August, but `humanvoice_survey.bib` has not been touched since 15:03 and still
contains exactly 83 entries. **Coverage gates were closed without a single citation being
added.** Every gap listed below was re-confirmed present after those gates closed. Either
the gate criteria measure search process rather than coverage, or they are calibrated too
loosely to detect the omissions below. This is worth auditing before the gates are used to
support a claim of completeness.

### Literature — Tier A

1. ✓ **Gopen & Swan (1990), "The Science of Scientific Writing," *American Scientist*
   78(6):550–558.** The largest gap. The document's whole thesis *is* reader-expectation
   theory. The rule at `part2_existing_tools.tex:105-107` — put concrete actors in subject
   position — is Gopen & Swan restated without attribution.
   Attaches to `02_problem.tex:30-33`, `04_evidence.tex:77-101`.

2. ✓ **Oppenheimer (2006), *Applied Cognitive Psychology* 20(2):139–156, DOI
   10.1002/acp.1178.** Five experiments: needless complexity *lowers* judged author
   intelligence, mediated by processing fluency. Direct experimental support for the
   central "private register costs the reader" claim, which currently rests only on
   internal cases. Attaches to `02_problem.tex:62-65`, `part1_failures.tex:92-101`.

3. ✓ **Kirchenbauer et al. (2023), "A Watermark for Large Language Models," PMLR
   202:17061–17084.** The document has a section titled "Why authorship detection is not
   the product" (`04_evidence.tex:156`) and R12 on population monitoring — and never
   discusses watermarking as the provenance alternative. "Watermark" appears 3× in 204
   pages, all inside a critique of another tool's *evasion* checks
   (`part4_oss.tex:160-169`). A reviewer will ask "why not provenance instead?" and there
   is no answer on file.

4. ✓ **Sadasivan et al. (TMLR 2024), arXiv:2303.11156.** Recursive paraphrasing drops
   watermark TPR@1%FPR from 99.8% → 9.7%, plus an impossibility result linking optimal
   AUROC to TV distance. This is the **strongest available support for the document's own
   refusal to do per-document detection** — currently missing. `krishna2023paraphrasing`
   and `weberwulff2023testing` make weaker versions of the same point.

### Literature — Tier B
- ✗ Draxler et al., "The AI Ghostwriter Effect" (ACM TOCHI 2024) → `04_evidence.tex:114-120`
- ✗ RAID benchmark (Dugan et al., ACL 2024) → detector robustness
- ✗ Sword, *Stylish Academic Writing*; Williams, *Style*; Doumont, *Trees, Maps and Theorems*
- **Nothing whatsoever on measuring review/revision rounds** — yet "human-feedback rounds
  to acceptance" is the *primary outcome* of the entire program. That construct has zero
  literature behind it.

### Bibliography shape
27 of 83 entries are 2026, 11 are 2025 — currency is excellent. The foundational
writing-studies layer is thin (`swales1990`, `biber1988`, `bereiter1987`, `flower1981`,
`hyland2005`, `graesser2004`). **Well-read on 2024–26 LLM papers; under-read on the
writing-studies canon it is operating inside.**

### Software — Tier A
1. **TexSoup and unified-latex — both absent.** The parser bake-off at
   `part5_proposal.tex:137-140` is Pandoc vs `pylatexenc` only. This is the technical core
   (R15, `hv diff`). Omitting the two best-known LaTeX ASTs is the first thing a technical
   reviewer will hit.
2. **Reader-study tooling — entirely absent.** No jsPsych, Prolific, Qualtrics. Ch. 19–20
   depend on timed forced-choice reader studies and name no instrument for running them.
   This is a plan gap as much as a survey gap.
3. **`chktex` / `lacheck` / `latexindent` — absent.** `hv gate`
   (`part5_proposal.tex:155-160`) reimplements compile-gating without reference to the
   standard LaTeX linters.

### Software — Tier B
- Local inference: only `llama.cpp`; **Ollama, vLLM** absent
- Eval harnesses: only Inspect AI; **promptfoo, DeepEval, lm-evaluation-harness** absent
- Citation identity: GROBID + Crossref; **OpenAlex, Semantic Scholar API, scite** absent (R6, `hv cite`)
- Detection OSS: **Ghostbuster, RADAR** absent
- Reproducible docs: **Quarto, Typst, MyST** absent — Quarto is a plausible integration
  *host*, not a competitor
- **difftastic** / semantic diff absent; `latexdiff` is the only comparison tool named

### Credit where due
The project's own audit already marks `package-held-out-benchmark`,
`specialist-domain-coverage` and `known-item-broad-recall` as **failed gates**. It
predicted these gaps. The fair criticism is that they cluster in the two places on the
12-week critical path: **the parser bake-off and the reader-study instrument.**

---

## Q3 — Is the plan sound? Problems

The architecture is right: staged investment, feasibility before efficacy, refusal of
per-document detection, human reader as final authority. The evaluation chapter's
estimand, safety conditions, comparator-honesty rule and stop conditions are
professionally constructed. Eight problems, by severity:

**1. Two mutually contradictory 12-week schedules.**
- `08_implementation.tex` (`tab:implementation-sequence`): 1–2 / 3–5 / 4–7 / 6–9 / **10–12**
- `part5_proposal.tex` (`tab:delivery`): 1–2 / **2–5** / **3–7** / 6–9 / **9–12**

Different phase boundaries, different (though overlapping) deliverable lists. A funder
reading the second cannot tell which governs.

**2. Cover page contradicts the evaluation chapter.**
- Title page: *"The investment tests whether located diagnosis, protected revision, and
  direct reader evidence **reduce costly review cycles**."*
- `07_evaluation.tex:110`: *"It **cannot** report a reduction in rounds relative to a
  counterfactual that was never run."*

Twelve weeks buys feasibility, not reduction. The cover claims the latter.

**3. Unfalsifiable acceptance criteria.**
- `part5_proposal.tex:104` — `hv leak` must *"fire **heavily**"*
- `part5_proposal.tex:130` — `hv defensive` false-positive rate must be *"low enough that
  an editor reviews its output **without resentment**"*

Neither is a threshold. Conspicuous in a document that otherwise insists on measurement.

**4. The build violates its own held-out requirement.**
R9 requires testing "on documents excluded from rule tuning"; R16 says only held-out
human-labelled evidence supports adoption. But `hv leak`'s rules are **seeded from the ZLB
style contract's ban list** and its acceptance test **runs on ZLB**. Tuned and validated
on the same document.

**5. Engineering is under-scoped.** 12 person-weeks, one engineer, for: LaTeX parsing +
semantic diff + citation identity + privacy boundary + editor integration + 7 CLI
commands. Macro expansion alone could consume most of it — R15 concedes the malformed-macro
problem exists.

**6. Adjudication conflict.** `08_implementation.tex:68` gives the domain writing reviewer
both "finding adjudication" and "live-case interpretation" — judging whether the tool's
output is correct *and* whether the trial succeeded.

**7. No power analysis** (defensible). `17_evaluation_detail.tex:159` gives
`n ≈ (z₁₋α/₂ · s_D / h)²` and honestly states s_D is unknown until the pilot. Methodologically
correct, but it means the sponsor is funding a project whose **follow-on study cost is
unknown**.

**8. Proportionality.** 204 pages and 74,245 words to request a 12-week feasibility build.
v1 was rejected at 16 pages for density; the response was 40 pages, then 204. The document
warns at `part1_failures.tex:298-300`:

> "A project about writing quality will be tempted to spend itself on instrumentation and
> self-description. The BGS record is what that looks like fully grown."

It then did this. **This is the most important finding in the review.**

---

## Q4 — Persuasiveness and honesty about risk

### Honesty: exceptional. Preserve it.

The document volunteers the facts most damaging to its own case:

- Evidence audit status is **`release-blocked`** and says so in the manuscript
  (`04_evidence.tex:212`, `09_appendix.tex:20`). As of 23:20 on 24 August, **10 of 15
  gates pass**; the 5 still failing are `manual-independent-screening`,
  `full-text-load-bearing-evidence`, `critical-appraisal`, `package-held-out-benchmark`
  and `external-review`. (This review was begun when only 5 of 15 passed — see the note
  at the top. The remaining five failures are the ones that require *human* work, which
  is the honest residue.)
- *"The present document is not a completed systematic review"* (`04_method.tex:11`)
- *"The doctrine is plausible, consistent, and untested"* (`part2_existing_tools.tex:250`)
- StoryScope: *"We have not inspected the paper; if it holds…"* (`part3_literature.tex:112`)
- *"The repository does not yet contain a defensible market-size estimate"* (`12_adoption_and_scale.tex:11`)
- Every economic figure flagged *"teaching numbers"* / *"not a forecast"*

Spot-checked four footnoted evidence files (ZLB case study, ZLB style contract, BGS
mission control, BGS release record) — **all exist** in sibling repositories. The evidence
chain is real, not decorative.

### Five things that weaken it

**1. The weakest evidence occupies the most prominent position.** Chapter 1 is a
**fabricated** teaching case — `13_worked_case.tex:5-7` admits it is *"assembled from the
failure patterns… not a claim about a real model's performance."* Meanwhile the project
holds **815 real before/after repair pairs** and a real five-round ZLB rescue that ended
in acceptance. The real material is in Chapter 5. A funder reads the invented case first.

**2. The economic case has no real data and is repeated three times.** 100 documents /
150 per hour / 3.0→2.4 hours appears in `00_orientation.tex:42-55`,
`01_decision.tex:126-148`, and `13_worked_case.tex:312-320`, each time disclaimed.
Disclaiming three times is not evidence; it makes the reader notice the absence three
times.

**3. The risk section is thin.** `part5_proposal.tex:299-313` — four risks in 15 lines, the
only perfunctory passage in an otherwise scrupulous document. **One real risk is missing
entirely: the pilot document is author-selected**, so an author can choose an easy
document and depress the round count. No safeguard is proposed.

**4. The heaviest caveat is on pp. 47 and 160.** `release-blocked / 5-of-15` appears
nowhere on the title page, in the abstract, or in Chapter 1. Placement problem, not
dishonesty — but it is the one fact a sponsor most needs early.

**5. The meta-problem.** `part1_failures.tex:594-597` sets the standard:

> "…should judge itself by one number only: how many rounds of human feedback a document
> needs before acceptance. This survey, whose first version failed that test immediately,
> is not exempt."

`humanvoice_document_status.json` currently reads `human_acceptance:
pending_project_owner`, `independent_reader_review: pending`. The document is inside the
failure mode it defined.

---

## Recommended fixes, in priority order

1. **Delete the duplicate openings.** Five entry points (`00_orientation`, Ch. 1, 2, 3, 4)
   state the same problem and the same request. Keep one. **This alone removes 30–40 pages.**
2. **Promote the real ZLB/BGS material into Chapter 1**; demote or delete the invented
   teaching case.
3. **Merge the two 12-week tables into one.** Reword the cover to "tests whether the
   workflow can be executed and measured," matching `07_evaluation.tex:110`.
4. **Replace `heavily` and `without resentment` with numeric thresholds.** Give `hv leak`
   a non-ZLB held-out fixture so it stops violating R9.
5. **Run the document through its own `hv rhythm` criteria.** Fixing the two heading
   templates (54% of headings) and the 44% "The"-opener rate resolves most of the Q1
   findings mechanically.
6. Add the four Tier-A citations; add a parser bake-off row for `unified-latex`/TexSoup
   and name a reader-study instrument.
7. Add the author-selection bias risk and a mitigation to `part5_proposal.tex:299`.

---

## Appendix: how the counts were produced

All prose measurements strip LaTeX markup and remove `tabular*`, `tikzpicture`,
`equation` and `align` environments before counting, so tables and math do not inflate
the figures. Reproduce with:

```bash
cd docs/survey

# rendered dash counts
pdftotext humanvoice_survey.pdf - | grep -o '—' | wc -l   # em dash  -> 0
pdftotext humanvoice_survey.pdf - | grep -o '–' | wc -l   # en dash  -> 73

# heading census
grep -hoE '\\(chapter|section)\*?\{[^}]*\}' *.tex proposal/*.tex \
  | sed -E 's/\\(chapter|section)\*?\{//; s/\}$//' > /tmp/heads.txt
wc -l /tmp/heads.txt                          # 229
awk '{print $1}' /tmp/heads.txt | sort | uniq -c | sort -rn | head   # The=75, What=33

# duplicate headings
sort /tmp/heads.txt | uniq -d                 # 3 duplicates

# section-opening word, same basis as the ZLB 20/55 measurement
#   -> 90 / 206 = 44% open with "The"
# (python snippet: first word of the first body paragraph after each \chapter/\section)
```

Full measurement scripts are in the session transcript; they are short enough to
re-derive from the commands above. Every figure in this review is reproducible from the
committed sources — no number here is asserted without a command that regenerates it.
