# Humanvoice pre-human release revision

## Objective

Make the product proposal promise an executable way to protect scarce expert
reading time: an incomplete brief or failed preflight must not become a
human-review packet.

## Scope

- Product narrative: brief compiler, argument blueprint, bounded drafting,
  pre-human preflight, causal repair, and release.
- Design and architecture: records, gates, command surface, failure states, and
  human-attention budget.
- First build: schedule, acceptance tests, mutation tests, critic calibration,
  repair limits, and operating handoffs.
- Requirements and regression checks: machine-readable controls and source-level
  assertions for the new path.
- Visuals: diagrams must show the same sequence as the prose.

## Review before execution

The initial draft was internally inconsistent: the product chapter began with a
bad paragraph, the architecture still specified four post-draft commands, and
the worked-case figure sent a private draft toward a reader. A simple prose
score could not catch that contradiction. The review therefore treated the
release boundary as the primary invariant and required a visual inspection after
compilation.

## Execution record

Completed on 26 August 2026:

- Rewrote the product, design, architecture, worked-case, operating-plan, and
  first-build sections around a fail-closed pre-human path.
- Added eight requirements (R17--R24) and synchronized the protocol, CSV, and
  JSON exports at 24 requirements.
- Added structural checks for the authoring contract and six-stage command path.
- Resized and inspected the new pipeline and dependency figures; removed the
  overfull layout defect introduced by the expanded table.
- Updated the repository README and generated document status.

## Verification

- `bash tools/build_humanvoice.sh`
- `python3 -m unittest discover -s tools -p 'test_*.py'` (46 tests)
- `python3 tools/check_humanvoice_document.py`
- `python3 tools/check_visual_density.py docs/survey/humanvoice_survey.aux`
- `python3 tools/survey_audit.py validate --run docs/survey/audit/latest`
- `git diff --check`

The current PDF is 256 pages, with 56,292 words on the main route, 38 figures,
67 tables, and 105 numbered visuals. Evidence and independent-reader status
remain explicitly pending; the audit snapshot is not an efficacy claim.
