# Humanvoice approval policy

- Use human review: `approval_policy = "on-request"` and
  `approvals_reviewer = "user"`. Never use `--approve-for-me`, Guardian review,
  automatic approval delegation, or a Luna approval model for this project.
- Keep sandbox restrictions. Do not substitute `never`, `danger-full-access`,
  `--full-auto`, or `--dangerously-bypass-approvals-and-sandbox` for user approval.
- Before an execution phase, enumerate required privileged actions and request
  approval together through the host approval mechanism. If scope changes, ask
  again before executing the new privileged action; never self-approve it.
- Prefer exact absolute executable/script paths and fixed action names. Do not
  request broad interpreter, shell, wildcard, or arbitrary-command allow rules.
- Use `tools/humanvoice_manual_approvals.py` with the absolute Python/script
  paths documented in `docs/plans/HUMAN_APPROVAL_POLICY_2026-10-24.md` for
  permission checks, stopped-run status, and the bounded offline tests.
- Keep the user-stopped master program stopped until explicitly authorized to
  resume. Allow-list installation alone authorizes no inference or restart.
- Frozen child launches use `--ignore-user-config`; a project configuration
  does not change them. Future reviewed launchers must explicitly bind human
  approval settings, with regression coverage, without editing frozen evidence.

