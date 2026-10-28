# Inventory recovery public configuration review — 28 October 2026

**Current disposition:** C1, C2, and C1-R are closed by bounded source inspection. The final explicit ownership-object guard resolves the raw-string digest case, and the six paired field-type plus three asymmetric object-type regressions are present. Final-source test execution remains coordinator-owned and pending at this closure. This is not live admission or actual-production readiness. Earlier findings and snapshots are retained as history; the final closure section records the current hashes and evidence boundary.

## Scope and evidence

One findings-only inspector; no delegation. Reviewed `tools/inventory_recovery_v3/configuration.py`, `public.py`, their immediate derivation dependencies, `tests/test_inventory_recovery_v3_configuration.py`, and the native configuration addition to `tests/test_inventory_recovery_v3_stage.py`. Followed `/home/ubuntu/AGENTS.md` and repository `AGENTS.md`. This report is the inspector's only write. No source, tests, master, service, authority, or frozen evidence was changed.

This is a static review of the nondispatching configuration candidate, not runtime admission or actual-production candidate readiness. Executed only filesystem/source inspection, scoped Git inspection, SHA-256 commands, and the patch creating this report. No application entry point, provider call, test suite, native preflight, service command, or production-data preparation was executed by this inspector.

Coordinator-reported execution, not independently executed or log-verified here:

- 48 configuration/native integration cases passed in 137.19 seconds with 16 workers. That integration revision enclosed configuration derivation in `accounting.document_scope`.
- After removing that enclosing scope, the standalone native configuration integration passed: 1 test in 156.90 seconds. The reviewed final test calls `configuration.derive()` and `configuration.validate()` directly at lines 479–480. It retains the host-installed-capture fixture and native plan/preparation/campaign binding. No cold-entry failure is asserted in this review.

Two bounded findings follow. Neither establishes a dispatch bypass: all five public live actions still reject before configuration inspection.

## Initial findings (historical; see follow-up disposition)

### C1 — P2: A completed preparation can lose its ownership preflight and still produce a ready configuration

**Locations:** `configuration.py:59–81,90–92,136–139`; `tools/prepare_inventory_recovery_v3.py:96–146`; `campaign_binding.py:35–43,188–198`; configuration test fixture at `tests/test_inventory_recovery_v3_configuration.py:62–68`.

`_derive()` accepts a selected subset of `preparation.json`: PASS/status booleans, zero counters, source map, successor, and native plan/transition/binding/seed/journal identities. It never reads `ownership-preflight.json`, checks the embedded `ownership` result, or binds the preparation's `authority` observation. The positive configuration fixture actually constructs a preparation without either `ownership` or `authority`, and without an ownership-preflight file.

Those omissions matter within the implemented preparation phase. `prepare()` publishes the campaign binding at line 97 **before** constructing the native resolver and checking inherited root/lineage usage, diagnostic handoff, import idempotence, and the check-only reservation at lines 104–130. It then writes `ownership-preflight.json` at line 137 and only subsequently sets PASS. The binding's immutable file list does not include this later completion evidence. Thus complete binding membership alone does not prove that the implemented final ownership preflight completed.

**Concrete failing regression to add:** Start with successful native preparation, remove its `ownership-preflight.json`, remove or replace `preparation.json["ownership"]`, and derive a new candidate. No inspected condition detects that loss; the preparation byte hash merely identifies the newly observed incomplete document. Rehashing the resulting configuration and passing it to `validate()` does not help, because fresh derivation consumes the same incomplete evidence. Separately cut preparation after binding publication but before ownership preflight, then supply only the currently required PASS fields: configuration must reject this case. These are static acceptance-path findings, not inspector-executed reproductions.

**Required correction:** Define and verify the completion evidence emitted by this existing preparation phase. Require its fixed location, exact record shape, agreement with the preparation receipt, and membership/limits derived from the retained native plan, observations, and initial journal. Bind the original authority observation consistently with the existing prepared anchor; do not require current mutable account bytes to equal a historical preparation snapshot. Add missing, altered, symlinked, and late-changing ownership-preflight cases and rehashed omission cases. This requests verification of already implemented preparation work, not later live ownership/floor implementation.

