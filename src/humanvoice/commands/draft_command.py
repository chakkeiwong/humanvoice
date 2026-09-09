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

from humanvoice.model import (
    ModelAdapter,
    ModelConfig,
    DRAFT_SCHEMA,
    BudgetTracker,
    BudgetExceeded,
    PROFILE_PATH,
)
from humanvoice.paths import new_run_dir, mint_run_id
from humanvoice.protected_objects import ProtectedManifest


# Output tokens allowed per word of budgeted prose.
#
# Deliberately generous. LaTeX with JSON-escaped backslashes tokenises far worse
# than plain prose: the ZLB run measured ~3.9 bytes per output token against a
# typical ~4.5 for English text, and the JSON envelope adds its own overhead. A
# tight conversion would truncate drafts that were the right length.
# Token budget multiplier for LaTeX generation.
#
# Raw LaTeX is token-dense: backslashes, braces, math mode delimiters, citation
# commands, and equation environments all add tokens beyond prose words. A
# 600-word draft with moderate math notation can easily require 2000+ tokens.
#
# This multiplier sets the output token ceiling as:
#   ceiling = word_budget × 1.2 (variance allowance) × WORDS_TO_TOKENS
#
# Set conservatively high (3.5) to avoid truncating valid drafts. Word count is
# validated post-generation, so overruns are caught and flagged for repair. A
# tight ceiling that cuts off mid-sentence is worse than a loose ceiling that
# lets an overrun complete—the former is unrecoverable without retry, the latter
# is fixable with editing.
WORDS_TO_TOKENS = 3.5

# Floor for the per-unit ceiling. A blueprint that omits word_budget, or sets an
# implausibly small one, must not produce a ceiling so low that every draft
# truncates -- that would read as a model failure rather than a planning error.
MIN_OUTPUT_CEILING_TOKENS = 600


def _output_ceiling_tokens(section: Dict[str, Any]) -> int:
    """
    Output token ceiling for one unit.

    Returns the profile's max_output_tokens_per_unit (16384) for all sections,
    allowing the model to complete its output without mid-sentence truncation.
    Word budget enforcement happens post-generation via word count validation,
    which is more robust than trying to predict token usage for LaTeX.

    Prior approach (deriving ceiling from word budget with WORDS_TO_TOKENS)
    caused consistent truncation because LaTeX token density is unpredictable:
    math-heavy sections can require 3-5 tokens/word, while prose sections need
    1.5-2 tokens/word. Pre-emptive ceilings cut off valid drafts.

    Post-generation validation catches overruns (word_count > budget × 1.2)
    and flags them for repair, which is recoverable. Mid-sentence truncation
    requires full retry and wastes the partial generation.

    Increased from 8192 to 16384 (2026-09-09) after ZLB test revealed large
    subsections exceeding the original ceiling even with fine-grained planning.
    """
    # Return profile maximum to avoid truncation. Word budget is validated
    # post-generation at lines 817-821.
    return 16384  # Matches inference_profile.json max_output_tokens_per_unit


def _extract_draft_metadata(latex: str) -> Dict[str, Any]:
    """
    Derive word count and citation keys from raw LaTeX, without a model call.

    Issue 6's plan proposed a second inference call to extract this. That doubles
    the cost per unit and introduces a failure branch ("what if the metadata call
    fails?") for two values the code can compute exactly. A model asked to count
    its own words would be estimating; this counts them.

    Word counting matches assemble_command's rule (\\w+ over the whole unit) so a
    draft's recorded count and its assembled count cannot disagree. That is a
    deliberate choice of consistency over precision: both include LaTeX command
    names, both are wrong in the same direction, and the budget check compares
    like with like.
    """
    word_count = len(re.findall(r'\w+', latex))

    # \cite, \citep, \citet, \parencite ... each taking one or more comma-separated
    # keys, optionally with [pre][post] arguments before the key group.
    citations: List[str] = []
    for match in re.finditer(r'\\[a-zA-Z]*cite[a-zA-Z]*\s*(?:\[[^\]]*\]\s*)*\{([^}]*)\}', latex):
        for key in match.group(1).split(','):
            key = key.strip()
            if key and key not in citations:
                citations.append(key)

    return {"word_count": word_count, "citations_needed": citations}


