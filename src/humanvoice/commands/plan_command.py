"""
hv plan - Generate narrative blueprint from brief and evidence.

Reads the authoring brief and evidence files from a snapshot, invokes the
model to generate a structured blueprint (sections, purposes, word budgets),
and writes the result to the current run directory.

Per contract 1.1.0:
- Model output is validated against PLAN_SCHEMA
- Abstention on validation failure or model uncertainty
- Budget caps enforced (max 12k input tokens per unit)
- Runtime manifest recorded with model version, tokens, latency
"""

import json
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Dict, Any

from humanvoice.model import ModelAdapter, ModelConfig, PLAN_SCHEMA


def _load_brief(brief_path: Path) -> Dict[str, Any]:
    """Load and validate authoring brief."""
    if not brief_path.exists():
        raise ValueError(f"Brief not found: {brief_path}")

    try:
        brief = json.loads(brief_path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Brief is not valid JSON: {e}")

    # Basic validation
    required = ["reader", "decision", "genre", "evidence_boundary"]
    missing = [f for f in required if f not in brief]
    if missing:
        raise ValueError(f"Brief missing required fields: {', '.join(missing)}")

    return brief


def _load_snapshot_manifest(snapshot_dir: Path) -> Dict[str, Any]:
    """Load snapshot manifest created by hv init."""
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Snapshot manifest not found: {manifest_path}")

    return json.loads(manifest_path.read_text())


def _build_plan_prompt(brief: Dict[str, Any], evidence_files: list[str]) -> str:
    """Build prompt for plan generation."""

    # Extract key constraints from brief
    reader = brief.get("reader", "expert technical reader")
    decision = brief.get("decision", "unspecified decision")
    genre = brief.get("genre", "technical document")
    max_words = brief.get("max_words", 5000)
    known_vocab = brief.get("known_vocabulary", [])
    protected = brief.get("protected_objects", [])

    prompt = f"""Generate a narrative blueprint for a {genre}.

**Reader:** {reader}
**Decision question:** {decision}
**Word target:** {max_words}

**Evidence available:**
{chr(10).join(f"- {ef}" for ef in evidence_files[:20])}
{"... (truncated)" if len(evidence_files) > 20 else ""}

**Constraints:**
- The reader knows: {', '.join(known_vocab[:10]) if known_vocab else 'general technical vocabulary'}
- Protected objects that must be preserved exactly: {len(protected)} items
- Register: third-person technical exposition, no first-person claims

**Task:**
Generate a blueprint with sections covering:
1. What problem or decision this addresses
2. What mechanism or approach is proposed
3. Which evidence is decisive for each claim
4. What qualifications change the interpretation

Return JSON matching this schema:
{{
  "blueprint": {{
    "sections": [
      {{
        "title": "Section title",
        "purpose": "What this section accomplishes for the reader",
        "evidence_needed": ["source/intro.tex"],
        "word_budget": 500
      }}
    ],
    "total_words": {max_words}
  }}
}}

The sections should:
- Sum to the word target (±10%)
- Map evidence to specific claims
- Build from problem → mechanism → evidence → qualifications
- Avoid protected objects in section titles (they appear in content)

**Critical constraint on evidence_needed:**
Every entry in "evidence_needed" MUST be copied verbatim from the
"Evidence available" list above. Do not invent, rename, or hypothesize
filenames. If the available evidence cannot support a section you would
otherwise want, drop that section or narrow its scope. If the available
evidence cannot support the document at all, set "abstention" and name
which of the listed files you inspected.

If evidence is insufficient or contradictory, include an "abstention" field explaining why.
"""

    return prompt


def _write_blueprint(
    output_dir: Path,
    blueprint: Dict[str, Any],
    brief_hash: str,
    response_metadata: Dict[str, Any]
) -> Path:
    """Write blueprint and runtime manifest to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write blueprint
    blueprint_path = output_dir / "blueprint.json"
    blueprint_path.write_text(json.dumps(blueprint, indent=2))

    # Write runtime manifest
    manifest = {
        "record_type": "RuntimeManifest",
        "schema_version": "HV-SCHEMA-1.0",
        "record_id": f"plan-{datetime.now(timezone.utc).isoformat()}",
        "run_id": output_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "inference",
        "compiler": {
            "name": "none",
            "version": "n/a",
            "executable_sha256": "0" * 64,
            "flags": []
        },
        "runtime_type": response_metadata["runtime_type"],
        "model_version_string": response_metadata["model_version"],
        "model_artifact_hash_if_local": None,
        "prompt_template_hash": response_metadata.get("prompt_template_hash"),
        "sampling": {"temperature": response_metadata["temperature"]},
        "seed_if_applicable": None,
        "api_endpoint": response_metadata.get("api_endpoint"),
        "request_id_if_available": response_metadata.get("request_id"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latency_ms": response_metadata.get("latency_ms", 0),
        "input_tokens": response_metadata["input_tokens"],
        "output_tokens": response_metadata["output_tokens"],
        "output_hash": sha256(json.dumps(blueprint).encode()).hexdigest(),
        "not_applicable_reason": None,
        "hardware": None,
        "network_policy": "api-only",
        "resource_limits": None,
    }

    manifest_path = output_dir / "runtime_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return blueprint_path


def run(args) -> int:
    """
    Execute hv plan command.

    Exit codes:
      0 - blueprint generated successfully
      2 - model abstained
      3 - invalid input or brief
      4 - internal error
      5 - security violation (budget exceeded)
    """

    try:
        # Load inputs
        snapshot_dir = args.snapshot
        brief_path = args.brief

        if not snapshot_dir.exists():
            print(f"Error: Snapshot directory not found: {snapshot_dir}", file=sys.stderr)
            return 3

        brief = _load_brief(brief_path)
        manifest = _load_snapshot_manifest(snapshot_dir)

        # Extract evidence file list from manifest.
        # hv init records these under "source_files" as snapshot-relative paths
        # (e.g. "source/intro.tex"). Fall back to "items" for older manifests.
        evidence_files = list(manifest.get("source_files", []))
        if not evidence_files:
            evidence_files = [
                item.get("path", item.get("name", "unknown"))
                for item in manifest.get("items", [])
            ]

        if not evidence_files:
            print(
                "Error: snapshot manifest lists no evidence files; "
                "re-run 'hv init' against a source directory with content",
                file=sys.stderr,
            )
            return 3

        # Create run directory
        run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        output_dir = Path.cwd() / ".humanvoice" / "runs" / run_id

        # Build prompt
        prompt = _build_plan_prompt(brief, evidence_files)
        system_prompt = (
            "You are a technical writing assistant. Your task is to generate "
            "a structured blueprint for a technical document. Respond with valid "
            "JSON matching the requested schema. If evidence is insufficient or "
            "contradictory, set the 'abstention' field in the blueprint."
        )

        # Load model config and invoke
        print("Loading model configuration...", file=sys.stderr)
        config = ModelConfig.from_profile()
        adapter = ModelAdapter(config, mock_mode=args.mock if hasattr(args, 'mock') else False)

        print(f"Generating blueprint with {config.model_version}...", file=sys.stderr)
        response = adapter.invoke(
            prompt=prompt,
            system_prompt=system_prompt,
            schema=PLAN_SCHEMA
        )

        # Check for abstention
        if response.abstention:
            print(f"Model abstained: {response.abstention}", file=sys.stderr)

            # Still write the abstention record
            abstention_record = {
                "blueprint": {
                    "sections": [],
                    "total_words": 0,
                    "abstention": response.abstention
                }
            }

            brief_hash = sha256(brief_path.read_bytes()).hexdigest()
            _write_blueprint(
                output_dir,
                abstention_record,
                brief_hash,
                {
                    "runtime_type": config.runtime_type,
                    "model_version": config.model_version,
                    "prompt_template_hash": config.prompt_template_hash,
                    "temperature": config.temperature,
                    "api_endpoint": config.api_endpoint,
                    "request_id": response.request_id,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                }
            )

            print(f"Abstention recorded to: {output_dir / 'blueprint.json'}", file=sys.stderr)
            return 2

        # Parse and validate blueprint
        try:
            blueprint = json.loads(response.text)
        except json.JSONDecodeError as e:
            print(f"Error: Model output is not valid JSON: {e}", file=sys.stderr)
            return 4

        # Write output
        brief_hash = sha256(brief_path.read_bytes()).hexdigest()
        blueprint_path = _write_blueprint(
            output_dir,
            blueprint,
            brief_hash,
            {
                "runtime_type": config.runtime_type,
                "model_version": config.model_version,
                "prompt_template_hash": config.prompt_template_hash,
                "temperature": config.temperature,
                "api_endpoint": config.api_endpoint,
                "request_id": response.request_id,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
        )

        # Report success
        num_sections = len(blueprint["blueprint"]["sections"])
        total_words = blueprint["blueprint"].get("total_words", 0)

        print(f"Blueprint generated: {num_sections} sections, {total_words} words")
        print(f"Output: {blueprint_path}")
        print(f"Tokens: {response.input_tokens} input / {response.output_tokens} output")
        print(f"Request ID: {response.request_id}")

        # Write CLI result
        cli_result = {
            "contract_version": "1.1.0",
            "command": "plan",
            "status": "released",
            "exit_code": 0,
            "run_id": run_id,
            "record_paths": [str(blueprint_path), str(output_dir / "runtime_manifest.json")],
            "blocking_reasons": [],
            "source_hash": sha256(snapshot_dir.as_posix().encode()).hexdigest(),
            "result_hash": sha256(json.dumps(blueprint).encode()).hexdigest(),
        }

        cli_result_path = output_dir / "cli_result.json"
        cli_result_path.write_text(json.dumps(cli_result, indent=2))

        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"Internal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 4
