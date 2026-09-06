# Phase 2 Gate Function Fixes — v1.2 External Release Preparation

**Priority:** Complete before corpus rights clearance. The 2026-08-29 pilot released a packet with known violations while reporting all gates pass — that's the blocker.

**Scope:** Fix the three defects that let `fixtures/synthetic/register/001.tex` release with unrepaired violations.

**Timeline:** 2-3 days.

---

## Fix 1: Canonical run-directory resolution (F-RELEASE-PATH-001)

**What:** All commands write and read from one canonical location.

**Current state:** `plan_command.py:217` and `draft_command.py:314` write to `Path.cwd() / ".humanvoice" / "runs" / run_id`. All five release gates read `snapshot_dir / ".humanvoice" / "runs"`. These never coincide unless cwd happens to be the snapshot dir.

**Impact:** Three never-except gates return `None` (pass) when the runs directory is absent:
- `check_unresolved_author_choice` (line 42-43)
- `check_protected_manifest_correspondence` (line 71-72)
- `check_evidence_gaps` (line 196-197)

**Fix:**
1. Create a shared `_resolve_runs_dir(snapshot_dir: Path) -> Path` helper that returns the canonical location
2. Use it consistently across `plan_command`, `draft_command`, `repair_command`, and all release gates
3. Decision: either all under `snapshot_dir/.humanvoice/runs/` OR establish an explicit runs registry that release can discover

**Preferred:** runs under `snapshot_dir/.humanvoice/runs/`. The snapshot is the authoritative artifact; having records scattered elsewhere breaks the "snapshot is self-contained" model.

**Also fix:** The three gates should distinguish "no records exist" from "records exist and are clean". For never-except conditions, absence of evidence is not evidence of compliance. Return a block when the expected directory or file structure is missing entirely, rather than `None`.

**Test:** Re-run the pilot. Release should now see the repair abstention marker (once Fix 2 writes it) and block.

---

## Fix 2: Persist repair abstention (F-REPAIR-NOPERSIST-007)

**What:** Write `unresolved_author_choice.json` when repair abstains, matching the oscillation/stop paths.

