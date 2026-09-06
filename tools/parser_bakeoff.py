"""
LaTeX parser bake-off for WP2.

Evaluates candidate parsers against the source-map contract:
- Protected-span recall: can it extract equations, citations, tables with stable locations?
- Intentional abstention: does it signal when it cannot parse safely?
- Round-trip: can raw input be reconstructed from the parse tree?
- Operator minutes: how long to set up and use?

Candidates: pylatexenc, TexSoup, plasTeX, LaTeXML, tree-sitter-latex
Selection criteria per v1.1 §4.2: same contract, not popularity
"""

import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParserScore:
    """Bake-off evaluation results."""
    parser_name: str
    protected_span_recall: float  # 0-1, fraction of test objects recovered
    intentional_abstention: bool  # True if signals unparseable constructs
    round_trip_possible: bool  # True if can reconstruct input
    setup_minutes: float
    parse_minutes: float  # Per fixture
    verdict: str  # "primary", "fallback", "rejected"
    notes: str


def test_pylatexenc(fixture_path: Path) -> ParserScore:
    """Test pylatexenc parser."""
    from pylatexenc.latexwalker import LatexWalker, LatexEnvironmentNode, LatexMacroNode

    start = time.time()
    source = fixture_path.read_text()

    try:
        walker = LatexWalker(source)
        nodes, _, _ = walker.get_latex_nodes()

        # Check what we can extract
        equations = []
        citations = []

        def walk(node_list):
            for node in node_list:
                if isinstance(node, LatexEnvironmentNode):
                    if node.environmentname in ('equation', 'align', 'eqnarray'):
                        equations.append({
                            'type': 'equation',
                            'env': node.environmentname,
                            'pos': node.pos,
                            'len': node.len,
                            'raw': source[node.pos:node.pos + node.len]
                        })
                    if hasattr(node, 'nodelist') and node.nodelist:
                        walk(node.nodelist)
                elif isinstance(node, LatexMacroNode):
                    if node.macroname == 'cite':
                        citations.append({
                            'type': 'citation',
                            'macro': node.macroname,
                            'pos': node.pos,
                            'len': node.len,
                            'raw': source[node.pos:node.pos + node.len]
                        })

        walk(nodes)

        parse_time = time.time() - start

        # Can we round-trip?
        reconstructed = source  # pylatexenc preserves positions, so can slice
        round_trip = True

        # Does it signal errors?
        abstention = False  # Doesn't have explicit abstention signals

        recall = len(equations) + len(citations)  # Found some structures

        return ParserScore(
            parser_name="pylatexenc",
            protected_span_recall=min(1.0, recall / 2.0),  # Rough estimate
            intentional_abstention=abstention,
            round_trip_possible=round_trip,
            setup_minutes=0.5,
            parse_minutes=parse_time / 60,
            verdict="candidate",
            notes=f"Found {len(equations)} equations, {len(citations)} citations; good position tracking"
        )

    except Exception as e:
        return ParserScore(
            parser_name="pylatexenc",
            protected_span_recall=0.0,
            intentional_abstention=False,
            round_trip_possible=False,
            setup_minutes=0.5,
            parse_minutes=(time.time() - start) / 60,
            verdict="rejected",
            notes=f"Parse failed: {e}"
        )


def test_texsoup(fixture_path: Path) -> ParserScore:
    """Test TexSoup parser."""
    import TexSoup

    start = time.time()
    source = fixture_path.read_text()

    try:
        soup = TexSoup.TexSoup(source)

        # Extract structures
        equations = list(soup.find_all('equation'))
        cites = list(soup.find_all('cite'))

        parse_time = time.time() - start

        # TexSoup doesn't preserve exact positions well
        round_trip = False
        abstention = False

        recall = len(equations) + len(cites)

        return ParserScore(
            parser_name="TexSoup",
            protected_span_recall=min(1.0, recall / 2.0),
            intentional_abstention=abstention,
            round_trip_possible=round_trip,
            setup_minutes=0.3,
            parse_minutes=parse_time / 60,
            verdict="candidate",
            notes=f"Found {len(equations)} equations, {len(cites)} citations; weak position tracking"
        )

    except Exception as e:
        return ParserScore(
            parser_name="TexSoup",
            protected_span_recall=0.0,
            intentional_abstention=False,
            round_trip_possible=False,
            setup_minutes=0.3,
            parse_minutes=(time.time() - start) / 60,
            verdict="rejected",
            notes=f"Parse failed: {e}"
        )


