# OD2 / OD2-R descriptor implementation review — 28 October 2026

Disposition: one P2 regression-oracle finding (DR1). No additional implementation
defect was established in this bounded inspection. The verifier and inspected
consumer adaptations satisfy the examined code paths; the claimed parent-death
regression acceptance remains incomplete until DR1 is repaired. Coordinator
owns all fixes.

## DR1 — P2: The grandchild test accepts failure of its final ownership proof

Location: `tests/test_inventory_recovery_v3_descriptors.py:240–277`, especially
246, 251–254 and 269–274.

The grandchild sends its only acknowledgement after the first
`exclusive_descriptor()` call. After the test confirms the parent has exited,
it sends the release byte; the grandchild then performs a second ownership
check and closes its FD. The test observes only that a competing acquisition
eventually succeeds. An exception in that second check also exits the process
and releases the FD, satisfying the same success condition. Grandchild stderr
is discarded, its `Popen` object is discarded by the exiting parent, and
neither a second success acknowledgement nor its exit status is checked.

There is no handshake ordering the first check after parent death: `Popen` can
allow the child to complete that check before the creator executes
`os._exit(73)`. Joining the parent before reading the already-buffered first
acknowledgement does not establish when the check occurred. Consequently a
failure specific to post-parent-death verification can escape the required
OD2 test. This does not establish a defect in the present verifier or kernel
exclusion; it establishes a concrete false-pass in the acceptance oracle.

### Reproduction executed during review

Run from `/home/ubuntu/workspace/humanvoice`. This replaces only the generated
subprocess source string in the inspector's Python process; it edits no
source/test file, uses temporary fixtures, and launches no provider.

```sh
/home/ubuntu/miniforge3/bin/python -B - <<'PY'
import json, sys, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path[:0] = [
    '/home/ubuntu/workspace/humanvoice',
    '/home/ubuntu/workspace/humanvoice/src',
    '/home/ubuntu/workspace/humanvoice/tests',
]
import test_inventory_recovery_v3_descriptors as test
native = test.subprocess.Popen
marker = 'os.read(stop,1);exclusive_descriptor(path,fd);os.close(fd)'
def spawn(args, **kwargs):
    args = list(args)
    index = args.index('-c') + 1
    assert marker in args[index]
    args[index] = args[index].replace(
        marker,
        "os.read(stop,1);raise ValueError('forced post-parent-death ownership failure')",
    )
    args.insert(1, '-B')
    return native(args, **kwargs)
with tempfile.TemporaryDirectory(prefix='humanvoice-od2-test-oracle-') as directory:
    with patch.object(test.subprocess, 'Popen', spawn):
        test.test_grandchild_retains_verified_lock_after_parent_death(Path(directory))
    print(json.dumps({'existing_grandchild_test': 'PASSED',
                      'injected_fault': 'post-parent-death proof always raises'}))
PY
```

Observed: the existing test returned successfully despite the forced
`ValueError` at its final verification point, in approximately 0.47 seconds.

Required closure: assert a distinct successful verification acknowledgement
after the test has confirmed the creator's death. Keep the grandchild holding
the FD after that acknowledgement until a separate release signal, and require
successful termination or an equivalent unambiguous completion record. Forced
failure at either proof must fail the regression; normal inherited ownership
must continue excluding the competitor until release. This repair fits the
existing descriptor regression and requires no future lease/collector unit.

## Examined behavior and evidence

- `descriptors.py:18–56` reads descriptor-specific fdinfo twice, requires one
  whole-file `FLOCK ADVISORY WRITE` record for the exact regular-file
  device/inode, checks descriptor/path identity, and performs no flock, dup,
  close or unlock. Missing/unsupported/ambiguous metadata fails closed.
  Shared/fresh FDs cannot pass merely because another FD owns the same inode.
- `job_ownership.py:9–22` clones functions into a private namespace and binds
  the private `binding` clone and new verifier without assigning to historical
  module globals. Private namespace identity and unchanged historical
  `exclusive_descriptor`, `binding`, `prepare`, `require` identities were
  independently checked after exercising the consumers.
- Independently ran the four existing borrowed-consumer regressions at test
  lines 152–232: campaign bootstrap/history; launch handoff/private job
  prepare/require; campaign authority/stage; chained handover. All passed
  using temporary fixtures with the old verifier and flock forbidden inside
  the borrowed sections. Incoming campaign, handoff and chain descriptors
  remain usable after borrowed scope exit.
- `CampaignHistory.owned` calls flock only for newly opened acquisition. Its
  inherited branch verifies and duplicates, then closes the duplicate.
  Handoff/handover also close owned duplicates rather than incoming FDs. The
  launcher imports the private job adapter. No residual use of the historical
  verifier was found in the named prospective consumers.
- Additional temporary observations retained the same fdinfo WRITE entry
  across creator death. A read-only-open exclusive FD passed the verifier and
  campaign borrower without leaking FDs. The campaign borrower left incoming
  fdinfo flags/lock metadata unchanged. These support the implementation but
  do not repair DR1's regression oracle.
- Coordinator reports focused 37 and adjacent 428 tests passing; these are
  attributed results, not an inspector rerun. The inspector independently
  exercised the four consumer paths and targeted counterexample. The prior
  R1–R4 schema/performance, executor and floor passes are historical after
  source changes; this review does not re-certify those separate units.

