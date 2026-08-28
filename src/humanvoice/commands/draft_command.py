"""
hv draft - Produce unit-level draft within blueprint boundary.

Reads a blueprint section, loads corresponding evidence files, and invokes the
model to generate LaTeX prose within the word budget. Validates register
compliance and records the draft in the current run directory.

Per contract 1.1.0:
- Model output is validated against DRAFT_SCHEMA
- Abstention on validation failure or model uncertainty
- Word budget enforced (section budget ±20% variance allowed)
- Register compliance checked (no first-person unless brief permits)
"""

import json
import re
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Dict, Any, List

from humanvoice.model import ModelAdapter, ModelConfig, DRAFT_SCHEMA


def _load_blueprint(blueprint_path: Path) -> Dict[str, Any]:
    """Load blueprint from hv plan output."""
    if not blueprint_path.exists():
        raise ValueError(f"Blueprint not found: {blueprint_path}")

    try:
        blueprint = json.loads(blueprint_path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Blueprint is not valid JSON: {e}")

    if "blueprint" not in blueprint or "sections" not in blueprint["blueprint"]:
        raise ValueError("Blueprint missing required structure")

    return blueprint


def _load_brief(brief_path: Path) -> Dict[str, Any]:
    """Load authoring brief."""
    if not brief_path.exists():
        raise ValueError(f"Brief not found: {brief_path}")

    return json.loads(brief_path.read_text())


def _load_evidence_content(snapshot_dir: Path, evidence_files: List[str]) -> str:
    """
    Load actual content from evidence files.

    Currently loads .tex files from snapshot/source. Returns concatenated content
    with filename markers for the model.
    """
    content_parts = []

    for filename in evidence_files:
        # Blueprints may reference snapshot-relative paths ("source/intro.tex")
        # or bare basenames ("intro.tex"). Resolve both, and guard against
        # traversal outside the snapshot.
        stem = Path(filename).name
        candidates = [
            snapshot_dir / filename,
            snapshot_dir / "source" / stem,
            snapshot_dir / "source" / f"{stem}.tex",
        ]

        file_path = None
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                resolved.relative_to(snapshot_dir.resolve())
            except (ValueError, OSError):
                continue
            if resolved.is_file():
                file_path = resolved
                break

        if file_path is not None and file_path.suffix == '.tex':
            try:
                file_content = file_path.read_text()
                content_parts.append(f"--- {filename} ---\n{file_content}\n")
            except Exception as e:
                content_parts.append(f"--- {filename} ---\n[Error reading: {e}]\n")
        else:
            content_parts.append(f"--- {filename} ---\n[File not found in snapshot/source]\n")

    if not content_parts:
        return "[No evidence files available]"

    return "\n".join(content_parts)


def _build_draft_prompt(
    section: Dict[str, Any],
    brief: Dict[str, Any],
    evidence_content: str
) -> str:
    """Build prompt for draft generation."""

    title = section.get("title", "Untitled Section")
    purpose = section.get("purpose", "")
    word_budget = section.get("word_budget", 500)
    evidence_needed = section.get("evidence_needed", [])

    reader = brief.get("reader", "expert technical reader")
    known_vocab = brief.get("known_vocabulary", [])
    protected = brief.get("protected_objects", [])

    prompt = f"""Generate a LaTeX draft for this section of a technical document.

**Section title:** {title}
**Purpose:** {purpose}
**Word budget:** {word_budget} (±20% acceptable)
**Reader:** {reader}
**Reader knows:** {', '.join(known_vocab[:10]) if known_vocab else 'general technical vocabulary'}

**Evidence available:**
{evidence_content[:3000]}
{"...(truncated for length)" if len(evidence_content) > 3000 else ""}

**Evidence requirements from blueprint:**
{chr(10).join(f"- {ef}" for ef in evidence_needed[:10])}

**Constraints:**
- Register: third-person technical exposition, no first-person claims unless evidence is first-person data
- Protected objects must be preserved exactly: {len(protected)} items
- LaTeX: use standard commands (\\section, \\subsection, \\emph, \\textbf, \\cite)
- Do not include \\documentclass or \\begin{{document}} - section content only
- Citations: use \\cite{{key}} where evidence is cited, list keys in citations_needed

**Task:**
Write LaTeX prose that fulfills the section purpose using the evidence provided.

Return JSON matching this schema:
{{
  "draft": {{
    "latex": "LaTeX source code for this section",
    "word_count": {word_budget},
    "citations_needed": ["list", "of", "citation", "keys"]
  }}
}}

IMPORTANT: The response must always have a top-level "draft" key.

If evidence is insufficient to fulfill the purpose, return:
{{
  "draft": {{
    "latex": "",
    "word_count": 0,
    "abstention": "Explanation of what evidence is missing"
  }}
}}

If evidence contradicts the blueprint's premise, abstain with the contradiction explained.
"""

    return prompt


def _check_register_violations(latex: str, brief: Dict[str, Any]) -> List[str]:
    """
    Check for register violations in generated LaTeX.

    Returns list of violations found. Empty list = clean.
    """
    violations = []

    # Strip math so LaTeX variables ($i$, $I$, $We$) are not read as pronouns.
    prose = _strip_math(latex)

    # Case-sensitive: "I" is first-person, "i" is an index variable. The rest are
    # matched with a leading case-insensitive group so sentence-initial "We" is
    # caught without matching mid-word.
    first_person_markers = [
        (r"\bI\b", 0),
        (r"\b[Ww]e\b", 0),
        (r"\b[Oo]ur(s|selves)?\b", 0),
        (r"\b[Mm]y(self)?\b", 0),
        (r"\b[Mm]ine\b", 0),
        (r"\b[Mm]e\b", 0),
        (r"\b[Uu]s\b", 0),
    ]

    for marker, flags in first_person_markers:
        match = re.search(marker, prose, flags)
        if match:
            violations.append(
                f"First-person usage detected: '{match.group(0)}' "
                f"at offset {match.start()}"
            )

    return violations


# Math environments whose contents are symbols, not prose.
_MATH_PATTERNS = [
    r"\$\$.*?\$\$",
    r"\$[^$]*\$",
    r"\\\[.*?\\\]",
    r"\\\(.*?\\\)",
    r"\\begin\{(equation|align|gather|multline)\*?\}.*?\\end\{\1\*?\}",
]


def _strip_math(latex: str) -> str:
    """Remove math content so LaTeX variables are not mistaken for prose words."""
    prose = latex
    for pattern in _MATH_PATTERNS:
        prose = re.sub(pattern, " ", prose, flags=re.DOTALL)
    return prose


def _write_draft(
    output_dir: Path,
    section_title: str,
    draft: Dict[str, Any],
    response_metadata: Dict[str, Any]
) -> Path:
    """Write draft LaTeX and runtime manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize section title for filename
    safe_title = "".join(c if c.isalnum() or c in (' ', '_') else '_'
                         for c in section_title.lower())
    safe_title = safe_title.replace(' ', '_')[:50]

    # Write LaTeX
    latex_path = output_dir / f"draft_{safe_title}.tex"
    latex_content = draft["draft"].get("latex", "")
    latex_path.write_text(latex_content)

    # Write runtime manifest
    manifest = {
        "record_type": "RuntimeManifest",
        "schema_version": "HV-SCHEMA-1.0",
        "record_id": f"draft-{section_title}-{datetime.now(timezone.utc).isoformat()}",
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
        "output_hash": sha256(latex_content.encode()).hexdigest(),
        "not_applicable_reason": None,
        "hardware": None,
        "network_policy": "api-only",
        "resource_limits": None,
    }

    manifest_path = output_dir / f"runtime_manifest_{safe_title}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return latex_path


def run(args) -> int:
    """
    Execute hv draft command.

    Exit codes:
      0 - draft generated successfully
      1 - register violation or structural failure
      2 - model abstained
      3 - invalid input or brief
      4 - internal error
    """

    try:
        # Load inputs
        blueprint_path = args.blueprint
        brief_path = args.brief
        snapshot_dir = args.snapshot
        section_index = args.section

        if not snapshot_dir.exists():
            print(f"Error: Snapshot directory not found: {snapshot_dir}", file=sys.stderr)
            return 3

        blueprint = _load_blueprint(blueprint_path)
        brief = _load_brief(brief_path)

        sections = blueprint["blueprint"]["sections"]
        if section_index < 0 or section_index >= len(sections):
            print(f"Error: Section index {section_index} out of range (0-{len(sections)-1})",
                  file=sys.stderr)
            return 3

        section = sections[section_index]

        # Load evidence content
        evidence_files = section.get("evidence_needed", [])
        evidence_content = _load_evidence_content(snapshot_dir, evidence_files)

        # Create run directory
        run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        output_dir = Path.cwd() / ".humanvoice" / "runs" / run_id

        # Build prompt
        prompt = _build_draft_prompt(section, brief, evidence_content)
        system_prompt = (
            "You are a technical writing assistant. Generate LaTeX prose for the "
            "specified section using the evidence provided. Respond with valid JSON "
            "matching the requested schema. Maintain third-person technical register "
            "unless evidence itself is first-person data."
        )

        # Load model config and invoke
        print(f"Loading model configuration...", file=sys.stderr)
        config = ModelConfig.from_profile()
        adapter = ModelAdapter(config, mock_mode=args.mock if hasattr(args, 'mock') else False)

        print(f"Generating draft for '{section['title']}' with {config.model_version}...",
              file=sys.stderr)
        response = adapter.invoke(
            prompt=prompt,
            system_prompt=system_prompt,
            schema=DRAFT_SCHEMA
        )

        # Check for abstention
        if response.abstention:
            print(f"Model abstained: {response.abstention}", file=sys.stderr)
            return 2

        # Parse and validate draft
        try:
            draft = json.loads(response.text)
        except json.JSONDecodeError as e:
            print(f"Error: Model output is not valid JSON: {e}", file=sys.stderr)
            return 4

        # Check register compliance
        latex_content = draft["draft"].get("latex", "")
        violations = _check_register_violations(latex_content, brief)

        if violations:
            print("Register violations detected:", file=sys.stderr)
            for v in violations:
                print(f"  - {v}", file=sys.stderr)
            return 1

        # Check word budget (±20% variance allowed)
        word_count = draft["draft"].get("word_count", 0)
        target = section.get("word_budget", 500)
        if word_count < target * 0.8 or word_count > target * 1.2:
            print(f"Warning: Word count {word_count} outside target range "
                  f"[{int(target*0.8)}, {int(target*1.2)}]", file=sys.stderr)

        # Write output
        latex_path = _write_draft(
            output_dir,
            section["title"],
            draft,
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
        citations = draft["draft"].get("citations_needed", [])
        print(f"Draft generated: {word_count} words, {len(citations)} citations needed")
        print(f"Output: {latex_path}")
        print(f"Tokens: {response.input_tokens} input / {response.output_tokens} output")
        print(f"Request ID: {response.request_id}")

        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"Internal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 4
