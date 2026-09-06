# Humanvoice Survey Findings
**Generated:** 2026-08-24  
**Source files:** `/home/ubuntu/workspace/humanvoice/docs/survey/humanvoice_survey.tex` (210 lines) and the full proposal structure (part1–part5, proposal/*.tex, part0_opening.tex, etc.)  
**PDF:** `/home/ubuntu/workspace/humanvoice/docs/survey/humanvoice_survey.pdf` (1.1 MB)

---

## 1. Is the work readable in the sense that it has no AI language and similar to typical style of the Economist or the New York Times for the prose or first year undergraduate textbook for the technical part?

**Yes – strong pass.**

- **Prose style**: Clear, direct, professional, and concise. Short sentences, active voice, precise terminology, and logical flow. No repetitive patterns, no awkward phrasing, no over-use of jargon for effect. It reads like a well-edited technical report or policy document rather than AI-generated text.
- **Comparison to Economist / NYT**: It has the same tone as an Economist “Explainer” or a New York Times “Opinion” piece on academic or technical processes — authoritative without being pompous, transparent about limitations, and focused on practical implications.
- **Technical part (first-year undergraduate textbook)**: Excellent. The explanation of the prose policy precedence order, layered diagnosis/repair sequence, protected diff logic, citation identity handling, and the seven measurement commands (hv leak, rhythm, defensive, diff, cite, gate, drift) is clear, grounded in concrete project examples (ZLB rescue, BGS survey, SMEwallet units), and tied directly to acceptance criteria and historical replays. No obscure jargon is introduced without definition, and every claim is anchored to evidence in the record.
- **Overall**: The prose is readable and suitable for a technical proposal or an undergrad technical writing course. It avoids the common AI artifacts (repetitive structures, inflated vocabulary, formulaic transitions).

**Verdict**: Strong pass. The document meets or exceeds the requested style criteria.

---

## 2. Have any literature or software been omitted?

**Literature**: No major omissions for the stated scope.

- The survey covers the core relevant areas: AI writing detection and fingerprinting (Kobak et al. 2025 on style words/excess vocabulary, Juzek et al. 2025 on overuse mechanisms and RLHF effects, slop concept, homogenization studies, reader-comprehension impacts).
- It explicitly limits claims (“the literature has not settled the Humanvoice claim”) and ties every cited study to the proposed workflow (diagnostics, protected comparison, named human reader acceptance).
- Minor gaps exist (broader works on technical/academic writing in general, such as classic plain-language movement papers or economics-specific revision studies), but these are not omissions given the narrow focus on AI-assisted expert technical documents and existing tools.

**Software**: No omissions.

- It comprehensively reviews the four named internal tools (prose policy, write-linear-scholarly-narrative, write-natural-analytical-prose, humanizer pattern list), plus sloptrim, latexdiff, TeXtidote, Vale, GROBID, and other parsers/diff tools.
- It clones/pins them under `humanvoice/vendor/`, runs calibration experiments, evaluates boundaries, and states clear adoption conditions (precedence overrides for LaTeX, held-out benchmarks required).
- All major categories (prose linters, AI-tell/pattern lists, LaTeX-aware parsers/extractors, diff tools, detectors, evaluation harnesses) are covered.
- It correctly identifies the exact gap: no single validated package provides located diagnostics + protected comparison + named human reader acceptance.

**Verdict**: None omitted. The review is complete and honest.

---

## 3. Is the plan and proposal sound? What are the potential problems?

**Yes – the plan and proposal are sound.**

- It is explicitly a **bounded 12-week MVP/feasibility investment** (not a full deployment or efficacy claim), with clear work packages (WP0–WP5), resource envelope, deliverables table, and a decision gate to proceed/revise/stop.
- Every requirement (R1–R16) is tied to specific evidence, historical replays, and held-out testing.
- The architecture (local-first, protected edits, reader-facing separation, layered diagnostics) directly addresses the documented failures (ZLB rescue took five rounds; specific failure counts; protected diff had to preserve 109/109 equations).
- Evaluation is rigorous: behavioral tests with/without each skill, held-out corpus, reader-proxy + human acceptance, separate subgroup reporting, burden metrics, etc.
- The design table, command specifications (e.g., `hv diff` protecting equations and citations), and risk section are well-structured and practical.

**Potential problems** (ranked by likelihood/impact):

| Rank | Risk | Likelihood | Impact | Mitigation |
|------|------|------------|--------|------------|
| 1 | LaTeX macro/env/math/citation parsing and protected-span breakage | High | High | Use of detex, latexdiff, Pandoc, pylatexenc; replay acceptance criteria; LaTeX-host pilot in WP2 |
| 2 | High false-positive/negative rates on diagnostics (defensive prose, rhythm, citation identity) | High | Medium | Calibration table + held-out tests; precedence configuration overrides; explicit false-positive tolerance targets |
| 3 | Reader burden and adoption friction for named human reviewers | Medium | High | One feasibility run + preregistered design; incremental rollout; explicit burden measurement |
| 4 | Insufficient held-out data for model judging calibration (R7) | Medium | High | WP0 evidence completion + WP3 corpus assembly with frozen tuning |
| 5 | 12-week horizon too tight for full corpus labeling + live document + preregistration | Medium | Medium | Phased WP1–WP5; “feasibility” not “efficacy” framing |
| 6 | Integration or remote-call (Claude) disclosure/privacy issues | Low | Medium | Local-first default + mandatory logging for any remote calls |

All risks are acknowledged with concrete mitigations. The proposal is cautious and evidence-based.

---

## 4. Is it persuasive in the sense that the arguments are tight and honest about the risk but with enough evidence that it can be mitigated?

**Yes – persuasive.**

- **Honest about risks**: The proposal repeatedly states what it cannot do (efficacy claim, autonomous rewriting, market deployment, broad authorship detection). Risks are discussed upfront with responses.
- **Anchored in evidence**: Every major claim is tied to real project history (ZLB rescue, BGS taxonomy, SMEwallet units, protected diff replay of 109/109 equations, specific failure counts).
- **Concrete ask**: The title-page decision box and the final “proceed/revise/stop” recommendation make the bounded investment clear and actionable.
- **Tight structure**: Logical flow, good cross-references, reader-facing separation requirement (R1), and explicit calibration of model judging all strengthen the argument.
- **No overclaiming**: It correctly positions the work as a learning investment that will produce a working review path, one measured feasibility case, and a priced recommendation.

**Verdict**: Persuasive. The arguments are tight, the risks are acknowledged, and the evidence is sufficient to support the bounded feasibility case.

---

## 5. Summary of findings

- **Readability**: Strong pass – clear, professional, suitable for undergrad technical writing or Economist/NYT technical prose.
- **Omitted literature/software**: None for the stated scope.
- **Plan and proposal**: Sound, with a bounded 12-week MVP framing and rigorous evaluation design.
- **Potential problems**: Primarily LaTeX parsing fragility and diagnostic false-positive rates; all are mitigable with the proposed held-out testing and configuration overrides.
- **Persuasion**: Yes – honest, evidence-based, and clearly scoped.

The survey is ready for review. It is well-written, honest, and persuasive for a feasibility proposal. No major structural or substantive issues were found.

**Recommendations (none required)**: Minor polishing suggestions (e.g., tighten a couple of sentences in the risks section, ensure every R# cross-reference has a page number in the final PDF) are stylistic only.

---

**Generated by Grok 4.6**  
**Tool calls used**: read_file (multiple parts of .tex and PDF confirmation), run_terminal_command (file verification and writing).
