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
import re
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Dict, Any, List

from humanvoice.model import ModelAdapter, ModelConfig, PLAN_SCHEMA
from humanvoice.paths import new_run_dir, mint_run_id


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


def _extract_section_structure(source_text: str, source_file: str) -> List[Dict[str, Any]]:
    """
    Parse \\section{...} from LaTeX source, compute line ranges.

    Returns list of dicts with keys: title, start_line, end_line, source_file.
    If the source has no \\section{} blocks, returns a single implicit section
    covering the entire file.
    """
    lines = source_text.split('\n')
    sections = []

    for i, line in enumerate(lines, start=1):
        m = re.search(r'\\section\{([^}]+)\}', line)
        if m:
            sections.append({
                'title': m.group(1).strip(),
                'start_line': i,
                'source_file': source_file,
            })

    # Compute end_line: next section's start - 1, or EOF
    for idx, sec in enumerate(sections):
        if idx + 1 < len(sections):
            sec['end_line'] = sections[idx + 1]['start_line'] - 1
        else:
            sec['end_line'] = len(lines)

    # Front matter (abstract, preamble equations/citations) sits before the first
    # \section{}. Without this, those protected objects belong to no section, are
    # never routed into any draft's evidence, and count as missing in the
    # correspondence gate -- sinking the preservation rate on any document with an
    # abstract. Extend the first section back to line 1 so coverage is total.
    if sections:
        sections[0]['start_line'] = 1

    # If no sections found, treat entire file as one implicit section
    if not sections:
        sections.append({
            'title': '(entire file)',
            'start_line': 1,
            'end_line': len(lines),
            'source_file': source_file,
        })

    return sections


def _load_snapshot_manifest(snapshot_dir: Path) -> Dict[str, Any]:
    """Load snapshot manifest created by hv init."""
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Snapshot manifest not found: {manifest_path}")

    return json.loads(manifest_path.read_text())


