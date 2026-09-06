"""
Truncation detection (scale fixes Issue 1).

A response that hits the output ceiling arrives with stop_reason == "max_tokens"
and a body cut off mid-token. Before this fix the truncated body was handed to
schema validation, which failed with "Expecting value: line 1 column 1 (char 0)"
and was recorded as a model abstention -- indistinguishable from the model
declining the task. That misreport cost a full debugging session chasing a regex
that could never match a closing fence the model never emitted.

These tests pin the distinction: budget exhaustion must name itself.
"""

import pytest
from unittest.mock import MagicMock, patch

from humanvoice.model import ModelAdapter, ModelConfig, DRAFT_SCHEMA


def _config():
    """Non-mock config; API path is patched, so no key is used."""
    return ModelConfig(
        runtime_type="claude-api",
        model_version="claude-opus-5",
        max_tokens=2000,
        prompt_template_hash="a" * 64,
    )


def _message(text, stop_reason, input_tokens=100, output_tokens=2000):
    """Build a stand-in for anthropic.types.Message."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    message = MagicMock()
    message.id = "msg_test_truncation"
    message.content = [block]
    message.stop_reason = stop_reason
    message.usage.input_tokens = input_tokens
    message.usage.output_tokens = output_tokens
    return message


# The shape section 2 of the ZLB run actually returned: an opening fence, valid
# JSON so far, and no closing fence because generation stopped mid-macro.
TRUNCATED_BODY = (
    '```json\n{\n  "draft": {\n    "latex": "\\\\section{Exact nonsmooth HMC}\\n\\n'
    'Let $(\\\\q,\\\\p)$ denote the extended state, and let $\\\\P'
)


class TestTruncationDetection:
    def test_max_tokens_raises_not_abstains(self):
        """stop_reason == max_tokens must raise, not return an abstention."""
        adapter = ModelAdapter(_config())

        with patch("anthropic.Anthropic") as client_cls:
            client_cls.return_value.messages.create.return_value = _message(
                TRUNCATED_BODY, "max_tokens", output_tokens=2000
            )
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                with pytest.raises(RuntimeError, match="truncated"):
                    adapter.invoke("prompt", schema=DRAFT_SCHEMA)

    def test_error_names_the_budget(self):
        """The diagnostic must carry the token count and point at the remedy."""
        adapter = ModelAdapter(_config())

        with patch("anthropic.Anthropic") as client_cls:
            client_cls.return_value.messages.create.return_value = _message(
                TRUNCATED_BODY, "max_tokens", output_tokens=2000
            )
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                with pytest.raises(RuntimeError) as exc:
                    adapter.invoke("prompt", schema=DRAFT_SCHEMA)

        detail = str(exc.value)
        assert "2000" in detail, "must report the ceiling that was hit"
        assert "msg_test_truncation" in detail, "must carry the request id"
        # Must not be mistakable for a schema/abstention failure.
        assert "schema validation" not in detail

    def test_truncation_is_not_reported_as_abstention(self):
        """
        Regression pin for the misdiagnosis: a truncated response must never come
        back as a ModelResponse carrying an abstention, because that reads as the
        model having declined.
        """
        adapter = ModelAdapter(_config())

        with patch("anthropic.Anthropic") as client_cls:
            client_cls.return_value.messages.create.return_value = _message(
                TRUNCATED_BODY, "max_tokens"
            )
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                try:
                    response = adapter.invoke("prompt", schema=DRAFT_SCHEMA)
                except RuntimeError:
                    return  # correct path
                pytest.fail(
                    "truncation returned an abstention instead of raising: "
                    f"{response.abstention!r}"
                )

    def test_end_turn_still_validates_normally(self):
        """A complete response is unaffected by the truncation check."""
        adapter = ModelAdapter(_config())
        complete = (
            '{"draft": {"latex": "\\\\section{Done}\\n\\nBody text.", '
            '"word_count": 2}}'
        )

        with patch("anthropic.Anthropic") as client_cls:
            client_cls.return_value.messages.create.return_value = _message(
                complete, "end_turn", output_tokens=50
            )
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                response = adapter.invoke("prompt", schema=DRAFT_SCHEMA)

        assert response.abstention is None
        assert "Done" in response.text

    def test_genuine_schema_failure_still_abstains(self):
        """
        Well-formed but schema-violating output is a real abstention and must
        stay one -- the fix must not convert every validation failure to a raise.
        """
        adapter = ModelAdapter(_config())
        wrong_shape = '{"unexpected_key": "no draft field here"}'

        with patch("anthropic.Anthropic") as client_cls:
            client_cls.return_value.messages.create.return_value = _message(
                wrong_shape, "end_turn", output_tokens=20
            )
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                response = adapter.invoke("prompt", schema=DRAFT_SCHEMA)

        assert response.abstention is not None
        assert "schema validation" in response.abstention

    def test_stop_sequence_is_not_truncation(self):
        """Only max_tokens signals budget exhaustion."""
        adapter = ModelAdapter(_config())
        complete = '{"draft": {"latex": "\\\\section{S}\\n\\nText.", "word_count": 1}}'

        with patch("anthropic.Anthropic") as client_cls:
            client_cls.return_value.messages.create.return_value = _message(
                complete, "stop_sequence", output_tokens=30
            )
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                response = adapter.invoke("prompt", schema=DRAFT_SCHEMA)

        assert response.abstention is None
