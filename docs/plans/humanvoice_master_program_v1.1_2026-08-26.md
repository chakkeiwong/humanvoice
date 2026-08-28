# Humanvoice master implementation program v1.1

**Version:** 1.1 - 26 August 2026
**Status:** WP0 executed in the repository; G0 is pending and WP1 is not authorized
**Supersedes for review:** `docs/plans/humanvoice_master_program_2026-08-26.md`
**Product proposal:** `docs/survey/humanvoice_survey.tex`
**Normative contract:** `schemas/implementation_contract.json` and
`docs/survey/proposal/21_implementation_contract.tex`

## Executive decision

Begin WP0 now and use its records to decide G0. At G0, approve only a
protected-core feasibility build. Authorize the model-assisted authoring
extension at the end of week six, and only if the protected core passes its
independent replay gate. The twelve-week effort is a
feasibility project, not a production launch and not evidence that Humanvoice
improves expert writing in general.

This revision keeps the useful architecture in v1.0, but makes the program
executable. It separates the product that exists from the product that is
specified, makes every gate independently observable, reconciles the record
schemas with the contract, replaces prose fixture descriptions with a required
machine-readable corpus, specifies the security runtime, and treats the live
reader case as feasibility evidence rather than a causal result.

## 0. Starting facts

The following facts are the baseline for this program. They are not completion
claims.

| Fact | Evidence | Consequence |
|---|---|---|
| The proposal and contract are present | `docs/survey/humanvoice_survey.tex`, `schemas/implementation_contract.json` | They define the intended boundary, not working software |
| The current repository contract check passes | `python3 tools/check_implementation_contract.py` | It checks contract bookkeeping and file shape; it does not execute the product |
| The current repository test suite has 61 passing tests | `python3 -m unittest discover -s tools -p 'test_*.py'` | These tests cover existing audit, document, contract, and program-consistency tools, not the planned `hv` commands |
| The evidence status is release-blocked | `docs/survey/humanvoice_evidence_status.json` | Six named evidence gates remain open; no "toward 15/15" claim is permitted |
| No product package or `hv` entry point exists | repository inspection | The first work package must create an implementation surface |
| The five historical corpus items have pending clearance | `docs/survey/evidence/corpus_rights_manifest.json` | They may not enter an external benchmark or reader packet until cleared |

Every later status report must distinguish these three states:

1. **Specified:** a behavior is written in the contract or this program.
2. **Implemented:** a testable source module and a passing integration test exist.
3. **Evidenced:** an independent human or held-out evaluation supports the claim.

Passing a schema check establishes none of the latter two states.

## 1. Changes from v1.0

| v1.0 weakness | v1.1 correction |
|---|---|
| Future test modules and runners were listed as if they were an executable program | Create a package, entry point, fixture directory, test tiers, and runnable commands before calling a work package complete |
| References used mutable line numbers and stale test locations | Use stable file paths, labels, schema IDs, and a consistency checker; fail when a cited artifact is absent or moved |
| Nine, eleven, and conceptual record inventories were mixed | Establish one canonical record catalogue and an explicit mapping from domain objects to machine records before coding |
| The contract required fields the JSON schemas did not require | Reconcile schemas, validate instances, add examples and mutation tests, and version any breaking change |
| Rights clearance was treated as the only route to engineering fixtures | Use synthetic or explicitly permitted internal fixtures for core engineering; reserve external claims for cleared material |
| Week six was called the only gate | Define start, core, extension, reader-release, and handoff gates with separate owners and stop behavior |
| P4 extended through week ten despite a week-nine contract checkpoint | Finish the authoring extension checkpoint at week nine; reserve weeks ten to twelve for integration and feasibility |
| Historical numbers were proposed as product thresholds | Keep them as quarantined provenance-replay tests, never as generalized quality ceilings |
| "One metric" encouraged proxy optimization | Use primary estimands plus non-negotiable safety constraints and feasibility process measures |
| Security controls named a container and namespace without selecting one | Select and pin one reference runtime profile, image, compiler, and limit mechanism before parser execution |
| `hv release` mixed packet generation and human acceptance | The machine emits an immutable reader packet; a separate human record records acceptance or requested changes |

## 2. Governing rules

### 2.1 Source of truth

The following files are authoritative for their respective jobs:

