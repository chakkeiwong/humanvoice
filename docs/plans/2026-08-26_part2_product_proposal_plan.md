# How to write Part 2: the concrete product proposal

Date: 2026-08-26. Author: the hpo-survey agent (author of
`docs/survey/suggestions_from_hpo_survey_2026-08-25.md`). Audience: the
agent writing the product half of the volume, and the manager gating it.

Scope read before writing this plan: `humanvoice_survey.tex` assembly
(four \part divisions; product half = "The product" and "Testing the
proposition"), `part5_proposal.tex` (the accepted small-scope sketch),
`humanvoice_product_requirements.json` (24 requirements with acceptance
tests and evidence IDs), the active `proposal/` chapters (edited
2026-08-26), and the two dormant files not in the assembly
(`01_decision.tex`, `19_reference_manual.tex`).

## 1. What Part 2 is, decided before any prose

Part 2 is the half of the volume that must survive two different
readers with one text: the sponsor's technical delegate, who checks
that the twelve-week ask is real, and the build lead, who must be able
to start in week one without reconstructing context. "Concrete" has a
testable meaning here, and it is not "more detail":

> Every commitment has a place where it is designed, a place where it
> is tested, a slot where it is scheduled, and a line where it is
> priced; and every design sentence either points at Part 1 evidence
> or is labeled engineering judgment.

One structural decision follows from requirement R1's own rule
(reader-facing manuscript separate from the internal record), applied
to ourselves: the volume's product half stays decision-concrete
(worked journey, behaviors with falsifiers, evaluation design,
calendar, economics), and build-reference material (schemas, CLI
contracts, fixture manifests, exit codes) lives in a reference layer,
either the dormant `19_reference_manual` restored as a final appendix
or a `docs/spec/` tree outside the volume, linked by requirement IDs.
Recommendation: appendix, so the volume remains the single artifact
the README promises, with the reference layer clearly marked as
skippable. The reader of the volume decides; the engineer opens the
appendix. Do not let schema listings leak into the narrative chapters.

## 2. The spine: a requirement coverage matrix, built first

Before touching prose, generate the traceability matrix from
`humanvoice_product_requirements.json`:

    R-ID -> evidence anchor (Part 1 label) -> design section (Part
    III label) -> test/acceptance section (Part IV label) -> calendar
    slot (week range) -> price line

The register already carries `acceptance_test` and `evidence_ids`
fields, so most of this is a join plus a search over `\label` and
`\ref` occurrences. Empty cells are the writing worklist; the matrix
itself becomes a table in the appendix and a check in
`tools/check_product_proposal.py` (fail the build if any R-ID lacks a
design or test anchor). This is what makes "concrete" checkable
instead of rhetorical, and it prevents the classic proposal failure:
commitments that appear in the promises chapter and nowhere else.

## 3. Writing order: the worked case first, then contracts, then plans

Bounded units, one at a time, build and measure between. The order is
chosen so each unit constrains the next.

Step 0. Freeze Part 2's reading brief (half a day, manager approves).
Genre: engineering and operating proposal inside a decision volume.
Readers and decision as above. Vocabulary whitelist: mechanically, the
first-use concept list of the rewritten Part 1, produced by the
hpo-survey concept meter; anything not on it gets taught at first use
or pointed forward. Exemption zones: tables, the appendix reference
layer, and the orientation map. Register exemplar: the rewritten
Part 1 itself; measure its pacing band and target it. Gate 1.

Step 1. Coverage matrix plus salvage audit (one day, mechanical).
Build the matrix. Then classify every platform-era passage in the
active product chapters keep / mine / drop against part5's six
commitments and the slice boundary, and record the dispositions in a
short appendix table so the scope cut is visible rather than silent.
Decide the two dormant chapters explicitly: fold anything still true
in `01_decision` into the orientation and economics chapters (a
decision chapter that the assembly dropped should not silently haunt
the repo), and either restore `19_reference_manual` as the reference
appendix or delete it in favor of `docs/spec/`.

Step 2. Rewrite the worked case (`13_worked_case`) first, and make
its artifacts real. This is the product half's concrete-case-first
opening and the single highest-leverage unit: one document travels
capture, inspect, revise, compare, review, with the actual finding
queue, the actual typed comparison, the actual reader-task transcript
shown and read back. If the software does not exist yet, run the
pipeline by hand on one real fixture (a ZLB chapter, or the hpo-survey
ordering fixture with its 25 known violations) and label the run as a
hand-executed protocol. Honest wizard-of-oz beats invented output, and
the non-fabrication policy leaves no third option. Everything the
later chapters specify should be visible here first in miniature.
Gate 2: the manager reads this chapter alone.

Step 3. Product and design chapters (`03_product`, `06_design`).
State every design choice in part5's table grammar: behavior, plus the
observation that would overturn it. Each choice cites its Part 1
evidence anchor or carries the phrase "engineering judgment" and a
reason. Fold in the three design additions from the hpo engagement:
exemplar documents and vocabulary whitelist and exemption zones in the
brief schema; an added-assertion check on prose diffs in compare (new
sentences bearing numbers, superlatives, or comparatives without a
citation become located questions); stopping-point and quoted-span
capture in the reader task.

Step 4. Architecture (`16_architecture`), constrained to the slice.
Module boundaries, the parser bake-off protocol as a decision
procedure (candidates, locked fixtures, the operator-burden tiebreak),
storage of versions and events. Anything that only matters at
platform scale moves to the salvage appendix.

Step 5. Testing half (`07_evaluation`, `17_evaluation_detail`,
`08_implementation`, `18_operating_plan`). Operationalize the burden
rule end to end: who measures incumbent minutes, on which documents,
when, and where the numbers land. Corpus chapter ingests the
hpo-survey adjudicated case as fixtures (three rounds, located fixes,
25 real ordering violations plus 80 adjudicated false alarms).
Candidate rule families from that engagement, pacing and ordering,
are specified here as calibration-gated experiments that must pass
the burden rule before entering the author queue; they are not v1
diagnostics, and saying so explicitly protects part5's boundary.
Implementation chapter carries the twelve-week calendar with named
tripwires; operating plan carries proceed, repair, stop with the
observable that triggers each.

Step 6. Hostile review pass, then Gate 3 (full read). In order:
requirement coverage check green; ordering audit of Part 2 against
the Part 1 whitelist; pacing meter against the Part 1 band (narrative
chapters only; the reference appendix is exempt by declared zone);
leak check for internal vocabulary; humanizer sweep; clean build;
ledger entry in the survey's findings record. Status stays
human-review-pending until the manager's read.

## 4. Standards that apply throughout

- Slow over dense, with the proportionality rule: teaching prose
  around a table stays slow; the table itself is the natural register
  for lookup material and is not padded into paragraphs.
- Never use a concept before Part 1 or the current chapter has taught
  it; generic term first, name after, or an explicit pointer.
- Every chapter ends the way part5's table thinks: what would
  overturn this. A proposal that states its falsifiers reads as
  engineering; one that does not reads as sales.
- No claims about effectiveness beyond what Part 1 established; the
  volume's own abstract already draws this line ("an investment in
  learning") and Part 2 must not creep past it.
- Additions during style repairs are the known smuggling route for
  unsupported claims; when glossing or unfolding, check each added
  sentence against the evidence anchors.

## 5. Division of labor and the three gates

The builder agent drafts and runs the checks; the hpo-survey tooling
(concept meter, first-use audit) can be run on request against any
draft; the manager holds three gates: the brief and skeleton with
coverage matrix, the worked case, the full product half. Cheap early
gates are the lesson of the hpo engagement's one expensive round: the
whole-document apparatus pass that skipped the checkpoint produced a
heavier document and a third round of feedback.

## 6. Open choices for the manager (recommendations attached)

1. Reference layer: restore `19_reference_manual` as the volume's
   final appendix (recommended) or move specs to `docs/spec/` outside
   the volume. Either way, requirement IDs are the join key.
2. Worked-case fixture: a ZLB chapter (continuity with the regression
   snapshots) or the hpo-survey ordering fixture (richer adjudicated
   ground truth). Recommended: ZLB for the journey chapter, hpo for
   the corpus chapter, so each asset does the job it is best at.
3. Dormant `01_decision`: fold and delete (recommended) or restore.
