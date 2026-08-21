# humanvoice

Teaching agents to write documents a human will actually read.

This repository consolidates the workspace's scattered efforts on human-facing
scientific writing (claudecodex policies and skills, the DynareMCP/AIpostdoc
record, the BayesFilter, MacroFinance, cardnpv, and SMEwallet documentation
histories, ResearchAssistant, MathDevMCP) and hosts the tooling those efforts
showed was missing.

## Start here

`docs/survey/humanvoice_survey.pdf` — the founding document. It contains:

1. The failure record across five projects, read in sequence, with a
   ten-point summary of what the record adds up to (Section 2).
2. An inventory of the tools we already have and the gaps (Section 3).
3. A survey of the research literature on why language models write this
   way and what interventions have evidence (Section 4).
4. An evaluation of fourteen open-source projects, with verdicts (Section 5,
   Table 1). Evaluated code is pinned under `vendor/` (see
   `vendor/MANIFEST.md` for commits).
5. The proposal: eight design principles, the repository shape, the `hv`
   diagnostic CLI, and five work packages WP1-WP5 (Section 6).

Rebuild with `pdflatex + bibtex` from `docs/survey/humanvoice_survey.tex`.

## The one-paragraph version

Agent-written documents fail in layers: internal register hides mechanical
style tells, which hide defensive prose, which hides missing substance; repair
must follow that order. The doctrine for avoiding this exists (the
reader-facing-prose policy, two writing skills, the humanizer pattern list,
all with a fixed precedence: correctness, source fidelity, domain meaning,
reader comprehension, then template regularity). What does not exist is the
measurement layer — register linter, rhythm profiler, defensive-register
finder, LaTeX-aware baseline differ — and the evaluation evidence that any of
the doctrine works. This project builds both, keeps process deliberately thin
(the BGS record shows governance cannot write), and treats the human read as
the only acceptance gate.

## Planned layout

```
policies/     single home for the writing doctrine (WP1)
diagnostics/  the hv CLI: leak, rhythm, defensive, diff, gate, drift (WP2)
corpus/       evaluation assets: BGS repair pairs, ZLB pass snapshots,
              SMEwallet draft units, pre-2022 economics baseline (WP3)
harness/      reader-proxy review templates and behavioral tests (WP3/WP4)
vendor/       pinned external tools with commit manifest (done)
docs/survey/  the founding survey and proposal (done)
```

Non-goal: detector evasion. humanvoice improves prose under disclosure norms
and never optimizes against an AI-text detector.
