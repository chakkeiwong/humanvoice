# Humanvoice reset memo

**Prepared:** 2026-08-26
**Purpose:** restore the working context after the VS Code crash and provide a
single, evidence-backed restart point for the Humanvoice project.

## Session source

The memo was reconstructed from the saved Codex transcript for:

- **Session ID:** `01a025c8-ed51-7231-b24e-ca4ba6f83bae`
- **Session name:** `Review survey document gaps`
- **Transcript:** `/home/ubuntu/.codex/sessions/2026/08/22/rollout-2026-08-22T03-25-20-01a025c8-ed51-7231-b24e-ca4ba6f83bae.jsonl`
- **Working directory:** `/home/ubuntu/workspace/humanvoice`
- **Session start:** `2026-08-21T19:25:20Z`
- **Last completed turn in this session:** `2026-08-26T14:52:30Z`
- **Transcript size:** 17,911 JSONL records, approximately 240 MB
- **Observable activity:** 41 user messages, 39 completed turns, 869 patch-application events

The source transcript also contains encrypted internal reasoning and policy
review records. This memo does not attempt to reproduce hidden reasoning. It
summarizes the observable user requests, assistant conclusions, tool actions,
file changes, outputs, and explicit status records.

## Resume command

```bash
cd /home/ubuntu/workspace/humanvoice
codex resume 01a025c8-ed51-7231-b24e-ca4ba6f83bae
```

Do not use `codex resume --last` if the intention is to resume the implementation
work. A newer lookup conversation is now the most recent session.

## Current state at reset

### Reader-facing document

The canonical document is one combined proposal and evidence survey:

- Source: `docs/survey/humanvoice_survey.tex`
- PDF: `docs/survey/humanvoice_survey.pdf`
- Role: `single_reader_facing_proposal_and_evidence_survey`
- Promotion state: `author_repaired_draft`
- Human acceptance: `pending_project_owner`
- Independent reader review: `pending`
- Current PDF: 266 pages, 95,413 extracted words, 56,558 reader-route words
- Visuals: 38 figures, 72 tables, 110 numbered visuals
- Visual density: one numbered visual per 2.20 body pages; largest gap 7 pages
- Source SHA-256: `a8f701abe51a5577acbd209727d4a74b0359193fbe26b2674be3b1a2db6d4a7d`
- Rendered PDF SHA-256: `c9005624b5e2d8089080b523504c0af8b94217b6a1fefb20b807eee24c7d2d6e`

Author inspection and automated checks have passed at various stages, but the
document has not been accepted by the project owner or an independent reader.
Use `docs/survey/humanvoice_document_status.json` as the current document-status
authority; earlier page counts in this memo's timeline are historical snapshots.

### Evidence audit

The current audit is deliberately **release-blocked**, with 9 of 15 gates
passing. The latest report is `docs/survey/audit/latest/audit_report.md` and the
machine gate record is `docs/survey/audit/latest/gate_results.json`.

What the latest run establishes:

- 182 search events recorded in online mode
- 13,761 deduplicated literature candidates
- 57 evidence records
- 17 load-bearing DOI identities resolved
- 26 of 26 actual bibliography DOI rows resolved
- 235 software records inventoried
- 11,700 domain-import records, all provenance-complete
- 15/18 known-item broad-search recall
- 14/18 exact challenge-query recall
- 0 load-bearing records with completed critical appraisal

Passing gates:

- protocol frozen
- minimum query count
- known-item broad recall
- domain database imports
- specialist-domain coverage
- bibliographic identity
- bibliography DOI identity
- package provenance
- artifact integrity

Failed gates:

- known-item challenge recall
- manual independent screening
- full-text load-bearing evidence
- critical appraisal
- package held-out benchmark
- external review

A title/abstract match is not an included study, a DOI match is not full-text
verification, a package README is not an effectiveness benchmark, and a model
review is not human acceptance.

### Implementation program

The current implementation plan is:

- `docs/plans/humanvoice_master_program_v1.1_2026-08-26.md`
- Version 1.1, dated 2026-08-26
- Status: WP0 executed; G0 pending; WP1 not authorized
- Normative contract: `schemas/implementation_contract.json` and
  `docs/survey/proposal/21_implementation_contract.tex`
- Contract ID/version: `HV-IC-2026-08-26` / `1.0.0`

