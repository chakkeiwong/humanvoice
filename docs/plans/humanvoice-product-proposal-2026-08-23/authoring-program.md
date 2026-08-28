# Humanvoice product proposal recomposition program

Date: 2026-08-24

Purpose: produce the reader-facing product proposal that can authorize and
guide a bounded implementation of humanvoice.

Transformation class: `whole_document_recomposition`

Scientific profile: conceptual and empirical, with the
`implementation-bearing` modifier.

Canonical reader-facing source:
`docs/survey/humanvoice_survey.tex`

Rendered artifact: `docs/survey/humanvoice_survey.pdf`

Document form: one reader-facing volume carrying the proposal, the literature
and software review, the implementation design, and the internal case as an
appendix. Search, identity, and reproducibility records stay backstage.

Evidence record: `docs/survey/audit/latest/`

Canonical standard:
`../claudecodex/docs/templates/scholarly-research-proposal/`

Current authoring state: `author_repaired_draft`

Human acceptance: pending the project owner's read of the rebuilt PDF.

## Baseline and diagnosis

The generated proposal published on 2026-08-22 is the rejected baseline. It is
preserved byte for byte in `docs/survey/audit/latest/final_product_proposal.*`.
The standalone 23 August candidate is preserved in
`docs/survey/archive/author-repaired-proposal-2026-08-23/`; neither is a
current reader-facing route.

| Baseline artifact | SHA-256 | Scale |
|---|---|---:|
| `final_product_proposal.md` | `6175f82a07831f7329cf6f55cb89d7c06946833a4637e8a366648fd8f781b997` | 6,508 words |
| `final_product_proposal.pdf` | `2455c0a733f18f4a7a24286d7ae9d204be7d88c22fb9d797bbc832d18c319e09` | 14 pages |
| `humanvoice_survey.tex` | `cf58787fa334d50427b4956a28175bf8e3989dcf8da0aacbff1ed5dd851e3d35` | 47-page rendered survey with included parts |

The baseline is not a product proposal. It is an implementation dossier shaped
by the evidence pipeline. Its opening asks the reader to process generation
metadata, search counts, review status, and release gates before encountering a
concrete user or product experience. The survey makes a related error by
placing document history and a long internal failure chronology in the main
reading route.

### Skeptical plan audit

The failed plan optimized evidence completeness and reproducibility as though
they could promote reader-facing prose. That substituted observable proxies
for the actual outcome. The following defects must be corrected before this
program can scale:

- Wrong artifact owner: the audit runner generated and published the public
  proposal.
- Wrong baseline: the generated dossier was treated as a draft to augment,
  rather than as material to recompose.
- Wrong promotion criteria: compilation, manifests, citations, and gate counts
  were checked; comprehension and persuasion were not.
- Wrong audience: the document addressed an auditor and implementer before the
  financier, economist, and project owner.
- Missing stop condition: more evidence and more requirements could always be
  added even when the public story became worse.
- Stale context: the proposal repeated the exact governance leakage diagnosed
  by its own internal cases and governing policy.

This program therefore keeps one cumulative public narrative, with evidence and
implementation records attached as backstage material and a technical
appendix. It qualifies the narrative on a short prototype and requires a human
decision on the rendered manuscript. Evidence limitations block strong efficacy
claims; they do not require audit language on the title page.

## Reader coalition

| Reader | Shared understanding required | Specialist exit | Decision enabled |
|---|---|---|---|
| Project owner or funder | The costly writing failure, proposed remedy, expected value, and bounded request | Pilot economics and stop rules | Authorize, revise, or reject the build |
| Economist or domain scholar | Why the intervention is plausible and how evidence constrains it | Literature survey and evidence record | Challenge the claim, rival, or evaluation |
| Product engineer | What must be built without inventing product choices | Technical appendix and requirements trace | Estimate and implement the MVP |
| Evaluation lead | What outcome distinguishes success from surface improvement | Pilot design and evidence matrix | Preregister and run the comparison |

Entry floor: the reader understands research writing and ordinary software
projects, but knows no repository history or internal identifiers.

Shared destination: every reader can explain the problem, the humanvoice
workflow, why generic LLM editing is an insufficient rival, the first build,
the pilot endpoint, and the decision requested now.

## Claim spine

Opening problem: technically correct documents can consume repeated rounds of
scarce expert-reader attention because current checks find surface defects but
cannot determine whether the argument is understood.

Main proposition: humanvoice should be built as a reader-first revision system
that locates diagnosable defects, protects meaning during editing, and reserves
acceptance for a human reader.

Supporting claims:

1. Existing linters, generic LLM rewriting, and governance review each solve
   only part of the revision problem.
2. The literature supports bounded assistance, localized feedback, protected
   revision, and direct human evaluation, but does not establish efficacy for
   expert technical writing.
3. A twelve-week MVP and one-document feasibility run can establish technical
   viability and supply the data needed to price and design an efficacy study.

Principal rival: use an ordinary LLM editor, existing prose linters, and manual
review without a dedicated product.

