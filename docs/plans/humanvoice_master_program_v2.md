# Humanvoice Master Program v2

**Version:** 2.0 — 11 September 2026  
**Status:** authorized for implementation; V2-G0 pending validation; V2-G1–V2-G6 not passed  
**Supersedes for current work:** `humanvoice_master_program_v1.2_2026-09-02.md`  
**Change record:** `humanvoice_v2_contract_change_2026-09-11.md`

## 1. Product mission and production operation

Humanvoice takes an immutable, finished AI-drafted technical manuscript and creates a separate revision that a declared trained reader can understand comfortably. It is a fidelity-preserving humanization operation, not summarization and not evidence-to-new-document generation. The source remains unchanged; an explicit author or editor invocation authorizes the child revision.

Fidelity is measured against a frozen, human-reviewed concept baseline. A concept includes definitions, distinctions, claims, mechanisms, assumptions, derivation steps, qualifications, examples, counterexamples, evidence interpretations, and teaching transitions. Every substantive concept must have verified output correspondence, and every active reader-specific explanation obligation must be fulfilled. Word counts, source-length ratios, and concept-density measures are diagnostics only.

## 2. Authority and precedence

Current authority, in order, is: (1) this program and its change record; (2) the product definition in `docs/survey/humanvoice_survey.tex`; (3) R1–R29 in `docs/survey/humanvoice_product_requirements.json`; (4) the normative annex and `schemas/implementation_contract.json`; (5) versioned record schemas and the inference profile. Conflicts stop implementation until these artifacts agree.

Output policy precedence is correctness, source and evidentiary fidelity, domain meaning, reader comprehension and natural expression, then style regularity. Safety and privacy controls override processing. The applicable policies in `../claudecodex/policies/humanizer-ai-writing-patterns.md` and `global-scientific-coding-agent-policy.md` are snapshotted and hashed for every run.

## 3. v1 historical boundary

v1.0–v1.2 records, gates, test results, and run artifacts remain historical evidence and retain their original meaning. They cannot satisfy a v2 gate. G6 and all v1 external-release work are suspended. Protected-object percentages, source-word retention, successful schema validation, or the existence of generated TeX/PDF files do not establish v2 semantic fidelity or product readiness. A v1 source snapshot may enter v2 only by re-initialization; no migration may invent concepts, obligations, or correspondence from a v1 blueprint.

## 4. Evidence-state vocabulary

Every report separates five states: **specified** (normative behavior exists), **implemented** (production code exists), **test-verified** (locked automated tests pass), **independently reproduced** (a second operator replays it), and **human-evidenced** (held-out readers support the product outcome). A later state is never inferred from an earlier one.

## 5. Non-negotiable invariants

1. `hv humanize` is the sole production orchestrator; greenfield authoring is legacy/experimental.
2. All reader-facing source spans receive deterministic coverage and a reviewed semantic/scaffolding disposition before rewriting.
3. Retention is exactly 1.0 over the frozen baseline; uncertain correspondence is unresolved, not partial credit.
4. Mention does not satisfy explanation. Every active obligation has located, independently verified fulfillment evidence.
5. Repetition with a distinct teaching role is semantic content.
6. Reader-irrelevant workflow scaffolding may move backstage or be removed only through an accepted span disposition after embedded domain meaning is extracted.
7. There is no document, chapter, or section length target. A roughly 2,000-word output estimate triggers semantic decomposition, never compression.
8. Exact equations, labels, citations, numbers, tables, quotations, assumptions, and qualifications remain protected in addition to semantic concepts.
9. The reader packet excludes audit machinery; a named human reader remains promotion authority.

## 6. Work packages and gates

### WP-V2-0 — authority migration

Align proposal, requirements, contract, catalogue, profile, CLI documentation, and checkers. Preserve v1 history and suspend its release path.

**V2-G0:** authority artifacts agree; R1–R29 and v2 records are specified; v1 cannot satisfy v2 release. Passing G0 establishes specification only.

### WP-V2-1 — typed semantic source model