The program authorizes a protected-source review utility first. The model-assisted
authoring extension is conditional on the protected-core gate. The twelve-week
effort is a feasibility project, not a production launch and not evidence that
Humanvoice improves expert writing in general.

The six-command product surface specified by the contract is:

```text
hv init -> hv plan -> hv draft -> hv preflight -> hv repair -> hv release
```

The initial deterministic core must support immutable source snapshots,
allow-listed scratch space, schema validation, a stable JSON result, a refusal
on incomplete briefs, and deterministic preflight on a synthetic fixture. It
does not promise autonomous prose generation, detector evasion, authorship
classification, Markdown support, a hosted service, or a scalar quality score.

The work packages are:

| Package | Timing | Purpose | Current disposition |
|---|---:|---|---|
| WP0 | days 0-5 | authorization, catalogue, runtime, fixtures, staffing | executed; G0 pending |
| WP1 | weeks 1-2 | secure vertical slice, `hv init`, deterministic `hv preflight` | not authorized |
| WP2 | weeks 2-4 | parser bake-off, source map, protected objects, canonical build | not started |
| WP3 | weeks 4-6 | protected diff, located findings, citation identity, mutation replay | not started |
| WP4 | weeks 7-9 | bounded authoring extension and calibrated critics | conditional on G1 |
| WP5 | weeks 10-11 | immutable reader packet and reader feasibility case | conditional |
| WP6 | week 12 | reproducibility, cost sensitivity, proceed/revise/stop memo | conditional |

## Durable product and editorial decisions

These decisions were repeated across the session and should not be reopened
without an explicit change record.

### Product purpose

Humanvoice is a reader-first authoring and revision system for technical
documents. Its value proposition is to reduce the work a real reader must do to
reconstruct an argument, while preserving source meaning and making uncertainty
visible.

The intended chain is:

```text
reader brief -> evidence and terminology map -> narrative blueprint ->
unit-level draft -> independent preflight -> protected build ->
blind reader rehearsal -> human acceptance
```

The product must prevent a document from reaching an expensive reader until its
argument, evidence, concept order, protected meaning, rendering, and known
failure modes have passed calibrated pre-human checks. It cannot guarantee
perfect prose for an unknown audience.

### Audience and document form

There is one reader-facing PDF, not two competing public documents. The main
readers are former professors who are now executives, financiers, economists,
project owners, and technically sophisticated decision-makers.

The document should read like explanatory nonfiction and a strong introductory
textbook: concrete cases first, visible actors, strong verbs, clear causal
transitions, definitions at the point of need, worked examples, figures that
carry an argument, and a slower cumulative pace. The desired qualities may be
informed by the Economist, good popular science, and first-year textbooks, but
the agent should not imitate a publication or copy its surface mannerisms.

The proposal's main route should contain the problem, stakes, product,
alternatives, evidence, design, pilot, economics, risks, and decision request.
Search ledgers, hashes, schemas, package inventories, requirements, gates, and
authoring history belong in appendices or backstage audit records.

### Evidence and evaluation boundaries

- Detector evasion and generic human-likeness are non-goals.
- Internal case history is not general efficacy evidence.
- A single live document can establish feasibility and burden, not a causal
  reduction in feedback rounds.
- Acceptance by a fixed horizon and cumulative reader time are the later
  comparative study's co-primary outcomes.
- Feedback rounds, author time, diagnostic triage time, abstentions, reader
  reconstruction, and confidence are secondary or feasibility measures.
- Safety failures are non-compensable: unexplained protected-object changes,
  unresolved promised objects, unauthorized disclosure, missing critical
  evidence, or an unreproducible build block release.

### Writing and pacing rules

The central writing diagnosis is grammatical and structural, not a vocabulary
defect. Abstract nouns and weak verbs hide agency; concepts often appear before
the event or object that makes them intelligible.

Use this order for ordinary exposition:

```text
actor or concrete event -> consequence -> mechanism -> name for the mechanism ->
evidence or derivation -> qualification -> decision
```

The HPO case supplied three distinct causes of a reader's complaint that a text
was "too dense": paragraph packing, concept bursts, and use-before-explain
ordering. Diagnose those separately. Use named exemplars for calibration rather
than universal words-per-concept thresholds. Treat "slow and skippable" as a
valid design objective. A visual is useful only when it makes a relation easier
to see and the surrounding prose explains what changed.

## Session timeline

The table records the user's request and the resulting substantive state. Dates
are UTC as recorded by the transcript.

