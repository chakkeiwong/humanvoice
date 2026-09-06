"""
End-to-end tests for `hv pipeline`, the orchestration command.

These tests drive the real command implementations -- plan, preflight, draft,
repair, assemble, release -- against a real snapshot on disk. Only the model
boundary is stubbed, by patching ModelAdapter.invoke to return schema-valid
content. Everything downstream of that boundary is the production code path:
the same file layout, the same manifests, the same release gates.

That split is deliberate. The bugs this suite exists to catch were all in the
seams between stages -- a stage writing where the next stage does not look, a
run_id minted per command so artifacts scattered, assembly reading the
pre-repair text. A test that stubbed the stages themselves would have missed
every one of them.

Mock mode (`--mock`) is not usable here: ModelAdapter._mock_response emits empty
arrays for array-typed schema properties and zero for numbers, so a mock
blueprint has zero sections and a mock draft has word_count 0, which
draft_command correctly rejects as a missing unit. The stub below returns
content with the shape real output has.
"""

import json
import sys
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest

from humanvoice.commands import init_command, pipeline_command
from humanvoice.model import ModelResponse


# A source document with protected objects (equation, label, citation) so the
# correspondence machinery has something real to track.
SOURCE_TEX = r"""\documentclass{article}
\begin{document}

\section{Introduction}
\label{sec:intro}

The system maintains a bounded error term as shown in
Equation~\ref{eq:bound}, following \cite{smith2020}.

\begin{equation}
\label{eq:bound}
E = mc^2
\end{equation}

\section{Method}
\label{sec:method}

The measured throughput reached 1200 requests per second under the
conditions described by \cite{jones2021}.

\end{document}
"""

BRIEF = {
    "record_type": "AuthoringBrief",
    "schema_version": "HV-SCHEMA-1.1",
    "reader": "Engineering reviewer deciding whether to approve a proposal",
    "reader_role": "Engineering reviewer",
    "decision": "Approve or reject the proposal",
    "decision_type": "approve_or_reject",
    "genre": "technical memo",
    "time_available_minutes": 15,
    "prior_knowledge": "Familiar with the system, not with internal phase labels",
    "success_criteria": "Reader can decide without needing internal context",
    "known_vocabulary": ["throughput", "error term", "bound"],
    "exemplars": [],
    "evidence_boundary": ["source/001.tex"],
    "privacy_class": "public",
    "protected_objects": [],
    "unknowns": [],
}


def _write_snapshot(tmp_path: Path, source_tex: str = SOURCE_TEX) -> tuple[Path, Path]:
    """
    Build a real snapshot with `hv init`, returning (snapshot_dir, brief_path).

    Going through init rather than hand-building the layout means these tests
    exercise whatever init actually produces, including the source protected-object
    manifest the correspondence gates read.
    """
    source_dir = tmp_path / "source_in"
    source_dir.mkdir()
    (source_dir / "001.tex").write_text(source_tex)

    brief_path = tmp_path / "brief.json"
    brief_path.write_text(json.dumps(BRIEF, indent=2))

    snapshot_dir = tmp_path / "snapshot"

    class InitArgs:
        source = source_dir
        brief = brief_path
        output = snapshot_dir

    exit_code = init_command.run(InitArgs())
    assert exit_code == 0, "fixture snapshot failed to initialise"
    return snapshot_dir, brief_path


