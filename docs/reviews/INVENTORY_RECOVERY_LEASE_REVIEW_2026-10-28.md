# Inventory recovery lease component review — 28 October 2026

Disposition: **two actionable findings; OD5 component acceptance remains open.**

## Scope and evidence

One findings-only inspector reviewed `tools/inventory_recovery_v3/ownership_roles.py`,
`tools/inventory_recovery_v3/ownership.py`, and
`tests/test_inventory_recovery_v3_ownership.py` against the OD1/OD4/OD5
component portions of `docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md`.
The added provider/campaign-consumer, successive-job, and partial-duplication
tests were included. Reviewed source hashes:

```text
d5c51d4479729b2579ea6845fb73fbbf8536eb6ddee69ee093447cc99d30a58f  ownership_roles.py
219ba8b7147aca7336c83eede3502688e7538fbd2965b7cb4f6cd85ff93f44a1  ownership.py
75671fa0ef925fbefe373ddc4ddd73162adade8915a541f10bf9f9b237a4a51f  test_inventory_recovery_v3_ownership.py
```

Independent run: `PYTHONDONTWRITEBYTECODE=1 /home/ubuntu/miniforge3/bin/python
-B -m pytest -q -p no:cacheprovider tests/test_inventory_recovery_v3_ownership.py`
completed with **56 passed in 5.59s**. The user's broader 166-case pass and Ruff
result were reported separately and were not rerun here. Three bounded,
stdin-fed Python probes used only temporary directories and real local file
locks; their concrete results are recorded below. No source or test was edited.

During final verification the user extended the parent-death test to monitor,
worker, campaign, and provider roles. That final test-file SHA-256 was
`c093d488a43fb37a07d18cfe2ece12b3adc1d5f194be8ab3c751d5085cf84309`; both
reviewed source hashes remained unchanged. A targeted run of
`test_complete_union_survives_parent_death_until_grandchild_finishes` passed
all **4 cases in 2.33s**. The 56-case result above belongs to the preceding
test snapshot; it is not a claimed full-suite run of the final snapshot.

## LR1 — P1: Replayed transfer cleanup closes a different live lease's reused FDs

**Location:** `ownership.py:201–213,217–224`, especially the unconditional
`close_all(incoming)` in the failure path.

**Failure path:**

1. Duplicate a valid parent's union into explicit incoming tuple R; consume
   capsule C with `inherit(..., received=R)`. It creates lease A on new
   descriptors, closes R, and records C as consumed.
2. Borrow from a newly generated capsule of A into lease B. Ordinary `os.dup`
   allocation naturally reuses every now-free number in R; no tampering with
   B's private fields or `dup2` is required. B is complete and passes `check()`.
3. Retry stale C with the original `received=R`. These numbers now refer to B's
   legitimate duplicates of the same open file descriptions, so validation
   passes. The consumed-identity check rejects C, but `finally` still closes R.
   This destroys B's references even though the first call already completed
   the ownership transfer.

The first probe produced identical incoming/live tuples `(11, 12, 13, 14, 15,
16, 17, 18)`, raised `Entrypoint capsule was already consumed`, and then failed
B's `check()` with `ValueError: Cannot prove inherited descriptor ownership`.
A second probe closed A and the original parent before the retry, leaving B as
the sole owner. After replay rejection, **all 8 of 8 competing acquisitions
succeeded while B still had `_active == True`**. This is loss of exclusion, not
only an error-reporting issue. It also leaves B's cleanup holding stale numbers
that can be reused again. No `LOCK_UN` was needed to trigger the failure.

**Required correction:** Give the executable-entry transfer an explicit
single-use ownership state, and consult it before claiming cleanup ownership
of raw FD numbers or invoking callbacks that can fail. A retry of an already
consumed/rejected transfer must not close numbers from its old tuple. Only the
first entry attempt may own and close its explicitly transferred originals.
Retain ordinary cleanup for a genuinely new rejected transfer. Merely moving
the replay check above descriptor validation while retaining the current
unconditional `finally` does not fix this.

**Required regression:** Extend
`test_entrypoint_closes_originals_and_rejects_replayed_capsule` with the sequence
above: create A by transfer, create B by borrowing A's fresh capsule, assert
natural reuse of R, close ancestors, and retry C. Require rejection, B's
`check()` and regenerated capsule still valid, all competitors still excluded,
and release only after B exits. Repeat with a replay-time leaf veto and with
old numbers reused for unrelated sentinel FDs; stale cleanup must preserve
both. The current test deliberately restores R using `dup2` into otherwise
unowned numbers, so closing them does not expose this defect.

## LR2 — P2: Early entry rejection does not consume the incoming capsule

**Location:** `ownership.py:203–213`; compare the explicit single-use-on-
rejection promise at `ownership.py:192–194`.

**Failure path:** A valid C/R transfer reaches `lease._prefix()` with a vetoing
leaf. It rejects and closes the incoming originals, but never reaches
`_consumed.add(...)`. If the same numbers subsequently refer to valid duplicates
of the still-held ancestor descriptions, C is accepted on another entry once
the leaf returns true. The same ordering leaves derivation, validation, and
received-union failures before line 213 outside the consumption record.

The temporary-lock probe retained the parent's real locks, built C/R from
duplicates, rejected the first entry with `leaf=lambda: False`, then restored R
with `os.dup2(parent_fd, received_fd)`. Retrying the **identical** C/R with a true
leaf activated a second entry lease. Observed output:

```text
first_entry_rejected: Leaf admission or stop predicate vetoed ownership
rejected_capsule_consumed: False
same_capsule_same_fds_accepted_after_veto: True
parent_still_valid: True
```

**Required correction:** Retire an explicitly owned transfer on its first
entry attempt, including failures before lease construction/validation
completes. Define how rejected/malformed input is associated with that transfer
without requiring successful validation first. Coordinate this with LR1 so a
retired transfer cannot reacquire cleanup ownership of reused FD numbers.
Borrowed component checks must remain non-consuming and must not close their
caller's references.

**Required regression:** Add a test beside
`test_entrypoint_rejection_closes_only_explicit_incoming_references`: first
reject a valid transfer at the initial leaf, confirm original references are
closed, remap its FD numbers to retained valid duplicates, then retry the same
capsule with the leaf now passing. Require replay rejection before any new
lease activates and preserve references now owned elsewhere. Cover an early
derivation exception and validation failure as well as leaf veto. Existing
tests check early cleanup and successful-entry replay separately, missing this
combined rejection/reuse path.

## Bounded remainder

No additional actionable finding was established in the remaining scoped
component paths. The actual derived order is predecessor monitor/jobs by
chain, sorted historical execution/executor pairs excluding the separately
bound program resource, program, campaign, monitor, then exact job and stage
additions. Name/path/inode conflicts reject. Acquisitions and duplications
validate their held prefix; activation requires the complete set. The reviewed
native campaign status reader does not call its ownership guard, and the
component does not itself insert a full-lease callback into its leaf predicate.
Process-local checks bind PID/start ticks/boot identity. Borrowed inheritance
and stage extension duplicate references, and ordinary unwind closes owned
references without `LOCK_UN`. The final parent-death test passes for each
monitor/worker/campaign/provider union retained by the surviving subprocess;
provider-union addition and actual campaign consumption are also covered by
the added component tests. This does not establish the future live
launcher/provider integration edges.

Public admission/immutable predecessor closure and live launcher/collector
integration remain explicitly excluded next units. Caller-supplied component
`derive`/`leaf` functions are not execution authorization. `public.py:22–24`
still rejects live actions before configuration inspection. Closed schema and
descriptor-proof reviews were not reopened. Human approval settings were
verified through the prescribed `humanvoice_manual_approvals.py check`; no
privileged action, production/provider/service action, or master edit/restart
was performed. The only persistent review write is this file.

## LR1/LR2 closure recheck — 28 October 2026

**Disposition: LR1 and LR2 are closed for the reviewed component revision.**
This disposition supersedes the initial open status for these two findings;
the original failure evidence above is retained. No further actionable finding
was established in this bounded repair recheck.

Reviewed SHA-256 values:

```text
77e0cc6d6fbcf9358265b02a422d285452cb01414fcad898a7dca025de450e93  ownership.py
d5c51d4479729b2579ea6845fb73fbbf8536eb6ddee69ee093447cc99d30a58f  ownership_roles.py
5cd73c6908a41953bef2f9081a33866447a340995f671b8666d79e071f458132  test_inventory_recovery_v3_ownership.py
```

**LR1 closure.** `IncomingTransfer` (`ownership.py:36–63`) checks and retires
the envelope digest and available nonce under the process-local registry lock
before assigning ownership of the incoming references. `inherit()` constructs
that transfer before entering its cleanup scope (`ownership.py:228–249`). A
consumed-input rejection therefore acquires no cleanup ownership, invokes no
derivation/leaf callback, and cannot close numbers belonging to another lease.
The first claimant empties its received tuple before closing originals, making
its success/finally cleanup idempotent.

Independently repeated the original natural-reuse failure sequence with only
the remapped survivor left alive. Both the identical capsule and a rehashed
envelope retaining its nonce rejected before callbacks; the survivor continued
to pass `check()` and **all 8 of 8 locks remained excluded**. The updated
regressions additionally pass for replay-time leaf veto and unrelated sentinel
FDs occupying the old numbers (`test_inventory_recovery_v3_ownership.py:212–238,
281–299`).

**LR2 closure.** Claiming the transfer now precedes `Lease` construction,
initial derivation, leaf checks, and capsule validation. Their failures retain
the retirement record while closing first-attempt originals. The independent
probe exercised initial leaf veto, derivation exception, inode-validation
failure, and malformed JSON-shaped input. Every first attempt closed its
originals; after natural FD-number reuse, replay rejected before callbacks and
preserved every restored reference. The corresponding repository cases also
pass (`test_inventory_recovery_v3_ownership.py:241–278`). Borrowed inheritance
still creates no incoming transfer and retains its non-consuming contract.

**Verification.** The same isolated command documented above completed with
**63 ownership cases passed in 7.78s**, including borrowed cleanup, full unions,
and all four parent-death roles. An additional temporary-lock/thread probe
paused the first claimant inside derivation, attempted a concurrent second
claim, and confirmed that the second rejected without invoking callbacks or
closing originals; the first then completed successfully. The user's
173-case combined pass and Ruff pass were reported, not independently rerun.
All independent probes used temporary files and no source/test edits.

This closes only LR1/LR2 in the component. It does not promote public admission,
immutable predecessor closure, live launcher/collector integration, or grant
execution permission. The roles module is unchanged; closed schema/descriptor
proof reviews were not reopened. Human approval settings were rechecked using
the prescribed helper. Only this review was appended; no production/provider/
service action, master edit/restart, or privileged execution was performed.