def _build_plan_prompt(
    brief: Dict[str, Any],
    evidence_files: list[str],
    snapshot_dir: Path
) -> str:
    """Build prompt for plan generation, including source structure."""

    # Extract key constraints from brief
    reader = brief.get("reader", "expert technical reader")
    decision = brief.get("decision", "unspecified decision")
    genre = brief.get("genre", "technical document")
    max_words = brief.get("max_words") or brief.get("target_word_count", 5000)
    known_vocab = brief.get("known_vocabulary", [])
    protected = brief.get("protected_objects", [])

    # Extract section structure from source files
    all_sections = []
    for rel_path in evidence_files:
        abs_path = snapshot_dir / rel_path
        if abs_path.exists() and abs_path.suffix == '.tex':
            source_text = abs_path.read_text(encoding='utf-8', errors='ignore')
            file_sections = _extract_section_structure(source_text, rel_path)
            all_sections.extend(file_sections)

    # Build source structure text for prompt
    structure_text = ""
    if all_sections:
        structure_text = "\n**Source Structure:**\n\n"
        structure_text += (
            "The evidence files contain the following sectional divisions. Each blueprint section\n"
            "you create should map to one or more of these source regions so that protected objects\n"
            "(equations, labels, citations) can be correctly routed. Include \"source_file\",\n"
            "\"source_start_line\", and \"source_end_line\" fields in each blueprint section to\n"
            "specify which source lines it draws from.\n\n"
        )
        current_file = None
        for sec in all_sections:
            if sec['source_file'] != current_file:
                current_file = sec['source_file']
                structure_text += f"File: {current_file}\n"
            structure_text += f"  - \"{sec['title']}\" (lines {sec['start_line']}-{sec['end_line']})\n"
        structure_text += "\n"

    prompt = f"""Generate a narrative blueprint for a {genre}.

**Reader:** {reader}
**Decision question:** {decision}
**Word target:** {max_words}

**Evidence available:**
{chr(10).join(f"- {ef}" for ef in evidence_files[:20])}
{"... (truncated)" if len(evidence_files) > 20 else ""}

{structure_text}**Constraints:**
- The reader knows: {', '.join(known_vocab[:10]) if known_vocab else 'general technical vocabulary'}
- Protected objects that must be preserved exactly: {len(protected)} items
- Register: third-person technical exposition, no first-person claims

**Task:**
Generate a blueprint with sections covering:
1. What problem or decision this addresses
2. What mechanism or approach is proposed
3. Which evidence is decisive for each claim
4. What qualifications change the interpretation

**Output format:**

For documents under 5,000 words, return flat sections:
{{
  "blueprint": {{
    "sections": [
      {{
        "title": "Section title",
        "purpose": "What this section accomplishes for the reader",
        "evidence_needed": ["source/intro.tex"],
        "word_budget": 500,
        "source_file": "source/intro.tex",
        "source_start_line": 1,
        "source_end_line": 50
      }}
    ],
    "total_words": {max_words}
  }}
}}

For documents of 5,000 words or more, organize as chapters with subsections.
Each subsection should target 800-1200 words to fit within per-unit output limits:
{{
  "blueprint": {{
    "chapters": [
      {{
        "title": "Chapter 1: Problem Statement",
        "purpose": "Establish the decision context",
        "subsections": [
          {{
            "title": "Background",
            "purpose": "Contextual foundation",
            "evidence_needed": ["source/intro.tex"],
            "word_budget": 800,
            "source_file": "source/intro.tex",
            "source_start_line": 1,
            "source_end_line": 50
          }},
          {{
            "title": "Key challenges",
            "purpose": "State the core problem",
            "evidence_needed": ["source/intro.tex"],
            "word_budget": 900,
            "source_file": "source/intro.tex",
            "source_start_line": 51,
            "source_end_line": 120
          }}
        ]
      }}
    ],
    "total_words": {max_words}
  }}
}}

**Subsection sizing rule (critical for documents ≥5k words):**
Every subsection must stay between 600-900 words, targeting 700-800 for safety.
If a conceptual unit would naturally be longer, split it across multiple subsections.
Example: a 3,000-word chapter becomes 4 subsections of ~750 words each, NOT three
1,000-word subsections.

Exceeding 900 words per subsection risks truncation during drafting.

**Guidelines:**
- Sections/subsections should sum to the word target (±10%)
- Map evidence to specific claims
- Build from problem → mechanism → evidence → qualifications
- Avoid protected objects in titles (they appear in content)

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
        # Mock runs transmit nothing, so they must not be recorded as inference:
        # the release transmission gate counts inference runs and blocks when
        # they are not matched by transmission-log entries.
        "mode": response_metadata.get("mode", "inference"),
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

        # Create run directory under the snapshot (canonical location).
        # An explicit run_id lets an orchestrator (hv pipeline) place every
        # stage's records in one run directory instead of one per command.
        run_id = getattr(args, "run_id", None) or mint_run_id()
        output_dir = new_run_dir(snapshot_dir, run_id)

        # Build prompt
        prompt = _build_plan_prompt(brief, evidence_files, snapshot_dir)
        system_prompt = (
            "You are a technical writing assistant. Your task is to generate "
            "a structured blueprint for a technical document. Respond with valid "
            "JSON matching the requested schema. If evidence is insufficient or "
            "contradictory, set the 'abstention' field in the blueprint."
        )

        # Load model config and invoke
        print("Loading model configuration...", file=sys.stderr)
        config = ModelConfig.from_profile()
        adapter = ModelAdapter(
            config,
            mock_mode=args.mock if hasattr(args, 'mock') else False,
            snapshot_dir=snapshot_dir,
        )

        print(f"Generating blueprint with {config.model_version}...", file=sys.stderr)
        response = adapter.invoke(
            prompt=prompt,
            system_prompt=system_prompt,
            schema=PLAN_SCHEMA,
            purpose="plan_generation",
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
                    "mode": "mock" if args.mock else "inference",
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

        # Validate and clamp section bounds
        sections = blueprint.get("blueprint", {}).get("sections", [])
        for sec in sections:
            source_file = sec.get("source_file")
            start_line = sec.get("source_start_line")
            end_line = sec.get("source_end_line")

            # Skip sections without bounds (partial coverage allowed)
            if start_line is None or end_line is None:
                continue

            # Validate source_file is in the manifest
            if source_file and source_file not in evidence_files:
                print(
                    f"Warning: section '{sec.get('title', 'Untitled')}' references "
                    f"unknown source_file '{source_file}'; defaulting to first evidence file",
                    file=sys.stderr
                )
                sec["source_file"] = evidence_files[0] if evidence_files else None

            # Clamp bounds to actual file length
            if source_file:
                abs_path = snapshot_dir / source_file
                if abs_path.exists():
                    file_lines = len(abs_path.read_text(encoding='utf-8', errors='ignore').split('\n'))
                    sec["source_start_line"] = max(1, min(start_line, file_lines))
                    sec["source_end_line"] = max(1, min(end_line, file_lines))

                    # Swap if reversed
                    if sec["source_start_line"] > sec["source_end_line"]:
                        sec["source_start_line"], sec["source_end_line"] = sec["source_end_line"], sec["source_start_line"]

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
                "mode": "mock" if args.mock else "inference",
            }
        )

        # Report success
        if "sections" in blueprint["blueprint"]:
            num_units = len(blueprint["blueprint"]["sections"])
            unit_label = "sections"
        elif "chapters" in blueprint["blueprint"]:
            num_chapters = len(blueprint["blueprint"]["chapters"])
            num_subsections = sum(len(ch["subsections"]) for ch in blueprint["blueprint"]["chapters"])
            num_units = num_subsections
            unit_label = f"chapters ({num_chapters} chapters, {num_subsections} subsections)"
        else:
            num_units = 0
            unit_label = "units"

        total_words = blueprint["blueprint"].get("total_words", 0)

        print(f"Blueprint generated: {num_units} {unit_label}, {total_words} words")
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