| Job | Authoritative artifact |
|---|---|
| Product rationale and reader experience | `docs/survey/humanvoice_survey.tex` |
| Normative execution boundaries | `docs/survey/proposal/21_implementation_contract.tex` and `schemas/implementation_contract.json` |
| Requirement identifiers and acceptance wording | `docs/survey/humanvoice_product_requirements.json` (R1-R24) |
| Machine record shape | `schemas/*.schema.json` plus the v1.1 record catalogue |
| Corpus rights | `docs/survey/evidence/corpus_rights_manifest.json` |
| Fixture identity and expected outcomes | `fixtures/manifest.json` (created in WP0) |
| Evidence completeness | `docs/survey/humanvoice_evidence_status.json` and the current audit run |

This program may schedule work and add test scaffolding. It may not silently
change a requirement, release authority, privacy rule, or evidence status.
Contract changes require a versioned change record and fixture replay.

The normative annex and `schemas/implementation_contract.json` govern behavior.
A JSON Schema proves only that an instance has the declared shape. If a schema
omits a field or permits behavior required or forbidden by the contract,
implementation stops until the schema is reconciled; schema validation does not
silently amend the contract.

### 2.2 Stable references

New planning documents must cite a path plus a stable heading, label, schema ID,
or JSON key. They must not cite a volatile line range as the sole traceability
link. `tools/check_program_consistency.py` verifies:

- every cited file exists;
- every cited heading, label, schema ID, and requirement ID exists;
- the phase-to-requirement mapping is exactly R1-R24, with no missing or invented ID;
- every named test, runner, fixture, and artifact has either a repository path or
  an explicit `planned` status; and
- the schedule agrees with the contract checkpoints.

The program cannot pass G0 while this checker is absent or failing in
`--require-g0-ready` mode.

### 2.3 Human and machine authority

The machine may locate, compare, measure, and prepare a question. It may not
accept a document, waive a protected-object mismatch, or convert an abstention
into a pass. The author owns wording decisions; the domain reviewer owns
meaning disputes; the security owner may veto a release; the named reader owns
the reader decision.

## 3. Product boundary and increments

### Increment A: protected-source review utility (weeks 1-6)

Increment A is the first deliverable and must be useful without a model. It
contains:

- a LaTeX source snapshot and read-only build wrapper;
- a canonical, reproducible build record;
- a source map and protected-object manifest;
- typed correspondence and protected comparison;
- citation identity checks separated from claim support;
- located deterministic findings and explicit abstentions; and
- the six-command JSON result contract, with at least `hv init` and
  `hv preflight` working end to end in the first vertical slice.

Increment A does not promise prose generation, autonomous repair, authorship
classification, Markdown support, a hosted service, or a scalar quality score.

### Increment B: bounded authoring extension (weeks 7-9, conditional)

Only after the core gate passes, the team may add:

- `hv plan` for a bounded claim and concept-dependency blueprint;
- `hv draft` for one approved unit with a declared evidence boundary;
- construct-specific critics calibrated on frozen human labels;
- `hv repair` as child revisions with a three-cycle limit and oscillation stop;
- pre-human integrity, argument, writing, evidence, and reconstruction checks; and
- a release packet that can be handed to a named reader.

If any model-dependent gate remains an abstention, the deterministic core may
continue, but the run cannot be described as a full authoring release.

### Feasibility handoff (weeks 10-12)

The final handoff contains one reproducible run, a timed reader record, a burden
account, rights and disclosure status, cost sensitivity, and a proceed/revise/
stop memorandum. It does not contain a claim of general efficacy.

## 4. Work packages and deliverables

The work packages below replace the looser phase descriptions in v1.0. Each has
one owner, one result note, a concrete artifact list, and an observable exit.
WP0 is the pre-authorization package created by this program; the six product
work packages named in the machine contract are WP1--WP6.

| WP | Weeks | Owner | Main output | Exit gate |
|---|---:|---|---|---|
| WP0 - authorization and catalogue | days 0-5 | sponsor + technical owner | decisions, record catalogue, runtime profile, fixture inventory | G0 |
| WP1 - secure vertical slice | 1-2 | product engineer + security owner | package, `hv init`, `hv preflight` deterministic path, threat fixtures | vertical-slice exit |
| WP2 - parse and protect | 2-4 | product engineer | parser scorecard, source map, protected manifest, canonical build | internal integration gate |
| WP3 - compare and diagnose | 4-6 | product engineer + domain reviewer | protected diff, findings, citation identity, CLI replay | G1 |
| WP4 - bounded authoring extension | 7-9 | product engineer + evaluation lead | plan, bounded draft, critics, mutation and repair path | G2 |
| WP5 - reader feasibility | 10-11 | evaluation lead + document owner | immutable packet, reader record, burden account | G3 |
| WP6 - decision handoff | 12 | sponsor + evaluation lead | reproducibility record, cost sensitivity, proceed/revise/stop memo | G4 |

