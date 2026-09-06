# Codex Audit Reply: DynareMCP Review and Humanvoice v1.2 Remedy Plan

**Date:** 2026-09-01  
**Auditor:** Codex

## Overall Verdict

The lessons document is directionally and technically sound, and the proposed v1.2 work addresses the most clearly demonstrated Humanvoice defect. I recommend proceeding, with the plan treated as an implementation hypothesis rather than a validated solution. The central diagnosis is well supported:

> Workflow and artifact completion were allowed to substitute for realization of the scholarly/document object the user actually needed.

The transfer from DynareMCP thesis production to Humanvoice document drafting is valid at the control-law level, but not as an assertion that the two systems have identical causes or remedies.

## Findings

### 1. Completeness

The 32 failures are a useful taxonomy and the seven architectural requirements cover the main recurring controls: objective/label separation, durable state, substantive operation accounting, valid stop certificates, and fail-closed verification. I would retain the categories.

Two additions should be made explicit rather than counted as new failures:

1. **Measurement validity / verifier independence.** A checker that counts objects but shares the same parser or assumptions as the producer can certify a common blind spot. The proposed “verify the verifier” section recognizes this, but it should be a first-class acceptance requirement.
2. **Provenance and version binding.** A manifest must identify the exact source hash, parser version, prompt/model version, and assembly input hashes. Otherwise a passing correspondence result may describe a different source or run.

The remedy classification is broadly correct. Traceability, rendered witnesses, honest labels, model-tree search, and stricter tick accounting improved observability or local rigor; they did not by themselves create a thesis argument. The ledgers also show an important interaction: honest labels and narrow review scopes reduced overclaiming while simultaneously permitting a procedurally correct endpoint that still failed the user's larger objective.

The “missing object” diagnosis is useful, but the named files should be presented as a minimal logical schema, not four mandatory files. A single versioned claim/necessity graph can subsume the spine, tension edges, reader-state entries, and section dependencies. Humanvoice likewise needs a canonical protected-object and evidence-routing record; it does not necessarily need the exact proposed filenames.

### 2. Correctness of Cited Claims

| Claim | Audit result |
|---|---|
| Trial produced an auditable blocked dossier, not a thesis-grade reconstruction | **Supported** by the final pilot report and process ledger. |
| UCB100 counted 20 nodes x 5 summarized rounds = 100 ticks | **Supported**, and explicitly identified as an accounting failure in the process ledger. |
| UCB150 produced 150 packet rows from six packets | **Supported in the ledger**, but this proves row production, not six independent substantive research operations. |
| A 34-operation run stopped below a 150 budget with an honest label | **Supported in the ledger**; it is correctly characterized as premature under-spend, not successful completion. |
| Snapshot 00 changed only title/date material | **Supported** by the ledger's direct TeX-diff description. |
| Claude reviews returned no-verdict/procedural failures | **Supported**; the ledger distinguishes invalid no-verdict from reviewer tool failure. |
| “~500 iterations across 15 phases” | **Not independently verified here.** Treat as an approximate handoff statistic unless a run manifest is cited. It must not be used as a precise denominator. |

The Humanvoice code claims are accurate with one precision caveat. `draft_command.py:122` slices the evidence to 3,000 characters. `compare.py` contains `normalize_object`, `match_objects`, and `compare_documents`. The command inventory contains `init`, `plan`, `draft`, `assemble`, `preflight`, `repair`, and `release`.

In `release_command.py`, `check_protected_manifest_correspondence()` does not block when runs exist but no matching protected-manifest files are found; it returns `None`. It does block when the canonical runs directory is absent, and it blocks individual unresolved comparisons. Therefore “pass with zero manifests” is an accurate description of the observed fail-open case, but not of every missing-run state.

The ZLB measurements are documented in the defect analysis and repeated consistently in the survey documents: 169,097 source characters, 109 equations, 168 labels, 3,000-character evidence window, 4 equations and 7 labels in the draft, and 6,976 words. They are documentary measurements rather than a currently reproducible benchmark in this checkout; the acceptance fixture should make them executable.

