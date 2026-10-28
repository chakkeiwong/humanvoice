# Durable control publication implementation slice — 28 October 2026

This prospective slice implements the missing producer behind
`stop_authority.verify`; it does not authorize a live launch. Provider P1
review is independently closed and the repaired 12-case executor gate passes
with unchanged source/authority. Its source/test freeze has ended, so this
control slice may proceed. A host-protected witness service is not installed.

## Trust boundary

Keep control authority in a host-protected witness, such as a narrowly scoped
root-owned broker with durable monotonic storage. A directory outside the
workspace is insufficient if the provider worker can rewrite its head. The
witness accepts atomic compare-and-swap on a monotonic sequence, authenticates
every response, and retains the full pending command so the client can recover
after dying immediately following prepare. Runtime readers receive read-only
capability; they cannot publish or impersonate the control client. If this
host boundary cannot be installed and independently reviewed, production stays
blocked.

The fixed release-bound host installer/control command is the writer. Its
absolute executable, script, action, release/configuration/preflight hashes,
control witness identity and initial exact stop/resume set must be included in the
grouped host approval. A program-written authorized_by field, a fixture
callback, or a workspace hash chain is not authorization. The reader derives
the one fixed external location from admitted configuration; it accepts no
caller-selected alternate history. Never install this store during offline
tests or infer permission from directory existence.

The authenticated witness holds `{sequence, genesis, committed_head, pending}`.
Initialize it from the release/preflight/configuration and approved initial
stop/resume set. `prepare(expected_sequence, expected_head, event)` atomically
verifies the prior head and retains the full pending event. `commit(sequence,
event_identity, new_head)` advances once. Each read authenticates the witness
and compares it with local committed evidence. This prevents workspace rollback
from deleting or rolling back the witnessed stop floor; it does not claim
protection against the host witness administrator rolling back its own protected
storage. If host isolation cannot be established, admission stays blocked.

## Transaction

1. Under an exclusive control lock, validate the exact admitted configuration,
   inherited contracts, external genesis/head and existing committed prefix.
   Verify all regular paths without symlink traversal. Missing initialized
   state is corruption; never reconstruct an empty head from current files.
2. Authenticate the fixed host action. Resume names the latest exact stop
   bytes for every selected root and its original contract. Initial adoption
   must bind the user-approved resume set explicitly; inherited resume files
   alone cannot manufacture provenance. Stop request IDs are unique and times
   strictly increase even across clock regression. Repeated exact commands
   reuse their retained transaction identity.
3. Call authenticated witness `prepare` first with compare-and-swap on previous
   sequence/head. It retains the complete pending event and immediately vetoes
   dispatch. Then write/fsync the local pending-head projection and immutable
   event. A crash after prepare but before local publication is recoverable from
   the witness's retained command, without reauthorization or sequence charge.
4. Project the exact stop/resume bytes into their existing canonical paths;
   fsync each parent. Never delete the latest stop to resume. A new stop
   invalidates any prior resume. Clear pending only after all projections
   match; reject conflicting projection bytes instead of silently replacing
   arbitrary evidence. The same locked repair command completes any coherent
   interrupted transaction without a new authorization or sequence charge.
5. Commit witness sequence/head after the event, projections and local committed
   head are durable. A crash before witness commit remains vetoed and is finished
   by the fixed repair action. Read-only runtime inspection authenticates a
   stable external witness before and after complete prefix/projection reads.
   Concurrent publication gives a retryable veto; missing/rolled-back evidence
   gives persistent stop/integrity veto. Inspection never repairs or writes. Return
   the exact existing stop_authority evidence shape, including raw UTF-8 bytes.

## Required executable checks

- Native reader/RuntimeLeaf integration for initial no-stop, inherited stop,
  one/two subsequent stops, explicit latest resume and cold restart.
- Kill writer before/after intent, event, witness, each workspace projection,
  and final commit; reopen twice and require one immutable event and no
  unauthorized resume. Read-only checks at every cut must never dispatch.
- Roll back/delete workspace stop, resume, head and complete workspace tree
  while retaining external witness; reject each. Delete committed external
  members or initialized head; reject without creating replacements.
- Reject forged resume, wrong configuration/root/contract/action, stale stop,
  reused request ID, duplicate/reordered events, extra/missing membership,
  alias/symlink, permissions drift and old external witness selection.
- Concurrent stop versus resume, writer lock contention, read publication
  races, ENOSPC/fsync failures, newline changes and decreasing wall clock.