### WP0 - authorization and catalogue (days 0-5)

WP0 is the work that produces the evidence for G0; G0 is its exit decision, not
an earlier work phase. Passing G0 authorizes WP1. Creating a plan or an empty
manifest does not authorize product code, parser execution, or TeX compilation
on untrusted material.

Before code is accepted, record the following decisions:

1. the reference operating environment and supported host platform;
2. the sandbox mechanism and its pinned image or executable hashes;
3. the canonical machine-record inventory and compatibility policy;
4. the engineering fixture rights mode (synthetic, cleared internal, or both);
5. the reference and fallback model policy, including the rule that no model is
   invoked before its artifact and prompt hashes are recorded;
6. the live feasibility document, comparator, and reader recruitment path; and
7. the people available for engineering, evaluation, domain review, security,
   independent replay, and sponsorship.

**Artifacts:**

- `schemas/record_catalog.json`;
- `security/runtime_profile.json`;
- `fixtures/manifest.json`;
- `fixtures/historical_sources.json`;
- `docs/plans/humanvoice_decisions_2026-08-26.md`;
- `docs/plans/humanvoice_staffing_plan_2026-08-26.json`;
- `docs/plans/templates/gate_decision_record.md`;
- `docs/plans/gates/G0_decision_2026-08-26.md`;
- a rights classification for every proposed source; and
- `tools/check_program_consistency.py`;
- `requirements-dev.txt` (the pinned schema-validator environment).

**Exit:** G0 passes only when each decision has an owner and a recorded value,
or the scope is explicitly narrowed. "To be decided later" is not a pass for a
decision needed by the next work package.

### WP1 - secure vertical slice (weeks 1-2)

Create the implementation surface that v1.0 lacked:

```text
pyproject.toml
src/humanvoice/
tests/
fixtures/
security/
```

The package exposes an `hv` console entry point. Existing document and survey
tools remain under `tools/`; they are not silently presented as the product.

Implement first:

- immutable source snapshot creation;
- allow-listed scratch directory creation;
- the selected runtime profile;
- JSON Schema instance validation;
- one JSON result on stdout and human diagnostics on stderr;
- `hv init` refusal on missing critical brief fields; and
- `hv preflight` on one synthetic fixture, including a blocking abstention.

WP1 may create `hv init`, schemas, adapters, runners, and test scaffolding before
the threat suite passes. It may not execute a parser, compiler, imported source
executable, or model on untrusted material until the applicable T1--T5 fixtures
are `ready` and passing:

| Control | Required implementation | Required observation |
|---|---|---|
| T1 | read-only bind or copy of the source and an allow-listed scratch mount | source hash unchanged; no write outside the allowlist |
| T2 | `-no-shell-escape`, `-halt-on-error`, `-file-line-error`, and no execution of model output | shell-command fixture cannot create a file |
| T3 | network-disabled sandbox for compiler and parser | attempted connection returns exit code 5 |
| T4 | delimited, instance-validated JSON adapter with no tool authority | instruction-looking source text is treated as data |
| T5 | time, memory, file, process, and output limits enforced by the runner | exhaustion aborts and records the limit |

The shell-escape test uses a per-run temporary directory and a non-sensitive
sentinel path. It must not rely on a shared `/tmp/pwned` file.

**Exit:** the vertical slice runs from a brief to a deterministic preflight
result on a clean checkout, and each T1-T5 test passes. A recorded security
blocker is a correct fail-closed result, but it does not satisfy the exit. No
parser benchmark is accepted before this exit.

### WP2 - parse and protect (weeks 2-4)

Run the parser bake-off on the locked fixture manifest. Candidates may include
`pylatexenc`, `unified-latex`, `TexSoup`, `plasTeX`, `LaTeXML`, and
`tree-sitter-latex`, but selection is based on the same source-map contract,
protected-span recall, intentional abstention, round-trip behavior, and
operator minutes. Popularity is not an acceptance criterion.

Implement:

- one primary adapter and one fallback with the same output contract;
- canonical entry-point validation and reproducible LaTeX build;
- typed protected objects retaining raw and normalized forms;
- stable source and rendered locations;
- equation, number, unit, label, citation, quotation, table, code, and
  qualification correspondence; and
