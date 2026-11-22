# Humanvoice reset memo — November 22, 2026

This is the current handoff for a fresh session in
`/home/ubuntu/workspace/humanvoice`, timezone **Asia/Shanghai**. Read
[AGENTS.md](../AGENTS.md) and the
[scientific master](plans/ENSEMBLE_MASTER_PROGRAM_2026-09-30.md). This memo
supersedes older reset instructions about restarting or repairing ZLB execution.
Older records remain evidence of what happened at their original dates.

## The state to carry forward

**The ZLB candidate is complete; the user accepted the revised text, and the
reader files and updated roadmap have been committed and pushed.** There is no
unfinished ZLB generation, review, assembly or release job to resume.

On November 22, after reading the blacklined comparison and confirming its
color convention, the user said:

> I agree that the text is sensible and better. Git commit and push. are there
> any remaining gaps we still have to work on before testing on large scale
> problems?

The next request was to write this full reset memo for a new session. The
readability acceptance is recorded in the
[reader delivery README](../releases/zlb-2026-11-18/README.md). It does not
establish success on other manuscripts, independent reproduction, or approval
of a scientific correction to the source.

The immediate next milestone is to make the successful execution reproducible
from a clean checkout, prepare a bounded held-out pilot, and then measure larger
workloads. Preparation can proceed locally; a new live campaign needs its actual
input, resource allocation and applicable execution authorization.

## Git checkpoint and local workspace

- Repository: `git@github.com:chakkeiwong/humanvoice.git`; branch `main`.
- Pushed scientific checkpoint:
  `13afaed08d6d5ceaa62b09ffd4cc70aa30b67527` —
  `Publish accepted ZLB reader candidate and refresh scale-up roadmap`.
- The push included the 21 previously local ancestor commits. Remote `main`
  was checked after the push and matched the checkpoint. At the start of this
  handoff, `HEAD` and the local `origin/main` tracking ref still matched it.
- The checkpoint contains 22 selected reader, status, plan and approval-policy
  files. All 22 committed file hashes were checked against the reviewed payload.
  This reset memo is a subsequent documentation handoff; use `git log -3` for
  the current documentation commit rather than expecting `HEAD` to remain at
  the scientific checkpoint forever.
- The working tree is **not clean**. At handoff start there were 1,723 status
  entries using normal untracked-directory grouping, with nothing staged.
  This is not a physical file count. Existing changes span `src`, `tests`,
  `tools`, schemas, security profiles, fixtures, documentation, snapshots and
  `.localresources`; many predate the latest completion work.
- Only the compact reader delivery was published, not the full runtime archive
  or all implementation changes. A fresh Git clone is not yet a demonstrated
  reproduction of the successful local pipeline.

Preserve the existing working tree. Do not use a blanket `git add .`, `git clean`,
hard reset, or replacement checkout over it. Identify the required implementation
and its dependencies, then make scoped prospective commits. The old snapshot
deletions and modified historical files visible in Git status were already present;
do not adopt or reverse them without understanding their scope. A separate worktree
is useful for reproduction only after the necessary local code is captured.

## Reader deliverables

The convenient Git directory is
`/home/ubuntu/workspace/humanvoice/releases/zlb-2026-11-18/`.

| File | Meaning |
| --- | --- |
| [revision.pdf](../releases/zlb-2026-11-18/revision.pdf) | Accepted revised manuscript, 66 pages. |
| [comparison.pdf](../releases/zlb-2026-11-18/comparison.pdf) | Blacklined comparison, 71 pages. |
| [revision/zlb_source.tex](../releases/zlb-2026-11-18/revision/zlb_source.tex) | Revised LaTeX, unchanged from the successful native candidate. |
| [original/zlb_source.tex](../releases/zlb-2026-11-18/original/zlb_source.tex) | Frozen original LaTeX for comparison. |
| [SOURCE_ERRATUM.md](../releases/zlb-2026-11-18/SOURCE_ERRATUM.md) | Separate scientific discrepancy, not applied to either source. |
| [manifest.json](../releases/zlb-2026-11-18/manifest.json) | Hashes and sizes of the delivery files; hash binding to the original packet and the acceptance record. |
| [verification-2026-11-18.json](../releases/zlb-2026-11-18/verification-2026-11-18.json) | Unchanged historical verification of the native release. |

Open the blackline from the repository root:

```bash
xdg-open releases/zlb-2026-11-18/comparison.pdf
```