def _load_budget_tracker() -> BudgetTracker:
    """
    Build a document-level budget tracker from the inference profile.

    The profile has always declared max_document_input_tokens and
    max_document_output_tokens, but nothing read them: BudgetTracker existed and
    was never instantiated, so the budget block was documentation rather than
    enforcement. The ZLB run recorded 37,002 input tokens for one section against
    a declared per-unit cap of 12,000 and no one was told.

    Falls back to the declared defaults when the profile omits the block, so a
    malformed profile bounds the run rather than removing the bound.
    """
    try:
        profile = json.loads(PROFILE_PATH.read_text())
        budget_block = profile.get("budget", {})
    except Exception:
        budget_block = {}

    return BudgetTracker(
        max_input=budget_block.get("max_document_input_tokens", 250000),
        max_output=budget_block.get("max_document_output_tokens", 50000),
    )


def _find_undrafted_sections(
    snapshot_dir: Path, sections: List[Dict[str, Any]]
) -> List[int]:
    """
    Return the indices of blueprint sections that have no draft on disk.

    This is what `--missing` drafts and what makes a large run convergent: after a
    partial run the operator re-invokes once and only the outstanding units are
    attempted.

    Draft discovery is delegated to assemble_command._find_section_draft rather
    than reimplemented. The two must agree exactly -- if resume considered a unit
    drafted while assembly did not, `--missing` would report success and assembly
    would still record a gap for the same unit, and the run would never converge.
    """
    from humanvoice.commands.assemble_command import _find_section_draft

    runs_dir = snapshot_dir / ".humanvoice" / "runs"
    return [
        i
        for i, section in enumerate(sections)
        if _find_section_draft(runs_dir, i, section.get("title", "Untitled")) is None
    ]


