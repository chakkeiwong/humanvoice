#!/usr/bin/env python3
"""
Blackline PDF generation for v2 pipeline.

Generates latexdiff comparison between original source and assembled output,
using per-chapter splitting to keep diff timeouts bounded. Reuses v1 logic
with fail-closed behavior: tool unavailable, timeout, or operator skip are
all recorded explicitly in assembly result.
"""

import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple


# Seconds allowed per chapter diff. Budgeting per chapter makes the total
# scale with chapter count rather than document length.
DIFF_TIMEOUT_PER_CHAPTER_SECONDS = 120


def check_latexdiff_available() -> bool:
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


def extract_preamble(source_content: str) -> str:
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


def extract_postamble(source_content: str) -> str:
    """
    Extract LaTeX postamble (bibliography commands + everything after \\end{document}).

    Bibliography commands (\\bibliographystyle, \\bibliography{}) often appear
    before \\end{document} but must be preserved in the assembled output.
    """
    match = re.search(r'\\end\{document\}', source_content)
    if not match:
        return ""

    # Extract content after \end{document}
    post_end = source_content[match.end():].strip()

    # Extract bibliography commands before \end{document}
    before_end = source_content[:match.start()]

    # Look for bibliography commands in the last ~10 lines before \end{document}
    lines_before = before_end.rstrip().split('\n')[-10:]
    bib_commands = []
    for line in lines_before:
        stripped = line.strip()
        if stripped.startswith('\\bibliographystyle') or stripped.startswith('\\bibliography{'):
            bib_commands.append(line)

    if bib_commands:
        bib_block = '\n'.join(bib_commands)
        return f"{bib_block}\n{post_end}" if post_end else bib_block

    return post_end


def extract_document_body(latex: str) -> str:
    """Extract content between \\begin{document} and \\end{document}."""
    begin_match = re.search(r'\\begin\{document\}', latex)
    end_match = re.search(r'\\end\{document\}', latex)

    if begin_match and end_match:
        return latex[begin_match.end():end_match.start()].strip()

    return latex


def extract_chapters(latex_doc: str) -> List[str]:
    """
    Split a document at \\chapter or \\section boundaries.

    Concatenating the result reproduces the input exactly. That property is what
    makes per-chapter diffing safe: a splitter that dropped or duplicated text
    would surface in the blackline as authored changes that nobody made.

    Text before the first heading (front matter, preamble prose) is returned as
    its own part rather than discarded.
    """
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


def wrap_as_document(body: str, preamble: str, postamble: str) -> str:
    """Wrap a document body in preamble and postamble for latexdiff."""
    return f"{preamble}\n\\begin{{document}}\n{body}\n\\end{{document}}\n{postamble}"


def chapter_label(chunk: str, index: int) -> str:
    """Human-readable identifier for a chapter chunk, for error reporting."""
    match = re.search(r'\\(?:chapter|section)\{([^}]*)\}', chunk)
    if match:
        return f"'{match.group(1)}' (part {index})"
    return f"part {index}"


def generate_blacklined_diff(
    original_path: Path,
    assembled_path: Path,
    output_path: Path,
) -> Tuple[bool, List[str]]:
    """
    Generate a blacklined comparison, one latexdiff invocation per chapter.

    Returns (ok, errors). `errors` is empty on success and otherwise names each
    chapter that failed, so the caller can report which parts of the document
    could not be compared.

    The blackline is the deliverable, so a failure here is reported to the caller
    for abstention rather than warned about and skipped.
    """
    original_content = original_path.read_text()
    assembled_content = assembled_path.read_text()

    # Extract document structure to wrap each chapter as a valid LaTeX document
    preamble = extract_preamble(original_content)
    postamble = extract_postamble(original_content)

    # Split the body only, not the full file
    original_body = extract_document_body(original_content)
    assembled_body = extract_document_body(assembled_content)

    original_chapters = extract_chapters(original_body)
    assembled_chapters = extract_chapters(assembled_body)

    if len(original_chapters) != len(assembled_chapters):
        print(
            f"Note: source has {len(original_chapters)} part(s), assembled has "
            f"{len(assembled_chapters)}; diffing pairwise"
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

            # latexdiff requires each input to be a complete LaTeX document
            original_chunk = tmp_dir / f"orig_{index:04d}.tex"
            assembled_chunk = tmp_dir / f"asm_{index:04d}.tex"
            original_chunk.write_text(wrap_as_document(original_part, preamble, postamble))
            assembled_chunk.write_text(wrap_as_document(assembled_part, preamble, postamble))

            label = chapter_label(original_part or assembled_part, index)

            try:
                # --exclude-textcmd tells latexdiff to treat section/chapter as atomic
                # --type=CTRADITIONAL provides clear visual distinction
                result = subprocess.run(
                    [
                        'latexdiff',
                        '--type=CTRADITIONAL',
                        '--exclude-textcmd=section,chapter,subsection',
                        '--config=PICTUREENV=(?:picture|tikzpicture|pgfpicture|DIFnomarkup)[\\w\\d*@]*',
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

            # Preserve the first diff's preamble (which carries DIF definitions)
            # and strip only the bodies of subsequent diffs
            if not diffs:
                diffs.append(result.stdout)
            else:
                diff_body = extract_document_body(result.stdout)
                diffs.append(diff_body)

    if errors:
        return False, errors

    if not diffs:
        return False, ["no chapters diffed successfully"]

    # First diff is complete document; subsequent are bodies only
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
            full_diff = "\n".join(diffs)
    else:
        full_diff = first_diff

    output_path.write_text(full_diff)
    return True, []
