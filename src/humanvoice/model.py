"""
Model adapter for WP4 authoring extension.

Per implementation contract 1.1.0 runtime.inference:
- Claude or OpenAI API (exact version string pinned)
- Tool-free output (T4: instruction-looking text is data)
- Prompt template hash recorded
- Behavioral reproducibility (not cryptographic)

WP4 uses models for:
- hv plan: narrative blueprint from brief + evidence
- hv draft: unit-level draft within blueprint boundary
- hv repair: bounded edits (max 3 cycles, oscillation detection)

All model outputs are JSON-validated against schemas. No model output gains
tool authority or modifies canonical source directly.
"""

import json
import os
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import anthropic
except ImportError:
    anthropic = None


PROFILE_PATH = Path(__file__).resolve().parents[2] / "security" / "inference_profile.json"


class BudgetExceeded(Exception):
    """Raised when token budget is exceeded."""
    pass


class BudgetTracker:
    """
    Track cumulative token usage against budget caps.

    Per inference_profile.json budget section:
    - max_document_input_tokens: 250000
    - max_document_output_tokens: 50000
    - Exceeding budget is a hard failure (exit code 5), not silent continuation
    """

    def __init__(self, max_input: int, max_output: int):
        self.max_input = max_input
        self.max_output = max_output
        self.input_used = 0
        self.output_used = 0

    def check_and_record(self, input_tokens: int, output_tokens: int):
        """
        Record token usage and raise BudgetExceeded if over limit.

        Called after each model invocation. Tracks cumulative usage across
        all plan/draft/repair calls in a single document run.
        """
        self.input_used += input_tokens
        self.output_used += output_tokens

        if self.input_used > self.max_input:
            raise BudgetExceeded(
                f"Input token budget exceeded: {self.input_used}/{self.max_input}"
            )
        if self.output_used > self.max_output:
            raise BudgetExceeded(
                f"Output token budget exceeded: {self.output_used}/{self.max_output}"
            )

    def get_usage(self) -> dict:
        """Return current usage for recording in manifest."""
        return {
            "input_used": self.input_used,
            "output_used": self.output_used,
            "input_budget": self.max_input,
            "output_budget": self.max_output,
            "input_remaining": max(0, self.max_input - self.input_used),
            "output_remaining": max(0, self.max_output - self.output_used),
        }


@dataclass
class ModelConfig:
    """Model runtime configuration."""
    runtime_type: str = "claude-api"
    model_version: str = "claude-opus-5"
    api_endpoint: str = "https://api.anthropic.com/v1/messages"
    temperature: float = 0.0  # Lowest variance for behavioral consistency
    # Ceiling for a single unit's output. Raised from 2000 after the ZLB run:
    # section 2 needed ~4160 output tokens and truncated, which was misreported
    # as a model abstention. Per-unit ceilings are normally derived from the
    # unit's own word budget (draft_command._output_ceiling_tokens) and are far
    # below this; this value is the profile-level cap that no unit may exceed.
    max_tokens: int = 8192
    timeout_seconds: int = 300
    prompt_template_hash: Optional[str] = None  # SHA256 from profile, required for non-mock invocation

    @classmethod
    def from_profile(cls, profile_path: Path = PROFILE_PATH) -> "ModelConfig":
        """
        Build config from the recorded inference profile.

        Contract 1.1.0 requires model_version and prompt_template_hash to be
        recorded before invocation; this loader is the only sanctioned way to
        construct a non-mock config.
        """
        if not profile_path.exists():
            raise ValueError(f"Inference profile not found: {profile_path}")

        profile = json.loads(profile_path.read_text())
        model = profile.get("model", {})
        runtime = profile.get("runtime", {})

        model_version = model.get("version_string")
        if not model_version or model_version == "pending":
            raise ValueError(
                "Contract violation: model_version is required before invocation"
            )

        template = profile.get("prompt_template", {})
        template_hash = template.get("template_sha256")
        if not template_hash or template_hash == "pending":
            raise ValueError(
                "Contract violation: prompt_template_hash is required before invocation"
            )

        config = cls(
            runtime_type=runtime.get("type", "claude-api"),
            model_version=model_version,
            api_endpoint=runtime.get("endpoint", cls.api_endpoint),
            max_tokens=profile.get("budget", {}).get("max_output_tokens_per_unit", cls.max_tokens),
            timeout_seconds=profile.get("budget", {}).get("timeout_seconds", cls.timeout_seconds),
        )
        # Store template hash for use by commands
        config.prompt_template_hash = template_hash
        return config


