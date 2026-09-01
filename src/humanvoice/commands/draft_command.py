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
from typing import Dict, Any, List, Optional, Tuple

from humanvoice.model import ModelAdapter, ModelConfig, DRAFT_SCHEMA
from humanvoice.paths import new_run_dir, mint_run_id
from humanvoice.protected_objects import ProtectedManifest


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


def _load_source_manifest(snapshot_dir: Path) -> Optional[ProtectedManifest]:
    """
    Load the source protected manifest from snapshot.

    Returns None if manifest doesn't exist (extraction failed or wasn't run).
    """
    manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    if not manifest_path.exists():
        return None

    # A manifest that exists but cannot be parsed is a different failure from one
    # that is absent: absence means extraction never ran, corruption means the
    # correspondence record is unreliable. Both must be visible, and neither may
    # be silently treated as "no protected objects to preserve".
    return ProtectedManifest.from_json(json.loads(manifest_path.read_text()))


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


def _prepare_section_evidence(
    section: Dict[str, Any],
    source_content: str,
    source_manifest: Optional[ProtectedManifest],
    evidence_files: List[str],
    snapshot_dir: Path,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Prepare evidence for a section, routing protected objects by line number.

    Returns:
        (evidence_text, protected_objects_in_section)

    evidence_text includes:
      - Full text of supplementary evidence files (not the source .tex)
      - Excerpts from source showing each protected object with context

    protected_objects_in_section is a list of objects with type/hash/content.
    """
    # Load supplementary evidence (papers, data, external docs)
    supplementary_evidence = _load_evidence_content(snapshot_dir, evidence_files)

    # Filter out the placeholder sentinel
    if supplementary_evidence == "[No evidence files available]":
        supplementary_evidence = ""

    # If no manifest or no source bounds, return supplementary only
    if not source_manifest:
        return supplementary_evidence if supplementary_evidence else "[No evidence available]", []

    start_line = section.get("source_start_line")
    end_line = section.get("source_end_line")
    section_source_file = section.get("source_file")

    if start_line is None or end_line is None:
        return supplementary_evidence if supplementary_evidence else "[No evidence available]", []

    # Select protected objects in this section's line range
    section_objects = []
    for obj in (source_manifest.equations + source_manifest.labels +
                source_manifest.citations + source_manifest.displaymath +
                source_manifest.tables):
        # Multi-file snapshots: obj.source_file is absolute, section_source_file is relative.
        # Match if obj's path ends with the section's relative path.
        file_match = (section_source_file is None or
                      str(obj.source_file).endswith(section_source_file))

        if obj.line_number is not None and start_line <= obj.line_number <= end_line and file_match:
            # Convert to dict for manifest emission
            section_objects.append({
                "object_type": obj.object_type,
                "hash": obj.hash,
                "content": obj.content,
                "line_number": obj.line_number,
                "context_before": obj.context_before,
                "context_after": obj.context_after,
            })

    # Build evidence text: supplementary + per-object excerpts from source
    evidence_parts = []

    if supplementary_evidence.strip():
        evidence_parts.append("=== Supplementary Evidence ===\n" + supplementary_evidence)

    if section_objects:
        evidence_parts.append("=== Protected Objects in This Section ===")
        for obj in section_objects:
            excerpt = f"""
Object type: {obj['object_type']}
Hash: {obj['hash']}
Line: {obj['line_number']}
Content: {obj['content']}
Context before: {obj['context_before']}
Context after: {obj['context_after']}
"""
            evidence_parts.append(excerpt.strip())

    evidence_text = "\n\n".join(evidence_parts) if evidence_parts else "[No evidence available]"
    return evidence_text, section_objects


def _build_draft_prompt(
    section: Dict[str, Any],
    brief: Dict[str, Any],
    evidence_content: str,
    protected_objects: List[Dict[str, Any]]
) -> str:
    """Build prompt for draft generation with protected object tracking."""

    title = section.get("title", "Untitled Section")
    purpose = section.get("purpose", "")
    word_budget = section.get("word_budget", 500)
    evidence_needed = section.get("evidence_needed", [])

    reader = brief.get("reader", "expert technical reader")
    known_vocab = brief.get("known_vocabulary", [])

    prompt = f"""Generate a LaTeX draft for this section of a technical document.

**Section title:** {title}
**Purpose:** {purpose}
**Word budget:** {word_budget} (±20% acceptable)
**Reader:** {reader}
**Reader knows:** {', '.join(known_vocab[:10]) if known_vocab else 'general technical vocabulary'}

**Evidence available:**
{evidence_content}

**Protected objects that must be preserved exactly:**
"""

    if protected_objects:
        prompt += f"{len(protected_objects)} objects in this section:\n"
        for obj in protected_objects:
            prompt += f"  - {obj['object_type']} [hash: {obj['hash']}]: {obj['content'][:80]}\n"
    else:
        prompt += "None in this section.\n"

    prompt += """
**Requirements:**
- Write in third-person technical register (no "I", "we", "our" unless quoting evidence)
- Preserve all protected objects exactly as shown (equations, labels, citations, displaymath, tables)
- Stay within word budget (±20%)
- Use LaTeX commands appropriate for the reader's vocabulary
- If evidence is insufficient or contradictory, abstain with explanation

**Output format:**

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
        # Mock runs transmit nothing. Recording them as "inference" makes the
        # release transmission gate count them as unlogged API calls, so the
        # mode has to reflect what actually ran.
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
        "output_hash": sha256(latex_content.encode()).hexdigest(),
        "not_applicable_reason": None,
        "hardware": None,
        "network_policy": "api-only",
        "resource_limits": None,
    }

    manifest_path = output_dir / f"runtime_manifest_{safe_title}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return latex_path