| # | Date/time | User request | Result or durable lesson |
|---:|---|---|---|
| 1 | Aug 21 19:25 | Explain why the Fable-edited survey felt incomplete, unscholarly, and unpersuasive. | Diagnosed a coverage-rich internal dossier with no governing decision, comparable evidence, real search method, or reader path. |
| 2 | Aug 21 19:39 | Make the document capable of leading implementation. | Reframed it as a design and implementation basis: observed problem -> evidence -> requirements -> architecture -> evaluation -> plan. |
| 3 | Aug 21 19:47 | Ensure literature and package coverage is not locally optimized by the agent. | Identified missing search protocol, independent screening, full-text appraisal, external validity, and software benchmark; recommended procedural independence. |
| 4 | Aug 21 19:56 | Propose and execute a complete executable program for the final proposal. | Built and ran `tools/survey_audit.py` and its protocol, discovery, screening, provenance, synthesis, and release-status outputs. |
| 5 | Aug 22 02:26 | Ask whether the work was done. | Answered no: the audit machinery ran, but the evidence review remained release-blocked. |
| 6 | Aug 22 02:27 | Pursue the final proposal for eight hours. | Continued work through an audit-backed proposal and later document revisions; the time request did not waive human-review gates. |
| 7 | Aug 22 09:58 | Object that the proposal was unreadable governance prose and violated the writing policy. | Rejected the generated artifact as a reader-facing proposal; identified proxy optimization and wrong release authority. |
| 8 | Aug 22 16:30 | Ask for a better plan. | Proposed three layers: one proposal, a survey/evidence record, and backstage audit/implementation records. |
| 9 | Aug 22 16:49 | Create and execute that plan. | Began the narrative recomposition; no separate final message was emitted for this continuation. |
| 10 | Aug 22 16:54 | Continue. | Work continued through the long-running authoring sequence. |
| 11 | Aug 23 13:51 | Continue. | Produced an 11-page reader-facing proposal candidate, separate supporting survey, 29 tests, and pending human review. |
| 12 | Aug 23 16:09 | Reject two documents; require one coherent document for former-professor executives. | Unified the manuscript into one reader-facing volume and retained audit material backstage. |
| 13 | Aug 23 16:44 | Compare against MacroFinance CIP and CardNPV documents. | Used them as scale and decision-structure references, not as unquestioned prose models. |
| 14 | Aug 23 18:07 | Ask why the version was still far below the standard. | Found that the product was too small, the case was intangible, literature was a catalogue, economics were illustrative, and governance checks did not test comprehension. |
| 15 | Aug 23 18:18 | Plan, review, and execute a remedy. | Rebuilt a single decision-first proposal with a worked case, literature/design links, software shortlist, MVP, evaluation, economics, risks, and gates. |
| 16 | Aug 24 03:57 | Object that merging had reduced content and request expansion to monograph scale. | Expanded the one volume to 212 pages with cumulative chapters, case evidence, foundations, software dossiers, architecture, evaluation, operations, and appendices. |
| 17 | Aug 24 09:33 | Identify strange, abstract, governance-like language. | Diagnosed nominalizations, invisible actors, and abstraction before example. |
| 18 | Aug 24 09:39 | Clarify that the target is Economist/pop-science/textbook quality, not the flawed exemplars. | Adopted concrete-first explanatory nonfiction and cumulative teaching as the editorial target. |
| 19 | Aug 24 12:34 | Apply the concrete-first analysis to Humanvoice. | Confirmed the same structural pattern in the back half of the proposal and specified active subjects, events before abstractions, and visible costs. |
| 20 | Aug 24 12:45 | Ask whether to imitate the Economist or New York Times. | Declined literal imitation; converted the request into an explicit house style and structural charter. |
| 21 | Aug 24 12:47 | Analyze, plan, and execute a repair. | Applied a whole-document concrete-first pass; recorded a 204-page, author-repaired candidate with audit gates still open. |
| 22 | Aug 24 13:29 | Ask for assessment of a Grok review at `docs/survey/findings.md`. | The file was initially absent, so no unsupported assessment was made. |
| 23 | Aug 24 13:40 | Provide the Grok review. | Accepted its useful engineering-risk observations but rejected its unsupported claims of complete scholarship, strong pass, and readiness. |
| 24 | Aug 24 14:13 | Ask whether literature gaps could be closed. | Defined closure as online retrieval, DOI identity, specialist imports, independent screening, full-text anchors, design appraisal, package benchmarks, and external sign-off. |
| 25 | Aug 24 14:17 | Execute the literature-closure work. | Added online/imported evidence and identity checks; the audit later recorded 10/15 gates at one intermediate snapshot, with human gates still open. |
| 26 | Aug 24 17:36 | Review Fable's survey review and decide what to change. | Agreed on repeated openings, weak outcome definitions, schedule conflicts, risk bias, missing foundations, and stale registers; qualified claims about thresholds, length, and audit gates. |
| 27 | Aug 24 18:01 | Execute the changes and add more diagrams. | Produced a 210-page candidate with 27 figures and 64 tables, while retaining author-repaired rather than accepted status. |
| 28 | Aug 24 20:30 | Object that the prose remained dense and hard to read; compare with CardNPV's slower pace. | Removed the cited dense package passage from the reading route, slowed case/literature chapters, added six diagrams, and expanded to 237 pages. |
| 29 | Aug 25 05:02 | Assess the HPO survey case study. | Treated it as useful internal evidence: 25 seeded ordering violations, 80 adjudicated false alarms, and three distinct density causes; not as general research evidence. |
| 30 | Aug 25 05:08 | Plan, review, and execute HPO integration. | Added `20_hpo_case.tex`, density and reader records, added-assertion safeguards, a fixture, `concept_density.py`, tests, and a 250-page candidate. |
| 31 | Aug 25 06:17 | Extract lessons from the proposal's writing experience. | Concluded that readability reduces reader reconstruction work; evidence counts, page counts, and style scores cannot certify understanding. |
| 32 | Aug 25 16:35 | Ask how to modify the proposal from that analysis. | Proposed structural recomposition: one cumulative route, real case first, one schedule/economic model, bounded MVP, populated source matrix, parser bake-off, reader instrument, and risk table. |
| 33 | Aug 25 17:04 | Build Humanvoice so future agents write well from the first draft. | Defined the pre-draft product: `hv init`, brief completeness, claim/concept/section/visual blueprints, bounded drafting, independent critics, cumulative memory, and batched decisions. |
| 34 | Aug 25 17:09 | Prevent bad prose from reaching an expensive human reader. | Defined a fail-closed pre-human contract with hard integrity, structural writing, independent critic, simulated reader, adversarial mutation, repair, and oscillation gates. |
| 35 | Aug 25 17:13 | Put the pre-human design in the product proposal. | Added requirements R17-R24 and the authoring-extension architecture to the proposal; one snapshot reported 256 pages, 46 tests, and pending human acceptance. |
| 36 | Aug 25 20:43 | Review and change the proposal using Fable's governing-document audit. | Added the implementation contract annex, machine schemas, threat controls, runtime/model rules, CLI contracts, rights manifest, staffing, work packages, and a week-six protected-core gate. |
| 37 | Aug 26 09:44 | Fully review Fable's master implementation program. | Found it a strong architecture memo but not yet executable authorization: stale traceability, future tests presented as present, incomplete schemas, unresolved rights/runtime/staffing, and no vertical slice. |
| 38 | Aug 26 10:04 | Produce a v1.1 plan and a review/change memo for Fable. | Created `humanvoice_master_program_v1.1_2026-08-26.md` and `humanvoice_master_program_v1.1_review_request_2026-08-26.md`; left contract edits pending review. |
| 39 | Aug 26 13:09 | Assess Fable's v1.1 review. | Corrected gate sequencing, rejected an artificial 33-fixture minimum, preserved co-primary outcomes, required schema-instance validation, and corrected a historical BGS/ZLB path error. |
| 40 | Aug 26 13:14 | Execute the agreed v1.1 plan. | Executed WP0 artifacts, reconciled contract and schemas, added fixtures/runtime/catalogue/staffing records, passed 61 repository tests, and left G0 pending with WP1 unauthorized. |
| 41 | Aug 26 14:51 | Ask what is needed from the project owner. | Requested five inputs: human roles/availability, runtime choice, fixture scope, catalogue approval, and immediate G0 scope. |

