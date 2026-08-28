# Review request for Fable: Humanvoice master program v1.1

**Date:** 26 August 2026
**Reviewer requested:** Fable
**Draft under review:** `docs/plans/humanvoice_master_program_v1.1_2026-08-26.md`
**Prior draft:** `docs/plans/humanvoice_master_program_2026-08-26.md`

## Why this revision was made

The v1.0 program had the right product instincts: a protected core before a
model-assisted extension, fail-closed behavior, explicit abstention, typed
protected comparisons, a security veto, and a named human reader. The review
found that it still read as an implementation specification rather than an
executable program. Several planned tests and runners did not exist, some
references were stale, the JSON schemas did not require fields the program
called mandatory, and the twelve-week schedule mixed independent gates with a
single "true gate."

The repository currently reports:

- the contract checker passes;
- 47 existing audit/document tests pass;
- no `hv` package or console entry point exists;
- no `run_fixture_suite.py` or `run_regression_replay.py` exists; and
- six evidence gates remain release-blocked in
  `docs/survey/humanvoice_evidence_status.json`.

Those facts are now stated as starting conditions in v1.1, not treated as
implementation evidence.

## What changed in v1.1

### 1. The plan now starts with an executable vertical slice

WP1 creates `pyproject.toml`, `src/humanvoice/`, `tests/`, `fixtures/`, and a
console entry point. `hv init` and deterministic `hv preflight` must run on one
synthetic fixture before parser work is accepted. Future test names are marked
planned until their source files and reports exist.

### 2. Traceability is made testable

The plan removes dependence on mutable line-number citations and requires
`tools/check_program_consistency.py`. It must verify paths, headings, labels,
schema IDs, R1-R24 coverage, named artifact status, and checkpoint alignment.
This addresses the stale `06_design.tex` and `part5_proposal.tex` references in
v1.0.

### 3. The record inventory is forced to one decision

The proposal currently describes different numbers of records in different
chapters. WP0 now requires `schemas/record_catalog.json`, with an explicit
mapping for document versions, source snapshots, protected spans, reader
decisions, and evidence items. The plan recommends standalone schemas where
lineage requires them, but asks the sponsor to approve the exact mapping before
code begins.

### 4. Schema and contract drift is closed

V1.1 requires instance validation and aligns the schemas with the declared
contract: all eleven runtime-manifest fields, all nine stable CLI fields, and
all eight corpus-rights fields. Unknown top-level fields are rejected except
under `extensions`. A breaking record decision requires a contract-version bump
and fixture replay.

### 5. Rights no longer block safe core engineering unnecessarily

The plan separates synthetic or owner-permitted internal fixtures from external
benchmarks and reader packets. Pending corpus items remain blocked for external
use. Historical numbers are replayed only when their source snapshots, hashes,
and permissions exist; otherwise the result is `unavailable`, never a pass.

### 6. Security is an implementation choice, not only a policy sentence

WP0 selects one pinned rootless, network-disabled runtime profile, including
mounts, capabilities, resource limits, compiler, packages, and image digest.
The plan has no unsandboxed fallback. The shell-escape test uses an isolated
per-run sentinel rather than a shared system path.

### 7. Gates and calendar now agree

V1.1 defines G0 authorization, an end-of-week-four integration gate, G1 at week
six, G2 at week nine, G3 for the reader packet, and G4 for handoff. The authoring
extension ends at the contract's week-nine checkpoint; weeks ten to twelve are
reserved for the feasibility case and decision handoff. A core-only path is
specified rather than implied.

### 8. Evaluation no longer optimizes one proxy

The later comparative study keeps acceptance and reader time as primary
outcomes, while the one-document feasibility case reports rounds, burden,
abstentions, reconstruction, and safety descriptively. Protected-object and
privacy constraints are vetoes, not quantities that a favorable average can
offset. Critics reduce routine defects before the reader; they do not replace
the reader.

### 9. Machine release and human acceptance are separated

`hv release` produces an immutable packet. A separate `ReaderDecision` record
captures the six reader questions, confidence, time, first reread point, and
acceptance or requested changes. This prevents a command from pretending that
the human outcome is available before the reader has read the document.

## Questions for Fable

Please review the v1.1 plan and answer each question with **accept**, **modify**,
or **reject**, followed by a short reason and the affected section.

| # | Question | Why it matters |
|---:|---|---|
| 1 | Is the protected-core-first authorization rule the right investment boundary? | It prevents the authoring extension from consuming the full feasibility horizon |
| 2 | Should the conceptual records named in the architecture receive standalone schemas, or should some be versioned nested objects? | The current proposal and schema directory use incompatible inventories |
| 3 | Is the proposed strict-schema policy (`extensions` only for unknown fields) compatible with the intended minor-version policy? | It determines whether "stable contract" is enforceable |
| 4 | Which sandbox runtime should be the reference profile: rootless Podman, rootless Docker, or another named mechanism? | T1-T5 cannot be tested reproducibly without this choice |
| 5 | Can the five historical corpus owners permit internal fixture use, and which items can be cleared for an external reader? | Rights status changes what can be benchmarked or published |
| 6 | Are the historical replay tests appropriately quarantined as provenance checks rather than quality thresholds? | Exact style counts can become targets and distort product behavior |
| 7 | Is the week-nine authoring checkpoint and week-ten-to-twelve feasibility split consistent with the contract? | The v1.0 calendar had an avoidable week-nine/week-ten ambiguity |
| 8 | Is two independent readers a realistic target for the feasibility case, with one reader allowed only for integration? | A single reader can demonstrate operation but cannot support a broad reader claim |
| 9 | Are acceptance and reader time the right later-study primary outcomes, with rounds as a process outcome? | This preserves the proposal's stated estimand and avoids a single proxy scoreboard |
| 10 | What minimum engineering and evaluation capacity is funded? | With one engineer, Increment A is plausible; Increment B should remain conditional |

## Requested review standard

Please check the plan against the repository, not only against its prose:

```bash
cd /home/ubuntu/workspace/humanvoice
python3 tools/check_implementation_contract.py
python3 -m unittest discover -s tools -p 'test_*.py'
test -e tools/run_fixture_suite.py; echo "fixture runner status=$?"
test -e tools/run_regression_replay.py; echo "replay runner status=$?"
```

For every artifact the plan calls "implemented," please require a source path,
an invocation, a passing test, and an owner. For every artifact still planned,
please ensure the plan says `planned` rather than implying that it already
exists. For every evidence claim, please check the rights and screening status
before accepting it as release-ready.

## Proposed disposition after review

Until Fable responds, v1.1 is a planning draft and no contract version bump or
product implementation is authorized. After review:

1. accepted changes to the plan will be incorporated and the plan versioned;
2. changes to normative behavior will be made in
   `schemas/implementation_contract.json`, the normative LaTeX annex, and the
   affected JSON Schemas;
3. the consistency checker, fixture manifest, and runtime profile will be
   created before WP1 is marked started; and
4. the sponsor will receive a G0 decision record before authorizing code.

Fable's review should end with a clear recommendation: **authorize G0**,
**revise v1.1**, or **stop the implementation direction**. A passing document
build alone is not an acceptable substitute for that decision.