### 3. Interpretation and Transfer

The root-cause interpretation matches the DynareMCP root-cause audit and the Humanvoice defect evidence. The strongest shared abstraction is **proxy-governed production under an under-specified objective**. “Document assembly outranked argument construction” is an appropriate DynareMCP-specific formulation; “workflow completion outranked object preservation” is an appropriate Humanvoice formulation.

The analogy has limits. Thesis quality includes explanatory coherence and reader belief change, while correspondence verification establishes preservation of syntactic/protected objects. Humanvoice's proposed gates can prevent catastrophic loss; they cannot establish that a rewrite is persuasive, correct, or necessary. The release contract must state this non-equivalence plainly.

The explanations for failed remedies are consistent with the ledgers: deletion is not synthesis, transitions do not create an argument, metadata does not explain equation roles, repeated review without required delta is procedural iteration, and LaTeX regeneration changes packaging rather than authorship. Alternative contributors include inadequate source selection, notation/model gaps, and review prompts scoped to a weaker artifact. These are complementary causes, not reasons to discard the diagnosis.

### 4. Remedy Plan Audit

The Phase 0 -> extraction -> routing -> gates -> assembly sequence is sound. Phase 0 must remain first, and the tests should include malformed manifests, duplicate IDs, stale source hashes, parser disagreement, and an adversarial object that looks syntactically valid but is semantically unrelated. Repair may run in parallel with documentation, but release documentation must not declare repair capability until repair is covered by the same mutation tests.

The technical approach is reasonable as a prototype, with these required changes:

- Use a parser bake-off (pylatexenc, unified-latex, and a controlled fallback) and preserve a manual gold inventory. Regex may assist discovery but must not be the sole authority for nested environments, escaped macros, labels in unusual positions, or generated equations.
- Compare stable object identities and normalized bodies, not only counts. A 95% count can hide replacement of the wrong 5%: load-bearing equations and labels need stricter, per-object rules.
- Make thresholds type-specific and configurable in the manifest. A 95% equation threshold and a 99% assembly threshold are reasonable starting points, not universal correctness claims.
- Require explicit dispositions for omitted objects (`not_relevant`, `merged`, `superseded`, or `manual_exception`) with human authorization. Silent omission must always block.
- Bind every manifest to source, blueprint, model, parser, and parent artifact hashes; reject stale manifests.
- Keep `compare.py` as a library only if its normalization/matching semantics are independently tested. Otherwise integrating an untested existing comparator merely moves the blind spot.

The six-to-eight-week estimate is plausible for the correspondence core, not for a proven authoring system. The week-six checkpoint should be a hard go/no-go for the protected-core utility. The plan should explicitly separate two product claims:

1. **Review utility:** reliably preserves and reports protected objects.
2. **Authoring/restructure system:** improves argument, reader comprehension, and section necessity.

Only the first can be accepted by the proposed automated gates. The second requires held-out documents and independent reader review.

## Required Plan Amendments

1. Add a provenance/version-binding requirement to the schemas and gates.
2. Add parser-disagreement and stale-manifest mutation fixtures to Phase 0.
3. Change acceptance reporting from aggregate retention alone to per-object, load-bearing retention.
4. Mark “argument quality” and “reader understanding” as unproven until an independent reader protocol exists.
5. Cite a run manifest or relabel “~500 iterations across 15 phases” as an approximate, unverified statistic.
6. Make rights clearance and fixture reproducibility explicit entry criteria for external benchmarking.
7. Require a human-approved disposition for every omitted protected object; never infer irrelevance from a count threshold.

## Final Assessment

No fundamentally different approach is required for v1.2. The proposed protected-object-first, evidence-routed, fail-closed pipeline is the right narrow intervention. Its success criterion must remain narrow: it can demonstrate correspondence and prevent silent loss, while argument construction and reader outcomes remain separate claims requiring separate evidence.

**Recommendation:** approve the plan after the amendments above; implement Phase 0 and the protected-core path first, and do not label the resulting system an argument-quality or thesis-quality validator.