### C2 — P2: Native configuration inspection writes a shared warmup report

**Locations:** `configuration.py:32–34,69,123`; `campaign_binding.py:134–136`; `accounting.py:25–37`; `tools/inventory_recovery_v2/program.py:155–169`; `tools/active_session_program.py:48–54`; `tools/parallel_verification_replay.py:67–72,87–97`; native integration at `tests/test_inventory_recovery_v3_stage.py:263–286,465–487`.

The configuration reader enters `campaign_binding.inspect()`, which enters native `accounting.document_scope(transition)` to validate account/grant history. The history-scope chain reaches `active_session_program.historical_scope()`. That scope explicitly calls `cached_parallel_verification(workers=16, progress=OUTPUT.parent / "active-session-warmup.json")`; `warm_settlements.publish()` writes this report immediately and during completion/failure. `no_inference()` blocks provider/account/grant operations, but does not block this ordinary `write_json` call.

The inspected chain is: v3 accounting → v2 program history → Sol runtime → token epoch → qualification history → qualification capture → response capture → recovery session → model canary → active-session transport probe → active-session recovery → active-session program historical scope. This is reached by the current read-only inspection path, not by a proposed live launcher.

**Impact:** A configuration/status inspection can overwrite shared progress evidence outside its candidate directory, or fail in an otherwise readable environment when that destination is unwritable. These are diagnostic writes, not account/grant consumption or inference; the zero authority-write counters do not measure them. Concurrent readers can also overwrite the same report.

**Missing regression:** Configuration unit tests replace the native document scope with a no-op through the bootstrap fixture. The native integration redirects warmup progress to `tmp_path / "warmup.json"` at lines 279–282, but its byte/mtime check covers the campaign subtree and account/grant only. Add a native public `status`/`configuration` check that observes or denies writes to the warmup destination and all touched evidence roots, including failure paths. Keep independent native settlement replay enabled. Supply a genuinely nonpublishing warmup mode (`progress=None` or an equivalent narrowly scoped reader) for configuration inspection.

## Initial regression gaps (historical; see follow-up coverage)

These are coverage gaps in this slice, not additional proven implementation defects:

- `test_rehashed_candidate_cannot_replace_derived_authority` replaces whole fields with `"foreign"`; it does not delete/reorder one inherited stop, delete the prospective stop, alter only a stop contract, omit a predecessor record, or remove/add one `execution_authority` field while rehashing. Add those structured mutations, including `verify`, `diagnose`, routing policy, inherited restart usage, and generation limits. Whole-value independent equality appears to reject them; the exact intended boundary should be pinned.
- The public configuration fixture exercises zero worker-restart receipts and two handover charges (`2` inherited, `14` remaining). Add configuration-level nonzero and pending restart-receipt cases and exhaustion at the original ceiling; assert every handover charge and native receipt is counted. Lower-level handover tests already cover pending receipt arithmetic, so this is a missing composition regression, not a newly discovered arithmetic bug.
- Add public read-only inspection over a coherent campaign PENDING state with a fully published binding, checking that no reconciliation occurs. The current configuration `pending` mutation instead corrupts the binding-publication marker and correctly expects rejection; that is a different state.
- Exercise both public read-only CLI actions and structured error output with native configuration derivation. Current CLI tests cover the five blocked live actions and one isolated `campaign-execute` subprocess. The direct native derivation pass resolves the former enclosing-scope concern but is not a positive public CLI or real-host installation test.

## Bounded conclusions and exclusions