## WP0 outputs and open G0 decisions

WP0 is complete as preparatory repository work. It did not pass G0 and did not
authorize parser, compiler, model, or reader execution on untrusted material.

### Current artifacts

- `schemas/record_catalog.json`: 13 conceptual records; sponsor approval pending
- `fixtures/manifest.json`: lifecycle states `planned`, `ready`, `unavailable`,
  `not-applicable`; one ready synthetic register fixture and 15 planned rows
- `fixtures/synthetic/register/001.tex`: ready synthetic source
- `fixtures/answer-keys/register-001.json`: ready answer key and abstention rule
- `fixtures/historical_sources.json`: quarantined historical artifacts; rights,
  snapshots, and answer keys are incomplete
- `security/runtime_profile.json`: Bubblewrap 0.6.1 profile selected but
  unverified on this host
- `docs/plans/humanvoice_decisions_2026-08-26.md`: technical defaults and
  unresolved human decisions
- `docs/plans/humanvoice_staffing_plan_2026-08-26.json`: eight roles, all
  unassigned
- `docs/plans/gates/G0_decision_2026-08-26.md`: pending WP0-only authorization
- `docs/plans/templates/gate_decision_record.md`: reusable gate template
- `tools/check_program_consistency.py`: strict consistency checker and mutation
  tests
