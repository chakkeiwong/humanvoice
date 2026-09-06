# Suggestions from the hpo-survey engagement

Date: 2026-08-25. Author: the agent that ran the hyperparameter-survey
revision arc in `~/workspace/hponas/hpo-survey`. Audience: the agent
building humanvoice. Provenance for every number below:
`hponas/hpo-survey/literature-audit.md` (dated entries for 2026-08-24/25)
and `hponas/hpo-survey/tools/concept_density.py`.

This memo reports what one live engagement taught us that the current
proposal (`part5_proposal.tex`, read 2026-08-25) does not yet exploit,
and what I would change or add in the first build. The engagement is
also an asset: it produced a three-round, fully adjudicated revision
record with located causes and located fixes, which is exactly the kind
of calibration and held-out material the proposal says it needs.

## The case in brief

One 90-page LaTeX monograph (a methods survey for a tuning product).
Three rounds of manager feedback, each time some version of "this is
too dense," each time after the writing agent had judged the document
good. Each round turned out to have a different, deeper cause, and each
cause became measurable and repairable once named:

1. Round one: paragraph packing. Six mechanisms and five citations in
   one 210-word paragraph. Fix: unfold to one idea per paragraph.
   Document moved from 128 mean words per prose paragraph to 90.
2. Round two: concept density. The manager supplied two exemplar
   documents ("write like these"). Measured with one detector across
   all three corpora: the survey introduced one new concept per 70
   words; the exemplars ran 83 and 253. The 253 document (800 pages
   for one project) was the standard the manager actually meant.
3. Round three: dependency ordering. "Don't use a concept before it is
   explained." A first-use audit found roughly 25 real violations,
   including the running example's own algorithm (PPO), used from page
   one and never introduced anywhere, and two acquisition-function
   names used one section before acquisitions were taught.

The reader's word for all three rounds was the same: dense. The causes
were at three different depths. That is the single most important fact
in this memo.

## What we learned

### 1. The complaint names a symptom; the cause sits one level down

"Too dense" meant packing, then pacing, then ordering. A product whose
diagnostics stop at surface style (repeated openings, stock phrases,
dashes) will pass documents that still fail the reader for structural
reasons. The diagnostic ladder should go: surface patterns, paragraph
mechanics, conceptual pacing, dependency order. The current bounded
rule set in the vertical slice covers the first rung well and the
fourth rung partially (undefined project labels are an ordering rule).
The middle rungs are missing and are where two of our three rounds
lived.

### 2. Calibrate against exemplars; do not legislate absolutes

Nothing in our arc worked until the manager pointed at two documents
and said "like these." One detector run over target and exemplars gave
numbers with meaning: 70 versus 83 versus 253 words per concept; 12.9
versus 5.9 versus 0.8 percent of paragraphs introducing three or more
new concepts. The detector is only about 80 percent precise, but the
noise is symmetric across documents, so the ratios are trustworthy
even where the absolute counts are not.

Implication for the build: the reading brief should accept exemplar
documents, and pacing thresholds should be derived from them rather
than hardcoded. Report findings as position relative to the exemplar
band, never as a bare score. This also keeps the product honest about
genre: a survey will never pace like a single-project monograph, and
the exemplar band encodes that without a rule author having to.

### 3. Conceptual pacing is measurable on three axes

The working meter (`concept_density.py`, ~230 lines, stdlib only)
measures: introduction rate (words per new concept, where concepts are
detected as acronyms, mid-sentence proper terms, emphasized definition
phrases, recurring technical bigrams, and citation keys),
consolidation (occurrences per concept, singleton share), and burst or
live load (new concepts per paragraph, and introductions within a
trailing 1,500-word window). The third axis is the operational form of
the working-memory budget in the existing teaching contract.

Two findings worth carrying into the product. Pacing is mostly
inventory: the chapters that taught one thing hit exemplar pacing
naturally, and the chapters that surveyed many things did not, so a
pacing finding should sometimes ask "should this unit take on fewer
named things?" rather than "write more." And burst is the actionable
form: a ranked list of paragraphs introducing three or more new
concepts, with file and line, was the worklist that actually drove
repairs.

### 4. Use-before-explain is a checkable contract