- The source → preparation → binding → configuration graph is acyclic in the inspected code. `review.sources()` hashes Python sources, not generated configuration/preparation, and `_derive()` computes the preparation root before reading it.
- The emitted `execution_authority` has exactly `program_base`, `supervisor_root`, `account`, `grant`, and `grant_identity`. Journal and stop bindings are top-level. Commands use the fixed absolute interpreter, `-I`, fixed public script, and fixed action names. All five live actions unconditionally raise `BLOCKED_OWNERSHIP` before `configuration.status()`.
- Full candidate equality against fresh derivation rejects rehashed output-field omissions/substitutions; this does not repair C1's missing independently checked input evidence. Binding inspection separately requires complete publication and exact immutable membership.
- Inherited stop bindings are copied with their original contracts and a distinct prospective campaign stop binding is appended. Restart accounting delegates to independently rebuilt native handover records; generation policy comes from the native proposal and is checked against the seed. No concrete renewal defect was established here. Returning a nondispatching candidate while stopped is not itself a stop bypass.
- **Source/dependency completeness is limited:** `review.sources():23–27` includes only top-level `tools/inventory_recovery_v3/*.py`, the review script, and the preparation script. It does not directly include imported historical/tool/core modules or `security/model_routing_policy.json`. Nested runtime/installed contracts and exact routing validation bind many of these separately; their omission from the root map does not establish that arbitrary changes are accepted. The final design text at lines 78–83 explicitly leaves full dependency bundling outstanding. Treat the map as a bounded candidate-source manifest, not a complete release/dependency closure. This known later gate is **not** reported as a new defect.
- Immutable runtime projection, advancing account/stage floors, descriptor transfer, external host permission, live reconciliation, and production admission remain expressly deferred. Transfer-time capture's full account-byte comparison is not criticized as a live guard because no live guard is provided by this slice. No production readiness conclusion follows from the inspected code or coordinator-reported tests.

## Initial reviewed SHA-256 identities

Hashes identify files on disk, not a clean Git tree or an executed release. Primary production modules were unchanged across repeated review reads. The stage test changed during coordinator work as described above; final reviewed hash is listed first. Dependencies below were inspected only to the extent needed for the derivation, completion, limit, and side-effect traces, not exhaustively audited.