Red prose is deleted from the original; blue prose is added in the revision;
unchanged prose is black. The actual LaTeX uses blue sans-serif additions and
smaller red deletions. Ordinary hyperlink/citation colors are not change markers.
The clean reading copy is `revision.pdf`.

All five reader artifacts were copied byte for byte and checked against the
original native packet manifest. No manuscript content, PDF rendering or
scientific evidence was changed during Git packaging.

The complete local reader/audit packet remains at:

```text
.localresources/scientific-extension-20261117/working-snapshot/release/20261117T235022.984126Z-8dc3251b/
```

It contains 27,214 manifest-bound files, including receipts, prior negative
judgments, charges and canonical scientific evidence. The original blackline is
`reader/comparison.pdf`; its revised copy is `reader/revision.pdf`. The full
packet is not included in the compact Git delivery. Preserve it locally.

| Artifact | SHA-256 |
| --- | --- |
| Original packet manifest | `da8a3110639a01d51fec3ec2394218275dc60d8defd9a2c9035f9a3603ea4d19` |
| Revised PDF | `27b518c59be810b1d4e7aa79e97ffb7d563a80015860e1d463794460a5915754` |
| Blackline PDF | `9d716e6f7f73ff90a242512a897983b144b2dbf2b575055f8883cf6da8697500` |
| Revised LaTeX | `0ccc3ad083aab9e91df3747183e10d08538d3bf5e3cb8ec127ccf97a11714334` |

## Completed scientific and execution result

Native release completed **November 18, 2026, 16:08:24 Asia/Shanghai**.

- Candidate session: `20261117T235022.984126Z-8dc3251b`.
- Authoritative assembly: `20261117T235022.984126Z-8dc3251b-052u1ctg`.
- Native release: `cli-4aa26337d9a2409caf433ab50e4de3cc`, exit code 0,
  `candidate-ready`, no blocking reasons.
- All **21 units accepted**, all **5,042 canonical concept mappings supported**,
  retention **1.0**; no blocking or unresolved canonical findings.
- Inventory: **180 windows**, **6,888 required functions**, **6,208 dependency edges**.
- All **20 relationship reviews pass**, with native findings. Eighteen unchanged
  reviews were reused; the two affected by unit 015 passed without retries.
- All **14 release gates pass**; native preflight, assembly, protected objects,
  builds, transmission, policy and runtime admission are complete at this scope.
- Runtime admission covered **1,902 retained runtime records** and **985 historical
  API attempts**. These audit counts are distinct from the latest call allocation.
- The original manifest and every one of its **27,214 files** were verified.

The final check is retained at
`.localresources/scientific-extension-20261117/admission-runtime-repair/final-packet-check.json`.
Reuse that evidence for unchanged artifacts. There is no reason to rehash the
whole archive, rebuild both PDFs, repeat the semantic reviews or rerun a full
test suite just because the conversation changed.

The native packet was frozen before human review, so its `reader_acceptance`
remains `pending` and `external_release_authorized` remains `false`. Those fields
describe the November 18 package. The later user statement records text acceptance
and authorizes Git publication. Do not rewrite the frozen packet to change its
history, or infer broad production/release approval from the text acceptance.

## Source erratum still open

The source prose following equations (60b)/(60c) says the maps change momentum
along `M^-1 n`. The displayed equations instead give a momentum increment along
`n`; with `v = M^-1 p`, the velocity increment is along `M^-1 n`.

The separate erratum includes an exact rational counterexample for a nonidentity
mass matrix and explains the corresponding inner-product projection. The accepted
candidate deliberately preserves the original source claim. Do not silently
correct this manuscript or change frozen concept expectations to remove it.

If the user chooses to apply the correction, create a new revision, update the
affected source-grounded concepts and dependent judgments, and retain the accepted
version. This issue does not block a held-out test on another manuscript.

## Completed repairs and where the working implementation lives

The continuation root is `.localresources/scientific-extension-20261117/`.
Important implementation and evidence locations under that root:

| Location | Purpose |
| --- | --- |
| `extension_program.py`, `extension_bootstrap.py`, `extension_runtime.py` | Completed orchestration and runtime adapters. Bootstrap imports the retained predecessor controller. |
| `admission_receipts.py`, `admission_reconciliation.py` | Route and reconcile retained receipts under their actual native contracts. |
| `qualification_endpoint.py`, `qualification-endpoint-repair/` | Bind qualification to the actual endpoint/profile and reject changed identities. |
| `reading_order_fix.py`, `reading-order-worker-repair/` | Accepted source/parser handling and native parser operation admission. |
| `preflight_resume.py`, `preflight_reuse.py`, `preflight-record-repair/` | Resume interrupted preflight and reuse matching canonical evidence. |
| `schema_reuse.py`, `inventory_view_reuse.py`, `inventory-view-repair/` | Reuse unchanged schema/inventory results while retaining dependency and authorization checks. |
| `source-contrast/`, `source_contrast.py`, `attribution-repair/` | Unit 009 source preservation and unit 015 attribution correction, with drafts and independent judgments. |
| `targeted-repairs.json`, `bank/`, `native-stage/` | Consumed repair rounds, actual allocated requests, retained responses and receipts. |
| `tests-result.json`, `admission-runtime-repair/verified-replay.json` | Source-bound focused verification and actual replay of the last failed receipt. |

The last blocker was the generic Codex reader receiving extension capture
receipts. `admission_receipts.py` dispatches those to their original verifier,
retaining charged-slot ownership, reviewed launch markers and native evidence
checks. Eight new routing checks and the real failing-receipt replay passed.
The completed payload records **93 unique focused checks**; do not sum overlapping
historical suite counts into a larger independent test total. The source-bound
`program.review()` passed before successful final admission. No new provider call
was needed for the final repair.

Unit 015 now explicitly attributes lack of access to Allik et al.'s full text
to the present manuscript's authors. Its six independent reviews cover all
335 concepts and 467 functions. Unit 009 preserves the original propositions
and protected mathematics and has five passing independent reviews. Earlier
negative judgments and consumed repair rounds remain retained.

The local import/dependency chain also uses
`.localresources/controller-independence-20261116/`,
`.localresources/scientific-continuation-20261115/` and earlier reviewed adapters.
Prior accounting/runtime state lives under
`.localresources/parallel-writing-semantics-20261112/` and related predecessors.
These are starting points for the reproducibility inventory, not a claim that
copying these few directories alone creates a complete portable installation.

Do not run `extension_program.py discover` merely to inspect the completed state:
native admission has already populated its destination. `install-start` is a
separate privileged service deployment and is unnecessary for the accepted result.

## Execution state, budgets and authority

At handoff, the authoritative files report:

- `offline-status.json`: `CANDIDATE_READY`, `native_release`, zero demands,
  21 accepted units, no rejected units.
- `frontier.json`: `CANDIDATE_READY`, empty demand list, 20 relationship reviews.
- `coordinator.json`: wave **11**, `pending: null`.

The offline tool session **25063** completed successfully and its owner PID
**2223904** exited. These are historical execution identifiers, not sessions
to reconnect or processes to restart. The older CLI conversation ID
`01a1da91-c511-7a13-b300-99baf7493a07` appears in the November 15 memo; a fresh
session can work from this handoff without reviving that conversation.

The live service remained stopped after offline completion. Its `status.json`,
observer and master-page `BLOCKED` banner describe the earlier failed live
attempt; they do not override offline completion. The service names were
`humanvoice-zlb-science-20261115.service` and
`humanvoice-zlb-science-reporting-20261115.service`. Do not restart them as a
consequence of reading an old banner. No new live service audit was needed for
this documentation handoff; distinguish recorded completion from a fresh process
inspection if a future task actually depends on current host state.

The last ZLB authorization is the user's additional **100 calls and 72 hours**,
recorded in `authorization.json` under the continuation root:

- Ceiling **277 calls**; **240 allocated** = 176 prior + 64 extension charges.
- **206 retained responses**; **36 usable extension slots** remain. One additional
  unused slot from the original pool remains held. Failed starts stay charged.
- Deadline **November 26, 2026, 17:03:49 Asia/Shanghai**. A session change does not
  renew that deadline, allocations, or the two automatic repair rounds per unit.
- Historical provider settings: four workers, 900-second provider bound,
  1,050-second attempt bound, 900-second transport backoff; manuscript profile
  Astra/xhigh with the pinned executable and provider/profile binding.

The historical grant covers the ZLB manuscript continuation. It is not an
allocation for a new held-out/FinMarketing campaign or independent reproduction.
Check any separately existing allocation for its actual scope before inference.
Do not change model, effort, endpoint, prompts or source silently under old
qualification. Preparing code and a pilot does not require restarting anything.