Running example: a funding proposal that compiled and passed agent review, yet
left its first human reader unable to state its purpose or requested action.

Decision request: authorize a bounded MVP and feasibility run with explicit
stop conditions; do not authorize deployment or claim efficacy.

## Cold-reader questions

A reader must answer these from the rendered manuscript alone:

1. What expensive or consequential problem opens the proposal?
2. What happens to one document when it passes through humanvoice?
3. Why are generic LLM editing and ordinary linting insufficient?
4. What evidence makes the product plausible, and what remains unproved?
5. What is built during the first twelve weeks?
6. What result would stop the project?
7. What decision is requested now?

An absent or materially wrong answer is a repair trigger. An author explanation
outside the proposal does not repair it.

## Artifact boundary

| Material | Main manuscript | Technical appendix | Backstage evidence |
|---|---:|---:|---:|
| Concrete problem, product journey, value, rival, request | yes | no | supporting only |
| Bounded literature synthesis that changes design | yes | deeper detail | full treatment |
| MVP architecture and milestones | yes | detailed interfaces | requirements trace |
| Pilot endpoint, comparator, stop rules, economics | yes | design detail | machine-readable plan |
| Search counts, API failures, screening ledgers, DOI identities | no | no | yes |
| Requirement IDs, schemas, hashes, manifests, commands | no | selected detail | yes |
| Development history and rejected-version chronology | one motivating case only | no | appendix or audit |

The audit runner may generate evidence and implementation dossiers. It must not
write or overwrite the canonical reader-facing manuscript or its PDF/status
record.

## Preservation map

| Intellectual object | Source | New role and destination |
|---|---|---|
| Reader rejection and costly feedback loop | `part1_failures.tex` | Opening case, compressed to the minimum needed |
| Layered defect model | `part1_failures.tex` and policy | Product rationale and diagnostic sequence |
| Localized, non-mutating diagnostics | `part3_literature.tex`, `part4_oss.tex` | Product experience and MVP |
| Meaning-preserving protected diff | internal cases and parser survey | Product promise and technical appendix |
| Human acceptance endpoint | internal cases and review literature | Pilot design |
| Productivity heterogeneity and frontier risk | external studies | Rival analysis, stratification, and stop rules |
| Feedback and higher-order-writing limits | external studies and reviews | Reason not to automate acceptance |
| Parser and tool shortlist | software survey | Technical appendix; benchmark before adoption |
| Sixteen detailed requirements | audit protocol | Machine-readable trace, summarized in public prose |
| Search and appraisal limitations | audit run | One honest evidence-status paragraph plus link |

## Prose disposition

| Baseline unit | Disposition | Reason |
|---|---|---|
| Status line, timestamp, protocol ID | remove from public proposal | Backstage generation metadata |
| Evidence-at-a-glance counts | relocate | Search administration is not the opening case |
| Search coverage and failure accounting | relocate | Belongs in the evidence audit |
| Sixteen bold requirement bullets | recompose | Preserve choices, remove database-row presentation |
| Seven command contracts | compress and relocate | Main text needs product behavior; appendix can hold interfaces |
| Gate list and release decision | relocate | Proposal state and evidence state are separate |
| Reproducibility commands and artifact inventory | relocate | Maintainer documentation |
| Evidence register | relocate | Backstage evidence matrix already owns it |
| Product boundary, evaluation, software strategy, economics | recompose | Useful intellectual content in the wrong voice and order |
| Survey section "A short history of this document" | remove from main route | Author journal, not scholarship |
| Long internal failure chronology | move behind main survey | Useful case evidence, not the literature survey's spine |

## Execution program

- [x] Bind the rejected baseline and classify the transformation.
- [x] Diagnose the reader failure against the governing policy.
- [x] Freeze the reader coalition, claim spine, rival, example, request, and
  cold-reader questions.
- [x] Write a two-to-four-page narrative prototype.
- [x] Recompose the complete proposal from the qualified story.
- [x] Restrict the audit runner to backstage outputs and add regression tests.
- [x] Rebuild the survey opening and move document history out of the main route.
- [x] Render the single manuscript; inspect page images, text extraction,
  references, density, and internal-register leakage.
- [x] Complete six author reads and a scaffolding-removal read, repairing the
  canonical proposal after each material finding.
- [ ] Obtain the project owner's unaided decision on the exact rendered
  candidate.

## Promotion and stop rules

The strongest state available without a human read is
`author_repaired_draft`. The project owner alone can mark the manuscript
`human_accepted`.

Stop and recompose rather than expand when any of the following occurs:

- a cold reader cannot state the problem, product, rival, or request;
- the first two pages contain audit administration before a product journey;
- a requirement list substitutes for explaining how the product works;
- evidence collection does not change a claim, design choice, or limitation;
- a style or build diagnostic is treated as evidence of readability; or
- the manuscript becomes longer because backstage records have leaked into it.

Evidence-specific limitations remain separate. The current audit does not
support a claim that humanvoice improves expert writing, and that claim is not
needed to authorize a bounded feasibility build.