```text
f6ad1dd9dc3f12aacaac2981954bf210706263e81c0197cd39adf169f07a04ef  tools/inventory_recovery_v3/configuration.py
a906d3c769697f4960c31091b8895fbabcf2ea4bab798d589edf8eb1687a346c  tools/inventory_recovery_v3/public.py
d44253cbd7e376f013c4d012e4fc0de736dff243fb43008dbe5deefb8b413bb7  tests/test_inventory_recovery_v3_configuration.py
76e556da059f8d65603d403650c4810c725548550cb15264ea36841486eb5769  tests/test_inventory_recovery_v3_stage.py
fa98931fdbd07cc0f77231a896c8306672aa87e2a2ab36519f74a64aa478468f  docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md
3cd1627d36b261701afc40e96db316365b6057c9d08f871f1300df2c747a3448  tools/review_inventory_recovery_v3.py
89a6ed354d3168e29e74fe22979b4e82f18dacead90f7bf3e82f9c500ffa1176  tools/prepare_inventory_recovery_v3.py
3d108a9786ce138543c1bf876d6f0f9951210e6a7aca83b39995f7893fb86eb2  tools/inventory_recovery_v3/campaign_binding.py
d64f2210128caf0e009463748210bf7af295a58f8474036f498cbf296431b8c5  tools/inventory_recovery_v3/binding_publication.py
8a77f7c6abb86990e6f8eb4518d186db1dc0cf9d86e95f92f40df2ae62a9dcc6  tools/inventory_recovery_v3/installed_authority.py
f496b46cbbb53a585c4c64e2b390178ed687093fb05a2710d160cd81cc800a6d  tools/inventory_recovery_v3/handover.py
24cc4b61582ddd5e7aad6c67f154dd3370ae407a93bee8b322a42f07316bd350  tools/inventory_recovery_v3/runtime.py
202405fb127c2aaae1f3d5d2c5cc477fcb8cda0536f194576d3f33d26295f7e7  tools/inventory_recovery_v3/campaign_preparation.py
9381409b881a20870f827e79e73de1318416577632a201cc7f654eae328c80df  tools/inventory_recovery_v3/campaign_initialization.py
a72ebdd3e2d45dea79903ae64dac8b65bb915afd73c25c56aa0d390046c38149  tools/inventory_recovery_v3/campaign_history.py
5ced4f768a9288ce83b3b31ce01b86ec7b5ec40d65e97c0ad03ed8169c0acf4c  tools/inventory_recovery_v3/accounting.py
4d0c38981f3d53d0e70c52174a66c28e0eba6f7b197f7dbbddd7f251d14500e2  tools/inventory_recovery_v3/policy.py
fefb6f9600f98f6c71164787558c840492fa19e5675aa57c71b58d2636d5c7b9  tools/inventory_recovery_v3/ancestry.py
0c07f02d5123ce34971f054ef6020a86e9be1dfd67720abe23555a70df041bd2  tools/inventory_recovery_v3/reservations.py
5cfb83a014114a9c1f765349431a2ca4686f8553fc204a7c121fafaeadf4b144  tools/inventory_recovery_v3/semantics.py
616ac738d08498e417d4a99fed0e686b6edabeeba590df9b4ab7924ddd2fb380  tools/inventory_recovery_v3/stage.py
4f7e49bab9bd5355dec597d058e438633ed9edc48c9e132ead27c90cbb07c546  tools/inventory_recovery_v2/runtime.py
80bee63948e44e28310185a5d15de219d77e781b464257a9e7f642e6bee4f399  tools/inventory_recovery_v2/program.py
ae9556df1547e1c28254eea0d060be2904807ad19b357ba74f697cc0341bb84a  tools/inventory_recovery_v2/campaign.py
a1112694eae18ab47e454e4ecccfdd235cd0e7bf65adcfe61c45cd9e2f5345b2  tools/model_routing_policy.py
22c06c05b957b324ccac7731c7769a110b2866bf3367d8f60354cd49a571b583  tools/inventory_history_adoption.py
151e6a01a4e350567377674c958850ded554b4bb24230f5f7c42810a75477e40  tools/inventory_history_handover.py
698c31ebe692c77747567b42814e11662d3f370f8b3610a9ed0aee0b9b5816ef  tools/inventory_history_repair.py
c1576d25d400e3cb9758f069c8a78e92200b0761deafc9524812dbeee04391cc  tools/inventory_history_live.py
ae6e6c2f192685337e98fd1704c785380b2e69d9ac97d5c4a9090a947d3d4f3a  tools/sol_inventory_runtime.py
025b6f65ef8eac9cb7a6a8f2a395a1628a897833ef4ff748a952dfb06827d210  tools/token_epoch_20261025.py
8a17471c237c8d97889884e171e86b354be80e86ccb259aae94ad147a155f879  tools/qualification_history_runtime.py
1346fd80eb12fedd81eecd273ce0b0d9aff4f549965c755cf2685665ddd7b764  tools/qualification_capture_runtime.py
b58800b206c60318602e0e5dbc0ea018f9947923cef3dcadb0e287e8207a4557  tools/response_capture_session.py
a5dee138ad5dfc9d7c45807e19e409a32a641cb19cbe9d1347a08dfda18b6e66  tools/recovery_session.py
8ea9aa4ce6f74651b8b81a3243f657068641d6243998506ac928129f76daf225  tools/model_canary_program.py
956757f6c8985cb99d44c86eb080a27d0a14eede50d06db1f1b3951de380189d  tools/active_session_transport_probe.py
356198faedf073cd26c5188dd4070b8163b130333c96f19ac32533e2714cc7ba  tools/active_session_recovery_program.py
3514c18de789c443cb61277a5770544c40953d7b968872a7440ac09a85b52fb6  tools/active_session_program.py
a892e953476509945a9dbc22c21caa28dbc7ab35d532186b77665453151dc7b6  tools/parallel_verification_replay.py
43c2a66b17305c79bd58624d773d259846cf22acf04cf20cbf217ca97dfe2352  tests/test_inventory_recovery_v3_bootstrap.py
f4c7f2a5c340878382c61e36b076e133ba093fb9045c02243612f6918bd684bb  tests/test_inventory_recovery_v3_campaign_binding.py
3e445a4b1d7bafc50e5b33f13df2629ffba3bea2069a695d306f8639138f219e  src/humanvoice/artifacts.py
```

