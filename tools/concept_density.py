#!/usr/bin/env python3
"""Locate conceptual pacing and first-use questions in LaTeX documents.

This is a small, dependency-free prototype inspired by the internal HPO
engagement recorded in the proposal. It applies the same heuristic to a target
and its named exemplars. The output is a worklist for a human author; it is not
a readability score, an authorship detector, or an acceptance decision.

Examples:

    python3 tools/concept_density.py draft.tex \
        --exemplar cardnpv.tex --exemplar cip.tex
    python3 tools/concept_density.py draft.tex --config brief.json --json
    python3 tools/concept_density.py --compare parent.tex child.tex

The optional configuration is JSON with ``whitelist`` (terms the reader owns)
and ``exempt_ranges`` (inclusive source-line pairs used for previews, maps,
decision boxes, or reference tables).
"""

from __future__ import annotations

import argparse
import bisect
import difflib
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


STOP = set(
    """the a an and or of to in on for with by at as is are was were be been
    from that this these those it its their our we you they he she not no if
    then than but so such via per each both all any some most more less least
    very also only even just still yet when where which who whom whose what how
    why into over under between across during within without against toward
    towards above below after before again once here there now out up down off
    own same other another new old first second third last next while because
    """.split()
)

CAP_STOP = set(
    """The A An In On For With By At As It Its Our We If Then But So Such
    Chapter Section Figure Table Equation Part Appendix Chapters Sections
    Figures Tables When Where Which Who What How Why This These Those There
    Here Not No Yes And Or Of To Every Each Both All Any Some Most More Less
    While Because Between Across Within Without Against Two Three Four Five
    One Take Suppose Write Let Given Return Returns Consider Start Recall
    Note First Second Third Fourth Finally""".split()
)

ACRO_STOP = {"II", "III", "IV", "OK", "PhD"}
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-'][A-Za-z0-9]+)*")


@dataclass(frozen=True)
class Paragraph:
    line: int
    text: str
    tokens: tuple[str, ...]
    citations: tuple[str, ...]
    emphasized: tuple[str, ...]


@dataclass(frozen=True)
class FirstUse:
    term: str
    kind: str
    line: int
    paragraph: int
    reason: str


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _strip_comments(text: str) -> str:
    return re.sub(r"(?m)(?<!\\)%.*$", "", text)


def _expand_inputs(path: Path, text: str, seen: set[Path] | None = None) -> str:
    """Inline local inputs so a top-level manuscript can be inspected."""

    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen:
        return "\n"
    seen.add(path)

    def replace(match: re.Match[str]) -> str:
        candidate = (path.parent / match.group(1)).with_suffix(".tex")
        if not candidate.is_file():
            return match.group(0)
        return _expand_inputs(candidate, candidate.read_text(encoding="utf-8", errors="ignore"), seen)

    return re.sub(r"\\input\{([^}]+)\}", replace, text)


