"""
LaTeX parser adapter implementing the source-map contract.

Primary: pylatexenc (round-trip capable, position-preserving)
Fallback: LaTeXML (semantic XML, signals errors)

Contract per WP2 §4.2:
- Typed protected objects with raw and normalized forms
- Stable source locations (char offset, line, column)
- Equation, citation, table, label, quotation extraction
- Explicit abstention when cannot parse safely
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from pathlib import Path
from enum import Enum


class ObjectType(Enum):
    """Protected object types per fixture manifest."""
    EQUATION = "equation"
    CITATION = "citation"
    TABLE = "table"
    LABEL = "label"
    MACRO = "macro"
    QUOTATION = "quotation"
    NUMBER = "number"
    QUALIFICATION = "qualification"


@dataclass
class SourceLocation:
    """Stable source location."""
    char_offset: int
    line: Optional[int] = None
    column: Optional[int] = None
    length: int = 0


@dataclass
class ProtectedObject:
    """
    Protected object with raw and normalized forms.

    Per implementation contract §6.2: preserve both representations
    so correspondence checking can distinguish explained normalization
    from substantive change.
    """
    object_id: str
    object_type: ObjectType
    raw_form: str  # Exact source text
    normalized_form: Optional[str]  # Canonical representation
    location: SourceLocation
    metadata: Dict[str, Any]  # Parser-specific annotations


@dataclass
class ParseResult:
    """
    Parser output contract.

    All adapters must produce this structure regardless of underlying
    parser implementation.
    """
    source_hash: str
    objects: List[ProtectedObject]
    abstentions: List[Dict[str, str]]  # Unparseable constructs
    parse_time_seconds: float
    parser_name: str
    parser_version: str


class PylatexencAdapter:
    """Primary parser adapter using pylatexenc."""

    def __init__(self):
        from pylatexenc.latexwalker import LatexWalker
        self.LatexWalker = LatexWalker

    def parse(self, source: str, source_hash: str) -> ParseResult:
        """Parse LaTeX source and extract protected objects."""
        import time
        from pylatexenc import latexwalker
        import pylatexenc

        start = time.time()
        walker = self.LatexWalker(source)

        objects = []
        abstentions = []
        object_counter = 0

        try:
            nodes, _, _ = walker.get_latex_nodes()

            def walk(node_list, depth=0):
                nonlocal object_counter

                for node in node_list:
                    # Extract equations and tables
                    if isinstance(node, latexwalker.LatexEnvironmentNode):
                        if node.environmentname in ('equation', 'equation*', 'align',
                                                     'align*', 'eqnarray', 'displaymath'):
                            raw = source[node.pos:node.pos + node.len]
                            obj = ProtectedObject(
                                object_id=f"eq_{object_counter}",
                                object_type=ObjectType.EQUATION,
                                raw_form=raw,
                                normalized_form=None,  # WP3 will add normalization
                                location=SourceLocation(
                                    char_offset=node.pos,
                                    length=node.len
                                ),
                                metadata={
                                    'environment': node.environmentname,
                                    'depth': depth
                                }
                            )
                            objects.append(obj)
                            object_counter += 1

                        elif node.environmentname in ('table', 'table*', 'tabular',
                                                       'tabularx', 'longtable'):
                            raw = source[node.pos:node.pos + node.len]
                            obj = ProtectedObject(
                                object_id=f"table_{object_counter}",
                                object_type=ObjectType.TABLE,
                                raw_form=raw,
                                normalized_form=None,  # WP3 adds cell-level normalization
                                location=SourceLocation(
                                    char_offset=node.pos,
                                    length=node.len
                                ),
                                metadata={
                                    'environment': node.environmentname,
                                    'depth': depth
                                }
                            )
                            objects.append(obj)
                            object_counter += 1

                        # Recurse into environment body
                        if hasattr(node, 'nodelist') and node.nodelist:
                            walk(node.nodelist, depth + 1)

                    # Extract citations
                    elif isinstance(node, latexwalker.LatexMacroNode):
                        if node.macroname in ('cite', 'citep', 'citet', 'citealp',
                                              'citealt', 'citeauthor', 'citeyear'):
                            raw = source[node.pos:node.pos + node.len]

                            # Extract citation key from arguments
                            cite_key = None
                            if node.nodeargd and node.nodeargd.argnlist:
                                for arg in node.nodeargd.argnlist:
                                    if arg and hasattr(arg, 'nodelist'):
                                        # Get text from argument nodes
                                        try:
                                            cite_key = source[arg.pos:arg.pos + arg.len].strip('{}')
                                        except:
                                            pass

                            obj = ProtectedObject(
                                object_id=f"cite_{object_counter}",
                                object_type=ObjectType.CITATION,
                                raw_form=raw,
                                normalized_form=cite_key,
                                location=SourceLocation(
                                    char_offset=node.pos,
                                    length=node.len
                                ),
                                metadata={
                                    'macro': node.macroname,
                                    'cite_key': cite_key,
                                    'depth': depth
                                }
                            )
                            objects.append(obj)
                            object_counter += 1

                        # Extract labels
                        elif node.macroname == 'label':
                            raw = source[node.pos:node.pos + node.len]
                            label_name = None
                            if node.nodeargd and node.nodeargd.argnlist:
                                for arg in node.nodeargd.argnlist:
                                    if arg and hasattr(arg, 'nodelist'):
                                        try:
                                            label_name = source[arg.pos:arg.pos + arg.len].strip('{}')
                                        except:
                                            pass

                            obj = ProtectedObject(
                                object_id=f"label_{object_counter}",
                                object_type=ObjectType.LABEL,
                                raw_form=raw,
                                normalized_form=label_name,
                                location=SourceLocation(
                                    char_offset=node.pos,
                                    length=node.len
                                ),
                                metadata={
                                    'label_name': label_name,
                                    'depth': depth
                                }
                            )
                            objects.append(obj)
                            object_counter += 1

            walk(nodes)

        except Exception as e:
            # Signal abstention when parser fails
            abstentions.append({
                'reason': 'parse_error',
                'message': str(e),
                'construct': 'unknown'
            })

        parse_time = time.time() - start

        return ParseResult(
            source_hash=source_hash,
            objects=objects,
            abstentions=abstentions,
            parse_time_seconds=parse_time,
            parser_name='pylatexenc',
            parser_version=pylatexenc.__version__
        )


def parse_latex(source: str, source_hash: str, prefer_primary: bool = True) -> ParseResult:
    """
    Parse LaTeX source with automatic fallback.

    Tries primary parser (pylatexenc); falls back to LaTeXML on failure.
    """
    if prefer_primary:
        try:
            adapter = PylatexencAdapter()
            result = adapter.parse(source, source_hash)

            # Use fallback if primary had abstentions
            if result.abstentions:
                print(f"Warning: Primary parser had {len(result.abstentions)} abstentions",
                      file=sys.stderr)

            return result

        except Exception as e:
            print(f"Warning: Primary parser failed: {e}", file=sys.stderr)
            # Fallback would go here (LaTeXML adapter)
            raise
    else:
        # Direct fallback
        raise NotImplementedError("LaTeXML fallback adapter not yet implemented")


if __name__ == '__main__':
    import sys
    from hashlib import sha256

    # Test on fixture
    fixture = Path('fixtures/synthetic/register/001.tex')
    if fixture.exists():
        source = fixture.read_text()
        source_hash = sha256(source.encode()).hexdigest()

        result = parse_latex(source, source_hash)

        print(f"Parsed with {result.parser_name} {result.parser_version}")
        print(f"Found {len(result.objects)} protected objects")
        print(f"Abstentions: {len(result.abstentions)}")
        print(f"Parse time: {result.parse_time_seconds:.3f}s")

        for obj in result.objects:
            print(f"  {obj.object_type.value}: {obj.raw_form[:50]}")