Earlier inspected versions, superseded during coordinator work:

```text
76acf6003a1be91e0176707abaae2e6be3ecc46878a2a841088fc3381b95be2c  tests/test_inventory_recovery_v3_stage.py (enclosing accounting scope)
065f51bd27d82a01c200613683cd5a9b2ad1cc7d328c704b2b7197e057c38862  docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md
```

## Bounded C1/C2 follow-up — 28 October 2026

### Disposition

- **C1 original missing-evidence path: repaired in inspected source.** `configuration.py:84–103` now requires the completion file, agreement with the preparation receipt, and independently replayed native ownership/first-pair eligibility. It also requires `preparation-authority.json`, exact account/grant/stages path membership, matching captured-content hashes, and agreement with the original account floor/prepared anchor, immutable grant, and initial stage floor. Both new evidence files participate in the observed-file stability checks. Historical authority observations are checked against their original anchors, not equated with mutable current account bytes. The exact completion-schema qualification below remains open.
- **Native ownership replay:** `ownership_preflight.py:18–73` deep-copies the binding's immutable initial journal, uses native history import/request resolution and check-only reservation, and rejects missing membership instead of persisting a repair. Owner checks remain on read/save/lock boundaries. First-pair eligibility includes inherited root/lineage usage, diagnostic handoff, and absence of prospective reservations. This is inspection of implemented preparation completion, not certification of future live ownership.
- **C2 diagnostic-write path: repaired in inspected source.** `inspection.py:9–17` wraps the real native `warm_settlements` with `progress=None`; it does not replace native settlement replay or swallow its exceptions. `configuration.derive()` enters this scope. `delayed_network_runtime.py:40–53` restores aliases in `finally`; native diagnostic publication is conditional on a non-None progress destination. Native integration now checks shared warmup bytes and mtime explicitly.
- The acyclic derivation, five execution-authority fields, inherited/prospective stop composition, cumulative limits, and unconditional live-command rejection conclusions remain bounded to this nondispatching candidate. No new claim of complete dependency closure or actual-production readiness is made.

### C1-R — P3: Completion equality does not enforce exact JSON field types (historical mechanism; see residual recheck)

**Locations:** `tools/inventory_recovery_v3/configuration.py:84–87`; `tools/inventory_recovery_v3/ownership_preflight.py:68–73`; component fixture at `tests/test_inventory_recovery_v3_configuration.py:65–67`.

The repaired comparison uses ordinary Python dictionary equality. Native replay returns integer `new_reservations: 0` and boolean `import_idempotent: True`, but JSON `false` compares equal to integer zero and integer `1` compares equal to boolean true. Equal-valued floating-point replacements for integer counts likewise compare equal. Thus a completion receipt can depart from the claimed exact native record types without rejection.

**Concrete missing regression:** After successful preparation, replace `new_reservations` with JSON `false`, or `import_idempotent` with JSON `1`, consistently in both `ownership-preflight.json` and `preparation.json["ownership"]`. Keep the rest of the native record unchanged. Fresh derivation currently passes these equality checks; the preparation byte hash then binds the newly observed bytes rather than rejecting their schema. A newly derived/rehashed candidate is therefore not a remedy. Also test integer-to-float substitutions in native counts, including nested count maps. The current component fixture substitutes an opaque fixture ownership record, so its missing/changed evidence cases do not pin these native field types. This acceptance trace is statically inspected, not an inspector-executed reproduction.