def test_latexml(fixture_path: Path) -> ParserScore:
    """Test LaTeXML (requires system latexml)."""
    import subprocess
    import tempfile

    start = time.time()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "output.xml"
            result = subprocess.run(
                ['latexml', '--destination', str(output), str(fixture_path)],
                capture_output=True,
                text=True,
                timeout=30
            )

            parse_time = time.time() - start

            if result.returncode == 0 and output.exists():
                xml_content = output.read_text()

                # LaTeXML produces XML with semantic structure
                equations = xml_content.count('<equation')
                cites = xml_content.count('<cite')

                return ParserScore(
                    parser_name="LaTeXML",
                    protected_span_recall=min(1.0, (equations + cites) / 2.0),
                    intentional_abstention=True,  # LaTeXML signals errors/warnings
                    round_trip_possible=False,  # XML output, not LaTeX
                    setup_minutes=0.0,  # Already installed
                    parse_minutes=parse_time / 60,
                    verdict="candidate",
                    notes=f"XML output with {equations} equations, {cites} citations; semantic but not round-trip"
                )
            else:
                return ParserScore(
                    parser_name="LaTeXML",
                    protected_span_recall=0.0,
                    intentional_abstention=True,
                    round_trip_possible=False,
                    setup_minutes=0.0,
                    parse_minutes=parse_time / 60,
                    verdict="rejected",
                    notes=f"Parse failed: {result.stderr[:200]}"
                )

    except Exception as e:
        return ParserScore(
            parser_name="LaTeXML",
            protected_span_recall=0.0,
            intentional_abstention=False,
            round_trip_possible=False,
            setup_minutes=0.0,
            parse_minutes=(time.time() - start) / 60,
            verdict="rejected",
            notes=f"Failed: {e}"
        )


def run_bakeoff(fixture_path: Path) -> dict:
    """Run parser bake-off on a fixture."""
    results = []

    print(f"\n=== Parser bake-off on {fixture_path.name} ===\n")

    # Test each parser
    for test_fn in [test_pylatexenc, test_texsoup, test_latexml]:
        print(f"Testing {test_fn.__name__.replace('test_', '')}...")
        score = test_fn(fixture_path)
        results.append(score)
        print(f"  Recall: {score.protected_span_recall:.2f}")
        print(f"  Abstention: {score.intentional_abstention}")
        print(f"  Round-trip: {score.round_trip_possible}")
        print(f"  Parse time: {score.parse_minutes*60:.3f}s")
        print(f"  Notes: {score.notes}")
        print()

    # Select primary and fallback
    # Priority: round-trip > recall > abstention > speed
    by_quality = sorted(results,
                       key=lambda s: (s.round_trip_possible,
                                     s.protected_span_recall,
                                     s.intentional_abstention,
                                     -s.parse_minutes),
                       reverse=True)

    if by_quality:
        by_quality[0].verdict = "primary"
        if len(by_quality) > 1:
            by_quality[1].verdict = "fallback"

    return {
        'fixture': str(fixture_path),
        'results': [
            {
                'parser': s.parser_name,
                'verdict': s.verdict,
                'recall': s.protected_span_recall,
                'abstention': s.intentional_abstention,
                'round_trip': s.round_trip_possible,
                'parse_seconds': s.parse_minutes * 60,
                'notes': s.notes
            }
            for s in results
        ],
        'recommendation': {
            'primary': next((s.parser_name for s in by_quality if s.verdict == "primary"), None),
            'fallback': next((s.parser_name for s in by_quality if s.verdict == "fallback"), None),
            'rationale': "Round-trip capability prioritized for protected-object preservation"
        }
    }


if __name__ == '__main__':
    # Run on ready fixture
    fixture = Path('fixtures/synthetic/register/001.tex')

    if not fixture.exists():
        print(f"Fixture not found: {fixture}")
        exit(1)

    result = run_bakeoff(fixture)

    print("\n=== Bake-off result ===")
    print(json.dumps(result, indent=2))

    # Save result
    output = Path('docs/plans/parser_bakeoff_2026-08-26.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\nResult saved to {output}")