Deliver the HumanizationBrief, SourceSnapshot, SourceSpan, SourceConcept, ConceptBaseline, ConceptDependency, ExplanationObligation, ScaffoldingDisposition, RewriteUnit, ConceptDisposition, ConceptCorrespondence, and SemanticPreflightResult schemas, with ConceptBaseline as the frozen record every later gate measures against; one shared schema loader; deterministic complete source partitioning; and a consolidated protected-object source-map contract.

**V2-G1:** every schema has valid and invalid examples; rewriting rejects uncovered spans, unresolved classification, dangling dependencies, missing obligations, and invalid exact-object links.

### WP-V2-2 — concept inventory and teaching plan

Implement resumable overlapping extraction, independent source-to-inventory and inventory-to-source critics, ambiguity adjudication, frozen baseline hashes, dependency planning, and semantic unit splitting. Humans adjudicate surfaced ambiguity and sign the baseline; they do not recreate routine inventory entries manually.

**V2-G2:** all source spans have dispositions; all substantive concepts pass bidirectional checks; ambiguities are adjudicated; every concept has obligations and a unit assignment; dependencies are acyclic or explicitly resolved.

### WP-V2-3 — source-grounded humanization

Rewrite exact source passages from the frozen plan. Every accepted replacement returns output spans and concept/obligation correspondence. Truncation or incomplete correspondence publishes no patch and causes split/resume.

**V2-G3:** mutations deleting a concept or qualification, mentioning without explaining, adding unsupported content, using a concept before teaching it, removing unapproved scaffolding, changing an exact object, or truncating output block acceptance.

### WP-V2-4 — independent preflight and causal repair

Verify the assembled candidate rather than the source alone. Retain atomic child revisions, cycle limits, repeated-finding detection, no-op checks, and oscillation detection. Replace placeholder repair behavior with concept- and obligation-targeted patches.

**V2-G4:** deterministic semantic mutations are caught or unresolved; every model critic has held-out human-labelled calibration; repair converges without regression or stops with intact parents and a located human choice.

### WP-V2-5 — patch assembly and release

Copy the immutable tree; apply non-overlapping stable-offset replacements in reverse order; encode structural moves explicitly; preserve untouched bytes; rebuild the complete candidate; and compile a clean whole-tree blackline. Release consumes v2 records only.

**V2-G5:** untouched regions are byte-stable; revised and comparison PDFs build cleanly; every semantic, exact-object, privacy, policy, and assembly gate passes; a second operator reproduces the run.

### WP-V2-6 — product evidence

Run locked unit/mutation fixtures, the complete ZLB benchmark, a held-out rights-cleared manuscript, and independent technical-reader evaluation. Card NPV-derived fixtures test teaching order and pacing only after rights review.

**V2-G6:** requires V2-G0–V2-G5, accepted ZLB and held-out packets, independent reproduction, and named reader evidence. Only V2-G6 can authorize production/external promotion. Missing human evidence cannot be waived.

## 7. Release contract

Never-except blockers are: an unfrozen or incomplete baseline; concept correspondence below exactly 1.0; any unmet active explanation obligation; unresolved dependency, unsupported addition, semantic critic, scaffolding disposition, exact-object mismatch, source/build error, assembly gap, or unauthorized transmission; invalid policy/runtime manifests; or a failed revised/blackline build. Human adjudication may correct the baseline or deactivate an inapplicable obligation before verification, with reason and lineage. It may not waive an unmet active obligation.

Operational token, time, or cost limits may pause work and require continuation authorization. They never authorize deletion or an incomplete release. The 2,000-word estimate is a pre-call split trigger only.

## 8. Verification ladder

Run, in gate order:

```bash
python tools/check_implementation_contract.py
python tools/check_program_consistency.py --require-g0-ready
python -m pytest tests/ -q
python tools/run_fixture_suite.py
python tools/run_regression_replay.py
```

The regression runner is a required WP-V2-6 deliverable and is not evidence until implemented. Later phases also require canonical no-shell-escape builds of the proposal, revised manuscript, and comparison document. Reports name every unavailable check and stop below the dependent gate.

## 9. Current decision

The owner authorized production-level implementation on 10 September 2026 and approved this semantic migration plan on 11 September 2026. That authorization permits implementation; it is not a product-release decision. As of this program’s publication, only the v2 contract is being established. No v2 implementation, replay, ZLB success, held-out generalization, or reader acceptance is claimed.
