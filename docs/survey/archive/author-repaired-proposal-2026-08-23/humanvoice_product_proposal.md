---
title: "Humanvoice"
subtitle: "A reader-first revision system for technical writing"
author: "Product proposal"
date: "23 August 2026"
lang: en
fontsize: 11pt
geometry: margin=1.05in
colorlinks: true
linkcolor: blue
urlcolor: blue
link-citations: true
bibliography: humanvoice_survey.bib
abstract: |
  Technical authors now have abundant help generating and polishing prose, but
  they still lack a reliable way to move a complex document from locally fluent
  to understood and accepted. Humanvoice is a revision system for that gap. It
  locates diagnosable problems without rewriting automatically, protects
  equations, numbers, citations, and claims during revision, and ends with a
  decision from a named human reader. This proposal requests a bounded
  twelve-week MVP and one-document feasibility run. The build will establish
  whether the workflow is usable and measurable; it will not be presented as
  evidence that the product improves expert writing. A later comparative study
  must earn that claim.
---

# Decision in brief

Build humanvoice as a reader-first revision system for technical documents.
The product should help an author find where a draft loses its reader, revise
without silently changing its substance, and learn whether the next version
actually reduced the work required for acceptance.

The immediate decision is deliberately bounded. Authorize a twelve-week MVP,
an evaluation corpus, and one live-document feasibility run. At the end of
that work, decide whether to fund a comparative study against the tools and
review process already in use. Do not authorize general deployment, and do not
claim that humanvoice improves writing before that comparison is complete.

The MVP can be built by one product engineer and one research and evaluation
lead, with a part-time domain reviewer. The primary outcome for the eventual
study is the number of human-feedback rounds required to reach reader
acceptance, provided that reader time and meaning-preservation failures do not
increase. If the product cannot improve that outcome, it has not earned a
place in the writing process.

# The problem worth solving

A technical document can be correct, compile without warnings, and survive
several agent reviews while failing in its first few minutes with a human
reader. One funding proposal in this workspace did exactly that. Its reader
could not state the purpose, did not know why internal file names appeared in
the argument, and could not tell what action was being requested. The document
had not failed because of a typo. It had transferred the work of constructing
the argument from the author to a scarce expert reader.[^case-record]

