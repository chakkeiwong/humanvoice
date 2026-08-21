# humanvoice

Teaching agents to write documents a human will actually read.

This repository consolidates the workspace's scattered efforts on human-facing
scientific writing (claudecodex policies and skills, the DynareMCP/AIpostdoc
record, the BayesFilter, MacroFinance, cardnpv, and SMEwallet documentation
histories, ResearchAssistant, MathDevMCP) and hosts the tooling those efforts
showed was missing.

## Start here

`docs/survey/humanvoice_survey.pdf` — the founding document (40 pages,
revised 22 August 2026 after the sixteen-page first version was rejected for
density; the rejection itself became evidence, see its Section 1.2). It
contains:

1. The failure record across five projects, told in sequence with real
   before/after repair examples and a defect taxonomy (Section 2).
2. A review of each existing tool with merits and issues (Section 3).
3. The research literature explained at method level, with the formulas a
   builder needs (Section 4).
4. Detailed reviews of fourteen open-source projects, including a
   calibration experiment run on our own documents (Section 5; verdicts in
   Table 4). Evaluated code is pinned under `vendor/` (see
   `vendor/MANIFEST.md` for commits).
5. Design requirements traced to evidence (Section 6, Table 5) and the
   proposal: the `hv` diagnostic CLI specified per command, and work
   packages WP1-WP5 with replay-based acceptance tests (Section 7).

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
