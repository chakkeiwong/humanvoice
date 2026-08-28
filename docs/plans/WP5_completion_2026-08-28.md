# WP5 Completion — reader feasibility

**Date:** 2026-08-28  
**Work package:** WP5  
**Contract version:** 1.1.0  
**Status:** complete — `hv release` implemented with deterministic gates, reader-packet independence, and schema validation

## What was delivered

The `hv release` command assembles an immutable reader packet after evaluating four deterministic gates. It produces a `ReleaseDecision` record conforming to [release-decision.schema.json](../../schemas/release-decision.schema.json) and exits with the code specified by the implementation contract.

### Gate implementation

Four gates are wired and evaluated before any packet is assembled:

1. **Protected correspondence** (never-except) — blocks if any `ProtectedManifest` object has `comparison.status == "unresolved"` or `comparison.unresolved_count > 0`. Scans all `protected-manifest-*.json` records across runs.

2. **Brief parsing promises** (never-except) — blocks if the brief's `expected_objects` field names object types (e.g., `{"equation": 3}`) that no `ProtectedManifest` contains. This gate enforces that parsing delivers what the brief promises.

3. **Evidence sufficiency** (never-except) — blocks if any `EvidenceItem` with `supports[].load_bearing == true` has `appraisal_state` of `insufficient` or `unappraised`. Load-bearing claims must have appraised evidence before release.

4. **Author convergence** (ordinary, exception-releasable) — blocks if any run's `revisions/unresolved_author_choice.json` exists. A `superseded_author_choice.json` does not block (the marker was retired by a later successful cycle).

Never-except conditions cannot be exception-released. The three never-except gates listed above, plus unauthorized external transmission and broken source build (not yet implemented), form the immutable release boundary.

### Reader-packet independence

The reader packet is assembled under `<output>/packet/` and contains:

- Source files (or rendered PDF when available)
- `reader_context.json` — includes only `reader`, `decision_type`, `time_available_minutes`, and `success_criteria` from the brief

The packet deliberately omits finding IDs, model confidence, parser warnings, private paths, internal phase names, run IDs, and record IDs. A test asserts this independence by checking that `reader_context.json` contains exactly the four reader-facing fields and none of the internal ones.

### Exit-code contract

| Code | Meaning | When returned |
|---:|---|---|
| 0 | released | All gates pass |
| 1 | deterministic gate failure | Any never-except or ordinary gate blocks |
| 2 | abstention | Reserved (not yet used) |
| 3 | invalid input | Missing snapshot, uninitialized snapshot, or malformed brief |
| 4 | internal error | Reserved (uncaught exceptions) |
| 5 | security violation | Reserved (not yet used) |

The tests verify exit 0 for clean release, exit 1 for each of the four gate blocks, and exit 3 for missing/uninitialized snapshot inputs.

### Record schema

Every emitted `release_decision.json` is validated against Draft 2020-12 JSON Schema. The test suite includes a property that validates the record after a clean release, and the contract-check tool (`check_implementation_contract.py`) validates all example records at every run.

The decision record includes:

- `gate_results`: one `"pass"` or `"blocked"` entry per gate
- `exceptions`: array of block objects, each with `gate`, `never_except`, and `detail` fields
- `unresolved_risks`: list of gate names that blocked
- `packet_hash`: SHA-256 of the reader packet (empty string if blocked)
- `status`: `"released"` or `"blocked"`

## Production bugs found and fixed

Two defects were caught by the new test suite that would have been invisible to earlier manual verification:

### Bug 1: Protected-object gates never matched real records