First occurrence of each concept, plus a check for an introduction
signal in the surrounding sentence (an expansion, an appositive gloss,
a "taught in Chapter X" pointer), plus a whitelist of vocabulary the
reader already owns. The audit found real violations that a careful
author had missed through two full revision passes. It needs two
inputs the proposal already plans: the brief's "vocabulary the reader
can reasonably be expected to know" is the whitelist, and it needs one
input the proposal does not yet have: declared exemption zones.
Preview and map sections, decision boxes, and reference tables
legitimately name things before teaching them; ours worked once the
introduction said so explicitly ("the names that follow are only
names for now"). Let authors mark such zones rather than tuning the
rule to tolerate them everywhere.

The repair pattern that satisfied the manager is worth encoding in the
finding text itself: generic term first, name after ("a
population-based method, BG-PBT, examined in Chapter 6"), or an
explicit taught-later pointer.

### 5. The asymmetry prior: slow and skippable beats dense

The manager's stated decision rule: "when it is slow, the reader can
skip; filling a gap is a lot harder." This is a default for repair
direction. When a pacing finding could be answered by cutting or by
expanding, the product should present expansion plus navigation
(headings, marked asides) as the first option, and should also check
that slow stretches are skippable: a long unit with no internal
headings fails the skippability half of the rule.

### 6. Slowness has a mechanism, and it is not padding

The 253-words-per-concept exemplar earns its pace through redundancy
with variation: a concrete case before any abstraction; the same idea
shown in three to five representations (instance, prose, figure,
formal statement, read-back); a read-back paragraph after every
figure; one concept per section; periodic reader tasks. These are
nameable operations. A moves catalogue with one before/after pair per
move, mined from the exemplar corpus, is the cheapest way to make an
inspection finding actionable without the system rewriting anything.
It respects the questions-before-rewrites commitment: the finding asks
the question and cites the move; the author performs it.

Moves we used repeatedly, as candidate catalogue entries:
concrete-case-first; inventory-then-tour (list the fifteen knobs, then
read them in groups); unfold-the-lineage (one method per paragraph,
each with its price); read-back-after-display; generic-first-name-
after; decode-the-acronym (the name read as a recipe); worked-micro-
case (two posterior outcomes, EHVI = 0.25); map-disclaimer (this
section is a map, not an argument).

### 7. Style passes smuggle claims through additions, not edits

The one near-miss in three rounds: while glossing a library name for
ordering reasons, I wrote "the most widely adopted tuning library."
The project's audit only supported "where sampler development is most
active." The protected-object design catches edits to existing claims;
this hazard is new assertions arriving inside style repairs. Suggest
extending `hv compare` with an added-assertion check on prose diffs:
added sentences containing numbers, superlatives, or comparatives
without a citation or a pointer to an existing protected claim become
located questions. In our arc, every such addition was supposed to be
either already-audited fact or elementary arithmetic, and the ledger
entry saying so was what made the pass safe.

### 8. Self-review cannot certify, but self-measurement can locate

The writing agent judged the document readable before every round and
was wrong every time. The meters never declared the document good;
they said where to look, and the human said whether it was fixed. This
is the proposal's own division of decisions, confirmed in the field.
For the agent-facing side it implies a loop contract: a revision pass
ends with build clean, meters re-run, ordering audit clean, ledger
entry written, status human-review-pending. Never a self-issued done.

### 9. Directives must be captured durably or they get relitigated

The manager's standing rules (err slow; never use before explain)
became enforceable only once written into the project ledger and the
agent's persistent memory, with the tools to check them. The reading
brief should therefore be cumulative and versioned: each reader
session and each author directive updates it, and the next inspection
runs against the updated brief. A brief that is filled in once at
capture and never learns will re-ask settled questions.

### 10. Bounded units, measured between

Every effective round worked the same way: fix one chapter, rebuild,
re-measure, then propagate. The one time the earlier history skipped
the checkpoint (a whole-document apparatus round), it produced a
heavier document and a third feedback round. The vertical slice
already thinks this way at document scale; keep it at unit scale too,
and let the finding queue be orderable by unit so an author can clear
one chapter and re-inspect it alone.

## What we can hand you today

1. `hponas/hpo-survey/tools/concept_density.py`: working pacing meter
   with exemplar calibration and burst lint. Known limits: ~80 percent
   detector precision (spot-checked, noise symmetric), LaTeX-oriented
   cleanup, no sentence-level dependency parse. Treat as a prototype
   to absorb, not a dependency.
2. Calibration numbers for three real corpora (survey, CIP monograph,
   CardNPV two-volume): words per concept 70 / 83 / 253; singleton
   share 40 / 35 / 19 percent; burst-paragraph share 12.9 / 5.9 / 0.8
   percent; live load mean 20.5 / 17.6 / 6.1 per 1,500-word window.
3. A fully adjudicated live case: three feedback rounds, each with the
   manager's verbatim complaint, the diagnosed cause, the located
   fixes (file and line, in git history), and dated ledger entries.
   This is calibration or held-out material with real author
   dispositions, the thing the evaluation plan says is scarce. The
   ordering round alone yields a seeded-defect list (25 real
   violations with locations) plus 80 adjudicated false alarms, which
   is a ready-made precision fixture for any ordering rule.
4. The exemplar-technique observations from CardNPV's own chapters
   (the moves list above), citable to specific sections of that
   document.

## Cautions

- Do not let the meter become the judge. Ratios against exemplars,
  with the precision caveat attached, presented as questions. The
  proposal's burden rule (retain a rule family only when it saves
  median minutes) should govern the pacing and ordering families too;
  ours earned their keep in this one engagement, but that is one
  engagement.
- Concept detection will never be clean. Possessives, capitalized
  ordinary words, and hyphenation variants all leak; we folded the
  worst mechanically and lived with the rest because comparisons
  survive symmetric noise. Any UI that shows per-concept lists must
  make dismissing noise one keystroke.
- Ordering rules need genre exemptions declared, not inferred.
- The three-axis meter measures pacing, not comprehension. In our
  case the manager's quoted paragraph, the place they stopped
  reading, was worth more than any metric. The reader task should
  capture stopping points and quoted spans, not only reconstruction
  answers; the quoted span is what turned "too dense" from a mood
  into a worklist.
