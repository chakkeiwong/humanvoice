# Retained writer identifier correction and continuation

The held-out reproduction stopped after nine completed writer calls. Writers
001–013 have accepted native results. Writer 014 returned all twenty mapping
rows, but one source identifier lost two characters:
`concept-b1b8a6d8bc3b81a6f13bf9` instead of
`concept-b1b8a6d6d8bc3b81a6f13bf9`. The strict correspondence validator correctly
rejected the response. This is outside size splitting and network recovery.

The user authorized repair, master refresh, a git commit and continued execution.
Master 3.28 / ensemble 118 implements the following bounded continuation:

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

The completed storage-cleanup-20261019 operation relocated 52 historical paths,
including 45 directories at the execution root, into a read-only SquashFS archive.
The original paths are readable symlinks. The first two probes stopped because
native readers resolved those links to physical archive paths before comparing
them with frozen receipt identities. No allowance or evidence bytes had changed.

Use the archive directly through `tools/archive_evidence.py`. Bind the exact
completed relocation receipt and archive image to their SHA-256 checksums, require
the read-only mount, and accept only the receipt's nonoverlapping completed aliases.
The prospective access scope preserves original logical path identities while
reading the archived bytes. Changed targets, missing archives, unexpected nested
links and unlisted aliases remain errors. Native content, membership, settlement,
source and receipt checks remain required. Directory-descriptor verification uses
the checked physical location, while its reports retain their original identity.

Recursive evidence scans include the approved archived trees. Existing empty
historical lock files are opened read-only for advisory locking; other archive
writes are rejected. Spawned settlement workers initialize the same access scope.
Native command dispatch carries it through inventory, preparation, execution and
verification children. Freeze this adapter's source hashes with the identifier
extension. Preserve all original receipts and prior implementation hashes.

Keep new replicas, logs and results on SSD. Leave archive symlinks and image in
place; do not restore entire historical trees or purchase completed responses
again. Regress original account identities, changed targets and bytes, unknown
links, read-only locks, process propagation and restoration of the access scope.
Require the independent zero-provider continuation probe before activation.

## Validation at commit

All 100 tests in the identifier, writer-size-recovery and process-accounting
suites pass. The saved-checkpoint diagnostic passes exact native replay for
all eight newly accepted writers and the corrected final writer, preserves the
five earlier accepted writers, verifies all nine paid calls and their 553,470
reported tokens, and leaves history/account bytes unchanged. It admits no phase
and spends no provider calls.

The combined identifier, archive, size-recovery and process-accounting suite now
passes 113 tests. The real archive-backed parent and child each independently
verify all 198 settlements with 16 workers. Account and grant verification passes
with 694 calls used, 1,306 available, no live reservation and unchanged historical
unknown charges. The independent `probe-04/verification.json` passes: thirteen
retained writers, one derived identifier result, first independent review reached,
no provider calls and unchanged account, grant and predecessor bytes. Freeze this
proof before activation; the adapter does not itself admit the manuscript or
authorize additional spending.