**Location:** [release_command.py:80](../../src/humanvoice/commands/release_command.py#L80), [release_command.py:157](../../src/humanvoice/commands/release_command.py#L157)

The `check_protected_manifest_correspondence` and `check_brief_parsing_promises` functions globbed `**/protected_manifest*.json` (underscore), but real records from WP2 are named `protected-manifest-*.json` (hyphen, per the record-naming convention). Both gates could never have fired on any actual run.

**Fix:** Changed both patterns to `**/protected-manifest*.json`. Confirmed by grep that the evidence pattern at line 204 (`**/evidence*.json`) already uses the correct convention and was unaffected.

### Bug 2: Release decision discarded all exception blocks

**Location:** [release_command.py:400](../../src/humanvoice/commands/release_command.py#L400)

The `decision_record` dict hardcoded `"exceptions": []`, overwriting the `blocks` list assembled by gate evaluation. When a gate blocked, stderr correctly logged the detail, but the written record contained no machine-readable reason. Never-except provenance was lost from the audit trail even though the exit code was correct.

**Fix:** Changed to `"exceptions": blocks`. Now the emitted record preserves the gate name, never-except flag, and detail for every block.

Both bugs were latent because the earlier 5-test suite exercised only the `author_convergence` gate (which reads from `revisions/`, a different path) and the clean-release path. No test planted protected-manifest or evidence records where the pattern and assembly bugs would have been visible. The new 7-gate tests plant synthetic records for all four gates, exposing both defects immediately.

## Test coverage

**9 tests pass** in `tests/test_release_command.py`, grouped into two suites:

### `TestReleaseGates` (7 tests)

- `test_clean_snapshot_releases_and_record_validates` — exit 0, all gates pass, packet hash present, schema validation passes
- `test_unresolved_author_choice_blocks_release` — plants `unresolved_author_choice.json` with `stop_reason: "cycle_limit"` → exit 1, gate blocked, block recorded
- `test_superseded_author_choice_does_not_block` — plants `superseded_author_choice.json` → exit 0 (marker does not block)
- `test_unresolved_protected_correspondence_blocks_never_except` — plants a `ProtectedManifest` with `comparison.status: "unresolved"` → exit 1, `never_except: true` in exceptions
- `test_unparsed_brief_promise_blocks_never_except` — brief promises `{"equation": 3}`, but manifest contains only a citation → exit 1, parsing-promise gate blocks
- `test_load_bearing_evidence_gap_blocks_never_except` — plants `EvidenceItem` with `supports[].load_bearing: true` and `appraisal_state: "insufficient"` → exit 1, evidence-sufficiency gate blocks
- `test_reader_packet_strips_internal_ids` — asserts `reader_context.json` contains exactly `{reader, decision_type, time_available_minutes, success_criteria}` and none of `{record_id, run_id, finding_id, phase}`

### `TestReleaseValidation` (2 tests)

- `test_missing_snapshot_returns_exit_3` — snapshot path does not exist → exit 3
- `test_uninitialized_snapshot_returns_exit_3` — snapshot exists but has no `manifest.json` → exit 3

Shared helpers (`init_snapshot`, `release`, `read_decision`, `write_run_record`) eliminate test duplication. The `write_run_record` helper plants synthetic records under `.humanvoice/runs/<run_name>/` so gate tests can exercise blocking conditions without running the full authoring pipeline.

## Full suite status

All 67 tests pass (9 new release tests + 58 existing). The three changes to `release_command.py` (two glob fixes, one record-assembly fix) do not regress any prior test. Contract validation (`check_implementation_contract.py`) passes with the new exception-block shape.

## Known limits

- The three unimplemented never-except conditions (unauthorized external transmission, broken source build, and a fifth TBD) have no gate functions yet. The contract names them, but they are not enforced by this implementation.
- The abstention exit code (2) is reserved but never returned. Gates either pass or block; there is no "cannot evaluate" state in the current implementation.
- Packet assembly copies source files but does not verify that a rendered PDF exists or that the build succeeded. If the build failed, the reader sees LaTeX source instead of a compiled document.
- Reader-packet independence is tested by asserting field presence/absence in `reader_context.json`, not by auditing every file in the packet for leaked internal paths or IDs.

## Next

WP6 (decision handoff): reproducibility record across the full fixture suite, cost sensitivity (tokens per command, elapsed wall-clock per gate), burden account (operator minutes for init + authoring + gate resolution), and proceed/revise/stop memo for the sponsor.

The completion criteria for WP6 include:

- All specified claims are marked as implemented or explicitly narrowed
- All abstentions are recorded with their cause
- At least one independent operator has replayed WP1-WP5 on a clean checkout
- Actual cost and burden are compared to the program envelope
- G3 prerequisites are verified (immutable packet, reader independence, gate determinism)