- `requirements-dev.txt`: pinned schema-validation environment

### G0 blockers

1. Assign the sponsor/project owner, product engineer, security or policy owner,
   evaluation lead, domain editor/writing reviewer, document owner/author,
   independent coding reviewer, and independent reader, with allocation and
   availability intervals.
2. Verify T1-T5 under the selected runtime, or select and pin a rootless OCI
   runtime that enforces the same boundary.
3. Obtain sponsor concurrence on the 13-record catalogue and fixture rights mode.
4. Decide whether G0 remains synthetic/core-only or includes a live integration
   case with a specified document, comparator, privacy classification, and
   recruitment path.

The selected Bubblewrap probe was:

```text
bwrap --ro-bind / / --unshare-net --proc /proc --dev /dev --tmpfs /tmp /usr/bin/true
```

The host returned:

```text
bwrap: loopback: Failed to create NETLINK_ROUTE socket: Operation not permitted
```

The program explicitly forbids an unsandboxed fallback. The current G0 record
expires on 2026-09-02 or when its conditions change, whichever comes first.

## Human input packet from the last turn

The shortest reply that would let the next agent update WP0 is:

```text
Sponsor:
Technical owner / engineer:
Security owner:
Evaluation lead:
Domain editor:
Document owner / author:
Independent coding reviewer:
Independent reader(s):
Availability and allocation:

Runtime choice: host/VM with namespaces | rootless Podman | rootless Docker | narrow scope
Record catalogue: approve | changes
Initial fixture scope: synthetic-only | other
G0 scope: core-only | include live case
```

The recommended defaults are synthetic, project-owned fixtures for WP1 and WP2;
historical documents quarantined until rights and snapshots are verified; and a
core-only G0 that defers the live reader case and external corpus.

The owner does not need to choose the model, obtain all external corpus
permissions, or authorize the full authoring extension at this stage.

## Main implementation contract

The normative contract requires:

- unknown top-level record fields rejected;
- additive fields preserved under `extensions`;
- immutable source snapshots;
- canonical input never modified in place by `hv repair`;
- read-only source and allow-listed scratch/output mounts;
- no shell escape and no model-output execution;
- network-disabled parser/compiler execution;
- bounded wall time, memory, process, source, and output sizes;
- delimited, instance-validated JSON with no tool authority;
- runtime, model, tokenizer, prompt, sampling, seed, hardware, and output hashes
  whenever a model is invoked;
- stable stdout fields and exit codes;
- protected comparison outcomes that include unresolved/abstention states;
- separate bibliographic identity and source-to-claim support;
- a maximum of three repair cycles and oscillation detection;
- a machine-generated immutable reader packet separate from human acceptance;
- an unoverridable security veto; and
- no release for unresolved protected correspondence, an unparsed promised
  object, unauthorized transmission, missing critical evidence, or a broken or
  unreproducible build.

## Verification history

The session reported successful checks at the relevant snapshots:

- repeated LaTeX builds with no unresolved citations or references;
- no fatal errors or overfull boxes in the reported builds;
- deterministic PDF checks at intermediate proposal revisions;
- structural document and visual-density checks;
- audit manifest and raw-response integrity checks;
- JSON Schema and implementation-contract checks;
- mutation tests for contract and program consistency;
- 61 repository tests at the final v1.1 execution snapshot;
- `git diff --check` at the final v1.1 execution snapshot.

