# TX3b canonical configuration design review — 28 October 2026

Disposition: six actionable composition findings. TX3b is not ready for
production admission. These concern the prospective public boundary, not a
reopening of TX3a offline campaign-binding findings.

Read-only, single-inspector review under `/home/ubuntu/AGENTS.md` and repository
`AGENTS.md`. Read both the public-admission and closure plans and traced their
direct authority consumers. Only this report is written. No tests, imports of
project execution modules, network/model-gateway requests, preparation, service
commands, source/test/master edits or production-artifact writes were performed.
The preparation session was left alone. At closure, the coordinator reports its
failure after 1063.83 seconds with source/authority unchanged and zero
calls/writes. The coordinator owns that regression; this inspector did not
investigate it. This report does not gate or block the coordinator's local
repair. Findings are static; proposed corner cases have not been executed.

## Findings

### PC1 — P1: define an acyclic source → preparation → deployment identity graph

Evidence: `tools/review_inventory_recovery_v3.py:23`,
`tools/prepare_inventory_recovery_v3.py:39`,
`tools/inventory_recovery_v3/runtime.py:33`, and
`docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md:8`.

Preparation lives under `preparation/digest(review.sources())[:20]`; its plans
also bind the bytes of every v3 Python module. Adding the future public module
there changes both identities. Hardcoding the currently running preparation's
hash/path into that hashed module invalidates the preparation and, if updated
again, creates a self-referential hash requirement. Conversely, putting a new
entrypoint outside the current source membership without extending the manifest
leaves its executable bytes unbound. The current offline preparation cannot be
promoted as validation of future TX3b source.

Remedy: freeze a complete explicit implementation/test/dependency manifest first;
derive the preparation path from its source identity, then validate the complete
preparation and full campaign-binding publication. Build configuration from those
lower-level identities. Release/preflight/host admission reference the resulting
configuration digest; configuration must not contain the digest of its own
admission or of a preflight that already contains the configuration digest. Keep
generated records outside source membership. Reprepare under a new derived root
after the final source freeze; never patch the old preparation to match. This is
a design dependency to resolve, not evidence of an existing TX3a hash cycle.

Corner cases: adding/changing the public CLI or a transitive helper invalidates
the receipt; generated admission/status files do not change source identity; an
old preparation is rejected after a source edit; identical inputs in a cold
process yield the same paths/configuration without embedding output hashes in
source or modifying historical evidence.

### PC2 — P1: the proposed authority shape contradicts its actual consumers

Evidence: public-admission plan `:19`;
`tools/inventory_recovery_v3/stage_authority.py:23`, `:27`, `:43`;
`tools/inventory_recovery_v3/journal_binding.py:29`, `:43`;
`tools/inventory_recovery_v3/cancellation.py:13`.

The plan places journal and stop bindings in `execution_authority`, but
`CampaignAuthority` accepts exactly five keys there. Journal and cancellation
consumers read top-level `recovery_journal` and `stop_bindings`. A literal
implementation of the plan fails construction; placing them only in the nested
object leaves downstream consumers without authority. Missing top-level stops
currently become an empty list. Also, admission is compared to the same fixed
configuration on every check: returning a binding inspection report containing
the advancing campaign cursor cannot work.

Remedy: adopt the exact topology below and require complete independently derived
top-level bindings in the public validator. Return only the immutable canonical
configuration after separately checking runtime state. Keep validation layered:
leaf descriptor/stop checks → immutable admission → runtime evidence. Do not
implement `require_admission()` by calling `campaign_binding.inspect` with
`check=authority.check`: the latter calls `require_admission()` again.

Corner cases: exact native configuration succeeds; journal/stop nesting errors,
empty/rehashed stop omission, extra authority keys and a foreign journal fail
before a hold. Repeated checks after lawful advancement return the identical
configuration. Exercise the real callback graph without recursion.

### PC3 — P1: changing only admission leaves a hidden whole-account runtime guard

