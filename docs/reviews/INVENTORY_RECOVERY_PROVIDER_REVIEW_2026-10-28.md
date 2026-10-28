# Bounded provider review — 2026-10-28

Review window: 06:45–06:52 UTC (14:45–14:52 Asia/Shanghai). One inspector; findings only. Read `/home/ubuntu/AGENTS.md`, project `AGENTS.md`, and the documented human-approval policy. Source and tests remained frozen.

## Finding

### P1 — A post-fork `Popen` OSError is incorrectly certified as zero launch

**Location:** `tools/inventory_recovery_v3/provider_capture.py:98–102`, with the incorrect result returned at lines 184–185 and consumed by `provider_runtime.py:99–103`.

The blanket `except OSError: known_unstarted = True` does not establish that the executable never started. On this environment's actual Python implementation, `subprocess.Popen._execute_child` first forks/executes the child, then reads its exec-error pipe with `os.read(errpipe_read, 50000)`. An OSError in that parent-side read can occur after the child is running. Since the constructor has not returned, assignment to the collector's `process` variable never occurs. The collector skips all process-group cleanup, creates empty streams, and returns `ZeroLaunch(error, True)` without `process-start.json` or `process.json`.

**Reproduced:** Injected one OSError into that specific exec-error-pipe read, leaving the real `subprocess.Popen`, fork/exec, final guard, and descriptor passing intact. The fixture executable wrote its PID to a marker and slept. Collector deadline was 0.2 seconds. The returned result was:

```json
{
  "result_type": "ZeroLaunch",
  "cleanup_complete": true,
  "error": "post-fork exec-error-pipe observation cut",
  "real_child_pid": 682817,
  "child_still_alive": true,
  "process_start_exists": false,
  "process_exists": false,
  "streams_empty": true,
  "fds_still_open": true
}
```

This violates the slice's no-false-zero-launch and bounded-cleanup requirements. The integration accepts this typed result as proven unstarted and calls `rejection.publish`; its generated process record states `process_started: false` and `group_quiescent: true`. That downstream publication follows directly from source inspection; the probe directly reproduced the collector's false proof and live escaped fixture child. A real child could continue provider activity beyond the deadline while the caller records zero launch.

**Required correction:** Treat constructor exceptions after a spawn attempt as uncertain unless the launch mechanism positively establishes no exec and reaps any child. Do not infer that proof from the exception class. Preserve access to child identity/cleanup across constructor failures, or retain an explicitly ambiguous outcome without publishing zero-launch evidence. Add coverage for a real child plus an exception in the parent's post-fork constructor path; a mocked `Popen` that immediately raises `FileNotFoundError` does not cover this case.

**Minimal reproduction core** (run with bytecode disabled and the repository on `PYTHONPATH`; `root` is a fresh temporary directory and `fds` are four held flock descriptors):

```python
marker = root / "spawned.pid"
program = ("import os,time;from pathlib import Path;"
           f"Path({str(marker)!r}).write_text(str(os.getpid()));time.sleep(30)")
original_read = capture.os.read
injected = []
def read(fd, length):
    if length == 50000 and not injected:
        injected.append(fd)
        raise OSError("post-fork exec-error-pipe observation cut")
    return original_read(fd, length)
capture.os.read = read
try:
    result = capture.launch(
        [sys.executable, "-B", "-c", program, "--output-last-message",
         str(root / "response-envelope.json")],
        "fixture", root, lock_fd=fds[-1], before_spawn=lambda: fds,
        deadline=0.2, byte_limit=1024)
finally:
    capture.os.read = original_read
# Wait up to three seconds for marker, then observe:
# isinstance(result, capture.ZeroLaunch) and result.cleanup_complete
# os.kill(int(marker.read_text()), 0) succeeds.
# ALWAYS killpg(child, SIGKILL) and waitpid(child, 0) after observing.
```

The live fixture child was explicitly killed and reaped: PID **682817**, wait exit code **-9**, `/proc/682817` absent. Probe parent **682816** exited **0**, also absent. No live provider executable or authenticated provider call was used.

## Bounded verification and scope

