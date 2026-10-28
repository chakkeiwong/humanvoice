# Native ownership bounded review — 2026-10-28

**Current disposition: P2 CLOSED after the frozen repair recheck on 2026-10-28. No residual finding in the repaired claim-tail integration scope.** The original finding, reproduction, and pre-repair hashes below are retained as historical evidence.

## Residual-only repair recheck — P2 closed

Inspected the repaired `stage_owner.py`, `claim_tail.py`, `stage_authority.py`, and the 12 new `test_claim_tail_rejects_lost_stage_before_publication` cases. Both `owned_stage` and cold `claim_tail.reconcile` now enter the shared `stage_ownership` context, including the provider Lease on the complete path, and pass its active `owner.owned_check` through `under_grant` to the claim callbacks. `grant_stage` rejects a needed claim tail when no explicit stage check is provided. The shared ExitStack restores the consumption callback and closes the provider lease and stage handles on rejection. The publication callback remains acyclic: it validates ownership without invoking consumption-floor status or acquiring the native spending locks again.

**Independent targeted result: 12 passed in 92.46s.** Both routes, both stage lock names, and receipt/ledger/complete-intent publication boundaries passed. The tests require the affected write to be prevented, account bytes to remain unchanged, the claim intent to remain pending, the floor callback to be restored, and both stage locks to be acquirable after unwind. This closes the previously reproduced lost-provider publication defect. No wider suite was repeated and no deferred collector/control/factory work was included.

Exact selected node:

```text
tests/test_inventory_recovery_v3_native_ownership.py::test_claim_tail_rejects_lost_stage_before_publication
```

Runner: `/home/ubuntu/miniforge3/bin/python -B -`, with `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `deterministic_runtime._worker = True` for in-process fixture parsing, and `pytest.main(['-q', '-x', '--tb=short', '-p', 'no:cacheprovider', <node above>])`. A 180-second alarm bounded the run. No process audit guard was installed for this recheck. Source/test hashes were captured before the run and checked unchanged afterward (`END_SHA256_MATCH=True`).

Coordinator-reported broader validation: 273 regressions passed in 64.55s with 16 workers; Ruff passed. Those results are supplementary, not independently rerun here.

**Process status:** targeted test session `20002` exited with code 0. No residual-review test/probe process remains running. Only this report was edited; production operations and source/test edits were not performed. The review is concluded and its source freeze may end.

Repair-review SHA-256 values (supersede the historical hashes for current disposition):

```text
ae2ee76a35d1d6b994e43683b6d3f7a48ff822f916c4b47985821ce3e57f1851  tools/inventory_recovery_v3/stage_authority.py
58f14df7d6051342465431bc566c5208763747c7aee9fb637153498373b0d2a1  tools/inventory_recovery_v3/stage_owner.py
2e343536f03bcab9b85626909f1f86eab418944595d7d842277dad02e3e0588a  tools/inventory_recovery_v3/claim_tail.py
6b9c7b803568a7ed1a1882f1f1e76096a4b269450a80d4c9d35e2ba93773f9d5  tests/test_inventory_recovery_v3_native_ownership.py
0b201e54ff76ee78aa6a1cbe0c34d3900eb39eb52bb7b124cce0052813f06f66  tools/inventory_recovery_v3/native_consumption.py
21395ff6502d77c35abf34a71fede98b64bcf0d554f63a5ecc9cfa917900e655  tools/inventory_recovery_v3/dispatcher.py
8d279268b33fcfd76c30e5d8f17b325734f1df8c4e4398b45e7c5b878ad437aa  tools/inventory_recovery_v3/claim.py
```

## Historical P2 — Existing claim-tail repair publishes a ledger after provider ownership is lost (closed)

**Location:** `tools/inventory_recovery_v3/claim_tail.py:40–41`; integration callers `stage_authority.py:116` and `stage_owner.py:95`.

`owned_stage` establishes the provider lease and rebinds `consumption.check` to `owner.owned_check`, but its early `grant_stage → claim_tail.under_grant` repair passes **campaign-only** `authority.owned_check` as both claim callbacks. In an interrupted, already-reserved claim, receipt/ledger repair runs through those callbacks. `claim.py:178–184` publishes the receipt and invokes `guarded_ledger`; these publications do not pass through the rebound consumption-floor writer. Consequently the callback still succeeds after `executor.lock` is removed, and the guarded native initializer writes `allocation-ledger.json` before a later provider check rejects execution.

**Reproduced result:** after an injected interruption immediately following the native account write, reenter `owned_stage` and unlink `executor.lock` immediately before the repair's `guarded_ledger`. Calling the actual supplied publication callback does not raise, and invoking the original guarded initializer creates the ledger. The outer scope subsequently raises `FileNotFoundError` for `executor.lock`. Account bytes remain unchanged and the floor callback is restored on unwind. This is a publication-under-lost-ownership defect; this probe does **not** demonstrate duplicate spending or a provider launch. The normal fresh-claim path's stronger callback does not protect the earlier tail-repair path.

**Requested correction:** thread the active stage/provider `owned_check` through `grant_stage` and `under_grant` for tail repair, retaining its acyclic behavior. Ensure every tail receipt/ledger/intent publication checks the stage descriptors and provider lease as applicable. Add a regression injecting provider-lock loss at the actual existing-only receipt/ledger publication boundary; rejection must precede the affected write and cleanup must restore the callback and close acquired references.

### Reproduction

Run from `/home/ubuntu/workspace/humanvoice` with `/home/ubuntu/miniforge3/bin/python -B -`. The following uses only temporary fixture artifacts and in-memory patches. The deterministic parser is placed in its in-process fixture mode so the probe creates no child processes. No admission/control/ownership predicate under review is replaced.

```python
import io
import json
import os
import signal
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
def audit(event, args):
    if event in {'subprocess.Popen', 'os.fork', 'os.forkpty',
                 'os.posix_spawn', 'os.exec', 'os.system',
                 'socket.connect', 'socket.getaddrinfo', 'socket.bind'}:
        raise RuntimeError('Bounded review forbids ' + event)