**Impact and correction:** This is an exact-schema integrity residual, not proof that eligibility replay can be skipped, missing membership inserted, authority consumed, or live dispatch enabled. Native checks still run. Require exact field types (distinguishing bool/int/float), or a type-sensitive canonical comparison to the independently computed native record, and add the paired-document mutations above. The original P2 missing-evidence defect is not being relabeled as an unresolved dispatch issue.

### Follow-up coverage and execution boundary

Inspected additions:

- Configuration tests at lines 194–216 cover missing, altered, symlinked, and late-changing completion/authority evidence. Lines 219–240 exercise structured rehashed stop/contract/predecessor/authority/generation mutations rather than only whole-field replacement.
- Lines 243–253 exercise positive/error JSON for both public read-only CLI actions with component fixtures. Lines 256–268 cover nonzero, pending, and exhausted restart usage; lines 271–280 cover coherent pending campaign inspection without reconciliation. This improves the original composition coverage; component CLI tests are not described as a real-host/native CLI certification.
- `test_inventory_recovery_v3_stage.py:424–505` retains native plan/preparation/campaign binding with installed capture patched away from host files. Configuration is entered directly without an outer accounting scope; lines 479–483 check shared warmup exact bytes and mtime.
- `test_inventory_recovery_v3_inspection.py:12–50` exercises native nonpublishing warmup, no diagnostic writes, propagated errors, and alias restoration. Lines 53–74 exercise retained-journal idempotent reuse, missing-membership refusal, check-only reserve, unchanged bytes/mtime, and owner veto.

**Coordinator-reported only:** Repaired configuration/native preflight: 72 passed in 172.87 seconds; fast configuration/warmup combination: 79 passed in 6.41 seconds; five RetainedJournal/warmup checks passed. These are not independent inspector executions or log verification, and no disjoint aggregate total is inferred. At report finalization the coordinator's exact-member current-source suite identified as `d98433571e61` was still running; no pass is claimed for it and that identifier is not treated as a verified file hash. Earlier 48-case and standalone one-case results above belong to earlier revisions.

**Inspector execution:** Source/document/test inspection, filesystem/Git metadata and SHA-256 inspection, and `apply_patch` edits to this report only. No tests, application entrypoints, native preflight, production preparation, provider calls, service operations, or source/test/master changes. No delegation. Production modules remained unchanged across the follow-up snapshots. The report does not authorize later runtime ownership/floor work or infer readiness from the reported passes.

### Follow-up reviewed SHA-256 identities

These supersede the corresponding initial hashes for this follow-up; they identify inspected files, not an executed release or a clean working tree. Dependencies retained from the initial review remain bounded traces, not an exhaustive dependency audit.