- Independently ran only `tests/test_inventory_recovery_v3_provider_capture.py` and `tests/test_inventory_recovery_v3_provider_runtime.py`: **28 passed in 28.22 seconds**, **16 workers**. The supplied full 164-test result and Ruff result were not rerun or represented as independently verified.
- Command: `PYTHONDONTWRITEBYTECODE=1 /home/ubuntu/miniforge3/bin/python -B -m pytest -q -p no:cacheprovider -n 16 --basetemp=/tmp/humanvoice-provider-review-20261028-focused tests/test_inventory_recovery_v3_provider_capture.py tests/test_inventory_recovery_v3_provider_runtime.py`. A read-only supervisor sampled process ancestry every 25 ms; fixture files stayed under the temporary test root.
- Passing cases include all ten rejection publication cuts; retained rejection replay with no resend; conflicting retained process evidence; normal native receipt validation; final FIFO veto; inherited full FD union including real creator death; stream/deadline limits; process-start/heartbeat write cuts; observer failures; and native/shared qualified/capture namespace preservation. Read the five scoped source files and both scoped test files, with direct dependencies inspected only to establish these behaviors.
- No additional reproduced finding from those paths. The independently closed ownership P2 was not reopened. Runtime/control/prepare fixture boundaries remain explicit; public factory, real authenticated control producer, TX4–TX7, and release were excluded. This is not release approval.
- Permission check used the documented absolute Python/script path with `-B`: settings were `on-request`, reviewer `user`, sandbox `workspace-write`; seven negative allow-list checks passed; model calls zero. No privileged action or approval change was needed. No deployment, production restart, git operation, delegation, or source/test edit occurred. Coordinator gate session **26230** was neither polled nor signalled. Only this report is a persistent repository edit.

## Process exit accounting

Review-owned test session **88450** completed with exit **0**. Supervisor **674098** and pytest controller **674099** exited; both were absent from `/proc` on the final check. The supervisor reported no still-running observed descendant.

- All 16 pytest worker PIDs were absent: **674103, 674106, 674109, 674112, 674117, 674120, 674123, 674126, 674129, 674133, 674137, 674140, 674144, 674148, 674154, 674158**.
- All observed fixture sandbox helper PIDs **674203–674230 inclusive** were absent.
- Collector fixture receipts recorded exit **-9** for **674191, 674193, 674194, 674195, 674196, 674197, 674199**, and exit **0** for **674192, 674198, 675051, 675288**. All were absent. PID **674196** intentionally exercised failed group observation, so its retained receipt conservatively says nonquiescent; the independent final `/proc` check established it had exited.
- The real creator-death fixture's parent **674200** exited with the asserted test code **73**; its child **674201** was also absent after the test's release and cleanup. Both identities came from retained process-start evidence.
- The extra reproduction parent **682816** exited **0**; child **682817** was killed/reaped with **-9** as described above.

These are exact observed or receipt-recorded PIDs, not a claim that 25 ms sampling captured every short-lived fixture descendant. No coordinator or unrelated process was terminated.

## Source hashes

SHA-256 captured before inspection/tests and rechecked after the reproduction; all seven were unchanged.

| File | SHA-256 |
| --- | --- |
| `tools/inventory_recovery_v3/provider_capture.py` | `8789a5a04d7528f949d1c0d99cc701a80f0a83d149a4bd0e36e357da8c85c2ab` |
| `tools/inventory_recovery_v3/provider_runtime.py` | `a23fb208b5bf2a0b4c8612be8d13c8486249cf11084107afe8973b7e69e65e96` |
| `tools/inventory_recovery_v3/rejection.py` | `4765bd72e0b393fb4ba9c5ca3f87c56367045612416df644a3017d7002f13b48` |
| `tools/inventory_recovery_v3/runtime.py` | `f0655d79c17462eb2ed8d3d052b99d27b0146c2f133fcd85f24384cd5d8551c8` |
| `tools/inventory_recovery_v3/cancellation.py` | `fbd9d94bae49819286db64d0ee0251b7ad920fa6fdf2278e5ef7c24db1d7e765` |
| `tests/test_inventory_recovery_v3_provider_capture.py` | `049b246f1915629ed0c324480c77645b6f2f42766b9f5225aa9bf32520884982` |
| `tests/test_inventory_recovery_v3_provider_runtime.py` | `f7fd91af0acb8fb2efc818b57a745bd93ded22bc39932c9495d9f43199629ecb` |

## Residual-only P1 recheck — 2026-10-28

**Status: P1 closed for the reviewed repair; no reproduced residual finding.** The original finding, reproduction, and hashes above are retained as history. Recheck began at **06:58:22 UTC / 14:58:22 Asia/Shanghai**; focused checks and process verification completed by **07:00:49 UTC**, with this appendix recorded immediately afterward. One inspector; source/tests frozen; only this report edited.

The changed collector retains the actual `OwnedPopen` instance before the base constructor runs. The old OSError-to-zero-launch inference is gone. Once the attempt flag is set, it publishes started evidence when a PID is known or explicit uncertainty when no PID is available, and propagates the original exception. Known-PID cleanup attempts both process-group and owned-PID termination, then reaps. The immediate runtime boundary still publishes rejection only for native prelaunch validation rejection or the typed pre-attempt `ZeroLaunch`; retained bindings/process evidence prevent resend.

### Independent focused verification

**12 passed in 26.41 seconds, 16 workers**; supervisor wall time **27.21 seconds**, exit **0**. Only the repaired paths and adjacent guard/namespace regression were selected:

```text
PYTHONDONTWRITEBYTECODE=1 /home/ubuntu/miniforge3/bin/python -B -m pytest -q -p no:cacheprovider -n 16 --basetemp=/tmp/humanvoice-provider-review-20261028-residual tests/test_inventory_recovery_v3_provider_capture.py tests/test_inventory_recovery_v3_provider_runtime.py -k 'postfork or missing_executable or constructor_failure or last_veto or forwards_full_lease'
```