## Scope and controls

Reviewed `descriptors.py`, `job_ownership.py`, descriptor adaptations in
`stage_authority.py`, `launcher.py`, `stage_owner.py`,
`campaign_initialization.py`, `launch_handoff.py`, `handover.py`,
`campaign_history.py`, and `tests/test_inventory_recovery_v3_descriptors.py`,
against OD2/OD2-R and implementation unit 1 of
`docs/plans/INVENTORY_RECOVERY_PUBLIC_ADMISSION_2026-10-28.md`. Historical
helpers/fixtures were read only to trace these dependencies.

Full ancestor lease/role forwarding, immutable runtime guards and collector
final spawn are explicitly outside this review. Their absence is not a
finding or a claim made by this component. Cross-role inode conflict handling
belongs to the next role-mapping unit. This report grants no launch permission.

Read `/home/ubuntu/AGENTS.md` and repository `AGENTS.md`. The prescribed manual
approval `check` and `status` confirmed on-request/user/workspace-write settings
and stopped production. No privileged execution was needed. No production
action, provider call, source/test/master edit, frozen-evidence edit or second
inspector was performed. Only this report is a persistent review write; probes
used temporary fixtures and disabled Python bytecode writes.

Final inspected-file SHA-256 values (unchanged during final consumer checks):

```text
a51a39450755b8f786c5b4f2d08126c5c75f25baad1dffadd5b459b1626743dc  tools/inventory_recovery_v3/descriptors.py
615760caa3c89b864e607b2fea71c2f481b1142637f068b60b3d9342beb413d6  tools/inventory_recovery_v3/job_ownership.py
cbcea2b0a47418f7016fa0ef03d2caacb67be1d09e6fb05f74d6239fa651e59b  tools/inventory_recovery_v3/stage_authority.py
79f82f88df2ae626def4e03147ce710d886724527f26d17fa5daff0be37340cb  tools/inventory_recovery_v3/launcher.py
44918e999afb8580abb373b278aa3893826cd60f29ac1d4c7e85ebe50b03bdca  tools/inventory_recovery_v3/stage_owner.py
0e0dbef5a4950285fdbc3eee063104368f3a69f6ea0c0822257edc25ce4c5933  tools/inventory_recovery_v3/campaign_initialization.py
580dcbf754f863c501f77de4c13cd2139e4f4a828d29d726fd7417a553d739ee  tools/inventory_recovery_v3/launch_handoff.py
aa536804935b81b15772474142404c963a05192d8a829a6e32f7d31fb7aa67b4  tools/inventory_recovery_v3/handover.py
13b17af7e9439169a7d861bf30232d7d0c21c0eccebb46dd1dbe031627b3d3a0  tools/inventory_recovery_v3/campaign_history.py
ca3037b0a73a7733393c9afae4db4efbce31479f3072bda4fb6b657d1de9e091  tests/test_inventory_recovery_v3_descriptors.py
```

## DR1 bounded recheck — closed, 28 October 2026

This appended disposition supersedes the initial open DR1 status. **DR1 is
closed; no remaining findings in the bounded OD2/OD2-R descriptor review.**
This recheck addresses only the regression repair and does not expand the
original component scope or grant public/production launch permission.

Reviewed `tests/test_inventory_recovery_v3_descriptors.py:235–327`. The repaired
helper now joins the creator and requires exit 73 before sending `v`
(284–289). The grandchild cannot execute its first proof before that signal
(245–248), and sends `verified` only after the proof succeeds. It then waits
for the separate `r` release signal; the test checks competing acquisition
still fails during that interval (290–294). The final proof and explicit FD
close precede `complete` (251–253). The test requires `complete`, pipe EOF and
eventual competing acquisition (295–305), so exceptional exit alone no longer
satisfies its success condition. Cleanup records the child's durable identity
and checks it before signaling (286–287, 313–317).

Independent execution used the absolute Python interpreter, `-B`, temporary
fixtures and an in-memory `Popen` wrapper adding `-B` to each grandchild:

- The repaired real parent-death positive test passed, including verified
  acknowledgement, retained exclusion, complete, EOF and eventual acquisition.
- Both new negative cases (`failure='initial'` and `failure='final'`) passed
  their required missing-ack `AssertionError` expectation.
- Independently wrapped the actual `exclusive_descriptor` function inside the
  generated grandchild source, without using the helper's `failure` argument.
  A call counter raised `ValueError` on proof 1, then on proof 2 in a separate
  run. Each run was rejected with exactly
  `Grandchild verification acknowledgement missing`. This independently
  reproduces the formerly undetected failure at the repaired proof boundary.

All five targeted executions completed in approximately 0.24 seconds after
imports (approximately 0.67 seconds for the complete Python command). All nine
production-file SHA-256 values match the original report; no implementation
re-review was needed. The repaired test file remained unchanged during the
recheck and has SHA-256:

```text
e48b8eb9cee1dd6170c21773ef7161f69c3c84affe72072b264d1f6c1e3d6e5f  tests/test_inventory_recovery_v3_descriptors.py
```

Coordinator reports 430 adjacent tests passing in 4.96 seconds with 16 workers
and Ruff passing. Those remain attributed results, not additional inspector
runs. Only this report was appended persistently; no source/test/master or
production changes and no provider calls were made.