```text
32c2b4e0ef367bad7ce67d5c648a1808e6350aa32c2b6f6f58f36a6b64c31ea9  tools/inventory_recovery_v3/configuration.py
a906d3c769697f4960c31091b8895fbabcf2ea4bab798d589edf8eb1687a346c  tools/inventory_recovery_v3/public.py
1c20c15f17ea6fb5850368633166261de006b3a6a67aa84e93150329f4519ca4  tools/inventory_recovery_v3/ownership_preflight.py
541264e718e95195ad60b104602b089214226b7ab8fc0387642754e05d261c7b  tools/inventory_recovery_v3/inspection.py
ce87c51f99e6840ea7c5502d7308d9590154e87dd922787e187b454879846916  tools/prepare_inventory_recovery_v3.py
ea8e89f44fa61caf2c9256839799a6ea63ca4fb3699cd5da9238fc02f9196485  tests/test_inventory_recovery_v3_configuration.py
ac357a993570ed345d32785ae1d198a770800060942f7231607887f8e7dae105  tests/test_inventory_recovery_v3_inspection.py
e3e1b423e3c09fb451ac26317d76ddaa841b7df5fa20c45c72fa453c5449398d  tests/test_inventory_recovery_v3_stage.py
73ad8df9d25216cd5f81ce2471cfb047f9de5cceb0874fe4a20f55330d34b0b0  docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md
c0bd5aeafbac620f2246492c608bca98c25b1cc833d7bbb8ebbfdf7d052527cf  tools/inventory_recovery_v3/requests.py
520dcacb013e4718174433f2262879a85b1034f2b5c73f538fdc9ee356195092  tools/inventory_recovery_v3/probe.py
5e75a5910f5e2bd278f1f1301d1e3f64fcd8bd200321ee26f22fa0599d59a605  tools/inventory_recovery_v3/registration.py
1dd27c86e3b6fe5fe78b9e89e19932de6c65235193f3edf3fe2bb9a52fcf50fb  tools/inventory_recovery_v3/journal_binding.py
ae5ca2914092d1a964d1643e085c907e40ed1d4bfadf8fcd527e84709f356a91  tools/inventory_recovery_v2/replay.py
e10a67f049342b3e67c38f7d91a044045ef04cf66e072243625e796ad78e7468  tools/delayed_network_runtime.py
```

Earlier inspected follow-up revisions, superseded during coordinator work:

```text
cd4b95c21f218840a83cc7a209fc9e8ecc1fd9ea101c303cf3828fcef9f6e069  tests/test_inventory_recovery_v3_configuration.py
b52351001dbf4e192eefba5b01a35dffaedaa94dbb16f44a02136c31aabf24d1  tests/test_inventory_recovery_v3_inspection.py
f4f029f7f0bd4077e98a0f322db2b9fa80d8e8732dfda41f583660eb3e8f3152  docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md
```

## C1-R bounded residual recheck — 28 October 2026 (historical)

**Disposition: field-level repair confirmed by inspection; one same-scope receipt-type residual remains (P3).** This recheck is limited to the changed comparisons, the digest helper, the native-shaped fixture, and the six new mutation cases. It does not reopen the wider configuration review or later runtime phases.

`configuration.py:85–86` now compares digests of both receipt copies and the independently computed native record. For object records, `humanvoice.artifacts.digest()` serializes with sorted-key compact JSON. Boolean/integer and integer/float substitutions inside those objects therefore produce different bytes, including nested counts. The six cases at `tests/test_inventory_recovery_v3_configuration.py:288–301` mutate both stored copies, retain an independent native-shaped expected record through the fixture at lines 65–72, expect the ownership-preflight rejection, and compare the evidence snapshot before/after derivation. These additions directly cover the previously reported field substitutions; they are inspected, not executed by this reviewer.

### Historical remaining case: the embedded receipt may be a JSON string instead of an object

**Locations:** `configuration.py:84–87`; `src/humanvoice/artifacts.py:15–22`.

The digest helper does not universally preserve input types: strings are encoded directly, whereas objects are JSON-serialized. Let `record` be the valid ownership object and let `serialized` be `json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`. Then `digest(serialized)` equals `digest(record)` by construction, without a cryptographic collision.

Replace only `preparation.json["ownership"]` with that JSON string, leaving `ownership-preflight.json` as the original object. The preparation file itself is still an object, so the existing file-level object check does not reject it. Both digest comparisons then match the independently computed native record. Fresh derivation binds the changed preparation bytes instead of rejecting the non-object embedded completion receipt. This is a static acceptance trace, not an executed reproduction.

**Required correction/regression:** Require the embedded ownership value to be an object before comparing digests, or use a type-preserving encoding that does not invoke the helper's raw-string special case. Add an asymmetric mutation that stores the canonical JSON string only in the preparation receipt, leaves the separate completion file and independent native record unchanged, and expects `BLOCKED_ACCOUNTING` with unchanged evidence. Mutating both file roots to strings would instead hit the existing file-level object guard and would not test this path.