class StubModel:
    """
    Schema-valid stand-in for the model, with per-purpose canned responses.

    Records every purpose it was invoked for, so tests can assert on which stages
    called the model and how often -- that is how "repair was skipped because
    preflight was clean" is verified.
    """

    def __init__(self, sections=None, draft_latex=None, repair_changes=None):
        self.sections = sections if sections is not None else [
            {
                "title": "Introduction",
                "purpose": "Frame the problem",
                "word_budget": 100,
                "source_file": "source/001.tex",
                "source_start_line": 1,
                "source_end_line": 14,
            },
            {
                "title": "Method",
                "purpose": "Describe the approach",
                "word_budget": 100,
                "source_file": "source/001.tex",
                "source_start_line": 15,
                "source_end_line": 22,
            },
        ]
        # Draft text per section title. Defaults carry the source's protected
        # objects through, so retention is high without being contrived at 100%.
        self.draft_latex = draft_latex if draft_latex is not None else {
            "Introduction": (
                "\\section{Introduction}\n\\label{sec:intro}\n\n"
                "The system maintains a bounded error term as shown in\n"
                "Equation~\\ref{eq:bound}, following \\cite{smith2020}.\n\n"
                "\\begin{equation}\n\\label{eq:bound}\nE = mc^2\n\\end{equation}\n"
            ),
            "Method": (
                "\\section{Method}\n\\label{sec:method}\n\n"
                "The measured throughput reached 1200 requests per second under the\n"
                "conditions described by \\cite{jones2021}.\n"
            ),
        }
        self.repair_changes = repair_changes if repair_changes is not None else []
        self.purposes = []
        self.max_tokens_seen = []

    def __call__(
        self,
        prompt,
        system_prompt=None,
        schema=None,
        purpose="unspecified",
        max_tokens=None,
    ):
        # max_tokens is accepted and recorded rather than ignored: draft_command
        # now sizes the ceiling per unit, and a stub that silently dropped it
        # would hide a caller passing the wrong value.
        self.purposes.append(purpose)
        self.max_tokens_seen.append(max_tokens)

        if purpose == "plan_generation":
            payload = {"blueprint": {
                "sections": self.sections,
                "total_words": sum(s.get("word_budget", 100) for s in self.sections),
            }}
        elif purpose == "draft_generation":
            latex = self._draft_for(prompt)
            payload = {"draft": {
                "latex": latex,
                "word_count": len(latex.split()),
                "citations_needed": [],
            }}
        elif purpose.startswith("repair"):
            payload = {"repair": {
                "changes": self.repair_changes,
                "findings_cleared": [],
                "abstention": "" if self.repair_changes else "no addressable change",
            }}
        else:
            payload = {}

        text = json.dumps(payload)
        return ModelResponse(
            text=text,
            prompt_hash=sha256(prompt.encode()).hexdigest(),
            model_version="stub-model",
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            temperature=0.0,
            request_id="stub-request",
        )

    def _draft_for(self, prompt):
        """Pick the canned draft whose section title appears in the prompt."""
        for title, latex in self.draft_latex.items():
            if title in prompt:
                return latex
        return "\\section{Untitled}\n\nPlaceholder prose for an unmatched section.\n"

    def count(self, purpose_prefix):
        return sum(1 for p in self.purposes if p.startswith(purpose_prefix))


class PipelineArgs:
    """argparse-shaped args for pipeline_command.run."""

    def __init__(self, snapshot, brief, run_id=None, mock=False):
        self.snapshot = snapshot
        self.brief = brief
        self.run_id = run_id
        self.mock = mock


def _run_pipeline(snapshot_dir, brief_path, stub, run_id=None):
    with patch("humanvoice.model.ModelAdapter.invoke", side_effect=stub):
        return pipeline_command.run(
            PipelineArgs(snapshot_dir, brief_path, run_id=run_id)
        )


def _manifest(snapshot_dir, run_id):
    path = snapshot_dir / ".humanvoice" / "runs" / run_id / "pipeline_manifest.json"
    assert path.exists(), f"no pipeline manifest at {path}"
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Artifact threading: one run_id across every stage
# ---------------------------------------------------------------------------

def test_all_stage_artifacts_land_in_one_run_directory(tmp_path):
    """
    Every stage writes into the pipeline's run directory.

    Before run_id was threaded through, each command minted its own timestamp
    id, so plan/draft/preflight artifacts scattered across sibling directories
    and the orchestrator only found them when two commands happened to start in
    the same second. This is the regression test for that.
    """
    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    stub = StubModel()

    _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-fixed-0001")

    run_dir = snapshot_dir / ".humanvoice" / "runs" / "run-fixed-0001"
    assert (run_dir / "blueprint.json").exists()
    assert list(run_dir.glob("preflight-*.json")), "preflight record not in run dir"
    assert (run_dir / "draft_introduction.tex").exists()
    assert (run_dir / "draft_method.tex").exists()
    assert (run_dir / "pipeline_manifest.json").exists()

    # Exactly one run directory: no stage minted its own.
    run_dirs = [d for d in (snapshot_dir / ".humanvoice" / "runs").iterdir() if d.is_dir()]
    assert [d.name for d in run_dirs] == ["run-fixed-0001"]