- an explicit unresolved outcome that blocks the affected release gate.

**Exit:** a second operator can run the parser and build on the fixture set,
inspect the source map, and reproduce the same deterministic record fields.

### WP3 - compare and diagnose (weeks 4-6)

Implement only located, reviewable findings:

- register leakage, with project-configurable vocabulary;
- structural repetition and pacing relative to declared exemplars;
- first-use and concept-dependency checks with abstention on uncertain matches;
- citation identity, separate from source-to-claim support;
- added-assertion questions for uncited numbers, superlatives, comparisons, and
  causal claims;
- protected diff with unchanged, explained change, added/removed with
  explanation, and unresolved outcomes; and
- `hv drift` refusal for a single document, preserving the R12 boundary.

No command in WP3 mutates the canonical input. Findings contain a location,
observation, consequence or question, rule/version, and author disposition
field. A priority value orders work; it is not a document-quality score.

**Exit:** the protected comparison and deterministic findings replay on the
machine fixture set; CLI stable fields remain unchanged across replay; seeded
sign, exponent, unit, number, citation, label, quotation, denominator, and
claim-scope mutations are caught or abstained.

## 5. Gates and stop behavior

There is no single "true gate." The following gates have distinct purposes and
owners.

### G0 - authorization gate (day 5)

**Decision owners:** sponsor or project owner, with technical-owner and security-
owner concurrence.

**Pass:** contract version, record catalogue, runtime profile, fixture rights
mode, staffing, live-case path, and consistency checker are recorded.
**Narrow:** authorize Increment A with synthetic fixtures only.
**Stop:** no safe runtime or no owner for a never-except decision.

### Internal integration gate (end of week 4)

**Decision owners:** product engineer and security or policy owner, with domain-
reviewer concurrence on protected meaning.

**Pass:** parser and source-map outputs satisfy the fixture contract.
**Narrow:** reduce the supported LaTeX subset and publish the unsupported
construct list.
**Stop:** the adapter produces a complete-looking protected record after losing
an object.

### G1 - protected-core gate (end of week 6)

**Decision owners:** sponsor or project owner and independent coding reviewer,
with security-owner concurrence.

A second operator starts from a clean environment and:

- reproduces the source map, protected comparison, and deterministic CLI fields;
- replays every machine fixture, including negative and abstention cases;
- observes a byte-identical source tree after build and inspection;
- records the build image, compiler, packages, configuration, and source date;
- reproduces the canonical rendered artifact under the pinned reference profile;
  if the profile differs, records the difference and keeps the run
  non-promotable until it is replayed under the reference profile; and
- measures the planning envelope without silently changing it.

**Pass:** authorize WP4 only after the reference-profile replay succeeds.
**Narrow:** if the profile differs or the replay cannot be completed, deliver the
protected-review utility and run a core-only feasibility case; do not claim a
full authoring path.
**Stop:** protected correspondence cannot be trusted or a security control is
unverifiable.

### G2 - authoring-extension gate (end of week 9)

**Decision owners:** sponsor or project owner and evaluation lead, with document-
owner and security-owner concurrence.

The exact runtime, model artifact, tokenizer, prompt template, and sampling
configuration have hashes. Calibration and held-out results are separate. Each
critic reports false positives, false negatives, abstentions, labels, and
operator burden. The bounded writer cannot widen the blueprint's evidence or
claim boundary. Repair passes mutation tests and stops at three cycles or an
oscillation.

**Pass:** prepare a reader packet.
**Narrow:** retain deterministic diagnostics and mark model-dependent gates
abstained.
**Stop:** a critic or repair path silently changes a protected object, or its
burden and error behavior are not measurable.

### G3 - reader-session gate (weeks 10-11)

**Decision owners:** evaluation lead and document owner or author. The independent
reader owns the reader decision, not the machine release result.

The machine emits one immutable PDF and packet hash after all required machine
gates pass. It does not record human acceptance itself. The reader receives no
finding IDs, model confidence, parser warnings, private paths, or internal
phase names. A separate `ReaderDecision` record captures the named reader,
document hash, six rubric responses, confidence, elapsed time, first stop or
reread point, and decision.

**Pass:** the reader can complete the task and the record is linked to the exact
packet. This is a human outcome after the machine packet gate; it is not a
second machine release status.
**Narrow:** report integration only if the reader record is incomplete.
**Stop:** protected comparison, privacy, or reader independence is compromised.