Evidence: `tools/inventory_recovery_v3/installed_authority.py:76`, `:82`, `:91`;
`tools/inventory_recovery_v3/handover.py:50`, `:87`, `:94`, `:113`;
`tools/inventory_recovery_v3/stage_authority.py:65`;
`tools/inventory_recovery_v3/claim.py:68`.

Every `ChainLease.check()` rebuilds its proposal through `capture()`, including
whole account/grant-stage bytes. Thus replacing only the public admission
callback with a monotonic validator still rejects the first lawful hold or
sibling update. The old cursor in this capture is the historical v2 cursor; it
must remain frozen after transfer. It is not the prospective cursor that may
advance. A generic exclusion of all cursors/state from integrity checks would
silently weaken predecessor immutability.

Remedy: retain the original capture as transfer evidence and introduce a separate
runtime validator with the explicit partition below. Freeze historical cursor,
job/state membership and stage/qualification lock inventory. Advance only new
campaign/runtime state, using native receipts and committed floors. Initial
TX3a floors are a lower bound, not protection for all later suffixes. Persist
spending-boundary intents before mutations and reconcile them on cold entry.
Do not update immutable configuration or transfer evidence to chase balances.

Define lock-aware validation: `grant_stage()` calls `authority.check()` while
holding the grant lock, and `readiness()` calls it while holding the account
lock. A new admission validator that independently reacquires those locks can
self-deadlock. Pass an already-owned observation/descriptor or use a leaf
validator with an explicit lock order; never recursively acquire these locks.

Corner cases: hold/reserve/settle plus sibling growth succeeds with unchanged
installation identity; cold rollback of a post-deployment suffix fails; every
floor-publication cut converges once; historical cursor/job changes fail;
validation under existing grant/account ownership completes without deadlock.

### PC4 — P1: inherited exclusions, shared locks and provider lifetime need one composition

Evidence: `tools/inventory_recovery_v3/handover.py:122`, `:129`, `:136`;
`tools/inventory_history_handover.py:160`;
`tools/inventory_recovery_v3/launcher.py:52`, `:74`;
`tools/inventory_recovery_v3/stage_owner.py:75`;
`src/humanvoice/codex_runtime.py:180`.

The chained capsule contains predecessor monitor/job descriptors only. Its
`shared_locks` are briefly probed by native `Lease.check()` and then released;
they are not continuously held or in the capsule. Calling `handover.lease()`
after taking the program lock also conflicts with its independent probe of
that same lock. The current v3 launcher forwards only its launch/job descriptor
at each spawn, and the provider context contains only the stage executor
descriptor. Merely adding a chained capsule to the environment does not make
its descriptors survive either spawn or keep program/campaign exclusions alive
after ancestor death.

Remedy: specify acquisition and transfer order once. Acquire predecessor
exclusions, establish quiescence and retain required historical stage exclusions;
acquire the shared program owner and new campaign owner without reacquiring
them through an independent probe. Pass the verified union of chain, program,
campaign, job and relevant stage descriptors through both launch edges. Retain
ownership until every provider is quiescent, using inherited descriptors or an
equally strong reviewed lifetime guardian. Derive capsule membership from fixed
paths; FD numbers are ephemeral capabilities, never configuration identity.

Corner cases: valid cold worker/campaign entry succeeds; missing/substituted FDs,
same-inode independently opened FDs, reordered roles and changed lock inodes
fail before hold/claim. Kill monitor, worker and campaign separately with a
provider surviving; another supervisor/campaign must neither spend nor charge
a restart until quiescence. Include entry with an already-held program lock.

### PC5 — P1: a content-valid authorization file is still not host permission

Evidence: public-admission plan `:24`;
`tools/inventory_recovery_v3/installed_authority.py:54`;
`tools/deploy_inventory_history_live.py:88`;
`tools/preflight_inventory_history_live.py:57`; closure plan `:62`.

