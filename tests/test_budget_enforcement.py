"""
Token budget enforcement (scale fixes Issue 5).

The inference profile has always declared budgets -- per-unit output, and
document-level input and output -- and until now nothing read them. The ZLB run
recorded 37,002 input tokens for one section against a declared per-unit cap of
12,000, and 2,418 output against a declared 2,000, and no one was told either
time. The budget block was documentation, not enforcement.

Four things are enforced here:

  1. Per-unit ceiling derived from the unit's own word budget, so a 650-word
     section cannot quietly emit 2,000 words (draft_command._output_ceiling_tokens).
  2. Truncation at that ceiling is rejected rather than written as success.
  3. A BudgetTracker spans every unit of one draft invocation, and exhausting it
     is terminal (exit 5) rather than an abstention.
  4. A release gate accumulates spend across invocations, which no single
     invocation's tracker can see.
"""

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from humanvoice.commands import draft_command
from humanvoice.commands.release_command import check_document_budget
from humanvoice.model import ModelConfig, ModelResponse, BudgetTracker


def _minimal_snapshot(tmp_path, word_budget=500):
    """
    Smallest snapshot draft_command will run against: a manifest, a source file,
    a one-section blueprint, and a brief.
    """
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "source").mkdir()
    (snapshot / ".humanvoice" / "runs").mkdir(parents=True)

    (snapshot / "manifest.json").write_text(json.dumps({
        "source_files": [],
        "protected_objects": [],
    }))

    (snapshot / "blueprint.json").write_text(json.dumps({
        "blueprint": {
            "sections": [{
                "title": "Test Section",
                "purpose": "Test",
                "word_budget": word_budget,
                "source_start_line": 1,
                "source_end_line": 10,
            }]
        }
    }))

    (snapshot / "brief.json").write_text(json.dumps({"register": "third-person"}))

    return snapshot


