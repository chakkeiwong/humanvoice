# humanvoice

Making a finished technical manuscript comfortably readable without losing
anything it says.

Humanvoice takes an immutable, finished AI-drafted LaTeX manuscript and produces
a separate child revision that a declared trained reader can understand
comfortably. The source is never edited in place. Before any prose changes, the
system inventories every substantive concept the source carries and freezes that
inventory as a human-reviewed baseline; every rewritten passage is then measured
against it. Retention is exactly 1.0: a concept may be paraphrased, expanded,
merged, split, or reordered, but not dropped, and naming a concept does not count
as explaining it.

This is not summarization and not shortening. There is no document, chapter, or
section length target anywhere in the release path — an adequate explanation
often needs more words, an intermediate derivation, an example, or a slower
pace than the source used.

**Status:** the v2 contract is specified. Nothing beyond specification is
claimed: no v2 implementation, benchmark result, independent replay, or reader
acceptance. See [`docs/plans/humanvoice_master_program_v2.md`](docs/plans/humanvoice_master_program_v2.md).

## Start here

Read [`docs/survey/humanvoice_survey.pdf`](docs/survey/humanvoice_survey.pdf).
This is the single reader-facing document: it is both the product proposal and
the literature/software evidence needed to decide whether to build it. Its
canonical source is [`docs/survey/humanvoice_survey.tex`](docs/survey/humanvoice_survey.tex).
Build it with:

```bash
tools/build_humanvoice.sh
```

The volume opens with the investment decision and a concrete failure, then
examines the research literature, the software field, the capabilities already
in the project, the product design, the evaluation, the economics, and the
implementation plan. The internal case record and detailed requirements are
appendices in that same volume. Readers should not need to choose between a
``proposal'' and a ``survey.''

The current expanded build is 268 A4 pages, with about 56,994 words on the
reader-facing route before the appendices. The
volume includes a worked source-to-reader case, foundational writing
scholarship, a discipline-level literature synthesis, an adjacent-product
comparison, package dossiers and held-out fixtures, a concrete architecture,
a detailed evaluation design, and an operating plan in the same volume. The
document is still an author-repaired draft pending independent reader review
and completion of the evidence review.

The machine-readable requirements trace is
`docs/survey/humanvoice_product_requirements.csv`. Search histories, source
identity checks, package benchmarks, and review records remain under
`docs/survey/audit/latest/` as private reproducibility material. They support
the single document; they are not a second public narrative.

The implementation boundary is specified in
`schemas/implementation_contract.json`, with JSON Schemas for every run record
under `schemas/` and a corpus-rights manifest at
`docs/survey/evidence/corpus_rights_manifest.json`.

## Evidence audit

The evidence runner records discovery, screening, claim inspection, software
inventory, package evaluation, and unresolved human review. Run it with:

```bash
python tools/survey_audit.py run --online --execute-tools --build-pdf --output docs/survey/audit/latest --replace-output
python tools/survey_audit.py validate --run docs/survey/audit/latest
python tools/survey_audit.py publish --run docs/survey/audit/latest
```

Runs refuse to write into a non-empty directory. Use a fresh output path for
each audit, or pass `--replace-output` to move the prior run to a timestamped
`.previous-*` sibling before rebuilding; prior artifacts are never silently
mixed into a new run.

To add the reproducible public ACL Anthology supplement first, run
`python tools/survey_audit.py collect-public`; licensed economics and indexing
exports still need to be supplied separately with provenance sidecars. The
public slices do not by themselves satisfy the specialist-domain gate. The
current run satisfies that gate with the bounded RePEc/IDEAS collector
(`python tools/collect_repec.py`); a future release may replace or extend that
slice with an institutional EconLit, SSRN, ACM, IEEE, Web of Science, or Scopus
export.

The protocol, query log, raw response hashes, candidate registry, screening
ledger and queue, claim-level evidence matrix, software inventory and package
record, evaluation plan, benchmark results, dossier, and artifact manifest are
written under `docs/survey/audit/latest/`. New runs generate
`implementation_dossier.*`; preserved older runs may retain the legacy
`final_product_proposal.*` names inside their run folder.

`publish` copies only machine-readable requirements and status summaries, while
leaving the human-readable audit report and dossier under the run directory.
It does not copy another narrative beside the proposal, and it never writes
the canonical `humanvoice_survey.tex`, its PDF, or
`humanvoice_document_status.json`. The runner returns a nonzero status while
required evidence or human review remains incomplete.

## Product thesis

A plausible draft can pass compilation, grammar checks, and several model
reviews while still making an expert reader reconstruct its purpose and
argument. That is the ordinary condition of an AI-drafted technical manuscript:
the concepts are present but under-taught, the prerequisites arrive after the
things that need them, and the qualifications float free of the claims they
limit.

The tempting fix — ask a model to rewrite it more readably — loses content,
because a fluent paragraph can quietly drop a distinction and still look
healthy under protected-object counts and length ratios. Humanvoice's answer is
to make the concepts the unit of account rather than the words: freeze what the
source teaches, rewrite passage by passage against that frozen record, and
verify correspondence and explanation independently of the writer before a
reader is asked for anything. A later comparison must earn any claim that the
result actually reads better.

## The production path

```bash
hv humanize manuscript/ --brief brief.yaml
```

That orchestrates eight resumable phases, each runnable directly for inspection
or recovery:

```
hv init        snapshot the immutable source; refuse an incomplete brief
hv inventory   partition every reader-facing span; build the concept baseline
hv plan        assign obligations and rewrite units in dependency order
hv rewrite     rewrite one source passage; publish nothing on truncation
hv preflight   verify the assembled candidate, not just the source
hv repair      apply one named causal repair; stop on oscillation
hv assemble    patch a copy of the source tree; build revision and blackline
hv release     produce the reader packet only when every result is a pass
```

A missing result is a failure, not a pass, and there is no generic release
exception. Greenfield authoring from a brief — the v1 product — remains
available only under an explicit `hv legacy` namespace and cannot satisfy a
release gate.

## Implementation surface

```
docs/survey/  the canonical proposal, evidence status, and source material
schemas/      normative implementation contract and machine-readable records
tools/        build, structural diagnostics, audit, and test commands
vendor/       candidate external components retained for bounded benchmarks
docs/plans/   execution plans and author-side review records
```

The implementation work should add source adapters, protected-object fixtures,
diagnostic adapters, and reader-evaluation assets only when they support the
contract in the proposal. Work-package names are deliberately not part of the
reader-facing story.

Run records, gates, and test results from v1 remain readable and keep their
original meaning, but they are labelled `legacy_v1` and cannot satisfy a v2
gate. A v1 source snapshot enters v2 only by re-initialization; no migration
infers concepts or correspondence from a v1 blueprint.

Verify the current state with:

```bash
python tools/check_implementation_contract.py
python tools/check_program_consistency.py --require-g0-ready
python -m pytest tests/ -q
```

Non-goal: detector evasion. humanvoice improves prose under disclosure norms
and never optimizes against an AI-text detector.