[^case-record]: The full case record, including the reader's response and the
    later repair history, is preserved in
    [the survey's internal evidence appendix](part1_failures.tex). It is used
    here as a motivating case, not as external efficacy evidence.

That transfer has an economic cost. A rejected draft begins another cycle of
diagnosis, revision, and rereading. Senior readers spend time rediscovering the
same kinds of problems: private project language in public exposition,
repetitive paragraph structure, qualifications that never explain a
mechanism, unsupported specificity, and missing links between an equation and
the decision it is supposed to inform. The cost is not simply author time.
Every cycle consumes the attention of the person whose judgment the document
was written to support.

Current tools make only parts of this cycle cheaper. Grammar checkers and
prose linters find local surface defects. General language models can draft,
rewrite, and comment. Citation services can confirm that a DOI exists. Version
control can show that text changed. None of these tells us that the intended
reader can now reconstruct the argument, and none protects every substantive
object while a large passage is recomposed.

Humanvoice is aimed at this missing middle: the journey from a plausible draft
to a document a named reader understands and accepts.

# Why the obvious alternative stops short

The strongest rival is not another specialist writing product. It is the
combination most authors can assemble today: an ordinary prose linter, a
general LLM editor, version control, and manual review. Humanvoice should reuse
those components where they work and compete on the connection between them.

| Revision job | Ordinary toolchain | Humanvoice |
|---|---|---|
| Find local style and grammar problems | Strong | Reuses replaceable linters and adds project-register diagnostics |
| Explain which issue matters most | Inconsistent, often presented as fluent commentary | Ranks located findings and leaves the editorial decision visible |
| Protect equations, numbers, citations, and claims | Depends on manual comparison | Treats them as protected content and requires an explanation for substantive change |
| Determine whether the revision helped | Surface scores or an uncalibrated model judgment | Compares reader reconstruction, review burden, and acceptance |
| Learn across documents | Prompt history and scattered review notes | Retains bounded, privacy-aware revision and reader outcomes |

The distinction matters because the evidence for AI assistance is conditional.
In a preregistered experiment, generative assistance reduced completion time
and improved evaluated output on occupation-specific writing tasks
[@noy2023experimental]. Field evidence also reports time or productivity gains
in workplace settings [@dillon2025shifting; @brynjolfsson2025work]. These
studies establish that assistance can change work. They do not estimate the
value of this workflow for expert economics writing, and the average effects
hide differences by task and worker experience. Assistance can also reduce
correctness when a task lies outside the model's capability frontier
[@dellacqua2026jagged].

The appropriate product claim is therefore modest and testable: humanvoice may
reduce wasted revision and rereading by connecting diagnosis, protected
editing, and reader evidence. The feasibility build is designed to learn
whether that mechanism can work. It is not a demonstration that it already
does.

# The product in use

Humanvoice sits beside the author's existing editor and repository. It does not
replace either. A document moves through four observable steps.

First, the author opens a LaTeX or Markdown draft and chooses the intended
reader and decision. Humanvoice parses the document into ordinary prose and
protected content. Equations, numbers, labels, citations, quotations, and
declared claims retain their source locations.

Second, the system presents a short, ranked set of findings. Some are fully
deterministic: a private path appears in the manuscript, five consecutive
sections open the same way, a citation has mismatched metadata, or a number
changed between versions. Others are editorial questions attached to a span:
does this qualification prevent a real misunderstanding, or does it merely
protect the author? Is the paragraph missing the mechanism that makes its
conclusion follow? Findings remain findings. Humanvoice does not silently edit
the source.

Third, the author or an explicitly chosen editor revises the draft. A protected
comparison explains what changed and calls attention to any altered equation,
number, citation, quotation, or claim. The author may make a substantive
change, but it cannot disappear inside a smoother sentence.

Finally, a low-context reviewer receives the rendered document without the
repository history that made its private language seem familiar. The reviewer
answers questions tied to the document's purpose: What problem is being
solved? What is proposed? Why is the obvious alternative insufficient? What
evidence matters? What decision is requested? A named human remains the final
authority. A missing answer sends the document back for substantive revision,
not another round of synonym replacement.

## Revision flow

```text
source -> format-aware parse -> located findings -> author revises
                 |                                  |
                 +-> protected content -------------+
                                                    |
                                           protected comparison
                                                    |
                                   low-context read -> human decision
```

This design keeps two records for good reason. The reader sees only the
document. The project retains the minimum provenance needed to reproduce a
diagnostic, understand a revision, and evaluate the workflow. Internal IDs,
search administration, and review machinery never become manuscript prose.

# What the evidence changes

The literature does not point toward an autonomous rewriting system. It points
toward a bounded editor with direct evaluation of the resulting revision.

## Feedback must be judged by the next draft

Writing feedback can sound specific while missing the most important problem.
On a test set of 1,300 deliberately corrupted stories, models often produced
accurate local comments but failed to identify the central defect or choose
appropriately between criticism and praise [@rashkin2025story]. Work on an
economic essay task similarly evaluates feedback through the revisions it
induces rather than through the fluency of the comment itself
[@nair2024closing]. Humanvoice therefore links each finding to a source span,
records whether the writer acted on it, and evaluates what changed in the next
version.

Two recent systematic reviews reinforce the boundary. Across their respective
evidence bases, benefits are more consistent for grammar, process, coherence,
and surface accuracy than for argumentation, discourse organization, or
creativity [@meng2026systematic; @abudalfa2026awe]. Humanvoice can automate
some measurements at the surface. It must measure higher-order understanding
with the intended readers.

## Model judgments need calibration

Model judges are useful screening instruments, but their preferences change
with answer order, length, and model family [@zheng2023judging;
@panickssery2024llm; @dubois2024length]. They also tend to be more generous
than expert writers when judging creative prose [@chakrabarty2024art]. Any
model-assisted review in humanvoice will therefore address one construct at a
time, randomize pair order, control for length, use a different model family
from the editor, and report calibration against human labels. It may direct
attention. It may not accept a document.

## Assistance can change trust and voice

Disclosure of AI assistance can affect reader ratings and increase disagreement
among readers [@li2024disclosure]. Assistance can also increase individual
performance while reducing the diversity of a collection
[@doshi2024generative; @padmakumar2024writing]. These are product outcomes,
not matters of cosmetic style. Humanvoice will retain the disclosure condition
used in evaluation and monitor convergence across a sufficiently large corpus.
It will never infer authorship from an individual document or optimize text to
evade a detector.

## Citation identity is not claim support

Generated scholarly references can be nonexistent or mismatched
[@mugaanyi2024citation]. A metadata service can establish that a paper and DOI
match. Only inspection of the paper can establish that it supports the sentence
in which it is cited. Humanvoice separates those jobs: automatic identity
resolution followed by a human source-to-claim check for important claims.

These findings narrow the design and the promise. They justify local
measurement, protected revision, explicit uncertainty, and direct reader
outcomes. They do not justify a single quality score, an automatic rewrite, an
authorship detector, or an efficacy claim before the pilot.

# What we will build

The MVP has four product capabilities and one evaluation asset.

The document core reads LaTeX and Markdown while preserving source locations
and protected regions. Pandoc and pylatexenc are the first parser candidates
because they expose structured documents through mature, documented interfaces
[@pandoc2026filters; @pylatexenc2026]. They will be tested on unknown macros,
nested environments, comments, mathematics, citations, malformed input, and
round-trip preservation. A parser is selected only after those fixtures pass.

The diagnostic layer locates private project register, structural repetition,
defensive prose candidates, citation identity problems, and build or rendering
defects. Vale and existing local rules are plausible hosts for deterministic
prose checks [@vale2026docs]. Every result carries its source span and a clear
question or measurement. No diagnostic command mutates its input.

The protected comparison reports changed equations, numbers, labels,
citations, quotations, and declared claims. latexdiff may provide a useful
rendered comparison, but the invariant check remains structural
[@latexdiff2026]. An unexplained protected change stops that revision from
being presented to a reader.

The review workspace shows a clean rendered draft, asks a short document-
specific rubric, and records the minimum decision evidence. It does not expose
the author's plans or audit records. Model-generated suggestions are optional,
identified, and reversible.

The evaluation corpus begins with existing rejected and repaired documents for
which reader verdicts or revision histories are already available. It will add
adjudicated labels for defect location, issue importance, protected changes,
and acceptance. Tuning and held-out documents will be separated before package
or model results are reported.

The detailed command contracts and sixteen implementation requirements remain
available in the [requirements trace](humanvoice_product_requirements.csv).
They are engineering inputs, not the public explanation of the product.

# How we will know whether it works

The evaluation has two stages because feasibility and efficacy answer different
questions.

The first live document tests whether the pieces work together. Can the parser
protect the document? Do findings point to the right source spans? Can an
author understand and dismiss a false positive? Does the comparison expose
meaning changes? Can a reader complete the rubric without seeing private
project machinery? Does the workflow respect privacy and disclosure choices?
One document can reveal integration failures and unacceptable burden. It cannot
estimate an effect.

If feasibility passes, the project will preregister a paired or stepped
comparison against the current workflow: existing linters, ordinary LLM
editing where the author already uses it, version control, and manual review.
Documents will be selected before outcomes are known. Reader blinding will be
used where practical. The sample size will be chosen by simulating power or
precision from the observed distribution of baseline revision rounds and
reader clustering, not by choosing a convenient number of documents.

The primary estimand is

$$
\Delta r = E[r_{\text{humanvoice}} - r_{\text{current}}],
$$

where $r$ is the number of human-feedback rounds to acceptance. Deployment
requires evidence that $\Delta r < 0$ without an increase in meaning-
preservation failures or total reader time. Reader reconstruction accuracy,
substantive revision rate, false-positive burden, editing time, suggestion
acceptance, and cross-document convergence are explanatory outcomes. None may
replace the primary endpoint.

Results will be reported separately by writer experience, document genre, and
reader role. This is not optional subgroup decoration. Field evidence shows
that average assistance effects can conceal smaller gains or harm among the
most experienced workers [@brynjolfsson2025work].

The project stops or changes direction when any of the following occurs:

- unexplained changes to protected content exceed the prespecified tolerance;
- diagnostic false positives consume more review time than they save;
- privacy or disclosure requirements cannot be met;
- a feasibility user cannot understand or control the workflow; or
- reader acceptance does not improve, or becomes slower, after two comparative
  pilot cycles.

# Delivery and investment

The twelve-week program ends with a working feasibility system, not a claim of
market readiness.

| Weeks | Work | Reader-visible result |
|---:|---|---|
| 1--2 | Freeze the baseline corpus, reader rubric, protected-content model, and parser fixtures | One representative document parses and renders with protected spans intact |
| 2--5 | Implement located diagnostics, citation identity checks, and protected comparison | An author can inspect findings and revise without hidden source mutation |
| 3--7 | Label tuning and held-out documents; benchmark parser and diagnostic candidates | Package decisions are supported by observed behavior rather than popularity |
| 6--9 | Integrate the author and reader workflow with local-first data handling | One document can move from source through revision to a recorded reader response |
| 9--12 | Run the live feasibility document, measure burden and failures, and price the next study | Proceed, revise, or stop recommendation with a preregisterable efficacy design |

The planning assumption is one product engineer, one research and evaluation
lead, and a part-time economics or scholarly-writing reviewer. Twelve weeks
covers the MVP and feasibility case. The efficacy study's duration depends on
the required precision and the arrival rate of suitable live documents.

The investment case should be calculated from project data. Let $r_0$ and
$r_1$ be revision rounds under the current and proposed workflows, $t_0$ and
$t_1$ the expert-reader hours per round, $c_r$ the loaded cost of that time,
$N$ the annual number of relevant documents, and $C$ the annualized build and
maintenance cost. The measurable reader-time component of annual value is

$$
V = N(r_0t_0-r_1t_1)c_r-C.
$$

Quality, author time, and avoided meaning failures may add value, but they
should enter the decision only when the pilot measures them. No published
study supplies the project-specific inputs to this equation.

# Risks and limits

The most serious product risk is meaning drift. Smoother prose is a loss if it
changes a model, number, source, or conclusion. Protected comparison and human
source checks are therefore part of the core, not later compliance features.

A second risk is alert fatigue. A diagnostic that is technically correct but
rarely useful can make the workflow slower and teach authors to ignore it. The
held-out benchmark will report precision by category and the time required to
review findings. Low-value rules will be removed rather than defended by their
coverage.

A third risk is convergence on a house style. Humanvoice is not meant to make
every economist sound alike. It reports patterns and asks questions; it does
not automatically normalize wording. Aggregate monitoring will look for loss
of lexical and structural diversity, while individual documents will never
receive authorship labels.

Privacy and disclosure create a fourth boundary. Protected manuscripts remain
local by default. Any remote model use must identify the provider, purpose,
retention terms, and approved content. The reader study must use the disclosure
condition intended for actual use because disclosure itself can affect reader
response.

Finally, the supporting evidence is not yet a completed systematic review.
The current audit has broad public discovery and verified bibliographic
identities, but independent screening, specialist database coverage,
full-text verification, critical appraisal, held-out package benchmarks, and
external review remain incomplete. The detailed status is reported in the
[evidence audit](humanvoice_product_proposal_audit.md). This limitation blocks
strong literature and efficacy claims. It does not prevent a reversible build
whose purpose is to measure feasibility.

# Decision requested

Authorize the twelve-week MVP and one live-document feasibility run under the
resource assumptions and stop rules above. The authorized deliverables are:

1. a local-first revision system for LaTeX and Markdown;
2. located, non-mutating diagnostics and protected comparison;
3. a small adjudicated corpus with frozen tuning and held-out partitions;
4. one end-to-end feasibility result, including burden and failure evidence;
5. a costed, power-justified design for the comparative study; and
6. a recommendation to proceed, revise, or stop.

This decision does not authorize autonomous rewriting, authorship detection,
general deployment, or a claim that humanvoice improves expert writing. It
authorizes the smallest build that can determine whether those further
investments are warranted.

# Technical appendix

## Product boundary

The MVP accepts local LaTeX and Markdown sources and emits findings, protected
comparisons, rendered review material, and bounded evaluation events. It does
not generate claims or citations, classify authorship, evade detectors, upload
manuscripts without approval, or accept a document on behalf of its reader.

The stable CLI concepts from the founding survey remain useful implementation
interfaces:

| Command | Contract |
|---|---|
| `hv leak` | Locate private project register and disclosure problems without editing |
| `hv rhythm` | Report sentence, paragraph, and section-shape measurements against genre configuration |
| `hv defensive` | Return contextualized candidate passages and editorial questions |
| `hv diff` | Explain changes to protected content between document versions |
| `hv cite` | Resolve bibliographic identity and prepare a separate source-to-claim review queue |
| `hv gate` | Build and render the document, report reference and layout failures, and expose pages for inspection |
| `hv drift` | Measure population-level convergence on sufficiently large corpora; refuse individual attribution |

The names are less important than the shared contracts: immutable input,
stable source locations, structured output, no silent source mutation, and no
diagnostic promotion of a document.

## Core records

Implementation needs six small records: a document version with protected
spans; a located diagnostic finding; an explained change; a citation identity
and claim anchor; a reader response tied to one rendered version; and a
privacy-bounded interaction event. Their complete fields and evidence links
are maintained in the machine-readable requirements rather than repeated in
the main proposal.

## Supporting scholarship and audit

The full literature and software treatment is in
[the supporting survey](humanvoice_survey.pdf). Search histories, screening
queues, evidence extraction, package inventory, manifests, and unresolved
review work remain under [`docs/survey/audit/latest/`](audit/latest/). Those
records protect the product's claims and implementation choices. They are not
the product proposal's narrative.