def read_paragraphs(path: str | Path) -> list[Paragraph]:
    """Return prose paragraphs with source-line locations."""

    source_path = Path(path)
    raw = _expand_inputs(source_path, source_path.read_text(encoding="utf-8", errors="ignore"))
    raw = _strip_comments(raw)
    # Preamble commands and color definitions are implementation detail, not
    # reader-facing concepts. Analyze the document body when it has one.
    if "\\begin{document}" in raw:
        raw = raw.split("\\begin{document}", 1)[1]
    if "\\end{document}" in raw:
        raw = raw.split("\\end{document}", 1)[0]
    # Drawing, table, and verbatim bodies are not prose. Keeping captions is
    # useful because they are part of the reader's conceptual route.
    raw = re.sub(
        r"\\begin\{(tikzpicture|tabular|tabularx|longtable|lstlisting|verbatim)\}.*?"
        r"\\end\{\1\}",
        "\n",
        raw,
        flags=re.DOTALL,
    )
    paragraphs: list[Paragraph] = []
    cursor = 0
    for block in re.split(r"\n\s*\n", raw):
        line = _line_for_offset(raw, cursor)
        cursor += len(block) + 1
        citations = tuple(
            key.strip()
            for group in re.findall(
                r"\\cite[a-zA-Z*]*\s*(?:\[[^]]*\]\s*)?\{([^}]*)\}", block
            )
            for key in group.split(",")
            if key.strip()
        )
        emphasized = tuple(
            match.strip().lower()
            for match in re.findall(r"\\emph\{([^{}]{3,80})\}", block)
            if re.fullmatch(r"[a-z][a-z -]+", match.strip().lower())
        )
        text = block
        text = re.sub(
            r"\\begin\{(equation|align|gather|multline)\*?\}.*?\\end\{\1\*?\}",
            " MATHDISP ",
            text,
            flags=re.DOTALL,
        )
        text = re.sub(r"\\\[.*?\\\]|\$\$.*?\$\$", " MATHDISP ", text, flags=re.DOTALL)
        text = re.sub(r"\$[^$]*\$|\\\(.*?\\\)", " ", text, flags=re.DOTALL)
        text = re.sub(
            r"\\(?:label|ref|eqref|pageref|cref|autoref|input|include|includegraphics|"
            r"bibliography\w*)\*?(?:\[[^]]*\])?\{[^}]*\}",
            " ",
            text,
        )
        text = re.sub(r"\\cite[a-zA-Z*]*\s*(?:\[[^]]*\]\s*)?\{[^}]*\}", " CITEMARK ", text)
        for _ in range(3):
            text = re.sub(
                r"\\(?:emph|textbf|textit|texttt|mbox|text|underline)\{([^{}]*)\}",
                r" \1 ",
                text,
            )
        text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^]]*\])?(?:\{[^{}]*\})?", " ", text)
        text = re.sub(r"[{}~]", " ", text)
        tokens = tuple(TOKEN.findall(text))
        if len(tokens) >= 5:
            paragraphs.append(Paragraph(line, text, tokens, citations, emphasized))
    return paragraphs


def _norm(term: str) -> str:
    value = term.lower().strip()
    return value[:-2] if value.endswith("'s") else value


def _add(vocab: dict[str, str], term: str, kind: str) -> None:
    normalized = _norm(term)
    if len(normalized) < 2 or normalized in STOP:
        return
    vocab.setdefault(normalized, kind)


def _term_occurrences(text: str, term: str) -> int:
    pattern = r"(?<![A-Za-z0-9])" + r"\s+".join(re.escape(part) for part in term.split()) + r"(?![A-Za-z0-9])"
    return len(re.findall(pattern, text, flags=re.IGNORECASE))


def _build_vocab(paragraphs: Sequence[Paragraph]) -> dict[str, str]:
    vocab: dict[str, str] = {}
    emphasized: list[str] = []
    for paragraph in paragraphs:
        emphasized.extend(paragraph.emphasized)
        previous = "."
        for token in paragraph.tokens:
            if token in {"MATHDISP", "CITEMARK"}:
                previous = "."
                continue
            if (
                len(token) >= 2
                and sum(character.isupper() for character in token) >= 2
                and token not in ACRO_STOP
            ):
                _add(vocab, token, "acronym")
            elif (
                token[:1].isupper()
                and previous not in {None, "."}
                and token not in CAP_STOP
                and len(token) > 2
            ):
                _add(vocab, token, "proper")
            previous = token
    for term in emphasized:
        _add(vocab, term, "emphasis")

    bigrams: dict[tuple[str, str], int] = {}
    for paragraph in paragraphs:
        words = [token.lower() for token in paragraph.tokens if token.isalpha()]
        for left, right in zip(words, words[1:]):
            if left in STOP or right in STOP or len(left) < 4 or len(right) < 4:
                continue
            bigrams[(left, right)] = bigrams.get((left, right), 0) + 1
    for (left, right), count in bigrams.items():
        if count >= 4:
            _add(vocab, f"{left} {right}", "technical-bigram")

    for paragraph in paragraphs:
        for key in paragraph.citations:
            _add(vocab, key, "citation")
    return vocab


def _first_line(paragraph: Paragraph, term: str) -> int:
    pattern = r"(?<![A-Za-z0-9])" + r"\s+".join(re.escape(part) for part in term.split()) + r"(?![A-Za-z0-9])"
    match = re.search(pattern, paragraph.text, flags=re.IGNORECASE)
    if not match:
        return paragraph.line
    return paragraph.line + paragraph.text[: match.start()].count("\n")