## Remaining work, ordered for scientific progress

1. **Capture the implementation for reproduction.** Identify the actual code,
   schemas, Python/LaTeX dependencies and retained adapters used by the accepted
   execution. Separate implementation from receipts, temporary trees and caches.
   Preserve local changes, package the necessary files with bounded focused
   checks, and make the intended entry point usable from a clean checkout.
   Then perform a separately allocated independent execution and verifier.
   Deterministic content/build checks and fresh-model source-fidelity reproduction
   are different evidence; a rebuild or copied packet is not fresh inference.
2. **Prepare and run a held-out pilot.** Start with an available separately
   authorized manuscript and its actual current evidence; do not assume prior
   historical held-out work is absent or current without inspecting its scope.
   Fix source-grounded expectations before seeing new outputs. Cover different
   structure, notation, long dependencies, equations, citations, tables and macros.
   Measure preservation and readability separately. One positive ZLB reader
   judgment does not estimate a general failure rate.
3. **Increase scale with measured evidence.** The roadmap proposes representative
   50–100-page, then 200–300-page, then approximately 1,000-page FinMarketing
   workloads. These sizes are a proposed progression, not newly authorized jobs.
   Measure calls/tokens, cost per accepted unit, elapsed time, peak memory,
   storage growth, retry frequency and quality. Test recovery from one meaningful
   interruption at an untested scale; preserve accepted checkpoints. Do not
   extend a single model request to hold an entire large document.
4. **Handle the source erratum separately.** Obtain the scientific choice before
   applying a new source revision; only affected evidence needs updating.

Before live execution, identify the pilot input, explicit call/token/time/storage
limits, the reproduction allocation and any required scoped host action. Use
the existing coverage, protected-object, semantic-review, relationship and build
checks as success criteria. Reuse evidence that still matches its inputs and
implementation. Do not add a new committee, daily inventory, redundant full-suite
replay, publication checklist or repeated unchanged review to this critical path.

## Approval and environment rules

Keep `approval_policy = "on-request"`, `approvals_reviewer = "user"` and sandbox
restrictions. No automatic approval delegation, broad interpreter/shell permission
rules, bypass flags or self-approval. Follow the exact
[human approval policy](plans/HUMAN_APPROVAL_POLICY_2026-10-24.md). New privileged
actions must be concrete, reviewed and grouped through the host mechanism when
required; existing authorization remains valid within its actual scope.

The fixed offline helpers, when their checks are relevant, are:

```bash
/home/ubuntu/miniforge3/bin/python /home/ubuntu/workspace/humanvoice/tools/humanvoice_manual_approvals.py check
/home/ubuntu/miniforge3/bin/python /home/ubuntu/workspace/humanvoice/tools/humanvoice_manual_approvals.py status
/home/ubuntu/miniforge3/bin/python /home/ubuntu/workspace/humanvoice/tools/humanvoice_manual_approvals.py test
```

Do not run all three as a new-session ritual. `status` enumerates a fixed older
service list; inspect its scope before treating it as comprehensive evidence
about the later science services. `test` runs bounded approval/recovery checks,
not a fresh ZLB scientific test. No subagents are authorized for the current
handoff. Frozen source, launchers, grants, charges, receipts and reviews remain
unchanged. Do not send messages to others or start new live work from this memo.

CLI use avoids depending on the VS Code renderer. Historical watcher repair
set 2,097,152 watches and 1,024 instances and passed a watch/create/write/delete
check. `.vscode/settings.json` excludes large evidence, cache and build trees
from watching/search and disables symlink following. The separate renderer heap
crash was not established as fixed. Do not claim a new session guarantees no
crashes or make further editor tuning a prerequisite for manuscript research.

## Minimal first steps in the new session

Read this memo and the current master, inspect a bounded Git status summary, and
confirm the accepted delivery location. Keep the completed run stopped. Begin
by tracing the successful runtime's necessary imports/configuration and the
uncommitted code that a clean checkout lacks. Draft a concrete reproduction and
held-out pilot package before requesting any missing live allocation or privileged
deployment. Do not redo the accepted ZLB work to demonstrate that the session resumed.

This handoff updates documentation only. It does not change the manuscript,
frozen packet, runtime, model qualification or accounting, and it spends no
provider calls. The prior root reset text is preserved
[here](plans/history-20261115/RESET_MEMO_before_2026-11-22.md).