- An adversarial writer changing a projection after the final retained-byte
  check but before rename. The host installer must ensure projection ancestors
  and existing control-file inodes are not writable by the workspace identity;
  descriptor-relative access alone does not make compare-then-replace atomic.
- Public CLI remains unavailable until genuine host provenance, release and
  factory composition are tested; temporary fixture stores are identified as
  fixture boundaries, never production authority.

After this slice: actual Monitor configuration/constructor and public factory;
TX4/CP3 transaction reconciliation, TX5 stale unspent plans, TX6 receipt-only
progress, TX7 bounded replay; full dependency binding and current-source release.


## Concrete next implementation boundary after crash recovery

Master 4.30 / ensemble 220: both existing gates passed (891 floors, 12 executor). The failed native
preflight was a cursor/lock fixture disagreement, not permission to remove the
runtime lock-membership check. Their exact source/authority receipts are retained; the source freeze ended
after both completed. The next slice is staged separately until review.

Implement the host witness in a separate bounded slice before public factory
composition. Use one local Unix-domain service with a root-owned socket and
protected durable storage. Readers verify canonical socket/parent ownership,
connect with a finite deadline, authenticate the kernel peer UID, and bind a
fresh request nonce, exact genesis and configuration to every returned snapshot.
The read command cannot initialize, prepare, commit or repair state. The service
allows state-changing commands only from the separately approved privileged
control process. Same-user workspace writers receive read access only; a path
outside the workspace does not make them trusted writers.

The durable witness stores its exact genesis, monotonic sequence, committed head
and full pending event in one atomic transaction. Prepare compares both previous
sequence and head, retains the complete authorized event and makes dispatch
unavailable. Repeating the identical prepare is idempotent; another request or
a stale base is rejected. Commit must bind the retained pending identity and
next head, advance once, and retain enough information to recognize exact
commit retries after a dropped connection. Neither read nor restart recreates
missing initialized storage. The privileged publisher still owns the ordered
workspace projections described above; broker commit alone cannot authorize
arbitrary workspace mutations.

Verification order: transaction/CAS/idempotency fault tests; actual local socket
nonce/peer/read-only tests; process death and durable reopen; malicious workspace
rollback with a stable witness; RuntimeLeaf and public factory integration. Test
stores/peer identities may be fixtures but must remain marked as such. A passing
fixture service is not production admission. The final installer must copy the
reviewed frozen dependency bundle to a protected location rather than execute
root imports from writable workspace code, bind configuration/release/preflight
and initial control bytes, and expose only fixed host actions for approval.
No host action or production start is required to build and test this slice.


## Execution increment 4.30 / 220

1. Save the validated recovery implementation/tests and candidate in a scoped
   Git checkpoint. This is not a dependency-complete release or deployment.
2. Add explicit stop/resume command semantics over the admitted initial stop
   floor. Only the protected host writer constructs time/request provenance;
   runtime inspection cannot reconstruct or authorize a resume.
3. Persist witness pending first, publish exact local intent/event/projections,
   publish the committed local head, then commit the witness. Reopening twice
   at every publication cut must converge without a new sequence or approval.
4. Bind a stable authenticated before/after witness read to native stop_authority
   evidence; test rollback, missing/corrupt files, stale resumes and late stops.
5. Review corner cases and run the bounded 16-worker suite. Keep fixture
   privilege adapters explicit. Full host installation/factory/soak/release
   remain open until their own real integration evidence exists.


## Refreshed execution checkpoint 4.31 / 221

The implementation and corner review completed offline. The candidate now records
147 exact tests, including 23 real process-death cuts (18 publication and five
initialization), native RuntimeLeaf/stop-authority integration, read-only Unix
socket integration, concurrent publication, repeated storage failure, fsync
retry, symlink/race, rollback, stale/forged command, JSON-null corruption, and
monotonic initialization-reset regressions. The exact 16-worker run passed all
147 cases in 2.63 seconds; Ruff passed; the approval-policy regression passed
56 tests. Collection and execution membership each contain exactly 147 cases with
no skips, deselections, collection errors, or mismatch. Evidence is retained in
`.localresources/control-witness-20261028/publication-final-exact.xml`,
`publication-collected.json`, `publication-executed.json`, and
`candidate-status.json`.

The review closes the candidate-level JSON-null and zero-sequence initialization
reset defects. The candidate remains outside public runtime admission. Protected
host installation/database recovery, independent host-boundary review, supervisor
diagnostics, public factory composition, bounded full-history replay, TX4–TX7,
native multi-successor/soak, release validation, and live ZLB execution remain
open. Production remains stopped; no model call, service start, deployment, or
ZLB receipt was performed.
