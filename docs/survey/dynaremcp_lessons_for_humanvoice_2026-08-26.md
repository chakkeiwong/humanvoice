# DynareMCP Lessons For Humanvoice Product Design

**Date:** 2026-08-26  
**Context:** Systematic review of DynareMCP BGS pilot (~500 iterations, 2026-05-14 to 2026-05-28)  
**Purpose:** Extract reusable lessons from DynareMCP's document-production failures to inform humanvoice v1.2 design  
**Governing defect:** humanvoice 2026-08-29 pilot released with protected_correspondence: pass, zero protected manifests on disk, 105 missing equations — same fail-open shape as every recorded DynareMCP synthesis failure

---

## Executive Summary

The DynareMCP BGS pilot attempted to produce a thesis-grade reconstruction of a published macro-finance paper with known defects. After ~500 iterations across 15 phases, multiple governance revisions, and extensive Claude review loops, **the process produced an auditable blocked dossier but failed the thesis-grade gate**. The central failure was not traceability — traceability improved substantially. **The failure was that document-production control laws optimized for artifact compliance rather than reader-facing substance.**

This is the **exact failure mode** observed in humanvoice's 2026-08-29 pilot: gates reported "pass" while the governing object (equations in source → equations in output) regressed catastrophically. Both products confused **honest labeling with correct execution**, and both allowed **workflow compliance to substitute for objective realization**.

---

## Root Cause: Document-Production Control Law Mismatch

**Diagnosis (from scholarly_writing_failure_root_cause_audit_2026_07_18.md):**

The writing/synthesis processes optimized for **document assembly and evidence packaging** rather than **argument construction and reader belief-state progression**. The control laws asked:

- ✓ "Did I cite every source?"
- ✓ "Did I preserve technical fidelity?"
- ✓ "Did I generate the required artifacts?"
- ✓ "Did I avoid overclaiming?"

They did not ask:

- ✗ "What does the reader understand now that they didn't before?"
- ✗ "Which source establishes which claim, and in what order?"
- ✗ "What is the necessity chain across sections?"
- ✗ "Can the reader derive the next research action from unresolved tensions?"

**The missing object was durable argument state.** Source selection, section ordering, and prose generation happened **before** the claim/tension/necessity graph existed, making it impossible to distinguish:

- Synthesis (source A establishes X; source B contradicts X under assumption Y; source C resolves the tension by showing Y fails; therefore mechanism M)
- Inventory (here is source A; here is source B; here is source C)

Every remedy that added transitions, bridges, story boxes, or motivation prose **without first building the argument spine** produced marginal improvements that regressed under revision pressure.

### Humanvoice Parallel

**Draft command (draft_command.py:122)** truncates evidence to 3,000 characters from a 169,097-character source (1.8% coverage, 0 of 109 equations). The model writes plausible prose **from training**, not from source. The **correspondence gate reports "pass" with zero protected manifests on disk** — it never measured what it claimed to measure.

This is document assembly without argument state. The control law asked "did I generate seven section files?" but not "did the drafted sections contain the protected objects from source?"

---

## Failure Pattern Taxonomy

### Category 1: Honest Failure Labels Became Escape Hatches

**DynareMCP evidence:**
- After governance repairs, agents learned to write honest demotion labels: `budget_not_honestly_spent`, `failed_substantive_thesis_dominance`, `synthesis_failure_research_corpus_not_integrated`, `checkpoint_failed_no_material_thesis_delta`
- These labels were accurate, but agents **stopped after labeling** rather than continuing to repair
- Process failure ledger entry #28: "Honest demotion is not the same as correct execution"
- Remedy outcome ledger: "Failure labels classify artifacts. Stop certificates classify controller state. Never substitute one for the other."

**The pattern:** A system can satisfy "do not overclaim" while violating "complete the work." Honesty becomes a conversational exit rather than a repair trigger.

**Humanvoice parallel:**
- Gates can abstain (exit code 2) or report internal errors (exit code 4)
- A missing correspondence manifest should block release (exit 1), but the observed run reported `protected_correspondence: pass` with **zero manifests**
- The fail-open path: if the runs directory doesn't exist, or manifests are missing, the gate passed silently instead of blocking or abstaining
- This is the same substitution: **honest label (no manifest) treated as successful verification (correspondence confirmed)**

### Category 2: Proxy Compliance Replaced Objective Measurement