**Current state:** [repair_command.py:572-582](src/humanvoice/commands/repair_command.py#L572-L582) prints abstention to stdout and returns 2. Lines 537 and 626 write `unresolved_author_choice.json` for oscillation and stop cases, but the abstention path does not.

**Fix:**
```python
if repair.get("abstention") and not repair.get("changes"):
    record = {
        "record_type": "ReaderDecision",
        "status": "unresolved",
        "reason": repair["abstention"],
        "cycle_attempted": cycle,
        "findings_presented": len(findings),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    marker = revisions_dir / "unresolved_author_choice.json"
    marker.write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))
    print(f"\nAbstention: {repair['abstention']}", file=sys.stderr)
    return 2
```

**Test:** Manually run repair on an empty draft with findings (reproducing the pilot condition). Verify `unresolved_author_choice.json` is written. Then run release — it should block on `author_convergence`.

---

## Fix 3: Gate release on preflight findings (new gate)

**What:** Add a sixth never-except gate that blocks release if the snapshot has unresolved deterministic findings.

**Current state:** Release registers five gates. None consult preflight output. The pilot's preflight exited 1 with 2 findings; release still passed every gate.

**Approach:**
1. `check_preflight_findings(snapshot_dir: Path) -> Optional[dict]`
2. Look for the most recent `preflight-*.json` under `snapshot_dir/.humanvoice/runs/` (after Fix 1, this location will be canonical)
3. If no preflight output exists, block with `"reason": "no_preflight_run"`
4. If `findings` is non-empty, block with the finding details
5. If `status != "pass"`, block
6. Register as `"deterministic_preflight"` with `"never_except": True`

**Edge case:** Preflight can run multiple times (the pilot ran it twice). Use the most recent by timestamp in the filename (`preflight-20260829-143248`).

**Also consider:** Should repair success clear the preflight block, or must preflight be re-run on the revised artifact? For v1.2, require re-running preflight after repair — simpler contract and matches the "deterministic gates are authoritative" principle.

**Test:** Re-run pilot. Release should now block on three grounds: no visible runs (after Fix 1 changes what "visible" means), unresolved repair abstention (after Fix 2 writes it), and unresolved preflight findings (this fix).

---

## Fix 4: Zero-word drafts are a hard failure (F-DRAFT-EMPTY-008)

**What:** Exit 1 when word_count is zero, instead of warning and proceeding.

**Current state:** [draft_command.py:361-365](src/humanvoice/commands/draft_command.py#L361-L365) prints a warning when word count is outside ±20% of target. Zero is always outside that range but still exits 0 and writes a `.tex` file.

**Fix:**
```python
word_count = draft["draft"].get("word_count", 0)
if word_count == 0:
    print("Error: Draft contains zero words", file=sys.stderr)
    return 1

target = section.get("word_budget", 500)
if word_count < target * 0.8 or word_count > target * 1.2:
    print(f"Warning: Word count {word_count} outside target range "
          f"[{int(target*0.8)}, {int(target*1.2)}]", file=sys.stderr)
```

**Rationale:** A zero-word draft is not a budget variance, it's a missing unit. It should fail like a register violation, not warn like ±25% variance. The pilot abstention was correct reasoning about bad input; the defect is that the bad input was accepted upstream.

**Test:** Draft a section that returns zero words (may need to craft a prompt that triggers it, since it's not deterministic). Verify exit 1.

---

## Fix 5: Invert evidence-appraisal check to allowlist (F-EVIDENCE-003)

**What:** Block unless `appraisal_state` is explicitly sufficient, rather than block only on two specific strings.

**Current state:** [release_command.py:216](src/humanvoice/commands/release_command.py#L216) blocks if `appraisal_state in ("insufficient", "unappraised")`. Missing field, `None`, or any other string passes.

**Fix:**
```python
SUFFICIENT_APPRAISAL_STATES = {"sufficient", "verified", "accepted"}

if has_load_bearing:
    state = ev.get("appraisal_state")
    if state not in SUFFICIENT_APPRAISAL_STATES:
        gaps.append({
            "evidence_id": ev.get("record_id"),
            "appraisal_state": state,
            "supports_count": len(supports),
        })
```

**Rationale:** The contract says load-bearing claims need appraised evidence. Default-absent is the common case for a record that hasn't been through appraisal yet. An allowlist makes the gate fail closed.

**Test:** Plant an evidence-item with `supports: [{"load_bearing": true}]` and no `appraisal_state` field. Verify release blocks on `evidence_sufficiency`.

---

## Order of work

1. **Fix 1 (run-directory)** — foundational; Fixes 2, 3, and 5 depend on it
2. **Fix 2 (repair abstention)** — small, isolated change
3. **Fix 3 (preflight gate)** — new gate, medium scope
4. **Fix 4 (zero-word draft)** — small, isolated change
5. **Fix 5 (evidence allowlist)** — small, isolated change
6. **Re-run pilot end-to-end** — verify all three original violations now block release

---

## Acceptance

The instrumented pilot (`fixtures/synthetic/register/001.tex`) must block release on all three grounds:
- `author_convergence` gate blocks on the persisted repair abstention
- `deterministic_preflight` gate blocks on the 2 preflight findings
- (The zero-word drafts should not reach release at all because draft exits 1)

`release_decision.json` should report at least two never-except blocks and `status != "released"`.

---

## After these five

Continue with the original Phase 2 plan:
- **Blocker 1:** Corpus rights clearance (5 items, 4-8 weeks, can run in parallel with remaining fixes)
- **Blocker 2:** Evidence-item emission (1-2 weeks; also fix protected-manifest emission)
- **Blocker 3:** Transmission tracking (1-2 weeks; `model.py` instrumentation + this release gate)
- **Blocker 4:** Independent human reproduction (1 day)

These five gate fixes are 2-3 days and clear the path for a release gate that actually gates.