sys.addaudithook(audit)
def timeout(*args):
    raise TimeoutError('90-second probe bound')
signal.signal(signal.SIGALRM, timeout)
signal.alarm(90)
sys.path.insert(0, str(Path('tests').absolute()))

import pytest
from humanvoice import deterministic_runtime
deterministic_runtime._worker = True
from test_inventory_recovery_v3_native_ownership import (
    complete_campaign, codex, baseline, prepared,
)
from tools.inventory_recovery_v3 import claim as claims
from tools.inventory_recovery_v3.stage_owner import owned_stage
from tools.inventory_recovery_v3.failures import RecoveryStop
from tools import sol_inventory_program as original

with tempfile.TemporaryDirectory(prefix='native-ownership-review-') as directory, pytest.MonkeyPatch.context() as mp:
    tmp = Path(directory)
    with redirect_stdout(io.StringIO()):
        provider = codex.__wrapped__(tmp, mp, SimpleNamespace(param=900))
        base = baseline.__wrapped__(tmp, mp)
        ready = prepared.__wrapped__(provider, base, tmp, mp, SimpleNamespace(param=None))
    with complete_campaign(ready, tmp, mp) as fixture:
        native_write = original.epoch.write_json
        def cut(path, value):
            native_write(path, value)
            if Path(path) == fixture.account:
                raise OSError('review account-write cut')
        with mp.context() as patch:
            patch.setattr(original.epoch, 'write_json', cut)
            try:
                with owned_stage(fixture.output, fixture.plan, authority=fixture.authority):
                    raise AssertionError('cut failed')
            except OSError as error:
                assert str(error) == 'review account-write cut'
        assert not (fixture.output / 'allocation-ledger.json').exists()
        before = fixture.account.read_bytes()
        native_ledger = claims.guarded_ledger
        evidence = {}
        def lose_provider(*args, **kwargs):
            (fixture.output / 'executor.lock').unlink()
            evidence['guard_after_lock_loss'] = args[2]()
            result = native_ledger(*args, **kwargs)
            evidence['ledger_written_after_lock_loss'] = (fixture.output / 'allocation-ledger.json').exists()
            return result
        with mp.context() as patch:
            patch.setattr(claims, 'guarded_ledger', lose_provider)
            try:
                with owned_stage(fixture.output, fixture.plan, authority=fixture.authority):
                    raise AssertionError('lost ownership reached caller')
            except (RecoveryStop, ValueError, OSError) as error:
                evidence['eventual_rejection'] = type(error).__name__ + ': ' + str(error)
        evidence['account_unchanged'] = fixture.account.read_bytes() == before
        evidence['floors_callback_restored'] = fixture.floors.check == fixture.authority.owned_check
        print(json.dumps(evidence, sort_keys=True))
