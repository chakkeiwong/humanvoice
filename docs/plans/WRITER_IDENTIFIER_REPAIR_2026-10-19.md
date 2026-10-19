# Retained writer identifier correction and continuation

The held-out reproduction stopped after nine completed writer calls. Writers
001–013 have accepted native results. Writer 014 returned all twenty mapping
rows, but one source identifier lost two characters:
`concept-b1b8a6d8bc3b81a6f13bf9` instead of
`concept-b1b8a6d6d8bc3b81a6f13bf9`. The strict correspondence validator correctly
rejected the response. This is outside size splitting and network recovery.

The user authorized repair, master refresh, a git commit and continued execution.
Master 3.27 / ensemble 117 implements the following bounded continuation:

1. Independently verify the stopped process, all nine paid receipts, settlement,
   source bindings and the thirteen accepted results. Preserve the sealed stage.
2. Permit exactly one malformed concept identifier with one or two contiguous
   characters deleted, only when the full frozen baseline gives one unique
   match and that match is the sole missing required identifier. Reject valid
   but wrong identifiers, substitutions, duplicates, ambiguity, multiple
   missing mappings and other native failures.
3. Correct only `source_concept_id` in a derived payload. Keep the original raw
   response, native receipt, manuscript text, evidence spans and all other
   mapping fields. Replay the unchanged native writer checks. Record the
   rejected attempt and a separate hash-bound derivation; create no API receipt
   and make no new writer call.
4. In a fresh isolated replica, retain the thirteen accepted writers and add
   the derived result. Run the native humanization workflow through its normal
   successful rewrite outcome. Archive historical pre-transmission denials
   using the existing checked mechanism. Require all fourteen independent unit
   reviews, twenty-seven assembled reviews, build checks and separate
   reproduction verification before admission.
5. Reserve forty-one review calls and the existing fifteen transport extras.
   Use sixteen workers for independent verification and sequential provider
   requests/accounting. Keep 100,000 writer input tokens, 32,000 output tokens,
   depth-three size splitting, fourteen child calls per root, 900-second
   response-free network backoff, 900-second/$4 audits and existing aggregate
   grants. Preserve historical unknown charges.
6. Require regression coverage of exact correction, ambiguity, overreach,
   unchanged source/output, preserved raw response, consumer tampering,
   no repeated writers and controller routing. Run an independent probe through
   the actual native workflow to the first review, with provider calls disabled
   and unchanged predecessor/account/grant bytes. Freeze verification evidence,
   refresh both masters, commit the repair, and activate durable supervision.

The repair is prospective: frozen source modules and earlier proofs remain
unchanged. Its diagnostic is not semantic acceptance. Independent reviews still
decide source fidelity automatically. No new manual intermediate judgment or
Claude review is required. Only final acceptance of the immutable actual ZLB
output is human.

After held-out reproduction: separate verification and settlement; full ZLB
inventory, humanization, review and release; independent ZLB reproduction;
automatic final admission; final human acceptance. At each phase transition or
stop, inspect, settle, verify, repair prospectively when necessary, refresh both
master documents and continue eligible work. A new substantive rejection remains
visible and cannot be converted into a network retry or accepted by this repair.

Controller: `tools/run_writer_identifier_program_20261019.py`.
Supervisor: `tools/supervise_writer_identifier_program_20261019.py`.
Authoritative state: `docs/audits/2026-10-05/master-program/automatic-execution/status.json`.
This identifier admission currently covers the exact retained unit-014 response;
it does not silently reinterpret future writer responses.

## Concurrent storage migration

During validation, the separate storage-cleanup-20261019 operation archived
49 directories in the master execution tree and replaced their original paths
with symlinks. Frozen accounting receipts bind the original real paths, and
native evidence validation rejects symlinked history. The first two new probes
therefore stopped before provider calls. The identifier diagnostic had completed
successfully before this relocation.

Restore required historical directories from the verified archive into SSD
staging, verify membership and content hashes, and replace only matching archive
symlinks with the verified directories. Preserve the archive and all receipt
bytes. Coordinate this restoration with the storage cleanup owner; do not weaken
the frozen path checks or rewrite accounting identities. The controller detects
relocated execution dependencies before spending and records the concrete stop
in both masters. Rerun the independent probe after restoration before freezing
and activating the repair.

## Validation at commit

All 100 tests in the identifier, writer-size-recovery and process-accounting
suites pass. The saved-checkpoint diagnostic passes exact native replay for
all eight newly accepted writers and the corrected final writer, preserves the
five earlier accepted writers, verifies all nine paid calls and their 553,470
reported tokens, and leaves history/account bytes unchanged. It admits no phase
and spends no provider calls.

The independent workflow probe is blocked by the concurrent storage migration,
before any new provider transmission. Consequently no activation proof has been
frozen and live execution has not resumed. Both masters record this limitation;
the 41-review continuation is implemented but awaits the successful isolated
probe after the original execution paths are restored.
