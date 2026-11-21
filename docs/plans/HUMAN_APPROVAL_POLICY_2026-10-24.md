# Human-only approvals and scoped offline allow list

## Verified configuration

The user requests human approval, never "approve for me" or a Luna-based
approval delegate. The global configuration already contains
`approval_policy = "on-request"`, `approvals_reviewer = "user"`, and
`sandbox_mode = "workspace-write"`. All twelve inspected turn contexts from
24 October 2026 in this session record `on-request` / `user`, including the
turns surrounding the Sol diagnostic. No inspected diagnostic launch argument
uses `--approve-for-me`, Guardian, or Luna. The retained inference request
selects Sol/max. There is no evidence that delegated approval caused its HTTP 504.

The child launch uses `--ignore-user-config`, so global/project settings do not
prove its effective approval policy. Future reviewed launcher revisions must
explicitly bind human approval settings and regression-test the resulting
command. Frozen launchers and historical evidence are not modified here.

## Installation scope

One grouped host approval is requested for the fixed installer to add:

- `.codex/config.toml`, explicitly pinning the three human-review settings.
- `~/.codex/rules/humanvoice-manual-approvals-20261024.rules`, containing only
  three fixed offline actions: `check`, `status`, and `test`.

The installer preserves the existing global configuration and rule files,
refuses unexpected existing targets and symlinks, and checks native allow-list
matching before and after installation. It makes no model call, changes no
budget, and does not start or enable services. Existing unrelated/broad rules
are not silently removed, so the new list is not a global permission revocation.

Canonical command form, without shell wrappers, substitutions or redirects:

```text
/home/ubuntu/miniforge3/bin/python /home/ubuntu/workspace/humanvoice/tools/humanvoice_manual_approvals.py check
/home/ubuntu/miniforge3/bin/python /home/ubuntu/workspace/humanvoice/tools/humanvoice_manual_approvals.py status
/home/ubuntu/miniforge3/bin/python /home/ubuntu/workspace/humanvoice/tools/humanvoice_manual_approvals.py test
```

`check` verifies human-review settings and native rule matching. `status` adds
read-only service state. `test` runs the permission, Sol-probe, fallback authorization,
local validation recovery and native offline settlement regression modules.
Arbitrary trailing arguments are
rejected; the wrapper has no live-call, shell, restart or arbitrary-path option.
The installer action is deliberately absent from its own allow list.

## Subsequent execution phases

Routine workspace tests, fault injection and offline replay require no sudo or
service installation. The fixed offline test action includes the new validation
recovery tests without changing installed command rules. Enumerate actual privileged
commands for a deployment and request any new scope together, after its tests and
concrete payload are ready. Existing approval remains valid for its original scope.
Do not delegate new approvals or select automatic review. Any new privileged scope
still requires a new human approval; an allow list cannot authorize unspecified
future repairs safely. A configuration change may require a new/resumed session
to take effect; do not claim an already-running session was reconfigured.

The master remains stopped. This permission repair is not authorization to
retry Sol, restart production, broaden budgets, or bypass model qualification.

## Verification status

Installed through the grouped host approval on 24 October 2026. All 54 bounded
offline tests pass, including ten new approval-control tests; Ruff passes.
Native rule matching confirms the three allowed actions and seven rejected
command forms. Project and global settings both resolve to human review; the
global configuration was not rewritten. Installed rules SHA-256:
`574913b6451fc670ecd8145ed284bdf074d34a9c9ec8b565b6f4a6d096c74340`.

Both production services remain disabled/inactive with `MainPID=0`. No model
calls, budget changes, production restarts, frozen-launcher changes or delegated
approval requests were performed by the permission installer.