```

Observed (temporary prefix abbreviated):

```json
{
  "account_unchanged": true,
  "eventual_rejection": "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/native-ownership-review-…/installed/new-campaign/generation-00/executor.lock'",
  "floors_callback_restored": true,
  "guard_after_lock_loss": null,
  "ledger_written_after_lock_loss": true
}
```

The `null` is the normal `None` return from `claim.check()`; the defect is that it does not reject lost provider ownership. The initializer performs its own check again and still writes.

## Bounded validation and limits

- Read `/home/ubuntu/AGENTS.md`, repository `AGENTS.md`, and the referenced human approval policy. Reviewed the five requested source modules, the new native-ownership tests, and directly adjacent lease, predicate, claim, floor, history, and owner paths.
- **112 passed in 159.32s:** `tests/test_inventory_recovery_v3_native_ownership.py`, `tests/test_inventory_recovery_v3_owner.py`, `tests/test_inventory_recovery_v3_claim.py`, and `tests/test_inventory_recovery_v3_floor_followup.py`. Executed through the specified Python with `-B`, `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `pytest.main(['-q', '-x', '--tb=short', '-p', 'no:cacheprovider', ...])`, a 180-second alarm, the audit guard above, and `deterministic_runtime._worker = True`. This is a bounded in-process fixture run, not an unmodified subprocess-integration run.
- The initial attempt without in-process parsing produced 112 fixture-setup errors because the review's audit guard blocked deterministic-parser `subprocess.Popen`; those errors are not component findings. No child launch succeeded.
- Existing cases exercised the full execution-FD union, nonrecursive owned callbacks, post-floor provider rechecks, stop rejection, floor loss/rollback rejection, claim-cut reopen without duplicate reservation, legacy owner behavior, and cleanup. Static inspection covered the complete-path constructor's role/configuration requirements and provider membership derivation. No additional scope/role finding was reproduced.
- Coordinator-reported evidence, not rerun as such by this inspector: prior 261 adjacent tests in 57.37s; additional fixed-runner/native ownership 30 tests in 19.08s; Ruff passed; fixed approval wrapper 56 tests in 2.09s.
- Public factory, authenticated stop-control publisher, final-spawn provider collector, TX4–TX7, and release remain expressly outside acceptance. Fixture control/admission and the component CampaignHistory seed remain explicit boundaries.
- One inspector; no delegation, production operation/write, gateway call, git edit, or source/test edit. Only this review file is a persistent repository edit; tests/probe used temporary fixtures. Sources/tests listed below matched their initial hashes at the end of inspection.
- All launched review test/probe sessions have exited: `21039` exit 1 (fixture guard), `17327` exit 0 (112 passes), `24704` exit 0 (reproduction). No review-owned test/probe process remains running.

## SHA-256 at review conclusion

```text
521b1ff7f50469990fc678ad08352a11da5e0234e97527383f28323cba958334  tools/inventory_recovery_v3/stage_authority.py
70abde74cb665ddaab040f06550e32d8361d658bbd767809b131bd4eab602487  tools/inventory_recovery_v3/stage_owner.py
0b201e54ff76ee78aa6a1cbe0c34d3900eb39eb52bb7b124cce0052813f06f66  tools/inventory_recovery_v3/native_consumption.py
3f49de11edf72e02cc3c86024415dbadc5099120a2677ccf433c2bf5ffa2741f  tools/inventory_recovery_v3/claim_tail.py
21395ff6502d77c35abf34a71fede98b64bcf0d554f63a5ecc9cfa917900e655  tools/inventory_recovery_v3/dispatcher.py
c8ae991b5b51dc2e5a63ee0e9c9d270be08957c172b14deca3d2cd3a7cfdf720  tests/test_inventory_recovery_v3_native_ownership.py
8d279268b33fcfd76c30e5d8f17b325734f1df8c4e4398b45e7c5b878ad437aa  tools/inventory_recovery_v3/claim.py
2cb95e54da5b6f6be512696712bcc007244496b104b9d673e2c51c5f0ac878b5  tests/test_inventory_recovery_v3_owner.py
0d5b046dd613542e55dc9831813a4c6acc516cd489039e6963c9e84d40b01dc8  tests/test_inventory_recovery_v3_claim.py
301bd3ee3a31a143d3ea2d996bbc99c3385c5a30c98999ea18c35d2bdfc44996  tests/test_inventory_recovery_v3_floor_followup.py
```