def analyze(path: str | Path, window: int = 1500) -> dict[str, object]:
    paragraphs = read_paragraphs(path)
    vocab = _build_vocab(paragraphs)
    occurrences: list[tuple[str, str, int, int, int]] = []
    # (term, kind, paragraph index, count in paragraph, first token offset)
    offsets: list[int] = []
    running = 0
    for paragraph in paragraphs:
        offsets.append(running)
        running += len(paragraph.tokens)
    for term, kind in vocab.items():
        hits: list[tuple[int, int]] = []
        for index, paragraph in enumerate(paragraphs):
            count = _term_occurrences(paragraph.text, term)
            if count:
                hits.append((index, count))
        if hits:
            first, _ = hits[0]
            last = hits[-1][0]
            total = sum(count for _, count in hits)
            occurrences.append((term, kind, first, total, last))

    words = sum(len(paragraph.tokens) for paragraph in paragraphs)
    concept_count = len(occurrences)
    per_paragraph = [0] * len(paragraphs)
    for _, _, first, _, _ in occurrences:
        per_paragraph[first] += 1
    bursts = [
        {
            "line": paragraphs[index].line,
            "paragraph": index,
            "new_concepts": count,
            "terms": [term for term, _, first, _, _ in occurrences if first == index],
        }
        for index, count in enumerate(per_paragraph)
        if count >= 3
    ]

    intro_offsets = sorted(offsets[first] for _, _, first, _, _ in occurrences)
    live: list[int] = []
    for index, paragraph in enumerate(paragraphs):
        end = offsets[index] + len(paragraph.tokens)
        low = bisect.bisect_left(intro_offsets, max(0, end - window))
        high = bisect.bisect_right(intro_offsets, end)
        live.append(high - low)

    counts = [total for _, _, _, total, _ in occurrences]
    result: dict[str, object] = {
        "path": str(path),
        "words": words,
        "concepts": concept_count,
        "words_per_concept": (words / concept_count if concept_count else None),
        "introductions_per_1000_words": (1000 * concept_count / words if words else 0.0),
        "paragraphs": len(paragraphs),
        "singleton_share": (sum(count == 1 for count in counts) / concept_count if concept_count else 0.0),
        "mean_occurrences": (statistics.mean(counts) if counts else 0.0),
        "burst_share": (len(bursts) / len(paragraphs) if paragraphs else 0.0),
        "max_burst": max(per_paragraph, default=0),
        "live_load_mean": (statistics.mean(live) if live else 0.0),
        "live_load_p95": (statistics.quantiles(live, n=20, method="inclusive")[18] if len(live) >= 2 else (live[0] if live else 0)),
        "bursts": bursts,
        "concepts_detail": [
            {"term": term, "kind": kind, "first_line": paragraphs[first].line, "occurrences": total, "last_line": paragraphs[last].line}
            for term, kind, first, total, last in sorted(occurrences, key=lambda item: (item[2], item[0]))
        ],
    }
    return result


def compare_to_exemplars(target: dict[str, object], exemplars: Sequence[dict[str, object]]) -> dict[str, object]:
    values = [float(item["words_per_concept"]) for item in exemplars if item.get("words_per_concept")]
    if not values or not target.get("words_per_concept"):
        return {"exemplar_count": len(values), "median_words_per_concept": None, "relative_position": None}
    target_value = float(target["words_per_concept"])
    median = statistics.median(values)
    return {
        "exemplar_count": len(values),
        "median_words_per_concept": median,
        "minimum_words_per_concept": min(values),
        "maximum_words_per_concept": max(values),
        "relative_position": target_value / median if median else None,
    }


def _in_ranges(line: int, ranges: Sequence[Sequence[int]]) -> bool:
    return any(len(pair) == 2 and int(pair[0]) <= line <= int(pair[1]) for pair in ranges)


