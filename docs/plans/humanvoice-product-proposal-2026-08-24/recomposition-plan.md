# Humanvoice proposal recomposition plan

Date: 2026-08-24

## Objective

Produce one reader-facing proposal that can support an implementation decision
for humanvoice. The audience is a coalition of former professors now acting as
executives, funders, domain scholars, and technical owners. They should not
need repository history, audit identifiers, or an oral briefing to understand
the problem, the product, the evidence, the economics, and the requested next
decision.

Canonical source: `docs/survey/humanvoice_survey.tex`

Canonical output: `docs/survey/humanvoice_survey.pdf`

Baseline hashes at the start of this run:

- source `aa6c09a9ff189eac674871d96bb99b9a2e168cbd0d6b21fa02450e333d1ba0d9`
- PDF `bafa1a404bef26ab26d1c9b9d269b21d6c1865062f30c82963e1227fe09de0d6`

Transformation class: `whole_document_recomposition`.

Scientific profile: `conceptual` plus `implementation-bearing`, with a
bounded empirical feasibility design. The proposal must not claim efficacy
before the study is run.

## Diagnosis being repaired

The current 58-page volume is a literature and package dossier with proposal
front matter. Its main route gives more space to internal history and tool
inventories than to the product. The product appears as an abstract flow and
seven command contracts, not as an end-to-end user experience. Its scholarship
is concentrated in AI-writing fingerprints and detection even though detection
is a non-goal. Its audit is release-blocked (5 of 15 evidence gates passed),
and its economic equation has no measured inputs. The new manuscript must
preserve useful evidence while changing the order, emphasis, and prose.

## Reader contract

The reader must be able to answer these questions from the rendered PDF alone:

1. What costly decision problem opens the proposal?
2. What happens to one document as it passes through humanvoice?
3. What does the product add to the current bundle of LLM editing, linting,
   version control, citation checking, and human review?
4. Which research findings make the design plausible, and which claims remain
   open?
5. What exactly is in the MVP, and what is deliberately outside it?
6. What comparison and reader outcome would justify further investment?
7. What is being authorized now, at what resource envelope, and what would
   cause a stop or redirection?

The author cannot count an explanation given outside the document as a passed
answer. The author-only state remains `author_repaired_draft` until an
independent reader and the project owner read the exact PDF.

## Claim spine

**Problem.** A technically correct document can still fail because it transfers
the work of reconstructing its purpose, mechanism, evidence, and requested
action to a scarce expert reader. Each failed review creates another diagnosis,
revision, and rereading cycle.

**Proposition.** Humanvoice should be a local-first revision system that (1)
locates diagnosable problems, (2) protects meaning-bearing content while an
author revises, and (3) measures acceptance by a named human reader.

**Principal rival.** Continue with the current bundle of general LLM editing,
prose linters, version control, citation services, and manual review.

**Running case.** A funding proposal that compiled and passed agent review but
left a low-context expert unable to state its purpose or requested action.

**Decision request.** Authorize a bounded MVP, an adjudicated evaluation set,
and one live-document feasibility run. Do not authorize deployment or an
efficacy claim.

## New narrative spine

1. **The decision.** Open with the failed reader decision, its economic cost,
   the rival bundle, and the bounded request.
2. **The problem as reader work.** Show the layered failure in the running case
   and explain why existing checks stop short of reader acceptance.
3. **The product in one document.** Work one illustrative technical paragraph
   through finding, author revision, protected diff, and reader decision. This
   is the proof of product concreteness.
4. **What the evidence says.** Organize scholarship by the design questions it
   answers: assistance and productivity, feedback and revision, comprehension
   and readability, trust/diversity/integrity, and human--AI evaluation.
5. **The field and the wedge.** Compare software categories and the current
   bundle; retain only package facts that change a product or adoption choice.
6. **The design.** Define the protected document model, four actors, local-first
   architecture, MVP boundary, and interfaces an engineer can implement.
7. **The test and the economics.** State the estimand, comparator, reader
   protocol, outcomes, cost model, uncertainty, and stop rules.
8. **The implementation decision.** Give milestones, people, person-weeks,
   deliverables, dependencies, and the exact authorization boundary.
9. **Technical and evidence notes.** Keep search limitations, package status,
   schemas, and compact internal cases in appendices, without making them the
   narrative.

## Content allocation targets

These are inspection targets, not quality scores:

| Material | Target share of main-text words | Treatment |
|---|---:|---|
| Problem, product, and running case | 25--30% | Main narrative |
| Literature synthesis and alternatives | 20--25% | Main narrative, organized by design question |
| Product/technical design | 20--25% | Main narrative with one worked artifact |
| Evaluation, economics, and implementation | 20--25% | Main narrative |
| Package catalog and internal history | under 10% combined | Compact appendix/backstage record |

The final PDF may be long, but no chapter may become a catalog merely to meet a
page target.

## Product proof required in the manuscript

The worked case must contain all of the following in one continuous sequence:

- a source excerpt with an identifiable technical claim;
- at least three located findings, including one deterministic and one
  substantive editorial question;