### G4 - handoff gate (week 12)

**Decision owners:** sponsor or project owner and evaluation lead.

The sponsor receives all abstentions, exceptions, rights status, actual burden,
cost sensitivity, reproducibility results, and a proceed/revise/stop decision.
The result note must state which claims are specified, implemented, and
evidenced. It must not report a causal reduction in review rounds from one live
document.

## 6. Canonical records and schema reconciliation

The v1.0 materials use different inventories: the design chapter describes nine
records, the architecture chapter describes eleven domain objects, and the
repository contains nine JSON Schemas with a different grouping. This is a
blocking ambiguity, not a documentation preference.

WP0 must publish `schemas/record_catalog.json` with one row per conceptual
object. The recommended mapping is:

| Conceptual object | Required for the first product path | Recommended v1.1 treatment |
|---|---|---|
| Authoring brief | yes | existing standalone schema |
| Argument blueprint | yes for Increment B | existing standalone schema |
| Document/version and source snapshot | yes for lineage | standalone schema or an explicitly versioned nested object; choose once |
| Protected span/object | yes for comparison | standalone schema or an explicitly versioned nested object; choose once |
| Finding | yes | existing standalone schema |
| Revision | yes | existing standalone schema |
| Preflight run | yes | existing standalone schema |
| Release decision | yes | existing standalone schema |
| Runtime manifest | yes for every inference run | existing schema expanded |
| CLI result | yes for every invocation | existing schema expanded |
| Reader decision/session | yes for G3 | standalone schema recommended |
| Evidence item | yes for claim support and package appraisal | standalone schema recommended |
| Corpus rights item | yes | existing corpus schema expanded |

The sponsor must approve this mapping at G0. If standalone schemas are added,
the contract version must change and all locked fixtures must replay. If objects
remain nested, the parent schemas must require the fields needed to reconstruct
lineage. Neither arrangement may leave an object named in the proposal without
an explicit machine representation.

The following schema corrections are mandatory whichever mapping is chosen:

These corrections repair pre-release scaffolding against the already approved
contract; no Humanvoice record has been released to an external consumer. G0
freezes the resulting schema version. If an external instance is discovered,
the team must issue a migration and versioned replay before accepting it.

- Runtime manifests require runtime revision, model hash, tokenizer hash,
  prompt-template hash, sampling parameters, seed, hardware, network state,
  latency, memory, and output hash, in addition to common record fields. For a
  deterministic no-model run, model-specific fields are explicit `null` values
  with a `not_applicable_reason`; an inference run must provide concrete values.
- CLI results require all nine stable stdout fields: contract version, command,
  status, exit code, run ID, record paths, blocking reasons, source hash, and
  result hash.
- Corpus records require all eight rights fields, including `consent_date`.
- Unknown top-level fields are rejected unless they occur under an explicit
  `extensions` object; the compatibility rule applies to extension contents.
- Authoring briefs require the reader, decision, genre, known vocabulary,
  exemplars, evidence boundary, privacy class, protected objects, and explicit
  unknowns. Argument blueprints require evidence anchors, terminology order,
  and a plan hash. Findings require a consequence, question, rule version, and
  author disposition in addition to their observation and location.
- A pinned JSON Schema validator validates record instances, not just schema
  files. Examples of valid, invalid, and abstained records are checked in.

## 7. Fixture, rights, and regression policy

### 7.1 Machine fixture corpus

Create the following layout:

```text
fixtures/
  manifest.json
  synthetic/
    macro/
    equation/
    table/
    citation/
    qualification/
    register/
    intentional-pattern/
    pacing/
    first-use/
    assertion/
    reader/
  historical/
    zlb/
    bgs/
  answer-keys/
```

Every manifest row has one lifecycle state:

- `planned`: the case is inventoried, but executable source or an answer key
  does not yet exist;
- `ready`: source and answer-key files exist, their hashes match, rights permit
  the declared use, and the runner may count the case;
- `unavailable`: a named source or permission cannot currently be obtained, with
  the reason recorded; or
- `not-applicable`: the case does not have the named outcome for a stated
  semantic reason.

Every row contains a fixture ID, lifecycle state, rights status, owner, intended
job, expected outcomes, requirements, and evaluation scope. A `ready` row also
requires real source and answer-key paths and hashes. Planned rows may not carry
placeholder hashes, and neither planned nor unavailable rows count as passing
evidence. A fixture with no answer key is not a held-out benchmark.