def first_use_audit(path: str | Path, whitelist: Iterable[str] = (), exempt_ranges: Sequence[Sequence[int]] = ()) -> list[FirstUse]:
    paragraphs = read_paragraphs(path)
    vocab = _build_vocab(paragraphs)
    known = {_norm(term) for term in whitelist}
    findings: list[FirstUse] = []
    for term, kind in vocab.items():
        first_index = None
        for index, paragraph in enumerate(paragraphs):
            if _term_occurrences(paragraph.text, term):
                first_index = index
                break
        if first_index is None:
            continue
        paragraph = paragraphs[first_index]
        line = _first_line(paragraph, term)
        if term in known or _in_ranges(line, exempt_ranges):
            continue
        # A nearby definition, appositive, or taught-later pointer is enough
        # for this first prototype. Ambiguous cases are intentionally emitted.
        context = paragraph.text
        escaped = re.escape(term)
        introduced = bool(
            re.search(
                rf"(?:\bis\b|\bare\b|\bmeans\b|\brefers to\b|\bcalled\b|\bknown as\b|\bdefined\b|\bmethod\b|\balgorithm\b|\bframework\b).{{0,100}}{escaped}",
                context,
                flags=re.IGNORECASE,
            )
            or re.search(rf"\(\s*{escaped}\s*\)", context, flags=re.IGNORECASE)
            or re.search(r"taught in (?:chapter|section)", context, flags=re.IGNORECASE)
        )
        if not introduced:
            findings.append(FirstUse(term, kind, line, first_index, "no introduction signal nearby"))
    return sorted(findings, key=lambda finding: (finding.line, finding.term))


ASSERTION_PATTERNS = re.compile(
    r"(?:\b\d+(?:\.\d+)?\b|\b(?:most|least|first|best|largest|smallest|widest|"
    r"more|less|higher|lower|greater|fewer|improves?|reduces?|causes?|leads?)\b)",
    flags=re.IGNORECASE,
)


def added_assertions(parent: str | Path, child: str | Path) -> list[str]:
    """Return added sentences that deserve a source or author explanation."""

    before = Path(parent).read_text(encoding="utf-8", errors="ignore")
    after = Path(child).read_text(encoding="utf-8", errors="ignore")
    before_sentences = re.split(r"(?<=[.!?])\s+", _strip_comments(before))
    after_sentences = re.split(r"(?<=[.!?])\s+", _strip_comments(after))
    matcher = difflib.SequenceMatcher(a=before_sentences, b=after_sentences, autojunk=False)
    additions: list[str] = []
    for tag, _, _, child_start, child_end in matcher.get_opcodes():
        if tag not in {"insert", "replace"}:
            continue
        for sentence in after_sentences[child_start:child_end]:
            if ASSERTION_PATTERNS.search(sentence) and not re.search(r"\\cite|https?://|DOI", sentence, flags=re.IGNORECASE):
                additions.append(sentence.strip())
    return additions


def _load_config(path: str | None) -> tuple[list[str], list[list[int]]]:
    if not path:
        return [], []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(data.get("whitelist", [])), list(data.get("exempt_ranges", []))


def _print_result(result: dict[str, object], comparison: dict[str, object] | None = None) -> None:
    print(f"document: {result['path']}")
    print(f"words={result['words']} concepts={result['concepts']} words_per_concept={result['words_per_concept']}")
    print(f"singleton_share={result['singleton_share']:.3f} burst_share={result['burst_share']:.3f} live_load_mean={result['live_load_mean']:.2f}")
    if comparison:
        print("exemplar comparison:", json.dumps(comparison, sort_keys=True))
    for burst in result["bursts"][:10]:
        print(f"  burst line {burst['line']}: +{burst['new_concepts']} {', '.join(burst['terms'][:8])}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", nargs="?", help="target LaTeX document")
    parser.add_argument("--exemplar", action="append", default=[], help="named exemplar document (repeatable)")
    parser.add_argument("--config", help="JSON file with whitelist and exempt_ranges")
    parser.add_argument("--compare", nargs=2, metavar=("PARENT", "CHILD"), help="inspect added assertions in a prose diff")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)
    if args.compare:
        additions = added_assertions(*args.compare)
        payload = {"parent": args.compare[0], "child": args.compare[1], "added_assertions": additions}
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else "\n".join(additions))
        return 0
    if not args.document:
        parser.error("a document is required unless --compare is used")
    whitelist, exempt_ranges = _load_config(args.config)
    target = analyze(args.document)
    exemplars = [analyze(path) for path in args.exemplar]
    comparison = compare_to_exemplars(target, exemplars)
    first_use = first_use_audit(args.document, whitelist, exempt_ranges)
    payload = {"target": target, "exemplars": exemplars, "comparison": comparison, "first_use_findings": [finding.__dict__ for finding in first_use]}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_result(target, comparison)
        print(f"first-use findings={len(first_use)}")
        for finding in first_use[:20]:
            print(f"  {finding.line}: {finding.term} ({finding.kind}) - {finding.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
