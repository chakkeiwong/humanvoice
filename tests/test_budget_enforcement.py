"""
Tests for Issue 5: ceiling + budget enforcement.

The profile declares a per-section ceiling (2000 words) and a total document
budget (250k input / 50k output tokens). Currently:
  - ModelAdapter.invoke ignores the word ceiling (max_tokens defaults to 4096)
  - Truncation is not detected (a cut-off draft is written as success)
  - BudgetTracker exists but is never instantiated in the pipeline

The fix:
  1. draft_command passes max_tokens = ceiling * 1.3 to the adapter
  2. draft_command detects truncation (output_tokens >= max_tokens - 10) and
     treats it as abstention (exit 2)
  3. pipeline_command instantiates BudgetTracker, records every inference call,
     and writes usage to the manifest
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from humanvoice.commands import draft_command
from humanvoice.model import ModelConfig, ModelResponse, BudgetTracker


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
            return ModelResponse(
                text='{"draft": {"latex": "\\\\section{Test}\\n\\nSome prose.\\n", "word_count": 50, "citations_needed": []}}',
                prompt_hash="test_hash",
                model_version="claude-opus-5",
                input_tokens=100,
                output_tokens=150,
                temperature=0.0,
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

        # The ceiling is derived from THIS unit's budget, not the profile maximum:
        # 500 words * 1.2 variance * 1.3 tokens/word = 780. Passing the profile
        # maximum instead would let a 500-word section emit 2000 words and call it
        # a success, which is the budget drift this exists to prevent.
        assert captured["max_tokens"] == 780

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