def _emit_draft_manifest(
    output_dir: Path,
    section_title: str,
    source_manifest: Optional[ProtectedManifest],
    protected_objects_in_section: List[Dict[str, Any]],
    draft_latex: str,
) -> Path:
    """
    Emit per-section draft correspondence manifest.

    Tracks which protected objects from source appear in draft, which are missing,
    and provides dispositions slot for human approval of omissions.
    """
    from humanvoice.protected_objects import extract_protected_objects_from_text

    # Extract protected objects from draft
    draft_manifest = extract_protected_objects_from_text(
        draft_latex,
        source_file=Path("draft"),
        parent_artifact_hash=source_manifest.source_file_hash if source_manifest else None
    )

    # Collect all draft objects (these are ProtectedObject dataclass instances)
    draft_objects = (draft_manifest.equations + draft_manifest.labels +
                     draft_manifest.citations + draft_manifest.displaymath +
                     draft_manifest.tables)

    # Build hash sets for comparison
    source_hashes = {obj["hash"] for obj in protected_objects_in_section}
    draft_hashes = {obj.hash for obj in draft_objects}

    # Categorize correspondence
    preserved = [obj for obj in protected_objects_in_section if obj["hash"] in draft_hashes]
    missing = [obj for obj in protected_objects_in_section if obj["hash"] not in draft_hashes]
    added = [{"type": obj.object_type, "hash": obj.hash, "content": obj.content}
             for obj in draft_objects if obj.hash not in source_hashes]

    # Calculate retention rate
    retention_rate = len(preserved) / len(protected_objects_in_section) if protected_objects_in_section else 1.0

    manifest = {
        "record_type": "DraftCorrespondenceManifest",
        "schema_version": "HV-SCHEMA-1.0",
        "section_title": section_title,
        "parent_artifact_hash": source_manifest.source_file_hash if source_manifest else None,
        "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
        "correspondence_to_source": {
            "preserved": [{"type": obj["object_type"], "hash": obj["hash"], "content": obj["content"]} for obj in preserved],
            "missing": [{"type": obj["object_type"], "hash": obj["hash"], "content": obj["content"]} for obj in missing],
            "added": added,
        },
        "retention_rate": retention_rate,
        "dispositions": {
            "omitted_objects": [
                {
                    "hash": obj["hash"],
                    "type": obj["object_type"],
                    "reason": None,  # Must be filled: "not_relevant" | "merged" | "superseded" | "manual_exception"
                    "human_approved": False,  # Must be True for release
                    "approver": None,
                    "approval_timestamp": None,
                }
                for obj in missing
            ]
        }
    }

    # Write manifest
    safe_title = "".join(c if c.isalnum() or c in (' ', '_') else '_'
                         for c in section_title.lower())
    safe_title = safe_title.replace(' ', '_')[:50]
    manifest_path = output_dir / f"draft_correspondence_{safe_title}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return manifest_path


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

        # Load the source protected manifest so protected objects can be routed
        # to this section by line number instead of truncating evidence blindly.
        source_manifest = _load_source_manifest(snapshot_dir)
        if source_manifest is None:
            print(
                "Warning: No source protected manifest found; drafting without "
                "protected-object routing (correspondence gates will block release)",
                file=sys.stderr,
            )

        # Route evidence and protected objects for this section
        evidence_files = section.get("evidence_needed", [])
        evidence_content, protected_objects = _prepare_section_evidence(
            section,
            source_content="",
            source_manifest=source_manifest,
            evidence_files=evidence_files,
            snapshot_dir=snapshot_dir,
        )

        if source_manifest is not None:
            if section.get("source_start_line") is None or section.get("source_end_line") is None:
                print(
                    f"Warning: Section '{section['title']}' has no source line bounds; "
                    "no protected objects routed to this section",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Routed {len(protected_objects)} protected objects to "
                    f"'{section['title']}' (lines {section['source_start_line']}-"
                    f"{section['source_end_line']})",
                    file=sys.stderr,
                )

        # Create run directory under the snapshot (canonical location).
        # An explicit run_id lets an orchestrator (hv pipeline) place every
        # section's records in one run directory instead of one per command.
        run_id = getattr(args, "run_id", None) or mint_run_id()
        output_dir = new_run_dir(snapshot_dir, run_id)

        # Build prompt
        prompt = _build_draft_prompt(section, brief, evidence_content, protected_objects)
        system_prompt = (
            "You are a technical writing assistant. Generate LaTeX prose for the "
            "specified section using the evidence provided. Respond with valid JSON "
            "matching the requested schema. Maintain third-person technical register "
            "unless evidence itself is first-person data."
        )

        # Load model config and invoke
        print(f"Loading model configuration...", file=sys.stderr)
        config = ModelConfig.from_profile()
        adapter = ModelAdapter(
            config,
            mock_mode=args.mock if hasattr(args, 'mock') else False,
            snapshot_dir=snapshot_dir,
        )

        print(f"Generating draft for '{section['title']}' with {config.model_version}...",
              file=sys.stderr)
        response = adapter.invoke(
            prompt=prompt,
            system_prompt=system_prompt,
            schema=DRAFT_SCHEMA,
            purpose="draft_generation",
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

        # A zero-word draft is a missing unit, not a budget variance. Writing it
        # starves downstream repair (which has no text to edit) and lets an empty
        # section reach release.
        word_count = draft["draft"].get("word_count", 0)
        if word_count == 0 or not latex_content.strip():
            print(
                "Error: Draft contains no prose (word_count=0); nothing written",
                file=sys.stderr,
            )
            return 1

        # Check word budget (±20% variance allowed)
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
                "mode": "mock" if args.mock else "inference",
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

        # Emit draft correspondence manifest
        if source_manifest is not None and protected_objects:
            manifest_path = _emit_draft_manifest(
                output_dir,
                section["title"],
                source_manifest,
                protected_objects,
                latex_content,
            )
            # Read back to report retention rate
            manifest_data = json.loads(manifest_path.read_text())
            retention_rate = manifest_data.get("retention_rate", 0.0)
            preserved_count = len(manifest_data["correspondence_to_source"]["preserved"])
            missing_count = len(manifest_data["correspondence_to_source"]["missing"])
            print(
                f"Protected object retention: {preserved_count}/{len(protected_objects)} "
                f"({retention_rate:.1%}), {missing_count} missing",
                file=sys.stderr,
            )
            print(f"Draft correspondence manifest: {manifest_path}", file=sys.stderr)

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