def test_pipeline_reaches_assembly_and_records_stage_order(tmp_path):
    """The pipeline runs plan → preflight → draft → assemble and records each."""
    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    stub = StubModel()

    _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-order-0001")
    manifest = _manifest(snapshot_dir, "run-order-0001")

    stages = [d["stage"] for d in manifest["decisions"]]
    assert stages.index("plan") < stages.index("preflight")
    assert stages.index("preflight") < stages.index("draft")
    assert "assemble" in stages

    assert manifest["preflight_path"] is not None
    assert len(manifest["section_drafts"]) == 2
    assert manifest["assembly_path"] is not None


def test_assembled_document_contains_every_section(tmp_path):
    """Assembly concatenates all drafted sections, not just the first."""
    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    stub = StubModel()

    _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-asm-0001")

    assembled = (snapshot_dir / ".humanvoice" / "revisions" / "assembled"
                 / "assembled_document.tex")
    assert assembled.exists()
    text = assembled.read_text()
    assert "\\section{Introduction}" in text
    assert "\\section{Method}" in text


# ---------------------------------------------------------------------------
# Assembly must read repaired text, not the pre-repair draft
# ---------------------------------------------------------------------------

def test_assembly_uses_published_revision_over_original_draft(tmp_path):
    """
    When repair publishes a revision, assembly must consume it.

    _find_section_draft originally globbed only the run directory root, while
    repair publishes to revisions/rev-NNN-<hash>/. Assembly therefore read the
    pre-repair text and every repair was silently discarded -- a loss that left
    no trace in any gate, which is the exact failure shape this project exists
    to prevent.
    """
    from humanvoice.commands.assemble_command import _find_section_draft

    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    stub = StubModel()
    _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-rev-0001")

    run_dir = snapshot_dir / ".humanvoice" / "runs" / "run-rev-0001"
    draft_path = run_dir / "draft_introduction.tex"
    assert draft_path.exists()

    # Publish a revision the way repair_command does: content plus the manifest
    # whose presence marks the revision as published.
    revision_dir = run_dir / "revisions" / "rev-001-abcdef123456"
    revision_dir.mkdir(parents=True)
    revised_text = draft_path.read_text() + "\n% revised by repair\n"
    (revision_dir / "draft_introduction.tex").write_text(revised_text)
    (revision_dir / "revision_manifest.json").write_text(json.dumps({
        "record_type": "RevisionManifest",
        "revision_id": "rev-001-abcdef123456",
        "content_hash": "abcdef123456",
    }))

    found, _ = _find_section_draft(
        snapshot_dir / ".humanvoice" / "runs", 0, "Introduction"
    )
    assert found == revision_dir / "draft_introduction.tex"
    assert "% revised by repair" in found.read_text()


def test_staged_revision_without_manifest_is_ignored(tmp_path):
    """
    An interrupted repair leaves a staging directory; assembly must not read it.

    repair_command writes the revision manifest last precisely so an
    interrupted publish is distinguishable from a completed one.
    """
    from humanvoice.commands.assemble_command import _find_section_draft

    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    stub = StubModel()
    _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-stage-0001")

    run_dir = snapshot_dir / ".humanvoice" / "runs" / "run-stage-0001"
    draft_path = run_dir / "draft_introduction.tex"

    # A revision directory with content but no manifest: not published.
    incomplete = run_dir / "revisions" / "rev-001-deadbeef0000"
    incomplete.mkdir(parents=True)
    (incomplete / "draft_introduction.tex").write_text("truncated garbage")

    found, _ = _find_section_draft(
        snapshot_dir / ".humanvoice" / "runs", 0, "Introduction"
    )
    assert found == draft_path, "unpublished revision was treated as published"