This independently covers all six real post-fork constructor cuts (exec-error read and post-init, each with OSError, ValueError, and KeyboardInterrupt), actual missing executable, pre-PID constructor failure, both pre-attempt guard veto categories, normal native FD-union/shared-namespace preservation, and the native integration retaining its charge without rejection or resend.

The supplied `.localresources/provider-postfork-integration-20261028.xml` was read without modification: **172 tests, zero failures/errors/skips**, XML suite time **77.983 seconds**. The coordinator reports total wall time **79.13 seconds** and Ruff passing; those broad checks were not rerun. The coordinator's intentionally interrupted predecessor gate and terminal record were not altered or re-audited.

Five additional temporary-fixture probes exercised residual cases without changing source or tests:

| Probe | Observed result |
| --- | --- |
| Base constructor raises before its own initialization | Same original KeyboardInterrupt object re-raised; `process_started`, PID, return code, and remaining members null; `group_quiescent=false`; regular output files; all four borrowed FDs open. |
| Constructor fails in `_get_handles` | Same original KeyboardInterrupt object re-raised; explicit unknown/no-PID receipt; no invented zero-launch proof; regular outputs and borrowed FDs preserved. |
| Real post-init child, original KeyboardInterrupt object | Same object re-raised after child **709565** was killed and reaped (**-9**); started and quiescent true; child absent from `/proc`. |
| Real post-init child plus failed group observer | Same original KeyboardInterrupt object preserved; child **709832** reaped (**-9**) and absent; receipt remains conservatively nonquiescent and records `OSError: cleanup observer unavailable`. |
| Real child lacks a separate group when constructor raises | Fixture-only `start_new_session=False` created child **710164** in PGID **710162**. Group-ID lookup for the child PID could not identify a group; the owned-PID fallback killed/reaped it (**-9**), preserved the original ValueError object, retained all four borrowed FDs, and produced a started/quiescent receipt. |

The last probe models the absent-group condition with a real child; it does not claim to force the kernel's exact pre-setsid scheduling interleaving. These probes completed in approximately 0.003–0.143 seconds per case and verified child reaping with `waitpid(..., WNOHANG)` raising `ChildProcessError`. Early constructor cases correctly had no child to reap. No residual false zero launch or escaped observed child was reproduced.

### Recheck process exits

Review-owned session **87034** exited **0**. Supervisor **708080** and pytest controller **708081** were absent on the final check, as were every observed worker and helper. Exact recorded PIDs:

- Sixteen workers: **708367, 708378, 708381, 708384, 708387, 708390, 708393, 708396, 708399, 708402, 708405, 708408, 708412, 708420, 708425, 708430**.
- Observed fixture sandbox helpers: **708460, 708461, 708462, 708463**.
- Receipt-recorded children exiting **-9**: **708453, 708454, 708455, 708457, 708458, 708459, 708921**. Actual missing-executable child **708456** exited **255**. Normal native fixture children **708929** and **709112** exited **0**. All were absent; receipts report quiescence.
- Extra-probe parents **709563** and **710163** exited **0**. Their real children **709565, 709832, 710164** were killed/reaped with **-9** and absent. No review-owned process remained among sampled or receipt-recorded identities. Sampling is not a claim of observing every short-lived subprocess.

No production/gateway calls, deployment, git operations, delegation, restart, or coordinator-process signal occurred. Human approval settings were rechecked through the documented wrapper and remained `on-request` / `user` / `workspace-write`. No privileged action was needed. Runtime/control/prepare fixture boundaries and the original slice exclusions remain in force; this closure is not release approval.

### Rechecked hashes

SHA-256 captured at entry and unchanged after the selected tests and extra probes:

| File | SHA-256 |
| --- | --- |
| `tools/inventory_recovery_v3/provider_capture.py` | `9471916590363b92a103421413466f7e506dbb4d76713f3255a6f71e7813ee43` |
| `tests/test_inventory_recovery_v3_provider_capture.py` | `156a6629dc7cdcc7272dba115a8eb478e6cf324352d9df2b80d8e6e2187488ee` |
| `tests/test_inventory_recovery_v3_provider_runtime.py` | `7619c6aec673748e96338c49c8800233369c34bff368e547ec42f314b9f33b30` |
| `tools/inventory_recovery_v3/provider_runtime.py` | `a23fb208b5bf2a0b4c8612be8d13c8486249cf11084107afe8973b7e69e65e96` |
| `tools/inventory_recovery_v3/runtime.py` | `f0655d79c17462eb2ed8d3d052b99d27b0146c2f133fcd85f24384cd5d8551c8` |
| `tools/inventory_recovery_v3/rejection.py` | `4765bd72e0b393fb4ba9c5ca3f87c56367045612416df644a3017d7002f13b48` |