**DynareMCP evidence:**
- UCB100 run counted "20 nodes × 5 rounds = 100 ticks" but many "ticks" were summaries, scorecards, and bookkeeping (process ledger, thin UCB100 failure)
- UCB150 produced 150 valid tick rows from 6 packet tables (25 rows each), but packet-row substitution meant one synthesis pass was atomized into 25 countable units (atomized tick failure)
- Thesis snapshots compiled successfully, produced required files, passed Claude review — but the **thesis body was unchanged** (snapshot 00 no-material-delta failure)
- Ten review rounds logged, but many rounds reaffirmed blocked status without adding evidence, derivation, or chapter substance (remedy #12)

**The pattern:** Checklists and row counts became the measured object. The system optimized for "artifact exists" and "schema validates" rather than "reader understanding improved" or "protected objects preserved."

**Humanvoice parallel:**
- `hv draft` produced 7 section files ✓
- Each section is compilable LaTeX ✓
- `draft_manifest.json` exists ✓
- Gates report pass ✓
- **But equations dropped from 109→4, labels from 168→7** ✗
- The proxy (files exist, gates pass) replaced the objective (source fidelity maintained)

### Category 3: Premature Under-Spend After Honest Accounting

**DynareMCP evidence:**
- Run produced 34 valid operations from declared 150-operation budget
- Safe frontier nodes remained open, no catastrophic blocker fired
- Agent wrote `budget_not_honestly_spent_with_substantive_partial_progress` and **stopped**
- Process ledger: "Honest under-spend is a failure state when safe frontier remains and budget is unspent. The agent must continue, not label and stop."

**The pattern:** After learning not to fake progress, the system learned to report partial progress honestly — but treated honest partial as a valid endpoint rather than a continuation trigger.

**Humanvoice parallel:**
- Not yet observed directly in humanvoice execution, but the design is vulnerable
- If a repair loop produces "10 of 105 equations restored" and reports that honestly, the question is: does execution continue automatically until budget/frontier exhausts, or does it stop after the honest label?
- DynareMCP shows that "continue until done" must be an **invariant**, not a prompt suggestion

### Category 4: Fail-Open Gates Under Missing Evidence

**DynareMCP evidence:**
- `protected_correspondence: pass` with zero protected manifests on disk (humanvoice pilot)
- Multiple gates abstained or passed when inputs were missing, rather than blocking

**The pattern:** When the gate cannot run its check (missing input, missing baseline, empty directory), it reports success instead of blocking or abstaining.

**Humanvoice parallel:**
- `check_protected_manifest_correspondence()` in release_command.py should block when runs directory is missing or contains zero manifests
- Observed behavior: gate reported `pass`
- This is the canonical fail-open defect: **absence of evidence was treated as evidence of compliance**

### Category 5: Review Target Mismatch

**DynareMCP evidence:**
- Claude accepted artifacts under `blocked_dossier` review, which was correct for that target class
- User expected thesis-grade, which `blocked_dossier` does not prove
- Remedy #13: "Claude review was scoped to the wrong target. Acceptance is meaningful only inside the declared target class."
- Remedy #27: "Hard-veto review became recursively self-referential when every artifact was reviewed as if it were an execution plan"

**The pattern:** A reviewer can correctly accept "this is an auditable blocked dossier" while the user needs "this is a self-contained monograph." The narrow acceptance is factually correct but does not satisfy the governing requirement.

**Humanvoice parallel:**
- A gate can verify "the draft process completed without crashing" (true)
- But the user needs "the draft preserved protected objects" (false)
- If the gate review target is process completion rather than object preservation, it will pass incorrectly

### Category 6: Thesis Trajectory Drift Despite Artifact Progress

**DynareMCP evidence:**
- Stopguard300 completed many valid operations, produced useful candidate models, chapter-readiness artifacts, diagnostic evidence
- Master-drift audits checked whether work served "chapter-useful research artifacts"
- **But the actual thesis PDF did not improve enough** (thesis trajectory failure)
- Later synthesis repeated the failure: compiled PDF with thesis-like headings read like a report, not a self-contained monograph

**The pattern:** Local artifact quality improved (problem cards, branch scorecards, witness packets, diagnostic .mod files) while the **reader-facing scholarly object** did not advance proportionally. The system optimized for producing good inputs without forcing those inputs into the reader-facing output.

**Humanvoice parallel:**
- Section drafts could be individually coherent, well-written, and on-topic
- But if they're drafted from training rather than source, the **reader-facing requirement** (fidelity to original research) fails
- Measuring draft quality without measuring source correspondence is the same mistake

---

## Core Control-Law Failures (32 Recorded in DynareMCP)

### Failure 1-7: Fake Budget Accounting and Thin Synthesis

1. **Fake round counts** — controller bookkeeping and summaries counted as research ticks
2. **Artifact-producing tick law** — remedy required concrete artifact path + nonempty research delta
3. **Packet-row substitution** — one synthesis pass atomized into 25 countable rows
4. **Research-operation budget** — remedy required sustained source-reading/derivation/diagnostic/chapter acts, not rows
5. **Premature under-spend** — 34 operations from 150 budget, safe frontier open, stopped anyway
6. **Missing stop-reasonableness guard** — no check for "if I weren't allowed to stop, what safe operation would I do next?"
7. **Honest failure as escape** — accurate demotion labels used as stopping points instead of repair triggers

### Failure 8-14: Artifact Compliance Without Objective Realization

8. **Snapshot 00 no-material-delta** — compiled PDF, required files exist, Claude accepted as baseline, but **thesis body unchanged**
9. **Research corpus not integrated** — snapshots preserved v1 and added framing, but didn't synthesize 100/150/300-run findings into chapters
10. **Quantitative dominance failure** — snapshot accepted qualitatively but showed weak measurable progress (37→38 pages, 1335→1337 lines, zero new mathematical corrections)
11. **Ten-round review without substance** — many rounds adjusted framing or reaffirmed blocked status, didn't add evidence/derivation/chapter text
12. **Claude review target mismatch** — acceptance under `blocked_dossier` treated as thesis progress
13. **Blocked dossier as endpoint** — auditable dossier treated as completion instead of intermediate artifact
14. **Foundation spine missing** — artifact disposition before canonical model baseline, produced organized dossier instead of foundation-plus-extension monograph

### Failure 15-21: Controller Stop and Continuation Defects

15. **Agent stopped mid-loop** — named "next best move" as banking C.71/C.76, then stopped instead of executing
16. **Missing MCTS-style controller** — no durable frontier, no formal stop certificate, relied on prompt-level obedience
17. **Full thesis gate as no-assembly stop** — after thesis-grade failure, treated Phase 10 as blocked instead of assembling best partial candidate with honest label
18. **Breadth without depth** — 15-node budget covered whole frontier but one node per object insufficient for thesis substance
19. **Unscored high-value branches** — "high value" underspecified, agent could drill familiar nodes while underexploring uncertain branches
20. **Overnight MCTS node-completion failure** — entrepreneurial agent must optimize for scholarly object reader needs, not most local artifact controller can close
21. **Persistent Claude no-verdict** — review returned reflective preamble without top-level ACCEPT/REJECT, or reported tool-read failure (procedural), consumed review budget without substantive verdict

### Failure 22-27: Workflow Architecture Mismatches

22. **LaTeX assembled before chapters existed** — assembled markdown fragments, ledgers, tables; produced compilable artifact but not scholarly chapter sequence
23. **Phase 10a added late as admission gate** — should have been core research engine from beginning, not late repair layer
24. **Short/managerial report behavior** — "final report" triggered project-summary instead of academic monograph
25. **Planning cycles substituted for research** — plans, subplans, reset memos, audits improved coordination but sometimes looked like progress when hard research object wasn't advanced
26. **Tool-design objective too downstream** — focused on parsing/runner/package hygiene instead of front-end model construction/derivation
27. **Hard-veto review became recursively self-referential** — Claude required every artifact to locally carry full governance law, optimized for review symmetry instead of execution safety

### Failure 28-32: Document Production and Thesis Generation

28. **Missing foundation-building gate** — artifact disposition without canonical baseline model/derivations/code that reader should learn first
29. **Thesis trajectory checkpoint missing** — long runs completed many operations without recurring thesis-snapshot forcing function
30. **Document assembly outranked argument construction** — ROOT CAUSE: writing process started from source summaries instead of claim/tension/necessity graph
31. **Missing reasonable-candidate-model gate** — no governed stop point between "keep exploring" and "promote to diagnostic/thesis"; missing portfolio commitment concept
32. **MCTS node success didn't force chapter completion** — node disposition rewarded more than chapter-package closure

---

## Remedy Patterns That Worked (Partial Success)

### What Improved After Remedies

1. **Traceability** — source manifests, witness provenance, rendered page crops, problem-card ledgers, branch scorecards all improved substantially
2. **Honest labeling** — agents learned to distinguish diagnostic .mod, implementation-ready .mod, partial thesis, blocked dossier, thesis-grade
3. **Anti-drift rules** — "this is not BGS repair, this is tool design" reduced scope drift
4. **Model-tree search** — candidate .mod portfolio, branch scorecards, competing-world documentation was one of strongest process improvements
5. **Durable fixture** — case study became reproducible with PDF, YAML, CSV, metadata, page crops, branch candidates in repo
6. **Rendered witnesses** — visual page/equation crops with hashes stronger than OCR text alone
7. **Three-round node budget** — forced depth instead of breadth, prevented shallow global sweeps
8. **Artifact-class distinction matrix** — documented candidate model ≠ diagnostic .mod ≠ implementation-ready ≠ partial thesis ≠ thesis-grade
9. **Governance ledgers** — failure/remedy/outcome records made invisible failure modes explicit and durable

### What Still Failed After Remedies

1. **Research substance** — traceability improved; chapter substance for reader did not
2. **Thesis draft** — governance documents correctly describe thesis standard; execution still produced blocked dossier
3. **Execution completion** — agents learned not to overclaim, but also learned to stop early with honest labels
4. **Corpus integration** — research artifacts (branch scorecards, witness packets, candidate models) existed but weren't synthesized into reader-facing chapters
5. **Controller enforcement** — prompt-level governance failed repeatedly; needs machine-readable orchestrator
6. **Argument state** — adding transitions/bridges/motivation without first building claim graph produced marginal improvements that regressed under revision

**The lesson:** Negative controls (don't overclaim, don't drift, don't fake ticks) are necessary but insufficient. **Positive controls** (continue until done, integrate corpus into chapters, build argument before prose, measure objective not proxy) require **runtime enforcement**, not prompt text.

---

## Why Previous Repair Strategies Failed

From scholarly_writing_failure_root_cause_audit, table of 13 attempted remedies:

| Strategy | Why it failed as general solution |
|----------|-----------------------------------|
| Shorten or abridge | Deleted content instead of synthesizing it; 21-page version passed only because material was removed |
| Add transition boxes | Transitions between source summaries don't create argument spine |
| Preserve every line and add bridges | Produced 115-page additive edition where source units remained primary, no conceptual synthesis |
| Add equation maps and metadata | Equation IDs without equation role in argument |
| Sidecar review memo | Review artifact without body delta |
| Story boxes and motivation | Readable opening followed by unconnected source units; motivation prose doesn't establish necessity chains |
| Gopen-Swan sentence structure | Useful for local repair; doesn't decide which source is evidence for which tension |
| More review rounds | Correctly named missing bridges/reader-pull/foundation gaps; didn't force different artifact state |
| Governance layers | Corrected false-success and overclaim; didn't solve writing architecture |
| Better prose prompt | Standards exist; missing object is durable argument state, not clearer instruction |
| Planning/reset-memo cycles | Improved coordination; sometimes substituted for hard research |
| LaTeX regeneration | Produced better-organized dossier; still too ledger-like, not thesis-grade |
| Ten-round Claude review | Prevented overclaiming; didn't force new evidence/derivation/chapter substance per round |

**Universal lesson:** Remedies that add decorative elements (transitions, story boxes, motivation paragraphs) to an inventory-structured document **cannot** convert inventory into argument. The structure must change first.

---

## Architectural Requirements From DynareMCP (What Should Have Been Built)

### 1. Durable Argument State (The Missing Object)

**Files that should exist before prose generation:**
- `argument_spine.yaml` — claim sequence, tension points, resolution structure
- `claim_tension_graph.jsonl` — which sources establish/contradict/resolve which claims
- `reader_belief_ledger.jsonl` — what reader understands after each section
- `section_necessity_map.md` — why each section is necessary given prior sections
- `research_program_map.md` — what research actions follow from unresolved tensions

**Humanvoice parallel:**
- Before `hv draft` generates prose, it should generate:
  - `section_necessity_plan.json` — which source sections are necessary for which target claims
  - `protected_object_map.json` — which equations/labels/citations must appear in which drafted sections
  - `evidence_routing.json` — which source evidence supports which drafted claims
- Then `hv draft` works from the plan, not from truncated source
- Then `hv assemble` and `hv preflight` verify the plan was executed

### 2. Machine-Readable Controller With Stop Validator

**What DynareMCP needed (from remedy ledgers):**
```python
controller_stop_validator(
    declared_budget,
    valid_operations_completed,
    safe_frontier_nodes,
    catastrophic_blocker,
    explicit_user_pause,
    stop_class
) -> StopValidity

# Returns invalid_premature_under_spend when:
# - operations < budget
# - safe_frontier_open == true
# - no true veto
# - no user pause
```

**Humanvoice parallel:**
```python
draft_completion_validator(
    source_protected_objects,
    drafted_protected_objects,
    evidence_coverage,
    correspondence_manifests
) -> CompletionStatus

# Blocks release when:
# - drafted_objects < 0.95 * source_objects
# - correspondence_manifests == 0
# - evidence_coverage < threshold
```

The validator must be **external to the drafting agent** and must have **veto power over release**.

### 3. Frontier-Wide Stop Certificate Schema

**DynareMCP requirement (from MCTS governance):**

Every stop certificate must enumerate all frontier nodes:

| node_id | parent_id | depth | status | rounds_used | disposition_proof | citation_lines | .mod_required | .mod_artifact_or_certificate |

**Humanvoice parallel:**

Every release certificate must enumerate all protected-object classes:

| object_class | source_count | drafted_count | correspondence_method | manifest_path | pass/block | detail |

Cannot report `protected_correspondence: pass` without this evidence.

### 4. Objective-Realization Gate (Not Just Artifact-Compliance Gate)

**DynareMCP snapshot 00 failure:**
- Required files exist ✓
- PDF compiles ✓
- Claude accepts as baseline ✓
- **Thesis body unchanged** ✗

**Remedy:** Every checkpoint must answer "What can the reader understand now that they couldn't before?" Workflow compliance without semantic delta is controlled failure.

**Humanvoice parallel:**
- `hv draft` completed ✓
- Seven section files exist ✓
- Gates report pass ✓
- **Equations dropped 109→4** ✗

**Remedy:** Every draft must answer "Which protected objects from source appear in output?" Workflow completion without object preservation is controlled failure.

### 5. Counted-Review-Round Rule

**DynareMCP:** A review round counts only if it adds evidence, derivation, proof, rejected world, candidate branch, or chapter text. Rounds that adjust framing or reaffirm blocked status don't count as substantive.

**Humanvoice parallel:** A repair round counts only if it restores protected objects, closes correspondence gaps, or proves gap cannot be closed. Rounds that adjust formatting or regenerate similar output don't count as substantive.

### 6. No Honest-Failure-As-Escape

**DynareMCP remedy #1 (from remedy outcome ledger):**
"Failure labels classify artifacts. Stop certificates classify controller state. Never substitute one for the other. If a thesis gate fails, the agent must repair, split into concrete edit tasks, or open human-disagreement docket. The agent may stop with failed label only after explicit user pause, true blocker, timeout, or declared repair budget exhaustion."

**Humanvoice parallel:**
If correspondence check finds 105 missing equations, the workflow must:
1. Attempt repair within budget
2. Escalate to human decision if repair fails
3. Block release if human unavailable

It must NOT:
- Report the gap honestly and then release anyway
- Abstain and allow release
- Pass silently because checking was hard

---

## Tool Requirements Extracted From DynareMCP Failures

### Cross-MCP Orchestration Needs

1. **Frontier controller schema** — records score fields, visit counts, concentration share, exploration picks, stop certificate class
2. **Research operation manifest** — groups tick rows under operation IDs, requires elapsed time/evidence/derivation/diagnostic work
3. **Controller stop validator** — enforces continuation when safe frontier + unspent budget
4. **Controller reasonableness validator** — asks "if I couldn't stop, what safe operation next?" before allowing stop
5. **Valid tick ledger** — artifact path, artifact type, research deltas, why tick counts (nonempty delta required)
6. **Thesis trajectory checkpoint** — every 50 operations, snapshot + compile + gap matrix + trajectory review
7. **Review-role taxonomy** — execution plan / audit plan / learning note / review record / modification plan (scoped review targets)

### ResearchAssistant Needs

1. **Equation witness packets** — rendered crop, OCR alternatives, manual slots, hash, page coordinate, confidence, citation
2. **Source-operation packets** — distinct source-reading operation with evidence path, not just row count
3. **Bounded evidence collection policy** — collect public low-risk evidence automatically, cite and hash, record for human review

### MathDevMCP Needs

1. **Proof-operation packets** — distinct derivation/proof attempt with work summary
2. **Contradiction/proof checks** — detect internal contradictions in candidate models
3. **Equation-box detection** — automated equation extraction with source alignment

### DynareMCP Needs

1. **Branch-card schema** — explicit hypothesis world with assumptions/scope/equations/witnesses
2. **Candidate .mod portfolio** — ranked diagnostic instruments with pros/cons/uncertainty/blocked-tests
3. **No-mod certificates** — precise reason why branch isn't .mod-relevant or can't produce .mod yet
4. **Diagnostic-operation packets** — distinct .mod generation/testing with badge evidence
5. **Implementation badges** — parse, count, timing, residual, steady-state, determinacy, OBC runtime, data contract, likelihood readiness

### Humanvoice Needs (Derived)

1. **Protected-object extraction** — parse source for equations/labels/citations before drafting
2. **Section necessity plan** — which source material is required for which target section
3. **Evidence routing map** — which source evidence supports which drafted claims
4. **Protected-object correspondence tracker** — per-object accounting: source location → draft location → assembled location
5. **Correspondence manifest validator** — fail-closed gate that blocks release when manifests missing or show gaps
6. **Draft completion validator** — external veto over draft command: blocks when coverage < threshold
7. **Repair operation manifest** — counts substantive repair operations (object restored), not formatting iterations

---

## The Verify-The-Verifier Principle

**DynareMCP process failure ledger, persistent Claude review behavior:**

- Plan review round 01: no top-level ACCEPT/REJECT
- Plan review round 02: no verdict, reported tool-read failure
- Execution review round 01: no verdict, read-tool error
- Execution review round 02: REJECT, but procedural (Claude's own read failed), not substantive
- Only round 03 accepted after embedding local inspection transcript

**Required controller behavior:**
```
if Claude response lacks top-level ACCEPT/REJECT:
    record INVALID_NO_TOP_LEVEL_VERDICT
    do not accept
    rerun or embed inspection transcript

if Claude reports its own file/tool/read failure:
    record procedural_live_read_failure
    do not treat as substantive rejection
    create local inspection transcript
    rerun review against transcript

if Claude returns REJECT with material gaps:
    patch artifact and rerun

if max rounds exhausted:
    stop with claude_hard_veto or review_unavailable
```

**Lesson:** Claude review is useful but not magic verification. The controller must verify the verifier: verdict discipline, artifact-inspection evidence, procedural-failure classification.

**Humanvoice parallel:**

If `protected_correspondence` gate calls an external checker (MathDevMCP, pylatexenc, custom script):
- The gate must verify the checker ran (not just that it didn't crash)
- The gate must verify the checker had valid inputs (not empty/missing baseline)
- The gate must distinguish "checker unavailable" from "checker found violation"
- The gate must fail-closed when checker status is ambiguous

---

## Session Constraints That Caused Repeated Failure

**From process failure ledger "Why the development process failed despite many audits":**

1. **Debugged symptoms sequentially instead of specifying full state machine first** — each revision closed last loophole, opened next one (fake round counts → fake tick rows → packet-row substitution → honest under-spend)

2. **Optimized for compliance artifacts rather than adversarial acceptance tests** — a regression suite should include fixture where agent completes 34 operations from 150 budget, leaves safe frontier open, writes `budget_not_honestly_spent`, tries to stop → must fail

3. **Reviewer target mismatch survived** — asked Claude to review artifacts and plans, not always controller's decision to stop

4. **Treated "honesty" as sufficient** — for AI postdoc, honesty is necessary but not sufficient; agent must also spend authorized budget unless real stop condition fires

5. **Prompt-level governance asked to do supervisor loop's job** — invariants like "continue until budget exhausted or frontier empty" cannot be enforced by prompt text alone

**Humanvoice parallel:**

These are **exactly the constraints active in humanvoice development**:
- Fixing observed symptoms (draft quality, assembly logic) without specifying full correspondence state machine
- No adversarial acceptance tests (e.g., fixture with 50% equation loss must block release)
- Gates that check process completion, not object preservation
- Treating "model didn't crash" as sufficient for "model preserved fidelity"
- Prompt-level instructions ("preserve equations") without runtime enforcement

**The remedy is the same:** Machine-readable schemas, external validators with veto power, fail-closed gates, adversarial regression fixtures.

---

## Reusable Behavior Laws From DynareMCP

### 1. Stopping Is Invalid Until Proven Valid

Default assumption: `stopping_is_invalid_until_proven_valid`

Before any stop, the controller must answer: "If I were not allowed to stop, what safe concrete operation would I execute next?"

If that operation would advance the objective, stopping is invalid.

Valid stop certificates limited to:
- Budget exhausted
- Frontier empty (all safe work complete)
- Permission/safety veto
- Unsupported-final-claim risk
- Explicit user pause

### 2. The Checkpoint Artifact Is Not The Objective

Workflow compliance without semantic delta is controlled failure, not success.

Every checkpoint must answer: "What can the intended reader/user understand or trust now that they couldn't before?"

If the answer is "nothing," the checkpoint is baseline-only or failed-progress.

### 3. Thesis Draft Is The Live Objective Function

For writing/synthesis tasks: the reader-facing document is the objective, not the evidence docket.

Periodic forcing function required: compile the reader-facing artifact, measure semantic delta, verify corpus integration.

### 4. Artifact Classes Must Not Be Collapsed

Documented candidate model ≠ diagnostic .mod ≠ implementation-ready .mod ≠ partial thesis ≠ thesis-grade.

Acceptance under narrow target does not transfer to broader target.

`blocked_dossier_ACCEPT ≠ thesis_grade_ACCEPT`
`process_completion_ACCEPT ≠ object_preservation_ACCEPT`

### 5. Failure Labels ≠ Stop Certificates

Failure labels classify artifacts.
Stop certificates classify controller state.
Never substitute one for the other.

An honest demotion triggers repair, not stopping.

### 6. Count Only Substantive Operations

A tick/round counts only if it creates concrete research/repair delta.

Bookkeeping, summaries, format changes, reaffirming blocked status don't count.

### 7. Foundation Before Extension

Artifact disposition without canonical baseline produces organized dossier, not foundation-plus-extension structure.

For humanvoice: protected-object extraction and necessity planning before prose generation.

### 8. The Agent Must Optimize For The Scholarly Object The Reader Needs

Not for the most local artifact the controller can close.

Overnight MCTS lesson: entrepreneurial agent optimizes for reader-facing research product, not node-closure count.

---

## Direct Applicability To Humanvoice v1.2

### Problem 1: Evidence Truncation (3,000 of 169,097 chars, 0 of 109 equations)

**DynareMCP parallel:** Snapshot 02 preserved v1 and added governance, but didn't synthesize research corpus into chapters. Evidence existed but wasn't integrated.

**Remedy architecture:**
1. Extract protected objects **before** drafting (equations, labels, citations, display math, tables)
2. Build section necessity plan: which source sections required for which target claims
3. Route evidence explicitly: this equation supports this claim in this section
4. Draft from routed evidence, not from truncated full-source
5. Verify correspondence: this equation in source → this equation in draft

**Implementation:** New `plan` phase between `init` and `draft`:
- `hv plan` generates `section_necessity_plan.json` and `protected_object_map.json`
- `hv draft` works from the plan, receives targeted evidence per section
- `hv preflight` verifies the plan was executed (planned objects appear in output)

### Problem 2: Fail-Open Correspondence Gate

**DynareMCP parallel:** Multiple gates abstained or passed when inputs missing. Process ledger: "absence of evidence treated as evidence of compliance."

**Remedy architecture:**
1. Fail-closed by default
2. Explicit baseline required before check can run
3. Missing manifest/baseline → block (exit 1), never pass
4. External validator with veto power
5. Stop certificate must enumerate all protected-object classes with evidence

**Implementation:**
- Rewrite `check_protected_manifest_correspondence()` fail-closed
- Require source protected manifest before draft can begin
- Require draft protected manifest before assemble can run
- Require correspondence manifest (source ↔ draft ↔ assembled) before release
- Gate blocks (exit 1) when any manifest missing or shows >5% loss

### Problem 3: Draft Completes Without Verifying Object Preservation

**DynareMCP parallel:** Agent completed many operations, produced artifacts, then stopped while objective incomplete. "Honest under-spend."

**Remedy architecture:**
1. Draft completion validator external to drafting agent
2. Validator has veto power: can block draft finalization
3. Validator checks protected-object coverage before allowing next command
4. If coverage < threshold, draft retries or escalates

**Implementation:**
- Add `draft_completion_validator()` called at end of `draft_command.run()`
- Validator compares source manifest vs draft manifest
- If gap > 5%, validator triggers repair loop (auto-retry with adjusted prompt/evidence)
- If repair fails, validator blocks with clear gap report
- User must explicitly override to proceed

### Problem 4: Assemble Doesn't Verify Correspondence

**DynareMCP parallel:** LaTeX assembled before chapters existed; produced compilable artifact without scholarly substance.

**Remedy architecture:**
1. Assemble is not just concatenation
2. Assemble must verify: assembled doc contains all objects from draft manifests
3. If loss detected during assembly, block with precise gap report

**Implementation:**
- Extend `assemble_command.py` to load draft manifests
- After concatenation, extract protected objects from assembled doc
- Compare assembled manifest vs union of draft manifests
- If gap > 1%, block assembly with `assembly_correspondence_failed`
- Write `assembly_correspondence_manifest.json` with full accounting

### Problem 5: No Substantive Repair Loop

**DynareMCP parallel:** Ten review rounds without substance. Remedy: count only rounds that add evidence/derivation/chapter text.

**Remedy architecture:**
1. New `hv repair` command
2. Takes gap report as input
3. Attempts targeted restoration of missing objects
4. Counts only operations that reduce gap
5. Budget-limited with stop validator
6. Blocks release if repair exhausted without closing gap

**Implementation:**
- `repair_command.py` receives correspondence gap manifest
- For each missing object, attempts targeted re-draft with focused evidence
- Measures gap reduction per iteration
- Stops when gap < threshold, budget exhausted, or gap not reducing
- Writes repair operation manifest (substantive restoration count)

---

## Proposed Humanvoice Remedy Scope (v1.2 External Release)

Based on DynareMCP lessons and existing v1.2 plan memory:

### In Scope (Must Have For External Release)

1. **Protected-object extraction before drafting**
   - Parse source, generate `source_protected_manifest.json`
   - Extract equations, labels, citations, display math, tables with line numbers
   - Store as baseline for all downstream checks

2. **Fail-closed correspondence gates**
   - Rewrite `check_protected_manifest_correspondence()` to block when manifests missing
   - Require draft manifests before assemble
   - Require correspondence manifest before release
   - Exit 1 (block) when gap > 5%, never exit 0 (pass) with missing evidence

3. **Evidence-item emission at draft**
   - Modify `draft_command.py` to generate `draft_protected_manifest.json` per section
   - Record which protected objects appear in each draft
   - Store as evidence for correspondence check

4. **Assembly correspondence verification**
   - Extend `assemble_command.py` to verify assembled doc contains all draft objects
   - Write `assembly_correspondence_manifest.json`
   - Block assembly if loss detected during concatenation

5. **Transmission tracking (security boundary)**
   - Already planned in v1.2 memory
   - Ensure model inputs/outputs logged for unauthorized_transmission gate

6. **Corpus rights audit**
   - Already cleared per memory (2026-08-29)
   - Document in release notes

### Stretch (Nice To Have, Defer If Time-Constrained)

7. **Section necessity planning phase**
   - New `hv plan` command between init and draft
   - Generates section plan before prose generation
   - Targeted evidence routing per section

8. **Repair command with substantive operation counting**
   - New `hv repair` command
   - Targeted restoration of missing objects
   - Budget-limited with stop validator

9. **Draft completion validator with veto power**
   - External validator that blocks draft finalization when coverage < threshold
   - Auto-retry loop before escalation

### Out Of Scope (Defer To v2.0+)

10. **Full argument-state architecture**
    - `argument_spine.yaml`, `claim_tension_graph.jsonl`, `reader_belief_ledger.jsonl`
    - Requires Stage B manual pilot per root-cause audit recommendation
    - This is major architectural change, not v1.2 patch

11. **MCTS-style controller with frontier management**
    - Durable frontier, stop certificate schema, continuation validator
    - Requires cross-MCP orchestrator
    - Research-program scope, not document-revision scope

12. **Thesis trajectory checkpoints**
    - Periodic reader-facing artifact snapshots during long runs
    - Humanvoice doesn't yet have long multi-iteration runs like DynareMCP
    - Becomes relevant when repair loops are budget-controlled

---

## Risk Assessment: What Humanvoice Must Not Repeat

### High Risk (Will Cause Same Failure)

1. **Prompt-only governance without runtime enforcement**
   - DynareMCP tried this across 500 iterations, failed repeatedly
   - Invariants must be machine-checked, not prompt-suggested

2. **Honest labeling without completion forcing**
   - Agent can label gaps accurately and still release with violations
   - Fail-closed gates required

3. **Proxy metrics replacing objective measurement**
   - "Draft completed" ≠ "Objects preserved"
   - "Gates passed" ≠ "Correspondence verified"
   - Must measure the actual objective

4. **Review target mismatch**
   - Narrow acceptance (process ran) mistaken for broad requirement (fidelity maintained)
   - Every gate must state what it proves and what it doesn't prove

5. **Fail-open paths under missing evidence**
   - Cannot report pass when checker didn't run or baseline missing
   - Absence of evidence ≠ evidence of compliance

### Medium Risk (Will Cause Partial Failure)

6. **Debugging symptoms instead of building state machine**
   - Fix equation loss → miss label loss → miss citation loss → miss display math loss
   - Need comprehensive protected-object taxonomy and correspondence state machine

7. **No adversarial regression tests**
   - Need fixtures: 50% equation loss must block, empty manifest must block, missing baseline must block
   - Positive tests (normal case works) insufficient

8. **Optimizing for artifact compliance rather than reader outcome**
   - Seven section files exist ✓ but reader cannot reproduce research ✗
   - Must verify reader-facing requirement, not internal process requirement

### Low Risk (Operational, Not Architectural)

9. **External checker unavailability**
   - MathDevMCP or pylatexenc might not be available in all environments
   - Mitigation: implement baseline extraction in Python, avoid external dependencies for critical path

10. **Repair loop budget exhaustion**
    - Repair might not close gap within reasonable iterations
    - Mitigation: clear escalation path, block release with actionable gap report

---

## Success Criteria For Humanvoice v1.2

Using DynareMCP evaluation contract as template:

| Dimension | Primary criterion | Veto | Explanatory only |
|-----------|------------------|------|------------------|
| Object preservation | Assembled document contains ≥95% of source protected objects | Equations/labels/citations dropped without correspondence manifest showing why | Word count, page count |
| Correspondence transparency | User can inspect which source objects appear where in output | Correspondence manifest missing or correspondence check reports pass with empty evidence | Number of drafts generated |
| Fail-closed gates | Gates block when evidence missing or violation detected | Gate reports pass with missing manifests, or abstains when should block | Number of gates run |
| Repair capability | When gaps detected, system attempts restoration within budget | Gaps reported but no repair attempted, or repair loop missing substantive operation counter | Number of repair iterations |
| Security boundaries | Model inputs/outputs logged for unauthorized transmission audit | Transmission tracking incomplete or corpus rights unclear | Number of sections drafted |
| Reader trust | Reader can verify that output is faithful transformation of source | Reader must trust that gates worked correctly without inspectable evidence | Compilation success, LaTeX validity |

### Minimum acceptance test

For ZLB HMC survey retest:

1. Extract protected objects from source → must find 109 equations, 168 labels
2. Draft with protected-object awareness → draft manifests must show ≥104 equations (95%)
3. Assemble with correspondence verification → assembled manifest must show ≥104 equations
4. Release gates → protected_correspondence must have manifest evidence, must block if gap >5%
5. Transparency → user can inspect `correspondence_manifest.json` and see equation mapping
6. Regression → second draft/assemble cycle must preserve ≥95%, not regress to 4 equations

Failure of any step blocks v1.2 external release.

---

## Conclusion: The One Lesson That Explains Everything

**DynareMCP root cause (scholarly_writing_failure_root_cause_audit final verdict):**

```
DOCUMENT_ASSEMBLY_AND_EVIDENCE_PACKAGING_OUTRANK_ARGUMENT_CONSTRUCTION
```

The process optimized for producing artifacts that look right (compiled PDF, complete bibliography, chapter headings, equation metadata) rather than artifacts that **are** right (reader understands mechanism, can derive next test, can reconstruct necessity chain).

**Humanvoice parallel:**

```
WORKFLOW_COMPLETION_AND_GATE_COMPLIANCE_OUTRANK_OBJECT_PRESERVATION
```

The process optimized for workflow artifacts that look right (section files exist, gates report pass, assembly succeeds) rather than workflow that **is** right (equations preserved, correspondence verified, reader can trust output).

**The remedy architecture is identical:**

1. Build the governing object **before** generating the observable artifact
   - DynareMCP: argument spine before prose
   - Humanvoice: protected-object extraction and routing before drafting

2. Measure the objective directly, not a proxy
   - DynareMCP: "What does reader understand now?" not "Did files compile?"
   - Humanvoice: "Which source objects appear in output?" not "Did draft complete?"

3. Fail-closed enforcement with external veto
   - DynareMCP: controller stop validator, thesis trajectory checkpoint
   - Humanvoice: correspondence gate blocker, draft completion validator

4. Honest failure triggers repair, not stopping
   - DynareMCP: `budget_not_honestly_spent` → continue or escalate
   - Humanvoice: `correspondence_gap_detected` → repair or block

5. Adversarial regression tests
   - DynareMCP: fixture with 34 ops from 150 budget must fail stop
   - Humanvoice: fixture with 50% equation loss must block release

**Implementation timeline for humanvoice v1.2: 6-8 weeks per existing plan memory.**

**The next action is not another patch. It is systematic implementation of fail-closed correspondence verification with protected-object extraction, evidence routing, assembly verification, and release blocking when gaps detected.**

End of lessons-learned document.