The existing deployer itself writes the exact `authorized_by=user` object that
capture validates. These historical records are useful evidence, but copying
this pattern cannot implement the plan's independent host authorization. An
ordinary caller able to write candidate JSON can reproduce the expected fields
and hashes. Human configuration settings and desktop delivery also do not prove
approval of this deployment. Separately, reusing the historical preflight as-is
would publish `live.ADOPTION` into old campaign storage, contradicting the new
no-authority-write preflight and frozen-history boundary.

Remedy: state the trust root: a host-authenticated receipt/capability verified
outside the candidate writer's authority, bound to exact action/argv, source,
configuration, release, preflight, deployment target and limits. Require unique
deployment identity and explicit replay/consumption semantics. If the host
cannot supply independently verifiable approval, public dispatch stays blocked;
a JSON flag is not a substitute. Keep new handover/admission under prospective
storage. Install exact disabled units, validate effective loaded unit paths,
drop-ins/environment and predecessor inactivity, then publish the admission
commit before a separately authorized launch. Distinguish install permission
from runtime admission so admission publication does not require itself.

Corner cases: rehashed forged authorization, old host receipt, unrelated desktop
receipt and mismatched target/argv fail. Crash after each unit/install/publication
step leaves dispatch disabled and supports exact resumption. Matching unit-file
bytes with a foreign loaded fragment/drop-in fail. No predecessor byte changes.
Verify effective child approval flags, not just config files;
`tools/active_session_runtime.py:47` already supplies explicit human overrides
for its applicable profile, whereas the base command ignores user config.

### PC6 — P1: inherited stops need old contracts plus a distinct prospective stop root

Evidence: `tools/inventory_recovery_v3/installed_authority.py:84`;
`tools/inventory_recovery_v3/handover.py:94`;
`tools/inventory_recovery_v3/cancellation.py:13`;
`tools/inventory_recovery_v2/control.py:26`.

The installed stop set contains only the historical campaign. Copying it
unchanged into the new configuration gives no prospective campaign stop
authority; replacing its contract with the v3 contract breaks exact historical
resume validation. The old checker treats a missing stop file as running and
validates a present resume by JSON fields/hash. Deployment approval therefore
cannot implicitly clear the existing stop or authenticate a newly invented
resume.

Remedy: exact stop membership is the independently derived inherited set,
retaining every original contract, plus the canonical new campaign control root
and its fixed contract. Missing/extra roots must fail public admission. Preserve
old stop/resume bytes; a new host-verified continuation authorization can bind
their exact stop identity prospectively without rewriting them. Retain an
observed-stop/control floor so deleting or rolling back a known stop cannot
become permission. Check every root again at hold, claim and dispatch boundaries.

Corner cases: old stop vetoes new deployment, new stop vetoes either cold command,
late stop between checks prevents spending, and an old/replayed resume cannot
authorize another stop/source. Test absent initial stop separately from deletion
of a previously recorded stop, plus dangling symlinks and root aliases.

## Minimum canonical configuration

This is a proposed exact schema layout, not a new authorization. Keep existing
consumer key locations; introduce one public factory/validator, no caller-selected
account, grant, seed, command, stops or journal.

| Block | Minimum fixed content and derivation |
| --- | --- |
| Identity | Version; exact reviewed source/dependency identity. Preparation root is `review.OUTPUT / preparation / digest(review.sources())[:20]` after the final manifest is defined. Verify full identities, not the directory prefix alone. |
| Candidate | Campaign root is preparation root plus `campaign`; verify completed binding publication, seed/proposal/initial native preparation and document/policy identities. New supervisor root can be preparation root plus `supervision`, with exact canonical disjoint paths. |
| `execution_authority` | Exactly `program_base`, `supervisor_root`, `account`, `grant`, `grant_identity`. Derive program base/account/grant from retained native authority and cross-check campaign binding. |
| Top-level `recovery_journal` | Exact binding descriptor: `path`, `binding`, `policy_identity`, `initialization_sha256`; derive from complete campaign binding/seed. |
| Top-level `stop_bindings` | Exact nonempty inherited-plus-prospective root/contract list from PC6. No current stop bytes inside configuration. |
| Ownership | Immutable handover identity, complete predecessor chain, fixed historical lock membership and original restart ceiling minus predecessor charges and transfers. Bind separate new program/campaign/job lock roles. |
| Commands | Fixed absolute interpreter plus `-I` and the reviewed public script, fixed `monitor`, `worker`, `campaign-execute`, `campaign-verify`, `campaign-repair`, `status` actions; exact cwd. Map existing `run`, `admission`, `verify`, `repair`, `diagnose` keys explicitly; validate the worker command too. Only the validated job identity is dynamic. |
| Execution policy | Exact environment allow/unset contract, unit identities, human approval/sandbox settings, qualified initial profile and ordered model policy; native account/grant/document/generation limits and distinct worker-restart limit. Carry operational timing settings explicitly. Do not blindly inherit old plan/snapshot/progress/repair-limit fields through `**old_config`. |
| Admission envelope, outside config | Configuration digest, campaign/handover identities, exact release test membership/results, no-call preflight and independent host authorization, installation commit. Offline binding remains `live_execution_enabled=False`; the envelope alone can admit the fixed public entrypoint. |

