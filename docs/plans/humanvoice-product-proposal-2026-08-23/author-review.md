# Author review of the rebuilt Humanvoice proposal

Date: 2026-08-23

> Historical note: this review covers the standalone candidate that was later
> archived. It is not acceptance evidence for the current unified manuscript;
> the current candidate is `docs/survey/humanvoice_survey.pdf` and requires a
> new unaided reader decision.

Promotion state: `author_repaired_draft`

Human acceptance: pending the project owner's unaided read.

## Candidate reviewed

| Artifact | SHA-256 | Scale |
|---|---|---:|
| `docs/survey/humanvoice_product_proposal.md` | `885f6bc0bfe36ef04b05d9ebab681ea0ee28d4cd1a6de7ea7e157727b7dc6066` | 3,280 words |
| `docs/survey/humanvoice_product_proposal.pdf` | `01ac69327290600a93833a41d8f988e3d68cc391cc641ac137e2d9aff2b815d3` | 11 pages |
| `docs/survey/humanvoice_survey.tex` | `67bcf0d11b8634d5ac9f5d37a77ef4d290f185dac791c09064642f30626d3431` | supporting source |
| `docs/survey/humanvoice_survey.pdf` | `775a683fecc7393a333de72d026d0a5e7dcfe5a0e75017267a12578150deec1b` | 47 pages |

The proposal was read in source and extracted-PDF form. All eleven proposal
pages were inspected as a contact sheet; pages 1--4 and the product-flow page
were inspected at readable resolution. The survey's opening and the boundary
between its main conclusion and internal-case appendix were also inspected.

## Read 1: decision, story, and stakes

The proposal opens with a bounded decision, then makes the cost concrete
through a funding proposal that consumed expert attention without conveying
its purpose or requested action. The principal rival is explicit: a prose
linter, general LLM editor, version control, and manual review. The product's
claim is narrower than generic writing improvement and the final request
matches the opening request.

Repair made: the audit-generated opening, evidence counts, and release status
were removed. The concrete case, feedback-cycle cost, rival, and twelve-week
request now occupy the first two pages.

## Read 2: product teaching and cognitive order

A reader encounters the user journey before architecture or command names.
The four steps distinguish deterministic findings, editorial questions,
author-controlled revision, protected comparison, and the final reader
decision. The compact dependency map agrees with the prose.

Repair made: the first diagram split across pages, and a later wrapper printed
Markdown fence markers. The final map is intact on page 3 and text extraction
contains neither a split branch nor literal fence markers.

## Read 3: scholarship and rival explanations

Twenty cited literature and software sources change a claim, product boundary,
evaluation choice, or component shortlist. The proposal distinguishes
controlled writing experiments, workplace evidence, systematic reviews,
feedback studies, model-judge studies, disclosure and convergence evidence,
citation reliability, and primary software documentation. It does not use
bibliography size as a claim of completeness.

Repair made: the previously uncited Noy and Zhang productivity result received
its Science citation. The supporting survey now leads with external literature
and software; the internal chronology and detailed requirement trace are
appendices. The remaining evidence-audit work is stated once under risks.

Residual limit: independent screening, specialist database coverage, full-text
verification and appraisal, held-out package benchmarks, and external review
remain incomplete. Those limits block strong scholarship and efficacy claims,
not a reversible feasibility build.

## Read 4: measurement and identification

The proposal names the current toolchain as comparator, separates feasibility
from efficacy, defines feedback rounds to acceptance as the primary endpoint,
states the estimand, protects reader time and meaning, requires reader
clustering and observed baseline variation in sample-size work, and names
heterogeneity by writer experience, genre, and reader role.

No arbitrary pilot sample size was inserted. A single live document is an
integration test only; the comparative study must be sized from baseline data.

## Read 5: engineering feasibility and investment

The product boundary, four MVP capabilities, evaluation asset, twelve-week
milestones, team shape, protected objects, stable CLI concepts, and six core
records give an implementer a coherent starting point. Package selection is
conditional on parser fixtures and held-out behavior rather than popularity.

Residual decision input: the proposal gives person roles and duration, not a
dollar budget, because loaded rates, document volume, and current reader time
are not in the repository. The value equation identifies those inputs. They
must be priced by the owner before authorization rather than invented by the
author.

## Read 6: voice, rhythm, and payoff

The main proposal uses continuous explanation, one rival table, one milestone
table, one compact journey map, and five stop-condition bullets. It contains no
bold mini-heading list and does not lead with internal status vocabulary. The
final section returns to the exact authorization boundary established on page
1. These observations are author judgments; the structural diagnostic is only
a regression check and is not evidence of readability.

## Read 7: scaffolding removal and artifact ownership

Search counts, API results, gate names, screening ledgers, manifests, protocol
IDs, generation timestamps, and document history are absent from the public
opening. The audit runner now emits an implementation dossier and publishes it
under `humanvoice_implementation_dossier.*`. A regression test protects the
authored proposal paths. Publishing the preserved audit left the proposal
Markdown, TeX, PDF, and status hashes unchanged.

## Author reconstruction against the cold-reader questions

1. The problem is repeated expert-reader work caused by drafts that are
   locally polished but not understood or accepted.
2. A document is parsed, diagnosed, revised by an author, compared for
   protected changes, and read by a low-context human.
3. The ordinary toolchain does not connect located diagnosis, protected
   meaning, and a measured reader outcome.
4. Existing evidence supports bounded assistance and direct evaluation, but
   does not establish efficacy for expert economics writing.
5. The first twelve weeks build the document core, diagnostics, protected
   comparison, review workflow, and evaluation corpus, then run one live case.
6. The project stops for meaning failures, excessive false-positive burden,
   unmet privacy requirements, unusable control, or no improvement after two
   comparative pilot cycles.
7. The requested decision is authorization for the MVP and one feasibility
   document, not deployment or an efficacy claim.

This reconstruction was performed by the author and therefore cannot satisfy
the cold-reader requirement. The exact PDF above must now be read without an
author briefing by the project owner or another independent reader.