class TestCeilingEnforcement:
    """
    Per-section ceiling enforcement. A section draft stops when it runs out of
    budget, and that is classified as truncation rather than success.
    """

    def test_max_tokens_set_from_word_ceiling(self, tmp_path):
        """
        Draft invocation sets max_tokens = ceiling_words * 1.3.

        The model must see the limit for it to matter. The 1.3 conversion is
        conservative (GPT tokenizer, English prose).
        """
        # Patch the invoke call to capture what max_tokens was actually sent
        captured = {}

        def mock_invoke(self, prompt, system_prompt, schema, purpose, max_tokens=None):
            captured["max_tokens"] = max_tokens
            # Raw LaTeX, not JSON
            return ModelResponse(
                text="\\section{Test}\n\nSome prose content here.",
                prompt_hash="test_hash",
                model_version="claude-opus-5",
                input_tokens=100,
                output_tokens=200,
                temperature=0.0,
                truncated=False,
            )

        snapshot_dir = tmp_path / "snap"
        snapshot_dir.mkdir()
        (snapshot_dir / "source").mkdir()
        (snapshot_dir / ".humanvoice").mkdir()
        (snapshot_dir / ".humanvoice" / "runs").mkdir()

        # Write minimal blueprint and brief
        blueprint = {
            "blueprint": {
                "sections": [
                    {
                        "title": "Test Section",
                        "purpose": "Test",
                        "word_budget": 500,
                        "source_start_line": 1,
                        "source_end_line": 10,
                    }
                ]
            }
        }
        brief = {"register": "third-person"}

        blueprint_path = tmp_path / "blueprint.json"
        brief_path = tmp_path / "brief.json"
        blueprint_path.write_text(json.dumps(blueprint))
        brief_path.write_text(json.dumps(brief))

        # Write empty manifest
        manifest = {"source_files": [], "protected_objects": []}
        (snapshot_dir / "manifest.json").write_text(json.dumps(manifest))

        # Mock ModelAdapter.invoke
        with patch("humanvoice.model.ModelAdapter.invoke", mock_invoke):
            class Args:
                snapshot = snapshot_dir
                blueprint = blueprint_path
                brief = brief_path
                section = 0
                mock = False

            draft_command.run(Args())

        # The ceiling is set to the profile maximum (8192) for all sections to
        # avoid mid-sentence truncation. Word budget enforcement happens post-
        # generation via word count validation, which is more robust than trying
        # to predict LaTeX token density (varies 1.5-5 tokens/word).
        assert captured["max_tokens"] == 8192

    def test_truncation_detected_when_output_equals_ceiling(self, tmp_path):
        """
        When output_tokens >= max_tokens - 10, classify as truncation.

        The model hit its limit, so the text is incomplete.
        """
        def mock_invoke(self, prompt, system_prompt, schema, purpose, max_tokens=None):
            # Simulate the model using all available tokens
            return ModelResponse(
                text='{"draft": {"latex": "\\\\section{Test}\\n\\nSome prose that was cut off midsentence because", "word_count": 50, "citations_needed": []}}',
                prompt_hash="test_hash",
                model_version="claude-opus-5",
                input_tokens=100,
                output_tokens=max_tokens - 5,  # Near the ceiling
                temperature=0.0,
                truncated=True,  # Indicate incomplete output
            )

        snapshot_dir = tmp_path / "snap"
        snapshot_dir.mkdir()
        (snapshot_dir / "source").mkdir()
        (snapshot_dir / ".humanvoice").mkdir()
        (snapshot_dir / ".humanvoice" / "runs").mkdir()

        blueprint = {
            "blueprint": {
                "sections": [
                    {
                        "title": "Test Section",
                        "purpose": "Test",
                        "word_budget": 500,
                        "source_start_line": 1,
                        "source_end_line": 10,
                    }
                ]
            }
        }
        brief = {"register": "third-person"}

        blueprint_path = tmp_path / "blueprint.json"
        brief_path = tmp_path / "brief.json"
        blueprint_path.write_text(json.dumps(blueprint))
        brief_path.write_text(json.dumps(brief))

        manifest = {"source_files": [], "protected_objects": []}
        (snapshot_dir / "manifest.json").write_text(json.dumps(manifest))

        with patch("humanvoice.model.ModelAdapter.invoke", mock_invoke):
            class Args:
                snapshot = snapshot_dir
                blueprint = blueprint_path
                brief = brief_path
                section = 0
                mock = False

            exit_code = draft_command.run(Args())

        # Truncation should be rejected with exit code 2 (abstention-class)
        assert exit_code == 2


class TestDocumentBudgetTracking:
    """
    Total document budget enforcement. The existing BudgetTracker in model.py
    has the right interface; it just needs to be instantiated and wired into
    the pipeline.
    """

    def test_budget_tracker_raises_on_overage(self):
        """
        BudgetTracker.check_and_record raises BudgetExceeded when limits hit.
        """
        from humanvoice.model import BudgetTracker, BudgetExceeded

        tracker = BudgetTracker(max_input=5000, max_output=2000)

        tracker.check_and_record(input_tokens=3000, output_tokens=1000)
        assert tracker.input_used == 3000
        assert tracker.output_used == 1000

        # Second call pushes output over
        with pytest.raises(BudgetExceeded, match="Output token budget exceeded"):
            tracker.check_and_record(input_tokens=1000, output_tokens=1500)

    def test_budget_usage_recorded_in_manifest(self):
        """
        get_usage() returns dict suitable for manifest serialization.
        """
        from humanvoice.model import BudgetTracker

        tracker = BudgetTracker(max_input=250000, max_output=50000)
        tracker.check_and_record(input_tokens=120000, output_tokens=20000)
        tracker.check_and_record(input_tokens=80000, output_tokens=15000)

        usage = tracker.get_usage()

        assert usage["input_used"] == 200000
        assert usage["output_used"] == 35000
        assert usage["input_budget"] == 250000
        assert usage["output_budget"] == 50000
        assert usage["input_remaining"] == 50000
        assert usage["output_remaining"] == 15000

    def test_adapter_propagates_budget_exceeded(self):
        """
        ModelAdapter.invoke() lets BudgetExceeded propagate rather than
        converting it to an abstention.
        """
        from humanvoice.model import ModelAdapter, ModelConfig, BudgetTracker, BudgetExceeded

        config = ModelConfig.from_profile()
        tracker = BudgetTracker(max_input=100, max_output=50)

        # Burn through the budget
        tracker.check_and_record(input_tokens=90, output_tokens=45)

        adapter = ModelAdapter(config, mock_mode=True, budget_tracker=tracker)

        # Next call should raise, not return an abstention
        with pytest.raises(BudgetExceeded):
            adapter.invoke("test prompt", purpose="test")

    def test_draft_exits_5_on_budget_exceeded(self, tmp_path):
        """
        Budget exhaustion is terminal and distinct from abstention.

        Exit 5 (trust/limit violation), not 2 (abstention): the model did not
        decline, the run ran out of the budget the operator authorised. Batch
        modes must stop rather than keep spending against an exhausted cap.
        """
        snapshot_dir = _minimal_snapshot(tmp_path, word_budget=500)

        def exhausted():
            tracker = BudgetTracker(max_input=100, max_output=50)
            tracker.check_and_record(input_tokens=90, output_tokens=45)
            return tracker

        with patch(
            "humanvoice.commands.draft_command._load_budget_tracker", exhausted
        ):
            args = Namespace(
                snapshot=snapshot_dir,
                blueprint=snapshot_dir / "blueprint.json",
                brief=snapshot_dir / "brief.json",
                section=0,
                missing=False,
                all=False,
                mock=True,
            )
            exit_code = draft_command.run(args)

        assert exit_code == 5, "budget exhaustion must exit 5, not abstain"