`require_admission()` must independently rebuild/compare this fixed configuration
and return it, never a current account/cursor report. Source-bound implementation
and generated configuration may refer downward to preparation; release and host
records refer downward to configuration. No reverse digest edges.

## Immutable installation versus runtime

| Category | Rule |
| --- | --- |
| Immutable installation | Source/test bundle, fixed configuration, units/environment contract, grant definition, preparation/seed/binding, journal initialization identity, handover chain, predecessor config/state/jobs/receipts/cursor and lock/stop-root membership. Historical evidence is never repaired in place. |
| Transfer observation | Account/grant-stage bytes and sampled process/service state prove transfer conditions. Preserve the capture for audit; do not use its whole-byte identity as a spending-time equality guard. Recheck actual service ownership/effective configuration separately. |
| Mutable runtime | Account events/plans and grant-stage membership obey validated committed prefixes; journal consumption, prospective head/cursor, restart and repair receipts obey their own durable protocols; stops/resumes obey authenticated monotonic control history. Lower net reservation after valid settlement is not rollback. |
| Spending boundary | Complete required native write-ahead receipt/floor before granting further spend; reconcile pending work under existing ownership before `StageOwner`. Follow the closure phase table, including no successor allocation before head/cursor/repair commit. |
| Read-only observation | Coherent pending publication may report nondispatching status. Reading status/admission cannot repair a journal, create a missing owner, issue permission or advance a floor. Integrity failure stays distinct from publication-in-progress and transient I/O. |

The minimum production-safe result includes the ownership, authenticated admission
and runtime-floor integrations; a configuration factory alone is not sufficient.
Use the prescribed final source freeze/release/preflight order after local
repairs. No TX3b promotion or production restart is authorized here.

## Reviewed-byte anchors

Read-only SHA-256 observations for coordinator reconciliation:

| File | SHA-256 |
| --- | --- |
| `tools/inventory_recovery_v3/installed_authority.py` | `8a77f7c6abb86990e6f8eb4518d186db1dc0cf9d86e95f92f40df2ae62a9dcc6` |
| `tools/inventory_recovery_v3/handover.py` | `f496b46cbbb53a585c4c64e2b390178ed687093fb05a2710d160cd81cc800a6d` |
| `tools/inventory_recovery_v3/stage_authority.py` | `134b517dcb2fe3767da5e381eb654e105bd9ae58c6f3af0f51b0c836232e3ecb` |
| `tools/inventory_recovery_v3/campaign_binding.py` | `3d108a9786ce138543c1bf876d6f0f9951210e6a7aca83b39995f7893fb86eb2` |
| `docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md` | `571771954bc89b5af6baef0bbf40484cc7f4692115b61e8af5e09f6032d936c4` |
| `docs/plans/INVENTORY_RECOVERY_CLOSURE_2026-10-28.md` | `d028331d3b9ffdd2d0c01d4b51ea99dcab3020e72e96dafb38a0f2a22f6328e3` |