These checks establish repository and artifact integrity. They do not establish
reader acceptance, literature completeness, package effectiveness, or causal
product efficacy.

## Important file map

### Proposal and survey

- `docs/survey/humanvoice_survey.tex`
- `docs/survey/humanvoice_survey.pdf`
- `docs/survey/humanvoice_survey.bib`
- `docs/survey/proposal/00_orientation.tex` through
  `docs/survey/proposal/21_implementation_contract.tex`
- `docs/survey/proposal/visuals.tex`
- `docs/survey/humanvoice_document_status.json`
- `docs/survey/humanvoice_product_requirements.csv`
- `docs/survey/humanvoice_product_requirements.json`

### Audit and evidence

- `docs/survey/audit_protocol.json`
- `docs/survey/audit/README.md`
- `docs/survey/audit/latest/`
- `docs/survey/audit/imports/`
- `docs/survey/evidence/pilot_evidence.json`
- `docs/survey/evidence/corpus_rights_manifest.json`
- `docs/survey/evidence/hpo_density_fixture.json`
- `docs/survey/humanvoice_evidence_status.json`
- `docs/survey/humanvoice_contract_verification_2026-08-26.md`
- `docs/survey/findings.md`
- `docs/survey/archive/`

### Planning and governance

- `docs/plans/humanvoice_master_program_2026-08-26.md` (v1.0 predecessor)
- `docs/plans/humanvoice_master_program_v1.1_2026-08-26.md` (current)
- `docs/plans/humanvoice_master_program_v1.1_review_2026-08-26.md`
- `docs/plans/humanvoice_master_program_v1.1_review_request_2026-08-26.md`
- `docs/plans/humanvoice_decisions_2026-08-26.md`
- `docs/plans/humanvoice_staffing_plan_2026-08-26.json`
- `docs/plans/gates/G0_decision_2026-08-26.md`
- `docs/plans/templates/gate_decision_record.md`
- `docs/plans/humanvoice-product-proposal-2026-08-23/`
- `docs/plans/humanvoice-product-proposal-2026-08-24/`
- `docs/plans/humanvoice-product-proposal-expansion-2026-08-24/`
- `docs/plans/humanvoice-hpo-integration-2026-08-25/`
- `docs/plans/humanvoice-prehuman-release-2026-08-26/`

### Contract, fixtures, security, and tools

- `schemas/implementation_contract.json`
- `schemas/*.schema.json`
- `schemas/examples/`
- `schemas/README.md`
- `fixtures/manifest.json`
- `fixtures/historical_sources.json`
- `fixtures/synthetic/`
- `fixtures/answer-keys/`
- `security/runtime_profile.json`
- `tools/survey_audit.py`
- `tools/build_humanvoice.sh`
- `tools/build_product_proposal.sh`
- `tools/check_humanvoice_document.py`
- `tools/check_product_proposal.py`
- `tools/check_implementation_contract.py`
- `tools/check_program_consistency.py`
- `tools/check_visual_density.py`
- `tools/concept_density.py`
- `tools/collect_repec.py`
- `tools/prepare_review_packets.py`
- `tools/update_humanvoice_status.py`
- `tools/test_*.py`

## What not to claim on resume

- Do not call the proposal final, human-accepted, or independently reviewed.
- Do not call the literature review systematic-complete.
- Do not call package metadata or smoke tests an effectiveness benchmark.
- Do not claim Humanvoice has reduced feedback rounds from the single live case.
- Do not execute untrusted parsers, compilers, or models before runtime controls
  T1-T5 pass.
- Do not promote `author_repaired_draft` to `human_accepted` by an agent or
  automated score.
- Do not treat the 266-page count or visual density as evidence of quality.

## Recommended next sequence

1. Collect the human inputs in the compact packet above.
2. Update the staffing plan, decisions record, and G0 decision record.
3. Resolve the runtime choice and run T1-T5 on the selected reference profile.
4. Obtain catalogue and fixture-rights concurrence.
5. Run `tools/check_program_consistency.py --require-g0-ready` and record the
   result.
6. Decide G0 explicitly as pass, narrow, or stop.
7. Only after G0 authorizes WP1, create the package and deterministic vertical
   slice described in the v1.1 program.
8. Keep the proposal's document-status and evidence-status records separate from
   the implementation gate status.

This memo is a reset aid. The current machine-readable files and the G0 decision
record remain authoritative when this memo conflicts with an intermediate
session summary.
