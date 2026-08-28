# Humanvoice monograph-scale proposal expansion

Date: 2026-08-24

## Objective

Replace the compressed 38-page reader route with one substantial product
proposal that can be read as a formal research-and-implementation volume.
The target is not page count by itself. The target is a document in which a
former professor or executive can follow the product question from observed
failure through mechanism, evidence, design, evaluation, economics, and a
funded build without opening a second narrative. The second expansion
pass adds the missing monograph-scale connective tissue in that same route.

## Editorial standard

The canonical proposal should read like serious explanatory nonfiction for
educated executives: the clarity and concrete stakes of an Economist
technology essay, the curiosity and examples of a good popular-science book,
and the cumulative teaching discipline of a well-written first-year
university textbook. These are reference points for cadence and exposition,
not templates to imitate. The main route should introduce a problem or case
before its machinery, name people and decisions directly, explain technical
terms when they become necessary, and let evidence create the transition.
Headings should name subjects or questions. Internal ledgers, gates, packets,
and status language belong in the implementation record or appendices unless
they name a real software or control object.

The voice pass also has explicit negative rules. Do not open a chapter by
describing the chapter, repeat a roadmap after the reader already has the
question, use a status noun as a metaphor for an ordinary idea, lead with a
defensive non-claim when a positive mechanism can be stated first, or use an
unsupported superlative to make a local result sound general. A diagnostic may
flag these tendencies, but a human reader decides whether a sentence belongs.

## What the exemplars establish

The cited CIP monograph and CardNPV volumes are useful scale and content
references, not prose authorities. Their cumulative teaching route illustrates
several structural practices:

- a short orientation tells the reader how the argument is nested;
- a concrete finite case fixes the objects before abstraction;
- each chapter derives one consequence, works a numerical or structural
  example, names the failure mode, and states what the next chapter needs;
- the literature and implementation material are explanatory chapters, not
  inventories detached from the central question;
- appendices preserve derivations, notation, source maps, and reproducibility
  detail without replacing the main argument.

Their scale is also informative. The inspected CardNPV Volume I is about
95,700 extracted words and 275 pages; Volume II is about 176,000 words and
506 pages. Humanvoice is a product proposal rather than a two-volume technical
monograph, so the first expanded release should be materially smaller while
still carrying roughly 50,000--80,000 words and approximately 120--220 pages
of actual explanation, examples, tables, and appendices. The exact page count
is subordinate to coverage and readability.

## Preserved material

The expansion must not discard the existing source merely because the current
route is shorter.

| Source | Approx. words | Treatment |
|---|---:|---|
| `part0_opening.tex` | 2,873 | Expand into the reader orientation and investment case. |
| `part1_failures.tex` | 4,984 | Main internal-case chapter, with substantive examples retained. |
| `part2_existing_tools.tex` | 2,441 | Main chapter on project assets and their limits. |
| `part3_literature.tex` | 4,357 | Main literature chapter; reconcile with newer evidence synthesis. |
| `part4_oss.tex` | 4,973 | Main software-field chapter; retain tool-by-tool reasoning. |
| `part5_proposal.tex` | 2,641 | Detailed product/work-package specification. |
| current canonical route | ~14,500 extracted | Retain the worked case, protected comparison, estimand, economics, design, and funding material where it adds clarity. |
| implementation/evidence dossier | ~6,400 | Absorb substantive requirements, reading briefs, evaluation, and limits; keep audit administration backstage. |

## Current chapter spine

The source route now uses the following reader-facing headings. The names are
intentionally plain; the implementation records and appendices carry the
formal schemas and acceptance vocabulary.

### Part I. Why technical documents fail

1. One document, from draft to decision.
2. Why good documents still fail.
3. The reader's problem.
4. What the first investment would buy.
5. The cases that made the problem visible.
6. What the existing project already contributes.

### Part II. What research and software can tell us

7. What the evidence supports.
8. How we reviewed the evidence.
9. The research behind Humanvoice.
10. What we know about AI-assisted writing.
11. Where Humanvoice fits.
12. Open-source tools.
13. The software we can use.

### Part III. The product

14. What the product does in one document.
15. How the product works.
16. Turning evidence into a build.
17. Building and testing the first version.
18. How the review system works.

### Part IV. How we will test it

19. The test and its economics.
20. How the test will work.
21. What twelve weeks would deliver.
22. The next research questions.
23. Who would use it, and why.
24. What comes after the first build.

### Appendices

A. Notation and terms.
B. Detailed requirements and records.
C. Internal case evidence and repair-pair index.
D. Literature claim-to-design matrix and evidence register.
E. Software benchmark protocol and candidate inventory.
F. Reader instruments, consent/disclosure, and scoring forms.
G. Cost model, sensitivity worksheets, and data requirements.
H. Reproducible build, source map, and status boundaries.

