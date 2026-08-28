# Humanvoice revision plan: use the HPO density case

Date: 25 August 2026

## Objective

Revise the single reader-facing proposal so that its account of readability is
backed by the HPO survey engagement and can be implemented. The new version
must explain why one complaint can have several causes, show how Humanvoice
would locate those causes, and preserve the distinction between a diagnostic,
an author decision, and a reader outcome.

The case record is internal evidence from one engagement. It is not a claim
that a particular words-per-concept value is a universal standard, nor that
the proposed workflow has already improved acceptance or reduced review rounds.

## Reader route

The main route will remain one proposal. It will add a short, concrete case
chapter in Part II, immediately after the existing open-source teaching
chapter. The chapter will tell the three HPO rounds in the order a reader
experienced them, then name the diagnostic ladder and the product implication.
The full measurement contract, fixture schema, and provenance boundary will
sit in the technical appendix of the same PDF.

## Work packages

1. **Case and argument.** Add a chapter that begins with the manager's repeated
   complaint, reconstructs the three rounds, and ends with a table mapping each
   symptom to a different repair. State the one-engagement limitation beside
   every numerical result.
2. **Diagnostic ladder.** Add a visual and prose contract for four levels:
   surface patterns, paragraph packing, conceptual pacing, and
   use-before-explain ordering. Make the tool output a ranked inspection list,
   not a pass/fail score.
3. **Calibration and reader evidence.** Extend the reading brief with named
   exemplars, known vocabulary, and declared exemption zones. Extend the reader
   record with stopping points, quoted spans, and the reader's reason for a
   requested change. Require chapter-level reruns and a cumulative brief.
4. **Integrity during revision.** Specify an added-assertion check for prose
   diffs. A new number, superlative, comparison, or causal assertion without a
   citation or protected-claim pointer becomes a located question.
5. **Executable prototype.** Add a standard-library-only local script that
   measures concept introduction, consolidation, bursts, live load, and
   first-use ordering on LaTeX text. It must expose its heuristic nature,
   accept a whitelist/exemption configuration, and never emit an acceptance
   verdict. Add focused unit tests using synthetic passages.
6. **Evaluation fixture.** Record the HPO case as a calibration/held-out
   fixture with provenance fields, 25 seeded ordering violations, and 80
   adjudicated false alarms. Mark replication and independent review as open.

## Skeptical review before execution

The plan was reviewed against the repository policy and the current build.

* **Wrong baseline risk:** the HPO exemplars are not a universal target. The
  script will report relative position against supplied exemplars and will not
  hard-code 253 words per concept as a threshold.
* **Proxy promotion risk:** concept counts and burst rates are explanatory
  diagnostics and repair triggers. Promotion still requires protected-object
  safety, measured burden, and a human reader outcome.
* **Measurement validity risk:** the detector is noisy and has no dependency
  parser. Findings will carry the detector version, location, and a dismiss
  path; the appendix will call for independent precision estimates.
* **Genre false-positive risk:** preview/map sections, decision boxes, and
  reference tables will be explicit exemption zones. Ordinary mathematical
  vocabulary remains allowed when the reading brief lists it.
* **Unsupported-claim risk:** HPO numbers will be labelled internal and dated.
  Any assertion introduced by an editorial repair will require a citation,
  an elementary derivation, or an author disposition.
* **Scope and readability risk:** the case will be concrete-first and limited
  to the decision it changes. Schemas and package inventories remain in the
  appendix so the main route does not become a ledger.
* **Build risk:** edits will preserve the existing single entry point, labels,
  bibliography boundary, visual-density checks, and 50,000-word route floor.

## Acceptance checks

The revision is ready for handoff when:

1. the main route contains the HPO case and its evidence boundary;
2. the appendix specifies calibration, ordering, stopping-point, and
   added-assertion records;
3. the prototype and tests run without external dependencies;
4. the unified LaTeX build has no unresolved citations/references or overfull
   boxes;
5. structural and visual-density checks pass; and
6. the status still says human acceptance and independent review are pending.

Passing these checks establishes a stronger proposal and a runnable feasibility
design. It does not establish product efficacy.

## Execution record

Implemented on 25 August 2026.

* Added the reader-facing Chapter ``A live lesson in density`` with the three
  HPO rounds, a diagnostic ladder, a slow-and-skippable repair rule, and
  stopping-point evidence.
* Added two TikZ figures, an HPO round table, and the full appendix record with
  its claim boundary, 25 positive ordering cases, and 80 adjudicated false
  alarms.
* Extended the reading brief, finding, reader, assertion, pacing, and
  first-use records; connected them to the product design, component choice,
  evaluation, implementation schedule, and operating plan.
* Added `tools/concept_density.py`, its focused tests, the checked-in HPO
  fixture, and an executable example reading brief. The prototype reports
  descriptive metrics and questions only.
* Rebuilt `docs/survey/humanvoice_survey.pdf`: 250 pages, 53,659 main-route
  words, 37 figures, 67 tables, and 104 numbered visuals.
* Verification: `python3 -m unittest discover -s tools -p 'test_*.py'` (46
  tests passed); structural diagnostics passed; visual-density diagnostics
  passed; `git diff --check` passed; the LaTeX log contains no unresolved
  citations/references, overfull boxes, or duplicate labels.

The status remains an author-repaired draft pending project-owner acceptance,
independent reader review, and the outstanding evidence-audit gates. The HPO
case remains internal calibration evidence, not a product-efficacy result.