@dataclass
class ModelResponse:
    """Model invocation result."""
    text: str
    prompt_hash: str
    model_version: str
    input_tokens: int
    output_tokens: int
    temperature: float
    request_id: Optional[str] = None
    abstention: Optional[str] = None  # If model signals uncertainty or validation fails
    truncated: bool = False  # True when output_tokens >= max_tokens - 10


class ModelAdapter:
    """
    Adapter for bounded model invocation.

    T4 verification: Model output is delimited JSON with no tool authority.
    All outputs pass through JSON schema validation before use.

    Blocker 3: Logs all API transmissions for the "unauthorized external
    transmission" never-except gate. Each invoke() call records a transmission
    event (destination, purpose, content hash) to support release-time audit.
    """

    def __init__(self, config: ModelConfig, mock_mode: bool = False, snapshot_dir: Optional[Path] = None, budget_tracker: Optional['BudgetTracker'] = None):
        self.config = config
        self.mock_mode = mock_mode
        self.snapshot_dir = snapshot_dir
        self.budget_tracker = budget_tracker

        if not mock_mode and anthropic is None:
            raise ImportError("anthropic package required for non-mock mode; install from requirements-dev.txt")

        if not mock_mode and not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError("ANTHROPIC_API_KEY environment variable required for non-mock mode")

    def invoke(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        purpose: str = "unspecified",
        max_tokens: Optional[int] = None,
    ) -> ModelResponse:
        """
        Invoke model with prompt.

        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            schema: Optional JSON schema for validation

        Returns:
            ModelResponse with text and metadata

        Raises:
            ValueError: If output fails schema validation
            RuntimeError: If API call fails
        """
        prompt_hash = sha256(prompt.encode()).hexdigest()

        if self.mock_mode:
            response_text = self._mock_response(prompt, schema)
            input_tokens = len(prompt.split())
            output_tokens = len(response_text.split())
            request_id = None
        else:
            response_text, input_tokens, output_tokens, request_id = self._invoke_api(
                prompt, system_prompt, max_tokens=max_tokens
            )

            # Blocker 3: log the transmission. Content itself is never logged --
            # only its hash -- so the log can be audited without re-exposing the
            # prompt. Mock mode transmits nothing, so it is not logged.
            if self.snapshot_dir is not None:
                try:
                    from humanvoice.transmission import log_transmission
                    log_transmission(
                        snapshot_dir=self.snapshot_dir,
                        action="api_invocation",
                        destination=self.config.api_endpoint,
                        purpose=purpose,
                        content_summary=f"sha256:{prompt_hash[:16]} ({input_tokens} in / {output_tokens} out)",
                        authorized_by="operator",
                    )
                except Exception as e:
                    # Logging must not break the command; the release gate will
                    # block on a missing log rather than silently proceeding.
                    print(f"Warning: transmission logging failed: {e}", file=sys.stderr)

        # Check budget after recording token usage
        if self.budget_tracker is not None:
            self.budget_tracker.check_and_record(input_tokens, output_tokens)

        # Validate against schema if provided
        if schema:
            try:
                import jsonschema
                parsed = json.loads(response_text)
                jsonschema.validate(parsed, schema)
            except (json.JSONDecodeError, jsonschema.ValidationError) as e:
                # Model output failed validation - treat as abstention
                # Debug: print first 500 chars of response
                debug_text = response_text[:500] if response_text else "(empty)"
                return ModelResponse(
                    text="",
                    prompt_hash=prompt_hash,
                    model_version=self.config.model_version,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    temperature=self.config.temperature,
                    request_id=request_id,
                    abstention=f"Output failed schema validation: {e}\nReceived: {debug_text}"
                )

        # Secondary truncation signal, derived from usage rather than stop_reason.
        #
        # _invoke_api already raises on stop_reason == "max_tokens", which is the
        # authoritative check on the live API path. This covers the cases that
        # never reach it: a runtime that omits stop_reason, and mock or stubbed
        # adapters in tests. Landing within 10 tokens of the requested ceiling is
        # not something a complete response does by coincidence.
        effective_ceiling = min(
            max_tokens or self.config.max_tokens, self.config.max_tokens
        )
        truncated = (
            not self.mock_mode
            and output_tokens >= effective_ceiling - 10
        )

        return ModelResponse(
            text=response_text,
            prompt_hash=prompt_hash,
            model_version=self.config.model_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            temperature=self.config.temperature,
            request_id=request_id,
            truncated=truncated,
        )

    def _mock_response(self, prompt: str, schema: Optional[Dict]) -> str:
        """Mock response for WP4 prototype testing."""
        # Return valid JSON matching schema if provided
        if schema and schema.get('type') == 'object':
            # Build minimal valid response
            response = {}
            for prop, spec in schema.get('properties', {}).items():
                if spec.get('type') == 'object':
                    # Recursively build nested objects
                    nested = {}
                    for nprop, nspec in spec.get('properties', {}).items():
                        if nspec.get('type') == 'string':
                            nested[nprop] = f"mock_{nprop}"
                        elif nspec.get('type') == 'array':
                            nested[nprop] = []
                        elif nspec.get('type') == 'number':
                            nested[nprop] = 0
                    response[prop] = nested
                elif spec.get('type') == 'string':
                    response[prop] = f"mock_{prop}"
                elif spec.get('type') == 'array':
                    response[prop] = []
                elif spec.get('type') == 'number':
                    response[prop] = 0
                elif spec.get('type') == 'boolean':
                    response[prop] = False
            return json.dumps(response, indent=2)

        return "Mock model response for prototype testing"

    def _invoke_api(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: Optional[int] = None,
    ) -> tuple[str, int, int, str]:
        """
        Invoke Claude API (production path).

        Returns:
            (response_text, input_tokens, output_tokens, request_id)

        Raises:
            RuntimeError: If API call fails or times out
        """
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        # A caller that knows its unit's word budget can request a tighter ceiling
        # than the profile default; the profile value is the fallback, not an
        # override, so a per-unit limit cannot silently exceed it.
        effective_max_tokens = min(
            max_tokens or self.config.max_tokens, self.config.max_tokens
        )

        try:
            message = client.messages.create(
                model=self.config.model_version,
                max_tokens=effective_max_tokens,
                temperature=self.config.temperature,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
                timeout=self.config.timeout_seconds,
            )
        except anthropic.APITimeoutError as exc:
            raise RuntimeError(
                f"Claude API exceeded {self.config.timeout_seconds}s timeout"
            ) from exc
        except anthropic.APIError as exc:
            raise RuntimeError(f"Claude API error: {exc}") from exc

        # Check message structure
        if not message.content or len(message.content) == 0:
            raise RuntimeError(f"Claude API returned empty content array. Message ID: {message.id}")

        # The response may lead with a thinking block whose text is None; take the
        # first block that actually carries text.
        response_text = next(
            (
                block.text
                for block in message.content
                if getattr(block, "type", None) == "text" and getattr(block, "text", None)
            ),
            None,
        )
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens
        request_id = message.id

        if not response_text:
            raise RuntimeError(
                f"Claude API returned no text block. Message ID: {message.id}, "
                f"stop_reason: {message.stop_reason}"
            )

        # Budget exhaustion must name itself. A response stopped at the ceiling is
        # cut off mid-token: its JSON never closes and no code fence is emitted, so
        # downstream schema validation fails with a parse error at char 0 and the
        # unit is recorded as a model abstention. That reads as the model having
        # declined the task, when in fact the unit was simply too large for the
        # per-unit output budget. The two demand opposite remedies -- decompose the
        # unit versus revise the prompt -- so they must never share a diagnostic.
        if message.stop_reason == "max_tokens":
            raise RuntimeError(
                f"Model output truncated at the {self.config.max_tokens}-token "
                f"per-unit output ceiling ({output_tokens} tokens emitted). "
                f"The unit is too large to draft in one call: split it into "
                f"smaller subsections, or raise max_output_tokens_per_unit in "
                f"the inference profile. "
                f"Message ID: {message.id}"
            )

        # Extract JSON from markdown code fences if present
        response_text = self._extract_json_from_markdown(response_text)

        return response_text, input_tokens, output_tokens, request_id

    @staticmethod
    def _extract_json_from_markdown(text: str) -> str:
        """
        Extract JSON from markdown code fences.

        API models sometimes wrap JSON in ```json ... ``` markers.
        This extracts the content between the fences.
        """
        if not text:
            return text

        # Look for ```json ... ``` or ``` ... ``` patterns
        import re

        # Try ```json first
        match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try generic ``` code fence
        match = re.search(r'```\s*\n(.*?)\n```', text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # No fence found, return as-is
        return text.strip()


# Schemas for bounded authoring tasks

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "blueprint": {
            "type": "object",
            "properties": {
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "purpose": {"type": "string"},
                            "evidence_needed": {"type": "array", "items": {"type": "string"}},
                            "word_budget": {"type": "number"},
                            "source_file": {"type": "string"},
                            "source_start_line": {"type": "integer", "minimum": 1},
                            "source_end_line": {"type": "integer", "minimum": 1}
                        },
                        "required": ["title", "purpose"]
                    }
                },
                "total_words": {"type": "number"},
                "abstention": {"type": "string"}
            },
            "required": ["sections"],
            # Either provide total_words (normal case) or abstention (insufficient evidence)
            "anyOf": [
                {"required": ["total_words"]},
                {"required": ["abstention"]}
            ]
        }
    },
    "required": ["blueprint"]
}

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "draft": {
            "type": "object",
            "properties": {
                "latex": {"type": "string"},
                "word_count": {"type": "number"},
                "citations_needed": {"type": "array", "items": {"type": "string"}},
                "abstention": {"type": "string"}
            },
            "required": ["latex", "word_count"],
            # Either provide latex content (normal case) or abstention (insufficient evidence)
            "anyOf": [
                {"required": ["latex"]},
                {"required": ["abstention"]}
            ]
        }
    },
    "required": ["draft"]
}

REPAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "repair": {
            "type": "object",
            "properties": {
                "changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "finding_id": {"type": "string"},
                            "original": {"type": "string"},
                            "revised": {"type": "string"},
                            "rationale": {"type": "string"}
                        },
                        "required": ["finding_id", "original", "revised", "rationale"]
                    }
                },
                "unaddressed": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "finding_id": {"type": "string"},
                            "reason": {"type": "string"}
                        },
                        "required": ["finding_id", "reason"]
                    }
                },
                "abstention": {"type": "string"}
            },
            "required": ["changes"]
        }
    },
    "required": ["repair"]
}


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Test model adapter")
    parser.add_argument("--real", action="store_true", help="Use real Claude API (not mock)")
    args = parser.parse_args()

    if args.real:
        config = ModelConfig.from_profile()
        adapter = ModelAdapter(config, mock_mode=False)
        print(f"Using Claude API: {config.model_version}")
    else:
        config = ModelConfig(temperature=0.0)
        adapter = ModelAdapter(config, mock_mode=True)
        print("Using mock mode")

    # Test plan generation with schema constraint
    system = "You are a technical writing assistant. Respond only with valid JSON matching the requested schema."
    prompt = """Generate a blueprint for a 500-word technical document about distributed systems.

Return JSON with this structure:
{
  "blueprint": {
    "sections": [
      {"title": "...", "purpose": "...", "evidence_needed": [], "word_budget": 100}
    ],
    "total_words": 500
  }
}"""

    response = adapter.invoke(
        prompt,
        system_prompt=system,
        schema=PLAN_SCHEMA
    )

    if response.abstention:
        print(f"\nAbstention: {response.abstention}")
    else:
        print(f"\nResponse ({response.output_tokens} tokens):")
        parsed = json.loads(response.text)
        print(json.dumps(parsed, indent=2))
        print(f"\nInput tokens: {response.input_tokens}")
        print(f"Output tokens: {response.output_tokens}")
        print(f"Request ID: {response.request_id}")
        print(f"Prompt hash: {response.prompt_hash[:16]}...")