The executed route uses a compact chapter numbering rather than forcing the
conceptual 24-step spine into 24 thin chapters. The second expansion pass adds
seven substantive chapters inside the same route: a worked source-to-reader
case, a discipline-level literature synthesis, software dossiers and fixtures,
a concrete architecture, a detailed evaluation design, an operating plan, and
a reference manual. The additional depth is carried by explanation and
worked objects, not by a second public document.

## Depth requirements for every substantive chapter

Each chapter must contain, where the subject permits:

- a question stated before the terminology;
- a definition or formal object with units and ownership;
- at least one worked example, counterexample, or reconstructed case;
- the tempting but invalid inference the example rules out;
- the implication for Humanvoice's product or implementation;
- what is known, what is hypothesized, and what remains open; and
- a transition explaining why the next chapter follows.

Tables may summarize a result, but they cannot substitute for the prose that
derives and interprets it. Requirements and audit records belong after the
reader understands the object they describe.

## Expansion acceptance tests

The expanded route fails review if any of these conditions holds:

1. A reader can reach the product decision without seeing a complete case and
   its mechanism.
2. The old substantive case/literature/tool material is absent or reduced to
   a list of names.
3. The document grows mainly through repeated status, governance, or audit
   prose rather than explanation.
4. A formula appears without definitions, units, a worked interpretation, and
   a statement of what it does not establish.
5. A package recommendation is not tied to a protected-source fixture,
   privacy boundary, maintenance criterion, and held-out outcome.
6. The economic request has no observable inputs, sensitivity, or stop rule.
7. The appendix is the only place where an implementer can discover the
   product's actual behavior.
8. The rendered volume has unresolved references, overfull boxes, isolated
   fragments, or large blank transitions introduced by expansion.

## Release boundary

The result may be called an expanded author-repaired proposal only after the
rendered volume and its source route pass the tests above. It remains pending
independent reader review, project-owner acceptance, and completion of the
release-blocked evidence checks.

## Execution record

The expanded route was built on 2026-08-24. It includes the previously omitted
`part0`--`part5` substantive chapters, `proposal/04_method.tex`,
`proposal/10_research_program.tex`, `proposal/12_adoption_and_scale.tex`, and
`proposal/11_expanded_appendices.tex`, plus the seven second-pass chapters in
the canonical single-document route. The final review pass also adds a
foundational writing-scholarship synthesis and a documented adjacent-product
comparison inside the literature and software chapters. The latest rendered
result is 204 A4 pages and approximately 74,245 extracted words; the
reader-facing route before
the appendices is approximately 51,824 words.

The build completed with the structural diagnostics, BibTeX, and three LaTeX
passes. There are no unresolved references, undefined citations, or overfull
boxes in the final log; the remaining TeX messages are underfull table-cell
warnings. The unit suite checks the expanded exemplar spine and a 50,000-word
reader-route floor, in addition to the substantive case, literature, software,
evidence-method, and adoption chapters. The deterministic PDF hash is recorded
in `docs/survey/humanvoice_document_status.json`.

The result is still not a completed systematic review or an efficacy result.
Independent screening, specialist-domain imports, full-text appraisal,
bibliographic identity checks, held-out package benchmarks, external reader
review, and project-owner acceptance remain release gates.

## Concrete-first voice pass

The final editorial pass applies a concrete-first explanatory register to the
same single route. It uses the Economist technology essay, strong popular
science, and well-written introductory textbooks as high-level reference
qualities rather than as imitation targets.

The working sequence is:

1. Put an actor, event, or failure before the category it motivates.
2. Give the actor a strong verb and name the object of the action.
3. State a real cost or consequence before listing benefits when that cost
   affects the investment decision.
4. Introduce technical nouns after the reader has seen the object they name.
5. Keep formal nouns when they denote an actual data, software, statistical,
   or legal object; do not replace them merely to lower a count.
6. Remove document-management narration from reader-facing prose unless the
   reader needs the navigation.
7. Preserve every source claim, qualification, number, equation, citation,
   and uncertainty while changing the exposition.

The 24 August voice pass rewrote high-impact openings and transitions in the
evidence, method, literature, software, architecture, evaluation,
implementation, adoption, operating, product, and internal-tool chapters. It
also revised selected passages in the opening and failure record. The pass did
not change the product boundary, estimand, cost equations, evidence status, or
release gates. The rendered proposal remains the only public narrative; this
section records the editorial method for reproducibility and does not belong in
that narrative.

The resulting build is 204 A4 pages with approximately 51,824 words in the
reader-facing route. Automated checks confirm source integrity and LaTeX
reproducibility, but they do not certify voice. A cold read by people who did
not author the proposal remains required before calling the register accepted.