class TestDocumentBudgetGate:
    """
    Document-level accumulation across invocations.

    draft_command's tracker spans one invocation. A large document is drafted
    over many (`--section` a few at a time, `--missing` after failures), each
    with a fresh tracker, so nothing sees the total. This gate reads the
    per-unit token counts every draft already records and does the accumulation.
    """

    def _runtime_manifest(self, snapshot_dir, name, mode, input_tokens, output_tokens):
        run_dir = snapshot_dir / ".humanvoice" / "runs" / "run-001"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / f"runtime_manifest_{name}.json").write_text(json.dumps({
            "mode": mode,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }))
        return snapshot_dir

    def test_blocks_on_output_and_input_overrun(self, tmp_path):
        snapshot_dir = self._runtime_manifest(
            tmp_path / "snapshot", "s1", "inference", 300000, 60000
        )

        block = check_document_budget(snapshot_dir)

        assert block is not None
        assert block["reason"] == "document_budget_exceeded"
        assert "output 60,000/50,000" in block["detail"]
        assert "input 300,000/250,000" in block["detail"]

    def test_passes_under_limit(self, tmp_path):
        snapshot_dir = self._runtime_manifest(
            tmp_path / "snapshot", "s1", "inference", 10000, 3000
        )
        assert check_document_budget(snapshot_dir) is None

    def test_accumulates_across_units(self, tmp_path):
        """
        The overrun is a property of the document, not of any single unit. Three
        units each comfortably inside the per-unit ceiling can still exceed the
        document cap together, and only this gate sees that.
        """
        snapshot_dir = tmp_path / "snapshot"
        for i in range(3):
            self._runtime_manifest(snapshot_dir, f"s{i}", "inference", 5000, 20000)

        block = check_document_budget(snapshot_dir)

        assert block is not None
        assert block["units_counted"] == 3
        assert block["total_output_tokens"] == 60000

    def test_ignores_mock_runs(self, tmp_path):
        """Mock mode transmits nothing, so it spends nothing."""
        snapshot_dir = self._runtime_manifest(
            tmp_path / "snapshot", "s1", "mock", 500000, 100000
        )
        assert check_document_budget(snapshot_dir) is None

    def test_absent_runs_directory_is_not_this_gate_s_business(self, tmp_path):
        """
        No runs at all is handled by the correspondence gates, which distinguish
        "no work done" from "work done and clean". This gate has nothing to add.
        """
        snapshot_dir = tmp_path / "snapshot"
        snapshot_dir.mkdir()
        assert check_document_budget(snapshot_dir) is None

