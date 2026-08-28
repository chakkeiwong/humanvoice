# WP4 Completion — bounded authoring extension

**Date:** 2026-08-28
**Work package:** WP4
**Contract version:** 1.1.0
**Status:** complete — `hv plan`, `hv draft`, and `hv repair` implemented and validated against the live API

This supersedes `WP4_completion_2026-08-27.md` (local llama.cpp environment) and
`WP4_complete_hv_plan_2026-08-28.md` (plan command only).

## What was delivered

Three authoring commands, wired into the CLI, each producing a runtime manifest
recording model version, token counts, and request ID.

### `hv plan`

Generates a narrative blueprint from a brief plus the snapshot's evidence list.

Two defects were found and fixed during live validation:

- The command read `manifest["items"]`, but `hv init` writes `source_files`. The
  evidence list was therefore always empty and the model invented plausible
  filenames (`current_system_metrics.json`, `migration_plan.md`) that did not
  exist in the snapshot. Fixed to read `source_files`.
- The prompt did not constrain evidence references to the supplied list. It now
  requires verbatim paths from the snapshot.

Post-fix run on the 800-word distributed-architecture fixture: 5 sections, 820
words, all `evidence_needed` entries verbatim snapshot paths. The model attached
a partial abstention noting that it saw only filenames, not contents, and named
the two provisional evidence mappings whose failure would narrow the argument.
That is the correct reading of its own epistemic position.

### `hv draft`

Produces one section's LaTeX within the blueprint boundary.

Evidence loading was broken: files live under `snapshot/source/` but the loader
looked at the snapshot root, so every draft abstained at zero words. The loader
now resolves both `source/intro.tex` and bare `intro.tex` forms.

Post-fix run on section 1 (180-word budget): 208 words, within the ±20% band.
Every figure verifies exactly against source — 12,000 qps, P50 8 ms, P99 45 ms,
85% pool saturation, 500 GB → 2.1 TB, three incidents at 23/8/45 minutes. The
arithmetic it introduced (31 minutes topology-attributable) is correct. It
converted the source's first-person "Our production database" to third person,
and flagged that the incident record states no root cause, so its attribution of
the third incident to an application defect is provisional.

The register checker had two defects: `re.IGNORECASE` on `\bI\b` matched the math
variable `$i$`, and violations reported raw regex patterns rather than matched
text. Both fixed; math-mode spans are now excluded and findings carry the matched
word and offset.

### `hv repair`

Applies bounded repairs as child revisions. The canonical draft is never modified
in place.

**Edit form.** The model returns verbatim `(original, revised)` string pairs. A
pair whose `original` is absent from the parent, ambiguous (multiple
occurrences), or empty is refused rather than fuzzy-matched. This is the
mechanism that keeps repair from silently rewriting text it was not asked to
touch.

**Pre-publication invariants.** A revision is published only if citation keys
survive, numeric figures survive modulo LaTeX digit-group separators, brief
protected objects survive verbatim, and no first-person construction is
introduced that the parent lacked.

Two false positives in that check were found and fixed by live runs:

- `12{,}000` → `12,000` was flagged as a dropped figure, because the LaTeX
  digit-group brace parses as two numbers. Digit separators are now normalized
  before extraction, so reformatting passes while genuine drops and altered
  magnitudes are still caught.
- A finding demanding removal of `WP2` necessarily removes that digit, which the
  checker read as a lost evidentiary figure. Digits appearing inside a finding's
  own offending text are now exempt. Citation keys stay strict, since no finding
  legitimately names one.

**Stop conditions.** Cycle limit (3) and repeated finding signature are evaluated
before the model runs, so a stalled repair costs no API call. Oscillation and
no-op are evaluated on the produced revision before publication.

A real bug here: oscillation was originally checked against the parent hash,
which meant normal chaining (cycle 1's published hash is cycle 2's parent) was
misreported as `alternating_parent_hashes`. The check now runs on newly produced
content.

Any stop condition writes `unresolved_author_choice.json` and withholds the
reader packet, exit 1. A later successful cycle moves that marker into the
resolving revision as `superseded_author_choice.json` — the record survives for
audit without permanently gating release.

## Live validation

| Case | Result |
|---|---|
| 4 genuine preflight findings (WP label, `/srv/` path, "We", "our") | 4 applied verbatim, 0 refused; revision clears preflight at 0 findings; both citations and all figures intact; parent still shows 4 violations |
| Second cycle, repairable finding | rev-002 published, lineage chains rev-001 hash → rev-002 parent, block marker retired |
| Cycle limit at cycle 4 | blocked, exit 1, packet withheld, no API call |
| Repeated finding signature | blocked, exit 1, author choice recorded |
| Finding requiring absent evidence | abstention, exit 2 — three separate such findings all refused rather than inventing durations, window bounds, or an attribution |
| Missing draft / findings / brief, malformed JSON | exit 3, nothing written |
| No findings | exit 0, no-op |

The abstention behavior is the result worth noting. Asked to bound a measurement
window the draft did not state, or to name the measuring party, the model declined
each time rather than supplying a plausible figure. That is the property the
governance design depends on, and it held without prompting for it specifically.

## Test coverage

58 tests pass. `tests/test_repair_command.py` (42) covers verbatim matching and
refusal, all three stop conditions and their timing, the invariant checks
including both false-positive fixes, canonical-source immutability, and marker
supersession. Stop-condition tests assert order independence of finding
signatures.

## Known limits

- Prompts are inline, not loaded from a hashed template file. The contract's
  `prompt_template_hash` discipline is therefore unenforced for these three
  commands.
- `hv plan` sees filenames only, not evidence contents. The model's own partial
  abstention names this as a limit on its evidence mapping.
- Register checking is regex-based. `\bourselves\b` matches inside
  `Ushuaia-ourselves-like`, which is correct on word-boundary grounds but shows
  the check is lexical, not syntactic.
- Behavioral reproducibility replaces cryptographic replay per contract 1.1.0.
  Independent artifact verification is not available; property conformance across
  runs is.

## Next

WP5 (reader feasibility case): one released packet, timed reader record, burden
account, all abstentions preserved. `hv release` is still a placeholder.