**Impact remains limited:** This is the same exact-completion-schema boundary as C1-R. Native ownership/eligibility replay still executes; no inference, authority consumption, missing-membership repair, or live dispatch bypass is established. Original C1/C2 repairs remain otherwise undisturbed.

### Execution and identities for this residual recheck

The coordinator reports **729 exact-member cases passed in 227.47 seconds before this two-line production change**. That result is historical validation, not a pass for the hashes below. The coordinator plans/runs the source-bound rerun after the tests; no result for that rerun or the six new cases was supplied at this recheck. No tests, application code, native preflight, production preparation, or service operations were executed by this inspector. Only source/test/report inspection, SHA-256 commands, and `apply_patch` on this report were used; no source/test/master edits or delegation.

Current inspected SHA-256 identities for this limited recheck:

```text
56b4e9b5be1883de0ec50910576275deb910c8c097fc0036a8ed176cbd5e7e3b  tools/inventory_recovery_v3/configuration.py
1c20c15f17ea6fb5850368633166261de006b3a6a67aa84e93150329f4519ca4  tools/inventory_recovery_v3/ownership_preflight.py
3e445a4b1d7bafc50e5b33f13df2629ffba3bea2069a695d306f8639138f219e  src/humanvoice/artifacts.py
f9f459a58d8cf58796030a380f87a06838ec472239874783de605e160ed567fb  tests/test_inventory_recovery_v3_configuration.py
```

## C1-R final bounded closure — 28 October 2026

**C1-R: closed by static inspection.** `tools/inventory_recovery_v3/configuration.py:84–88` now requires `isinstance(prepared.get("ownership"), dict)` before either digest comparison. A canonical JSON string, list, or null in the embedded receipt therefore short-circuits to the existing `BLOCKED_ACCOUNTING` rejection. The separate completion file is already required to decode to an object by the scoped reader. With both stored copies constrained to objects, their digest comparisons to each other and the independently computed native object retain JSON field-type distinctions and eliminate the reported raw-string special case. No concrete residual remains in this C1-R check.

**Regression inspection:** `tests/test_inventory_recovery_v3_configuration.py:304–315` adds the exact asymmetric canonical-string/list/null cases. Each changes only the embedded preparation receipt, leaves the separate ownership file intact, expects the ownership-preflight error, and checks the evidence snapshot is unchanged after derivation. The six paired field-type mutations at lines 288–301 remain present. These are source-inspected regression assertions, not inspector-executed pass claims.

**Execution boundary:** The coordinator reports the previous frozen suite completed with **735 cases passed in 209.94 seconds**, with source/authority unchanged during that run. That suite predates this final object guard and is not validation of the final hashes below. At this closure the final fast tests were reported running, and the final exact-member suite was planned afterward; neither final result has been supplied. The inspector ran no tests, application entrypoints, native preflight, production preparation, inference, or service operations. Only the precise guard/test/report locations and file hashes were read, and this findings file was edited using `apply_patch`. No wider audit, delegation, or source/test/master changes occurred.

The earlier C1/C2 repair dispositions stand. Closure covers only the nondispatching configuration candidate; it does not certify full dependency closure, future runtime ownership/floors, host authorization, or actual-production readiness.

### Final residual-closure SHA-256 identities

```text
5beb3f42a0dbebed711b7be057f387a787c0032e4a1684176e80987af5e282a6  tools/inventory_recovery_v3/configuration.py
3823e175aa6de9c1bf8fab0124ede6d6d12fd3589d46883e0d75a28a9b639fdc  tests/test_inventory_recovery_v3_configuration.py
3e445a4b1d7bafc50e5b33f13df2629ffba3bea2069a695d306f8639138f219e  src/humanvoice/artifacts.py
1c20c15f17ea6fb5850368633166261de006b3a6a67aa84e93150329f4519ca4  tools/inventory_recovery_v3/ownership_preflight.py
```
