# Humanvoice prototype scope clarification

**Date:** 2026-08-26  
**Context:** Reset after Codex session crash; user clarified this is a two-person feasibility prototype, not a staffed project

## The reframing

The v1.1 master program assumed a staffed project with eight distinct roles (sponsor, product engineer, security owner, evaluation lead, domain editor, document owner, independent coding reviewer, independent reader). That staffing model blocks G0 authorization and doesn't match the current reality.

**Current reality:** This is a feasibility prototype with two participants (project owner + AI agent), intended to demonstrate the core concept before seeking broader resources.

## What this means for the program

### Keep from v1.1
- The technical architecture (protected objects, immutable snapshots, fail-closed gates, threat controls T1–T5)
- The six-command surface (`hv init → plan → draft → preflight → repair → release`)
- The WP0–WP6 phasing with protected-core gate at week 6
- Synthetic fixtures for engineering (one ready, 15 planned)
- The implementation contract and schemas
- The 12-week feasibility timeline

### Change for prototype scale
- **Staffing:** Project owner fills multiple roles (sponsor, document owner, domain editor); agent fills others (product engineer, with security/evaluation/coding review as self-check responsibilities). Defer true independent reader to a later feasibility milestone.
- **G0 authorization:** Simplify to "Does the runtime pass T1–T5?" + "Is the synthetic fixture ready?" + "Does the owner approve starting WP1?"
- **Evidence gates:** Keep the 9/15 audit state as documentation of what's known vs what requires external validation. Don't block the prototype on external literature review or reader recruitment.
- **Scale target:** Build enough to demonstrate the concept on one real case (the humanvoice survey itself), not a production service.

## Immediate path forward

1. **Verify T1–T5 under Bubblewrap** — the probe that failed in the Codex session now passes on this host
2. **Update runtime profile** — change status from `blocked` to `verified`
3. **Simplify G0 decision** — owner approval to start WP1, no staffing expansion required yet
4. **Begin WP1** — create the `hv` package, deterministic vertical slice, threat fixtures

The full staffing model returns when/if the prototype demonstrates value and secures resources for a proper feasibility study with independent reviewers.

## Owner decision needed

To proceed with the prototype-scale program:

- **Runtime:** Use verified Bubblewrap for T1–T5 (rootless, network-disabled, read-only source)
- **Fixtures:** Start with synthetic-only (1 ready + build more as needed in WP1)
- **Scope:** Core-only G0 (defer external reader case to later milestone)
- **Authorization:** Begin WP1 vertical slice work

Reply with approval to start, or flag concerns to address first.