def test_highest_cycle_revision_wins(tmp_path):
    """With several published revisions, the latest repair cycle is used."""
    from humanvoice.commands.assemble_command import _find_section_draft

    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    stub = StubModel()
    _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-cycles-0001")

    run_dir = snapshot_dir / ".humanvoice" / "runs" / "run-cycles-0001"
    revisions = run_dir / "revisions"

    for cycle, marker in ((1, "first"), (2, "second"), (3, "third")):
        d = revisions / f"rev-{cycle:03d}-hash{cycle}"
        d.mkdir(parents=True)
        (d / "draft_introduction.tex").write_text(f"% {marker} cycle\n")
        (d / "revision_manifest.json").write_text(json.dumps({
            "revision_id": d.name, "content_hash": f"hash{cycle}",
        }))

    found, _ = _find_section_draft(
        snapshot_dir / ".humanvoice" / "runs", 0, "Introduction"
    )
    assert "% third cycle" in found.read_text()


# ---------------------------------------------------------------------------
# Abstention rather than fail-open
# ---------------------------------------------------------------------------

def test_empty_blueprint_abstains_before_drafting(tmp_path):
    """
    A zero-section blueprint abstains instead of assembling an empty document.

    The first pipeline run did the opposite: plan returned no sections, draft was
    skipped entirely, assembly produced a zero-section document, and that empty
    document was handed to the release gate as a document. Assembly even reported
    retention 1.0, because preserving none of nothing is vacuously perfect.
    """
    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    stub = StubModel(sections=[])

    exit_code = _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-empty-0001")

    assert exit_code == 2, "empty blueprint did not abstain"
    assert stub.count("draft_generation") == 0, "drafted against an empty plan"

    manifest = _manifest(snapshot_dir, "run-empty-0001")
    abstentions = [d for d in manifest["decisions"] if d["decision"] == "abstention"]
    assert any(d["detail"].get("reason") == "empty_blueprint" for d in abstentions)

    assembled = snapshot_dir / ".humanvoice" / "revisions" / "assembled"
    assert not assembled.exists(), "assembled an empty document"


def test_draft_failure_continues_then_blocks_at_release(tmp_path):
    """
    A failed section no longer stops the pipeline; the release gate stops it.

    Aborting at the first failure made a large run unable to converge: the
    operator got one exit code, no document, and no list of what to retry. The
    pipeline now drafts every section it can, assembles what exists with recorded
    gaps, and is refused at release by the assembly_gaps gate.

    The guarantee this preserves is the one that matters -- an incomplete document
    is never publishable. What changes is where that is decided, and how much
    work survives to be inspected.
    """
    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    # Second section drafts as whitespace, which draft_command rejects (exit 1).
    stub = StubModel(draft_latex={
        "Introduction": "\\section{Introduction}\n\nReal prose for the intro.\n",
        "Method": "   \n",
    })

    exit_code = _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-fail-0001")

    # Blocked, not crashed: release refused it.
    assert exit_code == 1

    manifest = _manifest(snapshot_dir, "run-fail-0001")
    assert any(d["decision"] == "section_1_failed" for d in manifest["decisions"])

    # The successful section survived rather than being discarded with the run.
    assert len(manifest["section_drafts"]) == 1
    assert manifest["section_drafts"][0]["index"] == 0

    # Assembly ran and recorded the hole instead of refusing to produce anything.
    assembled = snapshot_dir / ".humanvoice" / "revisions" / "assembled"
    assert assembled.exists(), "assembly skipped, so the partial document is unavailable"

    gaps = json.loads((assembled / "assembly_gaps.json").read_text())
    assert [g["section_index"] for g in gaps] == [1]
    assert gaps[0]["title"] == "Method"

    # The gap is visible in the document itself, positioned where it belongs.
    document = (assembled / "assembled_document.tex").read_text()
    assert "% MISSING: Method" in document
    assert "Real prose for the intro." in document

    # And release refused on exactly that basis.
    decision = json.loads(
        (snapshot_dir / "release" / "release_decision.json").read_text()
    )
    assert decision["gate_results"]["assembly_gaps"] == "blocked"


# ---------------------------------------------------------------------------
# Repair scheduling
# ---------------------------------------------------------------------------

