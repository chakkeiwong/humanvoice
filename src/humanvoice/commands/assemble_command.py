#!/usr/bin/env python3
"""
hv assemble - Assemble drafted sections into complete document

Collects individual section drafts from run directories and merges them into
a single document following blueprint order. Generates blacklined comparison
if latexdiff is available.

Exit codes:
  0 - assembly successful
  2 - abstention (missing section, invalid blueprint, etc.)
  3 - invalid input
  4 - internal error
"""

import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set


def _load_manifest(snapshot_dir: Path) -> Dict[str, Any]:
    """Load snapshot manifest."""
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Snapshot not initialized: {manifest_path}")

    return json.loads(manifest_path.read_text())


def _load_brief(brief_path: Path) -> Dict[str, Any]:
    """Load authoring brief."""
    if not brief_path.exists():
        raise ValueError(f"Brief not found: {brief_path}")

    return json.loads(brief_path.read_text())


def _find_blueprint(snapshot_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Find the most recent blueprint from plan runs.

    Returns None if no blueprint found.
    """
    runs_dir = snapshot_dir / ".humanvoice" / "runs"
    if not runs_dir.exists():
        return None

    # Find all blueprint.json files
    blueprints = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue

        blueprint_path = run_dir / "blueprint.json"
        if blueprint_path.exists():
            try:
                bp = json.loads(blueprint_path.read_text())
                blueprints.append((run_dir.name, bp, blueprint_path))
            except Exception:
                continue

    if not blueprints:
        return None

    # Return most recent by run directory name (timestamp-based)
    blueprints.sort(key=lambda x: x[0], reverse=True)
    return blueprints[0][1]


def _draft_filename_stem(section_title: str) -> str:
    """
    Reproduce draft_command._write_draft's filename sanitisation.

    Assembly locates drafts by name, so this must match the writer exactly. Any
    divergence reports a section as un-drafted while its file sits on disk.
    """
    safe = "".join(
        c if c.isalnum() or c in (" ", "_") else "_"
        for c in section_title.lower()
    )
    return safe.replace(" ", "_")[:50]


def _latest_published_revision(draft_path: Path) -> Optional[Path]:
    """
    Return the newest repaired copy of a draft, or None if it was never repaired.

    `hv repair` does not edit a draft in place. It publishes a child revision at
    <draft dir>/revisions/rev-<cycle>-<hash>/<draft filename> and leaves the
    original untouched, so the newest text is the deepest published revision
    rather than the file the draft stage wrote.

    A revision counts as published only once its revision_manifest.json exists --
    repair writes that manifest last, so an interrupted repair leaves a directory
    this function correctly ignores. Cycle numbers are zero-padded, so lexical
    order over the rev-* directory names is cycle order.
    """
    revisions_dir = draft_path.parent / "revisions"
    if not revisions_dir.is_dir():
        return None

    published = sorted(revisions_dir.glob("rev-*/revision_manifest.json"))
    for manifest_path in reversed(published):
        candidate = manifest_path.parent / draft_path.name
        if candidate.exists():
            return candidate

    return None


def _resolve_draft(draft_path: Path, run_id: str) -> Tuple[Path, str]:
    """
    Prefer a draft's repaired text over its original.

    Assembly must consume what repair produced. Reading the draft-stage file
    would silently discard every repair, shipping text whose findings were
    reported as cleared -- the failure mode this system exists to prevent.
    """
    revised = _latest_published_revision(draft_path)
    if revised is not None:
        return revised, run_id
    return draft_path, run_id


def _find_section_draft(runs_dir: Path, section_index: int, section_title: str) -> Optional[Tuple[Path, str]]:
    """
    Find the most recent draft for a given section, repairs included.

    Matching is by filename, because draft_command derives the filename from the
    section title. Title matching holds however the drafts are distributed across
    run directories -- one run per section (a manual `hv draft --section N` loop)
    or every section inside a single run (`hv pipeline`, which threads one run_id
    through all stages).

    Positional matching is kept as a fallback for snapshots whose titles have
    since changed in the blueprint, but only in the layout where it is
    unambiguous: exactly one draft per run directory, drafted in section order.
    Ordering is by run_id, which is timestamp-derived and therefore chronological.

    Returns (draft_path, run_id) or None if not found. The returned path is the
    newest published revision when the draft was repaired.
    """
    if not runs_dir.is_dir():
        return None

    run_dirs = sorted(d for d in runs_dir.iterdir() if d.is_dir())

    # Preferred: match the filename the draft stage would have written. When a
    # section was re-drafted across several runs, the newest run wins.
    wanted = f"draft_{_draft_filename_stem(section_title)}.tex"
    for run_dir in reversed(run_dirs):
        candidate = run_dir / wanted
        if candidate.exists():
            return _resolve_draft(candidate, run_dir.name)

    # Fallback: one draft per run directory, matched by position.
    single_draft_runs = []
    for run_dir in run_dirs:
        draft_files = list(run_dir.glob("draft_*.tex"))
        if len(draft_files) == 1:
            single_draft_runs.append((draft_files[0], run_dir.name))

    if len(single_draft_runs) == len(run_dirs) and section_index < len(single_draft_runs):
        return _resolve_draft(*single_draft_runs[section_index])

    return None


def _extract_preamble(source_content: str) -> str:
    """
    Extract LaTeX preamble (everything before \\begin{document}).

    Returns preamble including \\documentclass, packages, custom commands.
    """
    match = re.search(r'\\begin\{document\}', source_content)
    if match:
        return source_content[:match.start()].strip()

    # No \begin{document} found; return first 20 lines as fallback
    lines = source_content.split('\n')
    return '\n'.join(lines[:20])


def _extract_postamble(source_content: str) -> str:
    """
    Extract LaTeX postamble (everything after \\end{document}).

    Usually empty or contains only comments.
    """
    match = re.search(r'\\end\{document\}', source_content)
    if match:
        return source_content[match.end():].strip()

    return ""


def _assemble_document(
    sections: List[Dict[str, Any]],
    preamble: str,
    postamble: str
) -> str:
    """
    Assemble complete document from sections.

    sections: List of dicts with 'content', 'title', 'index'
    preamble: LaTeX preamble
    postamble: LaTeX postamble (usually empty)

    Returns complete LaTeX document as string.
    """
    # Sort sections by index to ensure correct order
    sorted_sections = sorted(sections, key=lambda s: s['index'])

    # Concatenate section content
    body_parts = []
    for section in sorted_sections:
        content = section['content'].strip()
        body_parts.append(content)

    body = '\n\n'.join(body_parts)

    # Assemble complete document
    document = f"{preamble}\n\\begin{{document}}\n\n{body}\n\n\\end{{document}}"

    if postamble:
        document += f"\n{postamble}"

    return document


def _check_latexdiff_available() -> bool:
    """Check if latexdiff is installed and available."""
    try:
        result = subprocess.run(
            ['latexdiff', '--version'],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


# Seconds allowed per chapter diff. The previous implementation allowed 60s for
# the entire document, which is optimistic for hundreds of pages of dense
# mathematics. Budgeting per chapter makes the total scale with chapter count
# rather than with document length, so a longer document takes proportionally
# longer instead of failing.
DIFF_TIMEOUT_PER_CHAPTER_SECONDS = 120


def _extract_chapters(latex_doc: str) -> List[str]:
    """
    Split a document at \\chapter or \\section boundaries.

    Concatenating the result reproduces the input exactly. That property is what
    makes per-chapter diffing safe: a splitter that dropped or duplicated text
    would surface in the blackline as authored changes that nobody made.

    Text before the first heading (front matter, preamble prose) is returned as
    its own part rather than discarded, so it still participates in the diff.
    """
    # Match complete section/chapter commands including their titles
    # This prevents latexdiff from seeing title changes as in-command edits,
    # which breaks LaTeX syntax (\section{old%DIFDELCMD...} leaves unclosed braces)
    pattern = r'(\\(?:chapter|section)\{[^}]*\})'
    parts = re.split(pattern, latex_doc)

    if len(parts) == 1:
        # No headings at all -- the whole document is one unit.
        return [latex_doc]

    chapters: List[str] = []

    # parts[0] is whatever preceded the first heading. Keep it when non-empty.
    if parts[0]:
        chapters.append(parts[0])

    # re.split with one capture group yields [pre, delim, body, delim, body, ...]
    for i in range(1, len(parts) - 1, 2):
        chapters.append(parts[i] + parts[i + 1])

    return chapters


def _generate_blacklined_diff(
    original_path: Path,
    assembled_path: Path,
    output_path: Path,
) -> Tuple[bool, List[str]]:
    """
    Generate a blacklined comparison, one latexdiff invocation per chapter.

    Returns (ok, errors). `errors` is empty on success and otherwise names each
    chapter that failed, so the caller can report which parts of the document
    could not be compared rather than only that something went wrong.

    The blackline is the deliverable, so a failure here is reported to the caller
    for abstention rather than warned about and skipped. The prior behaviour --
    print a warning, return False, let assembly exit 0 with a null blackline --
    is the fail-open shape this project has already shipped once.
    """
    original_content = original_path.read_text()
    assembled_content = assembled_path.read_text()

    # Extract document structure to wrap each chapter as a valid LaTeX document
    preamble = _extract_preamble(original_content)
    postamble = _extract_postamble(original_content)

    # Split the body only, not the full file (which would include preamble in chunk 0)
    original_body = _extract_document_body(original_content)
    assembled_body = _extract_document_body(assembled_content)

    original_chapters = _extract_chapters(original_body)
    assembled_chapters = _extract_chapters(assembled_body)

    if len(original_chapters) != len(assembled_chapters):
        # Structural divergence is expected: assembly may add or drop sections
        # relative to source. Diff the common prefix pairwise and let the
        # remainder be handled as whole-part additions or deletions by diffing
        # against an empty counterpart.
        print(
            f"Note: source has {len(original_chapters)} part(s), assembled has "
            f"{len(assembled_chapters)}; diffing pairwise and treating the "
            "remainder as added or removed",
            file=sys.stderr,
        )

    errors: List[str] = []
    diffs: List[str] = []

    total = max(len(original_chapters), len(assembled_chapters))
    with tempfile.TemporaryDirectory(prefix="hv-blackline-") as tmp:
        tmp_dir = Path(tmp)

        for index in range(total):
            original_part = (
                original_chapters[index] if index < len(original_chapters) else ""
            )
            assembled_part = (
                assembled_chapters[index] if index < len(assembled_chapters) else ""
            )

            # latexdiff requires each input to be a complete LaTeX document: it
            # refuses a fragment that carries \begin{document} without its
            # \end{document}, or neither. Splitting a real document at section
            # boundaries produces exactly those fragments, so each chunk is
            # wrapped in the source's own preamble before diffing and unwrapped
            # afterwards.
            original_chunk = tmp_dir / f"orig_{index:04d}.tex"
            assembled_chunk = tmp_dir / f"asm_{index:04d}.tex"
            original_chunk.write_text(_wrap_as_document(original_part, preamble, postamble))
            assembled_chunk.write_text(_wrap_as_document(assembled_part, preamble, postamble))

            label = _chapter_label(original_part or assembled_part, index)

            try:
                # --exclude-textcmd tells latexdiff to treat section/chapter as atomic units
                # When a section title changes, it's marked as deleted+added rather than
                # diffed internally, preventing malformed LaTeX like \section{\DIFdel{...}
                result = subprocess.run(
                    [
                        'latexdiff',
                        '--exclude-textcmd=section,chapter,subsection',
                        str(original_chunk),
                        str(assembled_chunk)
                    ],
                    capture_output=True,
                    timeout=DIFF_TIMEOUT_PER_CHAPTER_SECONDS,
                    text=True,
                )
            except subprocess.TimeoutExpired:
                errors.append(
                    f"{label}: timed out after {DIFF_TIMEOUT_PER_CHAPTER_SECONDS}s"
                )
                continue
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                continue

            if result.returncode != 0:
                detail = (result.stderr or "").strip().splitlines()
                first_line = detail[0] if detail else f"exit {result.returncode}"
                errors.append(f"{label}: {first_line}")
                continue

            # latexdiff injects \DIF* command definitions into its output's
            # preamble. Stripping them and reassembling the bodies under the
            # original preamble produces a document with markup that references
            # undefined commands. Instead, preserve the first diff's preamble
            # (which carries all the DIF definitions) and strip only the bodies
            # of subsequent diffs.
            if not diffs:
                # First diff: keep the full output, which includes the extended preamble
                diffs.append(result.stdout)
            else:
                # Subsequent diffs: extract only the body
                diff_body = _extract_document_body(result.stdout)
                diffs.append(diff_body)

    if errors:
        return False, errors

    # The first diff is a complete document with the extended preamble. Subsequent
    # diffs are bodies only. Insert them before \end{document} of the first diff.
    if not diffs:
        return False, ["no chapters diffed successfully"]

    first_diff = diffs[0]
    additional_bodies = diffs[1:]

    if additional_bodies:
        end_doc_match = re.search(r'\\end\{document\}', first_diff)
        if end_doc_match:
            insertion_point = end_doc_match.start()
            full_diff = (
                first_diff[:insertion_point]
                + "\n".join(additional_bodies)
                + "\n"
                + first_diff[insertion_point:]
            )
        else:
            # Fallback: concatenate all (shouldn't happen with valid latexdiff output)
            full_diff = "\n".join(diffs)
    else:
        full_diff = first_diff

    output_path.write_text(full_diff)
    return True, []


def _wrap_as_document(body: str, preamble: str, postamble: str) -> str:
    """Wrap a document body in preamble and postamble for latexdiff."""
    return f"{preamble}\n\\begin{{document}}\n{body}\n\\end{{document}}\n{postamble}"


def _extract_document_body(latex: str) -> str:
    """Extract content between \\begin{document} and \\end{document}."""
    begin_match = re.search(r'\\begin\{document\}', latex)
    end_match = re.search(r'\\end\{document\}', latex)

    if begin_match and end_match:
        return latex[begin_match.end():end_match.start()].strip()

    # Fallback if markers not found (shouldn't happen with valid latexdiff output)
    return latex


def _chapter_label(chunk: str, index: int) -> str:
    """Human-readable identifier for a chapter chunk, for error reporting."""
    match = re.search(r'\\(?:chapter|section)\{([^}]*)\}', chunk)
    if match:
        return f"'{match.group(1)}' (part {index})"
    return f"part {index}"


ASSEMBLY_RETENTION_THRESHOLD = 0.99


def _load_source_manifest(snapshot_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Load the source protected-object manifest written by hv init.

    Returns None when absent or unreadable. Assembly does not fail on a missing
    source manifest -- the release gate is the fail-closed point for that -- but
    it records the absence so the correspondence manifest cannot be mistaken for
    a measurement that was made against a known source.
    """
    manifest_path = snapshot_dir / ".humanvoice" / "protected_objects" / "source_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text())
    except Exception:
        return None


def _source_objects_by_hash(source_manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Flatten a source manifest's typed object lists into a hash-keyed index."""
    index: Dict[str, Dict[str, Any]] = {}
    for key in ("equations", "labels", "citations", "displaymath", "tables"):
        for obj in source_manifest.get(key, []):
            index[obj["hash"]] = obj
    return index


def _collect_approved_omissions(snapshot_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    Gather objects the drafts dropped with recorded human approval.

    An approved omission is legitimately absent from the assembled document, so
    counting it as assembly loss would penalise assembly for an editorial
    decision someone already signed. Only human_approved=True counts; an
    unapproved omission stays in the denominator and is caught by the release
    gate's disposition check.
    """
    approved: Dict[str, Dict[str, Any]] = {}
    runs_dir = snapshot_dir / ".humanvoice" / "runs"
    if not runs_dir.exists():
        return approved

    for manifest_path in sorted(runs_dir.glob("*/draft_correspondence_*.json")):
        try:
            record = json.loads(manifest_path.read_text())
        except Exception:
            continue
        for disposition in record.get("dispositions", {}).get("omitted_objects", []):
            if disposition.get("human_approved") is True and disposition.get("hash"):
                approved[disposition["hash"]] = {
                    "hash": disposition["hash"],
                    "type": disposition.get("type"),
                    "reason": disposition.get("reason"),
                    "approver": disposition.get("approver"),
                    "approval_timestamp": disposition.get("approval_timestamp"),
                    "approved_in": manifest_path.parent.name,
                }
    return approved


def _extract_hashes(content: str, label: str) -> Dict[str, Dict[str, Any]]:
    """Extract protected objects from text and index them by identity hash."""
    from humanvoice.protected_objects import extract_protected_objects_from_text

    manifest = extract_protected_objects_from_text(content, source_file=Path(label))
    objects = (manifest.equations + manifest.labels + manifest.citations +
               manifest.displaymath + manifest.tables)
    return {
        obj.hash: {"type": obj.object_type, "hash": obj.hash, "content": obj.content}
        for obj in objects
    }


def _emit_assembly_correspondence(
    snapshot_dir: Path,
    output_dir: Path,
    assembly_id: str,
    assembled_content: str,
    assembled_hash: str,
    drafted: List[Dict[str, Any]],
    source_manifest: Optional[Dict[str, Any]],
) -> Tuple[Path, Dict[str, Any]]:
    """
    Measure protected-object correspondence for the assembled document.

    Two rates are recorded because they answer different questions and only one
    of them is assembly's responsibility:

      retention_vs_drafts  -- did concatenation preserve what the section drafts
                              actually contained? Assembly is mechanical, so this
                              is the number assembly is accountable for and the
                              one gated at ASSEMBLY_RETENTION_THRESHOLD.

      retention_vs_source  -- does the finished document still carry the source's
                              objects? This is the reader-facing number. It is
                              reported, not gated here: it composes draft
                              retention with assembly retention, and draft
                              retention is already gated at its own threshold
                              with per-omission approval. Re-gating it at 99%
                              would reject runs whose omissions were properly
                              approved.
    """
    assembled_objects = _extract_hashes(assembled_content, "assembled")

    # What the drafts handed to assembly, measured from the content assembly
    # consumed rather than from the draft manifests. Assembly then verifies its
    # own input/output rather than trusting an upstream record.
    draft_objects: Dict[str, Dict[str, Any]] = {}
    for section in drafted:
        draft_objects.update(_extract_hashes(section["content"], f"draft_{section['index']}"))

    preserved_from_drafts = [
        {"type": o["type"], "hash": o["hash"]}
        for h, o in draft_objects.items() if h in assembled_objects
    ]
    lost_in_assembly = [
        {"type": o["type"], "hash": o["hash"]}
        for h, o in draft_objects.items() if h not in assembled_objects
    ]
    added_in_assembly = [
        {"type": o["type"], "hash": o["hash"]}
        for h, o in assembled_objects.items() if h not in draft_objects
    ]

    retention_vs_drafts = (
        len(preserved_from_drafts) / len(draft_objects) if draft_objects else 1.0
    )

    # Source-level accounting, with approved omissions removed from the
    # denominator so a signed editorial cut is not reported as document loss.
    approved_omissions = _collect_approved_omissions(snapshot_dir)
    source_index = _source_objects_by_hash(source_manifest) if source_manifest else {}
    expected_from_source = {
        h: o for h, o in source_index.items() if h not in approved_omissions
    }

    preserved_from_source = [
        {"type": o.get("type"), "hash": o["hash"]}
        for h, o in expected_from_source.items() if h in assembled_objects
    ]
    missing_from_source = [
        {"type": o.get("type"), "hash": o["hash"]}
        for h, o in expected_from_source.items() if h not in assembled_objects
    ]
    retention_vs_source = (
        len(preserved_from_source) / len(expected_from_source)
        if expected_from_source else (1.0 if source_manifest else None)
    )

    record = {
        "record_type": "AssemblyCorrespondenceManifest",
        "schema_version": "HV-SCHEMA-1.0",
        "assembly_id": assembly_id,
        "parent_artifact_hash": assembled_hash,
        "source_manifest_present": source_manifest is not None,
        "source_file_hash": source_manifest.get("source_file_hash") if source_manifest else None,
        "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
        "threshold": ASSEMBLY_RETENTION_THRESHOLD,
        "gated_rate": "retention_vs_drafts",
        "retention_vs_drafts": retention_vs_drafts,
        "retention_vs_source": retention_vs_source,
        # Kept under the draft manifests' key name so the release gate reads one
        # correspondence shape for both stages.
        "correspondence_to_source": {
            "preserved": [
                {"type": o.get("type"), "hash": o["hash"]}
                for o in preserved_from_source
            ],
            "missing": missing_from_source,
            "added": added_in_assembly,
        },
        "correspondence_to_drafts": {
            "preserved": preserved_from_drafts,
            "missing": lost_in_assembly,
            "added": added_in_assembly,
        },
        "counts": {
            "source_objects": len(source_index),
            "approved_omissions": len(approved_omissions),
            "expected_from_source": len(expected_from_source),
            "draft_objects": len(draft_objects),
            "assembled_objects": len(assembled_objects),
        },
        "approved_omissions": list(approved_omissions.values()),
        "dispositions": {
            "omitted_objects": [
                {
                    "hash": o["hash"],
                    "type": o.get("type"),
                    "reason": None,
                    "human_approved": False,
                    "approver": None,
                    "approval_timestamp": None,
                }
                for o in lost_in_assembly
            ]
        },
    }

    # retention_rate is the key the release gate and reader tooling read for a
    # single headline number; bind it to the gated rate so the headline and the
    # gate cannot drift apart.
    record["retention_rate"] = retention_vs_drafts

    manifest_path = output_dir / f"assembly_correspondence_{assembly_id}.json"
    manifest_path.write_text(json.dumps(record, indent=2))
    return manifest_path, record


def run(args) -> int:
    """
    Execute hv assemble command.

    Exit codes:
      0 - assembly successful
      2 - abstention (missing sections, no blueprint, correspondence below threshold)
      3 - invalid input
      4 - internal error
    """
    try:
        snapshot_dir = Path(args.snapshot).resolve()
        brief_path = Path(args.brief).resolve()

        # Validate inputs
        if not snapshot_dir.exists():
            print(f"Error: Snapshot directory not found: {snapshot_dir}", file=sys.stderr)
            return 3

        manifest = _load_manifest(snapshot_dir)
        brief = _load_brief(brief_path)

        # Find blueprint
        blueprint = _find_blueprint(snapshot_dir)
        if not blueprint:
            print("Abstention: No blueprint found; run hv plan first", file=sys.stderr)
            return 2

        if "blueprint" not in blueprint:
            print("Abstention: Blueprint missing required structure", file=sys.stderr)
            return 2

        bp = blueprint["blueprint"]

        # Issue 4: Support both legacy sections[] and new chapters[].subsections[]
        # Flatten chapters into sections for assembly, which concatenates sequentially
        if "sections" in bp:
            sections = bp["sections"]
        elif "chapters" in bp:
            sections = []
            for chapter_idx, chapter in enumerate(bp["chapters"]):
                for subsection_idx, subsection in enumerate(chapter.get("subsections", [])):
                    subsection["chapter_index"] = chapter_idx
                    subsection["chapter_title"] = chapter.get("title", f"Chapter {chapter_idx}")
                    subsection["subsection_index"] = subsection_idx
                    sections.append(subsection)
        else:
            print("Abstention: Blueprint must have 'sections' or 'chapters'", file=sys.stderr)
            return 2

        runs_dir = snapshot_dir / ".humanvoice" / "runs"

        if not runs_dir.exists():
            print("Abstention: No run records found; run hv draft for each section", file=sys.stderr)
            return 2

        # Collect drafted sections
        drafted = []
        missing_sections = []

        for i, section in enumerate(sections):
            result = _find_section_draft(runs_dir, i, section.get('title', 'Untitled'))

            if not result:
                # Structured, not a display string: the release gate reads these
                # records to decide whether the document may be published, and
                # `hv draft --missing` reads them to know what to retry.
                gap_record = {
                    "section_index": i,
                    "title": section.get("title", "Untitled"),
                    "reason": "draft_not_found",
                }
                missing_sections.append(gap_record)

                # Emit gap marker in the assembled document so the operator can see
                # exactly where each missing section belongs. Assembly produces a
                # complete document structure even with gaps -- the skeleton is
                # intact and every present section lands in the right position.
                drafted.append({
                    "index": i,
                    "title": section.get("title", "Untitled"),
                    "content": f"% MISSING: {section.get('title', 'Untitled')}\n",
                    "source_run": None,
                    "source_file": None,
                    "word_count": 0
                })
                continue

            draft_path, run_id = result
            content = draft_path.read_text()

            # Count words (rough estimate)
            word_count = len(re.findall(r'\w+', content))

            drafted.append({
                "index": i,
                "title": section.get("title", "Untitled"),
                "content": content,
                "source_run": run_id,
                "source_file": draft_path.name,
                "word_count": word_count
            })

        # Missing drafts are recorded as gaps rather than aborting the assembly.
        #
        # Aborting made the pipeline all-or-nothing, which does not survive scale:
        # at 100 units and 95% per-unit reliability a complete run arrives once in
        # 592 attempts, so the target is never reached and the operator is never
        # told which units to retry. Recording gaps makes progress convergent --
        # re-draft the three that failed rather than the hundred that did not.
        #
        # This is deliberately NOT a relaxation of the completeness requirement.
        # Assembly is a mechanical stage and is no longer the place that decides
        # whether a document may be published; release_command.check_assembly_gaps
        # is the fail-closed point. A gapped document assembles, and then cannot
        # be released until every gap is drafted or explicitly excepted.
        if missing_sections:
            print(
                f"Warning: assembled with {len(missing_sections)} gap(s); "
                "release will block until each is drafted or excepted:",
                file=sys.stderr,
            )
            for missing in missing_sections:
                print(f"  - {missing['title']} (section {missing['section_index']})",
                      file=sys.stderr)

        # Load original source for preamble/postamble
        source_files = manifest.get("source_files", [])
        if not source_files:
            print("Abstention: No source files in manifest", file=sys.stderr)
            return 2

        source_path = snapshot_dir / source_files[0]
        if not source_path.exists():
            print(f"Abstention: Source file not found: {source_path}", file=sys.stderr)
            return 2

        source_content = source_path.read_text()
        preamble = _extract_preamble(source_content)
        postamble = _extract_postamble(source_content)

        # Assemble document
        assembled_content = _assemble_document(drafted, preamble, postamble)

        # Create output directory
        if args.output:
            output_dir = Path(args.output).resolve()
        else:
            output_dir = snapshot_dir / ".humanvoice" / "revisions" / "assembled"

        output_dir.mkdir(parents=True, exist_ok=True)

        # Write assembled document
        assembled_path = output_dir / "assembled_document.tex"
        assembled_path.write_text(assembled_content)

        # Compute hash
        assembled_hash = sha256(assembled_content.encode()).hexdigest()

        # Gap record. Written unconditionally -- an empty list is a positive
        # statement that assembly found every section, which the release gate can
        # verify. Absence of the file would be ambiguous between "complete" and
        # "written by a version that did not record gaps".
        gaps_path = output_dir / "assembly_gaps.json"
        gaps_path.write_text(json.dumps(missing_sections, indent=2))

        # Generate blacklined diff if latexdiff available
        blacklined_file = None
        blackline_status = None
        diff_tool = None
        diff_tool_version = None

        # Blackline generation is controlled by --skip-blackline. When absent
        # from the argparse namespace (tests that predate the flag), default to
        # attempting generation.
        if getattr(args, 'skip_blackline', False):
            blackline_status = "skipped_by_operator"
            print(
                "Note: --skip-blackline passed; blacklined comparison not generated",
                file=sys.stderr,
            )
        elif not _check_latexdiff_available():
            blackline_status = "tool_unavailable"
            print(
                "Note: latexdiff not available; blacklined comparison not generated",
                file=sys.stderr,
            )
            print(
                "  Install with: apt-get install latexdiff (or your package manager)",
                file=sys.stderr,
            )
        else:
            blacklined_path = output_dir / "blacklined_comparison.tex"
            ok, errors = _generate_blacklined_diff(
                source_path, assembled_path, blacklined_path
            )

            if ok:
                blacklined_file = str(blacklined_path.relative_to(snapshot_dir))
                blackline_status = "generated"
                diff_tool = "latexdiff"

                # Get version
                try:
                    version_result = subprocess.run(
                        ['latexdiff', '--version'],
                        capture_output=True,
                        timeout=5,
                        text=True,
                    )
                    version_match = re.search(
                        r'(\d+\.\d+[.\d]*)', version_result.stdout
                    )
                    if version_match:
                        diff_tool_version = version_match.group(1)
                except Exception:
                    pass
            else:
                # Diff failure with the tool present is an abstention. The blackline
                # is the deliverable, so its absence is not something to warn about
                # and proceed from -- it is a reason to refuse the assembly entirely.
                #
                # This is the fail-open case Issue 8 exists to close: the prior code
                # printed a warning and exited 0, leaving blacklined_file null in a
                # way that was indistinguishable from a missing tool. A release gate
                # could not tell whether the operator had latexdiff or whether the
                # diff simply failed, so it could not refuse appropriately.
                print("Abstention: Blackline generation failed:", file=sys.stderr)
                for error in errors:
                    print(f"  {error}", file=sys.stderr)
                return 2

        # Write assembly manifest
        assembly_id = f"assembly-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

        assembly_manifest = {
            "record_type": "AssemblyManifest",
            "schema_version": "HV-SCHEMA-1.0",
            "assembly_id": assembly_id,
            "snapshot_id": manifest.get("snapshot_id", "unknown"),
            "blueprint_id": blueprint.get("blueprint_id", "unknown"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sections": [
                {
                    "section_index": s["index"],
                    "title": s["title"],
                    "source_run_id": s["source_run"],
                    "source_file": s["source_file"],
                    "word_count": s["word_count"],
                    "included": s["source_run"] is not None,  # False for gap markers
                    "abstention": None
                }
                for s in drafted
            ],
            "assembled_file": str(assembled_path.relative_to(snapshot_dir)),
            "assembled_hash": assembled_hash,
            "blacklined_file": blacklined_file,
            # Why the blackline is or is not present. A bare null could not
            # distinguish "no latexdiff on this machine" from "operator asked to
            # skip it", and the release gate needs to name the reason it refuses.
            "blackline_status": blackline_status,
            "original_source": source_files[0],
            "assembly_method": "sequential_concatenation",
            "preamble_source": "original",
            "diff_tool": diff_tool,
            "diff_tool_version": diff_tool_version,
            # Counts describe what the document actually carries, so gap markers
            # are excluded. The full blueprint length stays recoverable from
            # len(sections) above, and the shortfall from assembly_gaps.json.
            "total_sections": sum(1 for s in drafted if s["source_run"] is not None),
            "total_word_count": sum(s["word_count"] for s in drafted),
            "gap_count": len(missing_sections)
        }

        manifest_path = output_dir / "assembly_manifest.json"
        manifest_path.write_text(json.dumps(assembly_manifest, indent=2))

        # Emit assembly correspondence
        source_manifest = _load_source_manifest(snapshot_dir)
        correspondence_path, correspondence = _emit_assembly_correspondence(
            snapshot_dir,
            output_dir,
            assembly_id,
            assembled_content,
            assembled_hash,
            drafted,
            source_manifest,
        )

        # Gate on assembly retention threshold
        retention_vs_drafts = correspondence["retention_vs_drafts"]
        if retention_vs_drafts < ASSEMBLY_RETENTION_THRESHOLD:
            print(
                f"Abstention: Assembly correspondence below threshold "
                f"({retention_vs_drafts:.1%} < {ASSEMBLY_RETENTION_THRESHOLD:.0%})",
                file=sys.stderr
            )
            print(f"  Lost {len(correspondence['correspondence_to_drafts']['missing'])} objects during concatenation", file=sys.stderr)
            print(f"  Correspondence manifest: {correspondence_path}", file=sys.stderr)
            return 2

        # Output result
        result = {
            "status": "assembled",
            "assembly_id": assembly_id,
            "output": str(assembled_path),
            "manifest": str(manifest_path),
            "correspondence_manifest": str(correspondence_path),
            "sections": len(drafted),
            "word_count": assembly_manifest["total_word_count"],
            "blacklined_available": blacklined_file is not None,
            "retention_vs_drafts": retention_vs_drafts,
            "retention_vs_source": correspondence["retention_vs_source"],
        }

        print(json.dumps(result, indent=2))
        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"Internal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 4