- an author-controlled revision;
- a protected-object comparison showing what was preserved and what changed;
- a reader rubric with a decision and a remaining uncertainty; and
- an explanation of how the same record becomes an evaluation observation.

The case is illustrative, not an efficacy result. It must make the product
visible without pretending that a mock-up proves value.

## Scholarship requirements

- Use the existing audited sources where their inspection depth supports the
  sentence; classify stronger statements as provisional when it does not.
- Reorganize the literature around design questions rather than detector
  categories. Include direct positive, negative, heterogeneous, and integrity
  evidence.
- Cover the adjacent literatures needed by the product question: human--AI
  writing interaction, feedback and revision, readability/cohesion,
  professional/technical writing, evaluation, citation reliability, and
  disclosure/provenance.
- Treat software documentation as suitability evidence, not effectiveness
  evidence. State that held-out package benchmarks are still outstanding.
- Put the search method and the 5/15 gate status in one compact evidence note;
  do not repeat caveats throughout the narrative.

## Skeptical pre-edit audit

The plan fails and must be revised before scaling if any of these are true:

- the first two pages contain audit administration before the product problem;
- the running example cannot be followed without the appendix;
- a requirements matrix or command list is doing the work of explaining the
  product;
- the main claim is still “connect existing tools” without a specified user,
  artifact, interaction, and measurable outcome;
- the economic section supplies only symbols and no illustrative sensitivity or
  data-collection route;
- detection, repository history, or governance becomes a feature rather than a
  bounded design constraint;
- a claim is promoted because a structural checker or build passed; or
- the proposal gets longer by moving audit records into prose.

The plan passes this audit only if it produces a complete worked case, a clear
MVP boundary, an honest evidence status, and a decision a sponsor can actually
authorize.

### Audit result

`PASS WITH CONDITIONS` on 2026-08-24. The plan is proportionate to a
conceptual, implementation-bearing proposal and keeps the audit and search
records backstage. Before the complete route is promoted, the difficult-unit
forward test is the worked product case in Chapter 3, followed by a reset
low-context read of Chapters 1--4. A failure there triggers recomposition of
the route; it does not trigger more tables, package searches, or governance
records. The remaining hard condition is human review of the rendered PDF.

## Execution and verification

1. Preserve the current source and PDF hashes in this plan; do not erase the
   prior candidate or its audit records.
2. Replace the reader-facing route with the new cumulative chapters. Existing
   part files remain available as source material but are not automatically
   entitled to remain in the PDF.
3. Reduce the structural checker to a diagnostic that checks document boundary,
   citations, build integrity, and obvious backstage leakage. It must not
   pretend to certify readability or persuasion.
4. Build the PDF with the repository script and BibTeX; reject unresolved
   citations and references.
5. Inspect the rendered title, opening, worked case, literature synthesis,
   design, economics, implementation, and appendix pages at readable scale.
6. Run a cold-reader reconstruction using the seven questions above. This is an
   author diagnostic, not human acceptance; record the pending independent read.
7. Report remaining evidence and acceptance limits explicitly.

## Promotion boundary

The result of this execution may be promoted to `author_repaired_draft` only.
It cannot be called accepted, release-ready, or efficacy-proven until a named
independent reader and the project owner have read the exact rendered PDF and
recorded their decisions.

## Execution record

The canonical route was recomposed into eight cumulative chapters and one
compact appendix. The final build produced a 38-page PDF. The structural
checker passed all required diagnostics and explicitly reports that it cannot
certify readability, scholarship completeness, persuasion, or human
acceptance. BibTeX and two full pdfLaTeX passes completed without unresolved
citation/reference warnings or overfull boxes. Rendered pages covering the
title, opening, worked case, evidence synthesis, design, evaluation,
implementation, appendix, and bibliography were inspected at page scale.
The delivered route hash is `4413ad43959509c31811f1d5d031df67f747096020a82e31e8faa396bd788871`;
the rendered PDF hash is `01ea408e3e338c05e0f2ce1d857ea492c71420648fed708008bc8e8c466bf595`.

The final visual pass repaired two page-flow defects found by inspection: a
stranded sentence at the end of the product chapter and a split software
paragraph that began the next page with a sentence fragment. The CLI example
was also checked in extracted PDF text to ensure its `--reader` and
`--decision` flags remain copyable.

As a governance repair, the audit publisher now leaves its implementation
dossier inside `docs/survey/audit/<run>/` and publishes only compact evidence
summaries. The human-readable audit report is also kept in the run directory;
the pre-existing duplicate dossier and report were moved to
`docs/survey/archive/backstage-audit-2026-08-23/`; the canonical survey
directory now has one reader-facing PDF.

The build script fixes the PDF snapshot metadata through `SOURCE_DATE_EPOCH`;
two consecutive builds now produce the same 38-page PDF hash.

The author cold read is recorded in
`author-read-2026-08-24.md`. It confirms the intended decision spine while
leaving independent reader review, project-owner authorization, and the ten
failed evidence gates pending.