def _load_blueprint(blueprint_path: Path) -> Dict[str, Any]:
    """
    Load blueprint from hv plan output.

    Issue 4: Supports both legacy flat sections[] and new chapters[].subsections[]
    hierarchy. The two-level form is the standard output of `hv plan` for large
    documents, but this command works on units (subsections or legacy sections),
    so it flattens the hierarchy on load.
    """
    if not blueprint_path.exists():
        raise ValueError(f"Blueprint not found: {blueprint_path}")

    try:
        blueprint = json.loads(blueprint_path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Blueprint is not valid JSON: {e}")

    if "blueprint" not in blueprint:
        raise ValueError("Blueprint missing required structure")

    bp = blueprint["blueprint"]

    # Legacy format: sections[] directly under blueprint
    if "sections" in bp:
        return blueprint

    # New format: chapters[].subsections[]
    if "chapters" in bp:
        # Flatten to sections[] for draft_command, which works per-unit
        sections = []
        for chapter_idx, chapter in enumerate(bp["chapters"]):
            for subsection_idx, subsection in enumerate(chapter.get("subsections", [])):
                # Annotate each unit with its chapter context for assembly
                subsection["chapter_index"] = chapter_idx
                subsection["chapter_title"] = chapter.get("title", f"Chapter {chapter_idx}")
                subsection["subsection_index"] = subsection_idx
                sections.append(subsection)

        # Replace chapters[] with flattened sections[]
        blueprint["blueprint"]["sections"] = sections
        return blueprint

    raise ValueError("Blueprint must have 'sections' (legacy) or 'chapters' (new)")


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

Respond with raw LaTeX only. No JSON, no code fences, no markdown, no commentary
before or after. Begin with \\section or \\subsection and end after your final
paragraph.

If evidence is insufficient to fulfil the purpose, or contradicts the
blueprint's premise, respond with exactly:

ABSTAIN: <one line explaining what evidence is missing or contradictory>

and nothing else.
"""

    return prompt


# A draft that opens with this marker is an abstention, not prose. Raw-LaTeX
# output has no JSON envelope to carry an abstention field, so the signal has to
# live in the text and be unambiguous against real LaTeX -- no section starts
# with a bare capitalised word followed by a colon.
ABSTAIN_MARKER = "ABSTAIN:"


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
    added = [{"type": obj.object_type, "hash": obj.hash}
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
            "preserved": [{"type": obj["object_type"], "hash": obj["hash"]} for obj in preserved],
            "missing": [{"type": obj["object_type"], "hash": obj["hash"]} for obj in missing],
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

    Three modes:
      --section N      draft section N only (single-shot)
      --missing        draft only sections that have no draft on disk (resume)
      --all            draft every section, continuing past failures (full sweep)

    Exit codes:
      0 - draft(s) generated successfully
      1 - register violation or structural failure in --section mode
      2 - model abstained in --section mode
      3 - invalid input or brief
      4 - internal error

    In --missing and --all modes, per-unit failures are reported but do not stop
    the run: the exit code reflects only fatal setup errors (missing files, parse
    failures), not individual draft outcomes. A partial success exits 0.
    """

    try:
        # Load inputs
        blueprint_path = args.blueprint
        brief_path = args.brief
        snapshot_dir = args.snapshot

        if not snapshot_dir.exists():
            print(f"Error: Snapshot directory not found: {snapshot_dir}", file=sys.stderr)
            return 3

        blueprint = _load_blueprint(blueprint_path)
        brief = _load_brief(brief_path)

        sections = blueprint["blueprint"]["sections"]

        # Determine which sections to draft based on mode
        if args.section is not None:
            # Single-section mode
            section_index = args.section
            if section_index < 0 or section_index >= len(sections):
                print(f"Error: Section index {section_index} out of range (0-{len(sections)-1})",
                      file=sys.stderr)
                return 3
            sections_to_draft = [section_index]
            batch_mode = False
        elif args.missing:
            # Resume mode: draft only sections without a draft on disk
            sections_to_draft = _find_undrafted_sections(snapshot_dir, sections)
            if not sections_to_draft:
                print("All sections have been drafted. Nothing to do.")
                return 0
            print(f"Resume mode: drafting {len(sections_to_draft)} sections without drafts on disk.")
            batch_mode = True
        elif args.all:
            # Full sweep mode: draft every section regardless of prior state
            sections_to_draft = list(range(len(sections)))
            print(f"Full sweep mode: drafting all {len(sections)} sections.")
            batch_mode = True
        else:
            # Should never reach here due to mutually_exclusive_group(required=True)
            print("Error: One of --section, --missing, or --all is required.", file=sys.stderr)
            return 3

        # Load shared context once
        source_manifest = _load_source_manifest(snapshot_dir)
        if source_manifest is None:
            print(
                "Warning: No source protected manifest found; drafting without "
                "protected-object routing (correspondence gates will block release)",
                file=sys.stderr,
            )

        # Draft each section
        failures = []
        successes = []

        # Load model config once (shared across all drafts in batch mode)
        config = ModelConfig.from_profile()

        # Document-level budget, shared across every unit in this invocation.
        #
        # The per-unit ceiling stops one unit from running away; this stops the
        # document from doing so. Without it a 60-unit run could spend 20x the
        # declared budget and nothing would say so until the bill arrived: the
        # profile's budget block was documentation rather than enforcement.
        #
        # In --missing and --all mode one tracker spans all units, so the cap is
        # a document cap rather than a per-unit one. In --section mode it spans a
        # single unit; the pipeline aggregates across invocations separately.
        budget = _load_budget_tracker()

        for section_index in sections_to_draft:
            section = sections[section_index]
            section_title = section.get("title", f"Section {section_index}")

            try:
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
                            f"Warning: Section '{section_title}' has no source line bounds; "
                            "no protected objects routed to this section",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            f"Routed {len(protected_objects)} protected objects to "
                            f"'{section_title}' (lines {section['source_start_line']}-"
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

                adapter = ModelAdapter(
                    config,
                    mock_mode=args.mock if hasattr(args, 'mock') else False,
                    snapshot_dir=snapshot_dir,
                    budget_tracker=budget,
                )

                # Size the output ceiling to this unit rather than letting every
                # unit inherit the profile maximum. A unit whose budget is 650
                # words has no business being allowed 2000 words of output: an
                # overrun is a planning error, and capping it here makes that
                # error surface as truncation on the unit that caused it instead
                # of as silent budget drift across the document.
                #
                # WORDS_TO_TOKENS is deliberately generous. LaTeX with escaped
                # backslashes tokenises far worse than prose -- the ZLB run
                # measured ~3.9 bytes/token -- and the JSON envelope adds its own
                # overhead, so a tight conversion would truncate correct drafts.
                ceiling = _output_ceiling_tokens(section)

                # Issue 6: the model returns raw LaTeX. The prompt asks for it
                # directly (see _build_draft_prompt) rather than patching a JSON
                # instruction after the fact.
                print(f"Generating draft for '{section_title}' with {config.model_version} "
                      f"(ceiling {ceiling} tokens)...",
                      file=sys.stderr)

                latex_response = adapter.invoke(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    schema=None,  # Raw LaTeX has no JSON shape to validate
                    purpose="draft_generation",
                    max_tokens=ceiling,
                )

                if latex_response.abstention:
                    raise ValueError(f"Model abstained: {latex_response.abstention}")

                if latex_response.truncated:
                    raise ValueError(
                        f"Output truncated at {latex_response.output_tokens} tokens "
                        f"(ceiling was {ceiling}). Unit may be too large for its budget."
                    )

                latex_content = latex_response.text.strip()

                # Raw output carries no abstention field, so the marker is the
                # signal. Checked before anything else parses the text as prose.
                if latex_content.startswith(ABSTAIN_MARKER):
                    reason = latex_content[len(ABSTAIN_MARKER):].strip()
                    raise ValueError(f"Model abstained: {reason or 'no reason given'}")

                # Metadata is computed locally, not asked for in a second call.
                #
                # The plan proposed a second inference call to extract word count
                # and citations. That doubles cost and adds a failure branch for
                # data the code can derive exactly: assemble_command already counts
                # words this way, and citation keys are a regex over \cite. A model
                # asked to count its own words would also be guessing.
                metadata = _extract_draft_metadata(latex_content)
                word_count = metadata["word_count"]

                # Check register compliance
                violations = _check_register_violations(latex_content, brief)
                if violations:
                    raise ValueError(f"Register violations: {', '.join(violations)}")

                # A zero-word draft is a missing unit, not a budget variance.
                if word_count == 0 or not latex_content:
                    raise ValueError("Draft contains no prose (word_count=0)")

                # Check word budget (±20% variance allowed)
                target = section.get("word_budget", 500)
                if word_count < target * 0.8 or word_count > target * 1.2:
                    print(f"Warning: Word count {word_count} outside target range "
                          f"[{int(target*0.8)}, {int(target*1.2)}]", file=sys.stderr)

                # _write_draft still takes the nested shape; it is now built here
                # from raw text rather than parsed out of the model's response.
                draft = {
                    "draft": {
                        "latex": latex_content,
                        "word_count": word_count,
                        "citations_needed": metadata["citations_needed"],
                        "abstention": None,
                    }
                }

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
                        "request_id": latex_response.request_id,
                        "input_tokens": latex_response.input_tokens,
                        "output_tokens": latex_response.output_tokens,
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
                print(f"✓ Section {section_index} '{section_title}': {word_count} words, "
                      f"{len(citations)} citations needed")
                print(f"  Output: {latex_path}")
                print(f"  Tokens: {latex_response.input_tokens} input / "
                      f"{latex_response.output_tokens} output")

                successes.append(section_index)

            except BudgetExceeded as e:
                # Budget exceeded is terminal in all modes: continuing would spend
                # more tokens against a budget that is already exhausted.
                print(f"✗ Budget exceeded during section {section_index} '{section_title}'",
                      file=sys.stderr)
                print(f"  {e}", file=sys.stderr)
                print(f"  Drafted {len(successes)}/{len(sections_to_draft)} sections before limit.",
                      file=sys.stderr)
                return 5

            except Exception as e:
                error_msg = str(e)
                print(f"✗ Section {section_index} '{section_title}' failed: {error_msg}",
                      file=sys.stderr)
                failures.append((section_index, section_title, error_msg))

                # In single-section mode, a failure is terminal
                if not batch_mode:
                    if "truncated" in error_msg.lower() or "abstained" in error_msg.lower():
                        return 2
                    elif "register violation" in error_msg.lower() or "word_count=0" in error_msg:
                        return 1
                    else:
                        return 4

        # Batch mode: report summary
        if batch_mode:
            print(f"\n{'='*60}")
            print(f"Batch draft complete: {len(successes)}/{len(sections_to_draft)} succeeded")
            if failures:
                print(f"\nFailed sections ({len(failures)}):")
                for idx, title, error in failures:
                    print(f"  Section {idx} '{title}': {error}")
            print(f"{'='*60}")

        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"Internal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 4
