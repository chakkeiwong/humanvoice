# WP-V2-2 Phase 4: Model-Based Concept Extraction - Implementation Summary

## Status: COMPLETE

Phase 4 integrates model-assisted concept extraction with independent verification critics into the `hv inventory` command pipeline.

## Implementation Overview

### Core Components

1. **Model Integration** (`src/humanvoice/model_extraction.py`)
   - `extract_concepts_from_window()`: Main extraction function
   - `verify_reconstruction()`: Independent reconstruction critic
   - `verify_coverage()`: Independent coverage critic
   - Prompts include actual source text with span IDs
   - Returns structured `ConceptCandidate` objects

2. **Inventory Command Integration** (`src/humanvoice/commands/inventory_command.py`)
   - Phase 4 added after Phase 3 (window creation)
   - Loads source text and builds `span_id -> text` mapping
   - Calls extraction for each window
   - Runs independent critics on extracted concepts
   - Writes results to `.humanvoice/inventory/concepts.jsonl`

3. **Model Adapter** (`src/humanvoice/model.py`)
   - Uses existing `ModelAdapter` and `ModelConfig`
   - Loads configuration from `security/inference_profile.json`
   - Temperature fixed at 0.0 for behavioral consistency
   - Validates against inline schemas or registry types

### Extraction Flow

```
For each extraction window:
  1. Load source text for spans in window
  2. Generate extraction prompt with:
     - Source text with span IDs
     - Reader profile from brief
     - Genre expectations
     - Concept type definitions
     - Teaching role vocabulary
     - Abstention conditions
  
  3. Call model with extraction prompt
     - Returns JSON array of concept objects
     - Validates structure
     - Converts to ConceptCandidate dataclass
  
  4. Run reconstruction critic:
     - Given concepts, reconstruct source meaning
     - Compare to actual source
     - Verdict: supported | contradicted | unresolved
  
  5. Run coverage critic:
     - Check each span has ≥1 concept
     - Identify gaps in coverage
     - Verdict: covered | gap | unresolved
```

### Data Structures

**ConceptCandidate** (from `concept_extraction.py`):
```python
@dataclass
class ConceptCandidate:
    concept_id: str
    proposition: str
    concept_type: str  # definition, claim, mechanism, etc.
    source_span_ids: list[str]
    occurrence_count: int = 1
    teaching_roles: list[str] = field(default_factory=list)
    supporting_spans: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    confidence: float = 1.0
    extraction_window: Optional[str] = None
```

**ExtractionResult**:
```python
@dataclass
class ExtractionResult:
    window_index: int
    concepts: list[ConceptCandidate]
    abstentions: list[str] = field(default_factory=list)
    prompt_hash: Optional[str] = None
    model_response: Optional[ModelResponse] = None
```

### Output Files

After Phase 4, the inventory directory contains:

```
.humanvoice/inventory/
  spans.jsonl              # Source span records (Phase 1)
  protected_links.json     # Protected object mappings (Phase 2)
  concepts.jsonl           # Extracted concepts (Phase 4) ← NEW
```

Each line in `concepts.jsonl`:
```json
{
  "concept_id": "concept-001",
  "proposition": "Zero lower bound constrains monetary policy effectiveness",
  "concept_type": "claim",
  "source_span_ids": ["span-001", "span-002"],
  "teaching_roles": ["initial"],
  "supporting_spans": [],
  "prerequisites": ["monetary_policy_basics"],
  "confidence": 0.9
}
```

### Authorization Model

Phase 4 respects the security model:

1. **Remote inference authorization**: Checked via `brief.remote_inference_authorized`
2. **API key**: Required in environment (`ANTHROPIC_API_KEY`)
3. **Graceful degradation**: Skips model extraction if unauthorized
4. **Status reporting**: Returns `concept_extraction: "not_implemented" | "complete" | "no_concepts"`

### Test Coverage

**Prompt Generation Tests** (`test_model_extraction.py`):
- ✓ Extraction prompt includes source spans with text
- ✓ Extraction prompt includes reader profile
- ✓ Extraction prompt defines concept types
- ✓ Extraction prompt includes abstention conditions
- ✓ Reconstruction prompt blinds critic (concepts before source)
- ✓ Reconstruction prompt includes verdict options
- ✓ Coverage prompt includes spans and concepts
- ✓ Coverage prompt skips structural spans

**Integration Tests** (`test_inventory_command.py`):
- ✓ Phase 1 partitioning works
- ✓ Stdout JSON includes concept_extraction status
- ✓ Deterministic span ordering
- ✓ Missing snapshot/manifest/source handling

**Live Model Tests**:
- ✓ Single window extraction with real API calls
- ✓ Concept candidate construction
- ✓ Reconstruction and coverage critics

### Performance Characteristics

- **Window size**: 15 spans (configurable)
- **Overlap**: 3 spans between windows
- **Model calls per window**: 3 (extraction + reconstruction + coverage)
- **Timeout**: 300s per model call (from ModelConfig)
- **Token budget**: Tracked via BudgetTracker (not exceeded in tests)

### Known Limitations

1. **No reconciliation yet**: Duplicate concepts across windows not merged
2. **No adjudication interface**: Ambiguous concepts not surfaced to human
3. **No scaffolding classification**: Domain vs structural content not distinguished
4. **Window processing is sequential**: Could be parallelized for large documents

These are deferred to subsequent phases per the WP-V2-2 roadmap.

## Verification

Single-window extraction test (successful):
```bash
$ python -c "..." # See test in commit
Concepts extracted: 2
Abstentions: []
  - concept-001: The zero lower bound is a constraint that limits monetary policy effectiveness
    Type: definition, Confidence: 0.95
  - concept-002: The zero lower bound constraint becomes binding when nominal interest rates appr
    Type: mechanism, Confidence: 0.95
```

Test suite (all passing):
```bash
$ python -m pytest tests/test_inventory_command.py tests/test_model_extraction.py -v
======================== 20 passed in 81.21s ========================
```

## Next Steps (Future Phases)

1. **Reconciliation**: Merge duplicate concepts with identical teaching roles
2. **Scaffolding classification**: Separate domain content from structural/setup
3. **Adjudication interface**: Surface ambiguous boundaries for human review
4. **Baseline freezing**: Lock initial concept inventory as ground truth
5. **Parallel extraction**: Process windows concurrently for large documents

## Files Modified

- `src/humanvoice/model_extraction.py`: Complete implementation of extraction and critics
- `src/humanvoice/commands/inventory_command.py`: Phase 4 integration
- `tests/test_model_extraction.py`: Updated for new span_texts parameter
- `tests/test_inventory_command.py`: Updated concept_extraction status assertion

## Contract Compliance

✓ Phase 4 respects WP-V2-2 contract:
- Bounded windows (not whole manuscript)
- Independent critics (separate model calls)
- Abstention on low confidence
- All concepts link to source spans
- No self-certification (critics verify extractor output)