The catalogue describes eleven cases, but does not create a mechanical
eleven-times-three quota. Not all cases naturally have three outcomes. For
example, the Reader case
has a human outcome rather than a deterministic abstention; it is a reader
exercise, not a three-state parser test. The Assertion case needs a concrete
unresolvable-citation abstention. The denominator of every report is the
manifest, including not-applicable and skipped rows.

G0 requires a complete inventory and an honest readiness count. Before any
untrusted parser or compiler invocation, T1--T5 must be `ready` and passing.
Before G1, every machine fixture required by Increment A must be `ready` and
replayed. Stub files and invented hashes satisfy none of these gates.

`tools/run_fixture_suite.py --manifest fixtures/manifest.json --report` exists
as of WP3 (2026-08-27) and executes against the ready fixtures. Its last
recorded run reported `ready=4 matched=4 mismatched=0 errors=0
not_executed=12`; the 12 not-executed rows remain unready in the manifest and
are not claimed as passing.

### 7.2 Rights separation

Pending or restricted project documents may be used only for internal fixture
work when their owner permits that use. They cannot appear in a published
benchmark, external reader packet, or commercial training set. Until written
permission and real source hashes exist, use synthetic fixtures for public
reports and label historical results as unavailable.

Rights clearance is therefore an external-use gate, not a reason to stop all
deterministic engineering. The rights manifest must distinguish:

- `engineering-only` fixtures;
- `internal-evaluation` fixtures;
- `external-reader` fixtures; and
- `excluded` material.

These are evaluation-scope values, not replacements for the contract's
`redistribution_status` values. Store them in a dedicated manifest field (or an
explicit extension) so rights and evaluation use cannot be conflated.

### 7.3 Historical replay quarantine

`fixtures/historical_sources.json` is the locator registry for historical
material. Each row records the repository, path, hash, rights state, and replay
availability. A prose path is not evidence that an artifact exists.

The 133-dash, 109/109-equation, opener-distribution, sloptrim, and BGS taxonomy
observations remain useful only as historical reproduction tests. Each requires
the original source snapshot, artifact hash, provenance record, and permission.
They are not release thresholds, style targets, or evidence of performance on a
new document. If the source artifact is absent, the test is `unavailable`, not
silently passed.

`tools/run_regression_replay.py --historical` is a planned runner. Its report
must separate `reproduced`, `not-reproduced`, `unavailable`, and `not-applicable`.
No aggregate score may hide an unavailable historical artifact.

## 8. Security runtime profile

Before WP1, select one reference implementation for the local Linux MVP: a
rootless OCI container runtime (Podman or Docker rootless, one named choice) or
another mechanism that demonstrably supplies the same isolation. Record:

- image or executable digest;
- host OS and kernel assumptions;
- read-only source mounts and allow-listed output mounts;
- network-disabled mode;
- no-new-privileges and dropped capabilities;
- CPU, memory, process, file-size, wall-clock, and output limits;
- TeX distribution, compiler, fonts, packages, and versions; and
- the command used by the second operator to reproduce the profile.

If the selected runtime is unavailable, the run stops before parser invocation.
There is no "best effort" unsandboxed path in the product.

The PDF reproducibility policy distinguishes:

- source and record hashes, which must be deterministic under the same manifest;
- rendered PDF byte hashes, which require the same pinned image and toolchain; and
- visual or semantic comparisons, which diagnose environment differences but do
  not satisfy a byte-identity promotion gate unless the contract is amended.

`SOURCE_DATE_EPOCH` is necessary but not sufficient for a reproducible PDF.

## 9. Evaluation and reader protocol

### 9.1 Feasibility versus efficacy

The first twelve weeks contain one live document. They can establish that the
workflow runs, records burden, preserves protected objects, and presents a
reader task. They cannot estimate a treatment effect against a counterfactual.
The feasibility report must not call rounds saved, acceptance improved, or
return on investment an observed product effect.

### 9.2 Outcomes

For the later comparative study, retain the proposal's co-primary outcomes:

- acceptance by a fixed horizon; and
- cumulative reader time through that horizon.

Report feedback rounds, author time, diagnostic triage time, abstentions,
requested substantive changes, reader reconstruction, and confidence as process
or secondary outcomes. In the feasibility case, report them descriptively.

Use non-negotiable safety constraints alongside the primary estimands:

- zero unexplained protected-object changes in any released packet;
- no release with unresolved promised objects, critical evidence, unauthorized
  disclosure, or unreproducible source build;