def test_repair_skipped_when_preflight_is_clean(tmp_path):
    """
    No findings means no repair invocation.

    Repair with nothing to repair is not harmless: it spends an inference call
    and publishes a revision, which changes what assembly reads.
    """
    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    stub = StubModel()

    _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-norep-0001")
    manifest = _manifest(snapshot_dir, "run-norep-0001")

    preflight_decision = next(
        d for d in manifest["decisions"] if d["stage"] == "preflight"
    )
    if preflight_decision["detail"]["findings"] == 0:
        assert stub.count("repair") == 0, "repaired with no findings"
        assert any(
            d["stage"] == "repair" and d["decision"] == "skipped"
            for d in manifest["decisions"]
        )


def test_preflight_runs_once_not_once_per_section(tmp_path):
    """
    Preflight is a property of the snapshot, so it runs once.

    It reads manifest['source_files'] -- the immutable snapshot source -- not the
    drafts. Running it per section would produce N identical records and imply
    per-draft checking that is not happening.
    """
    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    stub = StubModel(sections=[
        {"title": "Alpha", "purpose": "First", "word_budget": 80},
        {"title": "Beta", "purpose": "Second", "word_budget": 80},
        {"title": "Gamma", "purpose": "Third", "word_budget": 80},
    ])

    _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-pf-0001")

    run_dir = snapshot_dir / ".humanvoice" / "runs" / "run-pf-0001"
    records = list(run_dir.glob("preflight-*.json"))
    assert len(records) == 1, f"expected one preflight record, found {len(records)}"

    manifest = _manifest(snapshot_dir, "run-pf-0001")
    preflight_decisions = [d for d in manifest["decisions"] if d["stage"] == "preflight"]
    assert len(preflight_decisions) == 1


# ---------------------------------------------------------------------------
# Release reporting
# ---------------------------------------------------------------------------

def test_blocked_release_reports_the_actual_blocking_gates(tmp_path):
    """
    Blocked gates are read back from the decision record.

    The orchestrator originally globbed release-*.json while release_command
    writes release_decision.json, so it reported "0 gate failures" on the same
    run where the gate printed three never-except blocks. A summary that
    contradicts the gate is worse than no summary.
    """
    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    stub = StubModel()

    exit_code = _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-rel-0001")
    manifest = _manifest(snapshot_dir, "run-rel-0001")

    if exit_code == 1:
        assert manifest["release_status"] == "blocked"
        assert manifest["release_blocks"], "blocked with an empty block list"
        assert manifest["release_gate_results"], "no gate results recorded"

        decision = json.loads(
            (snapshot_dir / "release" / "release_decision.json").read_text()
        )
        assert len(manifest["release_blocks"]) == len(decision["exceptions"])
        recorded = {b.get("gate") for b in manifest["release_blocks"]}
        actual = {b.get("gate") for b in decision["exceptions"]}
        assert recorded == actual


def test_mock_mode_is_not_recorded_as_inference(tmp_path):
    """
    A mock run must not be recorded as an external transmission.

    _count_inference_runs documents that mock runs "transmit nothing, so they
    must not be counted", but plan and draft hardcoded mode "inference"
    regardless. The transmission gate then blocked release for unlogged API calls
    that never happened.
    """
    from humanvoice.commands import plan_command
    from humanvoice.commands.release_command import _count_inference_runs

    snapshot_dir, brief_path = _write_snapshot(tmp_path)

    class PlanArgs:
        snapshot = snapshot_dir
        brief = brief_path
        run_id = "run-mock-0001"
        mock = True

    plan_command.run(PlanArgs())

    rm = json.loads(
        (snapshot_dir / ".humanvoice" / "runs" / "run-mock-0001"
         / "runtime_manifest.json").read_text()
    )
    assert rm["mode"] == "mock", f"mock run recorded as {rm['mode']!r}"
    assert _count_inference_runs(snapshot_dir) == 0


def test_pipeline_manifest_is_written_even_on_early_abstention(tmp_path):
    """
    The audit record exists whatever the outcome.

    A pipeline that abstains without leaving a record is indistinguishable from
    one that never ran.
    """
    snapshot_dir, brief_path = _write_snapshot(tmp_path)
    stub = StubModel(sections=[])

    _run_pipeline(snapshot_dir, brief_path, stub, run_id="run-rec-0001")

    manifest = _manifest(snapshot_dir, "run-rec-0001")
    assert manifest["record_type"] == "PipelineExecution"
    assert manifest["run_id"] == "run-rec-0001"
    assert manifest["decisions"], "no decisions recorded"