- every model-dependent result carries its runtime and artifact manifest; and
- a diagnostic enters the live queue only when its held-out burden distribution
  beats the incumbent operating rule and no silent protected failure occurs.

This is a primary outcome plus guardrails, not a single proxy scoreboard.

### 9.3 Reader task

The reader receives the PDF, declared role, and decision question, without source
history or project context. The six questions are:

1. What problem or decision is this document about?
2. What mechanism or object is proposed?
3. Which evidence is decisive?
4. Which qualification changes the interpretation?
5. What action would you take now, and why?
6. Where did you stop or reread, and what relation were you trying to recover?

One reader is enough for the integration gate only. A second independent reader
is the target for the feasibility case; if unavailable, the report labels the
single-reader limitation and makes no general reader claim. Human acceptance is
stored separately from the machine release decision.

### 9.4 Selection and comparator

Select the live document from a pre-specified intake pool using failure cost,
confidentiality, reader availability, and genre eligibility. Record rejected
candidates and reasons before the workflow is run. Describe the incumbent tools
and human process before assignment. Do not select a document because it is easy
to improve or likely to produce favorable optics.

### 9.5 Model critics

Critics reduce routine defects presented to a reader; they do not replace the
reader. Calibrate on a frozen human-labelled set, randomize pair order, control
length, test multiple judge families where practical, and report confusion
matrices, calibration, subgroup behavior, and abstentions. A model result can
nominate a passage or explain a discrepancy; it cannot accept a document.

### 9.6 Repair limit

The contract's maximum is three repair cycles per unit. The reader stop rule is
also three cycles unless the sponsor approves a stricter live-case rule before
the case begins. A report must never use "two" in one place and "three" in
another without identifying which limit it means.

## 10. Schedule and capacity

The calendar below preserves the contract's week-six core checkpoint and
week-nine authoring checkpoint.

| Time | Work | Required evidence at the end |
|---|---|---|
| days 0-5 | WP0 decisions, catalogue, runtime profile, fixture inventory, staffing record | G0 decision record and consistency check |
| weeks 1-2 | WP1 package, threat boundary, `hv init`, deterministic `hv preflight` | vertical-slice integration report |
| weeks 2-4 | WP2 parser bake-off, source map, protected objects, canonical build | parser scorecard and internal integration gate |
| weeks 4-6 | WP3 protected diff, findings, citation identity, mutation replay | G1 second-operator core replay |
| weeks 7-8 | blueprint, bounded unit writer, model manifest, critic calibration | calibration report; unresolved model gates abstain |
| week 9 | repair, release authority, held-out replay | G2 extension checkpoint |
| weeks 10-11 | immutable packet, reader task, burden and disclosure records | G3 reader-packet record |
| week 12 | clean rebuild, rights review, cost sensitivity, sponsor memo | G4 decision handoff |

The base plan requires at least one product engineer, an evaluation lead with
protected time, a domain editor, a security or policy owner, an independent
coding reviewer, an independent reader, and a sponsor. If only one engineer is
available, Increment A remains authorized but Increment B is not promised until
G1. A staffing shortfall is a scope decision, not an invisible schedule risk.

## 11. Test tiers and CI

The existing repository tests remain regression tests for the repository's
current document, audit, contract, and program-consistency tools. Product tests
are added under `tests/` and are not
counted as passing until their implementation exists.

Test tiers produce evidence; promotion gates consume evidence from several
tiers. An integration gate is therefore not a ninth test tier, and an
integration test is not itself authorization to proceed.

| Tier | Location or command | Purpose |
|---|---|---|
| Unit | `python3 -m unittest discover -s tests` | pure record, normalization, matching, and policy behavior |
| Contract | `tools/check_implementation_contract.py` plus instance validation | contract and schema invariants |
| Security | `tests/test_threat_controls.py` in the selected runtime | T1-T5 and failure semantics |
| Fixture integration | `tools/run_fixture_suite.py` | positive, negative, abstention, and N/A outcomes |
| Mutation | `tests/test_mutations.py` | seeded meaning and evidence changes cannot pass silently |
| Replay | `tools/run_regression_replay.py` | historical provenance only |
| Reproducibility | `tests/test_second_operator_replay.py` | clean-environment source/record/PDF behavior |
| Human | recorded reader protocol | comprehension, action, burden, and acceptance |

The build pipeline becomes:

```text
program consistency -> contract validation -> instance validation ->
security profile test -> unit tests -> fixture suite -> mutation suite ->
historical replay (if available) -> LaTeX build -> citation check ->
visual inspection -> status record
```

The pipeline must report skipped, unavailable, and abstained tests explicitly.
It may not improve a denominator by omitting difficult fixtures.

The claim in v1.0 that a mutation was already run is not carried forward unless
the mutation script, changed hash, failure output, and restoration hash are
stored as an artifact.

## 12. Decision log before G0

The named owners resolve these questions in the WP0 records before G0:

| Decision | Owner | Default recommendation | Blocks |
|---|---|---|---|
| Canonical record inventory | technical owner + sponsor | approve the catalogue and add standalone schemas where lineage requires them | all code |
| Schema strictness and validator | product engineer | reject unknown top-level fields; allow versioned `extensions`; pin validator | WP1 |
| Sandbox mechanism | security owner | rootless, network-disabled OCI profile with digest | WP1 |
| Engineering fixture rights | document owner | synthetic plus explicitly permitted internal fixtures | WP1/WP2 |
| Historical artifact availability | evidence lead | mark unavailable until source and permission hashes exist | replay claims |
| Reference machine and TeX image | sponsor | pin host/image/compiler/package versions | G1 |
| Model and fallback | evaluation lead + sponsor | no invocation until hashes and licence are recorded | WP4 |
| Live case and comparator | document owner + evaluation lead | pre-specified intake pool and incumbent description | WP5 |
| Reader count | evaluation lead | two target, one integration minimum | G3 |
| Extension staffing | sponsor | do not promise WP4 with one engineer alone | G2 |

## 13. Risks and responses

| Risk | Early signal | Response |
|---|---|---|
| The core package does not exist by week two | no `pyproject.toml`, entry point, or vertical-slice result | narrow to source snapshot and protected comparison; reset the extension promise |
| Parser loses a protected construct | complete-looking record with an unresolved object | fail closed, publish unsupported construct, select fallback or narrow scope |
| Sandbox cannot be reproduced | second operator lacks the same isolation profile | stop parser execution; do not use an unsandboxed substitute |
| Rights remain pending | source hash or written permission absent | use synthetic/internal-only fixtures; block external claims |
| Historical replay artifacts are missing | named JSONL/PDF/source files cannot be located | report `unavailable`; remove them from release gates |
| `hv plan` consumes the extension window | dependency graph cannot pass seeded and adjudicated cases by week eight | keep deterministic core; do not silently compress G2 or G3 |
| Model critics are noisy or expensive | held-out burden does not beat incumbent | leave critics abstained and run the core-only path |
| A metric improves while meaning worsens | protected incident or reader reconstruction failure | safety veto; no aggregate score can override it |
| Pilot selection is favorable | rejected candidates are not recorded | pause selection, publish the intake rule, and redraw the case |
| Instrumentation expands without user value | artifacts grow while burden is unmeasured | delete nonessential telemetry and preserve only contract records |

## 14. Definition of done

The v1.1 program is complete only when the sponsor can inspect:

- a working, installable protected-core package and its exact runtime profile;
- a machine-readable record catalogue and schemas whose required fields agree
  with the contract;
- a rights-labelled fixture manifest with source and answer-key hashes;
- passing positive, negative, abstention, and mutation tests;
- a second-operator core replay and its environment record;
- an explicitly conditional authoring extension result, including abstentions;
- an immutable reader packet and separate human reader decision, if G3 is run;
- a burden, safety, rights, and cost record; and
- a proceed/revise/stop memo that states what remains unproved.

The program does not declare success because a PDF builds, a model produces
fluent prose, a style count falls, or the current contract checker prints PASS.

## 15. Review disposition and execution status

Fable's review is retained at
`docs/plans/humanvoice_master_program_v1.1_review_2026-08-26.md`. Its useful
readiness findings produced the fixture lifecycle, historical-source registry,
staffing record, gate template, and executable consistency check in this
revision. Its proposed 33-stub quota, schema-over-contract precedence, single
feedback-round metric, and pre-test ban on writing any `hv` scaffolding are not
adopted because they conflict with this program or the normative contract.

WP0 is authorized as preparatory work only. This is a pre-G0 state, not the
gate's `narrow` outcome: G0's narrow outcome would authorize Increment A with
synthetic fixtures. G0 has not passed, and the gate record must distinguish a
structurally consistent program from a staffed and verified runtime. Any future
change to normative behavior must be made in the contract artifacts, not hidden
in this plan.
